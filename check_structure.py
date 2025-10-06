import json

with open('data/skins_database.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Check all unique weapons
weapons = set(skin['weapon'] for skin in data['skins'])
print("All unique weapons in database:")
for weapon in sorted(weapons):
    print(f'- "{weapon}"')

print(f"\nTotal unique weapons: {len(weapons)}")

# Look for potential issues (single word weapons that should be two words)
suspicious_weapons = [w for w in weapons if len(w.split()) == 1 and len(w) < 8]
print(f"\nPotentially problematic single-word weapons:")
for weapon in sorted(suspicious_weapons):
    skins_count = len([s for s in data['skins'] if s['weapon'] == weapon])
    print(f'- "{weapon}" ({skins_count} skins)')

    # Show a few skin names for this weapon
    sample_skins = [s['skin_name']
                    for s in data['skins'] if s['weapon'] == weapon][:3]
    for skin_name in sample_skins:
        print(f'    - {skin_name}')
    print()
