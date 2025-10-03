"""
Verify that prices were collected successfully
"""

import json


def verify_prices():
    with open('data/skins_database.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Find the AK-47 The Oligarch (first processed skin)
    for skin in data['skins']:
        if 'AK-47 The Oligarch' in skin['full_name']:
            print(f"Skin: {skin['full_name']}")
            print(f"Introduced: {skin['introduced']}")
            print("\nPrice data collected:")

            for variant in skin['variants']:
                wear = variant['wear']
                normal_price = variant['prices']['normal']['usd']
                stattrak_price = variant['prices']['stattrak']['usd']
                last_updated = variant['prices']['normal']['last_updated']

                print(f"  {wear}:")
                print(f"    Normal: ${normal_price}")
                print(f"    StatTrak: ${stattrak_price}")
                print(
                    f"    Updated: {last_updated[:19] if last_updated else 'Never'}")

            break
    else:
        print("Skin not found")

    # Check checkpoint file
    try:
        with open('price_collection_checkpoint.json', 'r', encoding='utf-8') as f:
            checkpoint = json.load(f)

        print("\nCheckpoint status:")
        print(f"  Processed skins: {checkpoint['processed_skins']}")
        print(f"  Last processed: {checkpoint['last_processed_skin_id']}")
        print(
            "  Last update: %s", checkpoint['last_update'][:19] if checkpoint['last_update'] else 'Never')

    except FileNotFoundError:
        print("\nNo checkpoint file found")


if __name__ == "__main__":
    verify_prices()
