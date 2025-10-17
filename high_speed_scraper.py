"""
High-Speed Scraping System V3.0 for CS2 Price Database
WebDriver-only architecture with worker stealing
"""

import asyncio
import logging
import time
import psutil
import math
import signal
import os
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta
from queue import Queue, Empty, PriorityQueue
import json
import random

from optimized_fallback_scraper import WebDriverPool

logger = logging.getLogger(__name__)


class WorkerType(Enum):
    """Types of workers in the system"""
    WEBDRIVER = "webdriver"


class WorkerStatus(Enum):
    """Status of workers"""
    IDLE = "idle"
    WORKING = "working"
    RATE_LIMITED = "rate_limited"
    FAILED = "failed"


@dataclass
class PriorityItem:
    """Wrapper for priority queue items"""
    priority: int  # Lower number = higher priority
    timestamp: datetime
    item: 'SkinItem'

    def __lt__(self, other):
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
    priority: int = 0
    attempts: int = 0
    last_attempt: Optional[datetime] = None
    assigned_to: Optional[str] = None
    failure_multiplier: int = 1

    def __hash__(self):
        return hash(self.id)

    def get_effective_priority(self) -> int:
        return max(0, self.priority - (self.failure_multiplier * 10))


class WebDriverRateLimiter:
    """Rate limiter for WebDriver instances (1-3 requests per second)"""

    def __init__(self, min_rps: float = 1.0, max_rps: float = 3.0):
        self.min_rps = min_rps
        self.max_rps = max_rps
        self.last_request_time = 0.0

    async def wait_for_next_request(self):
        target_rps = random.uniform(self.min_rps, self.max_rps)
        min_interval = 1.0 / target_rps
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < min_interval:
            delay = min_interval - time_since_last
            await asyncio.sleep(delay)

        self.last_request_time = time.time()

    async def jittered_page_load_delay(self):
        delay = random.uniform(0.2, 0.8)
        await asyncio.sleep(delay)


@dataclass
class Worker:
    """Represents a WebDriver scraping worker"""
    id: str
    worker_type: WorkerType
    status: WorkerStatus = WorkerStatus.IDLE
    webdriver_instance: Optional[Any] = None
    current_item: Optional[SkinItem] = None
    success_count: int = 0
    failure_count: int = 0
    last_activity: Optional[datetime] = None
    rate_limit_until: Optional[datetime] = None
    rate_limiter: Optional[WebDriverRateLimiter] = None

    def __post_init__(self):
        if self.worker_type == WorkerType.WEBDRIVER and not self.rate_limiter:
            self.rate_limiter = WebDriverRateLimiter()

    @property
    def is_available(self) -> bool:
        if self.status == WorkerStatus.RATE_LIMITED:
            if self.rate_limit_until and datetime.now() > self.rate_limit_until:
                self.status = WorkerStatus.IDLE
                return True
            return False
        return self.status == WorkerStatus.IDLE


