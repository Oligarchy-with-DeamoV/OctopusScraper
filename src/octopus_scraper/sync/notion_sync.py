"""Incremental PostgreSQL-to-Notion synchronization."""

import threading
import uuid
from typing import Any, Dict, Optional

import structlog

from octopus_scraper.config.models import NotionSyncConfig
from octopus_scraper.storages.notion_storage import NotionStorage
from octopus_scraper.storages.postgres_storage import PostgresStorage

logger = structlog.get_logger(__name__)


class NotionSyncService:
    """Claim canonical rows and synchronize them to optional Notion storage."""

    def __init__(
        self,
        config: Dict[str, Any],
        storage: PostgresStorage,
        notion_storage: Optional[NotionStorage] = None,
    ):
        self.config = NotionSyncConfig(**config)
        self.storage = storage
        self.worker_id = f"notion-sync-{uuid.uuid4()}"
        self._stop_event = threading.Event()
        self._run_lock = threading.Lock()
        self._worker_thread: Optional[threading.Thread] = None
        self.notion_storage = notion_storage

        if self.config.enabled:
            if not self.config.api_key or not self.config.database_id:
                raise ValueError(
                    "NOTION_API_KEY and NOTION_CONTENT_DATABASE_ID are required "
                    "when NOTION_SYNC_ENABLED is true"
                )
            if self.notion_storage is None:
                self.notion_storage = NotionStorage(
                    {
                        "api_key": self.config.api_key,
                        "database_id": self.config.database_id,
                    }
                )

    def start(self) -> None:
        """Start periodic synchronization when enabled."""
        if not self.config.enabled:
            return
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="notion-sync",
        )
        self._worker_thread.start()

    def stop(self) -> None:
        """Stop the periodic worker."""
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5)

    def run_once(self) -> Dict[str, Any]:
        """Synchronize one claimed batch and return detailed statistics."""
        stats: Dict[str, Any] = {
            "enabled": self.config.enabled,
            "busy": False,
            "claimed_count": 0,
            "synced_count": 0,
            "failed_count": 0,
            "lost_claim_count": 0,
            "errors": [],
        }
        if not self.config.enabled:
            return stats
        if not self._run_lock.acquire(blocking=False):
            stats["busy"] = True
            return stats

        claim_id = f"{self.worker_id}:{uuid.uuid4()}"
        try:
            for _ in range(self.config.batch_size):
                contents = self.storage.claim_contents(
                    worker_id=claim_id,
                    batch_size=1,
                    lease_seconds=self.config.lease_seconds,
                    max_attempts=self.config.max_attempts,
                )
                if not contents:
                    break
                content = contents[0]
                stats["claimed_count"] += 1
                if not self.storage.renew_claim(
                    content.content_id,
                    claim_id,
                    self.config.lease_seconds,
                ):
                    stats["lost_claim_count"] += 1
                    continue
                heartbeat_stop = threading.Event()
                claim_lost = threading.Event()
                heartbeat_thread = threading.Thread(
                    target=self._renew_lease_until_stopped,
                    args=(
                        content.content_id,
                        claim_id,
                        heartbeat_stop,
                        claim_lost,
                    ),
                    daemon=True,
                )
                heartbeat_thread.start()
                try:
                    results = self.notion_storage.store_contents(
                        [content], deduplicate=True
                    )
                    success = bool(results and results[0])
                except Exception as error:
                    success = False
                    stats["errors"].append(
                        {"content_id": content.content_id, "error": str(error)}
                    )
                finally:
                    heartbeat_stop.set()
                    heartbeat_thread.join(timeout=1)

                if claim_lost.is_set():
                    stats["lost_claim_count"] += 1
                    continue

                if success:
                    if self.storage.mark_synced(content.content_id, claim_id):
                        stats["synced_count"] += 1
                    else:
                        stats["lost_claim_count"] += 1
                    continue

                error_message = (
                    stats["errors"][-1]["error"]
                    if stats["errors"]
                    and stats["errors"][-1]["content_id"] == content.content_id
                    else "Notion storage returned an unsuccessful result"
                )
                if self.storage.mark_sync_failed(
                    content.content_id,
                    claim_id,
                    error_message,
                    self.config.max_attempts,
                ):
                    stats["failed_count"] += 1
                else:
                    stats["lost_claim_count"] += 1

            log_context = {
                key: value for key, value in stats.items() if key != "errors"
            }
            if stats["errors"] or stats["failed_count"] or stats["lost_claim_count"]:
                logger.error(
                    "Notion synchronization batch completed with errors",
                    errors=stats["errors"],
                    **log_context,
                )
            else:
                logger.info(
                    "Notion synchronization batch completed",
                    **log_context,
                )
            return stats
        finally:
            self._run_lock.release()

    def _renew_lease_until_stopped(
        self,
        content_id: str,
        claim_id: str,
        stop_event: threading.Event,
        claim_lost: threading.Event,
    ) -> None:
        interval = max(self.config.lease_seconds / 3, 0.1)
        while not stop_event.wait(interval):
            try:
                renewed = self.storage.renew_claim(
                    content_id,
                    claim_id,
                    self.config.lease_seconds,
                )
            except Exception as error:
                logger.error(
                    "Failed to renew Notion synchronization lease",
                    content_id=content_id,
                    error=str(error),
                )
                claim_lost.set()
                return
            if not renewed:
                claim_lost.set()
                return

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception as error:
                logger.error(
                    "Periodic Notion synchronization failed",
                    error=str(error),
                    exc_info=True,
                )
            self._stop_event.wait(self.config.interval_seconds)
