"""
CS2 Price Collection System V2.0 🚀
High-Performance Worker Stealing Architecture

✨ V2.0 FEATURES:
• 🚀 Worker stealing architecture with proxy and WebDriver workers
• 🔄 Smart priority queue system for optimal resource utilization  
• 📊 Proper skin-based limits (--limit 2 = 2 skins, not 20 variants)
• ⚡ Intelligent fallback with WebDriver scraping for failed items
• 💾 Advanced checkpointing and graceful shutdown handling
• 🎯 Dynamic worker management and health monitoring

💡 USAGE:
High-speed operation with limit:
  python collect_prices.py --missing-only --limit 5

Process all skins with full V2.0 power:
  python collect_prices.py

See --help for all options and configuration details.

🔧 V2.0 ARCHITECTURE:
- Worker stealing system with proxy and WebDriver workers
- Priority-based task queues for optimal throughput
- Dynamic worker scaling based on system resources
- Real-time health monitoring and proxy rotation
- Enhanced performance through concurrent processing

🌐 DATA SOURCES:
- Headers: https://raw.githubusercontent.com/TheLime1/Validity/refs/heads/main/data/headers.json
- Proxies: https://raw.githubusercontent.com/TheLime1/Validity/refs/heads/main/data/http.txt
"""

from high_speed_scraper import HighSpeedScraper, SkinItem
from summary_logger import get_summary_logger
import json
import asyncio
import argparse
import logging
import time
import signal
import os
from datetime import datetime
from typing import Dict, List, Optional, Any

# Configure logging to handle Unicode properly
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/price_collection.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


