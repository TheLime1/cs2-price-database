"""
Summary Logger for CS2 Price Database Collection System
Generates comprehensive summary reports at the end of collection runs
"""

import json
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class CollectionStats:
    """Statistics for price collection run"""
    # Environment configuration
    env_variables: Dict[str, Any]

    # Timing information
    start_time: datetime
    end_time: Optional[datetime] = None
    total_duration: Optional[float] = None

    # Collection counters
    total_skins_processed: int = 0
    total_variants_processed: int = 0

    # Success counters by method
    steam_api_success_count: int = 0
    fallback_scraper_success_count: int = 0
    total_success_count: int = 0

    # Failure counters
    steam_api_failure_count: int = 0
    fallback_scraper_failure_count: int = 0
    total_failure_count: int = 0

    # Network statistics
    rate_limit_hits: int = 0
    network_errors: int = 0
    timeout_errors: int = 0

    # Performance metrics
    average_response_time: float = 0.0
    fastest_response: float = 0.0
    slowest_response: float = 0.0
    requests_per_minute: float = 0.0

    # Data quality metrics
    invalid_variants_removed: int = 0
    database_backups_created: int = 0

    # Collection mode specific
    collection_mode: str = "sequential"
    resumed_from_checkpoint: bool = False
    checkpoint_saves: int = 0

    # Interruption handling
    interrupted_by_user: bool = False
    interruption_time: Optional[datetime] = None
    graceful_shutdown: bool = True


