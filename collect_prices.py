"""
Price Collection System for CS2 Skins
Collects Steam Market prices for all skins starting from newest to oldest
Respects Steam API rate limits (18 calls/minute) and provides progress tracking
"""

from steam_api import SteamMarketAPIClient
from proxy_manager import proxy_manager
import json
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import os
import re
import signal
import sys
import urllib.parse

# Set up main logger
logger = logging.getLogger(__name__)

# Set up dedicated logger for success-only responses
success_only_logger = logging.getLogger('success_only')
# Check if handler already exists to avoid duplicate handlers
if not success_only_logger.handlers:
    success_only_handler = logging.FileHandler(
        'success_only_responses.log', encoding='utf-8')
    success_only_formatter = logging.Formatter('%(asctime)s | %(message)s')
    success_only_handler.setFormatter(success_only_formatter)
    success_only_logger.addHandler(success_only_handler)
    success_only_logger.setLevel(logging.INFO)
    success_only_logger.propagate = False  # Don't send to parent loggers


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


# Set up logging with UTF-8 encoding
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('price_collection.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def safe_log_name(name: str) -> str:
    """Convert market hash name to logging-safe ASCII version"""
    return name.replace("™", "(TM)").encode('ascii', 'replace').decode('ascii')


class PriceCollector:
    """Collects Steam Market prices for CS2 skins with rate limiting and progress tracking"""

    def __init__(self, database_path: str = "data/skins_database.json", checkpoint_path: str = "price_collection_checkpoint.json", ignore_stattrak: bool = False, missing_only: bool = False, debug: bool = False, noproxy: bool = False):
        self.database_path = database_path
        self.checkpoint_path = checkpoint_path
        self.ignore_stattrak = ignore_stattrak
        self.missing_only = missing_only
        self.debug = debug
        self.noproxy = noproxy
        
        # Disable proxies if --noproxy flag is set
        if self.noproxy:
            proxy_manager.use_proxies = False
            logger.info("Proxies disabled via --noproxy flag")
        
        self.steam_client = SteamMarketAPIClient()
        self.shutdown_requested = False

        # API rate tracking for testing
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
        logger.info("All data saved. Shutdown complete.")

        # Run cleanup to remove invalid variants
        self.run_cleanup()

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

        logger.debug("Checkpoint saved")

    def save_database(self):
        """Save the updated database"""
        self.database['data_status']['last_price_update'] = datetime.now(
        ).isoformat()

        with open(self.database_path, 'w', encoding='utf-8') as f:
            json.dump(self.database, f, indent=2, ensure_ascii=False)

        logger.info("Database saved with updated prices")

    def run_cleanup(self):
        """Run the cleanup script to remove invalid variants"""
        try:
            from cleanup_invalid_variants import VariantCleaner

            logger.info("\n" + "=" * 80)
            logger.info("RUNNING AUTOMATIC CLEANUP")
            logger.info("Removing variants with no market data...")
            logger.info("=" * 80)

            cleaner = VariantCleaner(database_path=self.database_path)
            cleaner.run(dry_run=False)

            # Reload the database after cleanup
            self.load_database()

            logger.info("Cleanup completed successfully!\n")
        except Exception as e:
            logger.error(f"Failed to run cleanup: {e}")
            logger.info(
                "You can manually run: python cleanup_invalid_variants.py")

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

    async def collect_price_for_variant(self, skin: Dict, variant: Dict, stattrak: bool = False) -> Optional[Dict]:
        """Collect price for a single skin variant"""
        market_hash_name = self.create_market_hash_name(
            skin, variant, stattrak)

        try:
            # Record start time for response time tracking
            start_time = datetime.now()

            # Get price from Steam Market API (USD) - now returns (data, wait_time)
            price_data, wait_time = await self.steam_client.get_item_price(market_hash_name, currency=1)

            # DEBUG: Dump the raw response for troubleshooting (only if debug enabled)
            if self.debug:
                # Construct the full API endpoint URL for debugging
                base_url = self.steam_client.base_url
                params = {
                    "appid": "730",
                    "currency": "1",
                    "market_hash_name": market_hash_name
                }
                # Build properly encoded query string
                query_string = urllib.parse.urlencode(params)
                full_url = f"{base_url}?{query_string}"

                logger.info(
                    f"🔍 DEBUG - Item: {safe_log_name(market_hash_name)}")
                logger.info(f"🔍 DEBUG - API Endpoint: {full_url}")
                logger.info(f"🔍 DEBUG - Raw API Response: {price_data}")
                logger.info(f"🔍 DEBUG - Wait time: {wait_time}")

                # Check for the specific case where we only get {"success": true}
                if price_data and len(price_data) == 1 and "success" in price_data and price_data["success"] is True:
                    # Log to dedicated success-only log file
                    success_only_logger.info(
                        f"COLLECT_PRICES - ITEM: {safe_log_name(market_hash_name)}")
                    success_only_logger.info(
                        f"COLLECT_PRICES - URL: {full_url}")
                    success_only_logger.info(
                        f"COLLECT_PRICES - RESPONSE: {price_data}")
                    success_only_logger.info(
                        "COLLECT_PRICES - REASON: Item exists but has no market data or is not tradeable")
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

                self.stats['successful_requests'] += 1

                return {
                    'usd': final_price,
                    'last_updated': datetime.now().isoformat(),
                    'raw_data': price_data
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

                # Log failed API call (could be rate limit or other error)
                status_code = 429 if not price_data else 404
                self.log_api_call(market_hash_name,
                                  status_code, False, response_time, wait_time)

                logger.warning(
                    f"[FAIL] No price data for {safe_log_name(market_hash_name)}")
                self.stats['failed_requests'] += 1
                return None

        except Exception as e:
            # Log exception as failed call
            self.log_api_call(market_hash_name, 500, False, 0)

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
                    # Run cleanup before exit
                    self.run_cleanup()
                    # Run cleanup before exit
                    self.run_cleanup()
                    break
                except Exception as e:
                    logger.error(f"Error processing batch: {e}")

        logger.info("🎉 Missing-only price collection completed!")

        # Run cleanup to remove invalid variants
        self.run_cleanup()

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

        # Run cleanup to remove invalid variants
        self.run_cleanup()


async def main():
    """Main function to run price collection"""
    import argparse

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

    args = parser.parse_args()

    collector = PriceCollector(
        ignore_stattrak=args.ignore_stattrak, missing_only=args.missing_only, debug=args.debug, noproxy=args.noproxy)
    await collector.collect_all_prices(
        limit=args.limit,
        resume=not args.no_resume
    )


if __name__ == "__main__":
    asyncio.run(main())
