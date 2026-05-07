"""Tests for BaseStorage.store_contents method."""

from unittest.mock import MagicMock

import pytest

from octopus_scraper.protos import Content
from octopus_scraper.storages.base_storage import BaseStorage


def _make_content(content_id: str = "id-1", title: str = "Title") -> Content:
    return Content(
        content_id=content_id,
        title=title,
        link="https://example.com",
        summary="summary",
        content="body",
        published="2025-04-06T13:50:59+08:00",
    )


class ConcreteStorage(BaseStorage):
    """Minimal concrete subclass for testing."""

    def __init__(self, existing_ids=None, store_side_effect=None):
        self._existing_ids = existing_ids or set()
        self._store_side_effect = store_side_effect

    def get_all_content_ids(self) -> set:
        return self._existing_ids

    def _store_content(self, content: Content) -> bool:
        if self._store_side_effect:
            effect = self._store_side_effect.pop(0)
            if isinstance(effect, Exception):
                raise effect
            return effect
        return True


class TestStoreContentsEmpty:
    def test_empty_list_returns_empty(self):
        storage = ConcreteStorage()
        assert storage.store_contents([]) == []

    def test_empty_list_dedup_disabled(self):
        storage = ConcreteStorage()
        assert storage.store_contents([], deduplicate=False) == []


class TestStoreContentsDedup:
    def test_single_content_stored_successfully(self):
        storage = ConcreteStorage()
        result = storage.store_contents([_make_content()])
        assert result == [True]

    def test_existing_content_skipped(self):
        storage = ConcreteStorage(existing_ids={"id-1"})
        result = storage.store_contents([_make_content("id-1")])
        # Skipped items get True appended
        assert result == [True]

    def test_mix_of_new_and_existing(self):
        storage = ConcreteStorage(existing_ids={"id-1"})
        contents = [_make_content("id-1"), _make_content("id-2")]
        result = storage.store_contents(contents)
        # id-2 stored (True), id-1 skipped (True appended)
        assert len(result) == 2
        assert all(r is True for r in result)

    def test_batch_internal_dedup_removes_duplicates(self):
        storage = ConcreteStorage()
        contents = [
            _make_content("id-1"),
            _make_content("id-1"),
            _make_content("id-2"),
        ]
        result = storage.store_contents(contents)
        # id-1 stored once, id-2 stored, 1 batch dup skipped
        assert len(result) == 3
        assert all(r is True for r in result)

    def test_batch_internal_dedup_keeps_first_occurrence(self):
        """Verifies the first occurrence is kept when batch-internal dups exist."""
        stored_contents = []

        class TrackingStorage(BaseStorage):
            def get_all_content_ids(self):
                return set()

            def _store_content(self, content):
                stored_contents.append(content)
                return True

        storage = TrackingStorage()
        c1 = _make_content("dup-id")
        c1.title = "First"
        c2 = _make_content("dup-id")
        c2.title = "Second"
        storage.store_contents([c1, c2])
        assert len(stored_contents) == 1
        assert stored_contents[0].title == "First"


class TestStoreContentsNoDedupe:
    def test_dedup_disabled_stores_all(self):
        storage = ConcreteStorage(existing_ids={"id-1"})
        contents = [_make_content("id-1"), _make_content("id-2")]
        result = storage.store_contents(contents, deduplicate=False)
        assert result == [True, True]

    def test_dedup_disabled_allows_duplicate_ids(self):
        storage = ConcreteStorage()
        contents = [_make_content("id-1"), _make_content("id-1")]
        result = storage.store_contents(contents, deduplicate=False)
        assert result == [True, True]


class TestStoreContentsErrorHandling:
    def test_store_failure_returns_false(self):
        storage = ConcreteStorage(store_side_effect=[RuntimeError("API error")])
        result = storage.store_contents([_make_content()])
        assert result[0] is False

    def test_partial_failure(self):
        storage = ConcreteStorage(store_side_effect=[True, RuntimeError("fail"), True])
        contents = [_make_content("a"), _make_content("b"), _make_content("c")]
        result = storage.store_contents(contents)
        assert result == [True, False, True]

    def test_all_failures(self):
        storage = ConcreteStorage(
            store_side_effect=[RuntimeError("e1"), RuntimeError("e2")]
        )
        contents = [_make_content("a"), _make_content("b")]
        result = storage.store_contents(contents)
        assert result == [False, False]


class TestStoreContentsResultCounts:
    def test_result_length_matches_input_with_dedup(self):
        storage = ConcreteStorage(existing_ids={"id-2"})
        contents = [
            _make_content("id-1"),
            _make_content("id-1"),  # batch dup
            _make_content("id-2"),  # existing
            _make_content("id-3"),
        ]
        result = storage.store_contents(contents)
        assert len(result) == len(contents)

    def test_result_length_matches_input_no_dedup(self):
        storage = ConcreteStorage()
        contents = [_make_content("a"), _make_content("b"), _make_content("c")]
        result = storage.store_contents(contents, deduplicate=False)
        assert len(result) == 3


class TestBaseStorageAbstract:
    def test_cannot_instantiate_without_store_content(self):
        class Incomplete(BaseStorage):
            def get_all_content_ids(self):
                return set()

        with pytest.raises(TypeError, match="abstract method"):
            Incomplete()

    def test_cannot_instantiate_without_get_all_content_ids(self):
        class Incomplete(BaseStorage):
            def _store_content(self, content):
                return True

        with pytest.raises(TypeError, match="abstract method"):
            Incomplete()
