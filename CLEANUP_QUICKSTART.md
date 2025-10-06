# Automatic Database Cleanup - Quick Start

## What It Does

Automatically removes skin variants that return `success: True` from Steam API but have **NO PRICE DATA** (not tradeable/available on market).

### Example from your database:
- ❌ AWP Lightning Strike (Field-Tested) - Not available in game
- ❌ Desert Eagle Hypnotic (Well-Worn) - Not available in game  
- ⚠️ Glock-18 Fade (Factory New) - Normal variant not available (StatTrak exists)

## How To Use

### ✅ Automatic (Recommended)

The cleanup runs automatically when:
1. Price collection completes normally
2. You press **Ctrl+C** during collection
3. After missing-only collection

Just run price collection as normal:
```powershell
python collect_prices.py
```

### 🔍 Manual Dry Run (Preview Only)

See what would be removed without making changes:
```powershell
python cleanup_invalid_variants.py --dry-run
```

### 🧹 Manual Cleanup

Run cleanup independently:
```powershell
python cleanup_invalid_variants.py
```

## What Happened to Your Database?

Based on the dry run, here's what will be cleaned:

| Statistic                          | Count |
| ---------------------------------- | ----- |
| **Skins checked**                  | 1,361 |
| **Complete variants removed**      | 15    |
| **Individual price types removed** | 91    |
| **Skins completely deleted**       | 0     |

### Examples of What Gets Removed:

**Complete Variants (both normal & StatTrak invalid):**
- AWP Lightning Strike (Field-Tested, Well-Worn, Battle-Scarred)
- Desert Eagle Hypnotic (Minimal Wear, Field-Tested, Well-Worn, Battle-Scarred)
- Glock-18 Dragon Tattoo (Well-Worn, Battle-Scarred)
- USP-S Dark Water (Factory New, Well-Worn, Battle-Scarred)
- M4A1-S Dark Water (Factory New, Well-Worn, Battle-Scarred)

**Partial Removals (only normal or StatTrak):**
- Glock-18 Fade (all wear levels - normal variant doesn't exist)
- Desert Eagle Blaze (most wear levels - only Factory New exists normally)
- P90 Death by Kitty (several wear levels don't exist)
- Many others...

## Safety

✅ **Automatic backup** created before any changes  
✅ **Detailed logging** to `cleanup.log`  
✅ **No valid data removed** - only impossible variants  

## Backup Location

Backups are saved as:
```
data/skins_database.json.backup_YYYYMMDD_HHMMSS
```

To restore a backup:
```powershell
Copy-Item data/skins_database.json.backup_20251006_085901 data/skins_database.json -Force
```

## Next Steps

Just run your price collection normally - cleanup happens automatically! 🎉

For more details, see: [CLEANUP_GUIDE.md](CLEANUP_GUIDE.md)
