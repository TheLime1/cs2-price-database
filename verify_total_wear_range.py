"""
Verification script to check total_wear_range calculation
"""

import json


def verify_total_wear_ranges():
    """Check which skins have total_wear_range and verify calculations"""

    with open('data/skins_database.json', 'r', encoding='utf-8') as f:
        database = json.load(f)

    skins_with_total = []
    skins_without_total = []

    for skin in database['skins'][:10]:  # Check first 10 skins
        skin_id = skin['id']
        has_total = 'total_wear_range' in skin

        if has_total:
            total_range = skin['total_wear_range']

            # Verify calculation
            min_wear = float('inf')
            max_wear = float('-inf')

            for variant in skin.get('variants', []):
                wear_range = variant.get('wear_range', {})
                if 'min' in wear_range and 'max' in wear_range:
                    min_wear = min(min_wear, wear_range['min'])
                    max_wear = max(max_wear, wear_range['max'])

            is_correct = (
                total_range['min'] == min_wear and
                total_range['max'] == max_wear
            )

            skins_with_total.append({
                'id': skin_id,
                'total_range': total_range,
                'num_variants': len(skin.get('variants', [])),
                'correct': is_correct
            })
        else:
            skins_without_total.append(skin_id)

    print("=" * 80)
    print("TOTAL WEAR RANGE VERIFICATION")
    print("=" * 80)

    print(f"\n✅ Skins WITH total_wear_range: {len(skins_with_total)}")
    for item in skins_with_total:
        status = "✅ CORRECT" if item['correct'] else "❌ INCORRECT"
        print(
            f"  {status} {item['id']}: {item['total_range']['min']:.2f} - {item['total_range']['max']:.2f} ({item['num_variants']} variants)")

    print(f"\n⚠️  Skins WITHOUT total_wear_range: {len(skins_without_total)}")
    for skin_id in skins_without_total[:5]:  # Show first 5
        print(f"  - {skin_id}")

    if len(skins_without_total) > 5:
        print(f"  ... and {len(skins_without_total) - 5} more")

    print("\n" + "=" * 80)
    print(f"Total checked: {len(skins_with_total) + len(skins_without_total)}")
    print("=" * 80)


if __name__ == "__main__":
    verify_total_wear_ranges()
