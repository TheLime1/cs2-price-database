"""
Database Cleanup Script for CS2 Skins
Removes variants that have 'success: True' but no price data OR 'success: False' (not tradeable/available on market)
These are variants that exist in the database but are not actually available in the game
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Tuple
import shutil
import os

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler('cleanup.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class VariantCleaner:
    """Cleans up invalid variants from the skins database"""

    def __init__(self, database_path: str = 'data/skins_database.json'):
        self.database_path = database_path
        self.backup_path = None
        self.database = None

    def load_database(self) -> bool:
        """Load the database from file"""
        try:
            with open(self.database_path, 'r', encoding='utf-8') as f:
                self.database = json.load(f)
            logger.info(
                f"✓ Loaded database with {self.database.get('total_skins', 0)} skins")
            return True
        except FileNotFoundError:
            logger.error(f"✗ Database file not found: {self.database_path}")
            return False
        except json.JSONDecodeError as e:
            logger.error(f"✗ Failed to parse database JSON: {e}")
            return False

    def backup_database(self) -> bool:
        """Create a backup of the database before modification"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.backup_path = f"{self.database_path}.backup_{timestamp}"
            shutil.copy2(self.database_path, self.backup_path)
            logger.info(f"✓ Created backup: {self.backup_path}")
            return True
        except Exception as e:
            logger.error(f"✗ Failed to create backup: {e}")
            return False

    def is_invalid_variant(self, variant: Dict) -> Tuple[bool, str]:
        """
        Check if a variant should be removed
        Returns (should_remove, reason)

        A variant is invalid if:
        - normal price has 'success': True but no 'usd' value or usd == 0
        - stattrak price has 'success': True but no 'usd' value or usd == 0
        - normal price has 'success': False (variant doesn't exist)
        - stattrak price has 'success': False (variant doesn't exist)
        """
        reasons = []

        if 'prices' not in variant:
            return False, ""

        prices = variant['prices']

        # Check normal variant
        if 'normal' in prices:
            normal = prices['normal']
            if 'raw_data' in normal:
                raw = normal['raw_data']
                # Has success: True but no price data OR success: False
                if (raw.get('success') and not raw.get('lowest_price')) or raw.get('success') is False:
                    reasons.append('normal')

        # Check StatTrak variant
        if 'stattrak' in prices:
            stattrak = prices['stattrak']
            if 'raw_data' in stattrak:
                raw = stattrak['raw_data']
                # Has success: True but no price data OR success: False
                if (raw.get('success') and not raw.get('lowest_price')) or raw.get('success') is False:
                    reasons.append('stattrak')

        # Remove the entire variant if BOTH normal and stattrak are invalid
        # (meaning the wear level doesn't exist for this skin at all)
        if reasons and len(reasons) == len([k for k in prices.keys() if k in ['normal', 'stattrak']]):
            return True, f"Both {' and '.join(reasons)} invalid"

        return False, ""

    def should_remove_price_type(self, price_data: Dict) -> bool:
        """Check if a specific price type (normal/stattrak) should be removed"""
        if 'raw_data' not in price_data:
            return False

        raw = price_data['raw_data']
        # Has success: True but no price data OR success: False
        return (raw.get('success') and not raw.get('lowest_price')) or raw.get('success') is False

    def clean_database(self, dry_run: bool = False) -> Dict[str, int]:
        """
        Remove invalid variants from the database

        Args:
            dry_run: If True, only report what would be removed without modifying

        Returns:
            Dict with statistics about the cleanup
        """
        stats = {
            'skins_checked': 0,
            'variants_removed': 0,
            'price_types_removed': 0,
            'skins_completely_removed': 0
        }

        skins_to_remove = []

        for skin in self.database['skins']:
            stats['skins_checked'] += 1
            skin_id = skin.get('id', 'unknown')
            skin_name = skin.get('full_name', 'Unknown')

            variants_to_keep = []

            for variant in skin.get('variants', []):
                wear = variant.get('wear', 'Unknown')

                # Check if entire variant should be removed
                should_remove_variant, reason = self.is_invalid_variant(
                    variant)

                if should_remove_variant:
                    stats['variants_removed'] += 1
                    logger.info(
                        f"  ✗ Removing variant: {skin_name} ({wear}) - {reason}")
                else:
                    # Check individual price types
                    if 'prices' in variant:
                        prices_modified = False

                        if 'normal' in variant['prices']:
                            if self.should_remove_price_type(variant['prices']['normal']):
                                logger.info(
                                    f"  ⚠ Removing normal price for: {skin_name} ({wear})")
                                if not dry_run:
                                    del variant['prices']['normal']
                                stats['price_types_removed'] += 1
                                prices_modified = True

                        if 'stattrak' in variant['prices']:
                            if self.should_remove_price_type(variant['prices']['stattrak']):
                                logger.info(
                                    f"  ⚠ Removing stattrak price for: {skin_name} ({wear})")
                                if not dry_run:
                                    del variant['prices']['stattrak']
                                stats['price_types_removed'] += 1
                                prices_modified = True

                        # If variant has no valid prices left, mark it for removal
                        if not dry_run and prices_modified and not variant['prices']:
                            logger.info(
                                f"  ✗ Variant has no valid prices, removing: {skin_name} ({wear})")
                            stats['variants_removed'] += 1
                            continue

                    variants_to_keep.append(variant)

            # Update skin with cleaned variants
            if not dry_run:
                skin['variants'] = variants_to_keep

            # If skin has no variants left, mark for complete removal
            if not variants_to_keep:
                skins_to_remove.append(skin_id)
                stats['skins_completely_removed'] += 1
                logger.warning(
                    f"⚠ Skin has no valid variants, will be removed: {skin_name}")

        # Remove skins with no variants
        if not dry_run and skins_to_remove:
            self.database['skins'] = [
                skin for skin in self.database['skins']
                if skin.get('id') not in skins_to_remove
            ]
            self.database['total_skins'] = len(self.database['skins'])

        return stats

    def save_database(self) -> bool:
        """Save the cleaned database back to file"""
        try:
            # Update metadata
            if 'data_status' not in self.database:
                self.database['data_status'] = {}

            self.database['data_status']['last_cleanup'] = datetime.now(
            ).isoformat()
            self.database['generated_at'] = datetime.now().isoformat()

            # Write to file
            with open(self.database_path, 'w', encoding='utf-8') as f:
                json.dump(self.database, f, indent=2, ensure_ascii=False)

            logger.info(f"✓ Saved cleaned database to {self.database_path}")
            return True
        except Exception as e:
            logger.error(f"✗ Failed to save database: {e}")
            return False

    def run(self, dry_run: bool = False) -> bool:
        """
        Run the complete cleanup process

        Args:
            dry_run: If True, only report what would be removed without modifying
        """
        logger.info("=" * 80)
        logger.info("STARTING DATABASE CLEANUP")
        logger.info("=" * 80)

        if dry_run:
            logger.info("DRY RUN MODE - No changes will be made")

        # Load database
        if not self.load_database():
            return False

        # Create backup (skip for dry run)
        if not dry_run:
            if not self.backup_database():
                logger.error("Failed to create backup. Aborting cleanup.")
                return False

        # Clean database
        logger.info("\nAnalyzing variants...")
        stats = self.clean_database(dry_run=dry_run)

        # Report statistics
        logger.info("\n" + "=" * 80)
        logger.info("CLEANUP STATISTICS")
        logger.info("=" * 80)
        logger.info(f"Skins checked: {stats['skins_checked']}")
        logger.info(f"Complete variants removed: {stats['variants_removed']}")
        logger.info(
            f"Individual price types removed: {stats['price_types_removed']}")
        logger.info(
            f"Skins completely removed (no valid variants): {stats['skins_completely_removed']}")

        # Save database (skip for dry run)
        if not dry_run:
            logger.info("\nSaving cleaned database...")
            if not self.save_database():
                logger.error(
                    f"\n✗ Failed to save database. Backup available at: {self.backup_path}")
                return False

            logger.info(f"\n✓ Cleanup completed successfully!")
            logger.info(f"✓ Backup saved at: {self.backup_path}")
        else:
            logger.info("\nDRY RUN COMPLETED - No changes were made")

        logger.info("=" * 80)
        return True


def main():
    """Main function"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Clean up invalid variants from CS2 skins database'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be removed without actually removing anything'
    )
    parser.add_argument(
        '--database',
        default='data/skins_database.json',
        help='Path to the database file (default: data/skins_database.json)'
    )

    args = parser.parse_args()

    cleaner = VariantCleaner(database_path=args.database)
    success = cleaner.run(dry_run=args.dry_run)

    return 0 if success else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
