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
        self._proxy_fetch_task = None

        # Concurrency control for async proxy usage
        # Recommended: 10 concurrent requests for optimal performance
        self.max_concurrent_requests = int(
            os.getenv("MAX_CONCURRENT_REQUESTS", "10"))
        self._request_semaphore = None

        # Load proxy configuration
        self._load_proxy_config()

        # Health check task
        self._health_check_task = None

    def _load_proxy_config(self):
        """Load proxy configuration from environment variables and GitHub source"""
        # Check if proxies are enabled
        self.use_proxies = os.getenv("USE_PROXIES", "false").lower() == "true"

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
                                    "Testing proxies one by one to filter out dead ones...")
                                await self._test_and_filter_proxies_sequential()
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

    async def _test_and_filter_proxies_sequential(self):
        """Test proxies one by one and remove dead ones"""
        if not self.proxies:
            return

        logger.info(f"Testing {len(self.proxies)} proxies one by one...")
        working_proxies = []
        total_proxies = len(self.proxies)

        for i, proxy in enumerate(self.proxies, 1):
            # Show progress every 50 proxies
            if i % 50 == 0 or i == total_proxies:
                logger.info(
                    f"Testing proxy {i}/{total_proxies}: {proxy.host}:{proxy.port}")

            is_working = await self._test_proxy_health(proxy)
            if is_working:
                working_proxies.append(proxy)
                proxy.is_healthy = True
                proxy.failure_count = 0
                proxy.success_count += 1
            else:
                proxy.is_healthy = False
                proxy.failure_count += 1

            # Small delay to avoid overwhelming the test endpoint
            await asyncio.sleep(0.1)

        # Update the proxy list with only working proxies
        removed_count = len(self.proxies) - len(working_proxies)
        self.proxies = working_proxies

        if removed_count > 0:
            logger.info(
                f"Filtered out {removed_count} dead proxies, {len(self.proxies)} working proxies remain")
        else:
            logger.info(f"All {len(self.proxies)} proxies are working")

    async def _test_proxy_health(self, proxy: ProxyInfo) -> bool:
        """Test if a single proxy is working"""
        try:
            proxy_url = f"http://{proxy.host}:{proxy.port}"
            connector = aiohttp.TCPConnector()
            timeout = aiohttp.ClientTimeout(total=3)  # Reduced to 3 seconds

            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                # Use a simple HTTP endpoint to test proxy
                test_url = "http://httpbin.org/ip"
                async with session.get(test_url, proxy=proxy_url) as response:
                    if response.status == 200:
                        return True
            return False
        except Exception:
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
            self.rotate_proxy()

    def mark_proxy_success(self, proxy: ProxyInfo, response_time: float = 0.0):
        """Mark a proxy as successful"""
        proxy.success_count += 1
        proxy.response_time = response_time
        proxy.last_check = datetime.now()
        # Reset failure count on success
        if proxy.failure_count > 0:
            proxy.failure_count = max(0, proxy.failure_count - 1)

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
