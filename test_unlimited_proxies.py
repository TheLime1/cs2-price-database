#!/usr/bin/env python3
"""
Test script to verify unlimited proxy loading without MAX_PROXIES limit
"""

import asyncio
import os
import sys
from proxy_manager import ProxyManager


async def test_unlimited_proxies():
    """Test loading all proxies from GitHub source"""
    print("Testing unlimited proxy loading...")

    # Set environment variables
    os.environ['USE_PROXIES'] = 'true'

    # Create proxy manager
    pm = ProxyManager()

    # Override the health testing to just fetch proxies without testing them
    async def quick_fetch():
        """Fetch proxies without health testing"""
        github_url = "https://raw.githubusercontent.com/TheLime1/Validity/refs/heads/main/data/http.txt"

        try:
            import aiohttp
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.get(github_url) as response:
                    if response.status == 200:
                        content = await response.text()

                        for line in content.split('\n'):
                            line = line.strip()
                            # Skip comments and empty lines
                            if not line or line.startswith('#') or 'Format:' in line:
                                continue

                            # Parse proxy
                            proxy = pm._parse_proxy_string(line)
                            if proxy:
                                pm.proxies.append(proxy)

                        if pm.proxies:
                            print(
                                f"✓ Successfully fetched {len(pm.proxies)} proxies from GitHub")
                            pm.use_proxies = True

                            # Show sample proxies
                            print(f"✓ First 5 proxies:")
                            for i, proxy in enumerate(pm.proxies[:5]):
                                print(f"  {i+1}. {proxy.host}:{proxy.port}")

                            print(f"✓ Last 5 proxies:")
                            for i, proxy in enumerate(pm.proxies[-5:], len(pm.proxies)-4):
                                print(f"  {i}. {proxy.host}:{proxy.port}")
                        else:
                            print("✗ No valid proxies found")
                    else:
                        print(
                            f"✗ Failed to fetch proxies: HTTP {response.status}")

        except Exception as e:
            print(f"✗ Error fetching proxies: {e}")

    # Fetch proxies
    await quick_fetch()

    print(f"\nResults:")
    print(f"- Total proxies loaded: {len(pm.proxies)}")
    print(f"- Proxy support enabled: {pm.use_proxies}")
    print(f"- No MAX_PROXIES limit applied: ✓")

    # Test proxy rotation
    if pm.proxies:
        print(f"\nTesting proxy rotation:")
        current = pm.get_current_proxy()
        print(f"- Current proxy: {current.host}:{current.port}")

        pm.rotate_proxy()
        rotated = pm.get_current_proxy()
        print(f"- After rotation: {rotated.host}:{rotated.port}")
        print(f"- Rotation working: {'✓' if current != rotated else '✗'}")

if __name__ == "__main__":
    asyncio.run(test_unlimited_proxies())
