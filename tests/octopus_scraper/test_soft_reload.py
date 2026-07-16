"""Tests for soft reload of scrapers and improved config diff detection.

These tests cover the behavior we want when Notion configuration changes:
1. ``Octopus.update_scrapers`` swaps scrapers without restarting TaskManager.
2. ``ConfigManager._calculate_config_hash`` is stable against irrelevant
   reordering (e.g. ``default_keywords``).
3. ``ConfigManager.compute_scrapers_diff`` reports added/removed/modified
   scrapers with the modified field names.
4. ``ConfigManager.reload_config_if_changed`` skips reload when no semantic
   diff exists, even if the raw payload differs.
"""

from unittest.mock import Mock, patch

import pytest

from octopus_scraper.config.config_manager import ConfigManager
from octopus_scraper.config.models import (
    NotionDatabaseConfig,
    ScraperConfig,
    ServiceConfig,
)
from octopus_scraper.octopus import Octopus

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def octopus_config():
    return {
        "scrapers_config_with_fetch_params": [
            {
                "scraper_config": {
                    "fetcher_name": "rsshub",
                    "fetcher_config": {
                        "hub_root": "https://rsshub.app",
                        "route": "/initial",
                        "fetch_params": {},
                    },
                    "content_processor_configs": {},
                },
                "fetch_params": {"limit": 10},
            }
        ],
        "notion_api_config": {
            "api_key": "test_api_key",
            "database_id": "test_database_id",
        },
        "max_concurrent_scrapers": 2,
        "use_task_manager": True,
        "task_manager_config": {
            "max_concurrent_tasks": 2,
            "max_queue_size": 10,
            "result_retention_hours": 1,
        },
    }


@pytest.fixture
def config_manager():
    notion_config = NotionDatabaseConfig(
        api_key="key",
        scrapers_database_id="db",
        content_database_id="content",
    )
    service_config = ServiceConfig()
    with patch("octopus_scraper.config.config_manager.NotionConfigClient"):
        return ConfigManager(notion_config, service_config)


def _make_scraper(name: str, **overrides) -> ScraperConfig:
    base = {
        "name": name,
        "status": "Active",
        "fetcher": "rsshub",
        "hub_root": "https://rsshub.app",
        "route": f"/{name}",
        "fetch_params": {"limit": 10},
        "priority": 5,
        "content_processor_configs": {},
        "default_keywords": ["a", "b"],
    }
    base.update(overrides)
    return ScraperConfig(**base)


# ---------------------------------------------------------------------------
# Octopus.update_scrapers
# ---------------------------------------------------------------------------


class TestOctopusUpdateScrapers:
    @patch("octopus_scraper.octopus.NotionStorage")
    def test_update_scrapers_preserves_task_manager(
        self, mock_notion_class, octopus_config
    ):
        mock_notion_class.return_value = Mock()
        octopus = Octopus(octopus_config)
        try:
            original_task_manager = octopus._task_manager
            original_notion = octopus._notion_api

            new_scrapers_config = [
                {
                    "scraper_config": {
                        "fetcher_name": "direct_rss",
                        "fetcher_config": {
                            "hub_root": "https://example.com",
                            "route": "/new",
                            "fetch_params": {},
                        },
                        "content_processor_configs": {},
                    },
                    "fetch_params": {"limit": 99},
                },
                {
                    "scraper_config": {
                        "fetcher_name": "rsshub",
                        "fetcher_config": {
                            "hub_root": "https://rsshub.app",
                            "route": "/another",
                            "fetch_params": {},
                        },
                        "content_processor_configs": {},
                    },
                    "fetch_params": {"limit": 1},
                },
            ]

            updated = octopus.update_scrapers(new_scrapers_config)

            assert updated == 2
            assert len(octopus._scrapers) == 2
            assert octopus._scrapers[0][1] == {"limit": 99}
            # TaskManager and NotionStorage instances must be the *same* objects.
            assert octopus._task_manager is original_task_manager
            assert octopus._notion_api is original_notion
        finally:
            octopus.cleanup_task_manager()

    @patch("octopus_scraper.octopus.NotionStorage")
    def test_update_scrapers_with_empty_list(self, mock_notion_class, octopus_config):
        mock_notion_class.return_value = Mock()
        octopus = Octopus(octopus_config)
        try:
            original_task_manager = octopus._task_manager
            assert octopus.update_scrapers([]) == 0
            assert octopus._scrapers == []
            assert octopus._task_manager is original_task_manager
        finally:
            octopus.cleanup_task_manager()


