"""
High-Speed Scraping System for CS2 Price Database
Implements maximum performance scraping with worker stealing architecture
"""

import asyncio
import logging
import time
import threading
import psutil
import math
import signal
import os
import hashlib
import aiohttp
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
from queue import Queue, Empty, PriorityQueue
from concurrent.futures import ThreadPoolExecutor, Future
import json
import random

from proxy_manager import ProxyManager, ProxyInfo
from optimized_fallback_scraper import WebDriverPool, ScrapeRequest
from steam_api import SteamMarketAPIClient

logger = logging.getLogger(__name__)


class WorkerType(Enum):
    """Types of workers in the system"""
    PROXY = "proxy"
    WEBDRIVER = "webdriver"


class WorkerStatus(Enum):
    """Status of workers"""
    IDLE = "idle"
    WORKING = "working"
    HEALTH_CHECK = "health_check"
    RATE_LIMITED = "rate_limited"
    FAILED = "failed"


@dataclass
class PriorityItem:
    """Wrapper for priority queue items"""
    priority: int  # Lower number = higher priority
    timestamp: datetime
    item: 'SkinItem'

    def __lt__(self, other):
        # Primary sort by priority, secondary by timestamp (older first)
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.timestamp < other.timestamp


@dataclass
class SkinItem:
    """Represents a complete skin item with all its variants"""
    id: str
    weapon: str
    skin_name: str
    full_name: str
    detail_url: str
    variants: List[Dict[str, Any]]
    priority: int = 0  # Higher priority = processed first
    attempts: int = 0
    last_attempt: Optional[datetime] = None
    assigned_to: Optional[str] = None  # Worker ID that took this item
    # Multiplier for priority on failure (×10 for WebDriver failures)
    failure_multiplier: int = 1

    def __hash__(self):
        return hash(self.id)

    def get_effective_priority(self) -> int:
        """Get priority adjusted by failure multiplier"""
        return max(0, self.priority - (self.failure_multiplier * 10))


class WebDriverRateLimiter:
    """Rate limiter for WebDriver instances (1-3 requests per second)"""

    def __init__(self, min_rps: float = 1.0, max_rps: float = 3.0):
        self.min_rps = min_rps
        self.max_rps = max_rps
        self.last_request_time = 0.0  # First request has NO delay - immediate startup

    async def wait_for_next_request(self):
        """Wait for appropriate delay before next request"""
        # Random rate between min and max RPS
        target_rps = random.uniform(self.min_rps, self.max_rps)
        min_interval = 1.0 / target_rps

        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < min_interval:
            delay = min_interval - time_since_last
            # Add small jitter (±10% of delay)
            jitter = delay * 0.1 * (random.random() * 2 - 1)
            final_delay = max(0, delay + jitter)
            await asyncio.sleep(final_delay)

        self.last_request_time = time.time()

    async def jittered_page_load_delay(self):
        """Add jittered delay between page loads (200-800ms)"""
        delay = random.uniform(0.2, 0.8)  # 200-800ms
        await asyncio.sleep(delay)


@dataclass
class Worker:
    """Represents a scraping worker (proxy or webdriver)"""
    id: str
    worker_type: WorkerType
    status: WorkerStatus = WorkerStatus.IDLE
    proxy_info: Optional[ProxyInfo] = None
    webdriver_instance: Optional[Any] = None
    current_item: Optional[SkinItem] = None
    success_count: int = 0
    failure_count: int = 0
    last_activity: Optional[datetime] = None
    rate_limit_until: Optional[datetime] = None
    # For WebDriver workers
    rate_limiter: Optional[WebDriverRateLimiter] = None

    def __post_init__(self):
        # Initialize rate limiter for WebDriver workers
        if self.worker_type == WorkerType.WEBDRIVER:
            self.rate_limiter = WebDriverRateLimiter()

    @property
    def is_available(self) -> bool:
        """Check if worker is available for new tasks"""
        if self.status in [WorkerStatus.FAILED]:
            return False
        if self.status == WorkerStatus.RATE_LIMITED:
            if self.rate_limit_until:
                return datetime.now() > self.rate_limit_until
            return True
        return self.status == WorkerStatus.IDLE

    @property
    def success_rate(self) -> float:
        """Calculate worker success rate"""
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 1.0


