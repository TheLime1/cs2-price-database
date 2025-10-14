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

# Set up dedicated logger for success-only responses (overwrite mode for clean logs)
success_only_logger = logging.getLogger('success_only')
if not success_only_logger.handlers:  # Only add handler if it doesn't exist
    # Ensure logs directory exists
    import os
    log_dir = os.getenv("LOG_DIR", "logs")
    os.makedirs(log_dir, exist_ok=True)

    success_only_log_file = os.path.join(log_dir, os.getenv(
        "SUCCESS_ONLY_LOG_FILE", "success_only_responses.log"))
    success_only_handler = logging.FileHandler(
        success_only_log_file, mode='w', encoding='utf-8')  # Use overwrite mode
    success_only_formatter = logging.Formatter('%(asctime)s | %(message)s')
    success_only_handler.setFormatter(success_only_formatter)
    success_only_logger.addHandler(success_only_handler)
    success_only_logger.setLevel(logging.INFO)
    success_only_logger.propagate = False  # Don't send to parent loggers


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
        """Make a rate-limited request to the Steam Market API with enhanced proxy support and 19 req/min limiting

        NEVER gives up on an item due to proxy failures - will keep retrying with different proxies
        until successful or Steam API itself returns an error (not proxy-related).
        """
        if not self.session:
            raise RuntimeError(
                "API client not initialized. Use async context manager.")

        # Use semaphore to control concurrent requests when using proxies (now 100 concurrent)
        semaphore = None
        if proxy_manager.use_proxies:
            semaphore = proxy_manager.get_request_semaphore()

        # Acquire semaphore if using proxies
        if semaphore:
            await semaphore.acquire()

        try:
            return await self._try_request_with_all_proxies(url, params)
        finally:
            # Release semaphore if we acquired it
            if semaphore:
                semaphore.release()

    async def _try_request_with_all_proxies(self, url: str, params: Dict[str, Any]) -> tuple[Optional[Dict], float]:
        """Try request with all available proxies until success or legitimate API error"""
        max_proxy_cycles = 5  # Try cycling through all proxies up to 5 times
        max_attempts_per_proxy = 3  # Max attempts per individual proxy
        total_attempts = 0
        max_total_attempts = 50  # Absolute maximum to prevent infinite loops

        logger.debug(
            f"Starting aggressive proxy retry for item: {params.get('market_hash_name', 'unknown')}")

        for cycle in range(max_proxy_cycles):
            current_proxy = proxy_manager.get_next_available_proxy()

            # If no proxies are available at all, wait and try again
            if not current_proxy and proxy_manager.use_proxies:
                logger.warning(
                    f"No proxies available (cycle {cycle + 1}/{max_proxy_cycles}), waiting 2 seconds before retry...")
                await asyncio.sleep(2.0)
                continue

            for _ in range(max_attempts_per_proxy):
                total_attempts += 1
                if total_attempts > max_total_attempts:
                    logger.error(
                        f"🚫 NEVER SKIP: Reached maximum total attempts ({max_total_attempts}) for {params.get('market_hash_name', 'unknown')} - this should never happen!")
                    return None, 0.0

                result = await self._try_single_request(url, params, current_proxy, total_attempts)

                # Check result type
                if result[0] == "success":
                    logger.debug(
                        f"✅ Successfully retrieved data for {params.get('market_hash_name', 'unknown')} after {total_attempts} attempts")
                    return result[1], 0.0
                elif result[0] == "api_error":
                    logger.debug(
                        f"🔴 Legitimate Steam API error for {params.get('market_hash_name', 'unknown')} - not retrying")
                    return None, 0.0  # Legitimate API error, don't retry
                elif result[0] == "proxy_error":
                    logger.debug(
                        f"🔄 Proxy failed for {params.get('market_hash_name', 'unknown')}, trying next proxy (attempt {total_attempts})")
                    break  # Try next proxy
                # "rate_limit" continues to next proxy

        logger.error(
            f"🚫 NEVER SKIP: Exhausted all proxy retry attempts for {params.get('market_hash_name', 'unknown')} after {total_attempts} attempts across {max_proxy_cycles} cycles")
        return None, 0.0

    async def _try_single_request(self, url: str, params: Dict[str, Any], current_proxy: Optional[Any], attempt_num: int) -> tuple[str, Optional[Dict]]:
        """Try a single request with the given proxy. Returns (result_type, data)"""
        if not self.session:
            return ("api_error", None)

        try:
            # Check if we can make a request with this proxy
            if current_proxy and not proxy_manager.can_make_request(current_proxy):
                logger.debug(
                    f"Proxy {current_proxy.host}:{current_proxy.port} is rate limited, getting next proxy")
                return ("proxy_error", None)

            return await self._execute_request(url, params, current_proxy, attempt_num)

        except asyncio.TimeoutError:
            proxy_info = f"{current_proxy.host}:{current_proxy.port}" if current_proxy else "direct"
            logger.warning(
                f"Request timed out via proxy {proxy_info} - trying next proxy")
            if current_proxy:
                proxy_manager.mark_proxy_failed(current_proxy)
            return ("proxy_error", None)
        except (aiohttp.ClientProxyConnectionError, aiohttp.ClientHttpProxyError) as e:
            proxy_info = f"{current_proxy.host}:{current_proxy.port}" if current_proxy else "direct"
            logger.warning(
                f"Proxy connection error with {proxy_info}: {e} - trying next proxy")
            if current_proxy:
                proxy_manager.mark_proxy_failed(current_proxy)
            return ("proxy_error", None)
        except Exception as e:
            proxy_info = f"{current_proxy.host}:{current_proxy.port}" if current_proxy else "direct"
            logger.warning(
                f"Request failed via proxy {proxy_info}: {e} - trying next proxy")
            if current_proxy:
                proxy_manager.mark_proxy_failed(current_proxy)
            return ("proxy_error", None)

    async def _execute_request(self, url: str, params: Dict[str, Any], current_proxy: Optional[Any], attempt_num: int) -> tuple[str, Optional[Dict]]:
        """Execute the actual HTTP request"""
        if not self.session:
            return ("api_error", None)

        # Record the request for rate limiting
        if current_proxy:
            proxy_manager.record_request(current_proxy)

        # Log proxy usage
        proxy_info = f"{current_proxy.host}:{current_proxy.port}" if current_proxy else "direct"
        logger.debug(f"Using proxy: {proxy_info} (attempt {attempt_num})")

        proxy_url = current_proxy.url if current_proxy else None
        proxy_auth = current_proxy.auth if current_proxy else None

        request_start = time.time()
        async with self.session.get(
            url,
            params=params,
            proxy=proxy_url,
            proxy_auth=proxy_auth
        ) as response:
            request_time = time.time() - request_start
            data = await response.json() if response.status == 200 else None
            return self._handle_response(response, current_proxy, request_time, attempt_num, params, data)

    def _handle_response(self, response, current_proxy: Optional[Any], request_time: float, attempt_num: int, params: Dict[str, Any], data: Optional[Dict]) -> tuple[str, Optional[Dict]]:
        """Handle the HTTP response"""
        if response.status == 200:
            # Mark proxy as successful if used
            if current_proxy:
                proxy_manager.mark_proxy_success(current_proxy, request_time)
            logger.debug(f"✅ Success after {attempt_num} attempts")
            return ("success", data)
        elif response.status == 429:
            proxy_info = f"{current_proxy.host}:{current_proxy.port}" if current_proxy else "direct"
            logger.warning(
                f"Rate limited by Steam API via proxy {proxy_info} - rotating proxy")
            if current_proxy:
                proxy_manager.handle_rate_limit(current_proxy)
            return ("rate_limit", None)
        elif response.status in [500, 404]:
            # Steam API server error or item not found - legitimate failure
            logger.warning(
                f"Steam API returned {response.status} for params: {params}")
            return ("api_error", None)
        else:
            return self._handle_error_response(response, current_proxy)

    def _handle_error_response(self, response, current_proxy: Optional[Any]) -> tuple[str, Optional[Dict]]:
        """Handle non-success HTTP responses"""
        logger.warning(
            f"Steam API error {response.status} - trying next proxy")
        if current_proxy and response.status in [403, 407, 502, 503]:
            proxy_manager.mark_proxy_failed(current_proxy)
            return ("proxy_error", None)
        elif response.status in [400, 401, 405]:
            return ("api_error", None)  # Legitimate API error
        else:
            if current_proxy:
                proxy_manager.mark_proxy_failed(current_proxy)
            return ("proxy_error", None)

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

        # Construct the full API endpoint URL for detailed logging
        import urllib.parse
        query_string = urllib.parse.urlencode(params)
        full_url = f"{self.base_url}?{query_string}"

        try:
            data, wait_time = await self._rate_limited_request(self.base_url, params)

            # Log the API request and response details for debugging
            logger.info(f"🌐 API REQUEST: {full_url}")
            logger.info(f"🔄 API RESPONSE: {data}")

            if data and data.get("success"):
                # Check if we only got {"success": true} without actual price data
                if len(data) == 1 and "success" in data and data["success"] is True:
                    # Construct the full API endpoint URL for debugging
                    import urllib.parse
                    query_string = urllib.parse.urlencode(params)
                    full_url = f"{self.base_url}?{query_string}"

                    # Log to dedicated success-only log file
                    success_only_logger.info(f"ITEM: {market_hash_name}")
                    success_only_logger.info(f"URL: {full_url}")
                    success_only_logger.info(f"RESPONSE: {data}")
                    success_only_logger.info(
                        "REASON: Item exists but has no market data or is not tradeable")
                    success_only_logger.info("-" * 80)

                    # Also log to main logger for debug visibility
                    logger.warning(
                        f"🔍 DEBUG: Steam API returned only {{'success': true}} for item: {market_hash_name}")
                    logger.warning(f"🔗 API Endpoint: {full_url}")
                    logger.warning(
                        "This usually means the item exists but has no market data or is not tradeable")

                    # Return None since we don't have actual price data
                    return None, wait_time

                # Cache the result (only if we have actual price data)
                self.cache[cache_key] = {
                    "data": data,
                    "timestamp": now
                }
                logger.debug(
                    "Successfully fetched price for %s", market_hash_name)
                return data, wait_time
            else:
                logger.warning("No valid price data for %s", market_hash_name)
                logger.info(f"🌐 API REQUEST: {full_url}")
                logger.info(f"🔄 API RESPONSE: {data}")
                return None, wait_time

        except (aiohttp.ClientError, ConnectionError, ValueError) as e:
            logger.error("Failed to get price for %s: %s", market_hash_name, e)
            logger.info(f"🌐 API REQUEST: {full_url}")
            logger.info(f"❌ API ERROR: {str(e)}")
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
