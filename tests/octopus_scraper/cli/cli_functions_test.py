"""
Tests for CLI module functionality.
"""

import os
import tempfile
from unittest.mock import patch

import yaml

from octopus_scraper.cli import load_yml_config


class TestCLIFunctions:
    def test_load_yml_config_valid_file(self):
        """Test loading valid YAML config file."""
        config_data = {
            "notion_api_config": {"api_key": "test_key", "database_id": "test_db"},
            "scrapers_config_with_fetch_params": [
                {
                    "scraper_config": {
                        "fetcher_name": "rsshub",
                        "fetcher_config": {
                            "hub_root": "https://example.com",
                            "route": "/test",
                            "fetch_params": {},
                        },
                        "content_processor_configs": {},
                    },
                    "fetch_params": {},
                }
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            yaml.dump(config_data, f)
            temp_file = f.name

        try:
            result = load_yml_config(temp_file)
            assert result == config_data
        finally:
            os.unlink(temp_file)

    def test_load_yml_config_missing_file(self):
        """Test loading non-existent config file."""
        import pytest

        with pytest.raises(FileNotFoundError):
            load_yml_config("/path/to/nonexistent/file.yml")

    def test_load_yml_config_invalid_yaml(self):
        """Test loading invalid YAML file."""
        import pytest

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write("invalid: yaml: content: [")
            temp_file = f.name

        try:
            with pytest.raises(yaml.YAMLError):
                load_yml_config(temp_file)
        finally:
            os.unlink(temp_file)

    def test_load_yml_config_empty_file(self):
        """Test loading empty YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write("")
            temp_file = f.name

        try:
            result = load_yml_config(temp_file)
            assert result is None
        finally:
            os.unlink(temp_file)
