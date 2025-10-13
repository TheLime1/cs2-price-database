# Command Line Flags Documentation

## Overview

This document describes all available command-line flags for the CS2 Price Database collection system. These flags control various aspects of the price collection process, from limiting scope to enabling debugging features.

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

#### `--update-availability`
**Purpose**: Update weapon availability information to detect which wear conditions and StatTrak variants actually exist  
**Type**: Boolean flag  
**Default**: Skip availability updates  
**Usage**:
```bash
python collect_prices.py --update-availability
```
**Notes**:
- Analyzes Steam Market structure to determine actual variant availability
- Sets `available`, `stattrak_available`, `has_normal_listings`, and `has_stattrak_listings` fields
- Uses enhanced fallback scraper for comprehensive availability detection
- Prevents skipping weapons due to proxy issues by using multiple retry attempts
- Adds processing time but provides valuable data about variant availability
- Can be combined with other collection flags for comprehensive updates
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

### Network Control

#### `--noproxy`
**Purpose**: Disable proxy usage and use direct connection to Steam API  
**Type**: Boolean flag  
**Default**: Use proxies if configured in environment  
**Usage**:
```bash
python collect_prices.py --noproxy
```
**Notes**:
- Forces direct connection regardless of `USE_PROXIES` environment variable
- Useful for debugging proxy-related issues
- May be slower due to rate limiting without proxy rotation
- Overrides all proxy configuration

#### `--fallback-only`
**Purpose**: Skip Steam API entirely and use only fallback scraping method  
**Type**: Boolean flag  
**Default**: Try Steam API first, then fallback on failure  
**Usage**:
```bash
python collect_prices.py --fallback-only
```
**Notes**:
- Bypasses Steam Market API completely
- Goes directly to web scraping method for all items
- Useful when Steam API is completely unavailable or rate-limited
- Slower than API but more reliable for problem items
- Cannot be used with `--no-fallback` (conflicting flags)
- Ideal for collecting data that Steam API consistently fails to provide

### Debugging and Logging

#### `--debug`
**Purpose**: Enable detailed debug output including API endpoints and responses  
**Type**: Boolean flag  
**Default**: Standard logging level  
**Usage**:
```bash
python collect_prices.py --debug
```
**Notes**:
- Shows raw API responses and request details
- Logs full API endpoint URLs for debugging
- Enables detailed fallback scraper logging
- Increases log file sizes significantly
- Useful for troubleshooting API issues

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

#### No Network Issues
```bash
# Direct connection, no proxies, with debugging
python collect_prices.py --noproxy --debug
```

#### Fallback-Only Collection
```bash
# Use only fallback scraping, bypass Steam API entirely
python collect_prices.py --fallback-only
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
# Update missing StatTrak prices only (requires custom logic)
python collect_prices.py --missing-only
```

#### Network Troubleshooting
```bash
# Direct connection with detailed logging for 10 items
python collect_prices.py --limit 10 --noproxy --debug --no-resume
```

#### Fallback-Only Troubleshooting
```bash
# Fallback scraping only with debug output for 5 items
python collect_prices.py --fallback-only --limit 5 --debug
```

#### Complete Fallback Collection
```bash
# Full collection using only fallback method (when Steam API is unavailable)
python collect_prices.py --fallback-only --missing-only
```

#### Availability Detection
```bash
# Update availability information for all weapons
python collect_prices.py --update-availability

# Update availability for missing items only
python collect_prices.py --update-availability --missing-only

# Full availability analysis with fallback scraper
python collect_prices.py --update-availability --fallback-only

# Test availability detection on limited set
python collect_prices.py --update-availability --limit 5 --debug
```

## Flag Precedence and Interactions

### Processing Mode Priority
1. `--missing-only` takes precedence over sequential processing
2. When `--missing-only` is used, `--no-resume` is ignored (no checkpoints in missing-only mode)
3. `--limit` applies differently:
   - Sequential mode: limits number of skins
   - Missing-only mode: limits approximately (10 variants per limit number)

### Network Configuration
- `--noproxy` overrides all environment proxy settings
- `--fallback-only` bypasses Steam API entirely and uses only web scraping
- `--no-fallback` and `--fallback-only` cannot be used together (conflicting flags)
- Proxy settings from environment are used unless `--noproxy` is specified
- Fallback scraper uses same proxy settings as main collection

### Logging Levels
- `--debug` enables maximum verbosity for all components
- Without `--debug`: INFO level logging to console and file
- With `--debug`: DEBUG level with API details and raw responses

## Environment Variable Interactions

Some flags interact with environment variables:

| Flag                    | Environment Variable | Interaction                     |
| ----------------------- | -------------------- | ------------------------------- |
| `--noproxy`             | `USE_PROXIES`        | Overrides and disables          |
| `--debug`               | `LOG_LEVEL`          | Sets to DEBUG regardless of env |
| `--fallback-only`       | None                 | No environment equivalent       |
| `--no-fallback`         | None                 | No environment equivalent       |
| `--limit`               | None                 | No environment equivalent       |
| `--missing-only`        | None                 | No environment equivalent       |
| `--ignore-stattrak`     | None                 | No environment equivalent       |
| `--no-resume`           | None                 | No environment equivalent       |
| `--update-availability` | None                 | No environment equivalent       |

## Output and Logging

### Standard Output (without --debug)
- Progress updates every batch
- Success/failure summary statistics  
- ETA calculations and performance metrics
- Error notifications for major issues

### Debug Output (with --debug)
- Raw API request URLs and parameters
- Complete API response data
- Proxy selection and rotation details
- Fallback scraper activation and results
- Detailed timing and performance data

### Log Files Generated
- `logs/price_collection.log` - Main collection log
- `logs/success_only_responses.log` - API responses with success but no price data
- `logs/api_rate_test.log` - Rate limiting and performance metrics
- `logs/summary.txt` - Final collection summary (generated at end)

## Exit Codes

| Code | Meaning     | Triggered By                            |
| ---- | ----------- | --------------------------------------- |
| 0    | Success     | Normal completion                       |
| 1    | Error       | Unhandled exceptions, critical failures |
| 130  | Interrupted | Ctrl+C (SIGINT)                         |

## Best Practices

### Development and Testing
```bash
# Start small and build up
python collect_prices.py --limit 5 --debug
python collect_prices.py --limit 20 --ignore-stattrak  
python collect_prices.py --missing-only
```

### Production Usage
```bash
# Standard production run
python collect_prices.py

# Quick update run  
python collect_prices.py --missing-only --ignore-stattrak

# Full refresh (careful - takes ~11 hours)
python collect_prices.py --no-resume
```

### Troubleshooting
```bash
# Network issues
python collect_prices.py --noproxy --debug --limit 5

# Proxy problems
python collect_prices.py --debug --limit 10

# Steam API unavailable - use fallback only
python collect_prices.py --fallback-only --debug --limit 5

# Data issues
python collect_prices.py --missing-only --debug
```

## Error Handling

All flags are validated at startup:
- Invalid `--limit` values are rejected
- Conflicting flag combinations are detected
- Missing dependencies (when using fallback features) are checked
- Environment variable conflicts are resolved with clear precedence

The system provides helpful error messages for common mistakes:
```bash
# Invalid limit
python collect_prices.py --limit -5
# Error: --limit must be 0 or positive integer

# Unknown flag  
python collect_prices.py --unknown-flag
# Error: unrecognized arguments: --unknown-flag
```