class HighSpeedScraper:
    """Main high-speed scraping orchestrator"""

    def __init__(self, checkpoint_path: str = "fallback_checkpoint.json"):
        # Core components
        self.proxy_manager = ProxyManager()
        self.steam_client = SteamMarketAPIClient()

        # Worker management
        self.workers: Dict[str, Worker] = {}
        self.active_proxies: Set[str] = set()
        self.proxy_workers: List[Worker] = []
        self.webdriver_workers: List[Worker] = []

        # Queue management - use PriorityQueue for fallback
        self.main_queue: Queue[SkinItem] = Queue()
        self.fallback_queue: PriorityQueue[PriorityItem] = PriorityQueue()
        self.completed_items: Set[str] = set()
        self.failed_items: Set[str] = set()
        # Track in-progress fallback items
        self.in_progress_fallback: Dict[str, Dict] = {}

        # Headers management
        self.headers_pool: List[Dict[str, str]] = []
        self.headers_url = "https://raw.githubusercontent.com/TheLime1/Validity/refs/heads/main/data/headers.json"
        self.headers_refresh_interval = 3600  # 1 hour
        self.last_headers_fetch = 0

        # Checkpoint management
        self.checkpoint_path = checkpoint_path
        self.shutdown_handler_registered = False

        # Configuration
        self.max_active_proxies = 150
        self.initial_proxy_batch = 5
        self.rate_limit_wait = 61  # seconds
        self.health_check_interval = 30  # seconds

        # Calculate optimal WebDriver count
        self.webdriver_count = self._calculate_webdriver_count()

        # Control flags
        self.running = False
        self.shutdown_event = asyncio.Event()

        # Task management
        self.background_tasks: List[asyncio.Task] = []

        # Statistics
        self.stats = {
            'items_processed': 0,
            'items_failed': 0,
            'proxy_successes': 0,
            'proxy_failures': 0,
            'webdriver_successes': 0,
            'webdriver_failures': 0,
            'start_time': None,
            'last_activity': None
        }

        logger.info(
            f"🚀 High-speed scraper initialized with {self.webdriver_count} WebDrivers")
        logger.info(f"💾 Checkpoint path: {self.checkpoint_path}")

    def _calculate_webdriver_count(self) -> int:
        """Calculate optimal WebDriver count based on system resources"""
        cpu_cores = psutil.cpu_count(
            logical=True) or 1  # Fallback to 1 if None
        available_ram_mb = psutil.virtual_memory().available / (1024 * 1024)

        # Formula: min(2 × CPU_cores, floor(Available_RAM_MB / 600))
        cpu_based = 2 * cpu_cores
        ram_based = math.floor(available_ram_mb / 600)

        optimal_count = min(cpu_based, ram_based)

        # Ensure at least 1 WebDriver
        optimal_count = max(1, optimal_count)

        logger.info(
            f"💻 System resources: {cpu_cores} CPU cores, {available_ram_mb:.0f}MB RAM")
        logger.info(
            f"🧮 WebDriver calculation: min({cpu_based}, {ram_based}) = {optimal_count}")

        return optimal_count

    async def initialize(self):
        """Initialize the scraping system"""
        logger.info("🔧 Initializing high-speed scraping system...")

        # Register shutdown handlers
        self._register_shutdown_handler()

        # Load fallback checkpoint if it exists
        await self._load_fallback_checkpoint()

        # Fetch headers from remote source
        await self._fetch_headers()

        # Initialize proxy manager (using existing methods)
        self.proxy_manager._load_proxy_config()

        # Start WebDrivers immediately (they start stealing from queue ASAP)
        await self._initialize_webdrivers()

        # Start background tasks and store references
        task1 = asyncio.create_task(self._proxy_health_check_loop())
        task2 = asyncio.create_task(self._worker_management_loop())
        task3 = asyncio.create_task(self._statistics_loop())
        task4 = asyncio.create_task(self._headers_refresh_loop())

        self.background_tasks.extend([task1, task2, task3, task4])

        self.stats['start_time'] = datetime.now()
        logger.info("✅ High-speed scraping system initialized")

    async def _headers_refresh_loop(self):
        """Background loop to refresh headers periodically"""
        while not self.shutdown_event.is_set():
            await asyncio.sleep(self.headers_refresh_interval)
            if not self.shutdown_event.is_set():
                await self._ensure_headers_fresh()

    async def _initialize_webdrivers(self):
        """Initialize WebDriver pool and start workers"""
        logger.info(
            f"🌐 Initializing {self.webdriver_count} WebDriver workers...")

        # Create WebDriver pool
        self.webdriver_pool = WebDriverPool(
            pool_size=self.webdriver_count,
            proxies=None,  # WebDrivers can use any proxy or direct connection
            headless=True
        )

        # Initialize the pool
        await asyncio.get_event_loop().run_in_executor(
            None, self.webdriver_pool.initialize
        )

        # Create WebDriver workers
        for i in range(self.webdriver_count):
            worker_id = f"webdriver_{i+1}"
            worker = Worker(
                id=worker_id,
                worker_type=WorkerType.WEBDRIVER,
                status=WorkerStatus.IDLE
            )

            self.workers[worker_id] = worker
            self.webdriver_workers.append(worker)

        # Start WebDriver workers immediately - they begin stealing work ASAP
        for worker in self.webdriver_workers:
            asyncio.create_task(self._webdriver_worker_loop(worker))

        logger.info(
            f"🚀 {self.webdriver_count} WebDriver workers launched - IMMEDIATE work stealing activated!")

    async def _proxy_health_check_loop(self):
        """Continuously health check proxies in batches"""
        logger.info("🏥 Starting proxy health check loop...")

        while not self.shutdown_event.is_set():
            try:
                # Get all available proxies from proxy manager
                all_proxies = self.proxy_manager.proxies

                if not all_proxies:
                    logger.warning(
                        "⚠️ No proxies available for health checking")
                    await asyncio.sleep(30)
                    continue

                # Process proxies in batches
                await self._process_proxy_batches(all_proxies)

                # Wait before next full cycle
                await asyncio.sleep(self.health_check_interval)

            except Exception as e:
                logger.error(f"❌ Error in proxy health check loop: {e}")
                await asyncio.sleep(10)

    async def _process_proxy_batches(self, all_proxies: List[ProxyInfo]):
        """Process proxies in batches of 5"""
        for i in range(0, len(all_proxies), self.initial_proxy_batch):
            batch = all_proxies[i:i + self.initial_proxy_batch]

            # Health check this batch
            healthy_proxies = await self._health_check_proxy_batch(batch)

            # Add healthy proxies to active pool (up to max limit)
            for proxy in healthy_proxies:
                if len(self.active_proxies) >= self.max_active_proxies:
                    break

                if proxy.url not in self.active_proxies:
                    self._add_proxy_worker(proxy)

            # Small delay between batches
            await asyncio.sleep(2)

    async def _health_check_proxy_batch(self, proxies: List[ProxyInfo]) -> List[ProxyInfo]:
        """Health check a batch of proxies"""
        logger.debug(f"🔍 Health checking batch of {len(proxies)} proxies...")

        tasks = []
        for proxy in proxies:
            task = asyncio.create_task(self._test_proxy_health(proxy))
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        healthy_proxies = []
        for proxy, result in zip(proxies, results):
            if isinstance(result, Exception):
                logger.debug(
                    f"❌ Proxy {proxy.host}:{proxy.port} failed health check: {result}")
            elif result:
                healthy_proxies.append(proxy)
                logger.debug(f"✅ Proxy {proxy.host}:{proxy.port} is healthy")

        logger.info(
            f"🏥 Health check complete: {len(healthy_proxies)}/{len(proxies)} proxies healthy")
        return healthy_proxies

    async def _test_proxy_health(self, proxy: ProxyInfo) -> bool:
        """Test if a single proxy is healthy"""
        try:
            async with self.steam_client:
                # Use a simple test endpoint
                test_url = "https://httpbin.org/ip"
                async with self.steam_client.session.get(
                    test_url,
                    proxy=proxy.url,
                    timeout=10
                ) as response:
                    return response.status == 200
        except Exception:
            return False

    def _add_proxy_worker(self, proxy: ProxyInfo):
        """Add a healthy proxy as a worker"""
        worker_id = f"proxy_{proxy.host}_{proxy.port}"

        if worker_id in self.workers:
            return  # Already exists

        worker = Worker(
            id=worker_id,
            worker_type=WorkerType.PROXY,
            status=WorkerStatus.IDLE,
            proxy_info=proxy
        )

        self.workers[worker_id] = worker
        self.proxy_workers.append(worker)
        self.active_proxies.add(proxy.url)

        # Start the proxy worker immediately - begins stealing work ASAP
        task = asyncio.create_task(self._proxy_worker_loop(worker))
        self.background_tasks.append(task)

        logger.info(
            f"⚡ Added proxy worker: {worker_id} - IMMEDIATE work stealing activated! (Total active: {len(self.active_proxies)})")

    async def _worker_management_loop(self):
        """Manage worker health and lifecycle"""
        while not self.shutdown_event.is_set():
            try:
                current_time = datetime.now()

                # Check for failed workers and remove them
                failed_workers = []
                for worker_id, worker in self.workers.items():
                    if worker.status == WorkerStatus.FAILED:
                        failed_workers.append(worker_id)
                    elif worker.status == WorkerStatus.RATE_LIMITED:
                        # Check if rate limit has expired
                        if worker.rate_limit_until and current_time > worker.rate_limit_until:
                            worker.status = WorkerStatus.IDLE
                            logger.info(
                                f"⏰ Worker {worker_id} rate limit expired, back to work")

                # Remove failed workers
                for worker_id in failed_workers:
                    await self._remove_worker(worker_id)

                # Log active workers status
                self._log_worker_status()

                await asyncio.sleep(10)  # Check every 10 seconds

            except Exception as e:
                logger.error(f"❌ Error in worker management loop: {e}")
                await asyncio.sleep(5)

    async def _remove_worker(self, worker_id: str):
        """Remove a failed worker"""
        if worker_id not in self.workers:
            return

        worker = self.workers[worker_id]

        # Remove from active proxies if it's a proxy worker
        if worker.worker_type == WorkerType.PROXY and worker.proxy_info:
            self.active_proxies.discard(worker.proxy_info.url)
            self.proxy_workers = [
                w for w in self.proxy_workers if w.id != worker_id]
        elif worker.worker_type == WorkerType.WEBDRIVER:
            self.webdriver_workers = [
                w for w in self.webdriver_workers if w.id != worker_id]

        # Return any assigned item back to queue
        if worker.current_item:
            worker.current_item.assigned_to = None
            await self._return_item_to_queue(worker.current_item)

        del self.workers[worker_id]

        logger.warning(f"🗑️ Removed failed worker: {worker_id}")

    async def _proxy_worker_loop(self, worker: Worker):
        """Main loop for proxy workers - starts immediately"""
        logger.info(
            f"⚡ Proxy worker {worker.id} READY - starting immediate work stealing")

        while not self.shutdown_event.is_set() and worker.id in self.workers:
            try:
                if not worker.is_available:
                    await asyncio.sleep(0.1)  # Very brief availability check
                    continue

                # Try to steal an item from the main queue
                item = self._steal_from_main_queue(worker)
                if not item:
                    await asyncio.sleep(0.1)  # Minimal pause - stay responsive
                    continue

                # Process the item
                success = await self._process_item_with_proxy(worker, item)

                if success:
                    worker.success_count += 1
                    self.stats['proxy_successes'] += 1
                    self._mark_item_completed(item)
                else:
                    worker.failure_count += 1
                    self.stats['proxy_failures'] += 1
                    # Delegate entire item to fallback queue
                    self._delegate_to_fallback(item)

                worker.status = WorkerStatus.IDLE
                worker.current_item = None
                worker.last_activity = datetime.now()

            except Exception as e:
                logger.error(f"❌ Error in proxy worker {worker.id}: {e}")
                worker.status = WorkerStatus.FAILED
                break

    async def _webdriver_worker_loop(self, worker: Worker):
        """Main loop for WebDriver workers - starts scraping immediately"""
        logger.info(
            f"🚀 WebDriver worker {worker.id} READY - starting immediate work stealing")

        while not self.shutdown_event.is_set() and worker.id in self.workers:
            try:
                if not worker.is_available:
                    # Very brief check for availability
                    await asyncio.sleep(0.1)
                    continue

                # Prioritize fallback queue over main queue
                item = self._steal_from_fallback_queue(worker)
                if not item:
                    item = self._steal_from_main_queue(worker)

                if not item:
                    # Minimal pause - stay responsive for immediate work
                    await asyncio.sleep(0.1)
                    continue

                # Process the entire item with WebDriver (all variants at once)
                success = await self._process_item_with_webdriver(worker, item)

                if success:
                    worker.success_count += 1
                    self.stats['webdriver_successes'] += 1
                    self._mark_item_completed(item)
                else:
                    worker.failure_count += 1
                    self.stats['webdriver_failures'] += 1
                    # WebDriver failure - delegate with ×10 priority
                    self._delegate_to_fallback(item, is_webdriver_failure=True)

                worker.status = WorkerStatus.IDLE
                worker.current_item = None
                worker.last_activity = datetime.now()

            except Exception as e:
                logger.error(f"❌ Error in WebDriver worker {worker.id}: {e}")
                worker.status = WorkerStatus.FAILED
                break

    def _steal_from_main_queue(self, worker: Worker) -> Optional[SkinItem]:
        """Worker steals an item from the main queue"""
        try:
            item = self.main_queue.get_nowait()

            # Check if item is already assigned or completed
            if item.id in self.completed_items or item.assigned_to:
                return None

            # Assign to worker
            item.assigned_to = worker.id
            worker.current_item = item
            worker.status = WorkerStatus.WORKING

            logger.debug(f"📦 Worker {worker.id} stole item: {item.id}")
            return item

        except Empty:
            return None

    def _steal_from_fallback_queue(self, worker: Worker) -> Optional[SkinItem]:
        """Worker steals an item from the fallback queue"""
        try:
            priority_item = self.fallback_queue.get_nowait()
            item = priority_item.item

            # Check if item is already assigned or completed
            if item.id in self.completed_items or item.assigned_to:
                return None

            # Assign to worker
            item.assigned_to = worker.id
            worker.current_item = item
            worker.status = WorkerStatus.WORKING

            # Track in-progress fallback item
            self.in_progress_fallback[item.id] = {
                'worker_id': worker.id,
                'start_time': datetime.now().isoformat(),
                'priority': priority_item.priority,
                'attempts': item.attempts
            }

            logger.debug(
                f"🔄 Worker {worker.id} stole fallback item: {item.id} (priority: {priority_item.priority})")
            return item

        except Empty:
            return None

    async def _process_item_with_proxy(self, worker: Worker, item: SkinItem) -> bool:
        """Process a single variant of an item with proxy"""
        try:
            # For proxy workers, we process one variant at a time
            # If ANY variant fails, we delegate the entire item to fallback

            for variant in item.variants:
                try:
                    # Process this variant
                    success = await self._scrape_variant_with_proxy(worker, item, variant)
                    if not success:
                        logger.warning(
                            f"❌ Proxy {worker.id} failed variant {variant['wear']} for {item.id}")
                        return False  # Entire item fails if any variant fails

                    # Handle rate limiting
                    await asyncio.sleep(0.1)  # Small delay between variants

                except Exception as e:
                    logger.error(
                        f"❌ Error processing variant {variant['wear']} for {item.id}: {e}")
                    return False

            return True  # All variants processed successfully

        except Exception as e:
            logger.error(f"❌ Error processing item {item.id} with proxy: {e}")

            # Check if this is a rate limit error
            if "rate limit" in str(e).lower() or "429" in str(e):
                worker.status = WorkerStatus.RATE_LIMITED
                worker.rate_limit_until = datetime.now() + timedelta(seconds=self.rate_limit_wait)
                logger.warning(
                    f"⏰ Worker {worker.id} hit rate limit, waiting {self.rate_limit_wait}s")

            return False

    async def _scrape_variant_with_proxy(self, worker: Worker, item: SkinItem, variant: Dict) -> bool:
        """Scrape a single variant using proxy with random headers"""
        try:
            # Get random headers for this request
            headers = self._get_random_headers()

            # Construct Steam Market URL for this variant
            market_name = self._build_market_name(item, variant)

            # Use Steam API client with proxy and random headers
            async with self.steam_client:
                # Mock the request with headers and proxy for now
                # In real implementation, this would make the actual request
                # with the proxy and headers

                # Simulate request with realistic timing
                request_time = random.uniform(0.5, 2.0)
                await asyncio.sleep(request_time)

                # Simulate success rate for proxy requests
                success_rate = 0.7  # 70% success rate for proxy requests
                success = random.random() < success_rate

                if success:
                    # Simulate successful response
                    response = {
                        'success': True,
                        'lowest_price': f"${random.uniform(10, 1000):.2f}",
                        'volume': str(random.randint(1, 100)),
                        'median_price': f"${random.uniform(10, 1000):.2f}"
                    }

                    # Update variant price data
                    await self._update_variant_price(item, variant, response)
                    logger.debug(
                        f"✅ Proxy scraped {variant['wear']} for {item.id}")
                    return True
                else:
                    logger.debug(
                        f"❌ Proxy failed {variant['wear']} for {item.id}")
                    return False

        except Exception as e:
            logger.error(f"❌ Error scraping variant with proxy: {e}")
            return False

    async def _process_item_with_webdriver(self, worker: Worker, item: SkinItem) -> bool:
        """Process entire item (all variants) with WebDriver"""
        try:
            logger.info(
                f"🌐 WebDriver {worker.id} processing entire item: {item.id}")

            # Apply rate limiting (1-3 requests per second)
            if worker.rate_limiter:
                await worker.rate_limiter.wait_for_next_request()

            # Add jittered delay between page loads (200-800ms)
            if worker.rate_limiter:
                await worker.rate_limiter.jittered_page_load_delay()

            # Use WebDriver to scrape all variants at once
            success = await self._scrape_all_variants_with_webdriver(worker, item)

            if success:
                logger.info(
                    f"✅ WebDriver {worker.id} completed item: {item.id}")
            else:
                logger.warning(
                    f"❌ WebDriver {worker.id} failed item: {item.id}")

            return success

        except Exception as e:
            logger.error(
                f"❌ Error processing item {item.id} with WebDriver: {e}")
            return False

    async def _scrape_all_variants_with_webdriver(self, worker: Worker, item: SkinItem) -> bool:
        """Scrape all variants using WebDriver with rate limiting"""
        try:
            # This would use the existing optimized fallback scraper
            # to scrape all variants from the detail page at once

            # For now, simulate the process with realistic timing
            processing_time = random.uniform(2.0, 5.0)  # 2-5 seconds per item
            await asyncio.sleep(processing_time)

            # Simulate success rate (WebDrivers are more reliable)
            success_rate = 0.9  # 90% success rate for WebDrivers
            success = random.random() < success_rate

            if success:
                logger.debug(f"✅ WebDriver scraped all variants for {item.id}")
            else:
                logger.debug(f"❌ WebDriver failed to scrape {item.id}")

            return success

        except Exception as e:
            logger.error(f"❌ Error scraping with WebDriver: {e}")
            return False

    def _build_market_name(self, item: SkinItem, variant: Dict) -> str:
        """Build Steam Market name for a variant"""
        wear = variant['wear']
        has_stattrak = variant.get('stattrak_available', False)

        if has_stattrak:
            return f"StatTrak™ {item.full_name} ({wear})"
        else:
            return f"{item.full_name} ({wear})"

    async def _update_variant_price(self, item: SkinItem, variant: Dict, price_data: Dict):
        """Update variant price data"""
        # This would update the price in the variant data structure
        # and eventually save to the database
        pass

    def _delegate_to_fallback(self, item: SkinItem, is_webdriver_failure: bool = False):
        """Delegate item to fallback queue with appropriate priority"""
        item.assigned_to = None  # Clear assignment

        # Calculate priority (lower number = higher priority)
        if is_webdriver_failure:
            # WebDriver failure gets ×10 priority boost
            item.failure_multiplier = 10
            priority = item.get_effective_priority()
        else:
            # Regular proxy failure
            priority = item.get_effective_priority()

        # Create priority item and add to fallback queue
        priority_item = PriorityItem(
            priority=priority,
            timestamp=datetime.now(),
            item=item
        )

        self.fallback_queue.put(priority_item)

        failure_type = "WebDriver" if is_webdriver_failure else "proxy"
        logger.info(
            f"🔄 Item {item.id} delegated to fallback queue ({failure_type} failure, priority: {priority})")

    async def _return_item_to_queue(self, item: SkinItem):
        """Return item back to appropriate queue"""
        item.assigned_to = None
        self.main_queue.put(item)
        logger.debug(f"↩️ Item {item.id} returned to main queue")

    async def _fetch_headers(self):
        """Fetch headers from the remote URL"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.headers_url, timeout=30) as response:
                    if response.status == 200:
                        headers_data = await response.json()
                        if isinstance(headers_data, list) and headers_data:
                            self.headers_pool = headers_data
                            self.last_headers_fetch = time.time()
                            logger.info(
                                f"✅ Fetched {len(self.headers_pool)} headers from remote source")
                            return True
                    else:
                        logger.warning(
                            f"⚠️ Failed to fetch headers, status: {response.status}")
        except Exception as e:
            logger.error(f"❌ Error fetching headers: {e}")

        return False

    def _get_random_headers(self) -> Dict[str, str]:
        """Get random headers from the pool"""
        if not self.headers_pool:
            # Fallback headers if pool is empty
            return {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1"
            }

        return random.choice(self.headers_pool).copy()

    async def _ensure_headers_fresh(self):
        """Ensure headers are fresh, refresh if needed"""
        current_time = time.time()
        if (current_time - self.last_headers_fetch) > self.headers_refresh_interval:
            logger.info("🔄 Headers cache expired, refreshing...")
            await self._fetch_headers()

    def _register_shutdown_handler(self):
        """Register signal handlers for graceful shutdown"""
        if self.shutdown_handler_registered:
            return

        def signal_handler(signum, frame):
            logger.info(
                f"🛑 Received signal {signum}, initiating graceful shutdown...")
            asyncio.create_task(self._save_checkpoint_and_shutdown())

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        self.shutdown_handler_registered = True

    async def _save_checkpoint_and_shutdown(self):
        """Save checkpoint and initiate shutdown"""
        await self._save_fallback_checkpoint()
        self.shutdown_event.set()

    async def _save_fallback_checkpoint(self):
        """Save fallback checkpoint atomically"""
        try:
            # Collect fallback queue items
            fallback_items = []
            temp_queue = PriorityQueue()

            # Extract all items from fallback queue
            while not self.fallback_queue.empty():
                try:
                    priority_item = self.fallback_queue.get_nowait()
                    fallback_items.append({
                        'item_id': priority_item.item.id,
                        'priority': priority_item.priority,
                        'timestamp': priority_item.timestamp.isoformat(),
                        'full_name': priority_item.item.full_name,
                        'attempts': priority_item.item.attempts,
                        'failure_multiplier': priority_item.item.failure_multiplier
                    })
                    # Put back for continued processing
                    temp_queue.put(priority_item)
                except Empty:
                    break

            # Restore queue
            while not temp_queue.empty():
                self.fallback_queue.put(temp_queue.get_nowait())

            # Create checkpoint data
            checkpoint_data = {
                'timestamp': datetime.now().isoformat(),
                'version': '1.0',
                'fallback_queue': fallback_items,
                'in_progress_fallback': self.in_progress_fallback.copy(),
                'stats': self.stats.copy(),
                'total_items': len(fallback_items) + len(self.in_progress_fallback)
            }

            # Calculate checksum
            checkpoint_json = json.dumps(checkpoint_data, sort_keys=True)
            checksum = hashlib.md5(checkpoint_json.encode()).hexdigest()
            checkpoint_data['checksum'] = checksum

            # Atomic write
            temp_path = f"{self.checkpoint_path}.tmp"
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(checkpoint_data, f, indent=2, ensure_ascii=False)

            # Atomic rename
            if os.path.exists(self.checkpoint_path):
                backup_path = f"{self.checkpoint_path}.backup"
                os.rename(self.checkpoint_path, backup_path)

            os.rename(temp_path, self.checkpoint_path)

            logger.info(
                f"💾 Fallback checkpoint saved: {len(fallback_items)} items, checksum: {checksum[:8]}")

        except Exception as e:
            logger.error(f"❌ Error saving fallback checkpoint: {e}")

    async def _load_fallback_checkpoint(self):
        """Load fallback checkpoint if it exists"""
        if not os.path.exists(self.checkpoint_path):
            logger.info("📂 No fallback checkpoint found, starting fresh")
            return

        try:
            with open(self.checkpoint_path, 'r', encoding='utf-8') as f:
                checkpoint_data = json.load(f)

            # Verify checksum
            saved_checksum = checkpoint_data.pop('checksum', None)
            current_checksum = hashlib.md5(json.dumps(
                checkpoint_data, sort_keys=True).encode()).hexdigest()

            if saved_checksum != current_checksum:
                logger.warning(
                    "⚠️ Checkpoint checksum mismatch, ignoring checkpoint")
                return

            # Load fallback items with highest priority
            fallback_items = checkpoint_data.get('fallback_queue', [])
            for item_data in fallback_items:
                # Create a minimal SkinItem for the checkpoint
                item = SkinItem(
                    id=item_data['item_id'],
                    weapon="",
                    skin_name="",
                    full_name=item_data['full_name'],
                    detail_url="",
                    variants=[],
                    attempts=item_data.get('attempts', 0),
                    failure_multiplier=item_data.get('failure_multiplier', 1)
                )

                # Create priority item with original priority
                priority_item = PriorityItem(
                    priority=item_data['priority'],
                    timestamp=datetime.fromisoformat(item_data['timestamp']),
                    item=item
                )

                # Add to front of fallback queue (highest priority)
                self.fallback_queue.put(priority_item)

            # Restore in-progress items
            self.in_progress_fallback = checkpoint_data.get(
                'in_progress_fallback', {})

            logger.info(f"📂 Loaded checkpoint: {len(fallback_items)} fallback items, "
                        f"{len(self.in_progress_fallback)} in-progress items")

            # Remove checkpoint file after successful load
            os.remove(self.checkpoint_path)
            logger.info("🗑️ Checkpoint file removed after successful load")

        except Exception as e:
            logger.error(f"❌ Error loading fallback checkpoint: {e}")

    def _mark_item_completed(self, item: SkinItem):
        """Mark item as completed"""
        self.completed_items.add(item.id)
        self.stats['items_processed'] += 1
        self.stats['last_activity'] = datetime.now()

        # Remove from in-progress fallback if it was there
        self.in_progress_fallback.pop(item.id, None)

        logger.info(f"✅ Item completed: {item.id}")

    def _mark_item_failed(self, item: SkinItem):
        """Mark item as failed"""
        self.failed_items.add(item.id)
        self.stats['items_failed'] += 1

        # Remove from in-progress fallback if it was there
        self.in_progress_fallback.pop(item.id, None)

        logger.warning(f"❌ Item failed: {item.id}")

    def _log_worker_status(self):
        """Log current worker status"""
        proxy_count = len([w for w in self.workers.values()
                          if w.worker_type == WorkerType.PROXY])
        webdriver_count = len(
            [w for w in self.workers.values() if w.worker_type == WorkerType.WEBDRIVER])

        active_count = len([w for w in self.workers.values()
                           if w.status == WorkerStatus.WORKING])
        idle_count = len([w for w in self.workers.values()
                         if w.status == WorkerStatus.IDLE])
        rate_limited_count = len(
            [w for w in self.workers.values() if w.status == WorkerStatus.RATE_LIMITED])

        logger.info(f"👥 Workers: {proxy_count} proxies, {webdriver_count} WebDrivers | "
                    f"Active: {active_count}, Idle: {idle_count}, Rate Limited: {rate_limited_count}")

    async def _statistics_loop(self):
        """Periodic statistics reporting"""
        while not self.shutdown_event.is_set():
            await asyncio.sleep(60)  # Report every minute

            if self.stats['start_time']:
                elapsed = datetime.now() - self.stats['start_time']

                logger.info(f"📊 Statistics - Runtime: {elapsed}, "
                            f"Processed: {self.stats['items_processed']}, "
                            f"Failed: {self.stats['items_failed']}, "
                            f"Queue: {self.main_queue.qsize()}, "
                            f"Fallback: {self.fallback_queue.qsize()}")

    async def load_items_from_database(self, database_path: str):
        """Load items from database and populate the queue"""
        logger.info(f"📂 Loading items from database: {database_path}")

        try:
            with open(database_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            items_loaded = 0
            for skin_data in data.get('skins', []):
                item = SkinItem(
                    id=skin_data['id'],
                    weapon=skin_data['weapon'],
                    skin_name=skin_data['skin_name'],
                    full_name=skin_data['full_name'],
                    detail_url=skin_data['detail_url'],
                    variants=skin_data['variants']
                )

                self.main_queue.put(item)
                items_loaded += 1

            logger.info(f"✅ Loaded {items_loaded} items into scraping queue")

        except Exception as e:
            logger.error(f"❌ Error loading items from database: {e}")
            raise

    async def start_scraping(self):
        """Start the high-speed scraping process"""
        logger.info("🚀 Starting high-speed scraping...")

        self.running = True

        # Wait for initial workers to be ready
        await asyncio.sleep(5)

        logger.info("⚡ High-speed scraping is now running!")
        logger.info(f"📊 Queue size: {self.main_queue.qsize()} items")
        logger.info(f"👥 Active workers: {len(self.workers)}")

        # Wait until shutdown
        await self.shutdown_event.wait()

    async def shutdown(self):
        """Gracefully shutdown the scraping system"""
        logger.info("🛑 Shutting down high-speed scraping system...")

        self.running = False
        self.shutdown_event.set()

        # Close WebDriver pool
        if hasattr(self, 'webdriver_pool'):
            await asyncio.get_event_loop().run_in_executor(
                None, self.webdriver_pool.cleanup
            )

        # Close Steam client
        if self.steam_client:
            await self.steam_client.__aexit__(None, None, None)

        logger.info("✅ High-speed scraping system shutdown complete")


# Example usage
async def main():
    """Example of how to use the high-speed scraper"""
    scraper = HighSpeedScraper()

    try:
        # Initialize the system
        await scraper.initialize()

        # Load items from database
        await scraper.load_items_from_database("data/skins_database.json")

        # Start scraping
        await scraper.start_scraping()

    except KeyboardInterrupt:
        logger.info("⚠️ Received interrupt signal")
    finally:
        await scraper.shutdown()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
