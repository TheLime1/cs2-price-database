"""
CSGOSkins.gg Wear Range Scraper for CS2 Price Database V3.0

This module scrapes wear range data and achievability information from csgoskins.gg
to validate which wear conditions are actually achievable for each skin.

Data collected:
- Wear ranges (min/max float values) for each wear condition
- Achievability flags (whether a wear condition is possible for a skin)
- StatTrak availability for each achievable wear condition

Integration:
- Used by V3.0 migration script to enhance database with wear data
- Can be used standalone for wear range validation
"""

import asyncio
import logging
import time
import random
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.options import Options

logger = logging.getLogger(__name__)


@dataclass
class WearRange:
    """Represents a wear range for a specific condition"""
    wear_condition: str
    min_float: float
    max_float: float
    achievable: bool
    has_stattrak: bool


@dataclass
class SkinWearData:
    """Complete wear data for a skin"""
    skin_name: str
    weapon: str
    wear_ranges: List[WearRange]
    scraped_at: str


class CSGOSkinsGGScraper:
    """Scraper for csgoskins.gg wear range data"""

    # Standard CS2 wear condition float ranges
    WEAR_CONDITION_RANGES = {
        'Factory New': (0.00, 0.07),
        'Minimal Wear': (0.07, 0.15),
        'Field-Tested': (0.15, 0.38),
        'Well-Worn': (0.38, 0.45),
        'Battle-Scarred': (0.45, 1.00)
    }

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.driver: Optional[webdriver.Chrome] = None
        self.base_url = "https://csgoskins.gg"

    def _create_driver(self) -> webdriver.Chrome:
        """Create a Chrome WebDriver instance"""
        chrome_options = Options()

        if self.headless:
            chrome_options.add_argument('--headless=new')

        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument(
            '--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option(
            'excludeSwitches', ['enable-automation'])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        # Random user agent
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]
        chrome_options.add_argument(f'user-agent={random.choice(user_agents)}')

        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(30)

        return driver

    async def initialize(self):
        """Initialize the scraper"""
        logger.info("🌐 Initializing CSGOSkins.gg scraper...")
        loop = asyncio.get_event_loop()
        self.driver = await loop.run_in_executor(None, self._create_driver)
        logger.info("✅ CSGOSkins.gg scraper initialized")

    async def cleanup(self):
        """Cleanup resources"""
        if self.driver:
            logger.info("🧹 Cleaning up CSGOSkins.gg scraper...")
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.driver.quit)
            self.driver = None

    def _build_search_url(self, weapon: str, skin_name: str) -> str:
        """Build search URL for csgoskins.gg"""
        # Remove common prefixes
        weapon_clean = weapon.replace(
            'StatTrak™ ', '').replace('Souvenir ', '')

        # Format for URL - csgoskins.gg uses format like: /items/awp-asiimov (all lowercase)
        skin_slug = f"{weapon_clean}-{skin_name}".replace(' ', '-').lower()

        return f"{self.base_url}/items/{skin_slug}"

    def _extract_wear_ranges(self) -> List[WearRange]:
        """Extract wear range data from the current page"""
        wear_ranges = []

        try:
            # Wait for wear range content to load
            # Look for the "Wear Range" heading first
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//h2[contains(text(), 'Wear Range')]"))
            )

            # Method 1: Extract from wear range text format: "0.15 - 0.38 = Field-Tested (FT)"
            wear_divs = self.driver.find_elements(
                By.XPATH, "//div[contains(text(), ' = ') and contains(text(), '0.')]")

            wear_data_from_divs = {}
            for div in wear_divs:
                try:
                    text = div.text.strip()
                    if ' = ' not in text or ' - ' not in text:
                        continue

                    parts = text.split(' = ')
                    if len(parts) != 2:
                        continue

                    range_part = parts[0].strip()  # "0.15 - 0.38"
                    condition_part = parts[1].strip()  # "Field-Tested (FT)"

                    # Extract condition name (remove abbreviation)
                    wear_condition = condition_part.split(' (')[0].strip()

                    # Parse min and max float values
                    range_values = range_part.split(' - ')
                    if len(range_values) != 2:
                        continue

                    min_float = float(range_values[0].strip())
                    max_float = float(range_values[1].strip())

                    wear_data_from_divs[wear_condition] = (
                        min_float, max_float)
                    logger.debug(
                        f"   📏 Found range: {wear_condition} [{min_float} - {max_float}]")

                except (ValueError, IndexError) as e:
                    logger.debug(f"   ⚠️ Skipping div parse: {e}")
                    continue

            # Method 2: Check achievability from price listings
            # Find all wear condition spans (format: "Factory New", "Minimal Wear", etc.)
            # These are in spans with class "whitespace-nowrap"
            condition_spans = self.driver.find_elements(By.XPATH,
                                                        "//span[@class='whitespace-nowrap' and (contains(text(), 'Factory New') or contains(text(), 'Minimal Wear') or contains(text(), 'Field-Tested') or contains(text(), 'Well-Worn') or contains(text(), 'Battle-Scarred'))]")

            achievable_conditions = {}
            stattrak_conditions = {}

            for span in condition_spans:
                try:
                    condition_text = span.text.strip()

                    # Skip if it contains "StatTrak" - we'll handle those separately
                    if "StatTrak" in condition_text:
                        continue

                    # Normalize condition name
                    wear_condition = condition_text.strip()

                    # Check the grandparent row div for "Not possible"
                    # Structure: grandparent (row) -> parent (grow div) -> span (condition)
                    parent = span.find_element(By.XPATH, "./..")
                    grandparent = parent.find_element(By.XPATH, "./..")
                    grandparent_text = grandparent.text.strip()

                    # If row contains "Not possible", this wear is not achievable
                    is_achievable = "Not possible" not in grandparent_text

                    achievable_conditions[wear_condition] = is_achievable
                    logger.debug(
                        f"   {'✅' if is_achievable else '❌'} {wear_condition}: {'Achievable' if is_achievable else 'Not possible'}")

                except Exception as e:
                    logger.debug(f"   ⚠️ Error checking achievability: {e}")
                    continue

            # Method 3: Check StatTrak availability
            stattrak_spans = self.driver.find_elements(By.XPATH,
                                                       "//span[@class='whitespace-nowrap' and contains(text(), 'StatTrak')]")

            for span in stattrak_spans:
                try:
                    condition_text = span.text.strip()
                    # This span only contains "StatTrak", need to find the next sibling for condition
                    # Get parent, then find the next span sibling which has the condition name
                    parent = span.find_element(By.XPATH, "./..")

                    # Try to find the condition span in the same parent
                    try:
                        condition_span = parent.find_element(By.XPATH,
                                                             ".//span[@class='whitespace-nowrap' and (contains(text(), 'Factory New') or contains(text(), 'Minimal Wear') or contains(text(), 'Field-Tested') or contains(text(), 'Well-Worn') or contains(text(), 'Battle-Scarred'))]")
                        wear_condition = condition_span.text.strip()
                    except:
                        # Fallback: might be in adjacent element
                        continue

                    # Check grandparent row for "Not possible"
                    grandparent = parent.find_element(By.XPATH, "./..")
                    grandparent_text = grandparent.text.strip()

                    # If StatTrak version shows a price (not "Not possible"), StatTrak is available
                    has_stattrak = "Not possible" not in grandparent_text

                    stattrak_conditions[wear_condition] = has_stattrak
                    logger.debug(
                        f"   {'🌟' if has_stattrak else '⭕'} StatTrak {wear_condition}: {'Available' if has_stattrak else 'Not available'}")

                except Exception as e:
                    logger.debug(f"   ⚠️ Error checking StatTrak: {e}")
                    continue

            # Combine all data into WearRange objects
            # Use standard wear conditions as base
            for condition, (min_val, max_val) in self.WEAR_CONDITION_RANGES.items():
                # Get actual range if found, otherwise use standard
                if condition in wear_data_from_divs:
                    min_float, max_float = wear_data_from_divs[condition]
                else:
                    min_float, max_float = min_val, max_val

                # Check achievability
                achievable = achievable_conditions.get(
                    condition, True)  # Default to True

                # Check StatTrak availability
                has_stattrak = stattrak_conditions.get(
                    condition, achievable)  # Default to same as achievable

                wear_range = WearRange(
                    wear_condition=condition,
                    min_float=min_float,
                    max_float=max_float,
                    achievable=achievable,
                    has_stattrak=has_stattrak
                )

                wear_ranges.append(wear_range)
                logger.debug(f"   ✓ Final: {condition} [{min_float:.4f}-{max_float:.4f}] "
                             f"achievable={achievable} stattrak={has_stattrak}")

        except TimeoutException:
            logger.warning("⏰ Timeout waiting for wear range content")
        except Exception as e:
            logger.error(f"❌ Error extracting wear ranges: {e}")
            import traceback
            traceback.print_exc()

        return wear_ranges

    def _extract_wear_ranges_alternative(self) -> List[WearRange]:
        """Alternative extraction method if primary fails"""
        wear_ranges = []

        try:
            # Try finding wear info divs or other containers
            wear_elements = self.driver.find_elements(
                By.CSS_SELECTOR, "[data-wear-condition]")

            for elem in wear_elements:
                try:
                    wear_condition = elem.get_attribute('data-wear-condition')
                    min_float = float(elem.get_attribute(
                        'data-min-float') or 0.0)
                    max_float = float(elem.get_attribute(
                        'data-max-float') or 1.0)
                    achievable = elem.get_attribute(
                        'data-achievable') == 'true'
                    has_stattrak = elem.get_attribute(
                        'data-stattrak') == 'true'

                    wear_range = WearRange(
                        wear_condition=wear_condition,
                        min_float=min_float,
                        max_float=max_float,
                        achievable=achievable,
                        has_stattrak=has_stattrak
                    )

                    wear_ranges.append(wear_range)

                except Exception as e:
                    logger.debug(
                        f"Error parsing alternative wear element: {e}")
                    continue

        except Exception as e:
            logger.warning(f"⚠️ Alternative extraction also failed: {e}")

        return wear_ranges

    async def scrape_skin_wear_data(self, weapon: str, skin_name: str) -> Optional[SkinWearData]:
        """Scrape wear range data for a specific skin"""
        from datetime import datetime

        logger.info(f"🔍 Scraping wear data for: {weapon} | {skin_name}")

        try:
            # Build URL
            url = self._build_search_url(weapon, skin_name)
            logger.debug(f"   🌐 URL: {url}")

            # Navigate to page
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.driver.get, url)

            # Wait for page to load
            await asyncio.sleep(random.uniform(2.0, 4.0))

            # Extract wear ranges
            wear_ranges = await loop.run_in_executor(None, self._extract_wear_ranges)

            if not wear_ranges:
                logger.warning(
                    f"⚠️ No wear data found for {weapon} | {skin_name}")
                # Return default data with all conditions as achievable
                wear_ranges = self._generate_default_wear_ranges()

            skin_wear_data = SkinWearData(
                skin_name=skin_name,
                weapon=weapon,
                wear_ranges=wear_ranges,
                scraped_at=datetime.now().isoformat()
            )

            logger.info(
                f"✅ Scraped {len(wear_ranges)} wear ranges for {skin_name}")
            return skin_wear_data

        except Exception as e:
            logger.error(f"❌ Error scraping {weapon} | {skin_name}: {e}")
            return None

    def _generate_default_wear_ranges(self) -> List[WearRange]:
        """Generate default wear ranges when scraping fails"""
        logger.debug("   📋 Generating default wear ranges (all achievable)")

        return [
            WearRange(
                wear_condition=condition,
                min_float=min_val,
                max_float=max_val,
                achievable=True,  # Assume achievable by default
                has_stattrak=True  # Assume StatTrak available by default
            )
            for condition, (min_val, max_val) in self.WEAR_CONDITION_RANGES.items()
        ]

    async def scrape_multiple_skins(self, skins: List[Dict[str, str]]) -> List[SkinWearData]:
        """Scrape wear data for multiple skins"""
        results = []

        for i, skin in enumerate(skins, 1):
            weapon = skin.get('weapon', '')
            skin_name = skin.get('skin_name', '')

            logger.info(
                f"[{i}/{len(skins)}] Processing: {weapon} | {skin_name}")

            wear_data = await self.scrape_skin_wear_data(weapon, skin_name)

            if wear_data:
                results.append(wear_data)

            # Rate limiting - be respectful to csgoskins.gg
            if i < len(skins):
                delay = random.uniform(3.0, 6.0)
                logger.debug(
                    f"   ⏳ Waiting {delay:.1f}s before next request...")
                await asyncio.sleep(delay)

        logger.info(f"✅ Completed scraping {len(results)}/{len(skins)} skins")
        return results

    def convert_to_database_format(self, wear_data: SkinWearData) -> Dict[str, Any]:
        """Convert SkinWearData to database format"""
        wear_ranges_dict = {}

        for wr in wear_data.wear_ranges:
            wear_ranges_dict[wr.wear_condition] = {
                'min': wr.min_float,
                'max': wr.max_float,
                'achievable': wr.achievable,
                'has_stattrak': wr.has_stattrak
            }

        return {
            'wear_ranges': wear_ranges_dict,
            'scraped_at': wear_data.scraped_at
        }


async def main():
    """Test the scraper with a few skins"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Test skins
    test_skins = [
        {'weapon': 'AK-47', 'skin_name': 'Redline'},
        {'weapon': 'AWP', 'skin_name': 'Asiimov'},
        {'weapon': 'M4A4', 'skin_name': 'Howl'},
    ]

    scraper = CSGOSkinsGGScraper(headless=False)

    try:
        await scraper.initialize()

        results = await scraper.scrape_multiple_skins(test_skins)

        print("\n" + "="*80)
        print("WEAR RANGE SCRAPING RESULTS")
        print("="*80)

        for wear_data in results:
            print(f"\n{wear_data.weapon} | {wear_data.skin_name}")
            print("-" * 60)

            for wr in wear_data.wear_ranges:
                achievable_icon = "✅" if wr.achievable else "❌"
                stattrak_icon = "🌟" if wr.has_stattrak else "  "

                print(f"  {achievable_icon} {stattrak_icon} {wr.wear_condition:20s} "
                      f"{wr.min_float:.4f} - {wr.max_float:.4f}")

        print("\n" + "="*80)

    finally:
        await scraper.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
