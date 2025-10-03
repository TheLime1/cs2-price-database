Rate Limit Analysis for Steam API
=====================================

Based on analysis of api_rate_test.log:

## Rate Limit Detection
- **Rate Limit Hit**: Status 429 at 2025-10-03 22:44:55.237
- **Request that triggered limit**: P2000 | Scorpion (Factory New)
- **Response time when limited**: 60.253s (indicating a 60-second backoff)

## Request Timeline Analysis
**First batch (22:43:37 - 22:43:44):**
- 10 requests in ~7 seconds
- All successful (Status: 200)
- Summary: "10/min | 0 limits | 0 errors | 10 total"

**Second batch (22:43:46 - 22:43:53):**  
- 10 requests in ~7 seconds
- All successful (Status: 200)
- Summary: "20/min | 0 limits | 0 errors | 20 total"

**Third batch - Rate Limit Triggered:**
- Request #21 at 22:44:55.237 → **Status 429** (Rate Limited)
- Followed by successful requests after ~60 second delay
- Summary: "10/min | 1 limits | 1 errors | 30 total"

## Rate Limit Calculation
Based on the observed pattern:

**Estimated Rate Limit: ~20 requests per minute**

**Evidence:**
1. First 20 requests (in ~16 seconds) were successful
2. Request #21 triggered rate limiting (Status 429)
3. The system shows "20/min" in the summary before hitting the limit
4. 60-second backoff period was enforced
5. After backoff, requests resumed successfully

**Time between rate limit trigger and successful requests:**
- Rate limited at: 22:44:55.237
- Next successful request: 22:44:55.833 (same timestamp suggests immediate retry after backoff)
- The 60.253s response time indicates the API enforced a 60-second wait

## Recommendation
- **Safe rate**: 15-18 requests per minute (with buffer)
- **Maximum observed**: 20 requests per minute
- **Backoff period**: 60 seconds when rate limited
- **Status code**: 429 when rate limited

## Request Timing Pattern
The successful requests show consistent timing of ~0.2-0.6 seconds per request, suggesting the rate limit is count-based rather than frequency-based within the minute window.