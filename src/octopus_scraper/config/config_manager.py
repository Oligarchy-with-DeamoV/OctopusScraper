"""
Configuration Manager for OctopusService.

This module provides centralized configuration management including
loading, validation, change detection, and hot updates.
"""

import asyncio
import hashlib
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog

from octopus_scraper.config.models import (
    ConfigStatus,
    ConfigVersion,
    NotionDatabaseConfig,
    ScraperConfig,
    ServiceConfig,
)
from octopus_scraper.config.notion_config import NotionConfigClient

logger = structlog.get_logger(__name__)


class ConfigManager:
    """Centralized configuration management for OctopusService."""

    def __init__(
        self, notion_config: NotionDatabaseConfig, service_config: ServiceConfig
    ):
        self.notion_config = notion_config
        self.service_config = service_config
        self.notion_client = NotionConfigClient(notion_config)

        # Current configuration state
        self._current_scrapers: List[ScraperConfig] = []
        self._current_version: Optional[ConfigVersion] = None
        self._last_check: Optional[datetime] = None
        self._is_healthy: bool = True
        self._error_message: Optional[str] = None
        # Most recent structural diff produced by reload_config_if_changed.
        # Exposed via get_last_diff() so callers (e.g. on_config_changed
        # callbacks) can react based on what actually changed.
        self._last_diff: Optional[Dict[str, Any]] = None

        # Callback invoked when configuration changes are applied.
        # Registered via set_on_config_changed(); used by the background
        # watcher to trigger Octopus reload without needing a direct
        # reference to the Sanic app.
        self._on_config_changed_callback: Optional[Any] = None

        # Background task control
        self._watcher_task: Optional[asyncio.Task] = None
        self._stop_watcher: bool = False

    async def load_initial_config(self) -> List[ScraperConfig]:
        """Load initial configuration from Notion on service startup."""
        try:
            logger.info("Loading initial configuration from Notion")

            # Validate Notion connection first
            if not await self.notion_client.validate_connection():
                raise RuntimeError("Failed to validate Notion connection")

            # Load scrapers configuration
            scrapers = await self.notion_client.load_scrapers_config()

            # Validate configuration
            validation_errors = self.validate_scrapers_config(scrapers)
            if validation_errors:
                error_msg = (
                    f"Configuration validation failed: {'; '.join(validation_errors)}"
                )
                logger.error(error_msg)
                raise ValueError(error_msg)

            # Update current state
            self._current_scrapers = scrapers
            self._current_version = self._create_config_version(scrapers)
            self._last_check = datetime.now()
            self._is_healthy = True
            self._error_message = None

            logger.info(
                "Initial configuration loaded successfully",
                scrapers_count=len(scrapers),
                version_id=self._current_version.version_id,
            )

            return scrapers

        except Exception as e:
            self._is_healthy = False
            self._error_message = str(e)
            logger.error(
                "Failed to load initial configuration", error=str(e), exc_info=True
            )
            raise

    def set_on_config_changed(self, callback) -> None:
        """Register an async callback invoked when configuration changes.

        The callback receives no arguments and should handle reloading
        any dependent components (e.g. recreating the Octopus instance).

        Args:
            callback: An async callable invoked after config changes are applied.
        """
        self._on_config_changed_callback = callback

    def start_config_watcher(self):
        """Start background task to monitor configuration changes."""
        if self._watcher_task and not self._watcher_task.done():
            logger.warning("Config watcher already running")
            return

        self._stop_watcher = False
        self._watcher_task = asyncio.create_task(self._config_watcher_loop())
        logger.info(
            "Configuration watcher started",
            refresh_interval=self.service_config.config_refresh_interval,
        )

    def stop_config_watcher(self):
        """Stop background configuration monitoring."""
        if self._watcher_task:
            self._stop_watcher = True
            self._watcher_task.cancel()
            logger.info("Configuration watcher stopped")

    async def _config_watcher_loop(self):
        """Background loop for monitoring configuration changes."""
        while not self._stop_watcher:
            try:
                await asyncio.sleep(self.service_config.config_refresh_interval)

                if self._stop_watcher:
                    break

                logger.debug("Reloading configuration")

                config_changed = await self.reload_config_if_changed()
                if config_changed and self._on_config_changed_callback:
                    try:
                        await self._on_config_changed_callback()
                    except Exception as cb_err:
                        logger.error(
                            "on_config_changed callback failed",
                            error=str(cb_err),
                            exc_info=True,
                        )

                self._last_check = datetime.now()

            except asyncio.CancelledError:
                logger.info("Config watcher cancelled")
                break
            except Exception as e:
                logger.error("Error in config watcher loop", error=str(e))
                # Continue monitoring despite errors
                self._is_healthy = False
                self._error_message = str(e)

    async def reload_config_if_changed(self) -> bool:
        """Reload configuration if changes are detected."""
        try:
            # Load new configuration
            new_scrapers = await self.notion_client.load_scrapers_config()

            # Validate new configuration
            validation_errors = self.validate_scrapers_config(new_scrapers)
            if validation_errors:
                error_msg = f"New configuration validation failed: {'; '.join(validation_errors)}"
                logger.error(error_msg)
                self._error_message = error_msg
                return False

            # Check if configuration actually changed
            new_config_hash = self._calculate_config_hash(new_scrapers)
            current_config_hash = (
                self._current_version.config_hash if self._current_version else ""
            )

            if new_config_hash == current_config_hash:
                logger.debug("Configuration hash unchanged, skipping update")
                return False

            # Compute structural diff to validate the hash change reflects a real
            # semantic difference. This guards against pathological cases where
            # the hash changes but no observable field did (e.g. future hash
            # tweaks); in such a case we treat it as no-op.
            diff = self.compute_scrapers_diff(self._current_scrapers, new_scrapers)
            if not (diff["added"] or diff["removed"] or diff["modified"]):
                logger.info(
                    "Configuration hash changed but no semantic diff detected, "
                    "skipping reload"
                )
                # Refresh the stored hash so we don't keep flagging this state.
                self._current_version = self._create_config_version(new_scrapers)
                return False

            # Apply new configuration
            old_version = self._current_version
            self._current_scrapers = new_scrapers
            self._current_version = self._create_config_version(new_scrapers)
            self._is_healthy = True
            self._error_message = None

            change_summary = self._create_change_summary(
                old_version, self._current_version, diff
            )
            self._current_version.change_summary = change_summary
            self._last_diff = diff

            logger.info(
                "Configuration updated successfully",
                old_version=old_version.version_id if old_version else None,
                new_version=self._current_version.version_id,
                scrapers_count=len(new_scrapers),
                change_summary=change_summary,
                added=diff["added"],
                removed=diff["removed"],
                modified=[m["name"] for m in diff["modified"]],
            )

            return True

        except Exception as e:
            logger.error("Failed to reload configuration", error=str(e))
            self._is_healthy = False
            self._error_message = str(e)
            return False

    async def manual_refresh_config(self) -> Dict[str, Any]:
        """Manually trigger configuration refresh."""
        logger.info("Manual configuration refresh triggered")

        try:
            old_scrapers_count = len(self._current_scrapers)
            success = await self.reload_config_if_changed()
            new_scrapers_count = len(self._current_scrapers)

            return {
                "success": success,
                "old_scrapers_count": old_scrapers_count,
                "new_scrapers_count": new_scrapers_count,
                "version_id": (
                    self._current_version.version_id if self._current_version else None
                ),
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error("Manual configuration refresh failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    def validate_scrapers_config(self, scrapers: List[ScraperConfig]) -> List[str]:
        """Validate scrapers configuration."""
        errors = []

        # Allow empty scrapers list for testing/initial setup
        if not scrapers:
            return errors

        names = set()
        for scraper in scrapers:
            # Check for required fields
            if not scraper.name:
                errors.append("Scraper missing name")
            elif scraper.name in names:
                errors.append(f"Duplicate scraper name: {scraper.name}")
            else:
                names.add(scraper.name)

            if not scraper.hub_root:
                errors.append(f"Scraper '{scraper.name}' missing hub_root")

            if not scraper.route:
                errors.append(f"Scraper '{scraper.name}' missing route")

            if scraper.fetcher not in ["rsshub", "direct_rss"]:
                errors.append(
                    f"Scraper '{scraper.name}' has invalid fetcher: {scraper.fetcher}"
                )

            if scraper.priority < 1 or scraper.priority > 10:
                errors.append(
                    f"Scraper '{scraper.name}' has invalid priority: {scraper.priority}"
                )

            # Validate content_processor_configs
            if scraper.content_processor_configs:
                from octopus_scraper.processors import AVAILABLE_PROCESSOR

                for (
                    processor_key,
                    processor_cfg,
                ) in scraper.content_processor_configs.items():
                    if processor_key not in AVAILABLE_PROCESSOR:
                        errors.append(
                            f"Scraper '{scraper.name}' references unknown processor: "
                            f"'{processor_key}'. Available: {list(AVAILABLE_PROCESSOR.keys())}"
                        )
                    if not isinstance(processor_cfg, dict):
                        errors.append(
                            f"Scraper '{scraper.name}' has invalid config for processor "
                            f"'{processor_key}': must be a dict"
                        )

        return errors

    def get_current_config_status(self) -> ConfigStatus:
        """Get current configuration status."""
        next_check = None
        if self._last_check:
            next_check = self._last_check + timedelta(
                seconds=self.service_config.config_refresh_interval
            )

        return ConfigStatus(
            version=self._current_version,
            scrapers=self._current_scrapers.copy(),
            last_check=self._last_check or datetime.now(),
            next_check=next_check or datetime.now(),
            is_healthy=self._is_healthy,
            error_message=self._error_message,
        )

    def get_current_scrapers(self) -> List[ScraperConfig]:
        """Get current scrapers configuration."""
        return self._current_scrapers.copy()

    def get_current_version(self) -> Optional[ConfigVersion]:
        """Get current configuration version."""
        return self._current_version

    def get_scrapers_for_octopus(self) -> List[Dict[str, Any]]:
        """Get scrapers configuration in format expected by Octopus class."""
        return [
            {
                "scraper_config": scraper.to_octopus_config(),
                "fetch_params": scraper.fetch_params or {},
            }
            for scraper in self._current_scrapers
        ]

    def _create_config_version(self, scrapers: List[ScraperConfig]) -> ConfigVersion:
        """Create configuration version information."""
        config_hash = self._calculate_config_hash(scrapers)
        timestamp = datetime.now()
        version_id = f"v{timestamp.strftime('%Y%m%d_%H%M%S')}_{config_hash[:8]}"

        return ConfigVersion(
            version_id=version_id,
            timestamp=timestamp,
            config_hash=config_hash,
            scrapers_count=len(scrapers),
        )

    def _normalize_scraper_for_hash(self, scraper: ScraperConfig) -> Dict[str, Any]:
        """Return a canonical, order-independent representation of a scraper.

        Used both for hashing (change detection) and for structural diffing.
        Notion may return order-insensitive collections (e.g. multi-select
        keywords) in arbitrary order; normalising prevents spurious diffs.
        """
        return {
            "name": scraper.name,
            "status": scraper.status,
            "fetcher": scraper.fetcher,
            "hub_root": scraper.hub_root,
            "route": scraper.route,
            "fetch_params": scraper.fetch_params or {},
            "priority": scraper.priority,
            "content_processor_configs": scraper.content_processor_configs or {},
            # Multi-select order from Notion is not stable, sort to dedupe diffs.
            "default_keywords": sorted(scraper.default_keywords or []),
        }

    def compute_scrapers_diff(
        self,
        old_scrapers: List[ScraperConfig],
        new_scrapers: List[ScraperConfig],
    ) -> Dict[str, Any]:
        """Compute a structural diff between two scraper lists.

        Returns:
            Dict with keys:
                - added: list of scraper names added in ``new_scrapers``
                - removed: list of scraper names removed from ``old_scrapers``
                - modified: list of ``{"name": str, "fields": [str, ...]}``
                  for scrapers whose canonical representation changed.
        """
        old_map = {s.name: self._normalize_scraper_for_hash(s) for s in old_scrapers}
        new_map = {s.name: self._normalize_scraper_for_hash(s) for s in new_scrapers}

        added = sorted(set(new_map) - set(old_map))
        removed = sorted(set(old_map) - set(new_map))

        modified: List[Dict[str, Any]] = []
        for name in sorted(set(old_map) & set(new_map)):
            old_n = old_map[name]
            new_n = new_map[name]
            changed_fields = sorted(
                field for field in old_n if old_n[field] != new_n[field]
            )
            if changed_fields:
                modified.append({"name": name, "fields": changed_fields})

        return {"added": added, "removed": removed, "modified": modified}

    def _calculate_config_hash(self, scrapers: List[ScraperConfig]) -> str:
        """Calculate hash of configuration for change detection."""
        config_data = [
            self._normalize_scraper_for_hash(scraper)
            for scraper in sorted(scrapers, key=lambda s: s.name)
        ]
        config_json = json.dumps(config_data, sort_keys=True)
        return hashlib.sha256(config_json.encode()).hexdigest()

    def _create_change_summary(
        self,
        old_version: Optional[ConfigVersion],
        new_version: ConfigVersion,
        diff: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a human-readable summary of configuration changes.

        When a structural ``diff`` is provided (the typical case), the summary
        enumerates added/removed/modified scraper names so logs are actionable
        instead of just reporting that "something" changed.
        """
        if not old_version:
            return (
                f"Initial configuration loaded with "
                f"{new_version.scrapers_count} scrapers"
            )

        if diff is not None:
            parts: List[str] = []
            if diff["added"]:
                parts.append(f"added={diff['added']}")
            if diff["removed"]:
                parts.append(f"removed={diff['removed']}")
            if diff["modified"]:
                modified_desc = [
                    f"{m['name']}({','.join(m['fields'])})" for m in diff["modified"]
                ]
                parts.append(f"modified={modified_desc}")
            if parts:
                return "; ".join(parts)

        old_count = old_version.scrapers_count
        new_count = new_version.scrapers_count

        if old_count == new_count:
            return "Configuration updated (same scraper count)"
        elif new_count > old_count:
            return f"Added {new_count - old_count} scrapers ({old_count} → {new_count})"
        else:
            return (
                f"Removed {old_count - new_count} scrapers ({old_count} → {new_count})"
            )

    def get_last_diff(self) -> Optional[Dict[str, Any]]:
        """Return the diff produced by the most recent successful reload."""
        return self._last_diff

    def get_status(self):
        """Get current configuration status for health/admin endpoints."""
        from .models import ConfigStatus, ConfigVersion

        return ConfigStatus(
            version=self._current_version,
            scrapers=self._current_scrapers,
            last_check=self._last_check or datetime.now(),
            next_check=(self._last_check or datetime.now())
            + timedelta(seconds=self.service_config.config_refresh_interval),
            is_healthy=self._is_healthy,
            error_message=self._error_message,
        )
