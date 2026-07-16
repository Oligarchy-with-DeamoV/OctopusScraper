from pathlib import Path

from octopus_scraper.config.models import (
    DatabaseConfig,
    FileConfigSettings,
    NotionSyncConfig,
    ScraperConfig,
)


def test_scraper_config_status_and_octopus_conversion():
    config = ScraperConfig(
        id="example",
        name="Example",
        enabled=True,
        fetcher="direct_rss",
        hub_root="https://example.com",
        route="/feed.xml",
    )

    assert config.status == "Active"
    assert config.to_octopus_config()["id"] == "example"


def test_runtime_config_models():
    file_config = FileConfigSettings(Path("/tmp/scrapers"))
    database_config = DatabaseConfig("sqlite://")
    sync_config = NotionSyncConfig()

    assert file_config.poll_interval_seconds == 1.0
    assert database_config.pool_size == 5
    assert sync_config.enabled is False
