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

3. Configure proxies (optional, to dodge rate limits):
```bash
# Simply enable proxies in .env file - they'll be fetched automatically
USE_PROXIES=true

# Optional: Add backup proxies in case GitHub source fails
PROXY_LIST=proxy1.example.com:8080,proxy2.example.com:3128
```

4. Ensure you have a `data/skins_database.json` file with skin data

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

# Only process skins/variants that don't have prices yet
python collect_prices.py --missing-only

# Combine arguments: test with 5 skins, no StatTrak, fresh start
python collect_prices.py --limit 5 --ignore-stattrak --no-resume

# Fastest option: missing prices only + no StatTrak
python collect_prices.py --missing-only --ignore-stattrak
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

- `--missing-only`: Only process skins/variants that don't have prices yet
  - Skips items that already have price data
  - Perfect for updating incomplete collections
  - Combines well with other flags

### Verify Collection

```python
python verify_prices.py
```

### Proxy Management

Test and manage your proxy configuration:

```bash
# Test all configured proxies
python proxy_test.py test

# Show proxy statistics  
python proxy_test.py stats

# Benchmark proxy performance
python proxy_test.py benchmark

# Add a new proxy
python proxy_test.py add proxy.example.com 8080
python proxy_test.py add proxy.example.com 8080 --username user --password pass
```

## Features

- **Rate Limited**: Respects Steam API rate limits (configurable)
- **Proxy Support**: Automatic proxy rotation to bypass rate limits
- **Async Support**: Uses aiohttp for efficient concurrent requests
- **Progress Tracking**: Saves checkpoints to resume interrupted collections
- **Error Handling**: Graceful handling of network and API errors
- **Logging**: Comprehensive logging with configurable levels

## Environment Variables

### Steam API Configuration
- `STEAM_MARKET_API_URL`: Steam Market API endpoint (default: Steam's official endpoint)
- `STEAM_API_RATE_LIMIT`: Max requests per window (default: 20)
- `STEAM_API_RATE_WINDOW`: Time window in seconds (default: 60)

### Proxy Configuration
- `USE_PROXIES`: Enable proxy support (default: false)
- `PROXY_LIST`: Comma-separated list of backup proxies (format: `host:port` or `user:pass@host:port`)
- `PROXY_FILE`: Path to backup proxy file (default: proxies.txt)
- `PROXY_HEALTH_CHECK_INTERVAL`: Health check interval in seconds (default: 300)
- `PROXY_MAX_FAILURES`: Max failures before marking proxy as unhealthy (default: 3)
- `PROXY_TEST_URL`: URL for testing proxy health (default: https://httpbin.org/ip)
- `PROXY_TIMEOUT`: Proxy timeout in seconds (default: 10)

## Proxy Configuration

### Supported Proxy Formats

The system supports various proxy formats:

```
# HTTP/HTTPS proxies
http://proxy.example.com:8080
https://proxy.example.com:8080

# Proxies with authentication
http://username:password@proxy.example.com:8080

# SOCKS proxies
socks4://proxy.example.com:1080
socks5://proxy.example.com:1080

# Simple format (assumes HTTP)
proxy.example.com:8080
username:password@proxy.example.com:8080
```

### Configuration Methods

1. **Environment Variables** (.env file):
   ```bash
   USE_PROXIES=true
   PROXY_LIST=proxy1.com:8080,user:pass@proxy2.com:3128
   ```

2. **Proxy File** (proxies.txt):
   ```
   # HTTP proxies
   proxy1.example.com:8080
   user:pass@proxy2.example.com:3128
   
   # SOCKS proxies
   socks5://proxy3.example.com:1080
   ```

### Proxy Features

- **Dynamic Proxy Loading**: Automatically fetches fresh proxies from GitHub source
- **Automatic Rotation**: Proxies are rotated on failure or timeout
- **Health Monitoring**: Regular health checks remove dead proxies
- **Failure Recovery**: Failed proxies are automatically retested
- **Performance Tracking**: Response times and success rates are monitored
- **Graceful Fallback**: Falls back to backup proxies or direct connection if source fails

## Requirements

- Python 3.7+
- aiohttp >= 3.8.0
- python-dotenv >= 0.19.0