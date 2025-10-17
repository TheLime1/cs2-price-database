# CS2 Price Database V3.0

A high-performance Python application for collecting Steam Community Market prices for CS2 skins using WebDriver-based scraping with intelligent worker stealing architecture.

## 🚀 V3.0 - WebDriver-Only Architecture

**Major Changes in V3.0:**
- ✅ **WebDriver-Only**: Removed all proxy and Steam API dependencies
- ✅ **Simplified Architecture**: Pure Selenium scraping from csgodatabase.com
- ✅ **Wear Range Validation**: Integration with csgoskins.gg for accurate float ranges
- ✅ **Enhanced Schema**: Added wear ranges, achievability, and improved listing structure
- ✅ **Smaller Codebase**: 33% reduction in code size (removed ~3,000 lines)
- ✅ **More Reliable**: Direct scraping eliminates rate limiting and proxy issues

## Database Statistics

The CS2 skins database contains:

- **1,361 total skins** across **36 unique weapons**
- **6,805 variants** (different wear conditions per skin)
- Data sources: csgodatabase.com + csgoskins.gg

### Top 10 Weapons by Skin Count

1. **AK-47**: 56 skins
2. **P250**: 55 skins  
3. **MAC-10**: 54 skins
4. **Glock-18**: 51 skins
5. **P90**: 50 skins
6. **M4A4**: 48 skins
7. **AWP**: 47 skins
8. **Tec-9**: 45 skins
9. **Nova**: 44 skins
10. **M4A1-S**: 43 skins

## Files

- `high_speed_scraper.py` - V3.0 WebDriver-only worker stealing scraper
- `collect_prices.py` - Main price collection system with checkpoint support
- `csgoskins_scraper.py` - Wear range scraper for csgoskins.gg integration
- `migrate_database_v3.py` - Database migration script from V2.0 to V3.0
- `optimized_fallback_scraper.py` - WebDriver pool manager
- `cleanup_invalid_variants.py` - Removes skin variants that don't exist on the market
- `data/skins_database.json` - Database of CS2 skins (expected to exist)

## V3.0 Database Schema

### New Fields in V3.0

Each variant now includes:

- **`wear_range`**: `{min: float, max: float}` - Actual float range for wear condition
- **`achievable`**: `boolean` - Whether this wear condition is obtainable for this skin
- **`listing`**: `{normal: bool, stattrak: bool}` - Market listing availability

### Removed in V3.0

- ❌ `availability` array (top-level)
- ❌ `stattrak_availability` array (top-level)  
- ❌ `available` field (variant-level, replaced by `listing`)

## Database Cleanup ✨

The system automatically removes skin variants that return `success: True` from the API but have no actual price data. These are variants that technically exist but are **not tradeable or available on the market**.

**Cleanup runs automatically:**

- ✅ When price collection completes
- ✅ When you press Ctrl+C during collection
- ✅ After missing-only collection

**Quick Start:**

```bash
# Just run price collection normally - cleanup is automatic!
python collect_prices.py

# Or run cleanup manually
python cleanup_invalid_variants.py --dry-run  # Preview changes
python cleanup_invalid_variants.py             # Apply cleanup
```

## Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Install Chrome WebDriver (required for V3.0):

```bash
# Windows (using chocolatey)
choco install chromedriver

# macOS (using homebrew)
brew install chromedriver

# Linux
# Download from https://chromedriver.chromium.org/
```

3. Configure environment (optional):

```bash
cp .env.example .env
# Edit .env with your preferred settings
```

4. Ensure you have a `data/skins_database.json` file with skin data

## Usage

### Migrate Database to V3.0 (First Time Only)

If upgrading from V2.0, run the migration script first:

```bash
# Basic migration with default wear ranges
python migrate_database_v3.py

# Scrape actual wear ranges from csgoskins.gg (slower but more accurate)
python migrate_database_v3.py --scrape-wear-ranges

# Preview changes without saving
python migrate_database_v3.py --dry-run
```

### Collect Prices (V3.0)

Basic usage:

```bash
python collect_prices.py
```

With command-line arguments:

