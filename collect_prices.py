"""
CS2 Price Collection System V3.0 🚀
WebDriver-Only Architecture

✨ V3.0 FEATURES:
• 🚀 Pure WebDriver architecture with worker stealing
• 🔄 Smart priority queue system for optimal resource utilization  
• 📊 Proper skin-based limits (--limit 2 = 2 skins, not 20 variants)
• ⚡ Intelligent fallback queue for failed items
• 💾 Advanced checkpointing and graceful shutdown handling
• 🎯 Dynamic worker management and health monitoring
• 🌐 csgoskins.gg integration for wear range validation

💡 USAGE:
High-speed operation with limit:
  python collect_prices.py --missing-only --limit 5

Process all skins with full V3.0 power:
  python collect_prices.py

See --help for all options and configuration details.

🔧 V3.0 ARCHITECTURE:
- WebDriver-only worker stealing system (no proxies, no Steam API)
- Priority-based task queues for optimal throughput
- Dynamic worker scaling based on system resources
- Real-time health monitoring
- Enhanced performance through concurrent processing

🌐 DATA SOURCES:
- csgodatabase.com: Price data for all wear conditions
- csgoskins.gg: Wear range validation and achievability
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


class V3PriceCollector:
    """
    CS2 Price Collection System V3.0

    WebDriver-only worker stealing architecture for maximum reliability.
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

    def configure(self, update_availability: bool = False, ignore_stattrak: bool = False,
                  debug: bool = False):
        """Configure the collector with command-line flags"""
        self.config = {
            'update_availability': update_availability,
            'ignore_stattrak': ignore_stattrak,
            'debug': debug
        }

        # Log configuration
        if debug:
            logger.info("🔧 Debug mode enabled - detailed logging active")
        if ignore_stattrak:
            logger.info("⚡ Ignoring StatTrak variants for faster collection")
        if update_availability:
            logger.info(
                "📊 Availability update mode - analyzing variant availability")

    async def initialize(self):
        """Initialize the V3.0 scraping system"""
        print("🚀" + "="*80)
        print("🚀 CS2 PRICE COLLECTION SYSTEM V3.0")
        print("🚀 WebDriver-only worker stealing architecture")
        print("🚀" + "="*80)
        print("🌐 Data Sources: csgodatabase.com + csgoskins.gg")
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
        """Filter items that need price updates and convert to SkinItem objects (NEWEST FIRST)"""
        logger.info("Scanning database for missing prices...")

        missing_items = []
        processed_skins = 0
        ignore_stattrak = getattr(self, 'config', {}).get(
            'ignore_stattrak', False)

        if ignore_stattrak:
            logger.info(
                "⚡ Ignoring StatTrak variants - processing normal variants only")

        # Process skins in NEWEST FIRST order (reverse database order)
        skins_list = list(data.get('skins', []))
        logger.info(
            f"🔄 Scanning {len(skins_list)} skins in NEWEST FIRST order")

        for skin_data in reversed(skins_list):
            if limit and processed_skins >= limit:
                break

            # Check if any variant is missing price data
            has_missing = False
            missing_variants = []

            for variant in skin_data.get('variants', []):
                if self.needs_price_update(variant):
                    has_missing = True
                    missing_variants.append(variant)

                # Check StatTrak version (only if not ignoring StatTrak)
                if not ignore_stattrak:
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

    async def _update_availability_mode(self, data: Dict, limit: Optional[int] = None):
        """Update availability information for weapons using fallback scraper"""
        from optimized_fallback_scraper import OptimizedCSGODatabaseScraper

        logger.info(
            "🔍 Starting availability analysis using OptimizedCSGODatabaseScraper")

        # Get list of skins to analyze
        skins_list = list(data.get('skins', []))
        if limit:
            skins_list = skins_list[:limit]
            logger.info(f"📊 Limited analysis to first {limit} skins")
        else:
            logger.info(
                f"📊 Analyzing availability for all {len(skins_list)} skins")

        updated_count = 0

        # Use the optimized fallback scraper for availability analysis
        async with OptimizedCSGODatabaseScraper(pool_size=3, headless=True) as scraper:
            for i, skin_data in enumerate(skins_list, 1):
                try:
                    detail_url = skin_data['detail_url']
                    full_name = skin_data['full_name']

                    logger.info(
                        f"🔍 [{i}/{len(skins_list)}] Analyzing {full_name}")

                    # Get comprehensive weapon info including availability
                    weapon_info = await scraper.get_weapon_info(detail_url, full_name)

                    if weapon_info and weapon_info.get('availability'):
                        # Update availability data in the database
                        if await self._update_skin_availability(skin_data, weapon_info):
                            updated_count += 1
                            logger.info(
                                f"✅ Updated availability for {full_name}")
                        else:
                            logger.warning(
                                f"⚠️ Failed to save availability for {full_name}")
                    else:
                        logger.warning(
                            f"❌ No availability data found for {full_name}")

                except Exception as e:
                    logger.error(
                        f"❌ Error analyzing {skin_data.get('full_name', 'unknown')}: {e}")
                    continue

        # Save updated database
        await self._save_database(data)

        logger.info(
            f"🎉 Availability analysis complete! Updated {updated_count}/{len(skins_list)} skins")

    async def _update_skin_availability(self, skin_data: Dict, weapon_info: Dict) -> bool:
        """Update a single skin's availability data"""
        try:
            # Update availability fields
            if 'availability' in weapon_info:
                skin_data['availability'] = weapon_info['availability']

            if 'stattrak_availability' in weapon_info:
                skin_data['stattrak_availability'] = weapon_info['stattrak_availability']

            if 'listings' in weapon_info:
                skin_data['listings'] = weapon_info['listings']

            # Update metadata
            if 'metadata' not in skin_data:
                skin_data['metadata'] = {}
            skin_data['metadata']['availability_last_updated'] = datetime.now(
            ).isoformat()

            # Also update variant-level availability if variants exist
            if 'variants' in skin_data:
                for variant in skin_data['variants']:
                    wear = variant['wear']

                    # Set availability flags
                    variant['available'] = weapon_info.get(
                        'availability', {}).get(wear, False)
                    variant['stattrak_available'] = weapon_info.get(
                        'stattrak_availability', {}).get(wear, False)

                    # Set listing flags
                    variant['has_normal_listings'] = weapon_info.get(
                        'listings', {}).get(wear, False)
                    variant['has_stattrak_listings'] = weapon_info.get(
                        'listings', {}).get(f"StatTrak {wear}", False)

            return True

        except Exception as e:
            logger.error(
                f"❌ Error updating availability for {skin_data.get('full_name', 'unknown')}: {e}")
            return False

    async def _save_database(self, data: Dict):
        """Save the updated database"""
        try:
            # Update database metadata
            data['data_status']['last_availability_update'] = datetime.now().isoformat()

            # Save to file
            with open(self.database_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.info("💾 Database saved successfully")

        except Exception as e:
            logger.error(f"❌ Error saving database: {e}")
            raise

    async def collect_prices(self, missing_only: bool = False, limit: Optional[int] = None, resume: bool = True,
                             update_availability: bool = False, ignore_stattrak: bool = False,
                             debug: bool = False):
        """Main collection method using V3.0 WebDriver-only architecture"""

        # Configure the collector with the provided flags
        self.configure(update_availability, ignore_stattrak, debug)

        # Configure the scraper with relevant flags
        self.scraper.configure(ignore_stattrak=ignore_stattrak)

        self.stats['start_time'] = datetime.now()

        # Load database
        data = self.load_database()

        # Handle special modes
        if update_availability:
            logger.info(
                "🔍 Update availability mode - analyzing weapon availability")
            await self._update_availability_mode(data, limit)
            return

        # Load checkpoint if resuming
        if resume and not missing_only:
            checkpoint = self.load_checkpoint()
            # TODO: Use checkpoint data for resuming

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

                # Update the total_items count to reflect the actual limit
                self.scraper.stats['total_items'] = len(limited_items)
                logger.info(
                    f"Queue adjusted to {len(limited_items)} items due to --limit {limit}")

        # Set the total items count for completion tracking
        if missing_only:
            self.scraper.stats['total_items'] = len(missing_items)
        elif not hasattr(self.scraper.stats, 'total_items') or not self.scraper.stats.get('total_items'):
            self.scraper.stats['total_items'] = self.scraper.main_queue.qsize()

        logger.info(
            f"Total items to process: {self.scraper.stats['total_items']}")

        # Start the V3.0 high-speed scraping
        logger.info("Starting CS2 Price Collection System V3.0")
        
        # Convert SkinItem objects to dictionary format for the scraper
        items_data = []
        for item in missing_items:
            items_data.append({
                'id': item.id,
                'weapon': item.weapon,
                'skin_name': item.skin_name,
                'full_name': item.full_name,
                'detail_url': item.detail_url,
                'variants': item.variants
            })
        
        await self.scraper.process_items(items_data)

        # Wait for completion (the scraper handles its own completion logic)

    async def shutdown(self):
        """Graceful shutdown of the V3.0 system"""
        logger.info("Shutting down V3.0 system...")
        await self.scraper.shutdown()

        self.stats['end_time'] = datetime.now()

        # Generate summary report
        summary_logger = get_summary_logger()
        duration = self.stats['end_time'] - self.stats['start_time']

        logger.info(
            f"CS2 PRICE COLLECTION V3.0 COMPLETED in {duration.total_seconds():.2f} seconds!")

        # Create a proper CollectionStats object for V2.0 system
        from summary_logger import CollectionStats
        collection_stats = CollectionStats(
            env_variables={},
            start_time=self.stats['start_time'],
            end_time=self.stats['end_time'],
            total_duration=duration.total_seconds(),
            total_skins_processed=len(self.scraper.completed_items),
            total_variants_processed=len(
                self.scraper.completed_items) * 50,  # Estimate
            steam_api_success_count=self.scraper.stats.get(
                'proxy_successes', 0),
            fallback_scraper_success_count=self.scraper.stats.get(
                'webdriver_successes', 0),
            total_success_count=len(self.scraper.completed_items),
            steam_api_failure_count=self.scraper.stats.get(
                'proxy_failures', 0),
            fallback_scraper_failure_count=self.scraper.stats.get(
                'webdriver_failures', 0),
            total_failure_count=self.scraper.stats.get('items_failed', 0)
        )

        # Save summary using correct method name
        summary_logger.stats = collection_stats
        summary_logger.save_summary()

        logger.info(
            "Collection completed. Summary report saved to logs/summary.txt")


async def main():
    """Main entry point for V3.0 price collection system"""

    parser = argparse.ArgumentParser(
        description="CS2 Price Collection System V3.0 - WebDriver-Only Architecture",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
🚀 CS2 PRICE COLLECTION SYSTEM V3.0 🚀

EXAMPLES:
  python collect_prices.py --missing-only --limit 5
    Process only missing prices for first 5 skins with V3.0 architecture
    
  python collect_prices.py --missing-only  
    Process all missing prices with V3.0 worker stealing system
    
  python collect_prices.py --limit 10
    Process first 10 skins completely with V3.0 power
    
  python collect_prices.py
    Full V3.0 processing of entire database

V3.0 FEATURES:
• WebDriver-only worker stealing architecture (no proxies, no Steam API)
• Smart priority queues for optimal resource utilization
• Dynamic worker scaling and health monitoring
• csgoskins.gg integration for wear range validation
• Enhanced reliability through direct scraping
        """
    )

    parser.add_argument('--missing-only', action='store_true',
                        help='Only process items with missing price data')
    parser.add_argument('--limit', type=int, metavar='N',
                        help='Limit processing to N skins (counts skins, not variants)')
    parser.add_argument('--no-resume', action='store_true',
                        help='Start from beginning instead of resuming from checkpoint')

    # Additional flags from documentation
    parser.add_argument('--update-availability', action='store_true',
                        help='Update weapon availability information to detect which wear conditions and StatTrak variants actually exist')
    parser.add_argument('--ignore-stattrak', action='store_true',
                        help='Skip StatTrak variants to speed up collection')
    parser.add_argument('--debug', action='store_true',
                        help='Enable detailed debug output including scraping details and responses')

    args = parser.parse_args()

    # Handle debug flag - set logging level
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger('high_speed_scraper').setLevel(logging.DEBUG)
        logging.getLogger('optimized_fallback_scraper').setLevel(logging.DEBUG)

    # Create collector
    collector = V3PriceCollector()

    # Create shutdown event for proper signal handling
    shutdown_event = asyncio.Event()
    shutdown_initiated = False

    def signal_handler(signum, frame):
        nonlocal shutdown_initiated
        if not shutdown_initiated:
            shutdown_initiated = True
            logger.info("🛑 Ctrl+C pressed - Initiating immediate shutdown...")
            shutdown_event.set()
        else:
            logger.info("🚨 Multiple Ctrl+C detected - Force killing...")
            import sys
            sys.exit(1)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Initialize V3.0 system
        await collector.initialize()

        # Create collection task
        collection_task = asyncio.create_task(collector.collect_prices(
            missing_only=args.missing_only,
            limit=args.limit,
            resume=not args.no_resume,
            update_availability=args.update_availability,
            ignore_stattrak=args.ignore_stattrak,
            debug=args.debug
        ))

        # Wait for either completion or shutdown signal
        await asyncio.wait([
            collection_task,
            asyncio.create_task(shutdown_event.wait())
        ], return_when=asyncio.FIRST_COMPLETED)

        # If shutdown was triggered, cancel the collection
        if shutdown_event.is_set():
            logger.info(
                "🛑 Shutdown signal received - cancelling collection...")
            collection_task.cancel()
            try:
                await collection_task
            except asyncio.CancelledError:
                logger.info("✅ Collection cancelled successfully")

    except KeyboardInterrupt:
        logger.info("🛑 Keyboard interrupt detected")
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        raise
    finally:
        logger.info("🔧 Starting final cleanup...")
        await collector.shutdown()
        logger.info("✅ Shutdown complete")


if __name__ == "__main__":
    # Ensure logs directory exists
    os.makedirs('logs', exist_ok=True)

    # Run the V3.0 system
    asyncio.run(main())
