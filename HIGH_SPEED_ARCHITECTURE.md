# High-Speed Scraping Architecture

## Overview
The new high-speed scraping system implements a worker stealing architecture designed to maximize scraping throughput while maintaining efficiency and handling failures gracefully.

## Key Components

### 1. Worker Types
- **Proxy Workers**: Use proxies to scrape individual variants via Steam API
- **WebDriver Workers**: Use Selenium WebDrivers to scrape entire items (all variants) from detail pages

### 2. Queue System
- **Main Queue**: Contains all items to be scraped
- **Fallback Queue**: Contains items that failed proxy scraping and need WebDriver processing

### 3. Worker Stealing Architecture
- Workers continuously "steal" items from queues when they become idle
- No pre-assignment of items - dynamic load balancing
- Prevents workers from being idle while work remains

### 4. Proxy Management
- **Batch Health Checking**: Proxies are health-checked in batches of 5
- **Dynamic Scaling**: Up to 150 active proxies maximum
- **Background Health Monitoring**: Continuous health checking in background
- **No Rotation on Rate Limit**: Keep using same healthy proxy, just wait 61 seconds

### 5. WebDriver Pool
- **Dynamic Sizing**: Calculated as `min(2 × CPU_cores, floor(Available_RAM_MB / 600))`
- **Immediate Start**: WebDrivers start immediately and begin stealing from queues
- **Fallback Priority**: WebDrivers prioritize fallback queue over main queue

### 6. Failure Handling
- **Single Variant Failure**: If ANY variant fails for a proxy, entire item goes to fallback
- **WebDriver Processing**: WebDrivers scrape entire item (all variants) in one request
- **Smart Delegation**: Failed proxy items are delegated to WebDriver workers

### 7. Performance Features
- **Concurrent Health Checking**: Multiple proxies checked simultaneously
- **Background Processing**: Health checks run in background while scraping continues
- **No Waiting**: Workers don't wait for assignments, they actively steal work
- **Intelligent Queuing**: Priority system ensures urgent items are processed first

## Workflow

1. **Initialization**:
   - Calculate optimal WebDriver count
   - Start WebDriver pool immediately
   - Begin proxy health checking in background

2. **Item Processing**:
   - Items loaded into main queue
   - Proxy workers steal from main queue
   - WebDriver workers steal from both queues (fallback priority)

3. **Proxy Processing**:
   - Process variants one by one
   - If ANY variant fails → delegate entire item to fallback
   - If all variants succeed → mark item complete

4. **WebDriver Processing**:
   - Process entire item (all variants) at once
   - Can handle both fallback items and main queue items
   - Higher success rate due to different scraping method

5. **Continuous Operation**:
   - Health checking runs continuously
   - Failed workers are removed and replaced
   - Statistics and monitoring provide real-time feedback

## Benefits

- **Maximum Speed**: No artificial delays, workers always busy
- **Fault Tolerance**: Multiple fallback mechanisms
- **Resource Optimization**: Dynamic scaling based on system resources
- **Load Balancing**: Worker stealing prevents bottlenecks
- **Visibility**: Comprehensive logging and statistics

## Configuration

Key parameters can be adjusted:
- `max_active_proxies`: Maximum concurrent proxy workers (default: 150)
- `initial_proxy_batch`: Size of proxy health check batches (default: 5)
- `rate_limit_wait`: Wait time after rate limit (default: 61 seconds)
- `health_check_interval`: Frequency of health checks (default: 30 seconds)

This architecture ensures maximum scraping speed while maintaining reliability and providing comprehensive monitoring and failure handling.