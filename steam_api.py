"""
Steam Community Market API client
Integrates with Steam Market API for CS2 item prices with rate limiting
"""

import aiohttp
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import logging
import os
from dotenv import load_dotenv
import time

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
        self.session = aiohttp.ClientSession(
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

    def _check_rate_limit(self):
        """Check if we can make a request without exceeding rate limits"""
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

    async def _rate_limited_request(self, url: str, params: Dict[str, Any]) -> Optional[Dict]:
        """Make a rate-limited request to the Steam Market API"""
        if not self.session:
            raise RuntimeError(
                "API client not initialized. Use async context manager.")

        # Check rate limit
        sleep_time = self._check_rate_limit()
        if sleep_time > 0:
            logger.info(
                "Rate limit reached, sleeping for %.2f seconds", sleep_time)
            await asyncio.sleep(sleep_time)

        try:
            # Record the request timestamp
            self.request_timestamps.append(time.time())

            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                elif response.status == 429:
                    logger.warning("Rate limited by Steam API, backing off")
                    await asyncio.sleep(60)  # Back off for 1 minute
                    return None
                elif response.status == 500:
                    logger.warning(
                        "Steam API server error for params: %s", params)
                    return None
                else:
                    logger.error(
                        "Steam API error: %s for params: %s", response.status, params)
                    return None

        except asyncio.TimeoutError:
            logger.error("Steam API request timed out")
            return None
        except Exception as e:
            logger.error("Steam API request failed: %s", e)
            return None

    async def get_item_price(self, market_hash_name: str, currency: int = 3) -> Optional[Dict]:
        """
        Get price data for a single item from Steam Market API

        Args:
            market_hash_name: Steam market hash name (URL encoded)
            currency: Currency code (3 = EUR, 1 = USD, etc.)

        Returns:
            Price data dictionary or None if not found
        """
        # Check cache first
        cache_key = f"{market_hash_name}_{currency}"
        now = datetime.now()

        if cache_key in self.cache:
            cache_entry = self.cache[cache_key]
            if now - cache_entry["timestamp"] < self.cache_ttl:
                logger.debug("Cache hit for %s", market_hash_name)
                return cache_entry["data"]

        # Make API request
        params = {
            "appid": "730",  # CS2 app ID
            "currency": str(currency),
            "market_hash_name": market_hash_name
        }

        try:
            data = await self._rate_limited_request(self.base_url, params)

            if data and data.get("success"):
                # Cache the result
                self.cache[cache_key] = {
                    "data": data,
                    "timestamp": now
                }
                logger.debug(
                    "Successfully fetched price for %s", market_hash_name)
                return data
            else:
                logger.warning("No valid price data for %s", market_hash_name)
                return None

        except (aiohttp.ClientError, ConnectionError, ValueError) as e:
            logger.error("Failed to get price for %s: %s", market_hash_name, e)
            return None

    async def get_multiple_prices(self, market_hash_names: List[str], currency: int = 3) -> Dict[str, Dict]:
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
                price_data = await self.get_item_price(item_name, currency)
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
        """Get cache statistics"""
        now = datetime.now()
        valid_entries = sum(
            1 for entry in self.cache.values()
            if now - entry["timestamp"] < self.cache_ttl
        )

        return {
            "total_entries": len(self.cache),
            "valid_entries": valid_entries,
            "expired_entries": len(self.cache) - valid_entries,
            "cache_ttl_minutes": self.cache_ttl.total_seconds() / 60,
            "rate_limit": self.rate_limit,
            "rate_window": self.rate_window,
            "requests_in_window": len(self.request_timestamps)
        }


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
    async with steam_client:
        return await steam_client.get_item_price(market_hash_name, currency)
