"""
Price Collection System for CS2 Skins
Collects Steam Market prices for all skins with comprehensive logging,
environment-based configuration, and intelligent price freshness checking.
"""

from steam_api import SteamMarketAPIClient
from proxy_manager import proxy_manager
from optimized_fallback_scraper import OptimizedCSGODatabaseScraper
from summary_logger import get_summary_logger
import json
import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import os
import re
import signal
import sys
import urllib.parse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Environment-based configuration
LOG_DIR = os.getenv("LOG_DIR", "logs")
MAIN_LOG_FILE = os.getenv("MAIN_LOG_FILE", "price_collection.log")
SUCCESS_ONLY_LOG_FILE = os.getenv(
    "SUCCESS_ONLY_LOG_FILE", "success_only_responses.log")
API_RATE_LOG_FILE = os.getenv("API_RATE_LOG_FILE", "api_rate_test.log")

# Constants
SUMMARY_REPORT_MESSAGE = "📊 Summary report saved to logs/summary.txt"

# Ensure log directory exists
os.makedirs(LOG_DIR, exist_ok=True)

# Set up comprehensive logging system


def setup_logging():
    """Configure logging with environment-based settings"""
    log_level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper())

    # Main logger configuration (OVERWRITE mode - clean logs each run)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(os.path.join(
                LOG_DIR, MAIN_LOG_FILE), mode='w', encoding='utf-8'),  # OVERWRITE mode
            logging.StreamHandler(sys.stdout)
        ]
    )

    # Set up specialized loggers
    setup_success_only_logger()
    setup_api_rate_logger()


def setup_success_only_logger():
    """Set up logger for API responses with success but no price data"""
    success_only_logger = logging.getLogger('success_only')
    if not success_only_logger.handlers:
        handler = logging.FileHandler(
            os.path.join(LOG_DIR, SUCCESS_ONLY_LOG_FILE), mode='w', encoding='utf-8'
        )
        formatter = logging.Formatter('%(asctime)s | %(message)s')
        handler.setFormatter(formatter)
        success_only_logger.addHandler(handler)
        success_only_logger.setLevel(logging.INFO)
        success_only_logger.propagate = False


def setup_api_rate_logger():
    """Set up logger for API rate testing and performance monitoring"""
    api_rate_logger = logging.getLogger('api_rate')
    if not api_rate_logger.handlers:
        handler = logging.FileHandler(
            os.path.join(LOG_DIR, API_RATE_LOG_FILE), mode='w', encoding='utf-8'
        )
        formatter = logging.Formatter('%(asctime)s | %(message)s')
        handler.setFormatter(formatter)
        api_rate_logger.addHandler(handler)
        api_rate_logger.setLevel(logging.INFO)
        api_rate_logger.propagate = False


# Initialize logging
setup_logging()
logger = logging.getLogger(__name__)
success_only_logger = logging.getLogger('success_only')
api_rate_logger = logging.getLogger('api_rate')


