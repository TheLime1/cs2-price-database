# CS2 Price Database V3.0 Migration Plan

## 🎯 V3.0 Goals

1. **Remove ALL proxy-related code** - Simplify architecture
2. **WebDriver-only scraping** - No more Steam API dependencies
3. **Add wear range validation** - Integration with csgoskins.gg
4. **Database schema update** - Cleaner, more accurate data structure

---

## 📊 Database Analysis Results

- **Total skins**: 1,361
- **Total variants**: 6,790
- **Variants with prices**: 6,790 (100%)
- **Redundant fields identified**: 5 (3 top-level + 2 per-variant)

---

## 🗑️ Code To Remove

### Files to Delete
- [x] `proxy_manager.py` - **DELETED**

### Files to Clean
1. **collect_prices.py**
   - Remove `--noproxy` flag
   - Remove proxy URL configuration
   - Remove proxy-related logging setup
   - Remove Steam API fallback logic

2. **high_speed_scraper.py**
   - Remove ProxyManager import and usage
   - Remove all proxy worker logic
   - Remove proxy health check loops
   - Keep only WebDriver pool logic
   - Remove Steam API client usage

3. **steam_api.py**
   - **DELETE ENTIRE FILE** (no longer needed)

4. **summary_logger.py**
   - Remove `proxy_failures` field
   - Remove `log_proxy_failure()` method
   - Remove proxy statistics

5. **optimized_fallback_scraper.py**
   - Remove proxy parameter from WebDriverPool
   - Simplify to direct connections only

6. **.env.example**
   - Remove all PROXY_* variables (22+ lines)

---

## ➕ New Features to Add

### 1. csgoskins.gg Integration

**New File**: `csgoskins_scraper.py`

```python
class CSGOSkinsGGScraper:
    """
    Scrapes wear range and achievability data from csgoskins.gg
    
    Example URL: https://csgoskins.gg/items/awp-asiimov/
    
    Extracts:
    - Overall wear range (min/max float)
    - Per-wear achievability (is wear possible?)
    - Per-wear float ranges
    """
```

### 2. Database Schema V3.0

**Changes to `skins_database.json`**:

#### Top-Level Skin Fields
```json
{
  "wear_range": {
    "min": 0.18,
    "max": 1.0
  }
}
```

**REMOVE**:
- `availability` (redundant)
- `stattrak_availability` (redundant)

#### Per-Variant Fields
```json
{
  "wear": "Field-Tested",
  "wear_short": "FT",
  "achievable": true,
  "wear_float_range": {
    "min": 0.18,
    "max": 0.50
  },
  "listing": {
    "normal": true,
    "stattrak": true
  }
}
```

**REMOVE**:
- `available` → **RENAME** to `listing`
- `has_normal_listings` → **CONSOLIDATE** into `listing.normal`
- `has_stattrak_listings` → **CONSOLIDATE** into `listing.stattrak`

---

## 🔧 Implementation Steps

### Phase 1: Code Cleanup ✅
1. [x] Delete `proxy_manager.py`
2. [ ] Remove proxy code from `collect_prices.py`
3. [ ] Remove proxy code from `high_speed_scraper.py`
4. [ ] Delete `steam_api.py`
5. [ ] Clean `summary_logger.py`
6. [ ] Clean `optimized_fallback_scraper.py`
7. [ ] Update `.env.example`

### Phase 2: New Features
1. [ ] Create `csgoskins_scraper.py`
2. [ ] Create `migrate_database_v3.py` (migration script)
3. [ ] Update `collect_prices.py` for V3.0 logic
4. [ ] Update `high_speed_scraper.py` for WebDriver-only

### Phase 3: Documentation
1. [ ] Update `README.md`
2. [ ] Update all .md files in `docs/`
3. [ ] Create `V3_CHANGELOG.md`
4. [ ] Update `requirements.txt`

---

## 🚀 V3.0 Architecture

