"""
Adaptive Concurrency Control for CS2 Price Database
Dynamically adjusts concurrent requests based on system performance
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics for concurrency adjustment"""
    success_count: int = 0
    failure_count: int = 0
    rate_limit_count: int = 0
    network_error_count: int = 0
    total_requests: int = 0
    last_reset: Optional[datetime] = None

    @property
    def error_rate(self) -> float:
        """Calculate overall error rate"""
        if self.total_requests == 0:
            return 0.0
        return self.failure_count / self.total_requests

    @property
    def success_rate(self) -> float:
        """Calculate success rate"""
        if self.total_requests == 0:
            return 1.0
        return self.success_count / self.total_requests

    def reset(self):
        """Reset metrics for next measurement period"""
        self.success_count = 0
        self.failure_count = 0
        self.rate_limit_count = 0
        self.network_error_count = 0
        self.total_requests = 0
        self.last_reset = datetime.now()


class AdaptiveConcurrencyController:
    """Dynamically adjusts concurrency based on performance metrics"""

    def __init__(self, initial_concurrency: int = 19, min_concurrency: int = 3, max_concurrency: int = 50):
        self.current_concurrency = initial_concurrency
        self.min_concurrency = min_concurrency
        self.max_concurrency = max_concurrency
        self.metrics = PerformanceMetrics()
        self.adjustment_history = []
        self.last_adjustment = datetime.now()
        self.adjustment_cooldown = 30  # seconds between adjustments

        logger.info("🎛️ Adaptive concurrency initialized: %d (range: %d-%d)",
                    initial_concurrency, min_concurrency, max_concurrency)

    def record_success(self):
        """Record a successful request"""
        self.metrics.success_count += 1
        self.metrics.total_requests += 1

    def record_failure(self, failure_type: str = "general"):
        """Record a failed request with type classification"""
        self.metrics.failure_count += 1
        self.metrics.total_requests += 1

        if "rate limit" in failure_type.lower() or "429" in failure_type:
            self.metrics.rate_limit_count += 1
        elif "network" in failure_type.lower() or "connection" in failure_type.lower():
            self.metrics.network_error_count += 1

    def should_adjust(self) -> bool:
        """Check if enough time has passed and we have enough data for adjustment"""
        if self.metrics.total_requests < 10:  # Need minimum sample size
            return False

        time_since_adjustment = datetime.now() - self.last_adjustment
        return time_since_adjustment.total_seconds() >= self.adjustment_cooldown

    def calculate_new_concurrency(self, proxy_count: int) -> Tuple[int, str]:
        """Calculate optimal concurrency based on current metrics"""
        error_rate = self.metrics.error_rate
        rate_limit_rate = self.metrics.rate_limit_count / \
            max(1, self.metrics.total_requests)
        network_error_rate = self.metrics.network_error_count / \
            max(1, self.metrics.total_requests)

        logger.debug("📊 Metrics: %d requests, %.1f%% error rate, %.1f%% rate limits, %.1f%% network errors",
                     self.metrics.total_requests, error_rate * 100,
                     rate_limit_rate * 100, network_error_rate * 100)

        new_concurrency = self.current_concurrency
        adjustment_reason = ""

        # High rate limiting - aggressive reduction
        if rate_limit_rate > 0.3:  # >30% rate limits
            new_concurrency = max(self.min_concurrency,
                                  self.current_concurrency // 2)
            adjustment_reason = "high rate limiting (%.1f%%)" % (
                rate_limit_rate * 100)

        # High network errors - moderate reduction
        elif network_error_rate > 0.4:  # >40% network errors
            new_concurrency = max(self.min_concurrency, int(
                self.current_concurrency * 0.7))
            adjustment_reason = "high network errors (%.1f%%)" % (
                network_error_rate * 100)

        # High general error rate - gradual reduction
        elif error_rate > 0.5:  # >50% total errors
            new_concurrency = max(self.min_concurrency,
                                  self.current_concurrency - 2)
            adjustment_reason = "high error rate (%.1f%%)" % (error_rate * 100)

        # Moderate errors - small reduction
        elif error_rate > 0.3:  # >30% errors
            new_concurrency = max(self.min_concurrency,
                                  self.current_concurrency - 1)
            adjustment_reason = "moderate error rate (%.1f%%)" % (
                error_rate * 100)

        # Low errors and good performance - try to increase
        elif error_rate < 0.1 and self.metrics.success_rate > 0.9:  # <10% errors, >90% success
            # Only increase if we have healthy proxies
            max_safe_concurrency = min(self.max_concurrency, proxy_count)
            if self.current_concurrency < max_safe_concurrency:
                new_concurrency = min(
                    max_safe_concurrency, self.current_concurrency + 2)
                adjustment_reason = "good performance (%.1f%% errors)" % (
                    error_rate * 100)

        # Limit concurrency based on available proxies
        new_concurrency = min(new_concurrency, proxy_count)

        return new_concurrency, adjustment_reason

    def adjust_concurrency(self, proxy_count: int) -> bool:
        """Adjust concurrency if conditions are met"""
        if not self.should_adjust():
            return False

        new_concurrency, reason = self.calculate_new_concurrency(proxy_count)

        if new_concurrency != self.current_concurrency:
            old_concurrency = self.current_concurrency
            self.current_concurrency = new_concurrency

            # Record adjustment
            self.adjustment_history.append({
                'timestamp': datetime.now(),
                'old_concurrency': old_concurrency,
                'new_concurrency': new_concurrency,
                'reason': reason,
                'metrics': {
                    'error_rate': self.metrics.error_rate,
                    'success_rate': self.metrics.success_rate,
                    'total_requests': self.metrics.total_requests
                }
            })

            # Keep only recent history
            if len(self.adjustment_history) > 20:
                self.adjustment_history = self.adjustment_history[-20:]

            logger.info("🎛️ Concurrency adjusted: %d → %d (%s)",
                        old_concurrency, new_concurrency, reason)

            self.last_adjustment = datetime.now()
            self.metrics.reset()
            return True

        return False

    def get_current_concurrency(self) -> int:
        """Get current concurrency setting"""
        return self.current_concurrency

    def force_adjustment(self, new_concurrency: int, reason: str = "manual"):
        """Force concurrency to a specific value"""
        old_concurrency = self.current_concurrency
        self.current_concurrency = max(self.min_concurrency, min(
            self.max_concurrency, new_concurrency))

        logger.info("🎛️ Concurrency forced: %d → %d (%s)",
                    old_concurrency, self.current_concurrency, reason)
        self.last_adjustment = datetime.now()
        self.metrics.reset()

    def get_adjustment_history(self) -> List[Dict]:
        """Get recent adjustment history"""
        return self.adjustment_history.copy()

    def get_performance_summary(self) -> Dict:
        """Get current performance summary"""
        return {
            'current_concurrency': self.current_concurrency,
            'metrics': {
                'total_requests': self.metrics.total_requests,
                'error_rate': self.metrics.error_rate,
                'success_rate': self.metrics.success_rate,
                'rate_limit_count': self.metrics.rate_limit_count,
                'network_error_count': self.metrics.network_error_count
            },
            'last_adjustment': self.last_adjustment,
            'adjustment_count': len(self.adjustment_history)
        }


class RequestPrioritizer:
    """Prioritizes requests based on likelihood of success"""

    def __init__(self):
        self.item_success_history = {}  # item_name -> success_rate
        self.item_last_success = {}     # item_name -> timestamp
        self.item_volume_data = {}      # item_name -> volume info

    def record_item_result(self, item_name: str, success: bool, volume: Optional[int] = None):
        """Record success/failure for an item"""
        if item_name not in self.item_success_history:
            self.item_success_history[item_name] = {'success': 0, 'total': 0}

        self.item_success_history[item_name]['total'] += 1
        if success:
            self.item_success_history[item_name]['success'] += 1
            self.item_last_success[item_name] = datetime.now()

        if volume is not None:
            self.item_volume_data[item_name] = volume

    def get_item_priority_score(self, item_name: str) -> float:
        """Calculate priority score for an item (higher = better priority)"""
        score = 0.5  # Base score

        # Success rate factor (0.0 to 1.0)
        if item_name in self.item_success_history:
            history = self.item_success_history[item_name]
            if history['total'] > 0:
                success_rate = history['success'] / history['total']
                score += success_rate * 0.4  # Up to +0.4

        # Recent success factor (0.0 to 0.3)
        if item_name in self.item_last_success:
            hours_since_success = (
                datetime.now() - self.item_last_success[item_name]).total_seconds() / 3600
            if hours_since_success < 24:
                score += 0.3 * (1 - hours_since_success / 24)

        # Volume factor (0.0 to 0.2)
        if item_name in self.item_volume_data:
            volume = self.item_volume_data[item_name]
            if volume > 100:
                score += 0.2  # High volume items
            elif volume > 10:
                score += 0.1  # Medium volume items

        return min(1.0, score)

    def prioritize_requests(self, requests: List[tuple]) -> List[tuple]:
        """Sort requests by priority (highest first)"""
        def get_priority(request_tuple):
            # Extract item name from request tuple structure
            if len(request_tuple) >= 2:
                skin = request_tuple[1] if isinstance(
                    request_tuple[1], dict) else request_tuple[0]
                item_name = skin.get('name', '') if isinstance(
                    skin, dict) else str(skin)
                return self.get_item_priority_score(item_name)
            return 0.5

        sorted_requests = sorted(requests, key=get_priority, reverse=True)

        logger.debug(
            "📋 Prioritized %d requests based on success history", len(requests))
        return sorted_requests