```bash
# Collect prices for all skins (resumes from checkpoint)
python collect_prices.py

# Limit to first 10 skins for testing
python collect_prices.py --limit 10

# Process all skins without limit
python collect_prices.py --limit 0

# Start from beginning (ignore checkpoint)
python collect_prices.py --no-resume

# Skip StatTrak variants to speed up collection
python collect_prices.py --ignore-stattrak

# Only process skins/variants that don't have prices yet
python collect_prices.py --missing-only

# Combine arguments: test with 5 skins, no StatTrak, fresh start
python collect_prices.py --limit 5 --ignore-stattrak --no-resume

# Fastest option: missing prices only + no StatTrak
python collect_prices.py --missing-only --ignore-stattrak

# Enable debug output
python collect_prices.py --debug
```

#### Command-Line Arguments (V3.0)

- `--limit <number>`: Limit number of skins to process
  - Use small numbers (5-10) for testing
  - Use `0` for no limit (process all skins)
  - Default: no limit
  
- `--no-resume`: Start from beginning instead of resuming from checkpoint
  - Default: resumes from last processed skin
  
- `--ignore-stattrak`: Skip StatTrak variants to speed up collection
  - Processes only normal versions of skins
  - Roughly halves the processing time

- `--missing-only`: Only process skins/variants that don't have prices yet
  - Skips items that already have price data
  - Perfect for updating incomplete collections
  - Combines well with other flags

- `--update-availability`: Update weapon availability information
  - Analyzes which wear conditions and StatTrak variants exist

- `--debug`: Enable detailed debug output
  - Shows scraping details, timing information, and WebDriver actions
  - Useful for troubleshooting scraping issues

### Scrape Wear Ranges (V3.0 Feature)

Scrape wear range data from csgoskins.gg:

```bash
# Standalone wear range scraping
python csgoskins_scraper.py

# Integrated during migration
python migrate_database_v3.py --scrape-wear-ranges
```

## V3.0 Features

- **WebDriver-Only**: Pure Selenium scraping, no API rate limits
- **Worker Stealing**: Intelligent task distribution across WebDriver instances  
- **Priority Queues**: Failed items automatically retry with priority
- **Wear Range Validation**: Integration with csgoskins.gg for accurate float ranges
- **Enhanced Schema**: Richer data structure with achievability and wear ranges
- **Auto-Scaling**: Dynamic WebDriver pool based on system resources
- **Progress Tracking**: Checkpoints enable resuming interrupted collections
- **Error Handling**: Graceful handling of network and scraping errors
- **Logging**: Comprehensive logging with configurable levels
- **Automatic Cleanup**: Removes invalid skin variants that don't exist on the market

## Environment Variables (V3.0)

### WebDriver Configuration

- `WEBDRIVER_POOL_SIZE`: Number of concurrent WebDriver instances (default: 3)
- `WEBDRIVER_PAGE_LOAD_TIMEOUT`: Page load timeout in seconds (default: 30)
- `WEBDRIVER_HEADLESS`: Run WebDriver in headless mode (default: true)

### Rate Limiting

- `WEBDRIVER_MIN_RPS`: Minimum requests per second per WebDriver (default: 1.0)
- `WEBDRIVER_MAX_RPS`: Maximum requests per second per WebDriver (default: 3.0)

### Data Sources

- `CSGODATABASE_BASE_URL`: Base URL for csgodatabase.com (default: https://www.csgodatabase.com)
- `CSGOSKINS_BASE_URL`: Base URL for csgoskins.gg (default: https://csgoskins.gg)

### Data Freshness

- `PRICE_UPDATE_INTERVAL_HOURS`: Hours before considering prices stale (default: 24)
- `ENABLE_AUTO_BACKUP`: Create automatic backups (default: true)
- `BACKUP_RETENTION_DAYS`: Days to keep backups (default: 7)

See `.env.example` for complete configuration options.

## Requirements

- Python 3.8+
- selenium >= 4.0.0
- aiohttp >= 3.8.0
- python-dotenv >= 0.19.0
- Chrome WebDriver (chromedriver)