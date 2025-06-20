import os

import pytest
from dotenv import load_dotenv

from octopus_scraper.scrapers.scraper import BaseScraperConfig, Content, Scraper
from octopus_scraper.scrapers.utils.notion_api import NotionAPIConfig

load_dotenv()


@pytest.fixture
def owen_scraper_config():
    return BaseScraperConfig(
        fetcher_name="rsshub",
        fetcher_config={
            "hub_root": "https://www.owenyoung.com",
            "route": "/atom.xml",
            "fetch_params": {},
        },
        content_processor_configs={},
    )


@pytest.fixture
def machine_heart_scraper_config():
    return BaseScraperConfig(
        fetcher_name="rsshub",
        fetcher_config={
            "hub_root": "https://raw.githubusercontent.com",
            "route": "/osnsyc/Wechat-Scholar/main/channels/gh_dbc0a5474692.xml",
            "fetch_params": {},
        },
        content_processor_configs={},
    )


@pytest.fixture
def qbitai_scraper_config():
    return BaseScraperConfig(
        fetcher_name="rsshub",
        fetcher_config={
            "hub_root": "https://rss.owo.nz",
            "route": "/qbitai/category/资讯",
            "fetch_params": {},
        },
        content_processor_configs={},
    )


@pytest.fixture
def notion_config():
    return NotionAPIConfig(
        api_key=os.getenv("NOTION_API_KEY", ""),
        database_id=os.getenv("NOTION_CONTENT_DATABASE_ID", ""),
    )


@pytest.fixture
def octopus_config(
    owen_scraper_config,
    machine_heart_scraper_config,
    qbitai_scraper_config,
    notion_config,
):
    return {
        "scrapers_config_with_fetch_params": [
            {"scraper_config": owen_scraper_config, "fetch_params": {}},
            {"scraper_config": machine_heart_scraper_config, "fetch_params": {}},
            {"scraper_config": qbitai_scraper_config, "fetch_params": {}},
        ],
        "notion_api_config": notion_config,
    }
