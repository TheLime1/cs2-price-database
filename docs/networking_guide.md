# Networking and Rate Limiting Guide

## Overview

This document explains the networking architecture, rate limiting strategies, and performance considerations for the CS2 Price Database collection system.

## Steam API Rate Limits

### Official Limits
- **Rate Limit**: 200 requests per 5 minutes (40 requests/minute)
- **Burst Limit**: Up to 20 requests can be made rapidly
- **Cool-down Period**: 61 seconds when rate limited
- **HTTP Status**: Returns 429 (Too Many Requests) when exceeded

### Our Conservative Approach
- **Applied Rate**: 19 requests per minute (configurable via `STEAM_API_RATE_LIMIT`)
- **Safety Margin**: 47% below Steam's limit to avoid rate limiting
- **Window**: 60-second sliding window (configurable via `STEAM_API_RATE_WINDOW`)
- **Backoff**: Exponential backoff on rate limit hits

### Rate Limiting Configuration

```env
# Steam API Rate Limiting
STEAM_API_RATE_LIMIT=19                    # Requests per minute
STEAM_API_RATE_WINDOW=60                   # Time window in seconds
STEAM_API_BURST_DELAY=3.2                  # Seconds between requests (60/19)
STEAM_API_RATE_LIMIT_BACKOFF=65            # Backoff time when rate limited
```

## Proxy System Architecture

### Proxy Rotation Strategy
- **Round-Robin**: Distribute requests evenly across healthy proxies
- **Health-Based**: Remove failed proxies from rotation automatically
- **Load Balancing**: Track requests per proxy to avoid overloading
- **Failover**: Automatic fallback to direct connection if all proxies fail

### Proxy Configuration

```env
# Proxy Management
USE_PROXIES=true                           # Enable/disable proxy usage
PROXY_GITHUB_URL=https://raw.githubusercontent.com/TheLime1/Validity/refs/heads/main/data/http.txt
PROXY_LIST=proxy1.com:8080,proxy2.com:3128 # Backup static proxy list
PROXY_FILE=proxies.txt                     # Backup proxy file
PROXY_TIMEOUT=10                           # Proxy timeout in seconds
PROXY_MAX_FAILURES=3                       # Max failures before marking unhealthy
PROXY_HEALTH_CHECK_INTERVAL=300            # Health check interval in seconds
PROXY_BACKOFF_TIME=300                     # Time to wait before retrying failed proxy
```

### Proxy Performance Metrics
- **Response Time**: Average response time per proxy
- **Success Rate**: Percentage of successful requests
- **Failure Count**: Number of consecutive failures
- **Rate Limit Hits**: Number of 429 responses from Steam API
- **Health Status**: Active, unhealthy, or temporarily disabled

## Concurrency Management

### Connection Limits

```env
# Concurrent Request Management
MAX_CONCURRENT_REQUESTS=50                 # Maximum simultaneous requests
AIOHTTP_CONNECTOR_LIMIT=100               # Total connection pool size
AIOHTTP_CONNECTOR_LIMIT_PER_HOST=30       # Connections per host
TCP_CONNECTOR_TTL_DNS_CACHE=300           # DNS cache TTL in seconds
```

### Semaphore Control
- **Global Semaphore**: Limits total concurrent requests across all proxies
- **Per-Proxy Limiting**: Each proxy respects individual rate limits
- **Adaptive Scaling**: Reduce concurrency when proxies become unavailable
- **Graceful Degradation**: Maintain service with fewer resources

## Network Timeouts and Retries

### Timeout Configuration

```env
# Timeout Settings
HTTP_REQUEST_TIMEOUT=30                    # Total request timeout
HTTP_CONNECT_TIMEOUT=10                    # Connection establishment timeout
HTTP_READ_TIMEOUT=20                       # Response read timeout
PROXY_CONNECTION_TIMEOUT=15                # Proxy-specific connection timeout
FALLBACK_SCRAPER_TIMEOUT=45               # WebDriver page load timeout
```

### Retry Strategy

```env
# Retry Configuration  
HTTP_MAX_RETRIES=3                        # Maximum retry attempts per request
HTTP_RETRY_BACKOFF_FACTOR=2.0             # Exponential backoff multiplier
HTTP_RETRY_BACKOFF_MAX=60                 # Maximum backoff time
PROXY_RETRY_DIFFERENT_PROXY=true          # Try different proxy on failure
```

## Performance Optimization

### Connection Pooling
- **Keep-Alive**: Reuse TCP connections for multiple requests
- **Connection Limits**: Balance resource usage vs performance
- **DNS Caching**: Reduce DNS lookup overhead
- **TCP No-Delay**: Minimize network latency

### Request Optimization

```env
# Performance Tuning
ENABLE_HTTP_COMPRESSION=true              # Enable gzip/deflate compression
HTTP_CHUNK_SIZE=8192                      # HTTP response chunk size
CONNECTION_POOL_SIZE=100                  # aiohttp connector pool size
ENABLE_TCP_NODELAY=true                   # Disable Nagle's algorithm
DNS_CACHE_TTL=300                         # DNS resolution cache time
```

