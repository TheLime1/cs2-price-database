# 🔄 Integrated Workflow: Price Collection + Wear Range Validation

## Overview
The CS2 Price Database now uses an **integrated dual-source scraping approach** that combines:
1. **csgodatabase.com** - For accurate Steam market prices
2. **csgoskins.gg** - For accurate wear range validation

## How It Works

### Workflow Steps

When you run `python collect_prices.py`, each skin goes through this process:

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Load Skin from Database                                  │
│    - ID: awp-lightning-strike                               │
│    - csgodatabase_link: https://csgodatabase.com/...        │
│    - csgoskins_url: https://csgoskins.gg/...                │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Visit csgodatabase.com (Step 1/2)                        │
│    ✅ Extract Steam prices for all wear conditions          │
│    - Factory New: $925.00                                   │
│    - StatTrak Factory New: $961.60                          │
│    - Minimal Wear: No Listings                              │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Update Database with Prices                              │
│    💾 Save prices to skins_database.json                    │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Visit csgoskins.gg (Step 2/2)                            │
│    ✅ Extract total wear range                              │
│    - Method 1: Parse "ranges from 0.00 to 0.08"            │
│    - Method 2: Extract from visual indicator                │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. Update Database with Wear Range                          │
│    💾 Add total_wear_range: {min: 0.0, max: 0.08}          │
└─────────────────────────────────────────────────────────────┘
```

### Result in Database

```json
{
  "id": "awp-lightning-strike",
  "weapon": "AWP",
  "skin_name": "Lightning Strike",
  "variants": [
    {
      "wear": "Factory New",
      "wear_range": { "min": 0.0, "max": 0.07 },
      "prices": {
        "normal": {
          "usd": 925.0,
          "last_updated": "2025-10-17T20:54:34"
        }
      }
    },
    {
      "wear": "Minimal Wear",
      "wear_range": { "min": 0.07, "max": 0.15 },
      "prices": {
        "normal": {
          "usd": null,
          "last_updated": "2025-10-17T20:54:35"
        }
      }
    }
  ],
  "total_wear_range": {
    "min": 0.0,
    "max": 0.08
  }
}
```

## Key Features

### 1. **Automatic Fallback**
If csgoskins.gg scraping fails, the system automatically calculates wear range from achievable variants:
```python
# Fallback logic
if not wear_range_from_csgoskins:
    # Calculate from achievable variants only
    total_wear_range = calculate_from_variants(achievable_only=True)
```

### 2. **Rate Limiting**
The system respects rate limits between requests:
- 1-3 seconds between requests to csgodatabase.com
- 1-3 seconds between requests to csgoskins.gg
- Jittered delays to avoid detection

### 3. **Wear Range Accuracy**
- **Old approach**: Combined all variant ranges (0.0 - 0.15)
- **New approach**: Gets actual achievable range (0.0 - 0.08) ✅

### 4. **Two Extraction Methods**
The scraper tries multiple methods to extract wear range:

**Method 1**: Parse description text
```
"The float value of the AWP | Lightning Strike ranges from 0.00 to 0.08"
```

**Method 2**: Extract from visual indicator
```html
<h2>Wear Range</h2>
<div>0.00 → 0.08</div>
```

## Usage Examples

### Basic Usage
```bash
# Process one skin (for testing)
python collect_prices.py --limit 1

# Process all skins with missing prices
python collect_prices.py --missing-only

# Full database update
python collect_prices.py
```

### Debug Mode
```bash
# See detailed logs of both scraping steps
python collect_prices.py --limit 1 --debug
```

Expected output:
```
🌐 [1/2] Navigating to csgodatabase: https://...
✅ [1/2] Scraped 2 prices for awp-lightning-strike
🌐 [2/2] Navigating to csgoskins: https://...
📊 Found total wear range: 0.0 - 0.08
✅ [2/2] Updated wear range for awp-lightning-strike: 0.0 - 0.08
```

## Benefits

### ✅ Accurate Prices
Steam market prices from csgodatabase.com are the most reliable source

### ✅ Accurate Wear Ranges
csgoskins.gg provides the actual achievable float range, not theoretical ranges

### ✅ Complete Data
Single run collects both price data AND wear range validation

### ✅ Efficient
Uses same WebDriver instance to visit both sites (no extra browser spawning)

## Technical Details

### Modified Files
1. **high_speed_scraper.py**
   - Added `_extract_total_wear_range_from_csgoskins()` method
   - Added `_update_total_wear_range_from_scrape()` method
   - Modified `_scrape_all_variants_with_webdriver()` to visit both sites
   - Added `csgoskins_url` field to `SkinItem` dataclass

2. **collect_prices.py**
   - Updated to pass `csgoskins_url` when creating `SkinItem` objects

### Data Flow
```
Database → SkinItem → WebDriver → csgodatabase.com → Prices → Database
                  ↓                                              ↑
                  → WebDriver → csgoskins.gg → Wear Range ──────┘
```

## Troubleshooting

### Issue: "No csgoskins URL for skin"
**Solution**: Some skins may not have `csgoskins_url` in database. System will fallback to calculating from variants.

### Issue: Wear range extraction fails
**Solution**: System automatically falls back to calculating from achievable variants. Check logs for details.

### Issue: Slow performance
**Solution**: This is expected - visiting 2 sites per skin takes ~2x time. Consider using `--limit` for testing.

## Future Enhancements

- [ ] Cache wear ranges (only update prices on subsequent runs)
- [ ] Parallel scraping of both sites using separate workers
- [ ] Validate variant achievability flags from csgoskins.gg
- [ ] Extract pattern variants information
