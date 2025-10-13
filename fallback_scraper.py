"""
Fallback Price Scraper for CSGODatabase
Uses Selenium WebDriver to scrape Steam prices from CSGODatabase when Steam API fails
Bypasses anti-bot protection and extracts real-time price data
"""

import asyncio
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import re
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

logger = logging.getLogger(__name__)


class CSGODatabaseFallback:
    """
    Fallback price mechanism using Selenium WebDriver
    Scrapes real-time Steam prices from CSGODatabase when Steam API fails
    """
    
    def __init__(self, headless: bool = True):
        self.driver = None
        self.headless = headless
        self.timeout = 30
        
        # Rate limiting for scraping (be respectful)
        self.last_request_time = 0
        self.min_request_interval = 3.0  # 3 seconds between requests
        
    def _setup_driver(self):
        """Setup Chrome WebDriver with appropriate options"""
        try:
            chrome_options = Options()
            
            if self.headless:
                chrome_options.add_argument("--headless")
            
            # Add options to avoid detection
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            # Set user agent to look like real browser
            chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36")
            
            # Try different methods to setup driver
            try:
                # First try: Auto-download ChromeDriver
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            except Exception as e1:
                logger.warning(f"⚠️ Auto-download failed: {e1}")
                try:
                    # Second try: Use system ChromeDriver (if installed)
                    self.driver = webdriver.Chrome(options=chrome_options)
                except Exception as e2:
                    logger.warning(f"⚠️ System ChromeDriver failed: {e2}")
                    # Third try: Try Edge as fallback
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
                        
                        edge_service = EdgeService(EdgeChromiumDriverManager().install())
                        self.driver = webdriver.Edge(service=edge_service, options=edge_options)
                        
                    except Exception as e3:
                        logger.error(f"❌ All WebDriver options failed: Chrome1={e1}, Chrome2={e2}, Edge={e3}")
                        return False
            
            # Execute script to remove webdriver property (if Chrome)
            try:
                self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            except:
                pass  # Ignore if this fails
            
            logger.info("✅ Selenium WebDriver initialized successfully")
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
            logger.debug(f"Fallback rate limiting: sleeping {sleep_time:.2f}s")
            await asyncio.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def _parse_price_from_text(self, text: str) -> Optional[float]:
        """Extract price from text using regex"""
        if not text or text.strip().lower() in ['no listings', 'no listing', '', 'n/a', '-', '---']:
            return None
            
        # Look for price patterns like $910.00, $1,515.59, etc.
        price_patterns = [
            r'\$\s*([\d,]+\.?\d*)',  # $910.00, $1,515.59
            r'([\d,]+\.?\d*)\s*USD', # 910.00 USD
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
    
    def _extract_wear_condition_from_header(self, header_text: str) -> Optional[str]:
        """Extract wear condition from table header text"""
        if not header_text:
            return None
            
        header_lower = header_text.lower().strip()
        
        # Map table headers to our wear conditions
        wear_mapping = {
            'factory new': 'Factory New',
            'fn': 'Factory New',
            'minimal wear': 'Minimal Wear', 
            'mw': 'Minimal Wear',
            'field-tested': 'Field-Tested',
            'field tested': 'Field-Tested',
            'ft': 'Field-Tested',
            'well-worn': 'Well-Worn',
            'well worn': 'Well-Worn',
            'ww': 'Well-Worn',
            'battle-scarred': 'Battle-Scarred',
            'battle scarred': 'Battle-Scarred',
            'bs': 'Battle-Scarred'
        }
        
        for key, value in wear_mapping.items():
            if key in header_lower:
                return value
        
        return None
    
    async def scrape_steam_prices(self, detail_url: str, skin_name: str) -> Dict[str, Optional[float]]:
        """
        Scrape Steam prices from CSGODatabase page using Selenium
        
        Args:
            detail_url: URL to the skin's detail page
            skin_name: Name of the skin for logging
            
        Returns:
            Dict mapping wear conditions to prices: {'Factory New': 910.00, 'Minimal Wear': None, ...}
        """
        if not self.driver:
            raise RuntimeError("WebDriver not initialized. Use async context manager.")
        
        await self._rate_limit()
        
        logger.info(f"🔄 Fallback: Scraping {skin_name} from {detail_url}")
        
        try:
            # Navigate to the page
            self.driver.get(detail_url)
            
            # Wait for the page to load and look for the price table
            wait = WebDriverWait(self.driver, self.timeout)
            
            # Wait for the price comparison table to be present
            wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".table-overflow table, table"))
            )
            
            logger.info(f"✅ Page loaded for {skin_name}")
            
            # Find the table with price data
            table = self.driver.find_element(By.CSS_SELECTOR, ".table-overflow table")
            
            # Extract headers to identify wear conditions
            headers = []
            try:
                header_row = table.find_element(By.CSS_SELECTOR, "thead tr, tr:first-child")
                header_cells = header_row.find_elements(By.CSS_SELECTOR, "th, td")
                headers = [cell.text.strip() for cell in header_cells]
                logger.info(f"� Found table headers: {headers}")
            except NoSuchElementException:
                logger.warning(f"⚠️ No table headers found for {skin_name}")
                return {}
            
            if len(headers) < 2:
                logger.warning(f"⚠️ Invalid table structure for {skin_name}")
                return {}
            
            # Find the Steam row (look for row containing Steam logo or "Steam" text)
            steam_row = None
            try:
                rows = table.find_elements(By.CSS_SELECTOR, "tbody tr, tr")
                
                for i, row in enumerate(rows):
                    try:
                        cells = row.find_elements(By.CSS_SELECTOR, "td, th")
                        if cells:
                            first_cell_text = cells[0].text.strip().lower()
                            # Check if this is the Steam row
                            if 'steam' in first_cell_text or i == 1:  # Steam is usually first data row
                                steam_row = row
                                logger.info(f"🎯 Found Steam row: {first_cell_text}")
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
                steam_cells = steam_row.find_elements(By.CSS_SELECTOR, "td, th")
                prices = {}
                
                # Skip first cell (platform name), match remaining cells to headers
                for i, cell in enumerate(steam_cells[1:], 1):
                    if i < len(headers):
                        wear_condition = self._extract_wear_condition_from_header(headers[i])
                        if wear_condition:
                            price_text = cell.text.strip()
                            price = self._parse_price_from_text(price_text)
                            prices[wear_condition] = price
                            
                            if price:
                                logger.info(f"  💰 {wear_condition}: ${price:.2f}")
                            else:
                                logger.info(f"  ❌ {wear_condition}: No listing ({price_text})")
                
                logger.info(f"✅ Fallback: Scraped {len(prices)} wear conditions for {skin_name}")
                return prices
                
            except Exception as e:
                logger.error(f"❌ Error extracting prices from Steam row: {e}")
                return {}
                
        except TimeoutException:
            logger.error(f"❌ Fallback timeout waiting for page load: {skin_name}")
            return {}
        except WebDriverException as e:
            logger.error(f"❌ WebDriver error for {skin_name}: {e}")
            return {}
        except Exception as e:
            logger.error(f"❌ Fallback error for {skin_name}: {e}")
            return {}
    
    async def get_fallback_prices(self, detail_url: str, skin_name: str, required_wears: List[str]) -> Dict[str, Tuple[Optional[float], Optional[float]]]:
        """
        Get fallback prices using Selenium scraping
        
        Args:
            detail_url: URL to skin's detail page
            skin_name: Name of the skin  
            required_wears: List of wear conditions needed
            
        Returns:
            Dict mapping wear to (normal_price, stattrak_price) tuples
        """
        all_prices = await self.scrape_steam_prices(detail_url, skin_name)
        
        # CSGODatabase typically shows combined Steam prices, not separate normal/StatTrak
        # We'll use the scraped price for normal and return None for StatTrak
        result = {}
        for wear in required_wears:
            normal_price = all_prices.get(wear)
            result[wear] = (normal_price, None)  # StatTrak not available from scraping
        
        return result


# Test function
async def test_fallback():
    """Test the fallback mechanism with real scraping"""
    async with CSGODatabaseFallback(headless=False) as fallback:  # Set to False to see browser
        url = "https://www.csgodatabase.com/skins/awp-lightning-strike/"
        required_wears = ['Factory New', 'Minimal Wear', 'Field-Tested', 'Well-Worn', 'Battle-Scarred']
        
        prices = await fallback.get_fallback_prices(url, "AWP Lightning Strike", required_wears)
        
        print(f"Scraped prices: {prices}")
        for wear, (normal, stattrak) in prices.items():
            if normal:
                print(f"  {wear}: ${normal:.2f}")
            else:
                print(f"  {wear}: No listing")


if __name__ == "__main__":
    # Set up logging for testing
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
    
    # Run test
    asyncio.run(test_fallback())