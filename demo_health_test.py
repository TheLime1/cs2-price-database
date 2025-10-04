#!/usr/bin/env python3
"""
Demonstration of proxy health testing
"""

import asyncio
import os
import sys
from proxy_manager import ProxyManager


async def demonstrate_health_testing():
    """Show how proxy health testing works"""
    print("🩺 Proxy Health Testing Demonstration")
    print("=" * 50)

    # Set environment variables
    os.environ['USE_PROXIES'] = 'true'
    os.environ['MAX_CONCURRENT_REQUESTS'] = '5'
    os.environ['ENABLE_PROXY_HEALTH_CHECK'] = 'true'  # Enable health checking

    # Create proxy manager with first 5 proxies for quick demo
    pm = ProxyManager()

    # Manually add a few test proxies instead of loading all 1525
    print("📋 Adding test proxies for demonstration...")

    # Fetch first 5 proxies from GitHub for quick testing
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
                        if not line or line.startswith('#') or 'Format:' in line:
                            continue

                        proxy = pm._parse_proxy_string(line)
                        if proxy:
                            pm.proxies.append(proxy)
                            count += 1
                            if count >= 5:  # Only test 5 proxies for demo
                                break

                    print(f"✓ Added {len(pm.proxies)} test proxies")
    except Exception as e:
        print(f"✗ Error fetching proxies: {e}")
        return

    if not pm.proxies:
        print("✗ No proxies to test")
        return

    print(f"\n🔍 Health Testing Process:")
    print(f"- Test URL: http://httpbin.org/ip")
    print(f"- Timeout: 3 seconds per proxy")
    print(f"- Method: GET request through each proxy")
    print(f"- Success: HTTP 200 response")

    print(f"\n⏳ Testing {len(pm.proxies)} proxies one by one...")

    # Show before testing
    print(f"\n📊 Before Testing:")
    for i, proxy in enumerate(pm.proxies, 1):
        print(f"  {i}. {proxy.host}:{proxy.port} - Status: Unknown")

    # Run health testing
    start_time = asyncio.get_event_loop().time()
    await pm._test_and_filter_proxies_sequential()
    end_time = asyncio.get_event_loop().time()

    # Show results
    print(f"\n📊 After Testing:")
    working_proxies = len(pm.proxies)
    total_tested = 5  # We tested 5 proxies
    failed_proxies = total_tested - working_proxies

    for i, proxy in enumerate(pm.proxies, 1):
        print(f"  {i}. {proxy.host}:{proxy.port} - Status: ✅ Working")

    if failed_proxies > 0:
        print(f"\n❌ Failed proxies: {failed_proxies} (filtered out)")

    print(f"\n📈 Health Testing Results:")
    print(f"- Total tested: {total_tested}")
    print(f"- Working proxies: {working_proxies}")
    print(f"- Failed proxies: {failed_proxies}")
    print(f"- Success rate: {(working_proxies/total_tested)*100:.1f}%")
    print(f"- Test duration: {end_time - start_time:.2f} seconds")
    print(
        f"- Average per proxy: {(end_time - start_time)/total_tested:.2f} seconds")

    print(f"\n💡 How it works:")
    print(f"1. Each proxy is tested individually (one by one)")
    print(f"2. Makes HTTP GET request to http://httpbin.org/ip through proxy")
    print(f"3. If response status is 200, proxy is considered healthy")
    print(f"4. Failed proxies are removed from the list")
    print(f"5. Only working proxies remain for actual use")

    print(f"\n⚙️ Configuration Options:")
    print(f"- ENABLE_PROXY_HEALTH_CHECK=true  # Enable testing")
    print(f"- Test timeout: 3 seconds (hardcoded)")
    print(f"- Test interval between proxies: 0.1 seconds")

if __name__ == "__main__":
    asyncio.run(demonstrate_health_testing())
