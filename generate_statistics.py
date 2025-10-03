#!/usr/bin/env python3
"""
CS2 Skins Database Statistics Generator
Analyzes the skins database and generates detailed statistics in markdown format
"""

import json
import os
from datetime import datetime
from collections import defaultdict, Counter
from typing import Dict, List, Any, Optional
import sys


def load_database(file_path: str = "data/skins_database.json") -> Dict[str, Any]:
    """Load the skins database from JSON file"""
    if not os.path.exists(file_path):
        print(f"Error: Database file '{file_path}' not found!")
        sys.exit(1)

    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def analyze_database(db: Dict[str, Any]) -> Dict[str, Any]:
    """Perform comprehensive analysis of the database"""
    stats = {
        'general': {},
        'rarities': {},
        'collections': {},
        'weapons': {},
        'wear_conditions': {},
        'prices': {},
        'stattrak': {},
        'availability': {}
    }

    skins = db.get('skins', [])

    # General statistics
    stats['general']['total_skins'] = len(skins)
    stats['general']['database_version'] = db.get('version', 'Unknown')
    stats['general']['generated_at'] = db.get('generated_at', 'Unknown')
    stats['general']['last_price_update'] = db.get(
        'data_status', {}).get('last_price_update', 'Unknown')

    # Initialize counters
    rarity_counts = Counter()
    collection_counts = Counter()
    weapon_counts = Counter()
    wear_counts = Counter()

    # Price statistics
    price_stats = {
        'total_priced_items': 0,
        'items_with_prices': 0,
        'items_without_prices': 0,
        'highest_price': 0.0,
        'highest_priced_skin': '',
        'lowest_price': float('inf'),
        'lowest_priced_skin': '',
        'total_market_value': 0.0,
        'average_price': 0.0,
        'price_ranges': {
            '< $1': 0,
            '$1 - $10': 0,
            '$10 - $50': 0,
            '$50 - $100': 0,
            '$100 - $500': 0,
            '$500 - $1000': 0,
            '> $1000': 0
        }
    }

    # StatTrak statistics
    stattrak_stats = {
        'stattrak_available_skins': 0,
        'stattrak_only_skins': 0,
        'non_stattrak_skins': 0,
        'stattrak_with_prices': 0
    }

    # Availability statistics
    availability_stats = {
        'total_variants': 0,
        'available_variants': 0,
        'unavailable_variants': 0
    }

    # Process each skin
    for skin in skins:
        # Basic counts
        rarity_counts[skin.get('rarity', 'Unknown')] += 1
        collection_counts[skin.get('collection', 'Unknown')] += 1
        weapon_counts[skin.get('weapon', 'Unknown')] += 1

        # Check StatTrak availability
        has_stattrak = False
        has_normal = False

        # Process variants
        variants = skin.get('variants', [])
        for variant in variants:
            availability_stats['total_variants'] += 1

            wear = variant.get('wear', 'Unknown')
            wear_counts[wear] += 1

            # Availability
            if variant.get('available', False):
                availability_stats['available_variants'] += 1
            else:
                availability_stats['unavailable_variants'] += 1

            # StatTrak availability
            if variant.get('stattrak_available', False):
                has_stattrak = True

            # Price analysis
            prices = variant.get('prices', {})

            # Normal prices
            normal_price = prices.get('normal', {}).get('usd', 0)
            if normal_price > 0:
                has_normal = True
                price_stats['items_with_prices'] += 1
                price_stats['total_market_value'] += normal_price

                # Track highest/lowest prices
                if normal_price > price_stats['highest_price']:
                    price_stats['highest_price'] = normal_price
                    price_stats[
                        'highest_priced_skin'] = f"{skin['weapon']} | {skin['skin_name']} ({wear})"

                if normal_price < price_stats['lowest_price'] and normal_price > 0:
                    price_stats['lowest_price'] = normal_price
                    price_stats[
                        'lowest_priced_skin'] = f"{skin['weapon']} | {skin['skin_name']} ({wear})"

                # Price ranges
                if normal_price < 1:
                    price_stats['price_ranges']['< $1'] += 1
                elif normal_price < 10:
                    price_stats['price_ranges']['$1 - $10'] += 1
                elif normal_price < 50:
                    price_stats['price_ranges']['$10 - $50'] += 1
                elif normal_price < 100:
                    price_stats['price_ranges']['$50 - $100'] += 1
                elif normal_price < 500:
                    price_stats['price_ranges']['$100 - $500'] += 1
                elif normal_price < 1000:
                    price_stats['price_ranges']['$500 - $1000'] += 1
                else:
                    price_stats['price_ranges']['> $1000'] += 1
            else:
                price_stats['items_without_prices'] += 1

            # StatTrak prices
            stattrak_price = prices.get('stattrak', {}).get('usd', 0)
            if stattrak_price > 0:
                stattrak_stats['stattrak_with_prices'] += 1

        # StatTrak skin categorization
        if has_stattrak and has_normal:
            stattrak_stats['stattrak_available_skins'] += 1
        elif has_stattrak and not has_normal:
            stattrak_stats['stattrak_only_skins'] += 1
        elif not has_stattrak:
            stattrak_stats['non_stattrak_skins'] += 1

    # Calculate averages
    if price_stats['items_with_prices'] > 0:
        price_stats['average_price'] = price_stats['total_market_value'] / \
            price_stats['items_with_prices']

    # Fix lowest price if no items found
    if price_stats['lowest_price'] == float('inf'):
        price_stats['lowest_price'] = 0.0

    # Store results
    stats['rarities'] = dict(rarity_counts.most_common())
    stats['collections'] = dict(collection_counts.most_common())
    stats['weapons'] = dict(weapon_counts.most_common())
    stats['wear_conditions'] = dict(wear_counts.most_common())
    stats['prices'] = price_stats
    stats['stattrak'] = stattrak_stats
    stats['availability'] = availability_stats

    return stats


