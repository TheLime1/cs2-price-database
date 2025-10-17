# Command Line Flags Documentation - V3.0

## Overview

This document describes all available command-line flags for the CS2 Price Database V3.0 collection system. These flags control various aspects of the price collection process, from limiting scope to enabling debugging features.

## Basic Usage

```bash
python collect_prices.py [OPTIONS]
```

## Available Flags

### Collection Control

#### `--limit <number>`

**Purpose**: Limit the number of skins to process  
**Type**: Integer  
**Default**: No limit (process all skins)  
**Usage**:

```bash
python collect_prices.py --limit 10    # Process first 10 skins
python collect_prices.py --limit 0     # No limit (process all)
```

**Notes**:

- Use small numbers (5-10) for testing
- Use 0 to explicitly process all skins
- Applies to skin count, not variant count

#### `--no-resume`

**Purpose**: Start collection from the beginning instead of resuming from checkpoint  
**Type**: Boolean flag  
**Default**: Resume from checkpoint if available  
**Usage**:

```bash
python collect_prices.py --no-resume
```

**Notes**:

- Ignores existing checkpoint data
- Useful for restarting collection with different parameters
- Does not delete checkpoint file, just ignores it

#### `--missing-only`

**Purpose**: Only process skins/variants that don't have price data yet  
**Type**: Boolean flag  
**Default**: Process all skins in order  
**Usage**:

```bash
python collect_prices.py --missing-only
```

**Notes**:

- Scans entire database for missing prices
- Skips items that already have valid price data
- Perfect for updating incomplete collections
- Faster than full collection for partial updates
- No checkpoint needed (processes queue-based)

#### `--ignore-stattrak`

**Purpose**: Skip StatTrak variants to speed up collection  
**Type**: Boolean flag  
**Default**: Process both normal and StatTrak variants  
**Usage**:

```bash
python collect_prices.py --ignore-stattrak
```

**Notes**:

- Roughly halves the processing time
- Only collects prices for normal (non-StatTrak) variants
- Useful for quick price surveys
- Can be combined with other flags

#### `--update-availability`

**Purpose**: Update weapon availability information to detect which wear conditions and StatTrak variants actually exist  
**Type**: Boolean flag  
**Default**: Skip availability updates  
**Usage**:

```bash
python collect_prices.py --update-availability
```

**Notes**:

- Analyzes market structure to determine actual variant availability
- Sets `listing`, `achievable`, and related fields
- Uses WebDriver scraper for comprehensive availability detection
- Adds processing time but provides valuable data about variant availability
- Can be combined with other collection flags for comprehensive updates

### Debugging and Logging

#### `--debug`

**Purpose**: Enable detailed debug output including scraping details and responses  
**Type**: Boolean flag  
**Default**: Standard logging level  
**Usage**:

```bash
python collect_prices.py --debug
```

**Notes**:

- Shows detailed WebDriver actions and page interactions
- Logs scraping details and timing information
- Enables detailed fallback scraper logging
- Increases log file sizes significantly
- Useful for troubleshooting scraping issues

## Flag Combinations

### Common Use Cases

#### Quick Testing

```bash
# Test with 5 skins, no StatTrak, debug enabled
python collect_prices.py --limit 5 --ignore-stattrak --debug
```

#### Fast Collection (Normal variants only)

```bash
# Collect all normal variants, skip StatTrak
python collect_prices.py --ignore-stattrak
```

#### Update Missing Data

```bash
# Only update items without prices
python collect_prices.py --missing-only
```

#### Fresh Start

```bash
# Start from beginning, ignore checkpoint
python collect_prices.py --no-resume
```

#### Production Run (Fastest)

```bash
# Missing items only, no StatTrak, no debug output
python collect_prices.py --missing-only --ignore-stattrak
```

### Advanced Combinations

#### Complete Fresh Collection

```bash
# Full collection from start, with all features
python collect_prices.py --no-resume --debug
```

#### Targeted Update

