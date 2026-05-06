"""
Data models for configuration management.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ScraperConfig:
    """Configuration for a single scraper."""

    name: str
    status: str  # "Active" or "Inactive"
    fetcher: str  # "rsshub" or "direct_rss"
    hub_root: str
    route: str
    fetch_params: Optional[Dict[str, Any]] = None
    priority: int = 5
    content_processor_configs: Dict[str, Any] = field(default_factory=dict)
    default_keywords: List[str] = field(default_factory=list)

    def to_octopus_config(self) -> Dict[str, Any]:
        """Convert to format expected by Octopus class."""
        return {
            "name": self.name,
            "fetcher": self.fetcher,
            "hub_root": self.hub_root,
            "route": self.route,
            "fetch_params": self.fetch_params or {},
            "priority": self.priority,
            "content_processor_configs": self.content_processor_configs,
            "default_keywords": self.default_keywords,
        }

    @classmethod
    def from_notion_record(cls, record: Dict[str, Any]) -> "ScraperConfig":
        """Create ScraperConfig from Notion database record."""
        import json

        # Extract properties from Notion record
        properties = record.get("properties", {})

        # Helper: safely get first element's plain_text from a list property
        def _get_first_text(prop: dict, field_type: str) -> str:
            items = prop.get(field_type, [])
            if not items:
                return ""
            return items[0].get("plain_text", "")

        name = _get_first_text(properties.get("Name", {}), "title")
        status = properties.get("Status", {}).get("select", {}).get("name", "Inactive")
        fetcher = properties.get("Fetcher", {}).get("select", {}).get("name", "rsshub")
        hub_root = properties.get("Hub Root", {}).get("url", "")
        route = _get_first_text(properties.get("Route", {}), "rich_text")
        priority_value = properties.get("Priority", {}).get("number")
        priority = priority_value if priority_value is not None else 5

        # Parse fetch params JSON
        fetch_params_text = _get_first_text(
            properties.get("Fetch Params", {}), "rich_text"
        )
        fetch_params = None
        if fetch_params_text:
            try:
                fetch_params = json.loads(fetch_params_text)
            except json.JSONDecodeError:
                # Log warning and continue with None
                import structlog

                logger = structlog.get_logger()
                logger.warning(
                    "Invalid JSON in fetch_params",
                    scraper_name=name,
                    fetch_params_text=fetch_params_text,
                )

        # Parse content processor configs JSON
        content_processor_configs: Dict[str, Any] = {}
        content_processors_text = _get_first_text(
            properties.get("Content Processors", {}), "rich_text"
        )
        if content_processors_text:
            try:
                parsed_configs = json.loads(content_processors_text)
                if isinstance(parsed_configs, dict):
                    content_processor_configs = parsed_configs
                else:
                    import structlog

                    logger = structlog.get_logger()
                    logger.warning(
                        "Content Processors must be a JSON object, ignoring",
                        scraper_name=name,
                        content_processors_text=content_processors_text,
                    )
            except json.JSONDecodeError:
                import structlog

                logger = structlog.get_logger()
                logger.warning(
                    "Invalid JSON in Content Processors",
                    scraper_name=name,
                    content_processors_text=content_processors_text,
                )

        # Parse default keywords from multi_select
        default_keywords = [
            opt.get("name", "")
            for opt in properties.get("Keywords", {}).get("multi_select", [])
        ]
        default_keywords = [k.strip() for k in default_keywords if k.strip()]

        return cls(
            name=name,
            status=status,
            fetcher=fetcher,
            hub_root=hub_root,
            route=route,
            fetch_params=fetch_params,
            priority=priority,
            content_processor_configs=content_processor_configs,
            default_keywords=default_keywords,
        )


@dataclass
class NotionDatabaseConfig:
    """Configuration for Notion database connections."""

    api_key: str
    scrapers_database_id: str
    content_database_id: str


@dataclass
class ServiceConfig:
    """Overall service configuration."""

    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    log_level: str = "INFO"
    log_format: str = "plain"
    config_refresh_interval: int = 300  # seconds
    scraper_timeout: int = 10  # seconds
    upload_timeout: int = 15  # seconds
    upload_max_retries: int = 3


@dataclass
class ConfigVersion:
    """Configuration version tracking."""

    version_id: str
    timestamp: datetime
    config_hash: str
    scrapers_count: int
    change_summary: str = ""


@dataclass
class ConfigStatus:
    """Current configuration status."""

    version: ConfigVersion
    scrapers: List[ScraperConfig]
    last_check: datetime
    next_check: datetime
    is_healthy: bool = True
    error_message: Optional[str] = None
