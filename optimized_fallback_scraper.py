"""
Optimized fallback scraper with driver pool and queue system
Supports multiple concurrent WebDriver instances with proxies
"""

import asyncio
import time
import logging
import re
from typing import Dict, Optional, List, Any
from dataclasses import dataclass
from queue import Queue
import threading
from concurrent.futures import ThreadPoolExecutor
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logger = logging.getLogger(__name__)

# Constants for wear conditions
FACTORY_NEW = "Factory New"
MINIMAL_WEAR = "Minimal Wear"
FIELD_TESTED = "Field-Tested"
WELL_WORN = "Well-Worn"
BATTLE_SCARRED = "Battle-Scarred"

# Test constants
TEST_URL = "https://www.csgodatabase.com/skins/ak-47-fuel-injector/"
TEST_SKIN_NAME = "AK-47 Fuel Injector"


@dataclass
class ScrapeRequest:
    """Data class for scrape requests"""
    detail_url: str
    skin_name: str
    wear_condition: str
    stattrak: bool
    request_id: str
    future: asyncio.Future


@dataclass
class ScrapeResult:
    """Data class for scrape results"""
    request_id: str
    price: Optional[float]
    success: bool
    error: Optional[str] = None


class WebDriverPool:
    """Pool of WebDriver instances for concurrent scraping"""

    def __init__(self, pool_size: int = 3, proxies: Optional[List[str]] = None, headless: bool = True):
        self.pool_size = pool_size
        self.proxies = proxies or []
        self.headless = headless
        self.drivers = []
        self.driver_queue = Queue()
        self.is_initialized = False
        self.timeout = 15

    def _create_driver(self, proxy: Optional[str] = None) -> webdriver.Chrome:
        """Create a single WebDriver instance with optional proxy"""
        chrome_options = ChromeOptions()

        if self.headless:
            chrome_options.add_argument("--headless")

        # Anti-detection options
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument(
            "--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option(
            "excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        # Add proxy if provided
        if proxy:
            chrome_options.add_argument(f"--proxy-server={proxy}")
            logger.info(f"🌐 Setting up driver with proxy: {proxy}")

        try:
            # Try with webdriver-manager
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e1:
            logger.warning(f"⚠️ Auto-download failed: {e1}")
            try:
                # Try system ChromeDriver
                driver = webdriver.Chrome(options=chrome_options)
            except Exception as e2:
                logger.error(f"❌ Failed to create WebDriver: {e2}")
                raise

        # Execute script to remove webdriver property
        try:
            driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        except Exception:
            pass

        return driver

    async def initialize(self):
        """Initialize the driver pool"""
        if self.is_initialized:
            return

        logger.info(
            f"🚀 Initializing WebDriver pool with {self.pool_size} drivers...")

        # Create drivers in separate thread to avoid blocking
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=self.pool_size) as executor:
            tasks = []

            for i in range(self.pool_size):
                # Assign proxy if available
                proxy = self.proxies[i %
                                     len(self.proxies)] if self.proxies else None
                task = loop.run_in_executor(
                    executor, self._create_driver, proxy)
                tasks.append(task)

            # Wait for all drivers to be created
            drivers = await asyncio.gather(*tasks)

            for i, driver in enumerate(drivers):
                if driver:
                    self.drivers.append(driver)
                    self.driver_queue.put(driver)
                    proxy_info = f" (proxy: {self.proxies[i % len(self.proxies)]})" if self.proxies else ""
                    logger.info(f"✅ Driver {i+1} initialized{proxy_info}")

        self.is_initialized = True
        logger.info(
            f"🎯 WebDriver pool ready with {len(self.drivers)} active drivers")

    def get_driver(self) -> Optional[webdriver.Chrome]:
        """Get an available driver from the pool"""
        try:
            return self.driver_queue.get_nowait()
        except Exception:
            return None

    def return_driver(self, driver: webdriver.Chrome):
        """Return a driver to the pool"""
        if driver and driver in self.drivers:
            self.driver_queue.put(driver)

    def cleanup(self):
        """Clean up all drivers"""
        logger.info("🧹 Cleaning up WebDriver pool...")

        for driver in self.drivers:
            try:
                driver.quit()
            except Exception as e:
                logger.warning(f"⚠️ Error closing driver: {e}")

        self.drivers.clear()
        self.is_initialized = False
        logger.info("✅ WebDriver pool cleaned up")


