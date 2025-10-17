# CS2 Price Database V3.0# CS2 Price Database V3.0



A high-performance Python application for collecting and tracking Steam Community Market prices for Counter-Strike 2 skins. Uses WebDriver-based scraping with intelligent worker stealing architecture for optimal performance.A high-performance Python application for collecting and tracking Steam Community Market prices for Counter-Strike 2 skins. Uses WebDriver-based scraping with intelligent worker stealing architecture for optimal performance.



## 🚀 Features## 🚀 Features



### V3.0 - WebDriver-Only Architecture### V3.0 - WebDriver-Only Architecture

- ✅ **WebDriver-Only**: Pure Selenium scraping, no proxies or API keys needed

- ✅ **WebDriver-Only**: Pure Selenium scraping, no proxies or API keys needed- ✅ **Dual Source Integration**: 

- ✅ **Dual Source Integration**:  - Primary: csgodatabase.com for prices and market data

  - Primary: csgodatabase.com for prices and market data  - Secondary: csgoskins.gg for wear range validation

  - Secondary: csgoskins.gg for wear range validation- ✅ **Smart Worker Stealing**: Multi-worker architecture with dynamic task stealing

- ✅ **Smart Worker Stealing**: Multi-worker architecture with dynamic task stealing- ✅ **Wear Range Validation**: Accurate float ranges and achievability detection

- ✅ **Wear Range Validation**: Accurate float ranges and achievability detection- ✅ **Enhanced Schema**: Complete wear ranges, StatTrak availability, price history

- ✅ **Enhanced Schema**: Complete wear ranges, StatTrak availability, price history- ✅ **Production Ready**: Comprehensive error handling, checkpointing, and logging

- ✅ **Production Ready**: Comprehensive error handling, checkpointing, and logging

## Database Statistics

## 📊 Database Statistics

The CS2 skins database contains:

The CS2 skins database contains:

- **1,361 total skins** across **36 unique weapons**

- **1,361 total skins** across **36 unique weapons**- **6,805 variants** (different wear conditions per skin)

- **6,805 variants** (different wear conditions per skin)- Data sources: csgodatabase.com + csgoskins.gg

- Data sources: csgodatabase.com + csgoskins.gg

### Top 10 Weapons by Skin Count

### Top 10 Weapons by Skin Count

1. **AK-47**: 56 skins

1. **AK-47**: 56 skins2. **P250**: 55 skins  

2. **P250**: 55 skins3. **MAC-10**: 54 skins

3. **MAC-10**: 54 skins4. **Glock-18**: 51 skins

4. **Glock-18**: 51 skins5. **P90**: 50 skins

5. **P90**: 50 skins6. **M4A4**: 48 skins

6. **M4A4**: 48 skins7. **AWP**: 47 skins

7. **AWP**: 47 skins8. **Tec-9**: 45 skins

8. **Tec-9**: 45 skins9. **Nova**: 44 skins

9. **Nova**: 44 skins10. **M4A1-S**: 43 skins

10. **M4A1-S**: 43 skins

## Files

## 🗂️ Project Structure

- `high_speed_scraper.py` - V3.0 WebDriver-only worker stealing scraper

### Core Scripts- `collect_prices.py` - Main price collection system with checkpoint support

- `csgoskins_scraper.py` - Wear range scraper for csgoskins.gg integration

- `collect_prices.py` - Main price collection system with checkpoint support- `migrate_database_v3.py` - Database migration script from V2.0 to V3.0

- `high_speed_scraper.py` - V3.0 WebDriver-only worker stealing scraper- `optimized_fallback_scraper.py` - WebDriver pool manager

- `csgoskins_scraper.py` - Wear range scraper for csgoskins.gg integration- `cleanup_invalid_variants.py` - Removes skin variants that don't exist on the market

- `optimized_fallback_scraper.py` - WebDriver pool manager and fallback handler- `data/skins_database.json` - Database of CS2 skins (expected to exist)



### Utilities## V3.0 Database Schema



- `migrate_database_v3.py` - Database migration script from V2.0 to V3.0### New Fields in V3.0

- `cleanup_database.py` - Database cleanup and maintenance

- `cleanup_invalid_variants.py` - Removes invalid skin variantsEach variant now includes:

