# CS2 Skins Database Structure Guide - V3.0

## Overview

The CS2 skins database V3.0 is stored in JSON format and contains comprehensive information about Counter-Strike 2 weapon skins, including their variants, prices, wear ranges, and achievability data.

## V3.0 Changes

**What's New:**

- ✅ **`wear_range`**: Actual min/max float values for each wear condition
- ✅ **`achievable`**: Boolean flag indicating if a wear condition is obtainable
- ✅ **`listing`**: New structure replacing `available` with `{normal, stattrak}` format
- ❌ **Removed**: `availability` and `stattrak_availability` arrays (top-level)
- ❌ **Removed**: `available` field (variant-level, replaced by `listing`)

## Database File Location

- **Main Database**: `data/skins_database.json`
- **Backup Files**: `backups/skins_database_v2_backup_YYYYMMDD_HHMMSS.json`

## Root Structure

```json
{
  "version": "3.0",
  "migrated_at": "2025-10-17T12:00:00.000000",
  "migration_notes": "Migrated from V2.0 to V3.0 schema",
  "last_updated": "2025-10-17T12:30:00.000000",
  "skins": [...]
}
```

### Root Level Fields

| Field              | Type              | Description                             |
|--------------------|-------------------|-----------------------------------------|
| `version`          | string            | Database schema version (3.0)           |
| `migrated_at`      | string (ISO 8601) | When database was migrated to V3.0      |
| `migration_notes`  | string            | Migration details                       |
| `last_updated`     | string (ISO 8601) | Last price collection update            |
| `skins`            | array             | Array of skin objects                   |

## Skin Object Structure (V3.0)

Each skin in the `skins` array has the following structure:

```json
{
  "id": "awp-lightning-strike",
  "weapon": "AWP",
  "skin_name": "Lightning Strike", 
  "full_name": "AWP Lightning Strike",
  "rarity": "Covert",
  "rarity_color": "Red",
  "collection": "The Arms Deal Collection",
  "introduced": "14 August 2013",
  "detail_url": "https://www.csgodatabase.com/skins/awp-lightning-strike/",
  "variants": [...]
}
```

### Skin Fields

| Field          | Type   | Description                                |
|----------------|--------|--------------------------------------------|
| `id`           | string | Unique identifier (kebab-case)             |
| `weapon`       | string | Weapon name (e.g., "AK-47", "AWP")         |
| `skin_name`    | string | Skin pattern name                          |
| `full_name`    | string | Complete skin name                         |
| `rarity`       | string | Rarity tier (e.g., "Covert", "Classified") |
| `rarity_color` | string | Color associated with rarity               |
| `collection`   | string | Skin collection name                       |
| `introduced`   | string | Release date                               |
| `detail_url`   | string | URL to detailed skin information           |
| `variants`     | array  | Array of wear condition variants           |

**Removed in V3.0:**

- ❌ `availability` - Array of available wear conditions
- ❌ `stattrak_availability` - Array of StatTrak-available wear conditions

## Variant Object Structure (V3.0)

Each variant represents a different wear condition of the skin:

```json
{
  "wear": "Factory New",
  "image": "https://...image_url...",
  "wear_range": {
    "min": 0.00,
    "max": 0.07
  },
  "achievable": true,
  "listing": {
    "normal": true,
    "stattrak": true
  },
  "prices": {
    "normal": {
      "usd": 824.14,
      "last_updated": "2025-10-17T14:09:04.547652"
    },
    "stattrak": {
      "usd": 1250.50,
      "last_updated": "2025-10-17T14:09:05.123456"
    }
  },
  "has_normal_listings": true,
  "has_stattrak_listings": true
}
```

### Variant Fields

| Field                   | Type              | Description                                |
|-------------------------|-------------------|--------------------------------------------|
| `wear`                  | string            | Wear condition name                        |
| `image`                 | string            | URL to skin image                          |
| `wear_range` ✨         | object            | Min/max float values for this condition    |
| `achievable` ✨         | boolean           | Whether this wear is obtainable            |
| `listing` ✨            | object            | Listing availability structure             |
| `prices`                | object            | Price data for normal and StatTrak         |
| `has_normal_listings`   | boolean           | True if normal variant has active listings |
| `has_stattrak_listings` | boolean           | True if StatTrak variant has listings      |

**New in V3.0:**

- ✨ `wear_range`: Actual float range from csgoskins.gg or defaults
- ✨ `achievable`: Indicates if wear condition is possible for this skin
- ✨ `listing`: Replaces `available` with structured format

**Removed in V3.0:**

- ❌ `available` - Replaced by `listing.normal`
- ❌ `stattrak_available` - Replaced by `listing.stattrak`
- ❌ `float_range` - Replaced by `wear_range`
- ❌ `wear_short` - Not needed in V3.0

### Wear Range Object (V3.0) ✨

```json
{
  "min": 0.00,
  "max": 0.07
}
```

| Field | Type  | Description                              |
|-------|-------|------------------------------------------|
| `min` | float | Minimum float value for this condition   |
| `max` | float | Maximum float value for this condition   |

**Standard CS2 Wear Ranges:**

| Wear Condition   | Min Float | Max Float |
|------------------|-----------|-----------|
| Factory New      | 0.00      | 0.07      |
| Minimal Wear     | 0.07      | 0.15      |
| Field-Tested     | 0.15      | 0.38      |
| Well-Worn        | 0.38      | 0.45      |
| Battle-Scarred   | 0.45      | 1.00      |

**Note**: Some skins have restricted ranges (e.g., AWP Asiimov is only FT, WW, BS).

### Listing Object (V3.0) ✨

```json
{
  "normal": true,
  "stattrak": false
}
```

