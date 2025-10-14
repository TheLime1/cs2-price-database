"""
Integration script for the new high-speed scraping system
Shows how to integrate with existing collect_prices.py workflow
"""

import asyncio
import logging
import json
import argparse
from datetime import datetime
from typing import Dict, List

from high_speed_scraper import HighSpeedScraper, SkinItem
from summary_logger import get_summary_logger

logger = logging.getLogger(__name__)


class HighSpeedPriceCollector:
    """Integration class that bridges the new scraper with existing systems"""

    def __init__(self):
        self.scraper = HighSpeedScraper()
        self.summary_logger = get_summary_logger()
        self.start_time = None

    async def collect_prices(self,
                             database_path: str = "data/skins_database.json",
                             save_checkpoint: bool = True,
                             checkpoint_interval: int = 100):
        """
        Main price collection method using the new high-speed scraper

        Args:
            database_path: Path to the skins database
            save_checkpoint: Whether to save progress checkpoints
            checkpoint_interval: How often to save checkpoints (items processed)
        """

        logger.info("🚀 Starting high-speed price collection...")
        self.start_time = datetime.now()

        try:
            # Initialize the high-speed scraper
            await self.scraper.initialize()

            # Load items from database
            await self._load_and_queue_items(database_path)

            # Start scraping with monitoring
            await self._run_scraping_with_monitoring(
                save_checkpoint,
                checkpoint_interval,
                database_path
            )

        except Exception as e:
            logger.error(f"❌ Error in price collection: {e}")
            raise
        finally:
            # Ensure proper cleanup
            await self.scraper.shutdown()

            # Generate final summary
            await self._generate_final_summary()

    async def _load_and_queue_items(self, database_path: str):
        """Load items from database and add to scraping queue"""
        logger.info(f"📂 Loading items from: {database_path}")

        with open(database_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        items_loaded = 0
        for skin_data in data.get('skins', []):
            # Skip items that already have recent prices
            if self._has_recent_prices(skin_data):
                continue

            item = SkinItem(
                id=skin_data['id'],
                weapon=skin_data['weapon'],
                skin_name=skin_data['skin_name'],
                full_name=skin_data['full_name'],
                detail_url=skin_data['detail_url'],
                variants=skin_data['variants']
            )

            self.scraper.main_queue.put(item)
            items_loaded += 1

        logger.info(f"✅ Queued {items_loaded} items for scraping")

    def _has_recent_prices(self, skin_data: Dict, max_age_hours: int = 24) -> bool:
        """Check if skin has recent price data"""
        # This would implement the same logic as the existing system
        # to check if prices are fresh enough
        return False  # For now, scrape everything

    async def _run_scraping_with_monitoring(self,
                                            save_checkpoint: bool,
                                            checkpoint_interval: int,
                                            database_path: str):
        """Run scraping with progress monitoring and checkpoints"""

        logger.info("⚡ Starting high-speed scraping with monitoring...")

        # Start scraping in background
        scraping_task = asyncio.create_task(self.scraper.start_scraping())

        # Monitor progress
        last_checkpoint = 0

        try:
            while self.scraper.running:
                await asyncio.sleep(10)  # Check every 10 seconds

                # Log current progress
                self._log_progress()

                # Save checkpoint if needed
                if save_checkpoint:
                    processed = self.scraper.stats['items_processed']
                    if processed - last_checkpoint >= checkpoint_interval:
                        await self._save_checkpoint(database_path)
                        last_checkpoint = processed

                # Check if done
                if (self.scraper.main_queue.empty() and
                    self.scraper.fallback_queue.empty() and
                        self._all_workers_idle()):

                    logger.info("✅ All items processed, stopping scraper...")
                    await self.scraper.shutdown()
                    break

        except KeyboardInterrupt:
            logger.info("⚠️ Received interrupt, shutting down gracefully...")
            await self.scraper.shutdown()

        # Wait for scraping task to complete
        try:
            await asyncio.wait_for(scraping_task, timeout=30)
        except asyncio.TimeoutError:
            logger.warning("⚠️ Scraping task did not complete within timeout")

    def _all_workers_idle(self) -> bool:
        """Check if all workers are idle"""
        for worker in self.scraper.workers.values():
            if worker.status.value in ['working', 'health_check']:
                return False
        return True

    def _log_progress(self):
        """Log current scraping progress"""
        stats = self.scraper.stats

        if self.start_time:
            elapsed = datetime.now() - self.start_time

            logger.info(f"📊 Progress - "
                        f"Processed: {stats['items_processed']}, "
                        f"Failed: {stats['items_failed']}, "
                        f"Queue: {self.scraper.main_queue.qsize()}, "
                        f"Fallback: {self.scraper.fallback_queue.qsize()}, "
                        f"Workers: {len(self.scraper.workers)}, "
                        f"Runtime: {elapsed}")

    async def _save_checkpoint(self, database_path: str):
        """Save current progress as checkpoint"""
        checkpoint_data = {
            'timestamp': datetime.now().isoformat(),
            'stats': self.scraper.stats.copy(),
            'completed_items': list(self.scraper.completed_items),
            'failed_items': list(self.scraper.failed_items),
            'queue_size': self.scraper.main_queue.qsize(),
            'fallback_queue_size': self.scraper.fallback_queue.qsize()
        }

        checkpoint_path = database_path.replace('.json', '_checkpoint.json')
        with open(checkpoint_path, 'w', encoding='utf-8') as f:
            json.dump(checkpoint_data, f, indent=2, ensure_ascii=False)

        logger.info(f"💾 Checkpoint saved: {checkpoint_path}")

    async def _generate_final_summary(self):
        """Generate final summary report"""
        if not self.start_time:
            return

        end_time = datetime.now()
        elapsed = end_time - self.start_time
        stats = self.scraper.stats

        summary = {
            'scraping_method': 'high_speed_worker_stealing',
            'start_time': self.start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'total_runtime': str(elapsed),
            'items_processed': stats['items_processed'],
            'items_failed': stats['items_failed'],
            'proxy_successes': stats['proxy_successes'],
            'proxy_failures': stats['proxy_failures'],
            'webdriver_successes': stats['webdriver_successes'],
            'webdriver_failures': stats['webdriver_failures'],
            'max_concurrent_workers': len(self.scraper.workers),
            'webdriver_count': self.scraper.webdriver_count,
            'success_rate': self._calculate_success_rate()
        }

        # Log summary to both logger and summary logger
        logger.info("📊 Final Summary:")
        for key, value in summary.items():
            logger.info(f"  {key}: {value}")

        # Save summary to file
        summary_path = "logs/high_speed_summary.json"
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        logger.info(f"📄 Summary saved to: {summary_path}")

    def _calculate_success_rate(self) -> float:
        """Calculate overall success rate"""
        stats = self.scraper.stats
        total_processed = stats['items_processed'] + stats['items_failed']

        if total_processed == 0:
            return 0.0

        return (stats['items_processed'] / total_processed) * 100


async def main():
    """Main entry point for high-speed price collection"""
    parser = argparse.ArgumentParser(
        description='High-Speed CS2 Price Collection')
    parser.add_argument('--database', default='data/skins_database.json',
                        help='Path to skins database file')
    parser.add_argument('--no-checkpoint', action='store_true',
                        help='Disable checkpoint saving')
    parser.add_argument('--checkpoint-interval', type=int, default=100,
                        help='Items processed between checkpoints')
    parser.add_argument('--log-level', default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='Logging level')

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/high_speed_collection.log', mode='w'),
            logging.StreamHandler()
        ]
    )

    logger.info("🚀 Starting High-Speed CS2 Price Collection System")
    logger.info(f"📋 Arguments: {args}")

    # Create and run collector
    collector = HighSpeedPriceCollector()

    try:
        await collector.collect_prices(
            database_path=args.database,
            save_checkpoint=not args.no_checkpoint,
            checkpoint_interval=args.checkpoint_interval
        )

        logger.info("✅ High-speed price collection completed successfully!")

    except Exception as e:
        logger.error(f"❌ Price collection failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
