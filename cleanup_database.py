#!/usr/bin/env python3
"""
Database Cleanup Script for CS2 Price Database
===============================================

This script cleans up the skins database by:
1. Removing unnecessary metadata fields
2. Keeping only essential price data
3. Moving index to separate file
4. Recalculating accurate statistics
5. Creating a clean, optimized database structure

Usage:
    python cleanup_database.py
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Any


class DatabaseCleanup:
    def __init__(self, database_path: str = "data/skins_database.json"):
        self.database_path = database_path
        self.backup_path = f"{database_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.index_path = "data/skins_index.json"

    def load_database(self) -> Dict[str, Any]:
        """Load the current database"""
        print(f"📂 Loading database from {self.database_path}")
        with open(self.database_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def create_backup(self, data: Dict[str, Any]) -> None:
        """Create a backup of the original database"""
        print(f"💾 Creating backup at {self.backup_path}")
        with open(self.backup_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def clean_price_data(self, price_obj: Dict[str, Any]) -> Dict[str, Any]:
        """Clean price object to keep only essential data"""
        cleaned = {}

        # Keep only essential fields
        if 'usd' in price_obj and price_obj['usd']:
            cleaned['usd'] = price_obj['usd']

        if 'eur' in price_obj and price_obj['eur']:
            cleaned['eur'] = price_obj['eur']

        if 'last_updated' in price_obj:
            cleaned['last_updated'] = price_obj['last_updated']

        return cleaned if cleaned else None

    def clean_variant(self, variant: Dict[str, Any]) -> Dict[str, Any]:
        """Clean a single variant object"""
        cleaned_variant = {
            'wear': variant['wear'],
            'wear_short': variant['wear_short'],
            'float_range': variant['float_range']
        }

        # Add availability if present
        if 'available' in variant:
            cleaned_variant['available'] = variant['available']
        if 'stattrak_available' in variant:
            cleaned_variant['stattrak_available'] = variant['stattrak_available']

        # Clean prices
        if 'prices' in variant:
            cleaned_prices = {}

            if 'normal' in variant['prices']:
                cleaned_normal = self.clean_price_data(
                    variant['prices']['normal'])
                if cleaned_normal:
                    cleaned_prices['normal'] = cleaned_normal

            if 'stattrak' in variant['prices']:
                cleaned_stattrak = self.clean_price_data(
                    variant['prices']['stattrak'])
                if cleaned_stattrak:
                    cleaned_prices['stattrak'] = cleaned_stattrak

            if cleaned_prices:
                cleaned_variant['prices'] = cleaned_prices

        # Legacy price field handling
        if 'price' in variant:
            legacy_price = self.clean_price_data(variant['price'])
            if legacy_price:
                if 'prices' not in cleaned_variant:
                    cleaned_variant['prices'] = {}
                cleaned_variant['prices']['normal'] = legacy_price

        if 'stattrak_price' in variant:
            legacy_stattrak = self.clean_price_data(variant['stattrak_price'])
            if legacy_stattrak:
                if 'prices' not in cleaned_variant:
                    cleaned_variant['prices'] = {}
                cleaned_variant['prices']['stattrak'] = legacy_stattrak

        return cleaned_variant

    def clean_skin(self, skin: Dict[str, Any]) -> Dict[str, Any]:
        """Clean a single skin object"""
        cleaned_skin = {
            'id': skin['id'],
            'weapon': skin['weapon'],
            'skin_name': skin['skin_name'],
            'full_name': skin['full_name'],
            'rarity': skin['rarity'],
            'rarity_color': skin['rarity_color'],
            'collection': skin['collection'],
            'introduced': skin['introduced'],
            'detail_url': skin['detail_url']
        }

        # Clean variants
        if 'variants' in skin:
            cleaned_variants = []
            for variant in skin['variants']:
                cleaned_variant = self.clean_variant(variant)
                cleaned_variants.append(cleaned_variant)
            cleaned_skin['variants'] = cleaned_variants

        # Add metadata if it exists and is useful
        if 'metadata' in skin:
            useful_metadata = {}
            if 'last_updated' in skin['metadata']:
                useful_metadata['last_updated'] = skin['metadata']['last_updated']
            if 'availability_last_updated' in skin['metadata']:
                useful_metadata['availability_last_updated'] = skin['metadata']['availability_last_updated']

            if useful_metadata:
                cleaned_skin['metadata'] = useful_metadata

        return cleaned_skin

    def extract_index(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract and create a comprehensive index"""
        index = {
            'version': '1.0',
            'generated_at': datetime.now().isoformat(),
            'by_weapon': {},
            'by_collection': {},
            'by_rarity': {},
            'by_year': {}
        }

        # Build indexes
        for skin in data.get('skins', []):
            skin_id = skin['id']
            weapon = skin['weapon']
            collection = skin['collection']
            rarity = skin['rarity']

            # Extract year from introduced date
            try:
                # Get last word which should be year
                year = skin['introduced'].split()[-1]
                if year.isdigit():
                    year = int(year)
                else:
                    year = 'Unknown'
            except:
                year = 'Unknown'

            # By weapon
            if weapon not in index['by_weapon']:
                index['by_weapon'][weapon] = []
            index['by_weapon'][weapon].append(skin_id)

            # By collection
            if collection not in index['by_collection']:
                index['by_collection'][collection] = []
            index['by_collection'][collection].append(skin_id)

            # By rarity
            if rarity not in index['by_rarity']:
                index['by_rarity'][rarity] = []
            index['by_rarity'][rarity].append(skin_id)

            # By year
            if year not in index['by_year']:
                index['by_year'][year] = []
            index['by_year'][year].append(skin_id)

        return index

    def calculate_statistics(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate accurate statistics"""
        skins = data.get('skins', [])

        total_weapons = len(set(skin['weapon'] for skin in skins))
        total_collections = len(set(skin['collection'] for skin in skins))
        total_skins = len(skins)
        total_variants = sum(len(skin.get('variants', [])) for skin in skins)

        # Count prices
        prices_count = 0
        for skin in skins:
            for variant in skin.get('variants', []):
                if 'prices' in variant:
                    if 'normal' in variant['prices']:
                        prices_count += 1
                    if 'stattrak' in variant['prices']:
                        prices_count += 1
                # Legacy price fields
                if 'price' in variant and variant['price'].get('usd', 0) > 0:
                    prices_count += 1
                if 'stattrak_price' in variant and variant['stattrak_price'].get('usd', 0) > 0:
                    prices_count += 1

        return {
            'total_skins': total_skins,
            'total_weapons': total_weapons,
            'total_collections': total_collections,
            'total_variants': total_variants,
            'total_prices_available': prices_count,
            'last_calculated': datetime.now().isoformat()
        }

    def clean_database(self) -> None:
        """Main cleanup process"""
        print("🧹 Starting database cleanup...")

        # Load original data
        original_data = self.load_database()

        # Create backup
        self.create_backup(original_data)

        # Extract and save index
        print("📇 Extracting index...")
        index_data = self.extract_index(original_data)
        with open(self.index_path, 'w', encoding='utf-8') as f:
            json.dump(index_data, f, indent=2, ensure_ascii=False)
        print(f"✅ Index saved to {self.index_path}")

        # Clean the main database
        print("🧹 Cleaning skins data...")
        cleaned_data = {
            'version': '2.0',
            'generated_at': datetime.now().isoformat(),
            'data_status': {
                'base_info': 'complete',
                'prices': 'partial',
                'last_cleanup': datetime.now().isoformat()
            },
            'skins': []
        }

        # Clean each skin
        for i, skin in enumerate(original_data.get('skins', []), 1):
            if i % 100 == 0:
                print(
                    f"  Processed {i}/{len(original_data['skins'])} skins...")

            cleaned_skin = self.clean_skin(skin)
            cleaned_data['skins'].append(cleaned_skin)

        # Add accurate statistics
        print("📊 Calculating statistics...")
        cleaned_data['statistics'] = self.calculate_statistics(cleaned_data)

        # Save cleaned database
        print("💾 Saving cleaned database...")
        with open(self.database_path, 'w', encoding='utf-8') as f:
            json.dump(cleaned_data, f, indent=2, ensure_ascii=False)

        # Print summary
        original_size = os.path.getsize(self.backup_path) / (1024 * 1024)  # MB
        new_size = os.path.getsize(self.database_path) / (1024 * 1024)  # MB
        saved_space = original_size - new_size

        print("\n🎉 Cleanup Complete!")
        print(f"📊 Statistics:")
        print(f"  • Total skins: {cleaned_data['statistics']['total_skins']}")
        print(
            f"  • Total weapons: {cleaned_data['statistics']['total_weapons']}")
        print(
            f"  • Total collections: {cleaned_data['statistics']['total_collections']}")
        print(
            f"  • Total variants: {cleaned_data['statistics']['total_variants']}")
        print(
            f"  • Available prices: {cleaned_data['statistics']['total_prices_available']}")
        print(f"📁 File sizes:")
        print(f"  • Original: {original_size:.1f} MB")
        print(f"  • Cleaned: {new_size:.1f} MB")
        print(
            f"  • Saved: {saved_space:.1f} MB ({saved_space/original_size*100:.1f}%)")
        print(f"📂 Files created:")
        print(f"  • Cleaned database: {self.database_path}")
        print(f"  • Index file: {self.index_path}")
        print(f"  • Backup: {self.backup_path}")


if __name__ == "__main__":
    cleanup = DatabaseCleanup()
    cleanup.clean_database()