- `generate_statistics.py` - Generate database statistics

- `analyze_database.py` - Analyze database structure and content- **`wear_range`**: `{min: float, max: float}` - Actual float range for wear condition

- `summary_logger.py` - Logging utilities- **`achievable`**: `boolean` - Whether this wear condition is obtainable for this skin

- **`listing`**: `{normal: bool, stattrak: bool}` - Market listing availability

### Data

### Removed in V3.0

- `data/skins_database.json` - Main CS2 skins database

- `logs/` - Application logs directory- ❌ `availability` array (top-level)

- `price_collection_checkpoint.json` - Collection progress checkpoint- ❌ `stattrak_availability` array (top-level)  

- ❌ `available` field (variant-level, replaced by `listing`)

## 📋 Database Schema

## Database Cleanup ✨

### Skin Entry Structure

The system automatically removes skin variants that return `success: True` from the API but have no actual price data. These are variants that technically exist but are **not tradeable or available on the market**.

```json

{**Cleanup runs automatically:**

  "weapon": "AK-47",

  "skin_name": "Redline",- ✅ When price collection completes

  "rarity": "Classified",- ✅ When you press Ctrl+C during collection

  "variants": [...],- ✅ After missing-only collection

  "wear_ranges": [

    {**Quick Start:**

      "wear_condition": "Factory New",

      "min_float": 0.0,```bash

      "max_float": 0.07,# Just run price collection normally - cleanup is automatic!

      "achievable": true,python collect_prices.py

      "has_stattrak": true

    }# Or run cleanup manually

  ],python cleanup_invalid_variants.py --dry-run  # Preview changes

  "has_stattrak": true,python cleanup_invalid_variants.py             # Apply cleanup

  "has_souvenir": false```

}

```## Setup



### Variant Structure1. Install dependencies:



```json```bash

{pip install -r requirements.txt

  "wear": "Factory New",```

  "stattrak": false,

  "souvenir": false,2. Install Chrome WebDriver (required for V3.0):

  "market_hash_name": "AK-47 | Redline (Factory New)",

  "price_history": [```bash

    {# Windows (using chocolatey)

      "price": 125.50,choco install chromedriver

      "currency": "USD",

      "timestamp": "2025-10-17T12:00:00Z"# macOS (using homebrew)

    }brew install chromedriver

  ],

  "last_updated": "2025-10-17T12:00:00Z",# Linux

  "listings_count": 342,# Download from https://chromedriver.chromium.org/

  "exists_on_market": true```

}

```3. Configure environment (optional):



## 🚀 Quick Start```bash

cp .env.example .env

### Installation# Edit .env with your preferred settings

```

1. **Clone the repository**:

4. Ensure you have a `data/skins_database.json` file with skin data

```bash

git clone https://github.com/TheLime1/cs2-price-database.git## Usage

cd cs2-price-database

```### Migrate Database to V3.0 (First Time Only)



2. **Install dependencies**:If upgrading from V2.0, run the migration script first:



```bash```bash

pip install -r requirements.txt# Basic migration with default wear ranges

```python migrate_database_v3.py



3. **Install Chrome**: Chrome WebDriver is automatically managed by Selenium 4.x# Scrape actual wear ranges from csgoskins.gg (slower but more accurate)

python migrate_database_v3.py --scrape-wear-ranges

4. **Configure environment** (optional):

# Preview changes without saving

```bashpython migrate_database_v3.py --dry-run

cp .env.example .env```

# Edit .env with your preferred settings

```### Collect Prices (V3.0)



### First Time SetupBasic usage:



If you have an existing V2.0 database, migrate it first:```bash

python collect_prices.py

```bash```

python migrate_database_v3.py

```With command-line arguments:



### Running Price Collection```bash

# Collect prices for all skins (resumes from checkpoint)

**Collect prices for all skins**:python collect_prices.py



```bash# Limit to first 10 skins for testing

python collect_prices.pypython collect_prices.py --limit 10

```

# Process all skins without limit

**Resume from checkpoint**:python collect_prices.py --limit 0



```bash# Start from beginning (ignore checkpoint)

python collect_prices.py --resumepython collect_prices.py --no-resume

```