def parse_date(date_str: str) -> datetime:
    """Parse a date string into a datetime object"""
    if date_str == 'Unknown' or not date_str:
        return datetime.min

    try:
        # Try different date formats
        formats = [
            "%d %B %Y",      # "14 August 2013", "17 September 2025"
            "%Y-%m-%d",
            "%d-%m-%Y",
            "%m/%d/%Y",
            "%Y/%m/%d",
            "%B %d, %Y"
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        # If no format works, return min datetime
        return datetime.min
    except (ValueError, TypeError):
        return datetime.min


# Logging is already set up in setup_logging() function above
# This duplicate configuration is removed to prevent log file overwriting
logger = logging.getLogger(__name__)


def safe_log_name(name: str) -> str:
    """Convert market hash name to logging-safe ASCII version"""
    return name.replace("™", "(TM)").encode('ascii', 'replace').decode('ascii')


class PriceCollector:
    """Collects Steam Market prices for CS2 skins with comprehensive environment-based configuration"""

    def __init__(self, ignore_stattrak: bool = False, missing_only: bool = False, debug: bool = False, noproxy: bool = False, no_fallback: bool = False, fallback_only: bool = False, update_availability: bool = False):
        # Load configuration from environment variables
        self.database_path = os.getenv(
            "DATABASE_FILE", "data/skins_database.json")
        self.checkpoint_path = os.getenv(
            "CHECKPOINT_FILE", "price_collection_checkpoint.json")

        # Command line flags (override environment)
        self.ignore_stattrak = ignore_stattrak
        self.missing_only = missing_only
        self.debug = debug or os.getenv(
            "DEBUG_MODE", "false").lower() == "true"
        self.noproxy = noproxy
        self.no_fallback = no_fallback
        self.fallback_only = fallback_only
        self.update_availability = update_availability

        # Environment-based configuration
        self.price_update_interval_hours = float(
            os.getenv("PRICE_UPDATE_INTERVAL_HOURS", "24"))
        self.max_concurrent_requests = int(
            os.getenv("MAX_CONCURRENT_REQUESTS", "50"))
        self.webdriver_pool_size = int(os.getenv("WEBDRIVER_POOL_SIZE", "3"))
        self.batch_size_skins = int(os.getenv("BATCH_SIZE_SKINS", "20"))
        self.batch_size_variants = int(os.getenv("BATCH_SIZE_VARIANTS", "50"))
        self.batch_size_missing_items = int(
            os.getenv("BATCH_SIZE_MISSING_ITEMS", "50"))

        # Artificial delays (configurable)
        self.delay_between_requests = float(
            os.getenv("DELAY_BETWEEN_REQUESTS", "0.1"))
        self.delay_between_batches = float(
            os.getenv("DELAY_BETWEEN_BATCHES", "2.0"))
        self.delay_between_skins = float(
            os.getenv("DELAY_BETWEEN_SKINS", "0.5"))
        self.delay_before_save = float(os.getenv("DELAY_BEFORE_SAVE", "0.1"))
        self.delay_after_save = float(os.getenv("DELAY_AFTER_SAVE", "0.2"))

        # Proxy configuration
        if self.noproxy:
            proxy_manager.use_proxies = False
            logger.info("Proxies disabled via --noproxy flag")

        # Initialize clients
        self.steam_client = SteamMarketAPIClient()
        self.fallback_scraper = None
        self.shutdown_requested = False

        # Initialize summary logger
        self.summary_logger = get_summary_logger()

        # Collect all environment variables for summary
        env_vars = {k: v for k, v in os.environ.items() if not any(
            sensitive in k.lower() for sensitive in ['password', 'auth', 'token', 'key', 'secret']
        )}
        self.summary_logger.initialize_stats(env_vars)

        # Initialize fallback scraper (will be created when needed)
        self.fallback_scraper = None
        self.fallback_pool_size = 3  # Number of concurrent WebDriver instances
        # Add your proxies here if needed        # API rate tracking for testing
        self.fallback_proxies = []
        self.api_call_log = []
        self.rate_test_enabled = True  # Set to False to disable rate tracking

        # Load database
        self.load_database()

        # Load checkpoint if exists
        self.checkpoint = self.load_checkpoint()

        # Stats tracking
        self.stats = {
            'total_skins': 0,
            'total_variants': 0,
            'processed_skins': 0,
            'processed_variants': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'start_time': None,
            'last_update': None
        }

        # Set up signal handlers for graceful shutdown
        self.setup_signal_handlers()

        # Initialize API rate test log
        if self.rate_test_enabled:
            self.init_rate_test_log()

    def init_rate_test_log(self):
        """Initialize the API rate test log file"""
        with open('api_rate_test.log', 'w', encoding='utf-8') as f:
            f.write(
                f"API Rate Limit Test Log - Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(
                "Format: Timestamp | Status | Success | Response Time | Item Name\n")
            f.write("=" * 80 + "\n\n")
        logger.info(
            "[API-TEST] API rate testing enabled - logging to api_rate_test.log")

    def log_api_call(self, market_hash_name: str, status_code: int, success: bool, response_time: float = 0, wait_time: float = 0):
        """Log API call details for rate limit testing including wait times"""
        if not self.rate_test_enabled:
            return

        timestamp = datetime.now()

        # Add to memory log
        self.api_call_log.append({
            'timestamp': timestamp,
            'market_hash_name': market_hash_name,
            'status_code': status_code,
            'success': success,
            'response_time': response_time,
            'wait_time': wait_time
        })

        # Write to file immediately with wait time information
        wait_info = f" | Wait: {wait_time:.3f}s" if wait_time > 0 else ""
        log_entry = f"{timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} | Status: {status_code} | Success: {success} | Time: {response_time:.3f}s{wait_info} | Item: {safe_log_name(market_hash_name)}\n"

        with open('api_rate_test.log', 'a', encoding='utf-8') as f:
            f.write(log_entry)

        # Calculate and log rate every 10 calls
        if len(self.api_call_log) % 10 == 0:
            now = datetime.now()
            one_min_ago = now - timedelta(minutes=1)
            recent = [
                c for c in self.api_call_log if c['timestamp'] > one_min_ago]

            calls_per_min = len(recent)
            rate_limits = len(
                [c for c in recent if c.get('status_code') == 429])
            errors = len([c for c in recent if not c['success']])

            log_line = f"{now.strftime('%H:%M:%S')} | {calls_per_min}/min | {rate_limits} limits | {errors} errors | {len(self.api_call_log)} total\\n"

            with open('api_rate_test.log', 'a', encoding='utf-8') as f:
                f.write(log_line)

            if errors > 0:
                logger.warning(
                    f"API issues: {errors} errors, {rate_limits} rate limits in last minute")

    def log_rate_statistics(self):
        """Calculate and log current API call rate"""
        if not self.rate_test_enabled or len(self.api_call_log) < 2:
            return

        now = datetime.now()

        # Calculate calls in last minute
        one_minute_ago = now - timedelta(minutes=1)
        recent_calls = [
            call for call in self.api_call_log if call['timestamp'] > one_minute_ago]
        calls_per_minute = len(recent_calls)

        # Calculate calls in last 5 minutes
        five_minutes_ago = now - timedelta(minutes=5)
        five_min_calls = [
            call for call in self.api_call_log if call['timestamp'] > five_minutes_ago]
        calls_per_5min = len(five_min_calls)

        # Count rate limit hits (status 429)
        rate_limit_hits = len(
            [call for call in recent_calls if call['status_code'] == 429])

        # Log summary
        summary = f"\n--- RATE SUMMARY at {now.strftime('%H:%M:%S')} ---\n"
        summary += f"Calls in last 1 min: {calls_per_minute}\n"
        summary += f"Calls in last 5 min: {calls_per_5min} (avg {calls_per_5min/5:.1f}/min)\n"
        summary += f"Rate limit hits (429) in last min: {rate_limit_hits}\n"
        summary += f"Total API calls logged: {len(self.api_call_log)}\n"
        summary += "-" * 50 + "\n\n"

        with open('api_rate_test.log', 'a', encoding='utf-8') as f:
            f.write(summary)

        # Also log to console if rate limit hit
        if rate_limit_hits > 0:
            logger.warning(
                f"[RATE-LIMIT] RATE LIMIT HIT! {rate_limit_hits} times in last minute. Calls/min: {calls_per_minute}")

    def setup_signal_handlers(self):
        """Set up signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            logger.info(
                f"Received signal {signum} - initiating graceful shutdown...")
            self.shutdown_requested = True

        # Handle SIGINT (Ctrl+C) and SIGTERM
        signal.signal(signal.SIGINT, signal_handler)
        if hasattr(signal, 'SIGTERM'):  # SIGTERM may not be available on Windows
            signal.signal(signal.SIGTERM, signal_handler)

    def graceful_shutdown(self):
        """Perform graceful shutdown operations"""
        logger.info("Performing graceful shutdown...")
        self.save_checkpoint()
        self.save_database()

        # Clean up fallback scraper if it exists
        if self.fallback_scraper:
            logger.info("Cleaning up fallback scraper...")
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._cleanup_fallback_scraper())
                else:
                    asyncio.run(self._cleanup_fallback_scraper())
            except Exception as e:
                logger.warning(f"Error cleaning up fallback scraper: {e}")

        logger.info("All data saved. Shutdown complete.")

        sys.exit(0)

    def load_database(self):
        """Load the skins database"""
        logger.info(f"Loading database from {self.database_path}")

        with open(self.database_path, 'r', encoding='utf-8') as f:
            self.database = json.load(f)

        self.skins = self.database['skins']
        logger.info(f"Loaded {len(self.skins)} skins from database")

    def load_checkpoint(self) -> Dict:
        """Load checkpoint data if it exists"""
        if os.path.exists(self.checkpoint_path):
            try:
                with open(self.checkpoint_path, 'r', encoding='utf-8') as f:
                    checkpoint = json.load(f)
                logger.info(
                    f"Loaded checkpoint: processed {checkpoint.get('processed_skins', 0)} skins")
                return checkpoint
            except Exception as e:
                logger.warning(f"Could not load checkpoint: {e}")

        return {
            'processed_skins': 0,
            'processed_variants': 0,
            'last_processed_skin_id': None,
            'failed_items': [],
            'last_update': None
        }

    def save_checkpoint(self):
        """Save current progress to checkpoint file"""
        self.checkpoint['last_update'] = datetime.now().isoformat()

        with open(self.checkpoint_path, 'w', encoding='utf-8') as f:
            json.dump(self.checkpoint, f, indent=2)

        # Track checkpoint saves in summary logger
        self.summary_logger.log_checkpoint_save()
        logger.debug("Checkpoint saved")

    def save_database(self):
        """Save the updated database with artificial delay"""
        # Apply artificial delay before saving
        if self.delay_before_save > 0:
            time.sleep(self.delay_before_save)

        self.database['data_status']['last_price_update'] = datetime.now(
        ).isoformat()

        with open(self.database_path, 'w', encoding='utf-8') as f:
            json.dump(self.database, f, indent=2, ensure_ascii=False)

        logger.info("Database saved with updated prices")

        # Apply artificial delay after saving
        if self.delay_after_save > 0:
            time.sleep(self.delay_after_save)

    def is_price_fresh(self, variant: Dict, stattrak: bool = False) -> bool:
        """Check if price data is fresh enough based on update interval"""
        if self.price_update_interval_hours <= 0:
            return False  # Always update if interval is 0 or negative

        price_type = 'stattrak' if stattrak else 'normal'
        prices = variant.get('prices', {})

        if price_type not in prices:
            return False  # No price data exists

        price_data = prices[price_type]
        if not price_data.get('last_updated'):
            return False  # No timestamp available

        try:
            last_updated = datetime.fromisoformat(price_data['last_updated'])
            now = datetime.now()
            hours_since_update = (now - last_updated).total_seconds() / 3600

            is_fresh = hours_since_update < self.price_update_interval_hours

            if is_fresh and self.debug:
                logger.debug(
                    f"Price is fresh ({hours_since_update:.1f}h old, limit: {self.price_update_interval_hours}h)")

            return is_fresh

        except (ValueError, TypeError) as e:
            logger.debug(f"Could not parse last_updated timestamp: {e}")
            return False  # Invalid timestamp, treat as stale

    def sort_skins_by_date(self) -> List[Tuple[Dict, datetime]]:
        """Sort skins by introduction date (newest first)"""
        logger.info("Sorting skins by introduction date (newest first)...")

        skins_with_dates = []
        for skin in self.skins:
            intro_date = parse_date(skin.get('introduced', 'Unknown'))
            if intro_date:
                skins_with_dates.append((skin, intro_date))

        # Sort by date (newest first)
        skins_with_dates.sort(key=lambda x: x[1], reverse=True)

        logger.info(f"Sorted {len(skins_with_dates)} skins by date")
        return skins_with_dates

    def create_market_hash_name(self, skin: Dict, variant: Dict, stattrak: bool = False) -> str:
        """Create Steam Market hash name for a skin variant"""
        weapon = skin['weapon']
        skin_name = skin['skin_name']
        wear = variant['wear']

        # Handle StatTrak prefix
        prefix = "StatTrak™ " if stattrak else ""

        # Fix incorrectly split weapon names in the database
        # These weapons were split incorrectly and need to be reconstructed
        weapon_fixes = {
            "Desert": "Desert Eagle",
            "Dual": "Dual Berettas",
            "Galil": "Galil AR",
            "R8": "R8 Revolver",
            "SG": "SG 553",
            "SSG": "SSG 08",
            "Zeus": "Zeus x27"
        }

        # If this weapon needs fixing, reconstruct the correct name
        if weapon in weapon_fixes:
            # Get the correct weapon name
            correct_weapon = weapon_fixes[weapon]

            # Extract the actual skin name by removing the weapon part prefix
            if weapon == "Desert" and skin_name.startswith("Eagle "):
                actual_skin_name = skin_name[6:]  # Remove "Eagle "
            elif weapon == "Dual" and skin_name.startswith("Berettas "):
                actual_skin_name = skin_name[9:]  # Remove "Berettas "
            elif weapon == "Galil" and skin_name.startswith("AR "):
                actual_skin_name = skin_name[3:]  # Remove "AR "
            elif weapon == "R8" and skin_name.startswith("Revolver "):
                actual_skin_name = skin_name[9:]  # Remove "Revolver "
            elif weapon == "SG" and skin_name.startswith("553 "):
                actual_skin_name = skin_name[4:]  # Remove "553 "
            elif weapon == "SSG" and skin_name.startswith("08 "):
                actual_skin_name = skin_name[3:]  # Remove "08 "
            elif weapon == "Zeus" and skin_name.startswith("x27 "):
                actual_skin_name = skin_name[4:]  # Remove "x27 "
            else:
                # Fallback: use the original skin name if prefix doesn't match
                actual_skin_name = skin_name

            # Create the market hash name with corrected weapon name
            market_name = f"{prefix}{correct_weapon} | {actual_skin_name} ({wear})"
        else:
            # For correctly formatted weapons, use the original logic
            market_name = f"{prefix}{weapon} | {skin_name} ({wear})"

        return market_name

    async def process_variants_concurrently(self, skin: Dict, variants: List[Dict], skin_index: int, total_skins: int) -> None:
        """Process all variants of a skin concurrently with multiple proxies"""
        skin_name = f"{skin['weapon']} {skin['skin_name']}"
        logger.info(
            f"\n[{skin_index}/{total_skins}] Processing: {skin_name} ({len(variants)})")
        logger.info(f"Processing: {skin_name}")

        # Prepare tasks for concurrent execution
        tasks = []
        for variant in variants:
            task = self.process_single_variant(skin, variant, skin_name)
            tasks.append(task)

        # Execute all variants concurrently with proxy rotation
        completed_count = 0
        failed_count = 0

        # Get concurrent limit from proxy manager
        max_concurrent = 50  # Default
        if hasattr(proxy_manager, 'max_concurrent_requests'):
            max_concurrent = proxy_manager.max_concurrent_requests

        # Process in batches to control concurrency
        for i in range(0, len(tasks), max_concurrent):
            batch = tasks[i:i + max_concurrent]
            logger.info(
                f"  📦 Processing batch {i//max_concurrent + 1} with {len(batch)} variants using {len(batch)} proxies")

            try:
                # Execute batch concurrently
                results = await asyncio.gather(*batch, return_exceptions=True)

                # Process results
                for j, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.error(f"  ❌ Variant {i+j+1} failed: {result}")
                        failed_count += 1
                    elif result:
                        logger.info(
                            f"  ✅ Variant {i+j+1} completed successfully")
                        completed_count += 1
                    else:
                        logger.warning(
                            f"  ⚠️ Variant {i+j+1} completed with no result")
                        failed_count += 1

            except Exception as e:
                logger.error(f"  ❌ Batch failed: {e}")
                failed_count += len(batch)

        # Update stats
        self.stats['processed_variants'] += len(variants)
        self.stats['successful_requests'] += completed_count
        self.stats['failed_requests'] += failed_count

        logger.info(
            f"Completed {skin_name}: {completed_count}/{len(variants)} prices collected")

    async def process_single_variant(self, skin: Dict, variant: Dict, skin_name: str) -> bool:
        """Process a single variant with detailed logging"""
        try:
            # Check if missing_only mode and variant already has price
            if self.missing_only:
                normal_has_price = variant.get('prices', {}).get(
                    'normal', {}).get('usd', 0) > 0
                stattrak_has_price = variant.get('prices', {}).get(
                    'stattrak', {}).get('usd', 0) > 0

                # Skip if already has required prices
                if self.ignore_stattrak and normal_has_price:
                    return True
                elif not self.ignore_stattrak and normal_has_price and stattrak_has_price:
                    return True

            # Create market hash names for both normal and StatTrak
            variants_to_process = []

            # Normal variant (if needed)
            if not self.missing_only or variant.get('prices', {}).get('normal', {}).get('usd', 0) <= 0:
                normal_hash = self.create_market_hash_name(
                    skin, variant, stattrak=False)
                variants_to_process.append((normal_hash, False))

            # StatTrak variant (if not ignoring and needed)
            if not self.ignore_stattrak:
                if not self.missing_only or variant.get('prices', {}).get('stattrak', {}).get('usd', 0) <= 0:
                    stattrak_hash = self.create_market_hash_name(
                        skin, variant, stattrak=True)
                    variants_to_process.append((stattrak_hash, True))

            success_count = 0
            for market_hash_name, is_stattrak in variants_to_process:
                try:
                    # Get price with proxy rotation (USD currency)
                    price_data, wait_time = await self.steam_client.get_item_price(market_hash_name, currency=1)

                    if price_data:
                        # Ensure prices structure exists
                        if 'prices' not in variant:
                            variant['prices'] = {}

                        key = 'stattrak' if is_stattrak else 'normal'
                        if key not in variant['prices']:
                            variant['prices'][key] = {}

                        # Store price data
                        variant['prices'][key].update(price_data)
                        success_count += 1

                        # Log with proxy info
                        current_proxy = proxy_manager.get_current_proxy()

                        proxy_info = f" via {current_proxy.host}:{current_proxy.port}" if current_proxy else ""
                        price_str = price_data.get('lowest_price', 'N/A')
                        # Ensure USD display (Steam API should return USD with currency=1)
                        logger.info(
                            f"    💰 {key.capitalize()}: {price_str} USD{proxy_info}")

                        # Save immediately after successful price collection
                        self.save_database()

                    # Log API call for rate testing
                    self.log_api_call(
                        market_hash_name, 200 if price_data else 404, bool(price_data), wait_time)

                except Exception as e:
                    logger.error(
                        f"    ❌ Failed to get {('StatTrak' if is_stattrak else 'Normal')} price: {e}")
                    self.log_api_call(market_hash_name, 500, False, 0)

            return success_count > 0

        except Exception as e:
            logger.error(f"    ❌ Error processing variant: {e}")
            return False

    def calculate_total_work(self, skins_with_dates: List[Tuple[Dict, datetime]]) -> Tuple[int, int]:
        """Calculate total skins and variants to process"""
        total_skins = len(skins_with_dates)
        total_variants = 0

        for skin, _ in skins_with_dates:
            variants = skin.get('variants', [])
            # Each variant has normal price check, optionally stattrak
            multiplier = 1 if self.ignore_stattrak else 2
            total_variants += len(variants) * multiplier

        return total_skins, total_variants

    async def _get_fallback_scraper(self):
        """Get or create optimized fallback scraper instance"""
        if self.fallback_scraper is None:
            logger.info(
                f"🚀 Initializing optimized fallback scraper with {self.fallback_pool_size} drivers")
            self.fallback_scraper = OptimizedCSGODatabaseScraper(
                pool_size=self.fallback_pool_size,
                proxies=self.fallback_proxies,
                headless=True
            )
            await self.fallback_scraper.start()
        return self.fallback_scraper

    async def _cleanup_fallback_scraper(self):
        """Clean up optimized fallback scraper"""
        if self.fallback_scraper:
            try:
                await self.fallback_scraper.stop()
            except Exception as e:
                logger.warning(f"Error cleaning up fallback scraper: {e}")
            finally:
                self.fallback_scraper = None

    async def _try_fallback_price(self, skin: Dict, variant: Dict, stattrak: bool = False) -> Optional[Dict]:
        """
        Try to get price using enhanced fallback scraper

        Args:
            skin: Skin data containing detail_url
            variant: Variant data containing wear condition
            stattrak: Whether this is a StatTrak variant

        Returns:
            Price data dict or None if fallback fails
        """
        detail_url = skin.get('detail_url')
        if not detail_url:
            logger.warning(
                f"No detail_url found for {skin.get('full_name', 'Unknown')}")
            return None

        skin_name = skin.get('full_name', 'Unknown')
        wear_condition = variant.get('wear', 'Unknown')

        try:
            # Get fallback scraper
            scraper = await self._get_fallback_scraper()

            # Try to get price using enhanced fallback
            logger.info(
                f"🔄 Attempting enhanced fallback for {skin_name} ({wear_condition}) {'StatTrak™' if stattrak else 'Normal'}")

            # Get price for this specific wear condition and StatTrak variant
            final_price = await scraper.get_price(detail_url, skin_name, wear_condition, stattrak)

            if final_price and final_price > 0:
                logger.info(
                    f"✅ Enhanced fallback success: {skin_name} ({wear_condition}) {'StatTrak™' if stattrak else 'Normal'} = ${final_price:.2f}")

                # Create price data in same format as Steam API
                return {
                    'usd': final_price,
                    'last_updated': datetime.now().isoformat(),
                    'raw_data': {
                        'success': True,
                        'lowest_price': f"${final_price:.2f}",
                        'source': 'enhanced_fallback_scraper'
                    }
                }
            else:
                logger.info(
                    f"❌ Enhanced fallback: No price available for {skin_name} ({wear_condition}) {'StatTrak™' if stattrak else 'Normal'}")
                return None

        except Exception as e:
            logger.error(
                f"❌ Enhanced fallback error for {skin_name} ({wear_condition}): {e}")
            return None

    async def update_weapon_availability(self, skin: Dict) -> bool:
        """
        Update weapon availability information using enhanced fallback scraper

        Args:
            skin: Skin data containing detail_url and variants

        Returns:
            True if availability was successfully updated, False otherwise
        """
        detail_url = skin.get('detail_url')
        if not detail_url:
            logger.warning(
                f"No detail_url found for {skin.get('full_name', 'Unknown')}")
            return False

        skin_name = skin.get('full_name', 'Unknown')

        try:
            # Get fallback scraper
            scraper = await self._get_fallback_scraper()

            # Get comprehensive weapon information
            logger.info(f"🔍 Analyzing availability for {skin_name}")
            weapon_info = await scraper.get_weapon_info(detail_url, skin_name)

            if not weapon_info:
                logger.warning(f"❌ No weapon info available for {skin_name}")
                return False

            # Extract availability data
            availability = weapon_info.get('availability', {})
            stattrak_availability = weapon_info.get(
                'stattrak_availability', {})
            listings = weapon_info.get('listings', {})

            # Update each variant with availability information
            updated_variants = 0
            current_time = datetime.now().isoformat()

            for variant in skin.get('variants', []):
                wear_condition = variant.get('wear')
                if not wear_condition:
                    continue

                # Update availability flags
                # Default to True for existing data
                old_available = variant.get('available', True)
                old_stattrak_available = variant.get(
                    'stattrak_available', True)

                new_available = availability.get(wear_condition, False)
                new_stattrak_available = stattrak_availability.get(
                    wear_condition, False)

                variant['available'] = new_available
                variant['stattrak_available'] = new_stattrak_available
                variant['availability_verified'] = current_time

                # Update listing information
                wear_key = wear_condition
                stattrak_key = f"StatTrak {wear_condition}"

                variant['has_normal_listings'] = listings.get(wear_key, False)
                variant['has_stattrak_listings'] = listings.get(
                    stattrak_key, False)

                # Log changes
                if old_available != new_available or old_stattrak_available != new_stattrak_available:
                    logger.info(f"📋 Updated {skin_name} - {wear_condition}: "
                                f"Available: {old_available}→{new_available}, "
                                f"StatTrak: {old_stattrak_available}→{new_stattrak_available}")

                updated_variants += 1

            logger.info(
                f"✅ Availability updated for {skin_name}: {updated_variants} variants")
            return True

        except Exception as e:
            logger.error(f"❌ Error updating availability for {skin_name}: {e}")
            return False

    async def collect_price_for_variant(self, skin: Dict, variant: Dict, stattrak: bool = False) -> Optional[Dict]:
        """Collect price for a single skin variant with freshness checking"""
        market_hash_name = self.create_market_hash_name(
            skin, variant, stattrak)

        # Check if price is fresh enough (skip if recently updated)
        if not self.missing_only and self.is_price_fresh(variant, stattrak):
            if self.debug:
                logger.debug(
                    f"Skipping {safe_log_name(market_hash_name)} - price is fresh")
            return None

        try:
            # Apply artificial delay before request
            if self.delay_between_requests > 0:
                await asyncio.sleep(self.delay_between_requests)

            # Record start time for response time tracking
            start_time = datetime.now()

            # Skip Steam API if fallback-only mode is enabled
            if self.fallback_only:
                logger.info(
                    f"🕷️ FALLBACK-ONLY MODE: Skipping Steam API for {safe_log_name(market_hash_name)}")
                price_data = None
                wait_time = 0
            else:
                # Construct the full API endpoint URL for logging
                base_url = self.steam_client.base_url
                params = {
                    "appid": "730",
                    "currency": "1",
                    "market_hash_name": market_hash_name
                }
                query_string = urllib.parse.urlencode(params)
                full_url = f"{base_url}?{query_string}"

                # ALWAYS log API requests and responses (not just in debug mode)
                logger.info(f"🌐 API REQUEST: {full_url}")

                # Get price from Steam Market API (USD) - now returns (data, wait_time)
                price_data, wait_time = await self.steam_client.get_item_price(market_hash_name, currency=1)

            # ALWAYS log API response (not just debug mode) - except in fallback-only mode
            if not self.fallback_only:
                if price_data:
                    logger.info(f"🌐 API RESPONSE: {price_data}")
                else:
                    logger.info("🌐 API RESPONSE: None (network/proxy error)")

            # Additional debug details if debug mode enabled
            if self.debug:
                logger.info(
                    f"🔍 DEBUG - Item: {safe_log_name(market_hash_name)}")
                logger.info(f"🔍 DEBUG - Wait time: {wait_time}")

            # Log special cases to dedicated file
            if price_data and len(price_data) == 1 and "success" in price_data and price_data["success"] is True:
                success_only_logger.info(
                    f"ITEM: {safe_log_name(market_hash_name)}")
                success_only_logger.info(f"URL: {full_url}")
                success_only_logger.info(f"RESPONSE: {price_data}")
                success_only_logger.info(
                    "REASON: Item exists but has no market data")
                success_only_logger.info("-" * 80)

                # Also log to main logger for debug visibility
                logger.warning(
                    "🚨 DEBUG - DETECTED: Only {'success': true} response!")
                logger.warning(f"🔗 DEBUG - Link: {full_url}")
                logger.warning(
                    "🔍 DEBUG - This means item exists but has no market data or is not tradeable")

            # Calculate response time
            response_time = (datetime.now() - start_time).total_seconds()

            if price_data and price_data.get('success'):
                # Log successful API call with wait time
                self.log_api_call(market_hash_name, 200, True,
                                  response_time, wait_time)

                # DEBUG: Show what fields are available (only if debug enabled)
                if self.debug:
                    logger.info(
                        f"🔍 DEBUG - Success=True, Available fields: {list(price_data.keys())}")

                # Parse price strings (e.g., "$123.45" -> 123.45)
                lowest_price = price_data.get('lowest_price', '$0.00')
                median_price = price_data.get('median_price', '$0.00')

                # DEBUG: Show the raw price values (only if debug enabled)
                if self.debug:
                    logger.info(
                        f"🔍 DEBUG - lowest_price: '{lowest_price}', median_price: '{median_price}'")

                # Extract numeric value from price string
                def parse_price(price_str):
                    if not price_str:
                        return 0.0
                    # Remove currency symbols and convert to float
                    price_clean = re.sub(r'[^\d.,]', '', str(price_str))
                    price_clean = price_clean.replace(',', '')
                    try:
                        return float(price_clean)
                    except ValueError:
                        return 0.0

                lowest = parse_price(lowest_price)
                median = parse_price(median_price)

                # DEBUG: Show parsed prices (only if debug enabled)
                if self.debug:
                    logger.info(
                        f"🔍 DEBUG - Parsed lowest: {lowest}, median: {median}")

                # Use lowest price as the main price, fallback to median
                final_price = lowest if lowest > 0 else median

                # DEBUG: Show final decision (only if debug enabled)
                if self.debug:
                    logger.info(f"🔍 DEBUG - Final price: {final_price}")

                logger.debug(
                    f"[OK] {safe_log_name(market_hash_name)}: ${final_price}")

                # Log success to summary logger
                self.summary_logger.log_steam_api_success(response_time)

                return {
                    'usd': final_price,
                    'last_updated': datetime.now().isoformat(),
                    'raw_data': price_data,
                    'success': True,
                    'lowest_price': f"${final_price:.2f}"
                }
            else:
                # DEBUG: Show why it failed
                logger.info(
                    f"🔍 DEBUG - FAILED - price_data exists: {price_data is not None}")
                if price_data:
                    logger.info(
                        f"🔍 DEBUG - FAILED - price_data content: {price_data}")
                    logger.info(
                        f"🔍 DEBUG - FAILED - success field: {price_data.get('success', 'NOT_FOUND')}")
                else:
                    logger.info("🔍 DEBUG - FAILED - price_data is None/empty")

                # Determine the actual failure reason
                if not price_data:
                    # No response data - this is likely a proxy/network failure, NOT rate limit
                    status_code = 500  # Network/proxy error
                    failure_reason = "proxy/network failure"
                    logger.info(
                        f"🔌 Network/proxy failure for {safe_log_name(market_hash_name)} - trying fallback")
                else:
                    # Got response but no price data - could be rate limit or item not available
                    status_code = 404  # Not available
                    failure_reason = "no price data available"
                    logger.info(
                        f"🔄 No price data available for {safe_log_name(market_hash_name)} - trying fallback")

                self.log_api_call(market_hash_name, status_code,
                                  False, response_time, wait_time)

                # Only log rate limit if we actually got a 429 response from the API
                # (Not when proxies fail to connect)

                # Check if this is a case where we should try fallback
                should_try_fallback = False

                # Try fallback if:
                # 1. We got success=True but no price data (item exists but not tradeable)
                # 2. We got no response at all (proxy/network failure)
                # 3. We got response but no price available
                if price_data and price_data.get('success') and not price_data.get('lowest_price'):
                    should_try_fallback = True
                elif not price_data:
                    should_try_fallback = True
                else:
                    should_try_fallback = True

                if should_try_fallback and not self.no_fallback:
                    fallback_result = await self._try_fallback_price(skin, variant, stattrak)
                    if fallback_result:
                        # Log fallback success
                        fallback_response_time = (
                            datetime.now() - start_time).total_seconds()
                        self.summary_logger.log_fallback_success(
                            fallback_response_time)
                        return fallback_result
                    else:
                        # Log fallback failure
                        self.summary_logger.log_fallback_failure()

                # Log Steam API failure
                self.summary_logger.log_steam_api_failure()

                logger.warning(
                    f"[FAIL] No price data for {safe_log_name(market_hash_name)}")
                return None

        except Exception as e:
            # Log exception as failed call
            self.log_api_call(market_hash_name, 500, False, 0)

            # Log network error to summary logger
            self.summary_logger.log_network_error()

            logger.error(
                f"Error collecting price for {safe_log_name(market_hash_name)}: {e}")
            self.stats['failed_requests'] += 1
            return None

    async def process_skin(self, skin: Dict) -> bool:
        """Process all variants of a single skin"""
        skin_name = skin['full_name']
        logger.info(f"Processing: {skin_name}")

        variants = skin.get('variants', [])
        success_count = 0
        expected_total = len(variants) * (1 if self.ignore_stattrak else 2)

        for variant in variants:
            # Check if we should skip this variant (missing_only mode)
            if self.missing_only:
                normal_has_price = variant.get('prices', {}).get(
                    'normal', {}).get('usd', 0) > 0
                stattrak_has_price = variant.get('prices', {}).get(
                    'stattrak', {}).get('usd', 0) > 0

                # Skip if both normal and stattrak already have prices (or if ignoring stattrak and normal has price)
                if self.ignore_stattrak and normal_has_price:
                    continue
                elif not self.ignore_stattrak and normal_has_price and stattrak_has_price:
                    continue

            # Process normal version
            normal_needs_price = True
            if self.missing_only:
                normal_needs_price = variant.get('prices', {}).get(
                    'normal', {}).get('usd', 0) <= 0

            if normal_needs_price:
                normal_price = await self.collect_price_for_variant(skin, variant, stattrak=False)
                if normal_price:
                    variant['prices']['normal'].update(normal_price)
                    success_count += 1
                    # Save immediately after successful price collection to prevent data loss
                    self.save_database()

            self.stats['processed_variants'] += 1

            # Process StatTrak version only if not ignoring
            if not self.ignore_stattrak:
                stattrak_needs_price = True
                if self.missing_only:
                    stattrak_needs_price = variant.get('prices', {}).get(
                        'stattrak', {}).get('usd', 0) <= 0

                if stattrak_needs_price:
                    stattrak_price = await self.collect_price_for_variant(skin, variant, stattrak=True)
                    if stattrak_price:
                        variant['prices']['stattrak'].update(stattrak_price)
                        success_count += 1
                        # Save immediately after successful price collection to prevent data loss
                        self.save_database()

                self.stats['processed_variants'] += 1

        logger.info(
            f"Completed {skin_name}: {success_count}/{expected_total} prices collected")
        return success_count > 0

    def print_progress(self):
        """Print current progress statistics"""
        elapsed_time = datetime.now() - self.stats['start_time']

        print(f"\\n{'='*60}")
        print(f"PROGRESS UPDATE - {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'='*60}")
        print(
            f"Skins processed: {self.stats['processed_skins']:,} / {self.stats['total_skins']:,}")
        print(
            f"Variants processed: {self.stats['processed_variants']:,} / {self.stats['total_variants']:,}")
        print(f"Successful requests: {self.stats['successful_requests']:,}")
        print(f"Failed requests: {self.stats['failed_requests']:,}")
        print(f"Elapsed time: {elapsed_time}")

        if self.stats['processed_variants'] > 0:
            rate = self.stats['processed_variants'] / \
                elapsed_time.total_seconds() * 60
            print(f"Processing rate: {rate:.1f} variants/minute")

            remaining_variants = self.stats['total_variants'] - \
                self.stats['processed_variants']
            if rate > 0:
                eta_minutes = remaining_variants / rate
                eta_time = datetime.now() + timedelta(minutes=eta_minutes)
                print(f"Estimated completion: {eta_time.strftime('%H:%M:%S')}")

        print(f"{'='*60}\\n")

    def build_missing_items_queue(self):
        """Build a queue of all variants that need price updates"""
        missing_tasks = []

        logger.info("🔍 Scanning database for missing prices...")

        for skin in self.skins:
            variants = skin.get('variants', [])

            for variant in variants:
                # Check normal variant
                normal_has_price = variant.get('prices', {}).get(
                    'normal', {}).get('usd', 0) > 0
                if not normal_has_price:
                    # (skin, variant, is_stattrak)
                    missing_tasks.append((skin, variant, False))

                # Check StatTrak variant if not ignoring
                if not self.ignore_stattrak:
                    stattrak_has_price = variant.get('prices', {}).get(
                        'stattrak', {}).get('usd', 0) > 0
                    if not stattrak_has_price:
                        missing_tasks.append((skin, variant, True))

        logger.info(
            f"📋 Found {len(missing_tasks)} missing price entries to process")
        return missing_tasks

    async def collect_all_prices(self, limit: Optional[int] = None, resume: bool = True):
        """Collect prices for all skins starting from newest"""
        logger.info("Starting price collection process")

        # Set collection mode in summary logger
        collection_mode = "missing-only" if self.missing_only else "sequential"
        self.summary_logger.set_collection_mode(collection_mode, resume)

        if self.ignore_stattrak:
            logger.info("StatTrak variants will be ignored")

        # For missing-only mode, use queue-based approach (no checkpointing needed)
        if self.missing_only:
            logger.info(
                "🎯 Missing-only mode: Building queue of items needing price updates")
            missing_tasks = self.build_missing_items_queue()

            if not missing_tasks:
                logger.info(
                    "✅ All items already have prices - nothing to process!")
                return

            # Apply limit to missing tasks if specified
            if limit is not None and limit > 0:
                # Rough estimate: 10 variants per "limit"
                missing_tasks = missing_tasks[:limit * 10]
                logger.info(
                    f"Limited to approximately first {limit} skins worth of missing items")

            self.stats['total_variants'] = len(missing_tasks)
            self.stats['total_skins'] = len(
                set(task[0]['id'] for task in missing_tasks))
            self.stats['start_time'] = datetime.now()

            logger.info(
                f"📊 Processing {len(missing_tasks)} missing price entries from {self.stats['total_skins']} skins")

            await self._process_missing_items_queue(missing_tasks)
            return

        # Regular mode: process skins in order with checkpointing
        skins_with_dates = self.sort_skins_by_date()
        self.stats['total_skins'], self.stats['total_variants'] = self.calculate_total_work(
            skins_with_dates)
        self.stats['start_time'] = datetime.now()

        logger.info(
            f"Total work: {self.stats['total_skins']} skins, {self.stats['total_variants']} price requests")

        # Apply limit if specified (limit=0 means no limit)
        if limit is not None and limit > 0:
            skins_with_dates = skins_with_dates[:limit]
            logger.info(f"Limited to first {limit} skins for testing")
        elif limit == 0:
            logger.info("No limit applied - processing all skins")

        # Resume from checkpoint if requested
        start_index = 0
        if resume and self.checkpoint['last_processed_skin_id']:
            for i, (skin, _) in enumerate(skins_with_dates):
                if skin['id'] == self.checkpoint['last_processed_skin_id']:
                    start_index = i + 1
                    break
            logger.info(f"Resuming from skin index {start_index}")

        await self._process_skins_in_order(skins_with_dates, start_index, limit, resume)

    async def _process_missing_items_queue(self, missing_tasks):
        """Process missing items using pure queue-based approach"""
        async with self.steam_client:
            max_concurrent = 50
            if hasattr(proxy_manager, 'max_concurrent_requests'):
                max_concurrent = proxy_manager.max_concurrent_requests

            # Process missing items in batches
            for batch_start in range(0, len(missing_tasks), max_concurrent):
                if self.shutdown_requested:
                    logger.info("Shutdown requested - stopping collection...")
                    break

                batch_end = min(batch_start + max_concurrent,
                                len(missing_tasks))
                batch = missing_tasks[batch_start:batch_end]

                logger.info(
                    f"🔥 Processing batch {batch_start//max_concurrent + 1}: {len(batch)} missing items concurrently")

                try:
                    # Create all tasks for this batch
                    tasks = []
                    task_info = []

                    for skin, variant, is_stattrak in batch:
                        task = self.collect_price_for_variant(
                            skin, variant, stattrak=is_stattrak)
                        tasks.append(task)
                        task_info.append((skin, variant, is_stattrak))

                    # Execute all tasks concurrently
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    # Process results
                    success_count = 0
                    failed_count = 0

                    for result, (skin, variant, is_stattrak) in zip(results, task_info):
                        if isinstance(result, Exception):
                            failed_count += 1
                        elif result:
                            # Update the variant with the price data
                            if is_stattrak:
                                variant['prices']['stattrak'].update(result)
                            else:
                                variant['prices']['normal'].update(result)
                            success_count += 1
                        else:
                            failed_count += 1

                    # Update stats
                    self.stats['successful_requests'] += success_count
                    self.stats['failed_requests'] += failed_count
                    self.stats['processed_variants'] += len(batch)

                    # Save database after each batch (no checkpoint needed for missing-only)
                    self.save_database()

                    logger.info(
                        f"  ✅ Batch completed: {success_count} successful, {failed_count} failed")

                    # Print progress every batch
                    self.print_progress()

                except KeyboardInterrupt:
                    logger.info(
                        "Process interrupted by user - saving current progress...")
                    self.save_database()
                    logger.info("Progress saved. Safe to exit.")
                    break
                except Exception as e:
                    logger.error(f"Error processing batch: {e}")

        logger.info("🎉 Missing-only price collection completed!")

    async def _process_skins_in_order(self, skins_with_dates, start_index, limit=None, resume=True):
        """Collect prices for all skins starting from newest"""
        logger.info("Starting price collection process")

        if self.ignore_stattrak:
            logger.info("StatTrak variants will be ignored")

        # Sort skins by date
        skins_with_dates = self.sort_skins_by_date()

        # Calculate total work
        self.stats['total_skins'], self.stats['total_variants'] = self.calculate_total_work(
            skins_with_dates)
        self.stats['start_time'] = datetime.now()

        logger.info(
            f"Total work: {self.stats['total_skins']} skins, {self.stats['total_variants']} price requests")

        # Apply limit if specified (limit=0 means no limit)
        if limit is not None and limit > 0:
            skins_with_dates = skins_with_dates[:limit]
            logger.info(f"Limited to first {limit} skins for testing")
        elif limit == 0:
            logger.info("No limit applied - processing all skins")

        # Resume from checkpoint if requested
        start_index = 0
        if resume and self.checkpoint['last_processed_skin_id']:
            for i, (skin, _) in enumerate(skins_with_dates):
                if skin['id'] == self.checkpoint['last_processed_skin_id']:
                    start_index = i + 1
                    break
            logger.info(f"Resuming from skin index {start_index}")

        # Process skins with true concurrent processing across multiple skins
        async with self.steam_client:
            # Get concurrent limit from proxy manager
            max_concurrent = 50  # Default
            if hasattr(proxy_manager, 'max_concurrent_requests'):
                max_concurrent = proxy_manager.max_concurrent_requests

            # Calculate how many skins to process in each batch (aim for ~100 variants per batch)
            avg_variants_per_skin = 5  # Most skins have 5 variants
            # ~20 skins per batch for 100 concurrent
            skins_per_batch = max(1, max_concurrent // avg_variants_per_skin)

            remaining_skins = skins_with_dates[start_index:]

            for batch_start in range(0, len(remaining_skins), skins_per_batch):
                # Check for shutdown request
                if self.shutdown_requested:
                    logger.info("Shutdown requested - stopping collection...")
                    break

                batch_end = min(batch_start + skins_per_batch,
                                len(remaining_skins))
                skin_batch = remaining_skins[batch_start:batch_end]

                logger.info(
                    f"🔥 Processing batch of {len(skin_batch)} skins concurrently (max {max_concurrent} variants)")

                try:
                    # Create tasks for all variants across multiple skins
                    all_tasks = []
                    skin_indices = []

                    for j, (skin, intro_date) in enumerate(skin_batch):
                        actual_index = start_index + batch_start + j
                        variants = skin.get('variants', [])

                        # Update availability information if requested
                        if self.update_availability:
                            try:
                                logger.info(
                                    f"🔍 Updating availability for {skin['full_name']}")
                                await self.update_weapon_availability(skin)
                            except Exception as e:
                                logger.error(
                                    f"Failed to update availability for {skin['full_name']}: {e}")

                        # Create tasks for this skin's variants
                        for variant_idx, variant in enumerate(variants):
                            # Create tasks based on missing_only logic
                            if self.missing_only:
                                normal_has_price = variant.get('prices', {}).get(
                                    'normal', {}).get('usd', 0) > 0
                                stattrak_has_price = variant.get('prices', {}).get(
                                    'stattrak', {}).get('usd', 0) > 0

                                # Skip if already has required prices
                                if self.ignore_stattrak and normal_has_price:
                                    continue
                                elif not self.ignore_stattrak and normal_has_price and stattrak_has_price:
                                    continue

                            # Add normal variant task if needed
                            if not self.missing_only or variant.get('prices', {}).get('normal', {}).get('usd', 0) <= 0:
                                task = self.collect_price_for_variant(
                                    skin, variant, stattrak=False)
                                all_tasks.append(
                                    (task, skin, variant, False, actual_index))

                            # Add StatTrak variant task if needed
                            if not self.ignore_stattrak:
                                if not self.missing_only or variant.get('prices', {}).get('stattrak', {}).get('usd', 0) <= 0:
                                    task = self.collect_price_for_variant(
                                        skin, variant, stattrak=True)
                                    all_tasks.append(
                                        (task, skin, variant, True, actual_index))

                    if not all_tasks:
                        logger.info(
                            f"  ⏭️  Skipping batch - all items already have prices")
                        continue

                    logger.info(
                        f"  📦 Executing {len(all_tasks)} price requests concurrently")

                    # Execute all tasks concurrently with proper batching
                    tasks_only = [task_info[0] for task_info in all_tasks]
                    results = await asyncio.gather(*tasks_only, return_exceptions=True)

                    # Process results and update database
                    success_count = 0
                    failed_count = 0
                    processed_skins = set()

                    for i, (result, (_, skin, variant, is_stattrak, skin_index)) in enumerate(zip(results, all_tasks)):
                        if isinstance(result, Exception):
                            logger.error(f"  ❌ Task {i+1} failed: {result}")
                            failed_count += 1
                        elif result:
                            # Update the variant with the price data
                            if is_stattrak:
                                variant['prices']['stattrak'].update(result)
                            else:
                                variant['prices']['normal'].update(result)
                            success_count += 1
                            processed_skins.add(skin_index)
                        else:
                            failed_count += 1

                    # Update stats and save progress
                    self.stats['successful_requests'] += success_count
                    self.stats['failed_requests'] += failed_count
                    self.stats['processed_variants'] += len(all_tasks)
                    self.stats['processed_skins'] += len(skin_batch)

                    # Update summary logger stats
                    self.summary_logger.stats.total_skins_processed = self.stats['processed_skins']
                    self.summary_logger.stats.total_variants_processed = self.stats[
                        'processed_variants']

                    # Update checkpoint to last skin in batch
                    if skin_batch:
                        last_skin = skin_batch[-1][0]
                        self.checkpoint['processed_skins'] = start_index + batch_end
                        self.checkpoint['last_processed_skin_id'] = last_skin['id']

                    # Save progress after each batch
                    self.save_checkpoint()
                    self.save_database()

                    logger.info(
                        f"  ✅ Batch completed: {success_count} successful, {failed_count} failed")

                    # Print progress every batch
                    self.print_progress()

                except KeyboardInterrupt:
                    logger.info(
                        "Process interrupted by user - saving current progress...")
                    self.save_checkpoint()
                    self.save_database()
                    logger.info("Progress saved. Safe to exit.")
                    break
                except Exception as e:
                    logger.error(f"Error processing batch: {e}")
                    # Continue to next batch even if this one fails
                    continue

        # Check if shutdown was requested and perform graceful shutdown
        if self.shutdown_requested:
            self.graceful_shutdown()

        # Final save
        self.save_checkpoint()
        self.save_database()

        logger.info("Price collection completed!")
        self.print_progress()


async def main():
    """Main function to run price collection"""
    import argparse
    import signal

    parser = argparse.ArgumentParser(
        description='Collect Steam Market prices for CS2 skins')
    parser.add_argument('--limit', type=int,
                        help='Limit number of skins to process (0 = no limit, for testing use small numbers)')
    parser.add_argument('--no-resume', action='store_true',
                        help='Start from beginning instead of resuming')
    parser.add_argument('--ignore-stattrak', action='store_true',
                        help='Skip StatTrak variants to speed up collection')
    parser.add_argument('--missing-only', action='store_true',
                        help='Only process skins/variants that don\'t have prices yet')
    parser.add_argument('--debug', action='store_true',
                        help='Enable detailed debug output including API endpoints')
    parser.add_argument('--noproxy', action='store_true',
                        help='Disable proxy usage (use direct connection to Steam API)')
    parser.add_argument('--no-fallback', action='store_true',
                        help='Disable fallback scraping (Steam API only)')
    parser.add_argument('--fallback-only', action='store_true',
                        help='Skip Steam API and use only fallback scraping method')
    parser.add_argument('--update-availability', action='store_true',
                        help='Update weapon availability information (detect which wear conditions and StatTrak variants actually exist)')

    args = parser.parse_args()

    # Validate flag combinations
    if args.no_fallback and args.fallback_only:
        parser.error(
            "--no-fallback and --fallback-only cannot be used together")

    collector = PriceCollector(
        ignore_stattrak=args.ignore_stattrak,
        missing_only=args.missing_only,
        debug=args.debug,
        noproxy=args.noproxy,
        no_fallback=args.no_fallback,
        fallback_only=args.fallback_only,
        update_availability=args.update_availability
    )

    # Set up graceful shutdown handler
    def signal_handler(signum, frame):
        logger.info("🛑 Received shutdown signal. Generating summary report...")
        # Set interruption flag and save summary
        collector.summary_logger.set_interruption(
            interrupted_by_user=True, graceful=True)
        collector.summary_logger.save_summary()
        logger.info(SUMMARY_REPORT_MESSAGE)
        exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        await collector.collect_all_prices(
            limit=args.limit,
            resume=not args.no_resume
        )

        # Generate final summary report on normal completion
        collector.summary_logger.save_summary()
        logger.info(
            "✅ Collection completed. Summary report saved to logs/summary.txt")

    except KeyboardInterrupt:
        logger.info(
            "🛑 Collection interrupted by user. Generating summary report...")
        collector.summary_logger.set_interruption(
            interrupted_by_user=True, graceful=True)
        collector.summary_logger.save_summary()
        logger.info(SUMMARY_REPORT_MESSAGE)
    except Exception as e:
        logger.error(f"❌ Unexpected error during collection: {e}")
        collector.summary_logger.set_interruption(
            interrupted_by_user=False, graceful=False)
        collector.summary_logger.save_summary()
        logger.info(SUMMARY_REPORT_MESSAGE)
        raise


if __name__ == "__main__":
    asyncio.run(main())
