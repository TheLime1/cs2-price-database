"""
Test script to verify proxy fetching from GitHub source
"""

import asyncio
import os
from proxy_manager import proxy_manager


async def test_proxy_fetching():
    """Test fetching proxies from GitHub"""
    print("Testing proxy fetching from GitHub source...")

    # Enable proxies
    os.environ['USE_PROXIES'] = 'true'

    # Ensure proxies are loaded
    await proxy_manager.ensure_proxies_loaded()

    # Get stats
    stats = proxy_manager.get_proxy_stats()

    print(f"Proxy Status: {'Enabled' if stats['enabled'] else 'Disabled'}")
    print(f"Total Proxies: {stats['total_proxies']}")
    print(f"Healthy Proxies: {stats['healthy_proxies']}")

    if stats['total_proxies'] > 0:
        print(f"Current Proxy: {stats['current_proxy']}")
        print("\nFirst 5 proxies:")
        for i, proxy in enumerate(stats['proxies'][:5]):
            print(
                f"  {i+1}. {proxy['host']}:{proxy['port']} - {proxy['protocol']}")

        # Test a few proxies
        print("\nTesting first 3 proxies...")
        test_count = min(3, len(proxy_manager.proxies))
        for i in range(test_count):
            proxy = proxy_manager.proxies[i]
            print(f"Testing {proxy.host}:{proxy.port}...", end=" ")
            result = await proxy_manager.test_proxy(proxy)
            status = "✓ Working" if result else "✗ Failed"
            print(status)
    else:
        print("No proxies loaded!")

if __name__ == "__main__":
    asyncio.run(test_proxy_fetching())