| Field      | Type    | Description                              |
|------------|---------|------------------------------------------|
| `normal`   | boolean | Normal variant available on market       |
| `stattrak` | boolean | StatTrak variant available on market     |

### Prices Object

```json
{
  "normal": {
    "usd": 824.14,
    "last_updated": "2025-10-17T14:09:04.547652"
  },
  "stattrak": {
    "usd": 1250.50,
    "last_updated": "2025-10-17T14:09:05.123456"
  }
}
```

| Field          | Type              | Description                    |
|----------------|-------------------|--------------------------------|
| `normal`       | object            | Normal variant price data      |
| `stattrak`     | object            | StatTrak variant price data    |
| `usd`          | float             | Price in USD                   |
| `last_updated` | string (ISO 8601) | When price was last collected  |

## Complete Example (V3.0)

```json
{
  "version": "3.0",
  "migrated_at": "2025-10-17T12:00:00.000000",
  "last_updated": "2025-10-17T14:30:00.000000",
  "skins": [
    {
      "id": "ak-47-redline",
      "weapon": "AK-47",
      "skin_name": "Redline",
      "full_name": "AK-47 Redline",
      "rarity": "Classified",
      "rarity_color": "Pink",
      "collection": "The Phoenix Collection",
      "introduced": "20 February 2014",
      "detail_url": "https://www.csgodatabase.com/skins/ak-47-redline/",
      "variants": [
        {
          "wear": "Factory New",
          "image": "https://...image_url...",
          "wear_range": {
            "min": 0.10,
            "max": 0.15
          },
          "achievable": true,
          "listing": {
            "normal": true,
            "stattrak": true
          },
          "prices": {
            "normal": {
              "usd": 124.50,
              "last_updated": "2025-10-17T14:09:04.547652"
            },
            "stattrak": {
              "usd": 285.75,
              "last_updated": "2025-10-17T14:09:05.123456"
            }
          },
          "has_normal_listings": true,
          "has_stattrak_listings": true
        },
        {
          "wear": "Minimal Wear",
          "image": "https://...image_url...",
          "wear_range": {
            "min": 0.10,
            "max": 0.26
          },
          "achievable": true,
          "listing": {
            "normal": true,
            "stattrak": true
          },
          "prices": {
            "normal": {
              "usd": 18.25,
              "last_updated": "2025-10-17T14:10:15.234567"
            },
            "stattrak": {
              "usd": 45.80,
              "last_updated": "2025-10-17T14:10:16.345678"
            }
          },
          "has_normal_listings": true,
          "has_stattrak_listings": true
        }
      ]
    }
  ]
}
```

## Migration from V2.0 to V3.0

### Automatic Migration

Use the migration script to automatically convert your database:

```bash
# Basic migration with default wear ranges
python migrate_database_v3.py

# Scrape actual wear ranges (recommended)
python migrate_database_v3.py --scrape-wear-ranges

# Preview changes first
python migrate_database_v3.py --dry-run
```

### Manual Migration

If you need to manually migrate, here are the transformations:

**1. Add wear_range to each variant:**

```python
variant['wear_range'] = {
    'min': 0.00,  # From csgoskins.gg or defaults
    'max': 0.07
}
```

**2. Add achievable field:**

```python
variant['achievable'] = True  # From csgoskins.gg or assume True
```

**3. Transform available → listing:**

```python
variant['listing'] = {
    'normal': variant.get('available', False),
    'stattrak': variant.get('stattrak_available', False)
}
del variant['available']
del variant['stattrak_available']
```

**4. Remove top-level arrays:**

```python
del skin['availability']
del skin['stattrak_availability']
```

## Data Sources (V3.0)

- **Price Data**: csgodatabase.com (WebDriver scraping)
- **Wear Ranges**: csgoskins.gg (WebDriver scraping)
- **Achievability**: csgoskins.gg (wear range validation)
- **Base Information**: csgodatabase.com

## Validation

### Required Fields

Every skin must have:

- ✅ `id`, `weapon`, `skin_name`, `full_name`
- ✅ `detail_url`
- ✅ `variants` array (at least one)

Every variant must have:

- ✅ `wear`
- ✅ `wear_range` with `min` and `max`
- ✅ `achievable` boolean
- ✅ `listing` with `normal` and `stattrak`
- ✅ `prices` object

### Data Integrity

- Float values in `wear_range` must be between 0.0 and 1.0
- `min` must be less than `max` in `wear_range`
- Prices must be non-negative numbers
- Timestamps must be valid ISO 8601 format

## Performance Considerations

### File Size

- **V2.0**: ~8-10 MB (1,361 skins)
- **V3.0**: ~9-11 MB (added wear_range data)

### Loading Time

- Python `json.load()`: ~0.5-1.0 seconds
- Recommended: Load once at startup, keep in memory

### Backup Strategy

- Automatic backups before migration
- Recommended: Daily backups during active collection
- Keep at least 7 days of backups

## Common Queries

### Find all skins for a weapon

```python
ak47_skins = [s for s in data['skins'] if s['weapon'] == 'AK-47']
```

### Find achievable wear conditions for a skin

```python
achievable_wears = [
    v['wear'] for v in skin['variants']
    if v['achievable']
]
```

### Find skins with StatTrak listings

```python
stattrak_skins = [
    s for s in data['skins']
    if any(v['listing']['stattrak'] for v in s['variants'])
]
```

### Get wear range for specific condition

```python
fn_variant = next(v for v in skin['variants'] if v['wear'] == 'Factory New')
min_float = fn_variant['wear_range']['min']
max_float = fn_variant['wear_range']['max']
```

## See Also

- [Command Line Flags](command_line_flags.md) - Collection options
- [README.md](../README.md) - Main documentation
- Migration script: `migrate_database_v3.py`
