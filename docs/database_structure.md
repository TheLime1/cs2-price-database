# CS2 Skins Database Structure Guide

## Overview
The CS2 skins database is stored in JSON format and contains comprehensive information about Counter-Strike 2 weapon skins, including their variants, prices, and metadata.

## Database File Location
- **Main Database**: `data/skins_database.json`
- **Backup Files**: `data/skins_database.json.backup_YYYYMMDD_HHMMSS`

## Root Structure

```json
{
  "version": "1.0",
  "generated_at": "2025-10-13T19:10:18.018190",
  "total_skins": 1361,
  "data_status": {
    "base_info": "complete",
    "wear_availability": "assumed_all (needs verification)",
    "stattrak_availability": "assumed_all (needs verification)", 
    "prices": "not_fetched (all set to 0)",
    "last_price_update": "2025-10-05T18:20:52.764828"
  },
  "skins": [...]
}
```

### Root Level Fields

| Field          | Type              | Description                             |
| -------------- | ----------------- | --------------------------------------- |
| `version`      | string            | Database schema version                 |
| `generated_at` | string (ISO 8601) | When the database was initially created |
| `total_skins`  | integer           | Total number of unique skins            |
| `data_status`  | object            | Status of different data categories     |
| `skins`        | array             | Array of skin objects                   |

### Data Status Object

| Field                   | Type              | Description                      |
| ----------------------- | ----------------- | -------------------------------- |
| `base_info`             | string            | Status of basic skin information |
| `wear_availability`     | string            | Status of wear condition data    |
| `stattrak_availability` | string            | Status of StatTrak variant data  |
| `prices`                | string            | Status of price collection       |
| `last_price_update`     | string (ISO 8601) | Timestamp of last price update   |

## Skin Object Structure

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
| -------------- | ------ | ------------------------------------------ |
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

## Variant Object Structure

Each variant represents a different wear condition of the skin:

```json
{
  "wear": "Factory New",
  "wear_short": "FN", 
  "float_range": [0.0, 0.07],
  "available": true,
  "stattrak_available": true,
  "has_normal_listings": true,
  "has_stattrak_listings": true,
  "availability_verified": "2025-10-13T23:38:54.688000",
  "prices": {
    "normal": {
      "usd": 824.14,
      "last_updated": "2025-10-04T14:09:04.547652",
      "raw_data": {
        "success": true,
        "lowest_price": "$824.14"
      },
      "success": true,
      "lowest_price": "$824.14"
    },
    "stattrak": {
      "usd": 1515.59,
      "last_updated": "2025-10-04T14:09:05.275373", 
      "raw_data": {
        "success": true,
        "lowest_price": "$1,515.59"
      }
    }
  }
}
```

### Variant Fields

| Field                   | Type              | Description                                      |
| ----------------------- | ----------------- | ------------------------------------------------ |
| `wear`                  | string            | Full wear condition name                         |
| `wear_short`            | string            | Abbreviated wear condition                       |
| `float_range`           | array             | [min, max] float values                          |
| `available`             | boolean           | Whether variant exists on marketplace            |
| `stattrak_available`    | boolean           | Whether StatTrak version exists                  |
| `has_normal_listings`   | boolean           | Whether normal variant has active listings       |
| `has_stattrak_listings` | boolean           | Whether StatTrak variant has active listings     |
| `availability_verified` | string (ISO 8601) | When availability was last verified via scraping |
| `prices`                | object            | Price information for normal and StatTrak        |

## Price Object Structure

Price objects contain current market data:

```json
{
  "usd": 824.14,
  "last_updated": "2025-10-04T14:09:04.547652",
  "raw_data": {
    "success": true,
    "lowest_price": "$824.14",
    "median_price": "$850.00",
    "volume": "42",
    "source": "steam_api"
  },
  "success": true,
  "lowest_price": "$824.14"
}
```

### Price Fields

| Field          | Type              | Description                        |
| -------------- | ----------------- | ---------------------------------- |
| `usd`          | float             | Price in USD                       |
| `last_updated` | string (ISO 8601) | When price was last fetched        |
| `raw_data`     | object            | Raw API response data              |
| `success`      | boolean           | Whether price fetch was successful |
| `lowest_price` | string            | Formatted price string             |

### Raw Data Fields

