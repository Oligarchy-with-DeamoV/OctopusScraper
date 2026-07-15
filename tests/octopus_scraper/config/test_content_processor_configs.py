from pathlib import Path

import pytest

from octopus_scraper.config.yaml_config import (
    ScraperConfigError,
    YamlScraperConfigLoader,
)


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_yaml_loader_accepts_processor_mapping(tmp_path):
    path = _write(
        tmp_path / "feed.yaml",
        """
id: feed
name: Feed
enabled: true
fetcher: direct_rss
hub_root: https://example.com
route: /feed.xml
content_processor_configs:
  html_content:
    priority: 10
""",
    )

    config = YamlScraperConfigLoader().load(path)

    assert config.content_processor_configs["html_content"]["priority"] == 10


def test_yaml_loader_rejects_unknown_processor(tmp_path):
    path = _write(
        tmp_path / "feed.yaml",
        """
id: feed
name: Feed
fetcher: direct_rss
hub_root: https://example.com
route: /feed.xml
content_processor_configs:
  missing_processor: {}
""",
    )

    with pytest.raises(ScraperConfigError, match="Unknown processor"):
        YamlScraperConfigLoader().load(path)


def test_yaml_loader_rejects_non_mapping_processor_config(tmp_path):
    path = _write(
        tmp_path / "feed.yaml",
        """
id: feed
name: Feed
fetcher: direct_rss
hub_root: https://example.com
route: /feed.xml
content_processor_configs:
  html_content: invalid
""",
    )

    with pytest.raises(ScraperConfigError, match="must be a mapping"):
        YamlScraperConfigLoader().load(path)
