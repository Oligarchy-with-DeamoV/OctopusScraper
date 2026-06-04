"""Configuration helpers and utility functions for OctopusService."""

import os

import structlog
from dotenv import load_dotenv

from octopus_scraper.config import NotionDatabaseConfig, ServiceConfig

load_dotenv()

# Initialize logging configuration
log_format = os.getenv("LOG_FORMAT", "plain")
# `add_log_level` 将 level 名称注入事件字典，是下游日志消费方
# （Vector → 飞书告警、ELK 等）按级别过滤的前提；没有它两种渲染器
# 都不会把 level 写进输出。务必保持在渲染器之前。
if log_format == "json":
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
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