# Skip StatTrak variants to speed up collection

**Collect specific weapons**:python collect_prices.py --ignore-stattrak



```bash# Only process skins/variants that don't have prices yet

python collect_prices.py --weapon "AK-47" --weapon "AWP"python collect_prices.py --missing-only

```

# Combine arguments: test with 5 skins, no StatTrak, fresh start

**Force full refresh**:python collect_prices.py --limit 5 --ignore-stattrak --no-resume



```bash# Fastest option: missing prices only + no StatTrak

python collect_prices.py --force-refreshpython collect_prices.py --missing-only --ignore-stattrak

```

# Enable debug output

### Database Maintenancepython collect_prices.py --debug

```

**Generate statistics**:

#### Command-Line Arguments (V3.0)

```bash

python generate_statistics.py- `--limit <number>`: Limit number of skins to process

```  - Use small numbers (5-10) for testing

  - Use `0` for no limit (process all skins)

**Clean invalid variants**:  - Default: no limit

  

```bash- `--no-resume`: Start from beginning instead of resuming from checkpoint

python cleanup_invalid_variants.py --dry-run  # Preview  - Default: resumes from last processed skin

python cleanup_invalid_variants.py            # Apply  

```- `--ignore-stattrak`: Skip StatTrak variants to speed up collection

  - Processes only normal versions of skins

**Analyze database**:  - Roughly halves the processing time



```bash- `--missing-only`: Only process skins/variants that don't have prices yet

python analyze_database.py  - Skips items that already have price data

```  - Perfect for updating incomplete collections

  - Combines well with other flags

## ⚙️ Configuration

- `--update-availability`: Update weapon availability information

### Environment Variables (.env)  - Analyzes which wear conditions and StatTrak variants exist



```env- `--debug`: Enable detailed debug output

# Worker Configuration  - Shows scraping details, timing information, and WebDriver actions

WORKER_COUNT=3                    # Parallel workers (default: 3)  - Useful for troubleshooting scraping issues

MAX_RETRIES=3                     # Max retries per skin (default: 3)

CHECKPOINT_INTERVAL=10            # Save progress every N skins (default: 10)### Scrape Wear Ranges (V3.0 Feature)



# WebDriver SettingsScrape wear range data from csgoskins.gg:

HEADLESS_MODE=true                # Run browsers headless (default: true)

PAGE_LOAD_TIMEOUT=30              # Page timeout seconds (default: 30)```bash

IMPLICIT_WAIT=10                  # Implicit wait seconds (default: 10)# Standalone wear range scraping

python csgoskins_scraper.py

# Logging

LOG_LEVEL=INFO                    # DEBUG, INFO, WARNING, ERROR# Integrated during migration

```python migrate_database_v3.py --scrape-wear-ranges

```

### Command Line Options

## V3.0 Features

**collect_prices.py**:

- **WebDriver-Only**: Pure Selenium scraping, no API rate limits

```- **Worker Stealing**: Intelligent task distribution across WebDriver instances  

--workers N           Number of parallel workers- **Priority Queues**: Failed items automatically retry with priority

--resume              Resume from checkpoint- **Wear Range Validation**: Integration with csgoskins.gg for accurate float ranges

--force-refresh       Force refresh all prices- **Enhanced Schema**: Richer data structure with achievability and wear ranges

--weapon WEAPON       Collect specific weapon(s)- **Auto-Scaling**: Dynamic WebDriver pool based on system resources

--headless            Run in headless mode- **Progress Tracking**: Checkpoints enable resuming interrupted collections

```- **Error Handling**: Graceful handling of network and scraping errors

- **Logging**: Comprehensive logging with configurable levels

**migrate_database_v3.py**:- **Automatic Cleanup**: Removes invalid skin variants that don't exist on the market



```## Environment Variables (V3.0)

--input FILE          Input database file

--output FILE         Output database file### WebDriver Configuration

--skip-validation     Skip wear range validation

--dry-run             Preview changes only- `WEBDRIVER_POOL_SIZE`: Number of concurrent WebDriver instances (default: 3)

```- `WEBDRIVER_PAGE_LOAD_TIMEOUT`: Page load timeout in seconds (default: 30)