## Bandwidth and Data Usage

### Expected Data Usage
- **Per Request**: ~2-5 KB (API response)
- **Per Skin**: ~10-25 KB (normal + StatTrak variants)
- **Full Collection**: ~15-30 MB total data transfer
- **Daily Updates**: ~1-5 MB (missing items only)

### Bandwidth Requirements
- **Minimum**: 1 Mbps (for basic functionality)
- **Recommended**: 5+ Mbps (for full concurrent processing)
- **Peak Usage**: ~50 concurrent requests × 5 KB = 250 KB/s

## Error Handling and Recovery

### Network Error Types
1. **Connection Timeouts**: Retry with different proxy
2. **DNS Resolution Failures**: Cache miss, retry after delay
3. **HTTP 5xx Errors**: Server issues, exponential backoff
4. **HTTP 429**: Rate limited, switch proxy or wait
5. **Proxy Connection Failures**: Mark proxy unhealthy, try next

### Automatic Recovery

```env
# Error Recovery Configuration
ENABLE_AUTOMATIC_RETRY=true               # Enable automatic retry logic
NETWORK_ERROR_RETRY_DELAY=5               # Base delay for network errors
DNS_ERROR_RETRY_DELAY=10                  # Base delay for DNS errors
PROXY_ERROR_SWITCH_IMMEDIATELY=true       # Switch proxy on first failure
FALLBACK_TO_DIRECT_ON_ALL_PROXY_FAIL=true # Use direct connection as last resort
```

## Monitoring and Logging

### Network Metrics Logged
- Request/response times per proxy
- Success rates and failure patterns
- Rate limit hit frequency
- Bandwidth usage estimates
- Connection pool utilization

### Performance Logging

```env
# Monitoring Configuration
ENABLE_PERFORMANCE_LOGGING=true           # Log detailed performance metrics
LOG_NETWORK_TIMING=true                   # Log request/response times
LOG_PROXY_STATISTICS=true                 # Log proxy performance stats
LOG_RATE_LIMIT_EVENTS=true               # Log rate limiting events
PERFORMANCE_LOG_INTERVAL=60               # Seconds between performance logs
```

## Network Security Considerations

### Proxy Security
- **Authentication**: Support for username/password proxy auth
- **Protocol Support**: HTTP, HTTPS, SOCKS4, SOCKS5
- **No Logging**: Avoid logging proxy credentials
- **Rotation**: Regular proxy list updates from trusted sources

### Rate Limiting Ethics
- **Respectful Limits**: Stay well below API provider limits
- **Distributed Load**: Use proxies to distribute requests geographically  
- **Backoff Compliance**: Honor rate limit responses immediately
- **User-Agent**: Use identifiable, non-deceptive user agent strings

## Troubleshooting Network Issues

### Common Problems and Solutions

#### High Rate Limit Hits
```env
# Reduce rate limit further
STEAM_API_RATE_LIMIT=15                   # From 19 to 15 requests/minute
STEAM_API_RATE_LIMIT_BACKOFF=90          # Longer backoff period
```

#### Proxy Connection Failures
```env
# Stricter proxy management
PROXY_MAX_FAILURES=2                      # Mark unhealthy sooner
PROXY_CONNECTION_TIMEOUT=8                # Shorter connection timeout
ENABLE_PROXY_HEALTH_CHECK=true           # Pre-filter dead proxies
```

#### Slow Performance
```env  
# Increase concurrency carefully
MAX_CONCURRENT_REQUESTS=30                # Reduce if causing issues
HTTP_REQUEST_TIMEOUT=20                   # Shorter timeout for faster failures
```

#### Network Instability
```env
# More conservative settings
MAX_CONCURRENT_REQUESTS=25                # Lower concurrency
HTTP_MAX_RETRIES=5                        # More retry attempts
HTTP_RETRY_BACKOFF_MAX=120               # Longer maximum backoff
```

## Performance Benchmarks

### Typical Performance (with proxies)
- **Collection Rate**: 15-20 items per minute
- **Success Rate**: 95-98%
- **Average Response Time**: 2-5 seconds
- **Rate Limit Hits**: <1% of requests

### Performance without Proxies
- **Collection Rate**: 8-12 items per minute
- **Success Rate**: 90-95%
- **Average Response Time**: 3-8 seconds  
- **Rate Limit Hits**: 5-10% of requests

### Fallback Scraper Performance
- **Activation Rate**: 2-5% of requests
- **Success Rate**: 85-90%
- **Average Time**: 15-30 seconds per item
- **Resource Usage**: ~50MB RAM per WebDriver instance

## Scalability Considerations

### Horizontal Scaling
- Multiple instances with different proxy pools
- Distributed work queues with Redis/database
- Result aggregation and deduplication
- Coordinated rate limiting across instances

### Vertical Scaling
- Dynamic concurrency adjustment based on system resources
- Memory-aware batch sizing
- CPU usage monitoring and throttling
- Network interface utilization tracking