# ---------------------------------------------------------------------------
# ConfigManager hash + diff
# ---------------------------------------------------------------------------


class TestConfigManagerDiff:
    def test_hash_is_stable_against_keyword_reorder(self, config_manager):
        a = [_make_scraper("s1", default_keywords=["x", "y", "z"])]
        b = [_make_scraper("s1", default_keywords=["z", "x", "y"])]

        assert config_manager._calculate_config_hash(
            a
        ) == config_manager._calculate_config_hash(b)

    def test_hash_is_stable_against_scraper_reorder(self, config_manager):
        a = [_make_scraper("s1"), _make_scraper("s2")]
        b = [_make_scraper("s2"), _make_scraper("s1")]

        assert config_manager._calculate_config_hash(
            a
        ) == config_manager._calculate_config_hash(b)

    def test_hash_changes_on_real_diff(self, config_manager):
        a = [_make_scraper("s1", route="/old")]
        b = [_make_scraper("s1", route="/new")]

        assert config_manager._calculate_config_hash(
            a
        ) != config_manager._calculate_config_hash(b)

    def test_compute_scrapers_diff_added_removed(self, config_manager):
        old = [_make_scraper("s1"), _make_scraper("s2")]
        new = [_make_scraper("s2"), _make_scraper("s3")]

        diff = config_manager.compute_scrapers_diff(old, new)

        assert diff["added"] == ["s3"]
        assert diff["removed"] == ["s1"]
        assert diff["modified"] == []

    def test_compute_scrapers_diff_modified_fields(self, config_manager):
        old = [_make_scraper("s1", route="/old", priority=5)]
        new = [_make_scraper("s1", route="/new", priority=7)]

        diff = config_manager.compute_scrapers_diff(old, new)

        assert diff["added"] == []
        assert diff["removed"] == []
        assert diff["modified"] == [{"name": "s1", "fields": ["priority", "route"]}]

    def test_compute_scrapers_diff_keyword_reorder_is_not_modified(
        self, config_manager
    ):
        old = [_make_scraper("s1", default_keywords=["a", "b", "c"])]
        new = [_make_scraper("s1", default_keywords=["c", "a", "b"])]

        diff = config_manager.compute_scrapers_diff(old, new)

        assert diff == {"added": [], "removed": [], "modified": []}


# ---------------------------------------------------------------------------
# ConfigManager.reload_config_if_changed integration
# ---------------------------------------------------------------------------


class TestReloadIfChanged:
    async def test_skip_reload_when_only_keyword_reordered(self, config_manager):
        initial = [_make_scraper("s1", default_keywords=["a", "b"])]
        # Seed initial state as if load_initial_config had run.
        config_manager._current_scrapers = initial
        config_manager._current_version = config_manager._create_config_version(initial)

        reordered = [_make_scraper("s1", default_keywords=["b", "a"])]
        config_manager.notion_client.load_scrapers_config = Mock(return_value=reordered)

        # AsyncMock-like behaviour: load_scrapers_config is awaited.
        async def _load():
            return reordered

        config_manager.notion_client.load_scrapers_config = _load

        changed = await config_manager.reload_config_if_changed()
        assert changed is False
        assert config_manager.get_last_diff() is None

    async def test_reload_when_real_change(self, config_manager):
        initial = [_make_scraper("s1", route="/old")]
        config_manager._current_scrapers = initial
        config_manager._current_version = config_manager._create_config_version(initial)

        async def _load():
            return [_make_scraper("s1", route="/new")]

        config_manager.notion_client.load_scrapers_config = _load

        changed = await config_manager.reload_config_if_changed()
        assert changed is True
        diff = config_manager.get_last_diff()
        assert diff is not None
        assert diff["modified"] == [{"name": "s1", "fields": ["route"]}]
