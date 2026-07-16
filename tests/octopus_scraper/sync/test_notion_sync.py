import threading
import time
from unittest.mock import Mock

from octopus_scraper.protos import Content
from octopus_scraper.storages.postgres_storage import (
    SYNC_RETRY,
    SYNC_SYNCED,
    PostgresStorage,
)
from octopus_scraper.sync import NotionSyncService


def _content(content_id: str) -> Content:
    return Content(
        content_id=content_id,
        title="Title",
        link=f"https://example.com/{content_id}",
        summary="Summary",
        content="Body",
        published="2026-01-01",
    )


def _storage(tmp_path) -> PostgresStorage:
    storage = PostgresStorage({"url": f"sqlite:///{tmp_path / 'contents.sqlite3'}"})
    storage.initialize()
    return storage


def test_disabled_sync_does_not_call_notion(tmp_path):
    storage = _storage(tmp_path)
    notion = Mock()
    service = NotionSyncService(
        {"enabled": False},
        storage,
        notion_storage=notion,
    )
    try:
        result = service.run_once()

        assert result["enabled"] is False
        notion.store_contents.assert_not_called()
    finally:
        storage.dispose()


def test_overlapping_sync_run_returns_busy(tmp_path):
    storage = _storage(tmp_path)
    notion = Mock()
    service = NotionSyncService(
        {
            "enabled": True,
            "api_key": "key",
            "database_id": "db",
        },
        storage,
        notion_storage=notion,
    )
    service._run_lock.acquire()
    try:
        result = service.run_once()

        assert result["busy"] is True
        notion.store_contents.assert_not_called()
    finally:
        service._run_lock.release()
        storage.dispose()


def test_sync_success_updates_state(tmp_path):
    storage = _storage(tmp_path)
    storage.store_contents([_content("one")])
    notion = Mock()
    notion.store_contents.return_value = [True]
    service = NotionSyncService(
        {
            "enabled": True,
            "api_key": "key",
            "database_id": "db",
            "batch_size": 10,
        },
        storage,
        notion_storage=notion,
    )
    try:
        result = service.run_once()

        assert result["synced_count"] == 1
        assert storage.get_record("one").notion_sync_status == SYNC_SYNCED
    finally:
        storage.dispose()


def test_sync_failure_records_retry(tmp_path):
    storage = _storage(tmp_path)
    storage.store_contents([_content("one")])
    notion = Mock()
    notion.store_contents.side_effect = RuntimeError("notion unavailable")
    service = NotionSyncService(
        {
            "enabled": True,
            "api_key": "key",
            "database_id": "db",
            "batch_size": 10,
            "max_attempts": 3,
        },
        storage,
        notion_storage=notion,
    )
    try:
        result = service.run_once()

        assert result["failed_count"] == 1
        assert storage.get_record("one").notion_sync_status == SYNC_RETRY
    finally:
        storage.dispose()


def test_long_sync_renews_lease(tmp_path):
    storage = _storage(tmp_path)
    storage.store_contents([_content("one")])
    notion = Mock()

    def slow_store(*args, **kwargs):
        time.sleep(1.3)
        return [True]

    notion.store_contents.side_effect = slow_store
    service = NotionSyncService(
        {
            "enabled": True,
            "api_key": "key",
            "database_id": "db",
            "batch_size": 1,
            "lease_seconds": 1,
        },
        storage,
        notion_storage=notion,
    )
    result_holder = {}

    thread = threading.Thread(
        target=lambda: result_holder.setdefault("result", service.run_once())
    )
    thread.start()
    time.sleep(1.1)
    competing_claim = storage.claim_contents("other-worker", 1, 1, 3)
    thread.join(timeout=3)

    try:
        assert competing_claim == []
        assert result_holder["result"]["synced_count"] == 1
    finally:
        storage.dispose()
