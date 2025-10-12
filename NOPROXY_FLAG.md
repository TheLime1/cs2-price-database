# --noproxy Flag Documentation

## Overview

The `--noproxy` flag allows you to disable proxy usage and force a direct connection to the Steam API, even when proxies are configured in your environment.

## Usage

```bash
# Disable proxies for this run
python collect_prices.py --noproxy

# Combine with other flags
python collect_prices.py --noproxy --ignore-stattrak
python collect_prices.py --noproxy --debug --limit 5
```

## When to Use

### ✅ Use `--noproxy` when:

1. **Debugging API issues** - Eliminates proxy-related problems
2. **Proxies are causing errors** - Some proxies may be unreliable
3. **Testing direct connection** - Compare performance with/without proxies
4. **Environment has proxies enabled** - Override `USE_PROXIES=true` setting
5. **Rate limit is not an issue** - You're doing small test runs

### ❌ Don't use `--noproxy` when:

1. **Large-scale collection** - You'll hit Steam's rate limits quickly
2. **Collecting all skins** - Direct connection will take much longer
3. **Proxies are working well** - No need to disable them

## How It Works

The flag sets `proxy_manager.use_proxies = False` at initialization, which:
- Disables proxy rotation
- Forces all requests through direct connection
- Respects Steam's rate limits (20 requests/minute)
- Overrides environment variable `USE_PROXIES=true`

## Examples

### Before (with proxies):
```bash
python collect_prices.py --limit 5
# Uses proxy rotation, can make 50+ concurrent requests
```

### After (no proxies):
```bash
python collect_prices.py --limit 5 --noproxy
# Direct connection, limited to ~20 requests/minute
```

## Verification

Check logs to confirm proxies are disabled:
```
2025-10-06 09:11:33,763 - INFO - Proxies disabled via --noproxy flag
2025-10-06 09:11:33,763 - INFO - Loading database from data/skins_database.json
```

## Environment Variables

The `--noproxy` flag overrides the `USE_PROXIES` environment variable:

```bash
# Even with USE_PROXIES=true in .env
USE_PROXIES=true

# This will still disable proxies
python collect_prices.py --noproxy
```

## Performance Impact

| Configuration | Concurrent Requests | Est. Time for 1000 skins |
|--------------|--------------------|-----------------------|
| **With proxies** | 50+ | ~1-2 hours |
| **Without proxies (--noproxy)** | 1 | ~50 hours |

## Related Flags

- `--debug` - Show detailed API information
- `--ignore-stattrak` - Skip StatTrak variants (halves requests)
- `--limit N` - Process only N skins (for testing)

## Troubleshooting

If you're still seeing proxy-related messages after using `--noproxy`:
1. Check the logs for "Proxies disabled via --noproxy flag"
2. Ensure no other scripts are modifying proxy settings
3. Restart the collection process

## See Also

- [README.md](README.md) - Full documentation
- [Proxy Configuration](README.md#proxy-configuration) - How to set up proxies
