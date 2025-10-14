"""
Smart Retry Logic with Escalation for CS2 Price Database
Implements escalating retry strategies from API -> Fallback -> Manual Review
"""

import logging
import asyncio
from typing import Dict, Optional, Any, Callable, List, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class RetryMethod(Enum):
    """Available retry methods"""
    API = "api"
    API_BACKUP_PROXY = "api_backup"
    FALLBACK_SCRAPER = "fallback"
    MANUAL_REVIEW = "manual"


class RetryResult(Enum):
    """Retry attempt results"""
    SUCCESS = "success"
    FAILURE = "failure"
    EXHAUSTED = "exhausted"
    CIRCUIT_OPEN = "circuit_open"


@dataclass
class RetryAttempt:
    """Record of a retry attempt"""
    method: RetryMethod
    timestamp: datetime
    result: RetryResult
    error: Optional[str] = None
    response_time: Optional[float] = None
    proxy_used: Optional[str] = None


@dataclass
class RetryConfig:
    """Configuration for retry logic"""
    api_max_attempts: int = 3
    api_backup_proxies: int = 2
    enable_fallback: bool = True
    enable_manual_review: bool = True
    initial_delay: float = 1.0
    backoff_multiplier: float = 2.0
    max_delay: float = 30.0


class SmartRetryHandler:
    """Handles intelligent retry logic with escalation"""

    def __init__(self, config: Optional[RetryConfig] = None):
        self.config = config or RetryConfig()
        self.retry_history: Dict[str, List[RetryAttempt]] = {}
        self.manual_review_queue: List[Dict] = []

        # Success rate tracking per method
        self.method_stats = {
            RetryMethod.API: {'attempts': 0, 'successes': 0},
            RetryMethod.API_BACKUP_PROXY: {'attempts': 0, 'successes': 0},
            RetryMethod.FALLBACK_SCRAPER: {'attempts': 0, 'successes': 0}
        }

        logger.info("🔄 Smart retry handler initialized (API: %d attempts, Backup: %d proxies, Fallback: %s)",
                    self.config.api_max_attempts, self.config.api_backup_proxies,
                    "enabled" if self.config.enable_fallback else "disabled")

    def _record_attempt(self, item_key: str, attempt: RetryAttempt):
        """Record a retry attempt"""
        if item_key not in self.retry_history:
            self.retry_history[item_key] = []

        self.retry_history[item_key].append(attempt)

        # Update method statistics
        if attempt.method in self.method_stats:
            self.method_stats[attempt.method]['attempts'] += 1
            if attempt.result == RetryResult.SUCCESS:
                self.method_stats[attempt.method]['successes'] += 1

    def _get_success_rate(self, method: RetryMethod) -> float:
        """Get success rate for a retry method"""
        stats = self.method_stats.get(method, {'attempts': 0, 'successes': 0})
        if stats['attempts'] == 0:
            return 1.0  # Optimistic for new methods
        return stats['successes'] / stats['attempts']

    def _should_skip_method(self, method: RetryMethod) -> bool:
        """Check if a method should be skipped due to poor performance"""
        success_rate = self._get_success_rate(method)
        attempts = self.method_stats.get(method, {}).get('attempts', 0)

        # Skip if method has poor success rate and enough attempts
        if attempts >= 10 and success_rate < 0.1:  # <10% success with enough data
            return True

        return False

    def _calculate_delay(self, attempt_number: int) -> float:
        """Calculate delay with exponential backoff"""
        delay = self.config.initial_delay * \
            (self.config.backoff_multiplier ** (attempt_number - 1))
        return min(delay, self.config.max_delay)

    async def retry_with_escalation(
        self,
        item_key: str,
        api_func: Callable,
        fallback_func: Optional[Callable] = None,
        proxy_manager: Optional[Any] = None,
        **kwargs
    ) -> Tuple[Any, RetryMethod]:
        """
        Attempt to get data with escalating retry strategy

        Args:
            item_key: Unique identifier for the item being processed
            api_func: Primary API function to call
            fallback_func: Fallback scraper function
            proxy_manager: Proxy manager for getting backup proxies
            **kwargs: Additional arguments for the functions

        Returns:
            Tuple of (result, successful_method) or (None, RetryMethod.EXHAUSTED)
        """
        start_time = datetime.now()
        total_attempts = 0

        logger.debug("🎯 Starting escalated retry for item: %s", item_key)

        # Phase 1: Primary API attempts
        result, method, attempts = await self._try_api_primary(item_key, api_func, kwargs)
        total_attempts += attempts
        if result and method:
            return result, method

        # Phase 2: API with backup proxies
        result, method, attempts = await self._try_api_backup(item_key, api_func, proxy_manager, kwargs)
        total_attempts += attempts
        if result and method:
            return result, method

        # Phase 3: Fallback scraper
        if fallback_func:
            result, method, attempts = await self._try_fallback(item_key, fallback_func, kwargs)
            total_attempts += attempts
            if result and method:
                return result, method

        # Phase 4: Manual review queue
        self._add_to_manual_review(
            item_key, start_time, total_attempts, kwargs)

        # All methods exhausted
        logger.error(
            "💥 All retry methods exhausted for %s after %d attempts", item_key, total_attempts)
        return None, RetryMethod.MANUAL_REVIEW

    async def _try_api_primary(self, item_key: str, api_func: Callable, kwargs: Dict) -> Tuple[Optional[Any], Optional[RetryMethod], int]:
        """Try primary API with retries"""
        attempts = 0

        if self._should_skip_method(RetryMethod.API):
            return None, None, attempts

        for attempt in range(1, self.config.api_max_attempts + 1):
            attempts += 1
            attempt_start = datetime.now()

            try:
                logger.debug("🌐 API attempt %d/%d for %s",
                             attempt, self.config.api_max_attempts, item_key)

                result = await api_func(**kwargs)
                response_time = (datetime.now() -
                                 attempt_start).total_seconds()

                if result:  # Success
                    self._record_attempt(item_key, RetryAttempt(
                        method=RetryMethod.API,
                        timestamp=attempt_start,
                        result=RetryResult.SUCCESS,
                        response_time=response_time
                    ))

                    logger.debug("✅ API success for %s after %d attempts (%.2fs)",
                                 item_key, attempt, response_time)
                    return result, RetryMethod.API, attempts

            except Exception as e:
                response_time = (datetime.now() -
                                 attempt_start).total_seconds()
                error_msg = str(e)

                self._record_attempt(item_key, RetryAttempt(
                    method=RetryMethod.API,
                    timestamp=attempt_start,
                    result=RetryResult.FAILURE,
                    error=error_msg,
                    response_time=response_time
                ))

                logger.debug("❌ API attempt %d failed for %s: %s (%.2fs)",
                             attempt, item_key, error_msg, response_time)

                # Check if it's a circuit breaker exception
                if "Circuit breaker" in error_msg:
                    logger.info(
                        "⚡ API circuit breaker open for %s - skipping to fallback", item_key)
                    break

            # Delay before next attempt (except last attempt)
            if attempt < self.config.api_max_attempts:
                delay = self._calculate_delay(attempt)
                await asyncio.sleep(delay)

        return None, None, attempts

    async def _try_api_backup(self, item_key: str, api_func: Callable, proxy_manager: Any, kwargs: Dict) -> Tuple[Optional[Any], Optional[RetryMethod], int]:
        """Try API with backup proxies"""
        attempts = 0

        if (not proxy_manager or not hasattr(proxy_manager, 'get_backup_proxies') or
                self._should_skip_method(RetryMethod.API_BACKUP_PROXY)):
            return None, None, attempts

        backup_proxies = getattr(
            proxy_manager, 'get_backup_proxies', lambda: [])()
        backup_count = min(len(backup_proxies), self.config.api_backup_proxies)

        for i, proxy in enumerate(backup_proxies[:backup_count]):
            attempts += 1
            attempt_start = datetime.now()

            try:
                logger.debug("🔄 API backup proxy attempt %d/%d for %s (proxy: %s)",
                             i + 1, backup_count, item_key, proxy)

                # Update kwargs with backup proxy
                backup_kwargs = kwargs.copy()
                backup_kwargs['proxy'] = proxy

                result = await api_func(**backup_kwargs)
                response_time = (datetime.now() -
                                 attempt_start).total_seconds()

                if result:  # Success
                    self._record_attempt(item_key, RetryAttempt(
                        method=RetryMethod.API_BACKUP_PROXY,
                        timestamp=attempt_start,
                        result=RetryResult.SUCCESS,
                        response_time=response_time,
                        proxy_used=proxy
                    ))

                    logger.debug("✅ API backup success for %s with proxy %s (%.2fs)",
                                 item_key, proxy, response_time)
                    return result, RetryMethod.API_BACKUP_PROXY, attempts

            except Exception as e:
                response_time = (datetime.now() -
                                 attempt_start).total_seconds()

                self._record_attempt(item_key, RetryAttempt(
                    method=RetryMethod.API_BACKUP_PROXY,
                    timestamp=attempt_start,
                    result=RetryResult.FAILURE,
                    error=str(e),
                    response_time=response_time,
                    proxy_used=proxy
                ))

                logger.debug("❌ API backup failed for %s with proxy %s: %s",
                             item_key, proxy, str(e))

            # Small delay between backup attempts
            if i < backup_count - 1:
                await asyncio.sleep(1.0)

        return None, None, attempts

    async def _try_fallback(self, item_key: str, fallback_func: Callable, kwargs: Dict) -> Tuple[Optional[Any], Optional[RetryMethod], int]:
        """Try fallback scraper"""
        attempts = 0

        if (not fallback_func or not self.config.enable_fallback or
                self._should_skip_method(RetryMethod.FALLBACK_SCRAPER)):
            return None, None, attempts

        attempts = 1
        attempt_start = datetime.now()

        try:
            logger.debug("🕷️ Fallback scraper attempt for %s", item_key)

            result = await fallback_func(**kwargs)
            response_time = (datetime.now() - attempt_start).total_seconds()

            if result:  # Success
                self._record_attempt(item_key, RetryAttempt(
                    method=RetryMethod.FALLBACK_SCRAPER,
                    timestamp=attempt_start,
                    result=RetryResult.SUCCESS,
                    response_time=response_time
                ))

                logger.info("✅ Fallback success for %s (%.2fs)",
                            item_key, response_time)
                return result, RetryMethod.FALLBACK_SCRAPER, attempts

        except Exception as e:
            response_time = (datetime.now() - attempt_start).total_seconds()

            self._record_attempt(item_key, RetryAttempt(
                method=RetryMethod.FALLBACK_SCRAPER,
                timestamp=attempt_start,
                result=RetryResult.FAILURE,
                error=str(e),
                response_time=response_time
            ))

            logger.warning("❌ Fallback failed for %s: %s", item_key, str(e))

        return None, None, attempts

    def _add_to_manual_review(self, item_key: str, start_time: datetime, total_attempts: int, kwargs: Dict):
        """Add item to manual review queue"""
        if not self.config.enable_manual_review:
            return

        total_time = (datetime.now() - start_time).total_seconds()

        manual_item = {
            'item_key': item_key,
            'timestamp': datetime.now(),
            'total_attempts': total_attempts,
            'total_time': total_time,
            'last_error': self.retry_history.get(item_key, [])[-1].error if self.retry_history.get(item_key) else None,
            'kwargs': kwargs
        }

        self.manual_review_queue.append(manual_item)

        logger.warning("📋 Item %s added to manual review queue after %d attempts (%.2fs)",
                       item_key, total_attempts, total_time)

    def get_method_performance(self) -> Dict[str, Dict]:
        """Get performance statistics for each retry method"""
        performance = {}

        for method, stats in self.method_stats.items():
            success_rate = self._get_success_rate(method)
            performance[method.value] = {
                'attempts': stats['attempts'],
                'successes': stats['successes'],
                'success_rate': success_rate,
                'should_skip': self._should_skip_method(method)
            }

        return performance

    def get_manual_review_queue(self) -> List[Dict]:
        """Get items in manual review queue"""
        return self.manual_review_queue.copy()

    def clear_manual_review_queue(self):
        """Clear the manual review queue"""
        cleared_count = len(self.manual_review_queue)
        self.manual_review_queue.clear()
        logger.info("🗑️ Cleared %d items from manual review queue",
                    cleared_count)

    def get_retry_history(self, item_key: str) -> List[RetryAttempt]:
        """Get retry history for a specific item"""
        return self.retry_history.get(item_key, [])

    def get_summary_stats(self) -> Dict:
        """Get summary statistics"""
        total_items = len(self.retry_history)
        total_attempts = sum(len(attempts)
                             for attempts in self.retry_history.values())

        method_breakdown = {}
        for method, stats in self.method_stats.items():
            method_breakdown[method.value] = stats.copy()
            method_breakdown[method.value]['success_rate'] = self._get_success_rate(
                method)

        return {
            'total_items_processed': total_items,
            'total_attempts_made': total_attempts,
            'manual_review_queue_size': len(self.manual_review_queue),
            'method_performance': method_breakdown,
            'average_attempts_per_item': total_attempts / max(1, total_items)
        }
