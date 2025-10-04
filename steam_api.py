"""
Steam Community Market API client
Integrates with Steam Market API for CS2 item prices with rate limiting and proxy support
"""

import aiohttp
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import logging
import os
from dotenv import load_dotenv
import time
from proxy_manager import proxy_manager

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class SteamMarketAPIClient:
    """Steam Community Market API client for CS2 item prices with rate limiting"""

    def __init__(self):
        self.base_url = os.getenv(
            "STEAM_MARKET_API_URL", "https://steamcommunity.com/market/priceoverview/")
        self.rate_limit = int(os.getenv("STEAM_API_RATE_LIMIT", "20"))
        self.rate_window = int(os.getenv("STEAM_API_RATE_WINDOW", "60"))
        self.session: Optional[aiohttp.ClientSession] = None
        self.cache: Dict[str, Dict] = {}
        self.cache_ttl = timedelta(minutes=5)  # Cache for 5 minutes
        self.last_request_time = 0
        self.request_count = 0
        self.request_timestamps = []

    async def __aenter__(self):
        # Start proxy health monitoring and ensure proxies are loaded
        await proxy_manager.ensure_proxies_loaded()
        await proxy_manager.start_health_monitoring()

        # Create connector with proxy support
        connector = aiohttp.TCPConnector(
            limit=100,
            limit_per_host=30,
            ttl_dns_cache=300,
            use_dns_cache=True,
        )

        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=30),
            headers={
                "User-Agent": "CS2-TradeUp-Scanner/1.0",
                "Accept": "application/json"
            }
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
        # Stop proxy health monitoring
        await proxy_manager.stop_health_monitoring()

    def _check_rate_limit(self):
        """Check if we can make a request without exceeding rate limits"""
        # If rate_limit is 0, disable rate limiting (unlimited mode)
        if self.rate_limit <= 0:
            return 0

        now = time.time()

        # Remove timestamps older than the rate window
        self.request_timestamps = [
            timestamp for timestamp in self.request_timestamps
            if now - timestamp < self.rate_window
        ]

        # Check if we're at the rate limit
        if len(self.request_timestamps) >= self.rate_limit:
            oldest_request = min(self.request_timestamps)
            sleep_time = self.rate_window - (now - oldest_request)
            if sleep_time > 0:
                return sleep_time

        return 0

    async def _rate_limited_request(self, url: str, params: Dict[str, Any]) -> tuple[Optional[Dict], float]:
        """Make a rate-limited request to the Steam Market API with proxy support and concurrency control, returns (response, wait_time)"""
        if not self.session:
            raise RuntimeError(
                "API client not initialized. Use async context manager.")

        # Use semaphore to control concurrent requests when using proxies
        semaphore = None
        if proxy_manager.use_proxies:
            semaphore = proxy_manager.get_request_semaphore()

        # Acquire semaphore if using proxies
        if semaphore:
            await semaphore.acquire()

        try:
            # Check rate limit
            sleep_time = self._check_rate_limit()
            wait_time = 0.0
            if sleep_time > 0:
                logger.info(
                    "Rate limit reached, sleeping for %.2f seconds", sleep_time)
                wait_time = sleep_time
                await asyncio.sleep(sleep_time)

            # Get current proxy
            current_proxy = proxy_manager.get_current_proxy()
            proxy_url = current_proxy.url if current_proxy else None
            proxy_auth = current_proxy.auth if current_proxy else None

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # Record the request timestamp
                    self.request_timestamps.append(time.time())

                    # Log proxy usage
                    if current_proxy:
                        logger.debug(
                            f"Using proxy: {current_proxy.host}:{current_proxy.port}")

                    request_start = time.time()
                    async with self.session.get(
                        url,
                        params=params,
                        proxy=proxy_url,
                        proxy_auth=proxy_auth
                    ) as response:
                        request_time = time.time() - request_start

                        if response.status == 200:
                            data = await response.json()
                            # Mark proxy as successful if used
                            if current_proxy:
                                proxy_manager.mark_proxy_success(
                                    current_proxy, request_time)
                            return data, wait_time
                        elif response.status == 429:
                            logger.warning(
                                "Rate limited by Steam API, rotating proxy")
                            # Mark current proxy as failed and rotate
                            if current_proxy:
                                proxy_manager.mark_proxy_failed(current_proxy)
                                if attempt < max_retries - 1:
                                    proxy_manager.rotate_proxy()
                                    current_proxy = proxy_manager.get_current_proxy()
                                    proxy_url = current_proxy.url if current_proxy else None
                                    proxy_auth = current_proxy.auth if current_proxy else None
                                    logger.info(
                                        f"Rotated to proxy: {current_proxy.host}:{current_proxy.port}" if current_proxy else "No proxy available")
                                    continue
                            # If no proxy or last attempt, back off briefly
                            backoff_time = 5.0  # Reduced from 60s
                            wait_time += backoff_time
                            await asyncio.sleep(backoff_time)
                            return None, wait_time
                        elif response.status == 500:
                            logger.warning(
                                "Steam API server error for params: %s", params)
                            return None, wait_time
                        else:
                            logger.error(
                                "Steam API error: %s for params: %s", response.status, params)
                            # For non-200 responses, consider it a proxy failure if proxy was used
                            if current_proxy and response.status in [403, 407, 502, 503]:
                                proxy_manager.mark_proxy_failed(current_proxy)
                                if attempt < max_retries - 1:
                                    proxy_manager.rotate_proxy()
                                    current_proxy = proxy_manager.get_current_proxy()
                                    proxy_url = current_proxy.url if current_proxy else None
                                    proxy_auth = current_proxy.auth if current_proxy else None
                                    continue
                            return None, wait_time

                except asyncio.TimeoutError:
                    logger.error("Steam API request timed out")
                    if current_proxy:
                        proxy_manager.mark_proxy_failed(current_proxy)
                        if attempt < max_retries - 1:
                            proxy_manager.rotate_proxy()
                            current_proxy = proxy_manager.get_current_proxy()
                            proxy_url = current_proxy.url if current_proxy else None
                            proxy_auth = current_proxy.auth if current_proxy else None
                            continue
                    return None, wait_time
                except (aiohttp.ClientProxyConnectionError, aiohttp.ClientHttpProxyError) as e:
                    logger.error(f"Proxy connection error: {e}")
                    if current_proxy:
                        proxy_manager.mark_proxy_failed(current_proxy)
                        if attempt < max_retries - 1:
                            proxy_manager.rotate_proxy()
                            current_proxy = proxy_manager.get_current_proxy()
                            proxy_url = current_proxy.url if current_proxy else None
                            proxy_auth = current_proxy.auth if current_proxy else None
                            continue
                    return None, wait_time
                except Exception as e:
                    logger.error("Steam API request failed: %s", e)
                    if current_proxy and attempt < max_retries - 1:
                        proxy_manager.mark_proxy_failed(current_proxy)
                        proxy_manager.rotate_proxy()
                        current_proxy = proxy_manager.get_current_proxy()
                        proxy_url = current_proxy.url if current_proxy else None
                        proxy_auth = current_proxy.auth if current_proxy else None
                        continue
                    return None, wait_time

            return None, wait_time

        finally:
            # Release semaphore if we acquired it
            if semaphore:
                semaphore.release()

    async def get_item_price(self, market_hash_name: str, currency: int = 1) -> tuple[Optional[Dict], float]:
        """
        Get price data for a single item from Steam Market API

        Args:
            market_hash_name: Steam market hash name (URL encoded)
            currency: Currency code (1 = USD, 3 = EUR, etc.)

        Returns:
            Tuple of (Price data dictionary or None if not found, wait_time in seconds)
        """
        # Check cache first
        cache_key = f"{market_hash_name}_{currency}"
        now = datetime.now()

        if cache_key in self.cache:
            cache_entry = self.cache[cache_key]
            if now - cache_entry["timestamp"] < self.cache_ttl:
                logger.debug("Cache hit for %s", market_hash_name)
                return cache_entry["data"], 0.0

        # Make API request
        params = {
            "appid": "730",  # CS2 app ID
            "currency": str(currency),
            "market_hash_name": market_hash_name
        }

        try:
            data, wait_time = await self._rate_limited_request(self.base_url, params)

            if data and data.get("success"):
                # Cache the result
                self.cache[cache_key] = {
                    "data": data,
                    "timestamp": now
                }
                logger.debug(
                    "Successfully fetched price for %s", market_hash_name)
                return data, wait_time
            else:
                logger.warning("No valid price data for %s", market_hash_name)
                return None, wait_time

        except (aiohttp.ClientError, ConnectionError, ValueError) as e:
            logger.error("Failed to get price for %s: %s", market_hash_name, e)
            return None, 0.0

    async def get_multiple_prices(self, market_hash_names: List[str], currency: int = 1) -> Dict[str, Dict]:
        """
        Get price data for multiple items (with rate limiting)

        Args:
            market_hash_names: List of Steam market hash names
            currency: Currency code

        Returns:
            Dictionary mapping hash names to price data
        """
        results = {}

        # Process items one by one due to rate limiting
        for item_name in market_hash_names:
            try:
                price_data, _ = await self.get_item_price(item_name, currency)
                if price_data:
                    results[item_name] = price_data
                else:
                    logger.warning("No price data found for: %s", item_name)

                # Small delay between requests to be respectful
                await asyncio.sleep(0.1)

            except (aiohttp.ClientError, ConnectionError, ValueError) as e:
                logger.error("Error fetching price for %s: %s", item_name, e)
                continue

        return results

    def clear_cache(self):
        """Clear the price cache"""
        self.cache.clear()
        logger.info("Price cache cleared")

    def get_cache_stats(self) -> Dict:
        """Get cache and proxy statistics"""
        now = datetime.now()
        valid_entries = sum(
            1 for entry in self.cache.values()
            if now - entry["timestamp"] < self.cache_ttl
        )

        cache_stats = {
            "total_entries": len(self.cache),
            "valid_entries": valid_entries,
            "expired_entries": len(self.cache) - valid_entries,
            "cache_ttl_minutes": self.cache_ttl.total_seconds() / 60,
            "rate_limit": self.rate_limit,
            "rate_window": self.rate_window,
            "requests_in_window": len(self.request_timestamps)
        }

        # Add proxy stats
        proxy_stats = proxy_manager.get_proxy_stats()
        cache_stats["proxy"] = proxy_stats

        return cache_stats


# Global client instance
steam_client = SteamMarketAPIClient()


async def get_steam_prices(market_hash_names: List[str], currency: int = 3) -> Dict[str, Dict]:
    """
    Convenience function to get Steam Market prices with rate limiting

    Args:
        market_hash_names: List of Steam market hash names
        currency: Currency code (3 = EUR, 1 = USD, etc.)

    Returns:
        Dictionary mapping hash names to price data
    """
    async with steam_client:
        return await steam_client.get_multiple_prices(market_hash_names, currency)


async def get_steam_price(market_hash_name: str, currency: int = 3) -> Optional[Dict]:
    """
    Convenience function to get a single Steam Market price

    Args:
        market_hash_name: Steam market hash name
        currency: Currency code

    Returns:
        Price data dictionary or None if not found
    """
    steam_client = SteamMarketAPIClient()
    async with steam_client:
        price_data, _ = await steam_client.get_item_price(market_hash_name, currency)
        return price_data