class OptimizedCSGODatabaseScraper:
    """Optimized scraper with driver pool and queue system"""

    def __init__(self, pool_size: int = 3, proxies: Optional[List[str]] = None, headless: bool = True):
        self.driver_pool = WebDriverPool(pool_size, proxies, headless)
        self.request_queue = asyncio.Queue()
        self.result_cache = {}
        self.cache_ttl = 300  # 5 minutes cache
        self.min_request_interval = 2.0  # 2 seconds between requests per driver
        self.last_request_times = {}
        self.processing_task = None
        self.is_running = False

    async def __aenter__(self):
        """Async context manager entry"""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.stop()

    async def start(self):
        """Start the scraper and driver pool"""
        if self.is_running:
            return

        logger.info("🚀 Starting optimized scraper...")
        await self.driver_pool.initialize()

        # Start the processing task
        self.processing_task = asyncio.create_task(self._process_requests())
        self.is_running = True
        logger.info("✅ Optimized scraper started")

    async def stop(self):
        """Stop the scraper and clean up"""
        if not self.is_running:
            return

        logger.info("🛑 Stopping optimized scraper...")
        self.is_running = False

        # Cancel processing task
        if self.processing_task:
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                pass

        # Clean up driver pool
        self.driver_pool.cleanup()
        logger.info("✅ Optimized scraper stopped")

    def _get_cache_key(self, detail_url: str, wear_condition: str, stattrak: bool) -> str:
        """Generate cache key for request"""
        return f"{detail_url}:{wear_condition}:{'stattrak' if stattrak else 'normal'}"

    def _is_cache_valid(self, cache_entry: Dict) -> bool:
        """Check if cache entry is still valid"""
        return time.time() - cache_entry['timestamp'] < self.cache_ttl

    async def _rate_limit_driver(self, driver_id: str):
        """Ensure rate limiting per driver"""
        current_time = time.time()
        last_time = self.last_request_times.get(driver_id, 0)

        if current_time - last_time < self.min_request_interval:
            sleep_time = self.min_request_interval - (current_time - last_time)
            await asyncio.sleep(sleep_time)

        self.last_request_times[driver_id] = time.time()

    def _parse_price_from_text(self, text: str) -> Optional[float]:
        """Extract price from text using regex"""
        if not text or text.strip().lower() in ['no listings', 'no listing', '', 'n/a', '-', '---']:
            return None

        # Look for price patterns
        price_patterns = [
            r'\$\s*([\d,]+\.?\d*)',  # $910.00, $1,515.59
            r'([\d,]+\.?\d*)\s*USD',  # 910.00 USD
            r'([\d,]+\.?\d*)',       # 910.00
        ]

        for pattern in price_patterns:
            matches = re.findall(pattern, text.replace(',', ''))
            if matches:
                try:
                    return float(matches[0].replace(',', ''))
                except ValueError:
                    continue

        return None

    def _scrape_single_page(self, driver: webdriver.Chrome, detail_url: str, skin_name: str) -> Dict[str, Any]:
        """Scrape a single page with given driver (blocking)
        Returns: {
            'prices': Dict[str, Optional[float]], 
            'availability': Dict[str, bool],
            'stattrak_availability': Dict[str, bool],
            'listings': Dict[str, bool]
        }"""
        try:
            # Navigate to the page
            driver.get(detail_url)

            # Wait for the price table
            wait = WebDriverWait(driver, self.driver_pool.timeout)
            wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, ".table-overflow table, table"))
            )

            # Find the table
            table = driver.find_element(
                By.CSS_SELECTOR, ".table-overflow table")

            # Extract headers
            header_row = table.find_element(
                By.CSS_SELECTOR, "thead tr, tr:first-child")
            header_cells = header_row.find_elements(By.CSS_SELECTOR, "th, td")
            headers = [cell.text.strip() for cell in header_cells]

            # Parse headers to create column mapping
            column_mapping = {}
            logger.debug(f"🔍 DEBUG - Table headers found: {headers}")
            for i, header in enumerate(headers):
                header_lower = header.lower().strip()
                is_stattrak = "stattrak" in header_lower or "stat trak" in header_lower or "st " in header_lower

                wear_condition = None
                if "factory new" in header_lower:
                    wear_condition = FACTORY_NEW
                elif "minimal wear" in header_lower:
                    wear_condition = MINIMAL_WEAR
                elif "field-tested" in header_lower or "field tested" in header_lower:
                    wear_condition = "Field-Tested"
                elif "well-worn" in header_lower or "well worn" in header_lower:
                    wear_condition = "Well-Worn"
                elif "battle-scarred" in header_lower or "battle scarred" in header_lower:
                    wear_condition = "Battle-Scarred"

                if wear_condition:
                    key = f"StatTrak {wear_condition}" if is_stattrak else wear_condition
                    column_mapping[key] = i
                    logger.debug(
                        f"🔍 DEBUG - Mapped column {i} '{header}' -> key '{key}'")

            # Find Steam row
            rows = table.find_elements(By.CSS_SELECTOR, "tbody tr, tr")
            steam_row = None

            for row in rows:
                try:
                    cells = row.find_elements(By.CSS_SELECTOR, "td, th")
                    if cells:
                        first_cell_html = (cells[0].get_attribute(
                            "innerHTML") or "").lower()
                        first_cell_text = cells[0].text.strip().lower()

                        if 'steam' in first_cell_html or 'steam' in first_cell_text:
                            steam_row = row
                            break
                except Exception:
                    continue

            if not steam_row:
                return {}

            # Extract prices and availability information
            steam_cells = steam_row.find_elements(By.CSS_SELECTOR, "td, th")
            logger.debug(
                f"🔍 DEBUG - Found {len(steam_cells)} cells in steam row")
            logger.debug(
                f"🔍 DEBUG - Available column mappings: {list(column_mapping.keys())}")

            # Initialize result dictionaries
            prices = {}
            availability = {}
            stattrak_availability = {}
            listings = {}

            # Define all possible wear conditions
            all_wear_conditions = [
                FACTORY_NEW, MINIMAL_WEAR, FIELD_TESTED, WELL_WORN, BATTLE_SCARRED]

            # Process available columns
            for wear_key, col_index in column_mapping.items():
                if col_index < len(steam_cells):
                    price_text = steam_cells[col_index].text.strip()
                    price = self._parse_price_from_text(price_text)
                    prices[wear_key] = price

                    # Determine if this is StatTrak variant
                    is_stattrak_variant = wear_key.startswith("StatTrak ")
                    base_wear = wear_key.replace(
                        "StatTrak ", "") if is_stattrak_variant else wear_key

                    # Mark availability
                    if is_stattrak_variant:
                        stattrak_availability[base_wear] = True
                    else:
                        availability[base_wear] = True

                    # Check if there are actual listings (price exists and > 0)
                    has_listing = price is not None and price > 0
                    listings[wear_key] = has_listing

                    logger.debug(
                        f"📊 {wear_key}: price=${price}, available=True, has_listing={has_listing}")
                else:
                    logger.debug(
                        f"❌ Column index {col_index} for '{wear_key}' is out of range")

            # Mark unavailable wear conditions for both normal and StatTrak
            for wear in all_wear_conditions:
                if wear not in availability:
                    availability[wear] = False
                if wear not in stattrak_availability:
                    stattrak_availability[wear] = False

            return {
                'prices': prices,
                'availability': availability,
                'stattrak_availability': stattrak_availability,
                'listings': listings
            }

        except Exception as e:
            logger.error(f"❌ Error scraping {skin_name}: {e}")
            # Return empty availability data on error
            all_wear_conditions = [
                FACTORY_NEW, MINIMAL_WEAR, FIELD_TESTED, WELL_WORN, BATTLE_SCARRED]
            return {
                'prices': {},
                'availability': {wear: False for wear in all_wear_conditions},
                'stattrak_availability': {wear: False for wear in all_wear_conditions},
                'listings': {}
            }

    async def _process_requests(self):
        """Main processing loop for the request queue"""
        logger.info("🔄 Starting request processing loop...")

        while self.is_running:
            try:
                # Get request from queue with timeout
                try:
                    request = await asyncio.wait_for(self.request_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                # Check cache first
                cache_key = self._get_cache_key(
                    request.detail_url, request.wear_condition, request.stattrak)
                if cache_key in self.result_cache and self._is_cache_valid(self.result_cache[cache_key]):
                    cached_price = self.result_cache[cache_key]['price']
                    logger.info(
                        f"💾 Cache hit for {request.skin_name} ({request.wear_condition}): ${cached_price:.2f}" if cached_price else "No price")
                    request.future.set_result(cached_price)
                    continue

                # Implement retry logic with different drivers/proxies
                max_retries = 3
                scrape_result = None
                last_error = None

                for attempt in range(max_retries):
                    # Get available driver
                    driver = self.driver_pool.get_driver()
                    if not driver:
                        if attempt == max_retries - 1:
                            logger.error(
                                f"❌ No available drivers after {max_retries} attempts for {request.skin_name}")
                            request.future.set_result(None)
                            break
                        else:
                            logger.warning(
                                f"⚠️ No available drivers (attempt {attempt + 1}/{max_retries}) for {request.skin_name}, retrying...")
                            await asyncio.sleep(2)  # Wait before retry
                            continue

                    try:
                        # Rate limit this driver
                        driver_id = str(id(driver))
                        await self._rate_limit_driver(driver_id)

                        logger.debug(
                            f"🔄 Attempt {attempt + 1}/{max_retries} for {request.skin_name}")

                        # Scrape in thread pool to avoid blocking
                        loop = asyncio.get_event_loop()
                        with ThreadPoolExecutor(max_workers=1) as executor:
                            scrape_result = await loop.run_in_executor(
                                executor,
                                self._scrape_single_page,
                                driver,
                                request.detail_url,
                                request.skin_name
                            )

                        # If we got a result, break out of retry loop
                        if scrape_result and scrape_result.get('prices'):
                            logger.debug(
                                f"✅ Success on attempt {attempt + 1} for {request.skin_name}")
                            break
                        elif attempt < max_retries - 1:
                            logger.warning(
                                f"⚠️ Empty result on attempt {attempt + 1}, retrying {request.skin_name}")

                    except Exception as e:
                        last_error = e
                        logger.warning(
                            f"⚠️ Attempt {attempt + 1} failed for {request.skin_name}: {e}")
                        if attempt == max_retries - 1:
                            logger.error(
                                f"❌ All {max_retries} attempts failed for {request.skin_name}")

                    finally:
                        # Always return driver to pool
                        if driver:
                            self.driver_pool.return_driver(driver)
                            driver = None

                # Process the result if we got one
                if scrape_result:
                    # Extract specific price from result
                    key = f"StatTrak {request.wear_condition}" if request.stattrak else request.wear_condition
                    prices = scrape_result.get('prices', {})
                    logger.debug(
                        f"🔍 DEBUG - Scraping returned {len(prices)} prices")
                    logger.debug(f"🔍 DEBUG - Looking for key: '{key}'")
                    logger.debug(
                        f"🔍 DEBUG - Available keys: {list(prices.keys())}")

                    price = prices.get(key)

                    # Debug logging
                    if not price:
                        logger.debug(
                            f"🔍 DEBUG - No price found for key '{key}'")
                        if prices:
                            logger.debug(
                                f"🔍 DEBUG - All prices data: {prices}")
                        else:
                            logger.debug(
                                "🔍 DEBUG - prices dictionary is empty - scraping failed")

                    # Cache result
                    self.result_cache[cache_key] = {
                        'price': price,
                        'timestamp': time.time()
                    }

                    if price:
                        logger.info(
                            f"✅ Scraped {request.skin_name} ({request.wear_condition}{' StatTrak™' if request.stattrak else ''}): ${price:.2f}")
                    else:
                        logger.info(
                            f"❌ No price for {request.skin_name} ({request.wear_condition}{' StatTrak™' if request.stattrak else ''})")

                    request.future.set_result(price)
                else:
                    # All retries failed
                    logger.error(
                        f"❌ Failed to scrape {request.skin_name} after {max_retries} attempts")
                    if last_error:
                        logger.error(f"❌ Last error: {last_error}")
                    request.future.set_result(None)

            except Exception as e:
                logger.error(f"❌ Error in processing loop: {e}")
                await asyncio.sleep(1)

    async def get_price(self, detail_url: str, skin_name: str, wear_condition: str, stattrak: bool = False) -> Optional[float]:
        """Queue a price request and wait for result"""
        if not self.is_running:
            raise RuntimeError(
                "Scraper not started. Use async context manager or call start()")

        # Create request
        request_id = f"{skin_name}_{wear_condition}_{stattrak}_{time.time()}"
        future = asyncio.Future()

        request = ScrapeRequest(
            detail_url=detail_url,
            skin_name=skin_name,
            wear_condition=wear_condition,
            stattrak=stattrak,
            request_id=request_id,
            future=future
        )

        # Queue the request
        await self.request_queue.put(request)
        logger.debug(
            f"📤 Queued request for {skin_name} ({wear_condition}{'StatTrak™' if stattrak else ''})")

        # Wait for result
        try:
            result = await asyncio.wait_for(future, timeout=30.0)
            return result
        except asyncio.TimeoutError:
            logger.error(
                f"⏰ Timeout waiting for {skin_name} ({wear_condition})")
            return None

    async def get_weapon_info(self, detail_url: str, skin_name: str) -> Dict[str, Any]:
        """Get comprehensive weapon information including prices, availability, and listings"""
        if not self.is_running:
            raise RuntimeError(
                "Scraper not started. Use async context manager or call start()")

        # Use a dummy request to trigger the comprehensive scraping
        # We'll scrape the page once and extract all information
        try:
            driver = self.driver_pool.get_driver()
            if not driver:
                logger.error(f"⚠️ No available drivers for {skin_name}")
                return self._get_empty_weapon_info()

            try:
                # Rate limit this driver
                driver_id = str(id(driver))
                await self._rate_limit_driver(driver_id)

                # Scrape in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                with ThreadPoolExecutor(max_workers=1) as executor:
                    result = await loop.run_in_executor(
                        executor,
                        self._scrape_single_page,
                        driver,
                        detail_url,
                        skin_name
                    )

                logger.info(
                    f"🔍 Analyzed {skin_name}: found {len(result.get('prices', {}))} price points")
                return result

            except Exception as e:
                logger.error(
                    f"❌ Error getting weapon info for {skin_name}: {e}")
                return self._get_empty_weapon_info()

            finally:
                # Return driver to pool
                self.driver_pool.return_driver(driver)

        except Exception as e:
            logger.error(f"❌ Error in get_weapon_info: {e}")
            return self._get_empty_weapon_info()

    def _get_empty_weapon_info(self) -> Dict[str, Any]:
        """Return empty weapon info structure"""
        all_wear_conditions = ["Factory New", "Minimal Wear",
                               "Field-Tested", "Well-Worn", "Battle-Scarred"]
        return {
            'prices': {},
            'availability': dict.fromkeys(all_wear_conditions, False),
            'stattrak_availability': dict.fromkeys(all_wear_conditions, False),
            'listings': {}
        }
