#!/usr/bin/env python3
"""
API Rate Test Log Analyzer
Analyzes waiting times and rate limiting patterns from api_rate_test.log
"""

import re
from datetime import datetime
from typing import List, Dict, Any


def parse_log_entry(line: str) -> Dict[str, Any]:
    """Parse a single log entry"""
    # Pattern: 2025-10-03 22:43:37.269 | Status: 200 | Success: True | Time: 0.608s | Item: Five-SeveN | Jungle (Factory New)
    pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) \| Status: (\d+) \| Success: (\w+) \| Time: ([\d.]+)s(?:\s\|\sWait:\s([\d.]+)s)? \| Item: (.+)'

    match = re.match(pattern, line)
    if match:
        timestamp_str, status, success, response_time, wait_time, item = match.groups()

        return {
            'timestamp': datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f'),
            'status_code': int(status),
            'success': success == 'True',
            'response_time': float(response_time),
            'wait_time': float(wait_time) if wait_time else 0.0,
            'item': item
        }
    return None


def analyze_api_log(log_file: str = 'api_rate_test.log') -> Dict[str, Any]:
    """Analyze the API rate test log"""

    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: {log_file} not found!")
        return {}

    entries = []
    summary_lines = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith('API Rate') or line.startswith('Format:') or line.startswith('===='):
            continue

        # Check if it's a summary line (time | rate/min | limits | errors | total)
        if re.match(r'\d{2}:\d{2}:\d{2} \| \d+/min', line):
            summary_lines.append(line)
            continue

        entry = parse_log_entry(line)
        if entry:
            entries.append(entry)

    if not entries:
        print("No valid log entries found!")
        return {}

    # Calculate statistics
    stats = {
        'total_requests': len(entries),
        'successful_requests': len([e for e in entries if e['success']]),
        'failed_requests': len([e for e in entries if not e['success']]),
        'rate_limited_requests': len([e for e in entries if e['status_code'] == 429]),
        'response_times': {
            'min': min(e['response_time'] for e in entries),
            'max': max(e['response_time'] for e in entries),
            'avg': sum(e['response_time'] for e in entries) / len(entries)
        },
        'wait_times': {
            'min': min(e['wait_time'] for e in entries if e['wait_time'] > 0) if any(e['wait_time'] > 0 for e in entries) else 0,
            'max': max(e['wait_time'] for e in entries),
            'avg': sum(e['wait_time'] for e in entries) / len(entries),
            'total': sum(e['wait_time'] for e in entries)
        },
        'time_span': {
            'start': min(e['timestamp'] for e in entries),
            'end': max(e['timestamp'] for e in entries),
            'duration_seconds': (max(e['timestamp'] for e in entries) - min(e['timestamp'] for e in entries)).total_seconds()
        }
    }

    # Rate limiting analysis
    rate_limited_entries = [e for e in entries if e['status_code'] == 429]
    if rate_limited_entries:
        stats['rate_limiting'] = {
            'first_rate_limit': rate_limited_entries[0]['timestamp'],
            'requests_before_limit': len([e for e in entries if e['timestamp'] < rate_limited_entries[0]['timestamp'] and e['success']]),
            'average_backoff_time': sum(e['response_time'] for e in rate_limited_entries) / len(rate_limited_entries)
        }

    return stats


