"""
Test unlimited requests with proxy rotation
"""

import asyncio
import os
import time
from steam_api import SteamMarketAPIClient


async def test_unlimited_requests():
    """Test making rapid requests without rate limiting"""

    # Configure for unlimited requests
    os.environ['USE_PROXIES'] = 'true'
    os.environ['STEAM_API_RATE_LIMIT'] = '0'  # Unlimited
    os.environ['MAX_PROXIES'] = '200'         # Load more proxies

    print("Testing unlimited requests with proxy rotation...")
    print("Configuration:")
    print(f"  USE_PROXIES: {os.getenv('USE_PROXIES')}")
    print(f"  STEAM_API_RATE_LIMIT: {os.getenv('STEAM_API_RATE_LIMIT')}")
    print(f"  MAX_PROXIES: {os.getenv('MAX_PROXIES')}")

    # Test items
    test_items = [
        "AK-47 | Redline (Field-Tested)",
        "AWP | Dragon Lore (Field-Tested)",
        "M4A4 | Howl (Field-Tested)",
        "Glock-18 | Fade (Factory New)",
        "USP-S | Kill Confirmed (Minimal Wear)"
    ]

    async with SteamMarketAPIClient() as client:
        print(f"\nStarting rapid requests test...")
        start_time = time.time()

        for i, item in enumerate(test_items, 1):
            request_start = time.time()
            result, wait_time = await client.get_item_price(item)
            request_end = time.time()

            status = "✓" if result and result.get("success") else "✗"
            price = result.get("lowest_price", "N/A") if result else "N/A"

            print(f"  {i}. {status} {item}")
            print(
                f"     Price: {price} | Wait: {wait_time:.2f}s | Response: {request_end - request_start:.2f}s")

        total_time = time.time() - start_time
        print(
            f"\nCompleted {len(test_items)} requests in {total_time:.2f} seconds")
        print(f"Average time per request: {total_time / len(test_items):.2f}s")

        # Show proxy stats
        stats = client.get_cache_stats()
        if stats.get("proxy", {}).get("enabled"):
            proxy_stats = stats["proxy"]
            print(f"\nProxy Statistics:")
            print(f"  Total proxies: {proxy_stats['total_proxies']}")
            print(f"  Healthy proxies: {proxy_stats['healthy_proxies']}")
            print(f"  Current proxy: {proxy_stats['current_proxy']}")
        else:
            print("\nProxies not enabled or loaded")

if __name__ == "__main__":
    asyncio.run(test_unlimited_requests())
