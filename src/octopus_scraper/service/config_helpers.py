"""Configuration helpers and utility functions for OctopusService."""

import os
from typing import Any, Dict, Tuple

import structlog
from dotenv import load_dotenv

from octopus_scraper.config import NotionDatabaseConfig, ServiceConfig

load_dotenv()

# Initialize logging configuration
log_format = os.getenv("LOG_FORMAT", "plain")
# `add_log_level` 将 level 名称注入事件字典，是下游日志消费方
# （Vector → 飞书告警、ELK 等）按级别过滤的前提；没有它两种渲染器
# 都不会把 level 写进输出。务必保持在渲染器之前。
#
# JSONRenderer 本身不会处理 `exc_info=True`；如果不在它之前加
# `format_exc_info`，traceback 会被丢掉，下游只能看到 `error=...`
# 而看不到栈，定位问题非常困难。ConsoleRenderer 自带异常渲染，
# 无需该 processor。
if log_format == "json":
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    )
else:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.dev.ConsoleRenderer(),
        ]
    )

logger = structlog.get_logger()

# Default service configuration (can be overridden by CLI)
DEFAULT_SERVICE_CONFIG = {
    "host": os.getenv("OCTOPUS_HOST", "0.0.0.0"),  # nosec B104
    "port": int(os.getenv("OCTOPUS_PORT", "8000")),
    "debug": os.getenv("OCTOPUS_DEBUG", "False").lower() == "true",
}


def _get_memory_usage():
    """Get basic memory usage information."""
    try:
        import resource

        # Get memory usage in MB
        memory_usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Convert from different units based on platform
        if os.name == "posix":
            # Linux/Unix returns in kilobytes
            return {"rss_mb": round(memory_usage / 1024, 2)}
        else:
            # Other platforms might return in bytes
            return {"rss_mb": round(memory_usage / (1024 * 1024), 2)}
    except Exception:
        return {"rss_mb": "unavailable"}


def create_config_from_env() -> tuple[NotionDatabaseConfig, ServiceConfig, dict]:
    """Create configuration objects from environment variables."""
    # Notion database configuration
    notion_config = NotionDatabaseConfig(
        api_key=os.getenv("NOTION_API_KEY", ""),
        scrapers_database_id=os.getenv("NOTION_SCRAPERS_DATABASE_ID")
        or os.getenv("NOTION_DATABASE_ID", ""),
        content_database_id=os.getenv("NOTION_CONTENT_DATABASE_ID", ""),
    )

    # Service configuration
    service_config = ServiceConfig(
        host=os.getenv("SERVICE_HOST", "0.0.0.0"),  # nosec B104
        port=int(os.getenv("SERVICE_PORT", "8000")),
        debug=os.getenv("DEBUG", "False").lower() == "true",
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_format=os.getenv("LOG_FORMAT", "plain"),
        config_refresh_interval=int(
            os.getenv("CONFIG_REFRESH_INTERVAL", "300")
        ),  # 5 minutes
        scraper_timeout=int(os.getenv("SCRAPER_TIMEOUT", "10")),
        upload_timeout=int(os.getenv("UPLOAD_TIMEOUT", "15")),
        upload_max_retries=int(os.getenv("UPLOAD_MAX_RETRIES", "3")),
    )

    # TaskManager configuration - always enabled
    task_manager_config = {
        "max_concurrent_tasks": int(os.getenv("MAX_CONCURRENT_TASKS", "8")),
        "max_queue_size": int(os.getenv("MAX_QUEUE_SIZE", "1000")),
        "result_retention_hours": int(os.getenv("RESULT_RETENTION_HOURS", "48")),
    }

    return notion_config, service_config, task_manager_config


# Defaults match the historical hard-coded values in RssHubConifg / DirectRSSConfig
# so existing deployments behave identically when these env vars are unset.
DEFAULT_RSSHUB_CONNECT_TIMEOUT = 10.0
DEFAULT_RSSHUB_READ_TIMEOUT = 1200.0


def get_rsshub_request_timeout() -> Tuple[float, float]:
    """Resolve the (connect, read) timeout tuple for the RSSHub fetcher.

    Reads ``RSSHUB_CONNECT_TIMEOUT`` and ``RSSHUB_READ_TIMEOUT`` from the
    environment. Both default to the values previously hard-coded in
    ``RssHubConifg`` (10s connect, 1200s read) so behaviour is unchanged
    when no env vars are set.

    Returns:
        Tuple of ``(connect_timeout, read_timeout)`` in seconds, suitable
        to pass through as ``request_timeout`` on the rsshub fetcher_config.
    """
    connect = float(
        os.getenv("RSSHUB_CONNECT_TIMEOUT", str(DEFAULT_RSSHUB_CONNECT_TIMEOUT))
    )
    read = float(os.getenv("RSSHUB_READ_TIMEOUT", str(DEFAULT_RSSHUB_READ_TIMEOUT)))
    return (connect, read)


def build_fetcher_config(
    scraper, *, include_fetch_params: bool = True
) -> Dict[str, Any]:
    """Build a ``fetcher_config`` dict for a ``ScraperConfig``.

    Centralises the construction of fetcher configuration so that
    fetcher-specific tuning (e.g. RSSHub request timeouts driven by env
    vars) is applied consistently across the initial load, soft reload
    and admin-triggered code paths.

    Args:
        scraper: A ``ScraperConfig`` describing one scraper source.
        include_fetch_params: If True, include ``fetch_params`` in the
            returned dict. The admin test endpoints intentionally omit
            it because they pass test-time params separately.

    Returns:
        A dict ready to be assigned to ``scraper_config["fetcher_config"]``.
    """
    fetcher_config: Dict[str, Any] = {
        "hub_root": scraper.hub_root,
        "route": scraper.route,
    }
    if include_fetch_params:
        fetcher_config["fetch_params"] = scraper.fetch_params or {}
    if scraper.fetcher == "rsshub":
        fetcher_config["request_timeout"] = get_rsshub_request_timeout()
    return fetcher_config
