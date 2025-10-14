"""
Enhanced fallback price scraper for CSGODatabase
Handles both normal and StatTrak™ variants with improved parsing
"""

import asyncio
import time
import logging
import re
from typing import Dict, Optional, List
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

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


class EnhancedCSGODatabaseFallback:
    """Enhanced fallback scraper for CSGODatabase with StatTrak™ support"""

    def __init__(self, headless: bool = True, timeout: int = 15):
        self.headless = headless
        self.timeout = timeout
        self.driver = None
        self.min_request_interval = 3.0  # 3 seconds between requests
        self.last_request_time = 0

    def _setup_driver(self) -> bool:
        """Setup Selenium WebDriver with anti-detection measures"""
        try:
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
            chrome_options.add_experimental_option(
                'useAutomationExtension', False)
            chrome_options.add_argument(
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

            try:
                # Try with webdriver-manager
                from webdriver_manager.chrome import ChromeDriverManager
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(
                    service=service, options=chrome_options)
            except Exception as e1:
                logger.warning(f"⚠️ Auto-download failed: {e1}")
                try:
                    # Try system ChromeDriver
                    self.driver = webdriver.Chrome(options=chrome_options)
                except Exception as e2:
                    logger.warning(f"⚠️ System ChromeDriver failed: {e2}")
                    # Try Edge as fallback
                    try:
                        from selenium.webdriver.edge.options import Options as EdgeOptions
                        from selenium.webdriver.edge.service import Service as EdgeService
                        from webdriver_manager.microsoft import EdgeChromiumDriverManager

                        logger.info("🔄 Trying Edge WebDriver as fallback...")
                        edge_options = EdgeOptions()
                        if self.headless:
                            edge_options.add_argument("--headless")
                        edge_options.add_argument("--no-sandbox")
                        edge_options.add_argument("--disable-dev-shm-usage")

                        edge_service = EdgeService(
                            EdgeChromiumDriverManager().install())
                        self.driver = webdriver.Edge(
                            service=edge_service, options=edge_options)

                    except Exception as e3:
                        logger.error(
                            f"❌ All WebDriver options failed: Chrome1={e1}, Chrome2={e2}, Edge={e3}")
                        return False

            # Execute script to remove webdriver property
            try:
                self.driver.execute_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            except Exception:
                pass

            logger.info(
                "✅ Enhanced Selenium WebDriver initialized successfully")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to setup WebDriver: {e}")
            return False

    def _cleanup_driver(self):
        """Clean up WebDriver resources"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("🧹 WebDriver cleaned up")
            except Exception as e:
                logger.warning(f"⚠️ Error cleaning up WebDriver: {e}")
            finally:
                self.driver = None

    async def __aenter__(self):
        """Async context manager entry"""
        if not self._setup_driver():
            raise RuntimeError("Failed to initialize WebDriver")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        self._cleanup_driver()

    async def _rate_limit(self):
        """Ensure we don't make requests too quickly"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last
            logger.debug(
                f"Enhanced fallback rate limiting: sleeping {sleep_time:.2f}s")
            await asyncio.sleep(sleep_time)

        self.last_request_time = time.time()

    def _parse_price_from_text(self, text: str) -> Optional[float]:
        """Extract price from text using regex"""
        if not text or text.strip().lower() in ['no listings', 'no listing', '', 'n/a', '-', '---']:
            return None

        # Look for price patterns like $910.00, $1,515.59, etc.
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

    def _parse_table_headers(self, headers: List[str]) -> Dict[str, int]:
        """Parse table headers to create column mapping for normal and StatTrak™ variants"""
        column_mapping = {}

        for i, header in enumerate(headers):
            header_lower = header.lower().strip()

            # Check if this is a StatTrak™ column
            is_stattrak = "stattrak" in header_lower

            # Identify wear condition
            wear_condition = None
            if "factory new" in header_lower:
                wear_condition = FACTORY_NEW
            elif "minimal wear" in header_lower:
                wear_condition = "Minimal Wear"
            elif "field-tested" in header_lower or "field tested" in header_lower:
                wear_condition = "Field-Tested"
            elif "well-worn" in header_lower or "well worn" in header_lower:
                wear_condition = "Well-Worn"
            elif "battle-scarred" in header_lower or "battle scarred" in header_lower:
                wear_condition = "Battle-Scarred"

            if wear_condition:
                key = f"StatTrak {wear_condition}" if is_stattrak else wear_condition
                column_mapping[key] = i
                logger.debug(f"  Column {i}: {key}")

        return column_mapping

    async def scrape_prices(self, detail_url: str, skin_name: str, need_stattrak: bool = False) -> Dict[str, Optional[float]]:
        """
        Scrape prices from CSGODatabase page using enhanced Selenium

        Args:
            detail_url: URL to the skin's detail page
            skin_name: Name of the skin for logging
            need_stattrak: Whether to include StatTrak™ prices

        Returns:
            Dict mapping wear conditions to prices including both normal and StatTrak™ variants
            Example: {'Factory New': 910.00, 'StatTrak Factory New': 1200.00, 'Minimal Wear': None, ...}
        """
        if not self.driver:
            raise RuntimeError(
                "WebDriver not initialized. Use async context manager.")

        await self._rate_limit()

        logger.info(
            f"🔄 Enhanced Fallback: Scraping {skin_name} from {detail_url}")
        logger.info(f"🎯 Need StatTrak™: {need_stattrak}")

        try:
            # Navigate to the page
            self.driver.get(detail_url)

            # Wait for the page to load and look for the price table
            wait = WebDriverWait(self.driver, self.timeout)

            # Wait for the price comparison table to be present
            wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, ".table-overflow table, table"))
            )

            logger.info(f"✅ Page loaded for {skin_name}")

            # Find the table with price data
            table = self.driver.find_element(
                By.CSS_SELECTOR, ".table-overflow table")

            # Extract headers to identify wear conditions and StatTrak variants
            headers = []
            try:
                header_row = table.find_element(
                    By.CSS_SELECTOR, "thead tr, tr:first-child")
                header_cells = header_row.find_elements(
                    By.CSS_SELECTOR, "th, td")
                headers = [cell.text.strip() for cell in header_cells]
                logger.info(f"📊 Found table headers: {headers}")
            except NoSuchElementException:
                logger.warning(f"⚠️ No table headers found for {skin_name}")
                return {}

            if len(headers) < 2:
                logger.warning(f"⚠️ Invalid table structure for {skin_name}")
                return {}

            # Parse headers to create column mapping
            column_mapping = self._parse_table_headers(headers)
            logger.info(f"🗂️ Column mapping: {column_mapping}")

            # Find the Steam row (look for row containing Steam logo or "Steam" text)
            steam_row = None
            try:
                rows = table.find_elements(By.CSS_SELECTOR, "tbody tr, tr")

                for i, row in enumerate(rows):
                    try:
                        cells = row.find_elements(By.CSS_SELECTOR, "td, th")
                        if cells:
                            first_cell_html = (cells[0].get_attribute(
                                "innerHTML") or "").lower()
                            first_cell_text = cells[0].text.strip().lower()

                            # Check if this is the Steam row
                            if 'steam' in first_cell_html or 'steam' in first_cell_text:
                                steam_row = row
                                logger.info(f"🎯 Found Steam row at index {i}")
                                break
                    except Exception as e:
                        logger.debug(f"Error checking row {i}: {e}")
                        continue

            except NoSuchElementException:
                logger.warning(f"⚠️ No data rows found for {skin_name}")
                return {}

            if not steam_row:
                logger.warning(f"⚠️ No Steam row found for {skin_name}")
                return {}

            # Extract Steam prices
            try:
                steam_cells = steam_row.find_elements(
                    By.CSS_SELECTOR, "td, th")
                prices = {}

                # Extract prices for each mapped column
                for wear_key, col_index in column_mapping.items():
                    if col_index < len(steam_cells):
                        price_text = steam_cells[col_index].text.strip()
                        price = self._parse_price_from_text(price_text)
                        prices[wear_key] = price

                        if price:
                            logger.info(f"  💰 {wear_key}: ${price:.2f}")
                        else:
                            logger.info(
                                f"  ❌ {wear_key}: No listing ({price_text})")

                logger.info(
                    f"✅ Enhanced Fallback: Scraped {len(prices)} variants for {skin_name}")
                return prices

            except Exception as e:
                logger.error(f"❌ Error extracting prices from Steam row: {e}")
                return {}

        except TimeoutException:
            logger.error(
                f"❌ Enhanced fallback timeout waiting for page load: {skin_name}")
            return {}
        except WebDriverException as e:
            logger.error(f"❌ WebDriver error for {skin_name}: {e}")
            return {}
        except Exception as e:
            logger.error(f"❌ Enhanced fallback error for {skin_name}: {e}")
            return {}

    async def get_fallback_prices(
        self,
        detail_url: str,
        skin_name: str,
        required_wear: str,
        stattrak: bool = False
    ) -> Optional[float]:
        """
        Get fallback price for a specific wear condition and StatTrak™ variant

        Args:
            detail_url: URL to skin's detail page
            skin_name: Name of the skin  
            required_wear: Specific wear condition needed
            stattrak: Whether to get StatTrak™ variant

        Returns:
            Price as float or None if not available
        """
        all_prices = await self.scrape_prices(detail_url, skin_name, need_stattrak=stattrak)

        # Look for the specific variant
        key = f"StatTrak {required_wear}" if stattrak else required_wear
        return all_prices.get(key)