def generate_detailed_output(stats: Dict[str, Any]) -> str:
    """Generate detailed console output that can be copied to markdown"""

    output = []

    # Header
    output.append("# CS2 Skins Database Statistics")
    output.append("")
    output.append(
        f"**Generated on:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    output.append(
        f"**Database Version:** {stats['general']['database_version']}")
    output.append(
        f"**Database Generated:** {stats['general']['generated_at']}")
    output.append(
        f"**Last Price Update:** {stats['general']['last_price_update']}")
    output.append("")

    # General Overview - NUMBERS ONLY
    output.append("## General Overview")
    output.append("")
    output.append(f"- **Total Skins:** {stats['general']['total_skins']}")
    output.append(
        f"- **Total Variants:** {stats['availability']['total_variants']}")
    output.append(
        f"- **Available Variants:** {stats['availability']['available_variants']}")
    output.append(
        f"- **Unavailable Variants:** {stats['availability']['unavailable_variants']}")
    output.append("")

    # Rarity Distribution - COMPLETE NUMBERS
    output.append("## Rarity Distribution")
    output.append("")
    output.append("| Rarity | Count |")
    output.append("|--------|-------|")

    for rarity, count in stats['rarities'].items():
        output.append(f"| {rarity} | {count} |")
    output.append("")
    output.append(f"**Total Rarities:** {len(stats['rarities'])}")
    output.append("")

    # Weapon Types - COMPLETE NUMBERS
    output.append("## Weapon Types")
    output.append("")
    output.append("| Weapon | Skins Count |")
    output.append("|--------|-------------|")

    for weapon, count in stats['weapons'].items():
        output.append(f"| {weapon} | {count} |")
    output.append("")
    output.append(f"**Total Weapon Types:** {len(stats['weapons'])}")
    output.append("")

    # Collections - COMPLETE NUMBERS
    output.append("## Collections")
    output.append("")
    output.append("| Collection | Skins Count |")
    output.append("|------------|-------------|")

    for collection, count in stats['collections'].items():
        output.append(f"| {collection} | {count} |")
    output.append("")
    output.append(f"**Total Collections:** {len(stats['collections'])}")
    output.append("")

    # Wear Conditions - COMPLETE NUMBERS
    output.append("## Wear Conditions")
    output.append("")
    output.append("| Wear Condition | Variants Count |")
    output.append("|----------------|----------------|")

    for wear, count in stats['wear_conditions'].items():
        output.append(f"| {wear} | {count} |")
    output.append("")
    output.append(f"**Total Wear Types:** {len(stats['wear_conditions'])}")
    output.append("")

    # Price Analysis - DETAILED NUMBERS
    output.append("## Price Analysis")
    output.append("")

    prices = stats['prices']
    output.append("### Overall Price Statistics")
    output.append("")
    output.append(f"- **Items with Prices:** {prices['items_with_prices']}")
    output.append(
        f"- **Items without Prices:** {prices['items_without_prices']}")
    output.append(f"- **Highest Price:** ${prices['highest_price']:.2f}")
    output.append(
        f"- **Highest Priced Item:** {prices['highest_priced_skin']}")
    output.append(f"- **Lowest Price:** ${prices['lowest_price']:.2f}")
    output.append(f"- **Lowest Priced Item:** {prices['lowest_priced_skin']}")
    output.append(f"- **Average Price:** ${prices['average_price']:.2f}")
    output.append(
        f"- **Total Market Value:** ${prices['total_market_value']:.2f}")
    output.append("")

    output.append("### Price Distribution")
    output.append("")
    output.append("| Price Range | Items Count |")
    output.append("|-------------|-------------|")

    for price_range, count in prices['price_ranges'].items():
        output.append(f"| {price_range} | {count} |")
    output.append("")

    # StatTrak Analysis - DETAILED NUMBERS
    output.append("## StatTrak Analysis")
    output.append("")

    stattrak = stats['stattrak']
    output.append(
        f"- **Skins with StatTrak Available:** {stattrak['stattrak_available_skins']}")
    output.append(
        f"- **StatTrak-Only Skins:** {stattrak['stattrak_only_skins']}")
    output.append(
        f"- **Non-StatTrak Skins:** {stattrak['non_stattrak_skins']}")
    output.append(
        f"- **StatTrak Items with Prices:** {stattrak['stattrak_with_prices']}")
    output.append("")

    # Availability Statistics - DETAILED NUMBERS
    output.append("## Availability Statistics")
    output.append("")

    avail = stats['availability']
    output.append(f"- **Total Variants:** {avail['total_variants']}")
    output.append(f"- **Available Variants:** {avail['available_variants']}")
    output.append(
        f"- **Unavailable Variants:** {avail['unavailable_variants']}")
    output.append("")

    # Additional Detailed Breakdowns
    output.append("## Detailed Breakdowns")
    output.append("")

    # Rarity breakdown with actual numbers
    output.append("### Skins by Rarity (Detailed)")
    output.append("")
    for rarity, count in stats['rarities'].items():
        output.append(f"- **{rarity}:** {count} skins")
    output.append("")

    # Weapon breakdown with actual numbers
    output.append("### Weapons with Most Skins")
    output.append("")
    sorted_weapons = sorted(
        stats['weapons'].items(), key=lambda x: x[1], reverse=True)
    for weapon, count in sorted_weapons:
        output.append(f"- **{weapon}:** {count} skins")
    output.append("")

    # Collection breakdown with actual numbers
    output.append("### Collections with Most Skins")
    output.append("")
    sorted_collections = sorted(
        stats['collections'].items(), key=lambda x: x[1], reverse=True)
    for collection, count in sorted_collections:
        output.append(f"- **{collection}:** {count} skins")
    output.append("")

    # Footer
    output.append("---")
    output.append(
        "*This report was automatically generated by the CS2 Skins Database Statistics Generator*")

    return "\n".join(output)


def main():
    """Main function to generate statistics"""
    print("CS2 Skins Database Statistics Generator")
    print("=" * 50)

    # Load database
    print("Loading database...")
    db = load_database()
    print(f"Loaded database with {len(db.get('skins', []))} skins")

    # Analyze database
    print("Analyzing database...")
    stats = analyze_database(db)

    # Generate detailed output
    print("Generating detailed statistics output...")
    detailed_output = generate_detailed_output(stats)

    # Write to file
    output_file = "statistics.md"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(detailed_output)

    print(f"Statistics report generated: {output_file}")
    print("=" * 80)
    print("DETAILED STATISTICS OUTPUT (Copy this to your MD file):")
    print("=" * 80)
    print()

    # Print the complete detailed output to console
    print(detailed_output)

    print()
    print("=" * 80)
    print("END OF DETAILED STATISTICS")
    print("=" * 80)


if __name__ == "__main__":
    main()
