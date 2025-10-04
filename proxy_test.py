"""
Proxy Management Utility
Test proxies, check health, and manage proxy configuration
"""

import asyncio
import sys
import argparse
from proxy_manager import proxy_manager
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_all_proxies():
    """Test all configured proxies"""
    print("Testing all proxies...")
    await proxy_manager.health_check_all_proxies()

    stats = proxy_manager.get_proxy_stats()
    if not stats["enabled"]:
        print("Proxy support is disabled")
        return

    print(f"\nProxy Test Results:")
    print(f"Total proxies: {stats['total_proxies']}")
    print(f"Healthy proxies: {stats['healthy_proxies']}")
    print(f"Current proxy: {stats['current_proxy']}")

    print("\nDetailed Results:")
    for proxy in stats["proxies"]:
        status = "✓ Healthy" if proxy["is_healthy"] else "✗ Failed"
        print(f"  {proxy['host']}:{proxy['port']} - {status} "
              f"(Success: {proxy['success_count']}, Failures: {proxy['failure_count']}, "
              f"Response: {proxy['response_time']:.3f}s)")


async def add_proxy(host: str, port: int, username: str = None, password: str = None, protocol: str = "http"):
    """Add a new proxy to the configuration"""
    proxy_manager.add_proxy(host, port, username, password, protocol)
    print(f"Added proxy: {protocol}://{host}:{port}")

    # Test the new proxy
    for proxy in proxy_manager.proxies:
        if proxy.host == host and proxy.port == port:
            result = await proxy_manager.test_proxy(proxy)
            status = "✓ Working" if result else "✗ Failed"
            print(f"Test result: {status}")
            break


async def show_stats():
    """Show proxy statistics"""
    stats = proxy_manager.get_proxy_stats()

    if not stats["enabled"]:
        print("Proxy support is disabled")
        print("To enable proxies, set USE_PROXIES=true in your .env file")
        return

    print("Proxy Statistics:")
    print(f"  Total proxies: {stats['total_proxies']}")
    print(f"  Healthy proxies: {stats['healthy_proxies']}")
    print(f"  Current proxy: {stats['current_proxy']}")

    if stats["proxies"]:
        print("\nProxy Details:")
        for proxy in stats["proxies"]:
            status = "Healthy" if proxy["is_healthy"] else "Failed"
            print(f"  {proxy['protocol']}://{proxy['host']}:{proxy['port']}")
            print(f"    Status: {status}")
            print(
                f"    Success/Failure: {proxy['success_count']}/{proxy['failure_count']}")
            print(f"    Average response time: {proxy['response_time']:.3f}s")
            if proxy["last_check"]:
                print(f"    Last check: {proxy['last_check']}")
            print()


async def benchmark_proxy_performance():
    """Benchmark proxy performance"""
    if not proxy_manager.use_proxies or not proxy_manager.proxies:
        print("No proxies configured")
        return

    print("Benchmarking proxy performance...")

    # Test each proxy multiple times
    for proxy in proxy_manager.proxies:
        if not proxy.is_healthy:
            continue

        print(f"\nTesting {proxy.host}:{proxy.port}...")

        times = []
        success_count = 0

        for i in range(5):
            result = await proxy_manager.test_proxy(proxy)
            if result:
                success_count += 1
                times.append(proxy.response_time)
            await asyncio.sleep(0.5)  # Small delay between tests

        if times:
            avg_time = sum(times) / len(times)
            min_time = min(times)
            max_time = max(times)
            success_rate = (success_count / 5) * 100

            print(f"  Success rate: {success_rate:.1f}%")
            print(f"  Average response time: {avg_time:.3f}s")
            print(
                f"  Min/Max response time: {min_time:.3f}s / {max_time:.3f}s")
        else:
            print("  All tests failed")


async def main():
    parser = argparse.ArgumentParser(description="Proxy management utility")
    subparsers = parser.add_subparsers(
        dest="command", help="Available commands")

    # Test command
    subparsers.add_parser("test", help="Test all configured proxies")

    # Stats command
    subparsers.add_parser("stats", help="Show proxy statistics")

    # Benchmark command
    subparsers.add_parser("benchmark", help="Benchmark proxy performance")

    # Add proxy command
    add_parser = subparsers.add_parser("add", help="Add a new proxy")
    add_parser.add_argument("host", help="Proxy host")
    add_parser.add_argument("port", type=int, help="Proxy port")
    add_parser.add_argument("--username", help="Proxy username")
    add_parser.add_argument("--password", help="Proxy password")
    add_parser.add_argument("--protocol", default="http",
                            help="Proxy protocol (http, https, socks4, socks5)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    try:
        if args.command == "test":
            await test_all_proxies()
        elif args.command == "stats":
            await show_stats()
        elif args.command == "benchmark":
            await benchmark_proxy_performance()
        elif args.command == "add":
            await add_proxy(args.host, args.port, args.username, args.password, args.protocol)

    except KeyboardInterrupt:
        print("\nOperation cancelled")
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
