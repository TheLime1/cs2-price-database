"""
Bulk Fallback Collection for CS2 Price Database
Optimizes fallback scraping to collect all variants in single web scraping session
"""

import logging
import asyncio
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class BulkCollectionItem:
    """Item to be collected in bulk"""
    skin_name: str
    market_hash_name: str
    wear_condition: Optional[str] = None
    stattrak: bool = False
    souvenir: bool = False
    priority: int = 0  # Higher priority = collected first


@dataclass
class BulkCollectionBatch:
    """Batch of items for bulk collection"""
    batch_id: str
    skin_name: str
    items: List[BulkCollectionItem]
    timestamp: datetime
    max_variants: int = 10  # Max variants to collect in one session

    def get_item_count(self) -> int:
        return len(self.items)

    def get_wear_conditions(self) -> Set[str]:
        return {item.wear_condition for item in self.items if item.wear_condition}

    def has_stattrak_variants(self) -> bool:
        return any(item.stattrak for item in self.items)

    def has_souvenir_variants(self) -> bool:
        return any(item.souvenir for item in self.items)


@dataclass
class BulkCollectionConfig:
    """Configuration for bulk collection"""
    max_items_per_batch: int = 10  # Max items per bulk collection
    max_batches_concurrent: int = 3  # Max concurrent bulk collections
    session_timeout: int = 120  # Session timeout in seconds
    retry_failed_items: bool = True  # Retry individual failed items
    prioritize_missing_data: bool = True  # Prioritize items without recent data
    group_by_skin: bool = True  # Group variants of same skin together
    min_batch_size: int = 2  # Minimum items to justify bulk collection


