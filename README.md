# CS2 Price Database

A Python application for collecting Steam Community Market prices for CS2 skins with rate limiting and progress tracking.

## Database Statistics

The CS2 skins database contains:

- **1,361 total skins** across **36 unique weapons**
- **6,805 variants** (different wear conditions per skin)
- **13,610 estimated API calls** for complete price collection (Normal + StatTrak)
- **6,805 estimated API calls** for Normal variants only

### Processing Time Estimates (at 20 calls/minute rate limit)

- **Full collection (Normal + StatTrak)**: ~11.3 hours
- **Normal variants only**: ~5.7 hours (use `--ignore-stattrak`)

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

- `steam_api.py` - Steam Market API client with async support and rate limiting
- `collect_prices.py` - Main price collection system with checkpoint support
- `verify_prices.py` - Utility to verify collected prices
- `data/skins_database.json` - Database of CS2 skins (expected to exist)

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure environment (optional):
```bash
cp .env.example .env
# Edit .env with your preferred settings
```

3. Ensure you have a `data/skins_database.json` file with skin data

## Usage

### Collect Prices

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

# Combine arguments: test with 5 skins, no StatTrak, fresh start
python collect_prices.py --limit 5 --ignore-stattrak --no-resume
```

#### Command-Line Arguments

- `--limit <number>`: Limit number of skins to process
  - Use small numbers (5-10) for testing
  - Use `0` for no limit (process all skins)
  - Default: no limit
  
- `--no-resume`: Start from beginning instead of resuming from checkpoint
  - Default: resumes from last processed skin
  
- `--ignore-stattrak`: Skip StatTrak variants to speed up collection
  - Processes only normal versions of skins
  - Roughly halves the processing time

### Verify Collection
```python
python verify_prices.py
```

## Features

- **Rate Limited**: Respects Steam API rate limits (configurable)
- **Async Support**: Uses aiohttp for efficient concurrent requests
- **Progress Tracking**: Saves checkpoints to resume interrupted collections
- **Error Handling**: Graceful handling of network and API errors
- **Logging**: Comprehensive logging with configurable levels

## Environment Variables

- `STEAM_MARKET_API_URL`: Steam Market API endpoint (default: Steam's official endpoint)
- `STEAM_API_RATE_LIMIT`: Max requests per window (default: 20)
- `STEAM_API_RATE_WINDOW`: Time window in seconds (default: 60)

## Requirements

- Python 3.7+
- aiohttp >= 3.8.0
- python-dotenv >= 0.19.0