class HighSpeedScraper:
    """V3.0 High-speed scraping orchestrator - WebDriver only"""

    def __init__(self, checkpoint_path: str = "fallback_checkpoint.json"):
        # Core components - WebDriver only in V3.0
        self.webdriver_workers: List[Worker] = []
        self.workers: Dict[str, Worker] = {}

        # Queue management
        self.main_queue: Queue[SkinItem] = Queue()
        self.fallback_queue: PriorityQueue[PriorityItem] = PriorityQueue()
        self.completed_items: Set[str] = set()
        self.failed_items: Set[str] = set()
        self.in_progress_fallback: Dict[str, Dict] = {}

        # Checkpoint management
        self.checkpoint_path = checkpoint_path
        self.shutdown_handler_registered = False

        # Configuration
        self.rate_limit_wait = 61

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
            'webdriver_successes': 0,
            'webdriver_failures': 0,
            'start_time': None,
            'last_activity': None
        }

        logger.info(
            f"🚀 V3.0 High-speed scraper initialized with {self.webdriver_count} WebDrivers")
        logger.info(f"💾 Checkpoint path: {self.checkpoint_path}")

    def _calculate_webdriver_count(self) -> int:
        """Calculate optimal WebDriver count based on system resources"""
        cpu_cores = psutil.cpu_count(logical=True) or 1
        available_ram_mb = psutil.virtual_memory().available / (1024 * 1024)

        cpu_based = 2 * cpu_cores
        ram_based = math.floor(available_ram_mb / 600)

        optimal_count = min(cpu_based, ram_based)
        optimal_count = max(1, optimal_count)

        logger.info(
            f"💻 System resources: {cpu_cores} CPU cores, {available_ram_mb:.0f}MB RAM")
        logger.info(
            f"🧮 WebDriver calculation: min({cpu_based}, {ram_based}) = {optimal_count}")

        return optimal_count

    def configure(self, ignore_stattrak: bool = False):
        """Configure the scraper with command-line flags"""
        self.config = {
            'ignore_stattrak': ignore_stattrak
        }

        if ignore_stattrak:
            logger.info("⏭️ StatTrak variants will be ignored")

    async def initialize(self):
        """Initialize the scraping system"""
        logger.info("🔧 Initializing V3.0 scraping system...")

        # Register shutdown handlers
        self._register_shutdown_handler()

        # Load fallback checkpoint if it exists
        await self._load_fallback_checkpoint()

        # Start WebDrivers immediately
        await self._initialize_webdrivers()

        # Start background tasks
        task1 = asyncio.create_task(self._worker_management_loop())
        task2 = asyncio.create_task(self._statistics_loop())
        task3 = asyncio.create_task(self._completion_monitor_loop())

        self.background_tasks.extend([task1, task2, task3])

        self.stats['start_time'] = datetime.now()
        logger.info("✅ V3.0 scraping system initialized")

    async def _initialize_webdrivers(self):
        """Initialize WebDriver pool and start workers"""
        logger.info(
            f"🌐 Initializing {self.webdriver_count} WebDriver workers...")

        # Create WebDriver pool
        self.webdriver_pool = WebDriverPool(
            pool_size=self.webdriver_count,
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

        # Start WebDriver workers
        for worker in self.webdriver_workers:
            task = asyncio.create_task(self._webdriver_worker_loop(worker))
            self.background_tasks.append(task)

        logger.info(f"🚀 {self.webdriver_count} WebDriver workers launched!")

    async def _webdriver_worker_loop(self, worker: Worker):
        """Main loop for WebDriver workers"""
        while not self.shutdown_event.is_set() and worker.id in self.workers:
            try:
                if not worker.is_available:
                    await asyncio.sleep(0.1)
                    continue

                # Prioritize fallback queue over main queue
                item = self._steal_from_fallback_queue(worker)
                if not item:
                    item = self._steal_from_main_queue(worker)

                if not item:
                    await asyncio.sleep(0.1)
                    continue

                # Process the entire item with WebDriver
                success = await self._process_item_with_webdriver(worker, item)

                if success:
                    worker.success_count += 1
                    self.stats['webdriver_successes'] += 1
                    self._mark_item_completed(item)
                else:
                    worker.failure_count += 1
                    self.stats['webdriver_failures'] += 1
                    self._delegate_to_fallback(item, is_webdriver_failure=True)

                worker.status = WorkerStatus.IDLE
                worker.current_item = None
                worker.last_activity = datetime.now()

            except Exception as e:
                logger.error(f"❌ Error in WebDriver worker {worker.id}: {e}")
                worker.status = WorkerStatus.FAILED
                break

    async def _worker_management_loop(self):
        """Manage worker health and lifecycle"""
        while not self.shutdown_event.is_set():
            try:
                current_time = datetime.now()

                # Check for failed workers
                failed_workers = []
                for worker_id, worker in self.workers.items():
                    if worker.status == WorkerStatus.FAILED:
                        failed_workers.append(worker_id)
                    elif worker.status == WorkerStatus.RATE_LIMITED:
                        if worker.rate_limit_until and current_time > worker.rate_limit_until:
                            worker.status = WorkerStatus.IDLE
                            logger.info(
                                f"⏰ Worker {worker_id} rate limit expired")

                # Remove failed workers
                for worker_id in failed_workers:
                    await self._remove_worker(worker_id)

                # Log status
                self._log_worker_status()

                await asyncio.sleep(10)

            except Exception as e:
                logger.error(f"❌ Error in worker management loop: {e}")
                await asyncio.sleep(5)

    async def _remove_worker(self, worker_id: str):
        """Remove a failed worker"""
        if worker_id not in self.workers:
            return

        worker = self.workers[worker_id]

        if worker.worker_type == WorkerType.WEBDRIVER:
            self.webdriver_workers = [
                w for w in self.webdriver_workers if w.id != worker_id]

        if worker.current_item:
            worker.current_item.assigned_to = None
            await self._return_item_to_queue(worker.current_item)

        del self.workers[worker_id]
        logger.warning(f"🗑️ Removed failed worker: {worker_id}")

    def _steal_from_main_queue(self, worker: Worker) -> Optional[SkinItem]:
        """Worker steals an item from the main queue"""
        try:
            item = self.main_queue.get_nowait()

            if item.id in self.completed_items or item.assigned_to:
                return None

            item.assigned_to = worker.id
            worker.current_item = item
            worker.status = WorkerStatus.WORKING

            logger.info(f"📦 Worker {worker.id} took item: {item.id}")
            return item

        except Empty:
            return None

    def _steal_from_fallback_queue(self, worker: Worker) -> Optional[SkinItem]:
        """Worker steals an item from the fallback queue"""
        try:
            priority_item = self.fallback_queue.get_nowait()
            item = priority_item.item

            if item.id in self.completed_items or item.assigned_to:
                return None

            item.assigned_to = worker.id
            worker.current_item = item
            worker.status = WorkerStatus.WORKING

            self.in_progress_fallback[item.id] = {
                'worker_id': worker.id,
                'start_time': datetime.now().isoformat(),
                'priority': priority_item.priority,
                'attempts': item.attempts
            }

            logger.debug(
                f"🔄 Worker {worker.id} stole fallback item: {item.id}")
            return item

        except Empty:
            return None

    async def _process_item_with_webdriver(self, worker: Worker, item: SkinItem) -> bool:
        """Process entire item with WebDriver"""
        try:
            if worker.rate_limiter:
                await worker.rate_limiter.wait_for_next_request()
                await worker.rate_limiter.jittered_page_load_delay()

            success = await self._scrape_all_variants_with_webdriver(worker, item)

            if success:
                logger.info(f"✅ WebDriver {worker.id} completed: {item.id}")
            else:
                logger.warning(f"❌ WebDriver {worker.id} failed: {item.id}")

            return success

        except Exception as e:
            logger.error(f"❌ Error processing {item.id}: {e}")
            return False

    async def _scrape_all_variants_with_webdriver(self, worker: Worker, item: SkinItem) -> bool:
        """Scrape all variants using WebDriver from csgodatabase.com"""
        try:
            if worker.rate_limiter:
                await worker.rate_limiter.wait_for_next_request()

            driver = self.webdriver_pool.get_driver()
            if not driver:
                logger.warning(f"⚠️ No WebDriver available for {item.id}")
                return False

            try:
                # Navigate to detail page
                driver.get(item.detail_url)
                await asyncio.sleep(2)

                # Scrape page data
                loop = asyncio.get_event_loop()
                scraped_data = await loop.run_in_executor(
                    None,
                    self._extract_prices_from_page,
                    driver,
                    item.detail_url,
                    item.skin_name
                )

                if not scraped_data or not scraped_data.get('prices'):
                    logger.warning(
                        f"⚠️ No data scraped from {item.detail_url}")
                    return False

                # Update database with scraped prices
                for wear_condition, price_info in scraped_data['prices'].items():
                    variant = next(
                        (v for v in item.variants if v['wear'] == wear_condition), None)
                    if variant:
                        await self._update_variant_from_scraped_data(
                            item, variant, price_info
                        )

                logger.info(
                    f"✅ Scraped {len(scraped_data['prices'])} prices for {item.id}")
                return True

            finally:
                self.webdriver_pool.return_driver(driver)

        except Exception as e:
            logger.error(f"❌ WebDriver scraping error for {item.id}: {e}")
            return False

    def _extract_prices_from_page(self, driver, detail_url: str, skin_name: str) -> Dict:
        """Extract price data from the page (runs in executor)"""
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.wait import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            # Wait for price table
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CLASS_NAME, "price-cell"))
            )

            # Extract prices from the page
            prices = {}
            price_rows = driver.find_elements(By.CSS_SELECTOR, "tr.price-row")

            for row in price_rows:
                try:
                    wear_element = row.find_element(
                        By.CSS_SELECTOR, ".wear-name")
                    price_element = row.find_element(
                        By.CSS_SELECTOR, ".price-value")

                    wear = wear_element.text.strip()
                    price_text = price_element.text.strip()

                    if price_text and "$" in price_text:
                        price = float(price_text.replace(
                            "$", "").replace(",", ""))
                        prices[wear] = {
                            'usd': price,
                            'has_listing': True
                        }
                except Exception:
                    continue

            return {'prices': prices, 'success': len(prices) > 0}

        except Exception as e:
            logger.error(f"❌ Error extracting prices: {e}")
            return {'prices': {}, 'success': False}

    async def _update_variant_from_scraped_data(self, item: SkinItem, variant: Dict, price_info: Dict):
        """Update variant with scraped price data"""
        try:
            database_path = "data/skins_database.json"

            with open(database_path, 'r', encoding='utf-8') as f:
                database = json.load(f)

            # Find the skin
            skin = next(
                (s for s in database['skins'] if s['id'] == item.id), None)
            if not skin:
                return

            # Find variant
            var = next((v for v in skin['variants']
                       if v['wear'] == variant['wear']), None)
            if not var:
                return

            # Update prices
            if 'prices' not in var:
                var['prices'] = {}

            var['prices']['normal'] = {
                'usd': price_info.get('usd'),
                'last_updated': datetime.now().isoformat()
            }

            var['has_normal_listings'] = price_info.get('has_listing', False)

            # Save database
            with open(database_path, 'w', encoding='utf-8') as f:
                json.dump(database, f, indent=2, ensure_ascii=False)

            logger.debug(f"✅ Updated {variant['wear']} for {item.id}")

        except Exception as e:
            logger.error(f"❌ Error updating variant: {e}")

    def _mark_item_completed(self, item: SkinItem):
        """Mark item as completed"""
        self.completed_items.add(item.id)
        if item.id in self.in_progress_fallback:
            del self.in_progress_fallback[item.id]
        self.stats['items_processed'] += 1
        logger.info(f"✅ Completed: {item.id}")

    def _delegate_to_fallback(self, item: SkinItem, is_webdriver_failure: bool = False):
        """Delegate item to fallback queue"""
        item.attempts += 1
        item.assigned_to = None

        if is_webdriver_failure:
            item.failure_multiplier = 10

        effective_priority = item.get_effective_priority()
        priority_item = PriorityItem(
            priority=effective_priority,
            timestamp=datetime.now(),
            item=item
        )

        self.fallback_queue.put(priority_item)
        logger.warning(
            f"🔄 Delegated {item.id} to fallback (priority: {effective_priority})")

    async def _return_item_to_queue(self, item: SkinItem):
        """Return item to appropriate queue"""
        item.assigned_to = None

        if item.attempts > 0:
            priority_item = PriorityItem(
                priority=item.get_effective_priority(),
                timestamp=datetime.now(),
                item=item
            )
            self.fallback_queue.put(priority_item)
        else:
            self.main_queue.put(item)

    def _log_worker_status(self):
        """Log current worker status"""
        total = len(self.workers)
        idle = sum(1 for w in self.workers.values()
                   if w.status == WorkerStatus.IDLE)
        working = sum(1 for w in self.workers.values()
                      if w.status == WorkerStatus.WORKING)

        logger.debug(
            f"👷 Workers: {total} total, {idle} idle, {working} working")

    async def _statistics_loop(self):
        """Log statistics periodically"""
        while not self.shutdown_event.is_set():
            await asyncio.sleep(60)
            if not self.shutdown_event.is_set():
                self._log_statistics()

    def _log_statistics(self):
        """Log current statistics"""
        logger.info(f"📊 Stats: {self.stats['webdriver_successes']} successes, "
                    f"{self.stats['webdriver_failures']} failures, "
                    f"{self.stats['items_processed']} completed")

    async def _completion_monitor_loop(self):
        """Monitor for completion"""
        while not self.shutdown_event.is_set():
            await asyncio.sleep(5)

            if (self.main_queue.empty() and
                self.fallback_queue.empty() and
                    all(w.status == WorkerStatus.IDLE for w in self.workers.values())):

                logger.info(
                    "🎉 All queues empty and workers idle - collection complete!")
                self.shutdown_event.set()

    def _register_shutdown_handler(self):
        """Register signal handlers for graceful shutdown"""
        if self.shutdown_handler_registered:
            return

        def signal_handler(signum, frame):
            logger.info("🛑 Shutdown signal received")
            self.shutdown_event.set()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        self.shutdown_handler_registered = True

    async def _load_fallback_checkpoint(self):
        """Load checkpoint if exists"""
        if not os.path.exists(self.checkpoint_path):
            return

        try:
            with open(self.checkpoint_path, 'r', encoding='utf-8') as f:
                checkpoint = json.load(f)

            logger.info(
                f"📂 Loaded checkpoint with {len(checkpoint.get('items', []))} items")

        except Exception as e:
            logger.error(f"❌ Error loading checkpoint: {e}")

    async def shutdown(self):
        """Cleanup and shutdown"""
        logger.info("🧹 Shutting down V3.0 scraper...")

        self.shutdown_event.set()

        # Cancel background tasks
        for task in self.background_tasks:
            task.cancel()

        # Cleanup WebDriver pool
        if hasattr(self, 'webdriver_pool'):
            self.webdriver_pool.cleanup()

        logger.info("✅ V3.0 scraper shutdown complete")

    async def process_items(self, items: List[Dict]):
        """Process a list of items"""
        logger.info(f"📦 Processing {len(items)} items")

        for item_data in items:
            skin_item = SkinItem(
                id=item_data['id'],
                weapon=item_data['weapon'],
                skin_name=item_data['skin_name'],
                full_name=item_data['full_name'],
                detail_url=item_data['detail_url'],
                variants=item_data['variants']
            )
            self.main_queue.put(skin_item)

        logger.info(f"✅ Queued {len(items)} items")

        # Wait for completion
        await self.shutdown_event.wait()
