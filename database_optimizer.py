"""
Database Optimization for CS2 Price Database
Implements smart batching and caching to reduce I/O overhead
"""

import logging
import asyncio
import json
import os
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
import threading

logger = logging.getLogger(__name__)


@dataclass
class DatabaseChange:
    """Represents a change to be written to database"""
    item_key: str
    data: Dict[str, Any]
    timestamp: datetime
    operation: str = "update"  # update, insert, delete
    priority: int = 0  # Higher priority = written first


@dataclass
class DatabaseBatch:
    """Batch of database changes"""
    batch_id: str
    changes: List[DatabaseChange]
    created_at: datetime
    max_batch_size: int = 100

    def get_size(self) -> int:
        return len(self.changes)

    def is_full(self) -> bool:
        return len(self.changes) >= self.max_batch_size

    def add_change(self, change: DatabaseChange) -> bool:
        """Add a change to the batch. Returns True if successful, False if batch is full"""
        if self.is_full():
            return False
        self.changes.append(change)
        return True


@dataclass
class DatabaseOptimizerConfig:
    """Configuration for database optimization"""
    max_batch_size: int = 100  # Max changes per batch
    batch_timeout: float = 10.0  # Seconds to wait before forcing batch write
    max_memory_cache_size: int = 1000  # Max items to keep in memory
    backup_interval: int = 3600  # Seconds between backups (1 hour)
    compression_enabled: bool = True  # Enable JSON compression
    # Write immediately if less than N changes pending
    write_immediately_threshold: int = 5
    deduplicate_changes: bool = True  # Remove duplicate changes within batch
    auto_backup_on_significant_changes: bool = True
    significant_changes_threshold: int = 500  # Auto-backup after N changes