| Field          | Type    | Description                                   |
| -------------- | ------- | --------------------------------------------- |
| `success`      | boolean | API request success status                    |
| `lowest_price` | string  | Lowest market price                           |
| `median_price` | string  | Median market price (optional)                |
| `volume`       | string  | Trading volume (optional)                     |
| `source`       | string  | Data source ("steam_api", "fallback_scraper") |

## Availability Detection System

### Enhanced Fallback Mechanism

The database now includes comprehensive availability detection powered by the fallback scraper system. This system analyzes actual marketplace data to determine:

#### Availability Fields

- **`available`**: Indicates if the wear condition exists for the weapon (e.g., some weapons don't have Factory New condition)
- **`stattrak_available`**: Indicates if StatTrak variant exists for that wear condition
- **`has_normal_listings`**: Whether there are active marketplace listings for the normal variant
- **`has_stattrak_listings`**: Whether there are active marketplace listings for the StatTrak variant
- **`availability_verified`**: Timestamp when availability was last verified through scraping

#### Detection Process

1. **Scraping Analysis**: The fallback scraper examines the marketplace page structure
2. **Column Detection**: Identifies which wear conditions and StatTrak variants have columns in the price table
3. **Listing Verification**: Checks if actual prices exist (indicating active listings)
4. **Availability Mapping**: Maps findings to boolean availability flags

#### Examples

**UMP-45 Grand Prix** (Limited availability):
```json
{
  "wear": "Factory New",
  "available": false,
  "stattrak_available": false,
  "has_normal_listings": false,
  "has_stattrak_listings": false
}
```

**AK-47 The Oligarch** (Missing StatTrak Factory New):
```json
{
  "wear": "Factory New", 
  "available": true,
  "stattrak_available": false,
  "has_normal_listings": true,
  "has_stattrak_listings": false
}
```

### Proxy Management & Reliability

The system implements advanced proxy retry mechanisms to ensure no weapons are skipped due to network issues:

- **Multiple Retry Attempts**: Up to 3 attempts per weapon with different proxy connections
- **Automatic Proxy Rotation**: Switches to different proxies on failure
- **Rate Limiting**: Prevents overwhelming target servers
- **Comprehensive Error Handling**: Logs detailed failure information for troubleshooting

## Wear Conditions

Standard CS2 wear conditions in order from best to worst:

1. **Factory New (FN)** - Float: 0.00 - 0.07
2. **Minimal Wear (MW)** - Float: 0.07 - 0.15  
3. **Field-Tested (FT)** - Float: 0.15 - 0.38
4. **Well-Worn (WW)** - Float: 0.38 - 0.45
5. **Battle-Scarred (BS)** - Float: 0.45 - 1.00

## Rarity Tiers

CS2 skin rarities from most common to rarest:

1. **Consumer Grade** (White) - 79.92%
2. **Industrial Grade** (Light Blue) - 15.98% 
3. **Mil-Spec** (Blue) - 3.2%
4. **Restricted** (Purple) - 0.64%
5. **Classified** (Pink) - 0.2% 
6. **Covert** (Red) - 0.04%
7. **Special Items** (Gold/Yellow) - 0.02%

## Market Hash Names

Market hash names are used for Steam Market API calls:

- **Normal**: `{weapon} | {skin_name} ({wear_condition})`
- **StatTrak**: `StatTrak™ {weapon} | {skin_name} ({wear_condition})`

### Examples:
- `"AK-47 | Redline (Field-Tested)"`
- `"StatTrak™ AWP | Lightning Strike (Factory New)"`

## Invalid Variants

Some variants may be marked as invalid during cleanup:

- Variants that return `"success": true` but no price data
- Items that exist in API but aren't tradeable/marketable
- Region-restricted or discontinued items

These are automatically removed during database cleanup.

## File Size and Performance

- **Current Size**: ~15-25 MB (compressed)
- **Total Records**: 1,361 skins × ~5 variants = ~6,805 price entries
- **Expected Growth**: Minimal (new skins added infrequently)

## Backup Strategy

- Automatic backups created before cleanup operations
- Timestamped backup files: `skins_database.json.backup_20251013_143022`
- Manual backups recommended before major updates

## Data Validation

The system validates:
- JSON structure integrity
- Required field presence
- Price data format and ranges  
- Date format consistency
- Skin-variant relationships

## API Rate Considerations

- Each price update requires 2 API calls (normal + StatTrak)
- Total API calls for full update: ~13,610 requests
- Estimated time at 20 calls/minute: ~11.3 hours
- Use `--ignore-stattrak` to halve the time: ~5.7 hours