class BulkFallbackCollector:
    """Manages bulk collection of price data using fallback scraper"""

    def __init__(self, fallback_scraper, config: Optional[BulkCollectionConfig] = None):
        self.fallback_scraper = fallback_scraper
        self.config = config or BulkCollectionConfig()
        self.active_batches: Dict[str, BulkCollectionBatch] = {}
        self.completed_batches: Dict[str, Dict] = {}
        self.failed_items: List[BulkCollectionItem] = []

        # Performance tracking
        self.bulk_stats = {
            'batches_processed': 0,
            'items_collected': 0,
            'items_failed': 0,
            'total_time_saved': 0.0,  # Estimated time saved vs individual requests
            'success_rate': 0.0
        }

        logger.info("📦 Bulk fallback collector initialized (Max batch: %d, Concurrent: %d)",
                    self.config.max_items_per_batch, self.config.max_batches_concurrent)

    def create_batches_from_items(self, items: List[BulkCollectionItem]) -> List[BulkCollectionBatch]:
        """Create optimized batches from a list of items"""
        if not items:
            return []

        if self.config.group_by_skin:
            batches = self._create_skin_grouped_batches(items)
        else:
            batches = self._create_mixed_batches(items)

        logger.info("📦 Created %d bulk collection batches from %d items", len(
            batches), len(items))
        return batches

    def _create_skin_grouped_batches(self, items: List[BulkCollectionItem]) -> List[BulkCollectionBatch]:
        """Create batches grouped by skin name"""
        batches = []

        # Group items by skin name
        skin_groups = defaultdict(list)
        for item in items:
            skin_groups[item.skin_name].append(item)

        # Create batches for each skin group
        for skin_name, skin_items in skin_groups.items():
            if len(skin_items) >= self.config.min_batch_size:
                skin_batches = self._create_batches_for_skin(
                    skin_name, skin_items)
                batches.extend(skin_batches)
            else:
                # Add individual items to failed list for individual processing
                self.failed_items.extend(skin_items)
                logger.debug("⚠️ Skin %s has only %d items, adding to individual processing",
                             skin_name, len(skin_items))

        return batches

    def _create_batches_for_skin(self, skin_name: str, skin_items: List[BulkCollectionItem]) -> List[BulkCollectionBatch]:
        """Create batches for a specific skin"""
        batches = []

        # Sort by priority (higher first)
        skin_items.sort(key=lambda x: x.priority, reverse=True)

        # Split into batches if too many items
        for i in range(0, len(skin_items), self.config.max_items_per_batch):
            batch_items = skin_items[i:i + self.config.max_items_per_batch]
            batch_id = f"bulk_{skin_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{i}"

            batch = BulkCollectionBatch(
                batch_id=batch_id,
                skin_name=skin_name,
                items=batch_items,
                timestamp=datetime.now(),
                max_variants=self.config.max_items_per_batch
            )
            batches.append(batch)

            logger.debug("📋 Created batch %s for %s with %d items",
                         batch_id, skin_name, len(batch_items))

        return batches

    def _create_mixed_batches(self, items: List[BulkCollectionItem]) -> List[BulkCollectionBatch]:
        """Create batches without grouping by skin"""
        batches = []

        for i in range(0, len(items), self.config.max_items_per_batch):
            batch_items = items[i:i + self.config.max_items_per_batch]
            batch_id = f"bulk_mixed_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{i}"

            # Use first item's skin name as batch name
            skin_name = batch_items[0].skin_name if batch_items else "mixed"

            batch = BulkCollectionBatch(
                batch_id=batch_id,
                skin_name=skin_name,
                items=batch_items,
                timestamp=datetime.now(),
                max_variants=self.config.max_items_per_batch
            )
            batches.append(batch)

        return batches

    async def process_bulk_batches(self, batches: List[BulkCollectionBatch]) -> Dict[str, Any]:
        """Process multiple batches concurrently"""
        if not batches:
            return {'collected': {}, 'failed': [], 'stats': {}}

        logger.info("🚀 Starting bulk processing of %d batches", len(batches))

        # Limit concurrent batches
        semaphore = asyncio.Semaphore(self.config.max_batches_concurrent)

        async def process_single_batch(batch):
            async with semaphore:
                return await self._process_batch(batch)

        # Process batches concurrently
        start_time = datetime.now()
        results = await asyncio.gather(
            *[process_single_batch(batch) for batch in batches],
            return_exceptions=True
        )
        total_time = (datetime.now() - start_time).total_seconds()

        # Aggregate results
        all_collected = {}
        all_failed = []
        successful_batches = 0

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    "❌ Batch %d failed with exception: %s", i, str(result))
                # Add batch items to failed list
                all_failed.extend(batches[i].items)
            elif result and isinstance(result, dict):
                successful_batches += 1
                all_collected.update(result.get('collected', {}))
                all_failed.extend(result.get('failed', []))

        # Calculate statistics
        total_items = sum(len(batch.items) for batch in batches)
        collected_count = len(all_collected)
        failed_count = len(all_failed)

        # Update bulk statistics
        self.bulk_stats['batches_processed'] += len(batches)
        self.bulk_stats['items_collected'] += collected_count
        self.bulk_stats['items_failed'] += failed_count

        if total_items > 0:
            # Estimate time saved (assume 3 seconds per individual request vs bulk)
            estimated_individual_time = total_items * 3.0
            time_saved = max(0, estimated_individual_time - total_time)
            self.bulk_stats['total_time_saved'] += time_saved

            # Update overall success rate
            total_processed = self.bulk_stats['items_collected'] + \
                self.bulk_stats['items_failed']
            if total_processed > 0:
                self.bulk_stats['success_rate'] = self.bulk_stats['items_collected'] / \
                    total_processed

        logger.info("✅ Bulk processing completed: %d/%d items collected, %d batches successful, %.1fs total",
                    collected_count, total_items, successful_batches, total_time)

        return {
            'collected': all_collected,
            'failed': all_failed,
            'stats': {
                'total_batches': len(batches),
                'successful_batches': successful_batches,
                'total_items': total_items,
                'collected_count': collected_count,
                'failed_count': failed_count,
                'success_rate': collected_count / max(1, total_items),
                'total_time': total_time,
                'estimated_time_saved': max(0, total_items * 3.0 - total_time)
            }
        }

    async def _process_batch(self, batch: BulkCollectionBatch) -> Dict[str, Any]:
        """Process a single batch using fallback scraper"""
        logger.info("🔄 Processing bulk batch %s with %d items (%s)",
                    batch.batch_id, len(batch.items), batch.skin_name)

        start_time = datetime.now()
        collected = {}
        failed = []

        try:
            # Mark batch as active
            self.active_batches[batch.batch_id] = batch

            # Check if fallback scraper supports bulk collection
            if hasattr(self.fallback_scraper, 'collect_skin_variants_bulk'):
                # Use native bulk collection method
                result = await self._use_native_bulk_collection(batch)
            else:
                # Use optimized session-based collection
                result = await self._use_session_based_collection(batch)

            collected = result.get('collected', {})
            failed = result.get('failed', [])

            processing_time = (datetime.now() - start_time).total_seconds()

            # Store completed batch info
            self.completed_batches[batch.batch_id] = {
                'batch': batch,
                'collected_count': len(collected),
                'failed_count': len(failed),
                'processing_time': processing_time,
                'completed_at': datetime.now()
            }

            logger.info("✅ Batch %s completed: %d collected, %d failed (%.1fs)",
                        batch.batch_id, len(collected), len(failed), processing_time)

        except Exception as e:
            logger.error("❌ Batch %s failed: %s", batch.batch_id, str(e))
            # Add all batch items to failed list
            failed = batch.items

        finally:
            # Remove from active batches
            if batch.batch_id in self.active_batches:
                del self.active_batches[batch.batch_id]

        return {'collected': collected, 'failed': failed}

    async def _use_native_bulk_collection(self, batch: BulkCollectionBatch) -> Dict[str, Any]:
        """Use native bulk collection method if available"""
        logger.debug(
            "🔧 Using native bulk collection for batch %s", batch.batch_id)

        try:
            # Prepare items for native method
            item_data = []
            for item in batch.items:
                item_data.append({
                    'market_hash_name': item.market_hash_name,
                    'wear_condition': item.wear_condition,
                    'stattrak': item.stattrak,
                    'souvenir': item.souvenir
                })

            # Call native bulk collection
            result = await self.fallback_scraper.collect_skin_variants_bulk(
                skin_name=batch.skin_name,
                items=item_data,
                timeout=self.config.session_timeout
            )

            return result

        except Exception as e:
            logger.error("❌ Native bulk collection failed for %s: %s",
                         batch.batch_id, str(e))
            return {'collected': {}, 'failed': batch.items}

    async def _use_session_based_collection(self, batch: BulkCollectionBatch) -> Dict[str, Any]:
        """Use session-based collection for optimized scraping"""
        logger.debug(
            "🌐 Using session-based collection for batch %s", batch.batch_id)

        collected = {}
        failed = []

        try:
            # Start a scraping session
            if hasattr(self.fallback_scraper, 'start_session'):
                session = await self.fallback_scraper.start_session()
            else:
                session = None

            try:
                # Navigate to skin page once
                if hasattr(self.fallback_scraper, 'navigate_to_skin'):
                    await self.fallback_scraper.navigate_to_skin(batch.skin_name, session=session)

                # Collect each item using the same session
                for item in batch.items:
                    try:
                        logger.debug(
                            "🎯 Collecting %s from batch session", item.market_hash_name)

                        result = await self.fallback_scraper.get_item_price(
                            market_hash_name=item.market_hash_name,
                            session=session,
                            use_existing_page=True
                        )

                        if result:
                            collected[item.market_hash_name] = result
                            logger.debug("✅ Collected %s from batch",
                                         item.market_hash_name)
                        else:
                            failed.append(item)
                            logger.debug(
                                "❌ Failed to collect %s from batch", item.market_hash_name)

                        # Small delay between items in same session
                        await asyncio.sleep(0.5)

                    except Exception as e:
                        logger.debug(
                            "❌ Error collecting %s in batch: %s", item.market_hash_name, str(e))
                        failed.append(item)

            finally:
                # Close the session
                if session and hasattr(self.fallback_scraper, 'close_session'):
                    await self.fallback_scraper.close_session(session)

        except Exception as e:
            logger.error(
                "❌ Session-based collection failed for %s: %s", batch.batch_id, str(e))
            failed = batch.items

        return {'collected': collected, 'failed': failed}

    def get_bulk_statistics(self) -> Dict:
        """Get bulk collection statistics"""
        return self.bulk_stats.copy()

    def get_active_batches(self) -> Dict[str, BulkCollectionBatch]:
        """Get currently active batches"""
        return self.active_batches.copy()

    def get_failed_items(self) -> List[BulkCollectionItem]:
        """Get items that failed bulk collection"""
        return self.failed_items.copy()

    def clear_failed_items(self):
        """Clear the failed items list"""
        cleared_count = len(self.failed_items)
        self.failed_items.clear()
        logger.info(
            "🗑️ Cleared %d failed items from bulk collection", cleared_count)

    def estimate_time_savings(self, items: List[BulkCollectionItem]) -> Dict:
        """Estimate time savings from bulk collection"""
        if not items:
            return {'individual_time': 0, 'bulk_time': 0, 'time_saved': 0, 'efficiency_gain': 0}

        # Group by skin to estimate batches
        skin_groups = defaultdict(list)
        for item in items:
            skin_groups[item.skin_name].append(item)

        # Estimate individual collection time (3 seconds per item)
        individual_time = len(items) * 3.0

        # Estimate bulk collection time
        bulk_time = 0
        for skin_name, skin_items in skin_groups.items():
            if len(skin_items) >= self.config.min_batch_size:
                # Bulk collection: setup time + item time
                batches = (len(skin_items) + self.config.max_items_per_batch -
                           1) // self.config.max_items_per_batch
                # 10s setup + 0.5s per item
                bulk_time += batches * (10.0 + len(skin_items) * 0.5)
            else:
                # Individual collection for small groups
                bulk_time += len(skin_items) * 3.0

        time_saved = max(0, individual_time - bulk_time)
        efficiency_gain = (time_saved / individual_time *
                           100) if individual_time > 0 else 0

        return {
            'individual_time': individual_time,
            'bulk_time': bulk_time,
            'time_saved': time_saved,
            'efficiency_gain': efficiency_gain,
            'items_count': len(items),
            'skin_groups': len(skin_groups)
        }