class DatabaseOptimizer:
    """Optimizes database writes with smart batching and caching"""

    def __init__(self, database_path: str, config: Optional[DatabaseOptimizerConfig] = None):
        self.database_path = database_path
        self.config = config or DatabaseOptimizerConfig()

        # Batch management
        self.pending_changes: List[DatabaseChange] = []
        self.current_batch: Optional[DatabaseBatch] = None
        self.batch_timer: Optional[threading.Timer] = None

        # Memory cache for fast reads
        self.memory_cache: Dict[str, Dict] = {}
        self.cache_timestamps: Dict[str, datetime] = {}

        # Statistics
        self.stats = {
            'total_writes': 0,
            'batched_writes': 0,
            'immediate_writes': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'total_changes_processed': 0,
            'backups_created': 0,
            'last_backup': None,
            'average_batch_size': 0.0
        }

        # Thread safety
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()

        # Load existing data into cache
        self._initialize_cache()

        logger.info("💾 Database optimizer initialized (Batch size: %d, Timeout: %.1fs, Cache: %d items)",
                    self.config.max_batch_size, self.config.batch_timeout, self.config.max_memory_cache_size)

    def _initialize_cache(self):
        """Initialize memory cache with existing database data"""
        if os.path.exists(self.database_path):
            try:
                with open(self.database_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Load data into cache (limit by cache size)
                items_loaded = 0
                for key, value in data.items():
                    if items_loaded >= self.config.max_memory_cache_size:
                        break

                    self.memory_cache[key] = value
                    self.cache_timestamps[key] = datetime.now()
                    items_loaded += 1

                logger.info(
                    "📥 Loaded %d items into memory cache from database", items_loaded)

            except Exception as e:
                logger.error("❌ Failed to initialize cache: %s", str(e))

    def queue_change(self, item_key: str, data: Dict[str, Any], priority: int = 0, operation: str = "update"):
        """Queue a database change for batched writing"""
        change = DatabaseChange(
            item_key=item_key,
            data=data,
            timestamp=datetime.now(),
            operation=operation,
            priority=priority
        )

        with self._lock:
            # Update memory cache immediately for fast reads
            if operation == "update" or operation == "insert":
                self.memory_cache[item_key] = data.copy()
                self.cache_timestamps[item_key] = datetime.now()
            elif operation == "delete":
                if item_key in self.memory_cache:
                    del self.memory_cache[item_key]
                if item_key in self.cache_timestamps:
                    del self.cache_timestamps[item_key]

            # Manage cache size
            self._manage_cache_size()

            # Add to pending changes
            self.pending_changes.append(change)
            self.stats['total_changes_processed'] += 1

            # Check if we should write immediately
            if len(self.pending_changes) <= self.config.write_immediately_threshold:
                logger.debug("⚡ Immediate write triggered for %s (%d pending changes)",
                             item_key, len(self.pending_changes))
                self._schedule_immediate_write()
            else:
                self._try_create_batch()

        logger.debug("📝 Queued change for %s (priority: %d, pending: %d)",
                     item_key, priority, len(self.pending_changes))

    def _manage_cache_size(self):
        """Manage memory cache size by removing oldest items"""
        if len(self.memory_cache) <= self.config.max_memory_cache_size:
            return

        # Sort by timestamp and remove oldest items
        sorted_items = sorted(
            self.cache_timestamps.items(),
            key=lambda x: x[1]
        )

        items_to_remove = len(self.memory_cache) - \
            self.config.max_memory_cache_size

        for i in range(items_to_remove):
            key_to_remove = sorted_items[i][0]
            if key_to_remove in self.memory_cache:
                del self.memory_cache[key_to_remove]
            if key_to_remove in self.cache_timestamps:
                del self.cache_timestamps[key_to_remove]

        logger.debug("🧹 Cleaned %d items from memory cache", items_to_remove)

    def _try_create_batch(self):
        """Try to create a new batch if conditions are met"""
        if len(self.pending_changes) >= self.config.max_batch_size:
            self._create_batch()
        elif not self.batch_timer:
            # Start timer for batch timeout
            self.batch_timer = threading.Timer(
                self.config.batch_timeout, self._on_batch_timeout)
            self.batch_timer.start()
            logger.debug("⏰ Started batch timer (%.1fs)",
                         self.config.batch_timeout)

    def _create_batch(self):
        """Create a batch from pending changes"""
        if not self.pending_changes:
            return

        # Cancel existing timer
        if self.batch_timer:
            self.batch_timer.cancel()
            self.batch_timer = None

        # Sort changes by priority (higher first)
        self.pending_changes.sort(key=lambda x: x.priority, reverse=True)

        # Deduplicate changes if enabled
        if self.config.deduplicate_changes:
            self.pending_changes = self._deduplicate_changes(
                self.pending_changes)

        # Create batch
        batch_changes = self.pending_changes[:self.config.max_batch_size]
        self.pending_changes = self.pending_changes[self.config.max_batch_size:]

        batch = DatabaseBatch(
            batch_id=f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
            changes=batch_changes,
            created_at=datetime.now(),
            max_batch_size=self.config.max_batch_size
        )

        logger.info("📦 Created batch %s with %d changes",
                    batch.batch_id, len(batch_changes))

        # Process batch asynchronously
        threading.Thread(target=self._process_batch,
                         args=(batch,), daemon=True).start()

        # If there are still pending changes, create another batch
        if self.pending_changes:
            self._try_create_batch()

    def _deduplicate_changes(self, changes: List[DatabaseChange]) -> List[DatabaseChange]:
        """Remove duplicate changes, keeping the most recent for each item"""
        item_changes = {}

        # Keep only the most recent change for each item
        for change in reversed(changes):  # Process in reverse to keep most recent
            if change.item_key not in item_changes:
                item_changes[change.item_key] = change

        deduplicated = list(item_changes.values())
        removed_count = len(changes) - len(deduplicated)

        if removed_count > 0:
            logger.debug("🔄 Deduplicated %d changes (%d → %d)",
                         removed_count, len(changes), len(deduplicated))

        return deduplicated

    def _on_batch_timeout(self):
        """Handle batch timeout"""
        with self._lock:
            logger.debug("⏰ Batch timeout triggered (%d pending changes)", len(
                self.pending_changes))
            self.batch_timer = None
            if self.pending_changes:
                self._create_batch()

    def _schedule_immediate_write(self):
        """Schedule an immediate write for small number of changes"""
        if self.batch_timer:
            self.batch_timer.cancel()
            self.batch_timer = None

        # Process immediately in background thread
        threading.Thread(
            target=self._process_immediate_changes, daemon=True).start()

    def _process_immediate_changes(self):
        """Process immediate changes"""
        with self._lock:
            if not self.pending_changes:
                return

            changes_to_process = self.pending_changes.copy()
            self.pending_changes.clear()

        # Create immediate batch
        batch = DatabaseBatch(
            batch_id=f"immediate_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
            changes=changes_to_process,
            created_at=datetime.now()
        )

        logger.debug("⚡ Processing %d immediate changes",
                     len(changes_to_process))
        self._process_batch(batch)
        self.stats['immediate_writes'] += 1

    def _process_batch(self, batch: DatabaseBatch):
        """Process a batch of database changes"""
        start_time = datetime.now()

        try:
            with self._write_lock:
                # Load and apply changes
                database = self._load_database()
                changes_applied = self._apply_batch_changes(database, batch)

                # Write updated database
                self._write_database(database)

                # Update statistics and logging
                processing_time = (datetime.now() - start_time).total_seconds()
                self._update_batch_statistics(
                    batch, changes_applied, processing_time)

                # Handle backup if needed
                self._check_and_create_backup()

        except Exception as e:
            logger.error("❌ Failed to process batch %s: %s",
                         batch.batch_id, str(e))

    def _load_database(self) -> Dict:
        """Load current database from file"""
        if os.path.exists(self.database_path):
            with open(self.database_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            return {}

    def _apply_batch_changes(self, database: Dict, batch: DatabaseBatch) -> int:
        """Apply changes from batch to database"""
        changes_applied = 0

        for change in batch.changes:
            try:
                if change.operation in ["update", "insert"]:
                    database[change.item_key] = change.data
                    changes_applied += 1
                elif change.operation == "delete":
                    if change.item_key in database:
                        del database[change.item_key]
                        changes_applied += 1
            except Exception as e:
                logger.error("❌ Failed to apply change for %s: %s",
                             change.item_key, str(e))

        return changes_applied

    def _write_database(self, database: Dict):
        """Write database to file"""
        with open(self.database_path, 'w', encoding='utf-8') as f:
            if self.config.compression_enabled:
                json.dump(database, f, separators=(
                    ',', ':'), ensure_ascii=False)
            else:
                json.dump(database, f, indent=2, ensure_ascii=False)

    def _update_batch_statistics(self, batch: DatabaseBatch, changes_applied: int, processing_time: float):
        """Update statistics after batch processing"""
        self.stats['total_writes'] += 1
        self.stats['batched_writes'] += 1

        # Update average batch size
        total_batches = self.stats['batched_writes'] + \
            self.stats['immediate_writes']
        if total_batches > 0:
            self.stats['average_batch_size'] = (
                (self.stats['average_batch_size'] * (total_batches -
                 1) + len(batch.changes)) / total_batches
            )

        logger.info("✅ Processed batch %s: %d changes applied (%.2fs)",
                    batch.batch_id, changes_applied, processing_time)

    def _check_and_create_backup(self):
        """Check if backup is needed and create it"""
        if (self.config.auto_backup_on_significant_changes and
                self.stats['total_changes_processed'] % self.config.significant_changes_threshold == 0):
            self._create_backup()

    def get_item(self, item_key: str) -> Optional[Dict]:
        """Get an item from cache or database"""
        # Check memory cache first
        if item_key in self.memory_cache:
            self.stats['cache_hits'] += 1
            # Update access time
            self.cache_timestamps[item_key] = datetime.now()
            return self.memory_cache[item_key].copy()

        # Load from database
        self.stats['cache_misses'] += 1

        try:
            if os.path.exists(self.database_path):
                with open(self.database_path, 'r', encoding='utf-8') as f:
                    database = json.load(f)

                if item_key in database:
                    # Add to cache for future access
                    if len(self.memory_cache) < self.config.max_memory_cache_size:
                        self.memory_cache[item_key] = database[item_key].copy()
                        self.cache_timestamps[item_key] = datetime.now()

                    return database[item_key].copy()

        except Exception as e:
            logger.error(
                "❌ Failed to read item %s from database: %s", item_key, str(e))

        return None

    def force_write(self):
        """Force immediate write of all pending changes"""
        with self._lock:
            if self.pending_changes:
                logger.info("🔧 Forcing write of %d pending changes",
                            len(self.pending_changes))
                self._create_batch()

    def _create_backup(self):
        """Create a backup of the database"""
        if not os.path.exists(self.database_path):
            return

        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = f"{self.database_path}.backup_{timestamp}"

            # Copy database file
            with open(self.database_path, 'r', encoding='utf-8') as source:
                with open(backup_path, 'w', encoding='utf-8') as backup:
                    backup.write(source.read())

            self.stats['backups_created'] += 1
            self.stats['last_backup'] = datetime.now()

            logger.info("💾 Created database backup: %s", backup_path)

        except Exception as e:
            logger.error("❌ Failed to create backup: %s", str(e))

    def get_statistics(self) -> Dict:
        """Get optimizer statistics"""
        cache_hit_rate = 0.0
        if self.stats['cache_hits'] + self.stats['cache_misses'] > 0:
            cache_hit_rate = self.stats['cache_hits'] / \
                (self.stats['cache_hits'] + self.stats['cache_misses'])

        return {
            **self.stats,
            'cache_hit_rate': cache_hit_rate,
            'cache_size': len(self.memory_cache),
            'pending_changes': len(self.pending_changes),
            'memory_usage_mb': len(json.dumps(self.memory_cache).encode('utf-8')) / 1024 / 1024
        }

    def cleanup(self):
        """Cleanup resources and force final write"""
        logger.info("🧹 Cleaning up database optimizer...")

        # Cancel any pending timer
        if self.batch_timer:
            self.batch_timer.cancel()
            self.batch_timer = None

        # Force write any remaining changes
        self.force_write()

        # Clear memory cache
        self.memory_cache.clear()
        self.cache_timestamps.clear()

        logger.info("✅ Database optimizer cleanup completed")
