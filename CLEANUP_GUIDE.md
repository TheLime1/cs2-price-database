# Cleanup Invalid Variants

This script automatically removes skin variants from the database that return `success: True` from the Steam API but have no actual price data. These are variants that technically "exist" in the API response but are not tradeable or available on the Steam Community Market.

## What Gets Removed

The script removes variants where:
- The API returns `{"success": true}` but no `lowest_price` field
- The variant shows as "Not possible" on sites like CSGODatabase
- Both normal and StatTrak versions have no market data (the wear level doesn't actually exist for that skin)

### Example
From your `success_only_responses.log`:
```
AWP | Lightning Strike (Field-Tested) -> success: True, but no price
Desert Eagle | Hypnotic (Well-Worn) -> success: True, but no price
```

These variants will be completely removed from the database since they cannot be traded or purchased.

## Automatic Integration

The cleanup script runs **automatically** in these scenarios:

1. ✅ **When price collection completes normally** - After all prices are collected
2. ✅ **When you press Ctrl+C** - During graceful shutdown
3. ✅ **After missing-only collection** - When using `--missing-only` flag

No manual intervention needed! Just run your price collection as usual:

```powershell
python collect_prices.py
```

When it finishes (or you interrupt with Ctrl+C), the cleanup will run automatically.

## Manual Usage

If you want to run the cleanup independently:

### Dry Run (Preview Only)
See what would be removed without making changes:
```powershell
python cleanup_invalid_variants.py --dry-run
```

### Actual Cleanup
Remove invalid variants:
```powershell
python cleanup_invalid_variants.py
```

### Custom Database Path
```powershell
python cleanup_invalid_variants.py --database path/to/your/database.json
```

## Safety Features

1. **Automatic Backup**: Before any changes, a timestamped backup is created
   - Format: `skins_database.json.backup_YYYYMMDD_HHMMSS`
   - Stored in the same directory as your database

2. **Detailed Logging**: All actions are logged to `cleanup.log`
   - What was removed
   - Why it was removed
   - Statistics summary

3. **Dry Run Mode**: Test the cleanup without making any changes

## Output Example

```
================================================================================
STARTING DATABASE CLEANUP
================================================================================
✓ Loaded database with 1361 skins
✓ Created backup: data/skins_database.json.backup_20251005_182500

Analyzing variants...
  ✗ Removing variant: AWP Lightning Strike (Field-Tested) - Both normal and stattrak invalid
  ✗ Removing variant: Desert Eagle Hypnotic (Well-Worn) - Both normal and stattrak invalid
  ⚠ Removing stattrak price for: AWP Lightning Strike (Minimal Wear)

================================================================================
CLEANUP STATISTICS
================================================================================
Skins checked: 1361
Complete variants removed: 150
Individual price types removed: 45
Skins completely removed (no valid variants): 0

Saving cleaned database...
✓ Saved cleaned database to data/skins_database.json

✓ Cleanup completed successfully!
✓ Backup saved at: data/skins_database.json.backup_20251005_182500
================================================================================
```

## What Gets Kept

The script is smart about preserving data:
- ✅ Variants with actual prices (even $0.00 listed prices)
- ✅ Variants where only one type (normal OR stattrak) is invalid
- ✅ Variants that haven't been checked yet (no price data at all)

## Restoring from Backup

If you need to restore a backup:

```powershell
# Find your backup
ls data/*.backup_*

# Restore it (replace the timestamp with your backup's timestamp)
Copy-Item data/skins_database.json.backup_20251005_182500 data/skins_database.json -Force
```

## Integration with Price Collection

The cleanup is automatically triggered in `collect_prices.py`:

- After normal completion
- During graceful shutdown (Ctrl+C)
- After missing-only mode completion

You can disable auto-cleanup by commenting out the `self.run_cleanup()` calls in `collect_prices.py` if needed.

## Log Files

- `cleanup.log` - Detailed cleanup operations
- `success_only_responses.log` - Records of API responses with success but no price (for debugging)

## Benefits

1. **Cleaner Database**: No fake/impossible variants cluttering your data
2. **Accurate Statistics**: Correct count of actual tradeable skins
3. **Better Analysis**: Statistics and reports reflect only real market items
4. **Space Saving**: Smaller database file size
5. **No Manual Work**: Runs automatically, you don't have to think about it