### Worker System (Simplified)
```
┌─────────────────────────────────────┐
│     Price Collection System V3.0    │
└─────────────────────────────────────┘
                 │
                 ├─> WebDriver Pool (10-15 instances)
                 │   └─> csgodatabase.com scraping
                 │
                 └─> csgoskins.gg validation
                     └─> Wear range + achievability
```

### Data Flow
```
1. Load skins from database
2. For each skin:
   a. Check csgoskins.gg for wear ranges
   b. Update achievability flags
   c. Use WebDriver to scrape prices from csgodatabase
   d. Update listing status
3. Save to database with V3.0 schema
```

---

## 📝 Command Line Changes

### V2.0 (OLD)
```bash
python collect_prices.py --missing-only --limit 5 --noproxy
python collect_prices.py --fallback-only
```

### V3.0 (NEW)
```bash
python collect_prices.py --missing-only --limit 5
python collect_prices.py --validate-wear-ranges
python collect_prices.py --refresh-achievability
```

**Removed Flags**:
- `--noproxy` (proxies removed entirely)
- `--fallback-only` (WebDriver is now the only method)

**New Flags**:
- `--validate-wear-ranges` - Fetch/update wear ranges from csgoskins.gg
- `--refresh-achievability` - Re-check which wears are achievable

---

## 🎨 Example: AWP Asiimov Migration

### Before (V2.0)
```json
{
  "id": "awp-asiimov",
  "weapon": "AWP",
  "skin_name": "Asiimov",
  "availability": {
    "Factory New": false,
    "Minimal Wear": false,
    "Field-Tested": true,
    "Well-Worn": true,
    "Battle-Scarred": true
  },
  "stattrak_availability": {
    "Factory New": false,
    "Minimal Wear": false,
    "Field-Tested": true,
    "Well-Worn": true,
    "Battle-Scarred": true
  },
  "variants": [
    {
      "wear": "Factory New",
      "available": false,
      "has_normal_listings": false,
      "has_stattrak_listings": false
    },
    {
      "wear": "Field-Tested",
      "available": true,
      "has_normal_listings": true,
      "has_stattrak_listings": true,
      "float_range": [0.2, 0.5]
    }
  ]
}
```

### After (V3.0)
```json
{
  "id": "awp-asiimov",
  "weapon": "AWP",
  "skin_name": "Asiimov",
  "wear_range": {
    "min": 0.18,
    "max": 1.0
  },
  "variants": [
    {
      "wear": "Factory New",
      "achievable": false,
      "wear_float_range": null,
      "listing": {
        "normal": false,
        "stattrak": false
      }
    },
    {
      "wear": "Field-Tested",
      "achievable": true,
      "wear_float_range": {
        "min": 0.18,
        "max": 0.50
      },
      "listing": {
        "normal": true,
        "stattrak": true
      }
    }
  ]
}
```

---

## 📦 Dependencies Update

### Remove
- `aiohttp` (no more Steam API calls)
- `python-dotenv` proxy config entries

### Keep
- `selenium`
- `webdriver-manager`
- `beautifulsoup4`
- `lxml`

### Add
- None (using existing selenium stack)

---

## ✅ Testing Checklist

- [ ] Database migration runs without errors
- [ ] All 1,361 skins migrated correctly
- [ ] WebDriver pool functions without proxies
- [ ] csgoskins.gg scraper works
- [ ] Price collection still works
- [ ] No proxy references in code
- [ ] Documentation updated
- [ ] Example runs complete successfully

---

## 🎉 V3.0 Benefits

1. **Simpler Architecture** - No proxy management complexity
2. **More Reliable** - Direct WebDriver connections
3. **Better Data** - Wear range validation
4. **Cleaner Database** - Removed redundant fields
5. **Easier Maintenance** - Less code to maintain
6. **More Accurate** - Achievability confirmation

---

**Created**: 2025-10-17
**Version**: 3.0.0
**Status**: IN PROGRESS 🚧