class V2PriceCollector:
    """
    CS2 Price Collection System V2.0

    High-performance worker stealing architecture for maximum throughput.
    Uses the HighSpeedScraper with intelligent task distribution.
    """

    def __init__(self):
        self.scraper = HighSpeedScraper()
        self.stats = {
            'start_time': None,
            'end_time': None,
            'skins_processed': 0,
            'variants_processed': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'total_skins': 0
        }
        self.database_path = "data/skins_database.json"
        self.checkpoint_path = "price_collection_checkpoint.json"

        # Environment URLs for data sources
        self.headers_url = os.getenv(
            'HEADERS_SOURCE_URL',
            'https://raw.githubusercontent.com/TheLime1/Validity/refs/heads/main/data/headers.json'
        )
        self.proxy_url = os.getenv(
            'PROXY_GITHUB_URL',
            'https://raw.githubusercontent.com/TheLime1/Validity/refs/heads/main/data/http.txt'
        )

    async def initialize(self):
        """Initialize the V2.0 scraping system"""
        print("🚀" + "="*80)
        print("🚀 CS2 PRICE COLLECTION SYSTEM V2.0")
        print("🚀 High-performance worker stealing architecture")
        print("🚀" + "="*80)
        print(f"🌐 Headers Source: {self.headers_url}")
        print(f"🌐 Proxy Source: {self.proxy_url}")
        print("🚀" + "="*80)

        await self.scraper.initialize()

    def load_database(self) -> Dict:
        """Load the skins database"""
        logger.info(f"Loading database from {self.database_path}")

        try:
            with open(self.database_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            skins_count = len(data.get('skins', []))
            logger.info(f"Loaded {skins_count} skins from database")
            return data

        except Exception as e:
            logger.error(f"Error loading database: {e}")
            raise

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

        return {'processed_skins': 0, 'processed_skin_ids': []}

    def save_checkpoint(self, processed_skins: int, processed_skin_ids: List[str]):
        """Save checkpoint data"""
        checkpoint = {
            'processed_skins': processed_skins,
            'processed_skin_ids': processed_skin_ids,
            'timestamp': datetime.now().isoformat()
        }

        try:
            with open(self.checkpoint_path, 'w', encoding='utf-8') as f:
                json.dump(checkpoint, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save checkpoint: {e}")

    def needs_price_update(self, variant: Dict, update_interval_hours: int = 24) -> bool:
        """Check if a variant needs a price update"""
        price_data = variant.get('price', {})

        if not price_data:
            return True

        last_updated = price_data.get('last_updated')
        if not last_updated:
            return True

        try:
            last_update_time = datetime.fromisoformat(
                last_updated.replace('Z', '+00:00'))
            time_diff = datetime.now() - last_update_time.replace(tzinfo=None)
            return time_diff.total_seconds() > (update_interval_hours * 3600)
        except Exception:
            return True

    def filter_missing_items(self, data: Dict, limit: Optional[int] = None) -> List[SkinItem]:
        """Filter items that need price updates and convert to SkinItem objects"""
        logger.info("Scanning database for missing prices...")

        missing_items = []
        processed_skins = 0

        for skin_data in data.get('skins', []):
            if limit and processed_skins >= limit:
                break

            # Check if any variant is missing price data
            has_missing = False
            missing_variants = []

            for variant in skin_data.get('variants', []):
                if self.needs_price_update(variant):
                    has_missing = True
                    missing_variants.append(variant)

                # Check StatTrak version
                stattrak_price = variant.get('stattrak_price', {})
                if not stattrak_price or self.needs_price_update({'price': stattrak_price}):
                    has_missing = True
                    if variant not in missing_variants:
                        missing_variants.append(variant)

            if has_missing:
                # Create SkinItem with only missing variants
                item = SkinItem(
                    id=skin_data['id'],
                    weapon=skin_data['weapon'],
                    skin_name=skin_data['skin_name'],
                    full_name=skin_data['full_name'],
                    detail_url=skin_data['detail_url'],
                    variants=missing_variants  # Only include variants that need updates
                )
                missing_items.append(item)
                processed_skins += 1

        total_variants = sum(len(item.variants) for item in missing_items)
        logger.info(f"Found {total_variants} missing price entries to process")

        if limit:
            logger.info(
                f"Limited to first {limit} skins ({total_variants} total variants)")

        logger.info(
            f"Processing {total_variants} missing price entries from {len(missing_items)} skins")

        return missing_items

    async def collect_prices(self, missing_only: bool = False, limit: Optional[int] = None, resume: bool = True):
        """Main collection method using V2.0 worker stealing architecture"""

        self.stats['start_time'] = datetime.now()

        # Load database
        data = self.load_database()

        # Load checkpoint if resuming
        if resume:
            checkpoint = self.load_checkpoint()

        if missing_only:
            logger.info(
                "Missing-only mode: Building queue of items needing price updates")

            # Filter and load only missing items
            missing_items = self.filter_missing_items(data, limit)

            if not missing_items:
                logger.info(
                    "No missing prices found - database is up to date!")
                return

            # Load missing items into the scraper
            for item in missing_items:
                self.scraper.main_queue.put(item)

        else:
            # Load all items from database for full processing
            await self.scraper.load_items_from_database(self.database_path)

            if limit:
                # If limit is specified, we need to adjust the queue
                logger.info(f"Limiting processing to {limit} skins")

                # Drain the queue and keep only the first 'limit' items
                limited_items = []
                for _ in range(min(limit, self.scraper.main_queue.qsize())):
                    if not self.scraper.main_queue.empty():
                        limited_items.append(self.scraper.main_queue.get())

                # Clear the queue and re-add limited items
                while not self.scraper.main_queue.empty():
                    self.scraper.main_queue.get()

                for item in limited_items:
                    self.scraper.main_queue.put(item)

        # Start the V2.0 high-speed scraping
        logger.info("Starting CS2 Price Collection System V2.0")
        await self.scraper.start_scraping()

        # Wait for completion (the scraper handles its own completion logic)

    async def shutdown(self):
        """Graceful shutdown of the V2.0 system"""
        logger.info("Shutting down V2.0 system...")
        await self.scraper.shutdown()

        self.stats['end_time'] = datetime.now()

        # Generate summary report
        summary_logger = get_summary_logger()
        duration = self.stats['end_time'] - self.stats['start_time']

        logger.info(
            f"CS2 PRICE COLLECTION V2.0 COMPLETED in {duration.total_seconds():.2f} seconds!")

        # Save summary using correct method name
        summary_logger.collection_mode = "V2.0-WORKER-STEALING"
        summary_logger.stats = self.scraper.stats
        summary_logger.duration = duration.total_seconds()
        summary_logger.save_summary()

        logger.info(
            "Collection completed. Summary report saved to logs/summary.txt")


async def main():
    """Main entry point for V2.0 price collection system"""

    parser = argparse.ArgumentParser(
        description="CS2 Price Collection System V2.0 - High-Performance Worker Stealing Architecture",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
🚀 CS2 PRICE COLLECTION SYSTEM V2.0 🚀

EXAMPLES:
  python collect_prices.py --missing-only --limit 5
    Process only missing prices for first 5 skins with V2.0 architecture
    
  python collect_prices.py --missing-only  
    Process all missing prices with V2.0 worker stealing system
    
  python collect_prices.py --limit 10
    Process first 10 skins completely with V2.0 power
    
  python collect_prices.py
    Full V2.0 processing of entire database

V2.0 FEATURES:
• Worker stealing architecture with proxy and WebDriver workers
• Smart priority queues for optimal resource utilization
• Dynamic worker scaling and health monitoring
• Enhanced performance through concurrent processing

ENVIRONMENT VARIABLES:
  HEADERS_SOURCE_URL - Custom headers source URL
  PROXY_GITHUB_URL   - Custom proxy source URL
        """
    )

    parser.add_argument('--missing-only', action='store_true',
                        help='Only process items with missing price data')
    parser.add_argument('--limit', type=int, metavar='N',
                        help='Limit processing to N skins (counts skins, not variants)')
    parser.add_argument('--no-resume', action='store_true',
                        help='Start from beginning instead of resuming from checkpoint')

    args = parser.parse_args()

    # Create collector
    collector = V2PriceCollector()

    # Handle shutdown signals
    shutdown_task = None

    def signal_handler(signum, frame):
        nonlocal shutdown_task
        logger.info(
            "Received interrupt signal - initiating graceful shutdown...")
        if not shutdown_task:
            shutdown_task = asyncio.create_task(collector.shutdown())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Initialize V2.0 system
        await collector.initialize()

        # Start collection
        await collector.collect_prices(
            missing_only=args.missing_only,
            limit=args.limit,
            resume=not args.no_resume
        )

    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise
    finally:
        await collector.shutdown()


if __name__ == "__main__":
    # Ensure logs directory exists
    os.makedirs('logs', exist_ok=True)

    # Run the V2.0 system
    asyncio.run(main())
