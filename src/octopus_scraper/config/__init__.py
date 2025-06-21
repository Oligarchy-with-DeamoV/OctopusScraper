"""
Configuration management module for OctopusService.

This module provides dynamic configuration loading and management
capabilities for the OctopusService, allowing real-time updates
from Notion databases without service restart.
"""

from .config_manager import ConfigManager
from .models import (
    ConfigStatus,
    ConfigVersion,
    NotionDatabaseConfig,
    ScraperConfig,
    ServiceConfig,
)

__all__ = [
    "ConfigManager",
    "ScraperConfig",
    "NotionDatabaseConfig",
    "ServiceConfig",
    "ConfigStatus",
    "ConfigVersion",
]
