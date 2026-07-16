import os
from dataclasses import asdict

import pytest

from octopus_scraper.scraper import BaseScraperConfig, Content, Scraper


@pytest.fixture
def dummy_scraper_config():
    return BaseScraperConfig(
        fetcher_name="rsshub",
        fetcher_config={
            "hub_root": "https://rss.owo.nz/test",
            "route": "/api",
            "fetch_params": {},
        },
        content_processor_configs={},
    )


@pytest.fixture
def dummy_content():
    return Content(
        title="Test Title",
        link="https://example.com",
        summary="Test Summary",
        content="Test Content",
        content_id="content_id",
        published="2025-04-06T13:50:59+08:00",
    )


@pytest.fixture
def octopus_config(dummy_scraper_config, tmp_path):
    return {
        "scrapers_config_with_fetch_params": [
            {
                "scraper_config": asdict(dummy_scraper_config),
                "fetch_params": {"param1": "value1"},
                "scraper_id": "test-feed",
                "priority": 5,
            }
        ],
        "database_config": {
            "url": f"sqlite:///{tmp_path / 'contents.sqlite3'}",
        },
        "notion_sync_config": {"enabled": False},
        "task_manager_config": {
            "persistence_path": str(tmp_path / "tasks.sqlite3"),
        },
    }


@pytest.fixture(autouse=False)
def patch_scraper_scrap(monkeypatch, dummy_content):
    monkeypatch.setattr(
        Scraper, "scrap_contents", lambda self, fetch_params: [dummy_content]
    )


@pytest.fixture(autouse=False)
def patch_notion():
    """Compatibility fixture for tests that now run with sync disabled."""
