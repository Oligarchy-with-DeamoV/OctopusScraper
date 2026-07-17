from octopus_scraper.protos import Content
from octopus_scraper.storages.postgres_storage import (
    SYNC_RETRY,
    SYNC_SYNCED,
    PostgresStorage,
)


def _content(content_id: str) -> Content:
    return Content(
        content_id=content_id,
        title=f"Title {content_id}",
        link=f"https://example.com/{content_id}",
        summary="Summary",
        content="Body",
        published="2026-01-01T00:00:00Z",
        keywords=["one"],
        tags=["tag"],
        scraper_name="Feed",
    )


def _storage(tmp_path) -> PostgresStorage:
    storage = PostgresStorage({"url": f"sqlite:///{tmp_path / 'contents.sqlite3'}"})
    storage.initialize()
    return storage


def test_store_and_deduplicate_contents(tmp_path):
    storage = _storage(tmp_path)
    try:
        first = storage.store_contents_with_stats([_content("one"), _content("one")])
        second = storage.store_contents_with_stats([_content("one")])

        assert first == {"requested": 2, "inserted": 1, "duplicates": 1}
        assert second == {"requested": 1, "inserted": 0, "duplicates": 1}
        assert storage.get_all_content_ids() == {"one"}
    finally:
        storage.dispose()


def test_claims_are_disjoint_and_success_is_fenced(tmp_path):
    storage = _storage(tmp_path)
    try:
        storage.store_contents([_content("one"), _content("two")])

        first = storage.claim_contents("worker-1", 1, 60, 3)
        second = storage.claim_contents("worker-2", 1, 60, 3)

        assert first[0].content_id != second[0].content_id
        assert storage.renew_claim(second[0].content_id, "worker-1", 60) is False
        assert storage.renew_claim(second[0].content_id, "worker-2", 60) is True
        assert storage.mark_synced(first[0].content_id, "wrong-worker") is False
        assert storage.mark_synced(first[0].content_id, "worker-1") is True
        assert storage.get_record(first[0].content_id).notion_sync_status == SYNC_SYNCED
    finally:
        storage.dispose()


def test_failed_sync_is_scheduled_for_retry(tmp_path):
    storage = _storage(tmp_path)
    try:
        storage.store_contents([_content("one")])
        claimed = storage.claim_contents("worker", 1, 60, 3)

        assert storage.mark_sync_failed("one", "worker", "temporary", 3)
        record = storage.get_record("one")

        assert claimed[0].content_id == "one"
        assert record.notion_sync_status == SYNC_RETRY
        assert record.notion_sync_attempts == 1
        assert record.notion_sync_error == "temporary"
    finally:
        storage.dispose()
