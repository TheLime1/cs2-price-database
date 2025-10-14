"""
Proxy Manager for Steam API Client
Handles proxy rotation, health checking, and automatic failover
"""

import aiohttp
import asyncio
import logging
import random
import time
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class ProxyInfo:
    """Information about a proxy server"""
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    protocol: str = "http"  # http, https, socks4, socks5
    is_healthy: bool = True
    last_check: Optional[datetime] = None
    response_time: float = 0.0
    failure_count: int = 0
    success_count: int = 0
    # Rate limiting tracking
    request_timestamps: Optional[List[float]] = None
    consecutive_rate_limits: int = 0
    last_rate_limit: Optional[datetime] = None
    rate_limit_backoff_until: Optional[datetime] = None

    def __post_init__(self):
        if self.request_timestamps is None:
            self.request_timestamps = []

    @property
    def url(self) -> str:
        """Get the full proxy URL"""
        if self.username and self.password:
            return f"{self.protocol}://{self.username}:{self.password}@{self.host}:{self.port}"
        return f"{self.protocol}://{self.host}:{self.port}"

    @property
    def auth(self) -> Optional[aiohttp.BasicAuth]:
        """Get BasicAuth object if credentials are provided"""
        if self.username and self.password:
            return aiohttp.BasicAuth(self.username, self.password)
        return None


