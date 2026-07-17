"""Data models for configuration management."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ScraperConfig:
    """Configuration for a single scraper."""

    id: str
    name: str
    enabled: bool
    fetcher: str  # "rsshub" or "direct_rss"
    hub_root: str
    route: str
    fetch_params: Optional[Dict[str, Any]] = None
    priority: int = 5
    content_processor_configs: Dict[str, Any] = field(default_factory=dict)
    default_keywords: List[str] = field(default_factory=list)
    source_path: Optional[str] = None

    @property
    def status(self) -> str:
        """Return the legacy status label used by admin responses."""
        return "Active" if self.enabled else "Inactive"

    def to_octopus_config(self) -> Dict[str, Any]:
        """Convert to format expected by Octopus class."""
        return {
            "id": self.id,
            "name": self.name,
            "fetcher": self.fetcher,
            "hub_root": self.hub_root,
            "route": self.route,
            "fetch_params": self.fetch_params or {},
            "priority": self.priority,
            "content_processor_configs": self.content_processor_configs,
            "default_keywords": self.default_keywords,
        }


@dataclass
class FileConfigSettings:
    """Settings for the scraper configuration directory."""

    directory: Path
    poll_interval_seconds: float = 1.0
    debounce_seconds: float = 0.75


@dataclass
class DatabaseConfig:
    """Canonical content database settings."""

    url: str
    pool_size: int = 5
    max_overflow: int = 5
    connect_timeout_seconds: int = 10


@dataclass
class NotionSyncConfig:
    """Optional PostgreSQL-to-Notion synchronization settings."""

    enabled: bool = False
    api_key: str = ""
    database_id: str = ""
    interval_seconds: int = 60
    batch_size: int = 100
    max_attempts: int = 10
    lease_seconds: int = 300


@dataclass
class ServiceConfig:
    """Overall service configuration."""

    host: str = "0.0.0.0"  # nosec B104
    port: int = 8000
    debug: bool = False
    log_level: str = "INFO"
    log_format: str = "plain"
    config_refresh_interval: float = 1.0
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

    version: Optional[ConfigVersion]
    scrapers: List[ScraperConfig]
    last_check: datetime
    next_check: datetime
    is_healthy: bool = True
    error_message: Optional[str] = None
