import os
from dataclasses import asdict
from unittest.mock import MagicMock

import pytest

from octopus_scraper.scraper import BaseScraperConfig, Content, Scraper
from octopus_scraper.storages.notion_storage import NotionAPIConfig


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
def notion_config():
    return NotionAPIConfig(
        api_key=os.environ.get("NOTION_API_KEY", ""),
        database_id=os.environ.get("NOTION_CONTENT_DATABASE_ID", ""),
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
def octopus_config(dummy_scraper_config, notion_config):
    return {
        "scrapers_config_with_fetch_params": [
            {
                "scraper_config": asdict(dummy_scraper_config),
                "fetch_params": {"param1": "value1"},
            }
        ],
        "notion_api_config": asdict(notion_config),
    }


@pytest.fixture(autouse=False)
def patch_scraper_scrap(monkeypatch, dummy_content):
    monkeypatch.setattr(
        Scraper, "scrap_contents", lambda self, fetch_params: [dummy_content]
    )


@pytest.fixture(autouse=False)
def patch_notion(monkeypatch):
    class DummyNotionStorage:
        def __init__(self, config):
            self.config = config
            self.stored = []

        def store_contents(self, contents, deduplicate=False):
            return [True] * len(contents)

    monkeypatch.setattr("octopus_scraper.octopus.NotionStorage", DummyNotionStorage)
