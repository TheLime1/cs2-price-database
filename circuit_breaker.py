"""
Circuit Breaker Pattern for CS2 Price Database
Prevents cascading failures by temporarily disabling failing services
"""

import logging
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Optional, Callable, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "CLOSED"      # Normal operation
    OPEN = "OPEN"          # Circuit is open, requests fail fast
    HALF_OPEN = "HALF_OPEN"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker"""
    failure_threshold: int = 5          # Failures before opening circuit
    # Seconds before attempting recovery (5 min)
    recovery_timeout: int = 300
    success_threshold: int = 3          # Successes needed to close circuit in half-open
    timeout: int = 30                   # Request timeout in seconds


class CircuitBreakerException(Exception):
    """Exception raised when circuit breaker is open"""
    pass


class CircuitBreaker:
    """Circuit breaker implementation for API calls"""

    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED

        # Failure tracking
        self.failure_count = 0
        self.last_failure_time = None
        self.last_success_time = None

        # Half-open state tracking
        self.half_open_success_count = 0

        # Statistics
        self.total_requests = 0
        self.total_failures = 0
        self.total_successes = 0
        self.circuit_opened_count = 0

        logger.info("⚡ Circuit breaker '%s' initialized (threshold: %d failures, recovery: %ds)",
                    self.name, self.config.failure_threshold, self.config.recovery_timeout)

    def _should_attempt_reset(self) -> bool:
        """Check if circuit should attempt to reset from OPEN to HALF_OPEN"""
        if self.state != CircuitState.OPEN:
            return False

        if self.last_failure_time is None:
            return True

        time_since_failure = time.time() - self.last_failure_time
        return time_since_failure >= self.config.recovery_timeout

    def _record_success(self):
        """Record a successful operation"""
        self.failure_count = 0
        self.last_success_time = time.time()
        self.total_successes += 1

        if self.state == CircuitState.HALF_OPEN:
            self.half_open_success_count += 1
            if self.half_open_success_count >= self.config.success_threshold:
                self._close_circuit()
        elif self.state == CircuitState.OPEN:
            # Should not happen, but handle gracefully
            self._close_circuit()

    def _record_failure(self):
        """Record a failed operation"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        self.total_failures += 1

        if self.state == CircuitState.CLOSED:
            if self.failure_count >= self.config.failure_threshold:
                self._open_circuit()
        elif self.state == CircuitState.HALF_OPEN:
            # Failure during recovery attempt - go back to open
            self._open_circuit()

    def _open_circuit(self):
        """Open the circuit (fail fast mode)"""
        self.state = CircuitState.OPEN
        self.circuit_opened_count += 1
        self.half_open_success_count = 0

        logger.warning("🚨 Circuit breaker '%s' OPENED after %d failures",
                       self.name, self.failure_count)

    def _close_circuit(self):
        """Close the circuit (normal operation)"""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.half_open_success_count = 0

        logger.info(
            "✅ Circuit breaker '%s' CLOSED - service recovered", self.name)

    def _half_open_circuit(self):
        """Set circuit to half-open (testing recovery)"""
        self.state = CircuitState.HALF_OPEN
        self.half_open_success_count = 0

        logger.info(
            "🔄 Circuit breaker '%s' HALF-OPEN - testing recovery", self.name)

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a function with circuit breaker protection"""
        self.total_requests += 1

        # Check if we should attempt reset
        if self._should_attempt_reset():
            self._half_open_circuit()

        # Fail fast if circuit is open
        if self.state == CircuitState.OPEN:
            raise CircuitBreakerException(
                f"Circuit breaker '{self.name}' is OPEN. "
                f"Service unavailable for {self.config.recovery_timeout}s after {self.failure_count} failures."
            )

        # Attempt the operation
        try:
            result = func(*args, **kwargs)
            self._record_success()
            return result
        except Exception as e:
            self._record_failure()
            raise e

    async def call_async(self, func: Callable, *args, **kwargs) -> Any:
        """Execute an async function with circuit breaker protection"""
        self.total_requests += 1

        # Check if we should attempt reset
        if self._should_attempt_reset():
            self._half_open_circuit()

        # Fail fast if circuit is open
        if self.state == CircuitState.OPEN:
            raise CircuitBreakerException(
                f"Circuit breaker '{self.name}' is OPEN. "
                f"Service unavailable for {self.config.recovery_timeout}s after {self.failure_count} failures."
            )

        # Attempt the operation
        try:
            result = await func(*args, **kwargs)
            self._record_success()
            return result
        except Exception as e:
            self._record_failure()
            raise e

    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)"""
        return self.state == CircuitState.CLOSED

    def is_open(self) -> bool:
        """Check if circuit is open (failing fast)"""
        return self.state == CircuitState.OPEN

    def is_half_open(self) -> bool:
        """Check if circuit is half-open (testing recovery)"""
        return self.state == CircuitState.HALF_OPEN

    def force_open(self):
        """Manually open the circuit"""
        self._open_circuit()
        logger.warning("🔧 Circuit breaker '%s' manually OPENED", self.name)

    def force_close(self):
        """Manually close the circuit"""
        self._close_circuit()
        logger.info("🔧 Circuit breaker '%s' manually CLOSED", self.name)

    def get_stats(self) -> Dict:
        """Get circuit breaker statistics"""
        uptime_seconds = 0
        if self.last_success_time:
            uptime_seconds = time.time() - self.last_success_time

        downtime_seconds = 0
        if self.last_failure_time and self.state == CircuitState.OPEN:
            downtime_seconds = time.time() - self.last_failure_time

        return {
            'name': self.name,
            'state': self.state.value,
            'failure_count': self.failure_count,
            'total_requests': self.total_requests,
            'total_successes': self.total_successes,
            'total_failures': self.total_failures,
            'success_rate': self.total_successes / max(1, self.total_requests),
            'circuit_opened_count': self.circuit_opened_count,
            'last_failure_time': self.last_failure_time,
            'last_success_time': self.last_success_time,
            'uptime_seconds': uptime_seconds,
            'downtime_seconds': downtime_seconds,
            'config': {
                'failure_threshold': self.config.failure_threshold,
                'recovery_timeout': self.config.recovery_timeout,
                'success_threshold': self.config.success_threshold
            }
        }


class CircuitBreakerManager:
    """Manages multiple circuit breakers"""

    def __init__(self):
        self.breakers: Dict[str, CircuitBreaker] = {}

    def get_breaker(self, name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
        """Get or create a circuit breaker"""
        if name not in self.breakers:
            self.breakers[name] = CircuitBreaker(name, config)
        return self.breakers[name]

    def get_all_stats(self) -> Dict[str, Dict]:
        """Get statistics for all circuit breakers"""
        return {name: breaker.get_stats() for name, breaker in self.breakers.items()}

    def get_healthy_services(self) -> List[str]:
        """Get list of services with closed circuit breakers"""
        return [name for name, breaker in self.breakers.items() if breaker.is_closed()]

    def get_unhealthy_services(self) -> List[str]:
        """Get list of services with open circuit breakers"""
        return [name for name, breaker in self.breakers.items() if breaker.is_open()]

    def reset_all(self):
        """Reset all circuit breakers to closed state"""
        for breaker in self.breakers.values():
            breaker.force_close()
        logger.info("🔧 All circuit breakers reset to CLOSED state")


# Global circuit breaker manager instance
circuit_manager = CircuitBreakerManager()