```bash
# Update missing prices with availability check
python collect_prices.py --missing-only --update-availability
```

#### WebDriver Troubleshooting

```bash
# Direct WebDriver scraping with detailed logging for 10 items
python collect_prices.py --limit 10 --debug
```

## Migration Commands (V3.0)

### Database Migration

#### Basic Migration

```bash
# Migrate database from V2.0 to V3.0 with default wear ranges
python migrate_database_v3.py
```

#### Scrape Wear Ranges

```bash
# Migrate and scrape actual wear ranges from csgoskins.gg
python migrate_database_v3.py --scrape-wear-ranges
```

#### Dry Run

```bash
# Preview migration changes without saving
python migrate_database_v3.py --dry-run
```

#### Custom Database Path

```bash
# Migrate a specific database file
python migrate_database_v3.py --database path/to/database.json
```

## Removed Flags in V3.0

The following flags were removed as part of the V3.0 WebDriver-only architecture:

### ❌ `--noproxy` (REMOVED)

**Reason**: V3.0 uses WebDriver-only architecture, no proxy support  
**Alternative**: N/A - Direct WebDriver scraping is now the default and only method

### ❌ `--fallback-only` (REMOVED)

**Reason**: V3.0 removed Steam API integration  
**Alternative**: All scraping now uses WebDriver (former "fallback" method is now primary)

## Performance Considerations

### WebDriver Instances (V3.0)

The system automatically calculates optimal WebDriver instance count based on:

- CPU cores available
- Available RAM (each instance uses ~600MB)
- Formula: `min(2 × CPU_cores, RAM_MB / 600)`

Example: 8-core system with 8GB RAM = `min(16, 13) = 13` WebDriver instances

### Rate Limiting (V3.0)

Each WebDriver instance operates at:

- **1-3 requests per second** (randomized)
- Jittered delays for natural behavior
- Automatic backoff on failures

### Collection Speed Estimates

Based on system with 8 cores and 8GB RAM (~10 WebDriver instances):

- **Full collection**: ~4-6 hours (6,805 variants)
- **Normal only** (`--ignore-stattrak`): ~2-3 hours
- **Missing only** (`--missing-only`): Varies by database state

## Examples by Scenario

### First-Time Setup

```bash
# 1. Migrate database to V3.0
python migrate_database_v3.py

# 2. Test with limited skins
python collect_prices.py --limit 10 --debug

# 3. Full collection
python collect_prices.py
```

### Regular Maintenance

```bash
# Update prices for items missing data
python collect_prices.py --missing-only
```

### Performance Testing

```bash
# Quick 5-skin test without StatTrak
python collect_prices.py --limit 5 --ignore-stattrak --debug
```

### Complete Refresh

```bash
# Start over from scratch
python collect_prices.py --no-resume --debug
```

## Environment Variables

Command-line flags can be complemented with environment variables in `.env`:

```bash
# WebDriver configuration
WEBDRIVER_POOL_SIZE=3
WEBDRIVER_HEADLESS=true

# Rate limiting
WEBDRIVER_MIN_RPS=1.0
WEBDRIVER_MAX_RPS=3.0

# Logging
LOG_LEVEL=INFO
```

See `.env.example` for complete configuration options.

## Troubleshooting

### Collection Stalls

```bash
# Enable debug to see what's happening
python collect_prices.py --debug --limit 5
```

### Missing Prices

```bash
# Target only missing items
python collect_prices.py --missing-only --debug
```

### Memory Issues

Reduce WebDriver pool size in `.env`:

```bash
WEBDRIVER_POOL_SIZE=2  # Reduce from default 3
```

### ChromeDriver Issues

Ensure ChromeDriver is installed and in PATH:

```bash
# Test ChromeDriver
chromedriver --version

# If not found, reinstall
# Windows: choco install chromedriver
# macOS: brew install chromedriver
```

## See Also

- [Database Structure](database_structure.md) - V3.0 database schema
- [README.md](../README.md) - Main documentation
- `.env.example` - Environment configuration reference