def append_analysis_to_log(stats: Dict[str, Any], log_file: str = 'api_rate_test.log'):
    """Append the analysis to the log file"""

    if not stats:
        return

    analysis = []
    analysis.append("\\n\\n" + "=" * 80)
    analysis.append("WAITING TIME & RATE LIMIT ANALYSIS")
    analysis.append("=" * 80)
    analysis.append(
        f"Analysis performed on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    analysis.append("")

    # Basic statistics
    analysis.append("BASIC STATISTICS:")
    analysis.append(f"  Total Requests: {stats['total_requests']}")
    analysis.append(f"  Successful Requests: {stats['successful_requests']}")
    analysis.append(f"  Failed Requests: {stats['failed_requests']}")
    analysis.append(f"  Rate Limited (429): {stats['rate_limited_requests']}")
    analysis.append("")

    # Time statistics
    analysis.append("RESPONSE TIME STATISTICS:")
    analysis.append(
        f"  Minimum Response Time: {stats['response_times']['min']:.3f}s")
    analysis.append(
        f"  Maximum Response Time: {stats['response_times']['max']:.3f}s")
    analysis.append(
        f"  Average Response Time: {stats['response_times']['avg']:.3f}s")
    analysis.append("")

    # Wait time statistics
    analysis.append("WAIT TIME STATISTICS:")
    analysis.append(f"  Minimum Wait Time: {stats['wait_times']['min']:.3f}s")
    analysis.append(f"  Maximum Wait Time: {stats['wait_times']['max']:.3f}s")
    analysis.append(f"  Average Wait Time: {stats['wait_times']['avg']:.3f}s")
    analysis.append(
        f"  Total Wait Time: {stats['wait_times']['total']:.3f}s ({stats['wait_times']['total']/60:.1f} minutes)")
    analysis.append("")

    # Time span
    analysis.append("TESTING DURATION:")
    analysis.append(
        f"  Start Time: {stats['time_span']['start'].strftime('%Y-%m-%d %H:%M:%S')}")
    analysis.append(
        f"  End Time: {stats['time_span']['end'].strftime('%Y-%m-%d %H:%M:%S')}")
    analysis.append(
        f"  Total Duration: {stats['time_span']['duration_seconds']:.1f}s ({stats['time_span']['duration_seconds']/60:.1f} minutes)")
    analysis.append("")

    # Rate limiting analysis
    if 'rate_limiting' in stats:
        analysis.append("RATE LIMITING ANALYSIS:")
        analysis.append(
            f"  First Rate Limit Hit: {stats['rate_limiting']['first_rate_limit'].strftime('%H:%M:%S')}")
        analysis.append(
            f"  Successful Requests Before Limit: {stats['rate_limiting']['requests_before_limit']}")
        analysis.append(
            f"  Average Backoff Time: {stats['rate_limiting']['average_backoff_time']:.1f}s")
        analysis.append("")

    # Calculated rate limit
    successful_before_limit = stats.get(
        'rate_limiting', {}).get('requests_before_limit', 0)
    if successful_before_limit > 0:
        analysis.append("CALCULATED RATE LIMIT:")
        analysis.append(
            f"  Steam API Rate Limit: ~{successful_before_limit} requests per session")
        analysis.append(
            f"  Recommended Safe Rate: {max(1, successful_before_limit - 5)} requests per session")
        analysis.append("")

    # Performance metrics
    if stats['time_span']['duration_seconds'] > 0:
        actual_rate = stats['successful_requests'] / \
            (stats['time_span']['duration_seconds'] / 60)
        analysis.append("PERFORMANCE METRICS:")
        analysis.append(
            f"  Actual Request Rate: {actual_rate:.1f} requests/minute")
        analysis.append(
            f"  Efficiency: {(stats['successful_requests'] / stats['total_requests']) * 100:.1f}%")
        analysis.append("")

    analysis.append("=" * 80)

    # Append to log file
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write('\\n'.join(analysis))
        print(f"Analysis appended to {log_file}")
    except Exception as e:
        print(f"Error writing to {log_file}: {e}")


def main():
    """Main function"""
    print("API Rate Test Log Analyzer")
    print("=" * 40)

    # Analyze the log
    stats = analyze_api_log()

    if stats:
        # Print summary to console
        print(f"Total Requests: {stats['total_requests']}")
        print(f"Successful: {stats['successful_requests']}")
        print(f"Rate Limited: {stats['rate_limited_requests']}")
        print(f"Average Response Time: {stats['response_times']['avg']:.3f}s")
        print(f"Total Wait Time: {stats['wait_times']['total']:.1f}s")

        if 'rate_limiting' in stats:
            print(
                f"Requests Before Rate Limit: {stats['rate_limiting']['requests_before_limit']}")

        # Append analysis to log file
        append_analysis_to_log(stats)
    else:
        print("No data to analyze.")


if __name__ == "__main__":
    main()