class ProxyManager:
    """Manages proxy rotation and health checking"""

    def __init__(self):
        self.proxies: List[ProxyInfo] = []
        self.current_proxy_index = 0
        self.health_check_interval = 300  # 5 minutes
        self.max_failures = 3
        self.test_url = "https://httpbin.org/ip"
        self.timeout = 10
        self.use_proxies = False
        self.use_direct_ip = False
        self._proxy_fetch_task = None

        # Enhanced concurrency control
        self.max_concurrent_requests = int(
            os.getenv("MAX_CONCURRENT_REQUESTS", "19"))
        self._request_semaphore = None

        # Rate limiting configuration (19 req/min for ALL connections)
        self.max_requests_per_minute = int(
            os.getenv("STEAM_API_RATE_LIMIT", "19"))
        self.rate_limit_window = float(
            os.getenv("STEAM_API_RATE_WINDOW", "60"))
        self.rate_limit_backoff_time = float(
            os.getenv("STEAM_API_RATE_LIMIT_BACKOFF", "65"))
        self.max_consecutive_rate_limits = 5

        # Direct IP rate limiting (shares same limit pool as proxies)
        self.direct_ip_requests = []  # Timestamp tracking for direct IP
        self.last_direct_ip_request = None

        # Load proxy configuration
        self._load_proxy_config()

        # Health check task
        self._health_check_task = None

    def _load_proxy_config(self):
        """Load proxy configuration from environment variables and GitHub source"""
        # Check if proxies and direct IP are enabled
        self.use_proxies = os.getenv("USE_PROXIES", "false").lower() == "true"
        self.use_direct_ip = os.getenv(
            "USE_DIRECT_IP", "false").lower() == "true"

        if not self.use_proxies:
            logger.info("Proxy usage disabled")
            return

        # Load proxies from GitHub source
        if self.use_proxies:
            # Don't create task during init - will be done in ensure_proxies_loaded()
            self._proxy_fetch_task = None

        # Load proxies from environment variable (comma-separated) as backup
        proxy_list = os.getenv("PROXY_LIST", "")
        if proxy_list:
            for proxy_str in proxy_list.split(","):
                proxy_str = proxy_str.strip()
                if proxy_str:
                    proxy = self._parse_proxy_string(proxy_str)
                    if proxy:
                        self.proxies.append(proxy)

        # Load proxies from file as backup
        proxy_file = os.getenv("PROXY_FILE", "proxies.txt")
        if os.path.exists(proxy_file):
            try:
                with open(proxy_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            proxy = self._parse_proxy_string(line)
                            if proxy:
                                self.proxies.append(proxy)
            except Exception as e:
                logger.error(f"Error loading proxy file {proxy_file}: {e}")

        if self.proxies:
            logger.info(f"Loaded {len(self.proxies)} proxies")
            # Shuffle proxies for random starting point
            random.shuffle(self.proxies)
        else:
            logger.info(
                "No static proxies loaded, will fetch from GitHub source")

    async def ensure_proxies_loaded(self):
        """Ensure proxies are loaded from GitHub source"""
        # Initialize semaphore for concurrency control
        if self._request_semaphore is None:
            self._request_semaphore = asyncio.Semaphore(
                self.max_concurrent_requests)
            logger.info(
                f"Initialized semaphore with {self.max_concurrent_requests} concurrent requests")

        if self.use_proxies and not self._proxy_fetch_task:
            # Create the task now that we have an event loop
            self._proxy_fetch_task = asyncio.create_task(
                self._fetch_proxies_from_github())

        if self._proxy_fetch_task and not self._proxy_fetch_task.done():
            try:
                await self._proxy_fetch_task
            except Exception as e:
                logger.error(f"Failed to fetch proxies: {e}")

        if not self.proxies and self.use_proxies:
            logger.warning("No proxies available despite being enabled")
            self.use_proxies = False

    async def _fetch_proxies_from_github(self):
        """Fetch ALL proxies from GitHub source and filter out dead ones"""
        github_url = "https://raw.githubusercontent.com/TheLime1/Validity/refs/heads/main/data/http.txt"

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.get(github_url) as response:
                    if response.status == 200:
                        content = await response.text()
                        raw_proxy_count = 0

                        for line in content.split('\n'):
                            line = line.strip()
                            # Skip comments and empty lines
                            if not line or line.startswith('#') or 'Format:' in line:
                                continue

                            # Parse proxy
                            proxy = self._parse_proxy_string(line)
                            if proxy:
                                self.proxies.append(proxy)
                                raw_proxy_count += 1

                        if self.proxies:
                            logger.info(
                                f"Fetched {len(self.proxies)} raw proxies from GitHub")

                            # Note: Health testing can be enabled with environment variable
                            if os.getenv("ENABLE_PROXY_HEALTH_CHECK", "false").lower() == "true":
                                logger.info(
                                    "🔍 Starting asynchronous proxy health testing...")
                                await self._test_and_filter_proxies_async()
                            else:
                                logger.info(
                                    "Health testing disabled for faster startup (set ENABLE_PROXY_HEALTH_CHECK=true to enable)")

                            if self.proxies:
                                # Shuffle for random starting point
                                random.shuffle(self.proxies)
                                self.use_proxies = True
                                logger.info(
                                    f"Successfully loaded {len(self.proxies)} proxies")
                            else:
                                logger.warning(
                                    "No working proxies found after testing")
                                self.use_proxies = False
                        else:
                            logger.warning(
                                "No valid proxies found in GitHub source")
                    else:
                        logger.error(
                            f"Failed to fetch proxies from GitHub: HTTP {response.status}")

        except Exception as e:
            logger.error(f"Error fetching proxies from GitHub: {e}")
            if not self.proxies:
                logger.warning("No proxies available, proxy support disabled")
                self.use_proxies = False

    async def _test_and_filter_proxies_async(self):
        """Test proxies asynchronously and allow early start when healthy proxies are found"""
        if not self.proxies:
            return

        total_proxies = len(self.proxies)
        logger.info(
            f"🔍 Starting asynchronous health check for {total_proxies} proxies...")
        logger.info(
            "⚡ Will start scraping as soon as healthy proxies are found!")

        # Create shared tracking variables
        self.healthy_proxy_count = 0
        self.proxy_testing_complete = False

        # Start background proxy testing
        self._background_test_task = asyncio.create_task(
            self._test_all_proxies_background())

        # Wait for at least a few healthy proxies before returning
        # At least 1, max 5, or 5% of total
        min_healthy_proxies = min(5, max(1, total_proxies // 20))
        logger.info(
            f"⏳ Waiting for at least {min_healthy_proxies} healthy proxies before starting...")

        # Poll until we have enough healthy proxies or timeout
        timeout_seconds = 30  # Max 30 seconds wait
        start_time = time.time()

        while (self.healthy_proxy_count < min_healthy_proxies and
               not self.proxy_testing_complete and
               time.time() - start_time < timeout_seconds):
            await asyncio.sleep(0.5)

        if self.healthy_proxy_count > 0:
            logger.info(
                f"🚀 Found {self.healthy_proxy_count} healthy proxies - starting scraping!")
            logger.info(f"📊 Proxy testing continues in background...")
        else:
            logger.warning(
                "⚠️ No healthy proxies found yet, but continuing...")

    async def _test_all_proxies_background(self):
        """Background task to test all proxies asynchronously"""
        semaphore = asyncio.Semaphore(10)  # Test up to 10 proxies concurrently

        async def test_single_proxy(proxy, index):
            async with semaphore:
                try:
                    is_working = await self._test_proxy_health(proxy)

                    if is_working:
                        proxy.is_healthy = True
                        proxy.failure_count = 0
                        proxy.success_count += 1
                        self.healthy_proxy_count += 1
                        logger.info(
                            f"✅ HEALTHY #{self.healthy_proxy_count}: {proxy.host}:{proxy.port} ({index}/{len(self.proxies)})")
                    else:
                        proxy.is_healthy = False
                        proxy.failure_count += 1
                        logger.debug(
                            f"❌ FAILED: {proxy.host}:{proxy.port} ({index}/{len(self.proxies)})")

                    # Log progress every 50 proxies
                    if index % 50 == 0:
                        logger.info(
                            f"📊 Progress: {index}/{len(self.proxies)} tested, {self.healthy_proxy_count} healthy")

                except Exception as e:
                    proxy.is_healthy = False
                    proxy.failure_count += 1
                    logger.debug(
                        f"❌ Proxy {index}/{len(self.proxies)}: {proxy.host}:{proxy.port} - ERROR: {e}")

        # Test all proxies concurrently
        tasks = [test_single_proxy(proxy, i+1)
                 for i, proxy in enumerate(self.proxies)]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Remove unhealthy proxies
        working_proxies = [p for p in self.proxies if p.is_healthy]
        removed_count = len(self.proxies) - len(working_proxies)
        self.proxies = working_proxies

        self.proxy_testing_complete = True

        logger.info(f"🎯 Proxy health check complete!")
        logger.info(
            f"📊 Final results: {len(working_proxies)} healthy, {removed_count} removed")

        if not self.proxies:
            logger.warning("⚠️ No working proxies available after filtering!")

    async def _test_proxy_health(self, proxy: ProxyInfo) -> bool:
        """Test if a single proxy is working with Steam API"""
        try:
            proxy_url = f"http://{proxy.host}:{proxy.port}"
            connector = aiohttp.TCPConnector()
            timeout = aiohttp.ClientTimeout(
                total=10)  # 10 seconds for Steam API

            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                # Use Steam API health check endpoint from environment
                test_url = os.getenv("PROXY_HEALTH_CHECK_URL",
                                     "https://steamcommunity.com/market/priceoverview/?appid=730&currency=1&market_hash_name=AK-47")

                async with session.get(test_url, proxy=proxy_url) as response:
                    # Steam API returns 200 for successful requests (even if no price data)
                    # Status 429 means rate limited but proxy is working
                    if response.status in [200, 429]:
                        logger.debug(
                            f"✅ Proxy {proxy.host}:{proxy.port} healthy (Steam API status: {response.status})")
                        return True
                    else:
                        logger.debug(
                            f"❌ Proxy {proxy.host}:{proxy.port} unhealthy (Steam API status: {response.status})")
                        return False
        except Exception as e:
            logger.debug(
                f"❌ Proxy {proxy.host}:{proxy.port} health check failed: {e}")
            return False

    def get_request_semaphore(self) -> asyncio.Semaphore:
        """Get the semaphore for controlling concurrent requests"""
        if self._request_semaphore is None:
            # Fallback if not initialized
            self._request_semaphore = asyncio.Semaphore(
                self.max_concurrent_requests)
        return self._request_semaphore

    def _parse_proxy_string(self, proxy_str: str) -> Optional[ProxyInfo]:
        """Parse a proxy string into ProxyInfo object"""
        try:
            # Support formats:
            # http://host:port
            # http://user:pass@host:port
            # host:port (assumes http)
            # user:pass@host:port (assumes http)

            if "://" in proxy_str:
                protocol, rest = proxy_str.split("://", 1)
            else:
                protocol = "http"
                rest = proxy_str

            # Check for auth
            if "@" in rest:
                auth_part, host_part = rest.rsplit("@", 1)
                if ":" in auth_part:
                    username, password = auth_part.split(":", 1)
                else:
                    username, password = auth_part, ""
            else:
                username, password = None, None
                host_part = rest

            # Parse host and port
            if ":" in host_part:
                host, port_str = host_part.rsplit(":", 1)
                port = int(port_str)
            else:
                host = host_part
                port = 8080  # Default port

            return ProxyInfo(
                host=host,
                port=port,
                username=username,
                password=password,
                protocol=protocol
            )

        except Exception as e:
            logger.error(f"Error parsing proxy string '{proxy_str}': {e}")
            return None

    def get_current_proxy(self) -> Optional[ProxyInfo]:
        """Get the current active proxy"""
        if not self.use_proxies or not self.proxies:
            return None

        # Filter healthy proxies
        healthy_proxies = [p for p in self.proxies if p.is_healthy]
        if not healthy_proxies:
            logger.warning("No healthy proxies available")
            return None

        # Ensure index is within bounds
        if self.current_proxy_index >= len(healthy_proxies):
            self.current_proxy_index = 0

        return healthy_proxies[self.current_proxy_index]

    def can_use_direct_ip(self) -> bool:
        """Check if we can use direct IP (rate limit check)"""
        if not self.use_direct_ip:
            return False

        now = time.time()
        # Clean old requests outside the window
        self.direct_ip_requests = [req_time for req_time in self.direct_ip_requests
                                   if now - req_time < self.rate_limit_window]

        # Check if we're under the rate limit
        return len(self.direct_ip_requests) < self.max_requests_per_minute

    def use_direct_ip_request(self):
        """Record a direct IP request for rate limiting"""
        if self.use_direct_ip:
            now = time.time()
            self.direct_ip_requests.append(now)
            self.last_direct_ip_request = now

    def rotate_proxy(self):
        """Rotate to the next available proxy"""
        if not self.use_proxies or not self.proxies:
            return

        healthy_proxies = [p for p in self.proxies if p.is_healthy]
        if len(healthy_proxies) <= 1:
            return

        self.current_proxy_index = (
            self.current_proxy_index + 1) % len(healthy_proxies)
        current = self.get_current_proxy()
        if current:
            logger.info(f"Rotated to proxy: {current.host}:{current.port}")

    def mark_proxy_failed(self, proxy: ProxyInfo):
        """Mark a proxy as failed and potentially unhealthy"""
        proxy.failure_count += 1
        proxy.last_check = datetime.now()

        if proxy.failure_count >= self.max_failures:
            proxy.is_healthy = False
            logger.warning(
                f"Proxy {proxy.host}:{proxy.port} marked as unhealthy after {proxy.failure_count} failures")
            # Remove from active proxy pool
            self._remove_proxy_from_pool(proxy)

    def mark_proxy_success(self, proxy: ProxyInfo, response_time: float = 0.0):
        """Mark a proxy as successful"""
        proxy.success_count += 1
        proxy.response_time = response_time
        proxy.failure_count = 0  # Reset failure count on success
        proxy.consecutive_rate_limits = 0  # Reset consecutive rate limits on success
        proxy.last_check = datetime.now()

    def can_make_request(self, proxy: ProxyInfo) -> bool:
        """Check if proxy can make a request without exceeding rate limits"""
        if not proxy or not proxy.is_healthy:
            return False

        now = datetime.now()

        # Check if proxy is in backoff period
        if proxy.rate_limit_backoff_until and now < proxy.rate_limit_backoff_until:
            return False

        # Ensure request_timestamps is initialized
        if proxy.request_timestamps is None:
            proxy.request_timestamps = []

        # Clean old timestamps (older than 1 minute)
        current_time = time.time()
        proxy.request_timestamps = [
            ts for ts in proxy.request_timestamps
            if current_time - ts < self.rate_limit_window
        ]

        # Check if we're at the rate limit (19 requests per minute)
        return len(proxy.request_timestamps) < self.max_requests_per_minute

    def record_request(self, proxy: ProxyInfo):
        """Record a request timestamp for rate limiting"""
        if proxy:
            if proxy.request_timestamps is None:
                proxy.request_timestamps = []
            proxy.request_timestamps.append(time.time())

    def handle_rate_limit(self, proxy: ProxyInfo):
        """Handle rate limit response from Steam API"""
        if not proxy:
            return

        proxy.consecutive_rate_limits += 1
        proxy.last_rate_limit = datetime.now()

        # Set 61-second backoff period
        proxy.rate_limit_backoff_until = datetime.now(
        ) + timedelta(seconds=self.rate_limit_backoff_time)

        logger.warning(
            f"Proxy {proxy.host}:{proxy.port} hit rate limit #{proxy.consecutive_rate_limits}. Backing off for {self.rate_limit_backoff_time} seconds")

        # Remove proxy if it hits rate limit 5 consecutive times
        if proxy.consecutive_rate_limits >= self.max_consecutive_rate_limits:
            logger.warning(
                f"Proxy {proxy.host}:{proxy.port} removed after {proxy.consecutive_rate_limits} consecutive rate limits")
            self._remove_proxy_from_pool(proxy)

    def _remove_proxy_from_pool(self, proxy: ProxyInfo):
        """Remove a proxy from the active pool"""
        try:
            self.proxies.remove(proxy)
            logger.info(
                f"Removed proxy {proxy.host}:{proxy.port} from active pool")

            # Adjust current index if necessary
            if self.current_proxy_index >= len(self.proxies) and self.proxies:
                self.current_proxy_index = 0
        except ValueError:
            # Proxy already removed
            pass

    def get_next_available_proxy(self) -> Optional[ProxyInfo]:
        """Get the next available proxy that can make a request"""
        if not self.use_proxies or not self.proxies:
            return None

        healthy_proxies = [p for p in self.proxies if p.is_healthy]
        if not healthy_proxies:
            logger.warning("No healthy proxies available")
            return None

        # Try to find a proxy that can make a request (not rate limited)
        for _ in range(len(healthy_proxies)):
            proxy = healthy_proxies[self.current_proxy_index %
                                    len(healthy_proxies)]

            if self.can_make_request(proxy):
                return proxy

            # Move to next proxy
            self.current_proxy_index = (
                self.current_proxy_index + 1) % len(healthy_proxies)

        # If no proxy is immediately available, return the current one anyway
        # (it will handle the rate limiting internally)
        return healthy_proxies[self.current_proxy_index % len(healthy_proxies)] if healthy_proxies else None

    async def test_proxy(self, proxy: ProxyInfo) -> bool:
        """Test if a proxy is working"""
        try:
            start_time = time.time()

            connector = aiohttp.TCPConnector()
            timeout = aiohttp.ClientTimeout(total=self.timeout)

            async with aiohttp.ClientSession(
                connector=connector,
                timeout=timeout
            ) as session:
                async with session.get(
                    self.test_url,
                    proxy=proxy.url,
                    proxy_auth=proxy.auth
                ) as response:
                    if response.status == 200:
                        response_time = time.time() - start_time
                        self.mark_proxy_success(proxy, response_time)
                        return True
                    else:
                        self.mark_proxy_failed(proxy)
                        return False

        except Exception as e:
            logger.debug(
                f"Proxy test failed for {proxy.host}:{proxy.port}: {e}")
            self.mark_proxy_failed(proxy)
            return False

    async def health_check_all_proxies(self):
        """Perform health check on all proxies"""
        if not self.use_proxies or not self.proxies:
            return

        logger.info("Starting proxy health check...")

        # Test all proxies concurrently
        tasks = [self.test_proxy(proxy) for proxy in self.proxies]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        healthy_count = sum(1 for proxy in self.proxies if proxy.is_healthy)
        logger.info(
            f"Proxy health check completed. {healthy_count}/{len(self.proxies)} proxies healthy")

        # If current proxy is unhealthy, rotate
        current = self.get_current_proxy()
        if current and not current.is_healthy:
            self.rotate_proxy()

    async def start_health_monitoring(self):
        """Start the health monitoring background task"""
        if not self.use_proxies or self._health_check_task:
            return

        async def health_check_loop():
            while True:
                try:
                    await asyncio.sleep(self.health_check_interval)
                    await self.health_check_all_proxies()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error in health check loop: {e}")

        self._health_check_task = asyncio.create_task(health_check_loop())
        logger.info("Started proxy health monitoring")

    async def stop_health_monitoring(self):
        """Stop the health monitoring background task"""
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None
            logger.info("Stopped proxy health monitoring")

    def get_proxy_stats(self) -> Dict[str, Any]:
        """Get proxy statistics"""
        if not self.use_proxies:
            return {"enabled": False}

        healthy_count = sum(1 for proxy in self.proxies if proxy.is_healthy)

        proxy_details = []
        for proxy in self.proxies:
            proxy_details.append({
                "host": proxy.host,
                "port": proxy.port,
                "protocol": proxy.protocol,
                "is_healthy": proxy.is_healthy,
                "success_count": proxy.success_count,
                "failure_count": proxy.failure_count,
                "response_time": proxy.response_time,
                "last_check": proxy.last_check.isoformat() if proxy.last_check else None
            })

        current_proxy = self.get_current_proxy()

        return {
            "enabled": True,
            "total_proxies": len(self.proxies),
            "healthy_proxies": healthy_count,
            "current_proxy": f"{current_proxy.host}:{current_proxy.port}" if current_proxy else None,
            "proxies": proxy_details
        }

    def add_proxy(self, host: str, port: int, username: str = None, password: str = None, protocol: str = "http"):
        """Add a new proxy to the pool"""
        proxy = ProxyInfo(
            host=host,
            port=port,
            username=username,
            password=password,
            protocol=protocol
        )
        self.proxies.append(proxy)
        logger.info(f"Added proxy: {host}:{port}")

    def remove_proxy(self, host: str, port: int):
        """Remove a proxy from the pool"""
        self.proxies = [p for p in self.proxies if not (
            p.host == host and p.port == port)]
        logger.info(f"Removed proxy: {host}:{port}")


# Global proxy manager instance
proxy_manager = ProxyManager()
