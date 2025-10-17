"""
Database Migration Script for CS2 Price Database V3.0

Migrates the database from V2.0 schema to V3.0 schema:

V2.0 → V3.0 Changes:
1. Add 'wear_range' field to each variant: {min: float, max: float}
2. Add 'achievable' boolean field to each variant
3. Rename 'available' → 'listing' with structure: {normal: bool, stattrak: bool}
4. Remove top-level 'availability' and 'stattrak_availability' arrays
5. Update variant structure to new format

Optional Features:
- Scrape wear ranges from csgoskins.gg (--scrape-wear-ranges)
- Dry run mode to preview changes (--dry-run)
- Create backup before migration (automatic)
- Validation of migrated data

Usage:
  python migrate_database_v3.py                    # Basic migration with default ranges
  python migrate_database_v3.py --scrape-wear-ranges  # Scrape actual wear ranges
  python migrate_database_v3.py --dry-run          # Preview changes without saving
"""

import json
import asyncio
import logging
import argparse
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
import shutil

# Import the wear range scraper
from csgoskins_scraper import CSGOSkinsGGScraper, SkinWearData

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


class DatabaseMigrationV3:
    """Handles migration from V2.0 to V3.0 database schema"""

    # Standard CS2 wear condition float ranges (fallback)
    DEFAULT_WEAR_RANGES = {
        'Factory New': {'min': 0.00, 'max': 0.07},
        'Minimal Wear': {'min': 0.07, 'max': 0.15},
        'Field-Tested': {'min': 0.15, 'max': 0.38},
        'Well-Worn': {'min': 0.38, 'max': 0.45},
        'Battle-Scarred': {'min': 0.45, 'max': 1.00}
    }

    def __init__(self, database_path: str = "data/skins_database.json"):
        self.database_path = database_path
        self.backup_path = None
        self.stats = {
            'skins_processed': 0,
            'variants_migrated': 0,
            'wear_ranges_added': 0,
            'fields_removed': 0,
            'errors': 0
        }

    def create_backup(self) -> str:
        """Create a backup of the database before migration"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = Path("backups")
        backup_dir.mkdir(exist_ok=True)

        self.backup_path = backup_dir / f"skins_database_v2_backup_{timestamp}.json"

        logger.info(f"📦 Creating backup: {self.backup_path}")
        shutil.copy2(self.database_path, self.backup_path)
        logger.info(f"✅ Backup created successfully")

        return str(self.backup_path)

    def load_database(self) -> Dict:
        """Load the current database"""
        logger.info(f"📂 Loading database from: {self.database_path}")

        with open(self.database_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        skins_count = len(data.get('skins', []))
        logger.info(f"✅ Loaded {skins_count} skins")

        return data

    def save_database(self, data: Dict):
        """Save the migrated database"""
        logger.info(f"💾 Saving migrated database to: {self.database_path}")

        with open(self.database_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info("✅ Database saved successfully")

    def migrate_variant(self, variant: Dict, wear_range_data: Optional[Dict] = None) -> Dict:
        """Migrate a single variant to V3.0 schema"""
        migrated = {}

        # 1. Copy existing fields that don't change
        migrated['wear'] = variant.get('wear', 'Unknown')
        migrated['image'] = variant.get('image', '')

        # 2. Migrate pricing structure (prices remains the same in V3.0)
        migrated['prices'] = variant.get('prices', {})

        # 3. Add wear_range (from scraped data or defaults)
        wear_condition = variant.get('wear', 'Unknown')
        if wear_range_data and wear_condition in wear_range_data:
            migrated['wear_range'] = wear_range_data[wear_condition]
            self.stats['wear_ranges_added'] += 1
        else:
            # Use default ranges
            migrated['wear_range'] = self.DEFAULT_WEAR_RANGES.get(
                wear_condition,
                {'min': 0.0, 'max': 1.0}
            )

        # 4. Add achievable field (default to True if no data)
        if wear_range_data and wear_condition in wear_range_data:
            migrated['achievable'] = wear_range_data[wear_condition].get('achievable', True)
        else:
            migrated['achievable'] = True  # Assume achievable by default

        # 5. Migrate available → listing structure
        # Old: "available": true/false (just normal variant)
        # New: "listing": {"normal": true/false, "stattrak": true/false}
        old_available = variant.get('available', False)
        
        # Check if StatTrak price exists to determine StatTrak listing
        has_stattrak = 'stattrak' in variant.get('prices', {})
        
        if wear_range_data and wear_condition in wear_range_data:
            # Use scraped data for StatTrak availability
            has_stattrak = wear_range_data[wear_condition].get('has_stattrak', has_stattrak)

        migrated['listing'] = {
            'normal': old_available,
            'stattrak': has_stattrak
        }

        # 6. Copy other V2.0 fields if they exist (for compatibility)
        # Note: We're keeping 'has_normal_listings' and 'has_stattrak_listings' if they exist
        if 'has_normal_listings' in variant:
            migrated['has_normal_listings'] = variant['has_normal_listings']
        if 'has_stattrak_listings' in variant:
            migrated['has_stattrak_listings'] = variant['has_stattrak_listings']

        self.stats['variants_migrated'] += 1
        return migrated

    def migrate_skin(self, skin: Dict, wear_range_map: Optional[Dict] = None) -> Dict:
        """Migrate a single skin to V3.0 schema"""
        migrated = {}

        # Copy all top-level fields except those we're removing
        for key, value in skin.items():
            if key not in ['availability', 'stattrak_availability', 'variants']:
                migrated[key] = value

        # Get wear range data for this skin if available
        skin_id = skin.get('id', '')
        wear_range_data = None
        if wear_range_map and skin_id in wear_range_map:
            wear_range_data = wear_range_map[skin_id]

        # Migrate variants
        migrated['variants'] = []
        for variant in skin.get('variants', []):
            migrated_variant = self.migrate_variant(variant, wear_range_data)
            migrated['variants'].append(migrated_variant)

        # Track removed fields
        if 'availability' in skin:
            self.stats['fields_removed'] += 1
        if 'stattrak_availability' in skin:
            self.stats['fields_removed'] += 1

        self.stats['skins_processed'] += 1
        return migrated

    def migrate_database(self, data: Dict, wear_range_map: Optional[Dict] = None) -> Dict:
        """Migrate entire database to V3.0"""
        logger.info("🔄 Starting database migration to V3.0...")

        migrated = {
            'version': '3.0',
            'migrated_at': datetime.now().isoformat(),
            'migration_notes': 'Migrated from V2.0 to V3.0 schema',
            'skins': []
        }

        # Copy metadata if it exists
        if 'last_updated' in data:
            migrated['last_updated'] = data['last_updated']

        # Migrate each skin
        total_skins = len(data.get('skins', []))
        for i, skin in enumerate(data.get('skins', []), 1):
            if i % 100 == 0:
                logger.info(f"   Processing skin {i}/{total_skins}...")

            try:
                migrated_skin = self.migrate_skin(skin, wear_range_map)
                migrated['skins'].append(migrated_skin)
            except Exception as e:
                logger.error(f"❌ Error migrating skin {skin.get('id', 'unknown')}: {e}")
                self.stats['errors'] += 1

        logger.info("✅ Database migration complete!")
        return migrated

    def validate_migration(self, original: Dict, migrated: Dict) -> bool:
        """Validate the migrated database"""
        logger.info("🔍 Validating migrated database...")

        errors = []

        # Check skin count
        original_count = len(original.get('skins', []))
        migrated_count = len(migrated.get('skins', []))

        if original_count != migrated_count:
            errors.append(f"Skin count mismatch: {original_count} → {migrated_count}")

        # Check required fields
        for skin in migrated.get('skins', []):
            skin_id = skin.get('id', 'unknown')

            # Check that old fields are gone
            if 'availability' in skin:
                errors.append(f"Skin {skin_id} still has 'availability' field")
            if 'stattrak_availability' in skin:
                errors.append(f"Skin {skin_id} still has 'stattrak_availability' field")

            # Check variants have new fields
            for variant in skin.get('variants', []):
                wear = variant.get('wear', 'unknown')

                if 'wear_range' not in variant:
                    errors.append(f"Variant {skin_id}/{wear} missing 'wear_range'")

                if 'achievable' not in variant:
                    errors.append(f"Variant {skin_id}/{wear} missing 'achievable'")

                if 'listing' not in variant:
                    errors.append(f"Variant {skin_id}/{wear} missing 'listing'")
                else:
                    listing = variant['listing']
                    if 'normal' not in listing or 'stattrak' not in listing:
                        errors.append(f"Variant {skin_id}/{wear} has invalid 'listing' structure")

                if 'available' in variant:
                    errors.append(f"Variant {skin_id}/{wear} still has old 'available' field")

        if errors:
            logger.error(f"❌ Validation failed with {len(errors)} errors:")
            for error in errors[:10]:  # Show first 10 errors
                logger.error(f"   - {error}")
            if len(errors) > 10:
                logger.error(f"   ... and {len(errors) - 10} more errors")
            return False

        logger.info("✅ Validation passed!")
        return True

    def print_migration_stats(self):
        """Print migration statistics"""
        print("\n" + "="*80)
        print("MIGRATION STATISTICS")
        print("="*80)
        print(f"Skins processed:        {self.stats['skins_processed']}")
        print(f"Variants migrated:      {self.stats['variants_migrated']}")
        print(f"Wear ranges added:      {self.stats['wear_ranges_added']}")
        print(f"Old fields removed:     {self.stats['fields_removed']}")
        print(f"Errors encountered:     {self.stats['errors']}")
        print("="*80)

        if self.backup_path:
            print(f"\n💾 Backup saved to: {self.backup_path}")

        print("\n✨ Database successfully migrated to V3.0!")
        print("="*80 + "\n")

    async def scrape_wear_ranges(self, data: Dict) -> Dict[str, Dict]:
        """Scrape wear range data from csgoskins.gg"""
        logger.info("🌐 Starting wear range scraping from csgoskins.gg...")

        wear_range_map = {}
        scraper = CSGOSkinsGGScraper(headless=True)

        try:
            await scraper.initialize()

            skins = data.get('skins', [])
            total = len(skins)

            logger.info(f"   Processing {total} skins...")

            for i, skin in enumerate(skins, 1):
                weapon = skin.get('weapon', '')
                skin_name = skin.get('skin_name', '')
                skin_id = skin.get('id', '')

                if i % 10 == 0:
                    logger.info(f"   Progress: {i}/{total} ({i*100//total}%)")

                try:
                    wear_data = await scraper.scrape_skin_wear_data(weapon, skin_name)

                    if wear_data:
                        # Convert to map format
                        wear_map = {}
                        for wr in wear_data.wear_ranges:
                            wear_map[wr.wear_condition] = {
                                'min': wr.min_float,
                                'max': wr.max_float,
                                'achievable': wr.achievable,
                                'has_stattrak': wr.has_stattrak
                            }

                        wear_range_map[skin_id] = wear_map

                except Exception as e:
                    logger.warning(f"⚠️ Error scraping {weapon} | {skin_name}: {e}")

            logger.info(f"✅ Scraped wear ranges for {len(wear_range_map)}/{total} skins")

        finally:
            await scraper.cleanup()

        return wear_range_map


async def main():
    parser = argparse.ArgumentParser(
        description="Migrate CS2 Price Database from V2.0 to V3.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument('--database', default='data/skins_database.json',
                        help='Path to database file (default: data/skins_database.json)')
    parser.add_argument('--scrape-wear-ranges', action='store_true',
                        help='Scrape actual wear ranges from csgoskins.gg (slower but more accurate)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview migration without saving changes')
    parser.add_argument('--skip-backup', action='store_true',
                        help='Skip backup creation (not recommended)')
    parser.add_argument('--skip-validation', action='store_true',
                        help='Skip validation after migration')

    args = parser.parse_args()

    # Create migrator
    migrator = DatabaseMigrationV3(database_path=args.database)

    print("\n" + "="*80)
    print("CS2 PRICE DATABASE V3.0 MIGRATION")
    print("="*80)
    print(f"Database: {args.database}")
    print(f"Scrape wear ranges: {'Yes' if args.scrape_wear_ranges else 'No (using defaults)'}")
    print(f"Dry run: {'Yes' if args.dry_run else 'No'}")
    print("="*80 + "\n")

    # Load database
    data = migrator.load_database()

    # Create backup (unless skipped)
    if not args.skip_backup and not args.dry_run:
        migrator.create_backup()

    # Scrape wear ranges if requested
    wear_range_map = None
    if args.scrape_wear_ranges:
        wear_range_map = await migrator.scrape_wear_ranges(data)
    else:
        logger.info("ℹ️ Using default wear ranges (use --scrape-wear-ranges for actual data)")

    # Perform migration
    migrated_data = migrator.migrate_database(data, wear_range_map)

    # Validate migration
    if not args.skip_validation:
        validation_passed = migrator.validate_migration(data, migrated_data)
        if not validation_passed:
            logger.error("❌ Migration validation failed!")
            return

    # Save migrated database (unless dry run)
    if args.dry_run:
        logger.info("🔍 DRY RUN - Changes not saved")
        
        # Show sample of migrated data
        if migrated_data['skins']:
            sample_skin = migrated_data['skins'][0]
            print("\n" + "="*80)
            print("SAMPLE MIGRATED SKIN (first skin):")
            print("="*80)
            print(json.dumps(sample_skin, indent=2))
            print("="*80 + "\n")
    else:
        migrator.save_database(migrated_data)

    # Print statistics
    migrator.print_migration_stats()


if __name__ == "__main__":
    asyncio.run(main())
