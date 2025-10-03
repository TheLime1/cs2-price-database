"""
Price Collection System for CS2 Skins
Collects Steam Market prices for all skins starting from newest to oldest
Respects Steam API rate limits (18 calls/minute) and provides progress tracking
"""

from steam_api import SteamMarketAPIClient
import json
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import os
import re


def parse_date(date_str: str) -> datetime:
    """Parse a date string into a datetime object"""
    if date_str == 'Unknown' or not date_str:
        return datetime.min

    try:
        # Try different date formats
        formats = [
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


# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('price_collection.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class PriceCollector:
    """Collects Steam Market prices for CS2 skins with rate limiting and progress tracking"""

    def __init__(self, database_path: str = "data/skins_database.json", checkpoint_path: str = "price_collection_checkpoint.json", ignore_stattrak: bool = False):
        self.database_path = database_path
        self.checkpoint_path = checkpoint_path
        self.ignore_stattrak = ignore_stattrak
        self.steam_client = SteamMarketAPIClient()

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

        # Create the market hash name
        market_name = f"{prefix}{weapon} | {skin_name} ({wear})"

        return market_name

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
        try:
            market_hash_name = self.create_market_hash_name(
                skin, variant, stattrak)

            # Get price from Steam Market API
            # USD
            price_data = await self.steam_client.get_item_price(market_hash_name, currency=1)

            if price_data and price_data.get('success'):
                # Parse price strings (e.g., "$123.45" -> 123.45)
                lowest_price = price_data.get('lowest_price', '$0.00')
                median_price = price_data.get('median_price', '$0.00')

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

                # Use lowest price as the main price, fallback to median
                final_price = lowest if lowest > 0 else median

                logger.debug(f"✓ {market_hash_name}: ${final_price}")

                self.stats['successful_requests'] += 1

                return {
                    'usd': final_price,
                    'last_updated': datetime.now().isoformat(),
                    'raw_data': price_data
                }
            else:
                logger.warning(f"✗ No price data for {market_hash_name}")
                self.stats['failed_requests'] += 1
                return None

        except Exception as e:
            logger.error(f"Error collecting price for {market_hash_name}: {e}")
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
            # Process normal version
            normal_price = await self.collect_price_for_variant(skin, variant, stattrak=False)
            if normal_price:
                variant['prices']['normal'].update(normal_price)
                success_count += 1

            self.stats['processed_variants'] += 1

            # Shorter delay between requests for better rate utilization
            await asyncio.sleep(0.2)

            # Process StatTrak version only if not ignoring
            if not self.ignore_stattrak:
                stattrak_price = await self.collect_price_for_variant(skin, variant, stattrak=True)
                if stattrak_price:
                    variant['prices']['stattrak'].update(stattrak_price)
                    success_count += 1

                self.stats['processed_variants'] += 1
                await asyncio.sleep(0.2)

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

    async def collect_all_prices(self, limit: Optional[int] = None, resume: bool = True):
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

        # Process skins
        async with self.steam_client:
            for i, (skin, intro_date) in enumerate(skins_with_dates[start_index:], start_index):
                try:
                    logger.info(
                        "\\n[%d/%d] Processing: %s (%d)", i+1, len(skins_with_dates), skin['full_name'], intro_date.year)

                    await self.process_skin(skin)

                    self.stats['processed_skins'] += 1
                    self.checkpoint['processed_skins'] = self.stats['processed_skins']
                    self.checkpoint['last_processed_skin_id'] = skin['id']

                    # Save progress every 5 skins
                    if (i + 1) % 5 == 0:
                        self.save_checkpoint()
                        self.save_database()
                        self.print_progress()

                    # Shorter delay between skins for better rate utilization
                    await asyncio.sleep(1.0)

                except KeyboardInterrupt:
                    logger.info("Process interrupted by user")
                    break
                except Exception as e:
                    logger.error(
                        f"Error processing skin {skin['full_name']}: {e}")
                    continue

        # Final save
        self.save_checkpoint()
        self.save_database()

        logger.info("Price collection completed!")
        self.print_progress()


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

    args = parser.parse_args()

    collector = PriceCollector(ignore_stattrak=args.ignore_stattrak)
    await collector.collect_all_prices(
        limit=args.limit,
        resume=not args.no_resume
    )


if __name__ == "__main__":
    asyncio.run(main())
