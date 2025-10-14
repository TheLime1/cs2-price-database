"""
Proxy Health Monitoring for CS2 Price Database
Tracks proxy performance and automatically disables failing proxies
"""

import logging
import asyncio
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
from enum import Enum

logger = logging.getLogger(__name__)


class ProxyStatus(Enum):
    """Proxy health status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    QUARANTINED = "quarantined"


@dataclass
class ProxyMetrics:
    """Health metrics for a single proxy"""
    proxy: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    timeouts: int = 0
    connection_errors: int = 0
    avg_response_time: float = 0.0
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    status: ProxyStatus = ProxyStatus.HEALTHY
    quarantine_until: Optional[datetime] = None
    consecutive_failures: int = 0
    response_times: List[float] = field(default_factory=list)

    def get_success_rate(self) -> float:
        """Calculate success rate percentage"""
        if self.total_requests == 0:
            return 1.0  # Optimistic for new proxies
        return self.successful_requests / self.total_requests

    def get_failure_rate(self) -> float:
        """Calculate failure rate percentage"""
        return 1.0 - self.get_success_rate()

    def update_response_time(self, response_time: float):
        """Update average response time with new measurement"""
        self.response_times.append(response_time)
        # Keep only last 100 measurements
        if len(self.response_times) > 100:
            self.response_times.pop(0)

        if self.response_times:
            self.avg_response_time = sum(
                self.response_times) / len(self.response_times)


@dataclass
class ProxyHealthConfig:
    """Configuration for proxy health monitoring"""
    healthy_success_rate: float = 0.8  # 80% success rate for healthy
    degraded_success_rate: float = 0.5  # 50% success rate for degraded
    unhealthy_success_rate: float = 0.2  # 20% success rate for unhealthy
    max_consecutive_failures: int = 5  # Quarantine after 5 consecutive failures
    quarantine_duration: int = 300  # 5 minutes quarantine
    min_requests_for_evaluation: int = 10  # Minimum requests before evaluation
    response_time_threshold: float = 10.0  # 10 seconds is slow
    health_check_interval: int = 60  # Check health every minute
    cleanup_old_data_hours: int = 24  # Clean data older than 24 hours


class ProxyHealthTracker:
    """Monitors and tracks proxy health"""

    def __init__(self, config: Optional[ProxyHealthConfig] = None):
        self.config = config or ProxyHealthConfig()
        self.metrics: Dict[str, ProxyMetrics] = {}
        self.status_history: Dict[str, List[tuple]
                                  ] = defaultdict(list)  # (timestamp, status)
        self._health_check_task: Optional[asyncio.Task] = None

        logger.info("🏥 Proxy health tracker initialized (Healthy: %.0f%%, Degraded: %.0f%%, Unhealthy: %.0f%%)",
                    self.config.healthy_success_rate * 100,
                    self.config.degraded_success_rate * 100,
                    self.config.unhealthy_success_rate * 100)

    def start_health_monitoring(self):
        """Start background health monitoring"""
        if self._health_check_task is None or self._health_check_task.done():
            self._health_check_task = asyncio.create_task(
                self._health_check_loop())
            logger.info("🔄 Started proxy health monitoring background task")

    def stop_health_monitoring(self):
        """Stop background health monitoring"""
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            logger.info("⏹️ Stopped proxy health monitoring background task")

    async def _health_check_loop(self):
        """Background health check loop"""
        while True:
            try:
                await asyncio.sleep(self.config.health_check_interval)
                self._update_all_proxy_status()
                self._cleanup_old_data()
            except asyncio.CancelledError:
                logger.info("🛑 Health monitoring task cancelled")
                raise
            except Exception as e:
                logger.error("❌ Error in health check loop: %s", str(e))

    def record_request(self, proxy: str, success: bool, response_time: Optional[float] = None, error_type: Optional[str] = None):
        """Record a proxy request result"""
        if proxy not in self.metrics:
            self.metrics[proxy] = ProxyMetrics(proxy=proxy)

        metrics = self.metrics[proxy]
        metrics.total_requests += 1

        if success:
            metrics.successful_requests += 1
            metrics.consecutive_failures = 0
            metrics.last_success = datetime.now()

            if response_time is not None:
                metrics.update_response_time(response_time)
        else:
            metrics.failed_requests += 1
            metrics.consecutive_failures += 1
            metrics.last_failure = datetime.now()

            # Track error types
            if error_type:
                if "timeout" in error_type.lower():
                    metrics.timeouts += 1
                elif "connection" in error_type.lower():
                    metrics.connection_errors += 1

        # Update status after each request
        self._update_proxy_status(proxy)

        logger.debug("📊 Proxy %s: %d/%d success (%.1f%%), status: %s",
                     proxy[:15], metrics.successful_requests, metrics.total_requests,
                     metrics.get_success_rate() * 100, metrics.status.value)

    def _update_proxy_status(self, proxy: str):
        """Update status for a specific proxy"""
        if proxy not in self.metrics:
            return

        metrics = self.metrics[proxy]
        old_status = metrics.status

        # Check if quarantined and time is up
        if (metrics.status == ProxyStatus.QUARANTINED and
            metrics.quarantine_until and
                datetime.now() > metrics.quarantine_until):
            metrics.status = ProxyStatus.HEALTHY
            metrics.quarantine_until = None
            logger.info("🔓 Proxy %s released from quarantine", proxy)

        # Don't update if quarantined
        if metrics.status == ProxyStatus.QUARANTINED:
            return

        # Quarantine if too many consecutive failures
        if metrics.consecutive_failures >= self.config.max_consecutive_failures:
            metrics.status = ProxyStatus.QUARANTINED
            metrics.quarantine_until = datetime.now(
            ) + timedelta(seconds=self.config.quarantine_duration)
            logger.warning("🚨 Proxy %s quarantined for %d consecutive failures",
                           proxy, metrics.consecutive_failures)

        # Only evaluate if we have enough data
        elif metrics.total_requests >= self.config.min_requests_for_evaluation:
            success_rate = metrics.get_success_rate()

            if success_rate >= self.config.healthy_success_rate:
                metrics.status = ProxyStatus.HEALTHY
            elif success_rate >= self.config.degraded_success_rate:
                metrics.status = ProxyStatus.DEGRADED
            elif success_rate >= self.config.unhealthy_success_rate:
                metrics.status = ProxyStatus.UNHEALTHY
            else:
                # Very poor performance - quarantine
                metrics.status = ProxyStatus.QUARANTINED
                metrics.quarantine_until = datetime.now(
                ) + timedelta(seconds=self.config.quarantine_duration)
                logger.warning("🚨 Proxy %s quarantined for poor performance (%.1f%%)",
                               proxy, success_rate * 100)

        # Log status changes
        if old_status != metrics.status:
            self._record_status_change(proxy, old_status, metrics.status)
            logger.info("🔄 Proxy %s status: %s → %s (%.1f%% success)",
                        proxy[:15], old_status.value, metrics.status.value,
                        metrics.get_success_rate() * 100)

    def _update_all_proxy_status(self):
        """Update status for all proxies"""
        for proxy in self.metrics:
            self._update_proxy_status(proxy)

    def _record_status_change(self, proxy: str, old_status: ProxyStatus, new_status: ProxyStatus):
        """Record a status change in history"""
        self.status_history[proxy].append(
            (datetime.now(), old_status, new_status))

        # Keep only last 100 status changes per proxy
        if len(self.status_history[proxy]) > 100:
            self.status_history[proxy].pop(0)

    def _cleanup_old_data(self):
        """Clean up old response time data"""
        for metrics in self.metrics.values():
            # Clean old response times (keep last 100 anyway)
            if len(metrics.response_times) > 100:
                metrics.response_times = metrics.response_times[-100:]

    def get_healthy_proxies(self) -> List[str]:
        """Get list of healthy proxies"""
        return [
            proxy for proxy, metrics in self.metrics.items()
            if metrics.status == ProxyStatus.HEALTHY
        ]

    def get_usable_proxies(self) -> List[str]:
        """Get list of usable proxies (healthy + degraded)"""
        return [
            proxy for proxy, metrics in self.metrics.items()
            if metrics.status in [ProxyStatus.HEALTHY, ProxyStatus.DEGRADED]
        ]

    def get_backup_proxies(self) -> List[str]:
        """Get backup proxies sorted by performance"""
        usable = self.get_usable_proxies()

        # Sort by success rate (best first)
        return sorted(usable, key=lambda p: self.metrics[p].get_success_rate(), reverse=True)

    def get_proxy_status(self, proxy: str) -> Optional[ProxyStatus]:
        """Get status of a specific proxy"""
        return self.metrics[proxy].status if proxy in self.metrics else None

    def is_proxy_usable(self, proxy: str) -> bool:
        """Check if a proxy is usable"""
        if proxy not in self.metrics:
            return True  # Optimistic for unknown proxies

        status = self.metrics[proxy].status
        return status in [ProxyStatus.HEALTHY, ProxyStatus.DEGRADED]

    def get_proxy_metrics(self, proxy: str) -> Optional[ProxyMetrics]:
        """Get detailed metrics for a proxy"""
        return self.metrics.get(proxy)

    def get_all_metrics(self) -> Dict[str, ProxyMetrics]:
        """Get all proxy metrics"""
        return self.metrics.copy()

    def get_health_summary(self) -> Dict:
        """Get overall health summary"""
        if not self.metrics:
            return {
                'total_proxies': 0,
                'healthy': 0,
                'degraded': 0,
                'unhealthy': 0,
                'quarantined': 0,
                'overall_success_rate': 0.0
            }

        status_counts = defaultdict(int)
        total_requests = 0
        total_successes = 0

        for metrics in self.metrics.values():
            status_counts[metrics.status] += 1
            total_requests += metrics.total_requests
            total_successes += metrics.successful_requests

        overall_success_rate = total_successes / max(1, total_requests)

        return {
            'total_proxies': len(self.metrics),
            'healthy': status_counts[ProxyStatus.HEALTHY],
            'degraded': status_counts[ProxyStatus.DEGRADED],
            'unhealthy': status_counts[ProxyStatus.UNHEALTHY],
            'quarantined': status_counts[ProxyStatus.QUARANTINED],
            'overall_success_rate': overall_success_rate,
            'total_requests': total_requests,
            'total_successes': total_successes
        }

    def get_top_performers(self, limit: int = 10) -> List[tuple]:
        """Get top performing proxies"""
        if not self.metrics:
            return []

        # Filter to proxies with enough data
        qualified = [
            (proxy, metrics) for proxy, metrics in self.metrics.items()
            if metrics.total_requests >= self.config.min_requests_for_evaluation
        ]

        # Sort by success rate
        qualified.sort(key=lambda x: x[1].get_success_rate(), reverse=True)

        return [(proxy, metrics.get_success_rate(), metrics.avg_response_time)
                for proxy, metrics in qualified[:limit]]

    def get_worst_performers(self, limit: int = 10) -> List[tuple]:
        """Get worst performing proxies"""
        if not self.metrics:
            return []

        # Filter to proxies with enough data
        qualified = [
            (proxy, metrics) for proxy, metrics in self.metrics.items()
            if metrics.total_requests >= self.config.min_requests_for_evaluation
        ]

        # Sort by success rate (worst first)
        qualified.sort(key=lambda x: x[1].get_success_rate())

        return [(proxy, metrics.get_success_rate(), metrics.avg_response_time)
                for proxy, metrics in qualified[:limit]]
