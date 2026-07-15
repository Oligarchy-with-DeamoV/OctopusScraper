"""Main scraper orchestrator."""

import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import structlog
from dacite import from_dict

from octopus_scraper.config.models import DatabaseConfig, NotionSyncConfig
from octopus_scraper.scraper import BaseScraperConfig, Scraper
from octopus_scraper.storages.postgres_storage import PostgresStorage
from octopus_scraper.sync import NotionSyncService
from octopus_scraper.task_manager import ScraperTask, TaskBatch, TaskManager

logger = structlog.get_logger(__name__)


@dataclass
class ScraperRuntimeConfig:
    """Runtime scraper configuration and fetch parameters."""

    scraper_config: BaseScraperConfig
    fetch_params: dict
    scraper_id: Optional[str] = None
    priority: int = 5


@dataclass
class OctopusConfig:
    """Octopus runtime dependencies and scraper definitions."""

    scrapers_config_with_fetch_params: List[ScraperRuntimeConfig]
    database_config: DatabaseConfig
    notion_sync_config: NotionSyncConfig
    max_concurrent_scrapers: int = 5
    use_task_manager: bool = True
    task_manager_config: Optional[Dict[str, Any]] = None


class Octopus:
    """Coordinate scraper tasks, canonical persistence and downstream sync."""

    def __init__(self, config: Dict[str, Any]):
        self._config = from_dict(OctopusConfig, config)
        self._scrapers: List[Tuple[Scraper, Dict, str, int]] = []
        self._scrapers_lock = threading.Lock()
        self._storage = PostgresStorage(asdict(self._config.database_config))
        self._storage.initialize()
        self._sync_service = NotionSyncService(
            asdict(self._config.notion_sync_config),
            self._storage,
        )
        self._notion_api = self._sync_service.notion_storage

        task_manager_config = self._config.task_manager_config or {}
        persistence_path = task_manager_config.get(
            "persistence_path", str(Path(".octopus") / "task_results.sqlite3")
        )
        self._task_manager = TaskManager(
            max_concurrent_tasks=task_manager_config.get(
                "max_concurrent_tasks", self._config.max_concurrent_scrapers
            ),
            max_queue_size=task_manager_config.get("max_queue_size", 1000),
            result_retention_hours=task_manager_config.get(
                "result_retention_hours", 24
            ),
            persistence_path=persistence_path,
        )
        self._task_manager.set_storage(self._storage)
        self._setup()

    def _setup(self) -> None:
        for runtime_config in self._config.scrapers_config_with_fetch_params:
            self._scrapers.append(self._build_scraper(runtime_config))

    def _build_scraper(
        self, runtime_config: ScraperRuntimeConfig
    ) -> Tuple[Scraper, Dict, str, int]:
        scraper = Scraper(asdict(runtime_config.scraper_config))
        scraper.set_storage(self._storage)
        scraper_id = runtime_config.scraper_id or (
            runtime_config.scraper_config.scraper_name
            or runtime_config.scraper_config.fetcher_name
        )
        return (
            scraper,
            runtime_config.fetch_params,
            scraper_id,
            runtime_config.priority,
        )

    def update_scrapers(
        self, scrapers_config_with_fetch_params: List[Dict[str, Any]]
    ) -> int:
        """Atomically replace scrapers without interrupting submitted tasks."""
        runtime_configs = [
            from_dict(ScraperRuntimeConfig, item)
            for item in scrapers_config_with_fetch_params
        ]
        new_scrapers = [self._build_scraper(config) for config in runtime_configs]
        with self._scrapers_lock:
            self._config.scrapers_config_with_fetch_params = runtime_configs
            self._scrapers = new_scrapers
        logger.info(
            "Octopus scrapers hot-swapped without restarting TaskManager",
            scraper_count=len(new_scrapers),
        )
        return len(new_scrapers)

    def set_max_concurrent_scrapers(self, max_workers: int) -> None:
        """Update the reported scraper concurrency setting."""
        self._config.max_concurrent_scrapers = max_workers

    def start_background_services(self) -> None:
        """Start optional periodic downstream synchronization."""
        self._sync_service.start()

    def trigger_scraper(self) -> str:
        """Submit one independent task per currently enabled scraper."""
        with self._scrapers_lock:
            scraper_snapshot = list(self._scrapers)

        tasks = []
        for scraper, params, scraper_id, priority in scraper_snapshot:
            scraper_config = {
                "id": scraper_id,
                "name": scraper.config.scraper_name or scraper.config.fetcher_name,
                "fetcher_name": scraper.config.fetcher_name,
                "fetcher_config": scraper.config.fetcher_config,
                "content_processor_configs": scraper.config.content_processor_configs,
                "default_keywords": scraper.config.default_keywords or [],
                "priority": priority,
            }
            tasks.append(ScraperTask.from_scraper_config(scraper_config, params))

        batch = TaskBatch(
            batch_id=f"scraper_batch_{int(time.time())}",
            tasks=tasks,
            name="Manual Scraper Trigger",
            description="Manually triggered scraper batch execution",
        )
        submitted_ids = self._task_manager.submit_batch(batch)
        logger.info(
            "Scraper tasks submitted to TaskManager",
            batch_id=batch.batch_id,
            task_count=len(tasks),
            submitted_count=len(submitted_ids),
        )
        return batch.batch_id

    def trigger_upload(self) -> Dict[str, Any]:
        """Trigger one PostgreSQL-to-Notion incremental synchronization batch."""
        return self._sync_service.run_once()

    def get_storage(self) -> PostgresStorage:
        """Return canonical storage for health and diagnostics."""
        return self._storage

    def get_sync_status(self) -> Dict[str, Any]:
        """Return current downstream synchronization state counts."""
        return {
            "enabled": self._sync_service.config.enabled,
            "counts": self._storage.get_sync_counts(),
        }

    def get_task_manager(self) -> TaskManager:
        return self._task_manager

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        result = self._task_manager.get_task_result(task_id)
        if not result:
            return None
        return self._serialize_task_result(result)

    def list_tasks(
        self, status: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        from octopus_scraper.task_manager.models import TaskStatus

        task_status = None
        if status:
            try:
                task_status = TaskStatus(status)
            except ValueError:
                logger.warning("Invalid task status", status=status)
                return []
        return [
            self._serialize_task_result(result)
            for result in self._task_manager.list_tasks(status=task_status, limit=limit)
        ]

    def _serialize_task_result(self, result) -> Dict[str, Any]:
        return {
            "task_id": result.task_id,
            "status": result.status.value,
            "start_time": result.start_time.isoformat(),
            "end_time": result.end_time.isoformat() if result.end_time else None,
            "duration_seconds": result.duration_seconds,
            "items_fetched": result.items_fetched,
            "items_processed": result.items_processed,
            "items_uploaded": result.items_uploaded,
            "error_message": result.error_message,
            "metadata": result.metadata,
        }

    def cancel_task(self, task_id: str) -> bool:
        return self._task_manager.cancel_task(task_id)

    def get_task_manager_statistics(self) -> Dict[str, Any]:
        return self._task_manager.get_statistics()

    def submit_individual_scraper_task(
        self,
        scraper_name: str,
        scraper_config: Dict[str, Any],
        fetch_params: Dict[str, Any],
    ) -> str:
        task = ScraperTask.from_scraper_config(scraper_config, fetch_params)
        task.scraper_name = scraper_name
        return self._task_manager.submit_task(task)

    def wait_for_batch_completion(
        self, batch_id: str, timeout_seconds: int = 300
    ) -> Dict[str, Any]:
        """Wait for tasks associated with a batch identifier."""
        start_time = time.time()
        completed_tasks: List[Dict[str, Any]] = []
        failed_tasks: List[Dict[str, Any]] = []
        while time.time() - start_time < timeout_seconds:
            batch_tasks = [
                task
                for task in self.list_tasks(limit=1000)
                if task["metadata"].get("batch_id") == batch_id
            ]
            running = [
                task for task in batch_tasks if task["status"] in {"pending", "running"}
            ]
            completed_tasks = [
                task for task in batch_tasks if task["status"] == "completed"
            ]
            failed_tasks = [task for task in batch_tasks if task["status"] == "failed"]
            if not running:
                break
            time.sleep(1)
        return {
            "batch_id": batch_id,
            "completed": len(completed_tasks),
            "failed": len(failed_tasks),
            "total_items_fetched": sum(
                task["items_fetched"] for task in completed_tasks
            ),
            "timeout": time.time() - start_time >= timeout_seconds,
        }

    def cleanup_task_manager(self) -> None:
        """Stop workers and release storage resources."""
        self._sync_service.stop()
        self._task_manager.stop()
        self._storage.dispose()
