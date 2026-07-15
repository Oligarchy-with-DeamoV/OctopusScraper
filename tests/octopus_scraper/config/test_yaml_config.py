from pathlib import Path

import pytest

from octopus_scraper.config.yaml_config import (
    ScraperConfigError,
    YamlScraperConfigLoader,
)


VALID_CONFIG = """
id: example-feed
name: Example Feed
enabled: true
fetcher: direct_rss
hub_root: https://example.com
route: /feed.xml
fetch_params:
  limit: 10
priority: 3
content_processor_configs: {}
default_keywords:
  - rss
  - rss
"""


def _load(tmp_path: Path, text: str):
    path = tmp_path / "feed.yaml"
    path.write_text(text, encoding="utf-8")
    return YamlScraperConfigLoader().load(path)


def test_load_valid_yaml(tmp_path):
    config = _load(tmp_path, VALID_CONFIG)

    assert config.id == "example-feed"
    assert config.enabled is True
    assert config.default_keywords == ["rss"]
    assert config.source_path.endswith("feed.yaml")


def test_reject_yaml_aliases(tmp_path):
    text = VALID_CONFIG.replace(
        "fetch_params:\n  limit: 10",
        "fetch_params: &params\n  limit: 10\nextra_copy: *params",
    )
    text = text.replace("\nextra_copy: *params", "\ndefault_keywords: *params")

    with pytest.raises(ScraperConfigError, match="aliases are not supported"):
        _load(tmp_path, text)


def test_deep_yaml_is_reported_as_config_error(tmp_path):
    nested = "[" * 1500 + "0" + "]" * 1500
    text = VALID_CONFIG.replace("fetch_params:\n  limit: 10", f"fetch_params: {nested}")

    with pytest.raises(ScraperConfigError):
        _load(tmp_path, text)


def test_reject_non_string_yaml_mapping_key(tmp_path):
    text = VALID_CONFIG.replace(
        "fetch_params:\n  limit: 10",
        "fetch_params:\n  ? [nested, key]\n  : value",
    )

    with pytest.raises(ScraperConfigError, match="mapping keys must be strings"):
        _load(tmp_path, text)


@pytest.mark.parametrize(
    "text,error",
    [
        (VALID_CONFIG + "\nunknown: true\n", "Unknown fields"),
        (VALID_CONFIG.replace("id: example-feed", "id: Example Feed"), "id must match"),
        (
            VALID_CONFIG.replace("enabled: true", 'enabled: "yes"'),
            "enabled must be a boolean",
        ),
        (
            VALID_CONFIG.replace("priority: 3", "priority: 11"),
            "priority must be between",
        ),
        (
            VALID_CONFIG.replace("name: Example Feed", "name: A\nname: B"),
            "Duplicate YAML key",
        ),
        (VALID_CONFIG + "\n---\n{}\n", "exactly one YAML document"),
    ],
)
def test_reject_invalid_yaml(tmp_path, text, error):
    with pytest.raises(ScraperConfigError, match=error):
        _load(tmp_path, text)