- `WEBDRIVER_HEADLESS`: Run WebDriver in headless mode (default: true)

## 🏗️ Architecture

### Rate Limiting

### Worker Stealing Design

- `WEBDRIVER_MIN_RPS`: Minimum requests per second per WebDriver (default: 1.0)

```- `WEBDRIVER_MAX_RPS`: Maximum requests per second per WebDriver (default: 3.0)

┌─────────────────┐

│ Skins Database  │### Data Sources

└────────┬────────┘

         │- `CSGODATABASE_BASE_URL`: Base URL for csgodatabase.com (default: https://www.csgodatabase.com)

         ▼- `CSGOSKINS_BASE_URL`: Base URL for csgoskins.gg (default: https://csgoskins.gg)

┌─────────────────┐     ┌──────────────────┐

│ Worker Pool     │────▶│ csgodatabase.com │### Data Freshness

│ (3 workers)     │     └──────────────────┘

└────────┬────────┘              │- `PRICE_UPDATE_INTERVAL_HOURS`: Hours before considering prices stale (default: 24)

         │                       ▼- `ENABLE_AUTO_BACKUP`: Create automatic backups (default: true)

         ▼              ┌─────────────────┐- `BACKUP_RETENTION_DAYS`: Days to keep backups (default: 7)

┌─────────────────┐    │  Price Data     │

│ Wear Validator  │    └─────────────────┘See `.env.example` for complete configuration options.

└────────┬────────┘              

         │                       ## Requirements

         ▼              

┌──────────────────┐- Python 3.8+

│  csgoskins.gg    │- selenium >= 4.0.0

└────────┬─────────┘- aiohttp >= 3.8.0

         │- python-dotenv >= 0.19.0

         ▼- Chrome WebDriver (chromedriver)
┌─────────────────┐
│ Wear Ranges     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Updated DB      │
└─────────────────┘
```

## 📝 Requirements

- **Python**: 3.11+
- **Chrome**: Latest version
- **Dependencies**:
  - selenium>=4.0.0
  - beautifulsoup4>=4.9.0
  - python-dotenv>=1.0.0
  - aiohttp>=3.8.0
  - requests>=2.28.0

## 🎯 Performance

V3.0 Performance Metrics:

- **Speed**: ~200-300 skins per hour (3 workers)
- **Reliability**: 99%+ success rate with retries
- **Memory**: ~500MB RAM usage
- **CPU**: Low-moderate usage

## 📚 Documentation

For detailed documentation, see:

- `ALGORITHM_DETAILED.md` - Algorithm documentation
- `HIGH_SPEED_ARCHITECTURE.md` - Architecture deep dive
- `ENHANCED_FEATURES.md` - Feature documentation
- `V3_MIGRATION_COMPLETE.md` - V3.0 migration guide
- `docs/` - Additional documentation

## ⚠️ Important Notes

1. **Rate Limiting**: Built-in delays to respect server resources
2. **Browser**: Chrome must be installed and up-to-date
3. **Data Accuracy**: Prices scraped from public sources
4. **Maintenance**: Run cleanup scripts periodically

## 🐛 Troubleshooting

### Chrome WebDriver Issues

```bash
# Clear Selenium cache
rm -rf ~/.cache/selenium/
python collect_prices.py
```

### Database Corruption

```bash
# Restore from backup
cp data/skins_database.json.backup data/skins_database.json
```

### Memory Issues

```bash
# Reduce worker count
python collect_prices.py --workers 1
```

## 📈 Version History

### V3.0 (October 2025)
- ✅ Complete rewrite to WebDriver-only architecture
- ✅ Removed all proxy and API dependencies
- ✅ Added wear range validation from csgoskins.gg
- ✅ Implemented worker stealing architecture
- ✅ Enhanced database schema
- ✅ 33% code size reduction

## 🤝 Contributing

Contributions are welcome! Please submit a Pull Request.

## 📄 License

MIT License - See LICENSE file for details.

## 🔗 Links

- [Repository](https://github.com/TheLime1/cs2-price-database)
- [Issues](https://github.com/TheLime1/cs2-price-database/issues)

---

**Version**: 3.0  
**Status**: Production Ready ✅  
**Last Updated**: October 2025
