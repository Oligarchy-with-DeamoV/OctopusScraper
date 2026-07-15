"""Configuration helpers and utility functions for OctopusService."""

import os
from pathlib import Path
from typing import Any, Dict, Tuple

import structlog
from dotenv import load_dotenv
from sqlalchemy.engine import URL

from octopus_scraper.config import (
    DatabaseConfig,
    FileConfigSettings,
    NotionSyncConfig,
    ServiceConfig,
)

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


def _positive_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _positive_float(name: str, default: float) -> float:
    value = float(os.getenv(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def create_config_from_env() -> tuple[
    FileConfigSettings,
    DatabaseConfig,
    NotionSyncConfig,
    ServiceConfig,
    dict,
]:
    """Create configuration objects from environment variables."""
    file_config = FileConfigSettings(
        directory=Path(
            os.getenv("SCRAPER_CONFIG_DIR", "resources/scrapers.d")
        ).expanduser(),
        poll_interval_seconds=_positive_float("SCRAPER_CONFIG_POLL_INTERVAL", 1.0),
        debounce_seconds=_positive_float("SCRAPER_CONFIG_DEBOUNCE_SECONDS", 0.75),
    )

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        database_url = URL.create(
            "postgresql+psycopg",
            username=os.getenv("POSTGRES_USER", "octopus"),
            password=os.getenv("POSTGRES_PASSWORD", "octopus"),
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("POSTGRES_DB", "octopus"),
        ).render_as_string(hide_password=False)

    database_config = DatabaseConfig(
        url=database_url,
        pool_size=_positive_int("DB_POOL_SIZE", 5),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "5")),
        connect_timeout_seconds=_positive_int("DB_CONNECT_TIMEOUT_SECONDS", 10),
    )
    if database_config.max_overflow < 0:
        raise ValueError("DB_MAX_OVERFLOW must be zero or greater")

    notion_sync_config = NotionSyncConfig(
        enabled=os.getenv("NOTION_SYNC_ENABLED", "false").lower() == "true",
        api_key=os.getenv("NOTION_API_KEY", ""),
        database_id=os.getenv("NOTION_CONTENT_DATABASE_ID", ""),
        interval_seconds=_positive_int("NOTION_SYNC_INTERVAL_SECONDS", 60),
        batch_size=_positive_int("NOTION_SYNC_BATCH_SIZE", 100),
        max_attempts=_positive_int("NOTION_SYNC_MAX_ATTEMPTS", 10),
        lease_seconds=_positive_int("NOTION_SYNC_LEASE_SECONDS", 300),
    )

    # Service configuration
    service_config = ServiceConfig(
        host=os.getenv("SERVICE_HOST", "0.0.0.0"),  # nosec B104
        port=int(os.getenv("SERVICE_PORT", "8000")),
        debug=os.getenv("DEBUG", "False").lower() == "true",
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_format=os.getenv("LOG_FORMAT", "plain"),
        config_refresh_interval=file_config.poll_interval_seconds,
        scraper_timeout=int(os.getenv("SCRAPER_TIMEOUT", "10")),
        upload_timeout=int(os.getenv("UPLOAD_TIMEOUT", "15")),
        upload_max_retries=int(os.getenv("UPLOAD_MAX_RETRIES", "3")),
    )

    # TaskManager configuration - always enabled
    task_manager_config = {
        "max_concurrent_tasks": _positive_int(
            "TASK_MANAGER_MAX_CONCURRENT",
            int(os.getenv("MAX_CONCURRENT_TASKS", "8")),
        ),
        "max_queue_size": _positive_int(
            "TASK_MANAGER_MAX_QUEUE_SIZE",
            int(os.getenv("MAX_QUEUE_SIZE", "1000")),
        ),
        "result_retention_hours": _positive_int("RESULT_RETENTION_HOURS", 48),
    }

    return (
        file_config,
        database_config,
        notion_sync_config,
        service_config,
        task_manager_config,
    )


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