class SummaryLogger:
    """Handles generation and writing of collection summary reports"""

    def __init__(self, log_dir: str = None):
        self.log_dir = log_dir or os.getenv("LOG_DIR", "logs")
        self.summary_file = os.path.join(
            self.log_dir, os.getenv("SUMMARY_LOG_FILE", "summary.txt"))

        # Ensure log directory exists
        os.makedirs(self.log_dir, exist_ok=True)

        # Statistics tracking
        self.stats = CollectionStats(
            env_variables={},
            start_time=datetime.now()
        )

        # Response time tracking
        self._response_times: List[float] = []

    def initialize_stats(self, env_vars: Dict[str, Any]):
        """Initialize statistics with environment variables"""
        self.stats.env_variables = env_vars
        self.stats.start_time = datetime.now()

    def log_steam_api_success(self, response_time: float = 0.0):
        """Log successful Steam API request"""
        self.stats.steam_api_success_count += 1
        self.stats.total_success_count += 1
        if response_time > 0:
            self._response_times.append(response_time)

    def log_steam_api_failure(self):
        """Log failed Steam API request"""
        self.stats.steam_api_failure_count += 1
        self.stats.total_failure_count += 1

    def log_fallback_success(self, response_time: float = 0.0):
        """Log successful fallback scraper request"""
        self.stats.fallback_scraper_success_count += 1
        self.stats.total_success_count += 1
        if response_time > 0:
            self._response_times.append(response_time)

    def log_fallback_failure(self):
        """Log failed fallback scraper request"""
        self.stats.fallback_scraper_failure_count += 1
        self.stats.total_failure_count += 1

    def log_rate_limit_hit(self):
        """Log rate limit hit"""
        self.stats.rate_limit_hits += 1

    def log_network_error(self):
        """Log network error"""
        self.stats.network_errors += 1

    def log_timeout_error(self):
        """Log timeout error"""
        self.stats.timeout_errors += 1

    def log_checkpoint_save(self):
        """Log checkpoint save operation"""
        self.stats.checkpoint_saves += 1

    def log_invalid_variant_removed(self):
        """Log invalid variant removal"""
        self.stats.invalid_variants_removed += 1

    def log_database_backup(self):
        """Log database backup creation"""
        self.stats.database_backups_created += 1

    def set_collection_mode(self, mode: str, resumed: bool = False):
        """Set collection mode information"""
        self.stats.collection_mode = mode
        self.stats.resumed_from_checkpoint = resumed

    def set_interruption(self, interrupted_by_user: bool = True, graceful: bool = True):
        """Set interruption information"""
        self.stats.interrupted_by_user = interrupted_by_user
        self.stats.interruption_time = datetime.now()
        self.stats.graceful_shutdown = graceful

    def finalize_stats(self):
        """Finalize statistics calculations"""
        self.stats.end_time = datetime.now()

        # Calculate duration
        if self.stats.start_time and self.stats.end_time:
            duration = self.stats.end_time - self.stats.start_time
            self.stats.total_duration = duration.total_seconds()

        # Calculate performance metrics
        if self._response_times:
            self.stats.average_response_time = sum(
                self._response_times) / len(self._response_times)
            self.stats.fastest_response = min(self._response_times)
            self.stats.slowest_response = max(self._response_times)

        # Calculate requests per minute
        if self.stats.total_duration and self.stats.total_duration > 0:
            total_requests = self.stats.total_success_count + self.stats.total_failure_count
            self.stats.requests_per_minute = (
                total_requests / self.stats.total_duration) * 60

    def generate_summary_report(self) -> str:
        """Generate comprehensive summary report"""
        self.finalize_stats()

        report_lines = []

        # Header
        report_lines.append("=" * 80)
        report_lines.append("CS2 PRICE DATABASE COLLECTION SUMMARY")
        report_lines.append("=" * 80)
        report_lines.append("")

        # Timing Information
        report_lines.append("TIMING INFORMATION")
        report_lines.append("-" * 40)
        report_lines.append(
            f"Started:           {self.stats.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        if self.stats.end_time:
            report_lines.append(
                f"Ended:             {self.stats.end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        if self.stats.total_duration:
            hours, remainder = divmod(self.stats.total_duration, 3600)
            minutes, seconds = divmod(remainder, 60)
            report_lines.append(
                f"Total Duration:    {int(hours)}h {int(minutes)}m {seconds:.1f}s")
        report_lines.append("")

        # Environment Configuration
        report_lines.append("ENVIRONMENT CONFIGURATION")
        report_lines.append("-" * 40)
        report_lines.append(
            "Started scraping with the following configuration:")
        for key, value in sorted(self.stats.env_variables.items()):
            # Mask sensitive values
            if any(sensitive in key.lower() for sensitive in ['password', 'auth', 'token', 'key']):
                value = "***MASKED***"
            report_lines.append(f"  {key}={value}")
        report_lines.append("")

        # Collection Statistics
        report_lines.append("COLLECTION STATISTICS")
        report_lines.append("-" * 40)
        report_lines.append(
            f"Collection Mode:   {self.stats.collection_mode.upper()}")
        if self.stats.resumed_from_checkpoint:
            report_lines.append("Resumed:           YES (from checkpoint)")
        else:
            report_lines.append("Resumed:           NO (fresh start)")
        report_lines.append(
            f"Skins Processed:   {self.stats.total_skins_processed:,}")
        report_lines.append(
            f"Variants Processed: {self.stats.total_variants_processed:,}")
        report_lines.append("")

        # Success Statistics by Method
        report_lines.append("SUCCESS STATISTICS BY METHOD")
        report_lines.append("-" * 40)
        report_lines.append(
            f"Steam API Success:     {self.stats.steam_api_success_count:,}")
        report_lines.append(
            f"Fallback Success:      {self.stats.fallback_scraper_success_count:,}")
        report_lines.append(
            f"Total Success:         {self.stats.total_success_count:,}")

        # Calculate success rate
        total_requests = self.stats.total_success_count + self.stats.total_failure_count
        if total_requests > 0:
            success_rate = (self.stats.total_success_count /
                            total_requests) * 100
            report_lines.append(f"Success Rate:          {success_rate:.1f}%")
        report_lines.append("")

        # Failure Statistics
        report_lines.append("FAILURE STATISTICS")
        report_lines.append("-" * 40)
        report_lines.append(
            f"Steam API Failures:    {self.stats.steam_api_failure_count:,}")
        report_lines.append(
            f"Fallback Failures:     {self.stats.fallback_scraper_failure_count:,}")
        report_lines.append(
            f"Total Failures:        {self.stats.total_failure_count:,}")
        report_lines.append("")

        # Network Statistics
        report_lines.append("NETWORK STATISTICS")
        report_lines.append("-" * 40)
        report_lines.append(
            f"Rate Limit Hits:       {self.stats.rate_limit_hits:,}")
        report_lines.append(
            f"Network Errors:        {self.stats.network_errors:,}")
        report_lines.append(
            f"Timeout Errors:        {self.stats.timeout_errors:,}")
        report_lines.append("")

        # Performance Metrics
        report_lines.append("PERFORMANCE METRICS")
        report_lines.append("-" * 40)
        if self.stats.requests_per_minute > 0:
            report_lines.append(
                f"Requests/Minute:       {self.stats.requests_per_minute:.1f}")
        if self.stats.average_response_time > 0:
            report_lines.append(
                f"Avg Response Time:     {self.stats.average_response_time:.2f}s")
        if self.stats.fastest_response > 0:
            report_lines.append(
                f"Fastest Response:      {self.stats.fastest_response:.2f}s")
        if self.stats.slowest_response > 0:
            report_lines.append(
                f"Slowest Response:      {self.stats.slowest_response:.2f}s")
        report_lines.append("")

        # Data Quality Metrics
        report_lines.append("DATA QUALITY & MAINTENANCE")
        report_lines.append("-" * 40)
        report_lines.append(
            f"Invalid Variants Removed: {self.stats.invalid_variants_removed:,}")
        report_lines.append(
            f"Database Backups Created: {self.stats.database_backups_created:,}")
        report_lines.append(
            f"Checkpoint Saves:         {self.stats.checkpoint_saves:,}")
        report_lines.append("")

        # Interruption Information
        if self.stats.interrupted_by_user:
            report_lines.append("INTERRUPTION INFORMATION")
            report_lines.append("-" * 40)
            report_lines.append(
                "Status:            INTERRUPTED BY USER (Ctrl+C)")
            if self.stats.interruption_time:
                report_lines.append(
                    f"Interrupted At:    {self.stats.interruption_time.strftime('%Y-%m-%d %H:%M:%S')}")
            if self.stats.graceful_shutdown:
                report_lines.append("Shutdown:          GRACEFUL (data saved)")
            else:
                report_lines.append(
                    "Shutdown:          FORCED (possible data loss)")
            report_lines.append("")

        # Footer
        report_lines.append("=" * 80)
        report_lines.append(
            f"Report generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append("=" * 80)

        return "\\n".join(report_lines)

    def save_summary(self):
        """Save summary report to file (text and JSON)"""
        try:
            summary_report = self.generate_summary_report()

            # Save text summary (write mode - overwrites previous)
            with open(self.summary_file, 'w', encoding='utf-8') as f:
                f.write(summary_report)

            logger.info(f"📄 Summary report saved to: {self.summary_file}")

            # Save JSON summary with only important metrics (write mode - overwrites previous)
            json_file = os.path.join(self.log_dir, "summary_stats.json")

            # Create clean summary dictionary with only important stats
            summary_data = {
                "collection_summary": {
                    "start_time": self.stats.start_time.isoformat() if self.stats.start_time else None,
                    "end_time": self.stats.end_time.isoformat() if self.stats.end_time else None,
                    "total_duration_seconds": round(self.stats.total_duration, 2) if self.stats.total_duration else 0,
                    "collection_mode": self.stats.collection_mode,
                    "resumed_from_checkpoint": self.stats.resumed_from_checkpoint,
                    "interrupted_by_user": self.stats.interrupted_by_user,
                    "graceful_shutdown": self.stats.graceful_shutdown
                },
                "skins_and_variants": {
                    "total_skins_processed": self.stats.total_skins_processed,
                    "total_variants_processed": self.stats.total_variants_processed
                },
                "success_metrics": {
                    "steam_api_success": self.stats.steam_api_success_count,
                    "fallback_scraper_success": self.stats.fallback_scraper_success_count,
                    "total_success": self.stats.total_success_count,
                    "success_rate_percent": round(
                        (self.stats.total_success_count / max(1,
                         self.stats.total_success_count + self.stats.total_failure_count)) * 100,
                        2
                    )
                },
                "failure_metrics": {
                    "steam_api_failures": self.stats.steam_api_failure_count,
                    "fallback_scraper_failures": self.stats.fallback_scraper_failure_count,
                    "total_failures": self.stats.total_failure_count,
                    "rate_limit_hits": self.stats.rate_limit_hits,
                    "network_errors": self.stats.network_errors,
                    "timeout_errors": self.stats.timeout_errors
                },
                "performance_metrics": {
                    "requests_per_minute": round(self.stats.requests_per_minute, 2),
                    "average_response_time_seconds": round(self.stats.average_response_time, 2),
                    "fastest_response_seconds": round(self.stats.fastest_response, 2),
                    "slowest_response_seconds": round(self.stats.slowest_response, 2)
                },
                "data_quality": {
                    "invalid_variants_removed": self.stats.invalid_variants_removed,
                    "database_backups_created": self.stats.database_backups_created,
                    "checkpoint_saves": self.stats.checkpoint_saves
                },
                "generated_at": datetime.now().isoformat()
            }

            # Write JSON in 'w' mode (overwrites previous)
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(summary_data, f, indent=2, ensure_ascii=False)

            logger.info(f"📊 Summary JSON saved to: {json_file}")

        except Exception as e:
            logger.error(f"❌ Failed to save summary report: {e}")

    def print_summary(self):
        """Print summary report to console"""
        try:
            summary_report = self.generate_summary_report()
            print("\\n" + summary_report)
        except Exception as e:
            logger.error(f"Failed to print summary report: {e}")


# Global summary logger instance
summary_logger = SummaryLogger()


def get_summary_logger() -> SummaryLogger:
    """Get the global summary logger instance"""
    return summary_logger
