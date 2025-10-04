#!/usr/bin/env python3
"""
Test script to verify proxy health monitoring and concurrency control
"""

import asyncio
import os
import sys
from proxy_manager import ProxyManager


async def test_proxy_health_monitoring():
    """Test the one-by-one proxy health monitoring"""
    print("🧪 Testing Proxy Health Monitoring and Concurrency Control")
    print("=" * 60)

    # Set environment variables
    os.environ['USE_PROXIES'] = 'true'
    # Test with 5 concurrent requests
    os.environ['MAX_CONCURRENT_REQUESTS'] = '5'

    # Create proxy manager
    pm = ProxyManager()
    print(
        f"✓ ProxyManager created with max concurrent requests: {pm.max_concurrent_requests}")

    # Quick fetch of first 10 proxies for testing
    async def fetch_test_proxies():
        """Fetch first 10 proxies for testing"""
        github_url = "https://raw.githubusercontent.com/TheLime1/Validity/refs/heads/main/data/http.txt"

        try:
            import aiohttp
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.get(github_url) as response:
                    if response.status == 200:
                        content = await response.text()
                        count = 0

                        for line in content.split('\n'):
                            line = line.strip()
                            # Skip comments and empty lines
                            if not line or line.startswith('#') or 'Format:' in line:
                                continue

                            # Parse proxy
                            proxy = pm._parse_proxy_string(line)
                            if proxy:
                                pm.proxies.append(proxy)
                                count += 1
                                if count >= 10:  # Limit to 10 for testing
                                    break

                        print(
                            f"✓ Fetched {len(pm.proxies)} test proxies from GitHub")
                        pm.use_proxies = True
                    else:
                        print(
                            f"✗ Failed to fetch proxies: HTTP {response.status}")

        except Exception as e:
            print(f"✗ Error fetching proxies: {e}")

    # Initialize proxy manager
    await fetch_test_proxies()
    await pm.ensure_proxies_loaded()

    if not pm.proxies:
        print("✗ No proxies available for testing")
        return

    print(f"\n🔍 Testing health monitoring (one by one):")
    print(f"- Total proxies to test: {len(pm.proxies)}")

    # Test health monitoring
    print("\n⏳ Starting health check...")
    start_time = asyncio.get_event_loop().time()

    await pm._test_and_filter_proxies_sequential()

    end_time = asyncio.get_event_loop().time()
    test_duration = end_time - start_time

    print(f"\n📊 Health Check Results:")
    print(f"- Total working proxies: {len(pm.proxies)}")
    print(f"- Test duration: {test_duration:.2f} seconds")
    print(f"- Average time per proxy: {test_duration/10:.2f} seconds")

    # Test semaphore functionality
    print(f"\n🔒 Testing Concurrency Control:")
    semaphore = pm.get_request_semaphore()
    print(f"- Semaphore initialized: {'✓' if semaphore else '✗'}")
    print(f"- Max concurrent requests: {pm.max_concurrent_requests}")
    print(f"- Available permits: {semaphore._value if semaphore else 'N/A'}")

    # Test proxy rotation
    if pm.proxies:
        print(f"\n🔄 Testing Proxy Rotation:")
        current = pm.get_current_proxy()
        print(f"- Current proxy: {current.host}:{current.port}")

        pm.rotate_proxy()
        rotated = pm.get_current_proxy()
        print(f"- After rotation: {rotated.host}:{rotated.port}")
        print(f"- Rotation working: {'✓' if current != rotated else '✗'}")

    print(f"\n✅ All tests completed!")
    print(f"\nRecommendations:")
    print(f"- For optimal performance, use 5-10 concurrent requests")
    print(
        f"- Current setting: {pm.max_concurrent_requests} concurrent requests")
    print(f"- Health monitoring tests proxies individually for accuracy")

if __name__ == "__main__":
    asyncio.run(test_proxy_health_monitoring())
