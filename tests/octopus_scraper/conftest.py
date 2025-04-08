import pytest
from unittest.mock import MagicMock
from octopus_scraper.scrapers.scraper import BaseScraperConfig, Content, Scraper
from octopus_scraper.scrapers.utils.notion_api import NotionAPIConfig


@pytest.fixture
def dummy_scraper_config():
    return BaseScraperConfig(
        fetcher_name="rsshub",
        fecher_config={
            "hub_root": "https://rsshub.app/test",
            "route": "/api",
            "fetch_params": {},
        },
        content_processor_configs={},
    )


@pytest.fixture
def dummy_notion_config():
    return NotionAPIConfig(api_key="dummy-key", database_id="dummy-db")


@pytest.fixture
def dummy_content():
    return Content(
        title="Test Title", link="https://example.com", summary="Test Summary"
    )


@pytest.fixture
def dummy_octopus_config(dummy_scraper_config, dummy_notion_config):
    return {
        "scrapers_config_with_fetch_param": [
            (dummy_scraper_config, {"param1": "value1"})
        ],
        "notion_api_config": dummy_notion_config,
    }


@pytest.fixture(autouse=False)
def patch_scraper_scrap(monkeypatch, dummy_content):
    monkeypatch.setattr(
        Scraper, "scrap_contents", lambda self, fetch_params: [dummy_content]
    )


@pytest.fixture(autouse=False)
def patch_notion(monkeypatch):
    from octopus_scraper.scrapers.utils import notion_api

    class DummyNotionStorage:
        def __init__(self, config):
            self.config = config
            self.stored = []

        def store_content(self, content):
            self.stored.append(content)

    monkeypatch.setattr(notion_api, "NotionStorage", DummyNotionStorage)
