"""
Tests for content_processor_configs integration in ScraperConfig.

Covers parsing from Notion records, validation in ConfigManager,
and propagation through octopus_service scraper config construction.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from octopus_scraper.config.models import ScraperConfig


class TestScraperConfigContentProcessors:
    """Tests for content_processor_configs field on ScraperConfig."""

    def test_default_content_processor_configs_is_empty_dict(self):
        """Content processor configs defaults to empty dict when not specified."""
        scraper = ScraperConfig(
            name="test",
            status="Active",
            fetcher="rsshub",
            hub_root="https://example.com",
            route="/test",
        )
        assert scraper.content_processor_configs == {}

    def test_to_octopus_config_includes_content_processor_configs(self):
        """to_octopus_config should include content_processor_configs."""
        processor_configs = {"html_content": {}, "llm_summary": {"model": "gpt-4"}}
        scraper = ScraperConfig(
            name="test",
            status="Active",
            fetcher="rsshub",
            hub_root="https://example.com",
            route="/test",
            content_processor_configs=processor_configs,
        )
        result = scraper.to_octopus_config()
        assert result["content_processor_configs"] == processor_configs

    def test_to_octopus_config_empty_processors(self):
        """to_octopus_config should include empty dict when no processors configured."""
        scraper = ScraperConfig(
            name="test",
            status="Active",
            fetcher="rsshub",
            hub_root="https://example.com",
            route="/test",
        )
        result = scraper.to_octopus_config()
        assert result["content_processor_configs"] == {}


class TestFromNotionRecordContentProcessors:
    """Tests for parsing Content Processors column from Notion records."""

    def _make_notion_record(self, content_processors_text=None):
        """Helper to create a Notion record with optional Content Processors."""
        record = {
            "properties": {
                "Name": {"title": [{"plain_text": "Test Scraper"}]},
                "Status": {"select": {"name": "Active"}},
                "Fetcher": {"select": {"name": "rsshub"}},
                "Hub Root": {"url": "https://example.com"},
                "Route": {"rich_text": [{"plain_text": "/test/route"}]},
                "Priority": {"number": 5},
                "Fetch Params": {"rich_text": [{"plain_text": ""}]},
            }
        }
        if content_processors_text is not None:
            record["properties"]["Content Processors"] = {
                "rich_text": [{"plain_text": content_processors_text}]
            }
        return record

    def test_parse_valid_json_processors(self):
        """Valid JSON in Content Processors column should be parsed correctly."""
        configs = {
            "html_content": {},
            "llm_summary": {"model": "gpt-4", "temperature": 0.3},
        }
        record = self._make_notion_record(json.dumps(configs))

        scraper = ScraperConfig.from_notion_record(record)

        assert scraper.content_processor_configs == configs

    def test_parse_empty_string(self):
        """Empty string in Content Processors should result in empty dict."""
        record = self._make_notion_record("")

        scraper = ScraperConfig.from_notion_record(record)

        assert scraper.content_processor_configs == {}

    def test_parse_missing_column(self):
        """Missing Content Processors column should result in empty dict."""
        record = self._make_notion_record()
        # Explicitly remove the key if present
        record["properties"].pop("Content Processors", None)

        scraper = ScraperConfig.from_notion_record(record)

        assert scraper.content_processor_configs == {}

    def test_parse_invalid_json_logs_warning(self):
        """Invalid JSON should log warning and result in empty dict."""
        record = self._make_notion_record("not valid json {{{")

        scraper = ScraperConfig.from_notion_record(record)

        assert scraper.content_processor_configs == {}

    def test_parse_non_dict_json_logs_warning(self):
        """JSON that is not a dict (e.g. a list) should log warning and result in empty dict."""
        record = self._make_notion_record('["html_content", "llm_summary"]')

        scraper = ScraperConfig.from_notion_record(record)

        assert scraper.content_processor_configs == {}

    def test_parse_single_processor(self):
        """Single processor config should be parsed correctly."""
        configs = {"html_content": {"clean_content": True}}
        record = self._make_notion_record(json.dumps(configs))

        scraper = ScraperConfig.from_notion_record(record)

        assert scraper.content_processor_configs == configs
        assert (
            scraper.content_processor_configs["html_content"]["clean_content"] is True
        )

    def test_parse_multiple_processors(self):
        """Multiple processor configs should all be preserved."""
        configs = {
            "html_content": {},
            "llm_summary": {"model": "gpt-4"},
            "llm_tags": {"model": "gpt-3.5-turbo", "temperature": 0.5},
            "llm_keywords": {"model": "gpt-3.5-turbo"},
        }
        record = self._make_notion_record(json.dumps(configs))

        scraper = ScraperConfig.from_notion_record(record)

        assert len(scraper.content_processor_configs) == 4
        assert scraper.content_processor_configs == configs

    def test_existing_fields_still_parsed_correctly(self):
        """Adding Content Processors should not break parsing of other fields."""
        configs = {"html_content": {}}
        record = self._make_notion_record(json.dumps(configs))
        # Also set fetch_params
        record["properties"]["Fetch Params"] = {
            "rich_text": [{"plain_text": '{"limit": 10}'}]
        }

        scraper = ScraperConfig.from_notion_record(record)

        assert scraper.name == "Test Scraper"
        assert scraper.status == "Active"
        assert scraper.fetcher == "rsshub"
        assert scraper.hub_root == "https://example.com"
        assert scraper.route == "/test/route"
        assert scraper.priority == 5
        assert scraper.fetch_params == {"limit": 10}
        assert scraper.content_processor_configs == configs


class TestConfigManagerProcessorValidation:
    """Tests for content_processor_configs validation in ConfigManager."""

    def _make_scraper(self, content_processor_configs=None):
        """Create a valid ScraperConfig with optional processor configs."""
        return ScraperConfig(
            name="test_scraper",
            status="Active",
            fetcher="rsshub",
            hub_root="https://example.com",
            route="/test",
            priority=5,
            content_processor_configs=content_processor_configs or {},
        )

    def test_valid_processor_configs_no_errors(self):
        """Valid processor configs should produce no validation errors."""
        from octopus_scraper.config.config_manager import ConfigManager
        from octopus_scraper.config.models import NotionDatabaseConfig, ServiceConfig

        manager = ConfigManager(
            notion_config=NotionDatabaseConfig(
                api_key="test", scrapers_database_id="test", content_database_id="test"
            ),
            service_config=ServiceConfig(),
        )

        scraper = self._make_scraper(
            {"html_content": {}, "llm_summary": {"model": "gpt-4"}}
        )
        errors = manager.validate_scrapers_config([scraper])

        # Filter only processor-related errors
        processor_errors = [e for e in errors if "processor" in e.lower()]
        assert processor_errors == []

    def test_unknown_processor_key_produces_error(self):
        """Unknown processor key should produce a validation error."""
        from octopus_scraper.config.config_manager import ConfigManager
        from octopus_scraper.config.models import NotionDatabaseConfig, ServiceConfig

        manager = ConfigManager(
            notion_config=NotionDatabaseConfig(
                api_key="test", scrapers_database_id="test", content_database_id="test"
            ),
            service_config=ServiceConfig(),
        )

        scraper = self._make_scraper({"nonexistent_processor": {}})
        errors = manager.validate_scrapers_config([scraper])

        processor_errors = [e for e in errors if "processor" in e.lower()]
        assert len(processor_errors) == 1
        assert "nonexistent_processor" in processor_errors[0]

    def test_non_dict_processor_config_produces_error(self):
        """Non-dict processor config value should produce a validation error."""
        from octopus_scraper.config.config_manager import ConfigManager
        from octopus_scraper.config.models import NotionDatabaseConfig, ServiceConfig

        manager = ConfigManager(
            notion_config=NotionDatabaseConfig(
                api_key="test", scrapers_database_id="test", content_database_id="test"
            ),
            service_config=ServiceConfig(),
        )

        scraper = self._make_scraper({"html_content": "not_a_dict"})
        errors = manager.validate_scrapers_config([scraper])

        processor_errors = [e for e in errors if "processor" in e.lower()]
        assert len(processor_errors) == 1
        assert "must be a dict" in processor_errors[0]

    def test_empty_processor_configs_no_errors(self):
        """Empty processor configs should produce no validation errors."""
        from octopus_scraper.config.config_manager import ConfigManager
        from octopus_scraper.config.models import NotionDatabaseConfig, ServiceConfig

        manager = ConfigManager(
            notion_config=NotionDatabaseConfig(
                api_key="test", scrapers_database_id="test", content_database_id="test"
            ),
            service_config=ServiceConfig(),
        )

        scraper = self._make_scraper({})
        errors = manager.validate_scrapers_config([scraper])

        processor_errors = [e for e in errors if "processor" in e.lower()]
        assert processor_errors == []
