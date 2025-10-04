"""
Quick Setup Script for CS2 Price Database with Proxy Support
Helps users configure proxies and test the setup
"""

import os
import asyncio
from steam_api import SteamMarketAPIClient
from proxy_manager import proxy_manager


async def test_basic_api():
    """Test basic API functionality without proxies"""
    print("Testing basic Steam API connection...")

    async with SteamMarketAPIClient() as client:
        # Test with a common skin
        test_item = "AK-47 | Redline (Field-Tested)"
        result, _ = await client.get_item_price(test_item)

        if result and result.get("success"):
            print(f"✓ Steam API is working")
            print(f"  Test item: {test_item}")
            print(f"  Price: {result.get('lowest_price', 'N/A')}")
            return True
        else:
            print("✗ Steam API test failed")
            return False


async def test_proxy_api():
    """Test API functionality with proxies"""
    if not proxy_manager.use_proxies:
        print("Proxies are disabled. To enable:")
        print("1. Set USE_PROXIES=true in your .env file")
        print("2. Configure proxies in proxies.txt or PROXY_LIST")
        return False

    print("Testing Steam API with proxy support...")

    # Check proxy stats
    stats = proxy_manager.get_proxy_stats()
    print(f"Loaded {stats['total_proxies']} proxies")

    if stats['healthy_proxies'] == 0:
        print("No healthy proxies available")
        return False

    async with SteamMarketAPIClient() as client:
        # Test with a common skin
        test_item = "AK-47 | Redline (Field-Tested)"
        result, _ = await client.get_item_price(test_item)

        if result and result.get("success"):
            current_proxy = proxy_manager.get_current_proxy()
            proxy_info = f"{current_proxy.host}:{current_proxy.port}" if current_proxy else "Direct"
            print(f"✓ Steam API with proxy is working")
            print(f"  Using proxy: {proxy_info}")
            print(f"  Test item: {test_item}")
            print(f"  Price: {result.get('lowest_price', 'N/A')}")
            return True
        else:
            print("✗ Steam API with proxy test failed")
            return False


def setup_environment():
    """Setup .env file if it doesn't exist"""
    if os.path.exists('.env'):
        print("✓ .env file already exists")
        return

    if os.path.exists('.env.example'):
        print("Creating .env file from .env.example...")
        with open('.env.example', 'r') as src, open('.env', 'w') as dst:
            dst.write(src.read())
        print("✓ .env file created")
        print("  Edit .env to configure proxy settings")
    else:
        print("Creating basic .env file...")
        env_content = """# CS2 Price Database Configuration
STEAM_API_RATE_LIMIT=20
STEAM_API_RATE_WINDOW=60

# Proxy Configuration
USE_PROXIES=false
PROXY_LIST=
PROXY_FILE=proxies.txt
"""
        with open('.env', 'w') as f:
            f.write(env_content)
        print("✓ Basic .env file created")


def setup_proxy_file():
    """Setup proxy file if it doesn't exist"""
    if os.path.exists('proxies.txt'):
        print("✓ proxies.txt already exists")
        return

    print("Creating sample proxies.txt file...")
    proxy_content = """# Proxy Configuration File
# Format: protocol://[username:password@]host:port
# Or simply: host:port (assumes HTTP)
# Lines starting with # are ignored

# Example HTTP proxies (replace with real proxies)
# proxy1.example.com:8080
# user:pass@proxy2.example.com:3128

# Example SOCKS proxies  
# socks5://proxy3.example.com:1080

# Add your proxy servers here:
"""
    with open('proxies.txt', 'w') as f:
        f.write(proxy_content)
    print("✓ Sample proxies.txt created")
    print("  Add your proxy servers to this file")


async def main():
    print("CS2 Price Database - Proxy Setup")
    print("=" * 40)

    # Setup files
    setup_environment()
    setup_proxy_file()

    print("\nTesting configuration...")
    print("-" * 30)

    # Test basic API
    basic_works = await test_basic_api()

    if basic_works:
        # Test with proxies if enabled
        proxy_works = await test_proxy_api()

        if proxy_works:
            print("\n✓ Setup complete! Ready to collect prices with proxy support")
        elif proxy_manager.use_proxies:
            print("\n⚠ Proxy configuration needs attention")
            print("  Check your proxy settings in .env and proxies.txt")
            print("  Run 'python proxy_test.py test' to test individual proxies")
        else:
            print("\n✓ Setup complete! Ready to collect prices (no proxy)")
            print("  To enable proxy support:")
            print("  1. Set USE_PROXIES=true in .env")
            print("  2. Add proxies to proxies.txt or PROXY_LIST")
    else:
        print("\n✗ Basic API test failed")
        print("  Check your internet connection and Steam API availability")

    print("\nNext steps:")
    print("1. python collect_prices.py --limit 5  # Test with 5 skins")
    print("2. python proxy_test.py stats          # Check proxy status")
    print("3. python collect_prices.py            # Full collection")


if __name__ == "__main__":
    asyncio.run(main())
