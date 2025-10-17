# 🎯 CS2 Skin Data Format Specification

This repository defines the **official JSON structure** for representing CS2 (Counter-Strike 2) skin data.  
The following format ensures consistency across all tools, APIs, and databases that reference skin information.

---

## ✅ Correct JSON Format Example

```json
{
  "id": "awp-lightning-strike",
  "weapon": "AWP",
  "skin_name": "Lightning Strike",
  "rarity": "Covert",
  "rarity_color": "Red",
  "collection": "The Arms Deal Collection",
  "cs2database_link": "https://www.csgodatabase.com/skins/awp-lightning-strike/",
  "csgoskins_url": "https://csgoskins.gg/items/awp-lightning-strike",
  "variants": [
    {
      "wear": "Factory New",
      "image": "",
      "wear_range": {
        "min": 0.0,
        "max": 0.07
      },
      "achievable": true,
      "listing": {
        "normal": false,
        "stattrak": true
      },
      "prices": {
        "normal": {
          "usd": 824.14,
          "last_updated": "2025-10-04T14:09:04.547652"
        },
        "stattrak": {
          "usd": 1515.59,
          "last_updated": "2025-10-04T14:09:05.275373"
        }
      }
    },
    {
      "wear": "Minimal Wear",
      "image": "",
      "wear_range": {
        "min": 0.07,
        "max": 0.15
      },
      "achievable": true,
      "listing": {
        "normal": false,
        "stattrak": false
      },
      "prices": {
        "normal": {
          "usd": 771.57,
          "last_updated": "2025-10-04T14:09:06.523536"
        }
      }
    }
  ]
}
```

| Key                     | Type      | Description                                        |
| ----------------------- | --------- | -------------------------------------------------- |
| `id`                    | `string`  | Unique skin identifier (lowercase, hyphenated).    |
| `weapon`                | `string`  | The weapon associated with the skin.               |
| `skin_name`             | `string`  | The skin's display name.                           |
| `rarity`                | `string`  | The rarity tier (e.g., Covert, Classified).        |
| `rarity_color`          | `string`  | The visual rarity color (e.g., Red, Pink, Purple). |
| `collection`            | `string`  | The in-game collection this skin belongs to.       |
| `cs2database_link`      | `string`  | Reference link to CS2 Database entry.              |
| `csgoskins_url`         | `string`  | Reference link to CS:GO Skins website entry.       |
| `variants`              | `array`   | List of available wear variants.                   |
| `variants[].wear`       | `string`  | Wear level (Factory New, Minimal Wear, etc.).      |
| `variants[].image`      | `string`  | Image URL or local path (can be empty).            |
| `variants[].wear_range` | `object`  | Float range for that wear type.                    |
| `variants[].achievable` | `boolean` | Whether the variant is obtainable in-game.         |
| `variants[].listing`    | `object`  | Market availability (normal / StatTrak).           |
| `variants[].prices`     | `object`  | Pricing information (USD and timestamp).           |
