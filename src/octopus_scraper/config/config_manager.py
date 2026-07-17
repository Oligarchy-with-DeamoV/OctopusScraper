"""Directory-backed scraper configuration management."""

import asyncio
import hashlib
import json
import time
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import structlog

from octopus_scraper.config.models import (
    ConfigStatus,
    ConfigVersion,
    FileConfigSettings,
    ScraperConfig,
    ServiceConfig,
)
from octopus_scraper.config.yaml_config import (
    MAX_CONFIG_FILE_BYTES,
    ScraperConfigError,
    YamlScraperConfigLoader,
)
from octopus_scraper.metrics import metrics

logger = structlog.get_logger(__name__)


class ConfigManager:
    """Load scraper definitions from a directory and hot-reload them safely."""

    def __init__(
        self,
        file_settings: FileConfigSettings,
        service_config: ServiceConfig,
    ):
        self.file_settings = file_settings
        self.service_config = service_config
        self._loader = YamlScraperConfigLoader()
        self._accepted_by_path: Dict[Path, ScraperConfig] = {}
        self._file_hashes: Dict[Path, str] = {}
        self._current_version: Optional[ConfigVersion] = None
        self._last_check: Optional[datetime] = None
        self._is_healthy = True
        self._error_message: Optional[str] = None
        self._file_errors: Dict[str, str] = {}
        self._last_diff: Optional[Dict[str, Any]] = None
        self._on_config_changed_callback: Optional[Any] = None
        self._watcher_task: Optional[asyncio.Task] = None
        self._stop_watcher = False
        self._refresh_lock = asyncio.Lock()
        self._pending_fingerprint: Optional[str] = None
        self._pending_since: Optional[float] = None
        self._applied_fingerprint: Optional[str] = None

    async def load_initial_config(self) -> List[ScraperConfig]:
        """Load all valid scraper files during service startup."""
        changed = await self._refresh(force=True, invoke_callback=False)
        logger.info(
            "Initial scraper configuration loaded",
            scraper_count=len(self.get_current_scrapers()),
            config_changed=changed,
            config_dir=str(self.file_settings.directory),
        )
        return self.get_current_scrapers()

    def set_on_config_changed(self, callback) -> None:
        """Register an async callback for applied configuration changes."""
        self._on_config_changed_callback = callback

    def start_config_watcher(self) -> None:
        """Start the polling watcher."""
        if self._watcher_task and not self._watcher_task.done():
            return
        self._stop_watcher = False
        self._watcher_task = asyncio.create_task(self._config_watcher_loop())
        logger.info(
            "Configuration watcher started",
            config_dir=str(self.file_settings.directory),
            poll_interval_seconds=self.file_settings.poll_interval_seconds,
            debounce_seconds=self.file_settings.debounce_seconds,
        )

    def stop_config_watcher(self) -> None:
        """Stop the polling watcher."""
        self._stop_watcher = True
        if self._watcher_task:
            self._watcher_task.cancel()

    async def _config_watcher_loop(self) -> None:
        while not self._stop_watcher:
            try:
                await asyncio.sleep(self.file_settings.poll_interval_seconds)
                if self._stop_watcher:
                    break
                await self._refresh(force=False, invoke_callback=True)
            except asyncio.CancelledError:
                break
            except Exception as error:
                self._is_healthy = False
                self._error_message = str(error)
                logger.error(
                    "Configuration watcher scan failed",
                    error=str(error),
                    error_type=type(error).__name__,
                )

    async def reload_config_if_changed(self) -> bool:
        """Immediately rescan and apply stable directory contents."""
        return await self._refresh(force=True, invoke_callback=True)

    async def manual_refresh_config(self) -> Dict[str, Any]:
        """Manually trigger a directory refresh."""
        old_count = len(self.get_current_scrapers())
        changed = await self.reload_config_if_changed()
        return {
            "success": self._is_healthy,
            "changed": changed,
            "old_scrapers_count": old_count,
            "new_scrapers_count": len(self.get_current_scrapers()),
            "version_id": (
                self._current_version.version_id if self._current_version else None
            ),
            "timestamp": datetime.now().isoformat(),
        }

    async def _refresh(self, force: bool, invoke_callback: bool) -> bool:
        async with self._refresh_lock:
            scan = self._scan_directory()
            if scan is None:
                metrics.record_config_refresh(success=False)
                return False

            fingerprint, file_hashes = scan
            now = time.monotonic()
            if not force and fingerprint != self._applied_fingerprint:
                if fingerprint != self._pending_fingerprint:
                    self._pending_fingerprint = fingerprint
                    self._pending_since = now
                    return False
                if (
                    self._pending_since is None
                    or now - self._pending_since < self.file_settings.debounce_seconds
                ):
                    return False

            if fingerprint == self._applied_fingerprint:
                self._last_check = datetime.now()
                self._is_healthy = True
                self._error_message = self._format_errors()
                return False

            previous_by_path = self._accepted_by_path.copy()
            previous_hashes = self._file_hashes.copy()
            previous_errors = self._file_errors.copy()
            previous_last_check = self._last_check
            previous_last_diff = self._last_diff
            candidate_by_path, errors = self._build_candidate(file_hashes)
            candidate_scrapers = self._sort_scrapers(candidate_by_path.values())
            previous_scrapers = self._sort_scrapers(previous_by_path.values())
            new_hash = self._calculate_config_hash(candidate_scrapers)
            old_hash = self._calculate_config_hash(previous_scrapers)

            if new_hash == old_hash:
                self._file_errors = errors
                self._last_check = datetime.now()
                self._pending_fingerprint = None
                self._pending_since = None
                self._applied_fingerprint = fingerprint
                self._file_hashes = file_hashes
                self._is_healthy = True
                self._error_message = self._format_errors()
                metrics.record_config_refresh(success=True)
                return False

            diff = self.compute_scrapers_diff(previous_scrapers, candidate_scrapers)
            old_version = self._current_version
            self._accepted_by_path = candidate_by_path
            self._file_hashes = file_hashes
            self._file_errors = errors
            self._last_check = datetime.now()
            self._current_version = self._create_config_version(candidate_scrapers)
            self._current_version.change_summary = self._create_change_summary(diff)
            self._last_diff = diff

            try:
                if invoke_callback and self._on_config_changed_callback:
                    callback_result = await self._on_config_changed_callback()
                    if callback_result is False:
                        raise RuntimeError("Runtime rejected the scraper configuration")
            except Exception as error:
                self._accepted_by_path = previous_by_path
                self._file_hashes = previous_hashes
                self._file_errors = previous_errors
                self._last_check = previous_last_check
                self._last_diff = previous_last_diff
                self._current_version = old_version
                self._is_healthy = False
                self._error_message = str(error)
                raise

            self._pending_fingerprint = None
            self._pending_since = None
            self._applied_fingerprint = fingerprint
            self._is_healthy = True
            self._error_message = self._format_errors()
            metrics.record_config_refresh(success=True)
            logger.info(
                "Scraper configuration applied",
                added=diff["added"],
                removed=diff["removed"],
                modified=[item["id"] for item in diff["modified"]],
                active_scrapers=len(self.get_current_scrapers()),
                invalid_files=len(errors),
            )
            return True

    def _scan_directory(self) -> Optional[Tuple[str, Dict[Path, str]]]:
        directory = self.file_settings.directory
        try:
            if not directory.is_dir():
                raise FileNotFoundError(
                    f"Configuration directory not found: {directory}"
                )
            file_hashes: Dict[Path, str] = {}
            for path in sorted(directory.iterdir()):
                if (
                    path.name.startswith(".")
                    or path.suffix.lower() not in {".yml", ".yaml"}
                    or not path.is_file()
                    or path.is_symlink()
                ):
                    continue
                file_size = path.stat().st_size
                if file_size > MAX_CONFIG_FILE_BYTES:
                    file_hashes[path] = f"oversize:{file_size}"
                else:
                    file_hashes[path] = hashlib.sha256(path.read_bytes()).hexdigest()
            fingerprint_data = [
                (path.name, digest) for path, digest in sorted(file_hashes.items())
            ]
            fingerprint = hashlib.sha256(
                json.dumps(fingerprint_data).encode("utf-8")
            ).hexdigest()
            return fingerprint, file_hashes
        except (OSError, UnicodeError) as error:
            self._is_healthy = False
            self._error_message = str(error)
            self._last_check = datetime.now()
            logger.error(
                "Failed to scan scraper configuration directory",
                path=str(directory),
                error=str(error),
                error_type=type(error).__name__,
            )
            return None

    def _build_candidate(
        self, file_hashes: Dict[Path, str]
    ) -> Tuple[Dict[Path, ScraperConfig], Dict[str, str]]:
        candidate: Dict[Path, ScraperConfig] = {}
        errors: Dict[str, str] = {}
        changed_paths = {
            path
            for path, digest in file_hashes.items()
            if self._file_hashes.get(path) != digest
        }

        for path in file_hashes:
            if path not in changed_paths and path in self._accepted_by_path:
                candidate[path] = self._accepted_by_path[path]
                continue
            try:
                candidate[path] = self._loader.load(path)
            except ScraperConfigError as error:
                errors[str(path)] = str(error)
                if path in self._accepted_by_path:
                    candidate[path] = self._accepted_by_path[path]
                    action = "retained_last_good"
                else:
                    action = "ignored_new"
                logger.error(
                    "Invalid scraper configuration file",
                    path=str(path),
                    error=str(error),
                    error_type=type(error).__name__,
                    action=action,
                )

        self._resolve_duplicates(candidate, changed_paths, errors, "id")
        self._resolve_duplicates(candidate, changed_paths, errors, "name")
        return candidate, errors

    def _resolve_duplicates(
        self,
        candidate: Dict[Path, ScraperConfig],
        changed_paths: set,
        errors: Dict[str, str],
        field: str,
    ) -> None:
        grouped: Dict[str, List[Path]] = {}
        for path, scraper in candidate.items():
            grouped.setdefault(getattr(scraper, field), []).append(path)

        for value, paths in grouped.items():
            if len(paths) < 2:
                continue
            prior_owners = [
                path
                for path in paths
                if path in self._accepted_by_path
                and getattr(self._accepted_by_path[path], field) == value
            ]
            owner = prior_owners[0] if len(prior_owners) == 1 else None
            for path in paths:
                if path == owner:
                    continue
                message = f"Duplicate scraper {field}: {value}"
                errors[str(path)] = message
                if path in changed_paths and path in self._accepted_by_path:
                    candidate[path] = self._accepted_by_path[path]
                else:
                    candidate.pop(path, None)
                logger.error(
                    "Duplicate scraper configuration rejected",
                    path=str(path),
                    scraper_field=field,
                    scraper_value=value,
                    action=(
                        "retained_last_good"
                        if path in self._accepted_by_path
                        else "ignored_new"
                    ),
                )

    def validate_scrapers_config(self, scrapers: List[ScraperConfig]) -> List[str]:
        """Validate uniqueness for an already parsed scraper list."""
        errors: List[str] = []
        ids = set()
        names = set()
        for scraper in scrapers:
            if scraper.id in ids:
                errors.append(f"Duplicate scraper id: {scraper.id}")
            ids.add(scraper.id)
            if scraper.name in names:
                errors.append(f"Duplicate scraper name: {scraper.name}")
            names.add(scraper.name)
        return errors

    def get_current_scrapers(self) -> List[ScraperConfig]:
        """Return enabled scrapers in scheduling order."""
        return [
            scraper
            for scraper in self._sort_scrapers(self._accepted_by_path.values())
            if scraper.enabled
        ]

    def get_all_scrapers(self) -> List[ScraperConfig]:
        """Return all accepted scraper files, including disabled ones."""
        return self._sort_scrapers(self._accepted_by_path.values())

    def get_file_errors(self) -> Dict[str, str]:
        """Return per-file validation failures from the latest scan."""
        return self._file_errors.copy()

    def get_current_version(self) -> Optional[ConfigVersion]:
        return self._current_version

    def get_last_diff(self) -> Optional[Dict[str, Any]]:
        return self._last_diff

    def get_status(self) -> ConfigStatus:
        last_check = self._last_check or datetime.now()
        return ConfigStatus(
            version=self._current_version,
            scrapers=self.get_all_scrapers(),
            last_check=last_check,
            next_check=last_check
            + timedelta(seconds=self.file_settings.poll_interval_seconds),
            is_healthy=self._is_healthy,
            error_message=self._error_message,
        )

    def get_current_config_status(self) -> ConfigStatus:
        return self.get_status()

    def get_scrapers_for_octopus(self) -> List[Dict[str, Any]]:
        return [
            {
                "scraper_config": scraper.to_octopus_config(),
                "fetch_params": scraper.fetch_params or {},
            }
            for scraper in self.get_current_scrapers()
        ]

    def compute_scrapers_diff(
        self,
        old_scrapers: List[ScraperConfig],
        new_scrapers: List[ScraperConfig],
    ) -> Dict[str, Any]:
        old_map = {s.id: self._normalize_scraper_for_hash(s) for s in old_scrapers}
        new_map = {s.id: self._normalize_scraper_for_hash(s) for s in new_scrapers}
        added = sorted(set(new_map) - set(old_map))
        removed = sorted(set(old_map) - set(new_map))
        modified = []
        for scraper_id in sorted(set(old_map) & set(new_map)):
            fields = sorted(
                field
                for field in old_map[scraper_id]
                if old_map[scraper_id][field] != new_map[scraper_id][field]
            )
            if fields:
                modified.append({"id": scraper_id, "fields": fields})
        return {"added": added, "removed": removed, "modified": modified}

    def _sort_scrapers(self, scrapers) -> List[ScraperConfig]:
        return sorted(scrapers, key=lambda scraper: (scraper.priority, scraper.id))

    def _normalize_scraper_for_hash(self, scraper: ScraperConfig) -> Dict[str, Any]:
        normalized = replace(scraper, source_path=None)
        return {
            "id": normalized.id,
            "name": normalized.name,
            "enabled": normalized.enabled,
            "fetcher": normalized.fetcher,
            "hub_root": normalized.hub_root,
            "route": normalized.route,
            "fetch_params": normalized.fetch_params or {},
            "priority": normalized.priority,
            "content_processor_configs": normalized.content_processor_configs or {},
            "default_keywords": sorted(normalized.default_keywords or []),
        }

    def _calculate_config_hash(self, scrapers: List[ScraperConfig]) -> str:
        data = [
            self._normalize_scraper_for_hash(scraper)
            for scraper in sorted(scrapers, key=lambda scraper: scraper.id)
        ]
        return hashlib.sha256(
            json.dumps(data, sort_keys=True).encode("utf-8")
        ).hexdigest()

    def _create_config_version(self, scrapers: List[ScraperConfig]) -> ConfigVersion:
        config_hash = self._calculate_config_hash(scrapers)
        timestamp = datetime.now()
        return ConfigVersion(
            version_id=f"v{timestamp.strftime('%Y%m%d_%H%M%S')}_{config_hash[:8]}",
            timestamp=timestamp,
            config_hash=config_hash,
            scrapers_count=len(scrapers),
        )

    def _create_change_summary(self, diff: Dict[str, Any]) -> str:
        parts = []
        for key in ("added", "removed"):
            if diff[key]:
                parts.append(f"{key}={diff[key]}")
        if diff["modified"]:
            parts.append(
                "modified="
                + str(
                    [
                        f"{item['id']}({','.join(item['fields'])})"
                        for item in diff["modified"]
                    ]
                )
            )
        return "; ".join(parts) or "Configuration updated"

    def _format_errors(self) -> Optional[str]:
        if not self._file_errors:
            return None
        return "; ".join(
            f"{path}: {error}" for path, error in sorted(self._file_errors.items())
        )
