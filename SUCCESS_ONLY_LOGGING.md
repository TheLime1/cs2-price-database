# Success-Only Response Logging

## Overview
A dedicated logging system for tracking Steam API responses that return only `{"success": true}` without actual price data.

## Log File
**File:** `success_only_responses.log`

## What Gets Logged
When the Steam API returns a response containing only:
```json
{"success": true}
```

This indicates that the item exists in Steam's database but has no market data available (not tradeable, no recent sales, etc.).

## Log Format
Each entry contains:
- **Timestamp**: When the response was received
- **ITEM**: The market hash name of the item
- **URL**: The complete Steam API endpoint that was called
- **RESPONSE**: The actual JSON response from Steam API
- **REASON**: Explanation of what this response means
- **Separator**: 80 dashes to separate entries

## Example Log Entry
```
2025-10-05 18:20:52,406 | ITEM: AWP | Lightning Strike (Field-Tested)
2025-10-05 18:20:52,406 | URL: https://steamcommunity.com/market/priceoverview/?appid=730&currency=1&market_hash_name=AWP+%7C+Lightning+Strike+%28Field-Tested%29
2025-10-05 18:20:52,406 | RESPONSE: {'success': True}
2025-10-05 18:20:52,406 | REASON: Item exists but has no market data or is not tradeable
2025-10-05 18:20:52,406 | --------------------------------------------------------------------------------
```

## Why These Items Return Success-Only
Items that return only `{"success": true}` typically fall into these categories:

1. **No Recent Sales**: Item hasn't been sold recently enough for Steam to show pricing data
2. **Not Tradeable**: Item exists but isn't available for trading/market transactions  
3. **Market Restrictions**: Item may be restricted from the Steam Community Market
4. **Very New Items**: Recently added items that haven't had market activity yet
5. **Very Rare Items**: Items so rare that there's no active market data

## How This Helps
- **Debugging**: Easy to identify which items are causing "no price data" results
- **Analysis**: Understand which items consistently have no market presence
- **Manual Verification**: Direct URLs for manual testing of problematic items
- **Cleanup**: Identify items that might need to be excluded from price collection

## Integration
This logging works alongside the main debug logging system:
- **Main logs**: Still show detailed debug information when `--debug` flag is used
- **Success-only log**: Dedicated file specifically for these edge cases
- **No Duplication**: Both systems work together without interfering

The system automatically detects these responses in both `steam_api.py` and `collect_prices.py`, ensuring comprehensive coverage.