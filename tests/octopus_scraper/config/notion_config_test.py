"""
Tests for config/notion_config.py module.
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from octopus_scraper.config.models import NotionDatabaseConfig, ScraperConfig
from octopus_scraper.config.notion_config import NotionConfigClient


class TestNotionConfigClient:
    @pytest.fixture
    def notion_config(self):
        return NotionDatabaseConfig(
            api_key="test_api_key",
            scrapers_database_id="test_scrapers_db",
            content_database_id="test_content_db",
        )

    @pytest.fixture
    def notion_client(self, notion_config):
        return NotionConfigClient(notion_config)

    @pytest.mark.asyncio
    async def test_validate_connection_success(self, notion_client):
        """Test successful connection validation."""
        with patch.object(
            notion_client.client.databases, "retrieve", new_callable=AsyncMock
        ) as mock_retrieve, patch.object(
            notion_client.client.databases, "update", new_callable=AsyncMock
        ) as mock_update:
            mock_retrieve.return_value = {"id": "database_id", "properties": {}}
            mock_update.return_value = {"id": "database_id"}

            result = await notion_client.validate_connection()

            assert result == True
            # 3 calls: scrapers DB, schema check retrieve, content DB
            assert mock_retrieve.call_count == 3

    @pytest.mark.asyncio
    async def test_validate_connection_failure(self, notion_client):
        """Test connection validation failure."""
        with patch.object(
            notion_client.client.databases, "retrieve", new_callable=AsyncMock
        ) as mock_retrieve:
            mock_retrieve.side_effect = Exception("Connection failed")

            result = await notion_client.validate_connection()

            assert result == False

    @pytest.mark.asyncio
    async def test_ensure_scrapers_database_schema_creates_missing_columns(
        self, notion_client
    ):
        """Test that _ensure_scrapers_database_schema only creates missing columns."""
        with patch.object(
            notion_client.client.databases, "retrieve", new_callable=AsyncMock
        ) as mock_retrieve, patch.object(
            notion_client.client.databases, "update", new_callable=AsyncMock
        ) as mock_update:
            # Simulate existing columns — everything except Content Processors
            mock_retrieve.return_value = {
                "id": "database_id",
                "properties": {
                    "Name": {"id": "title"},
                    "Status": {"id": "sel1"},
                    "Fetcher": {"id": "sel2"},
                    "Hub Root": {"id": "url1"},
                    "Route": {"id": "rt1"},
                    "Priority": {"id": "num1"},
                    "Fetch Params": {"id": "rt2"},
                },
            }
            mock_update.return_value = {"id": "database_id"}

            await notion_client._ensure_scrapers_database_schema()

            mock_update.assert_called_once()
            call_kwargs = mock_update.call_args
            properties = call_kwargs.kwargs.get("properties", {}) or call_kwargs[1].get(
                "properties", {}
            )
            # Only the missing column should be created
            assert "Content Processors" in properties
            assert properties["Content Processors"] == {"rich_text": {}}
            # Existing columns should NOT be included (avoids clearing select options)
            assert "Status" not in properties
            assert "Fetcher" not in properties
            assert "Name" not in properties

    @pytest.mark.asyncio
    async def test_ensure_schema_skips_update_when_all_columns_exist(
        self, notion_client
    ):
        """No databases.update() call when all required columns already exist."""
        with patch.object(
            notion_client.client.databases, "retrieve", new_callable=AsyncMock
        ) as mock_retrieve, patch.object(
            notion_client.client.databases, "update", new_callable=AsyncMock
        ) as mock_update:
            # All columns already exist
            mock_retrieve.return_value = {
                "id": "database_id",
                "properties": {
                    "Name": {"id": "title"},
                    "Status": {"id": "sel1"},
                    "Fetcher": {"id": "sel2"},
                    "Hub Root": {"id": "url1"},
                    "Route": {"id": "rt1"},
                    "Priority": {"id": "num1"},
                    "Fetch Params": {"id": "rt2"},
                    "Content Processors": {"id": "rt3"},
                },
            }

            await notion_client._ensure_scrapers_database_schema()

            # Should NOT call update since nothing is missing
            mock_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_schema_failure_does_not_break_validation(self, notion_client):
        """Schema initialization failure should not prevent validate_connection from succeeding."""
        with patch.object(
            notion_client.client.databases, "retrieve", new_callable=AsyncMock
        ) as mock_retrieve, patch.object(
            notion_client.client.databases, "update", new_callable=AsyncMock
        ) as mock_update:
            mock_retrieve.return_value = {"id": "database_id", "properties": {}}
            mock_update.side_effect = Exception("Permission denied")

            result = await notion_client.validate_connection()

            # Should still succeed — schema init failure is a warning, not fatal
            assert result == True

    @pytest.mark.asyncio
    async def test_load_scrapers_config_success(self, notion_client):
        """Test successful scrapers config loading."""
        mock_response = {
            "results": [
                {
                    "properties": {
                        "Name": {"title": [{"plain_text": "Test Scraper"}]},
                        "Status": {"select": {"name": "Active"}},
                        "Fetcher": {"select": {"name": "rsshub"}},
                        "Hub Root": {"url": "https://example.com"},
                        "Route": {"rich_text": [{"plain_text": "/test"}]},
                        "Priority": {"number": 1},
                        "Fetch Params": {"rich_text": [{"plain_text": "{}"}]},
                    }
                }
            ]
        }

        with patch.object(
            notion_client.client.databases, "query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_response

            scrapers = await notion_client.load_scrapers_config()

            assert len(scrapers) == 1
            assert scrapers[0].name == "Test Scraper"
            assert scrapers[0].status == "Active"
            assert scrapers[0].fetcher == "rsshub"
            assert scrapers[0].hub_root == "https://example.com"
            assert scrapers[0].route == "/test"
            assert scrapers[0].priority == 1

    @pytest.mark.asyncio
    async def test_load_scrapers_config_empty(self, notion_client):
        """Test loading empty scrapers config."""
        mock_response = {"results": []}

        with patch.object(
            notion_client.client.databases, "query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_response

            scrapers = await notion_client.load_scrapers_config()

            assert len(scrapers) == 0

    @pytest.mark.asyncio
    async def test_load_scrapers_config_inactive_filtered(self, notion_client):
        """Test that inactive scrapers are filtered out by the database query."""
        # Mock response should only contain active scrapers (as the query filters them)
        mock_response = {
            "results": [
                {
                    "properties": {
                        "Name": {"title": [{"plain_text": "Active Scraper"}]},
                        "Status": {"select": {"name": "Active"}},
                        "Fetcher": {"select": {"name": "rsshub"}},
                        "Hub Root": {"url": "https://example.com"},
                        "Route": {"rich_text": [{"plain_text": "/test"}]},
                        "Priority": {"number": 1},
                        "Fetch Params": {"rich_text": [{"plain_text": "{}"}]},
                    }
                }
                # Inactive scrapers should not be in response since query filters them
            ]
        }

        with patch.object(
            notion_client.client.databases, "query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_response

            scrapers = await notion_client.load_scrapers_config()

            # Verify that the query was called with correct filter
            mock_query.assert_called_once()
            call_args = mock_query.call_args
            assert call_args[1]["filter"]["property"] == "Status"
            assert call_args[1]["filter"]["select"]["equals"] == "Active"

            # Only active scrapers should be returned
            assert len(scrapers) == 1
            assert scrapers[0].name == "Active Scraper"
            assert scrapers[0].status == "Active"

    @pytest.mark.asyncio
    async def test_check_config_changes_true(self, notion_client):
        """Test config changes detection when changes exist."""
        from datetime import datetime

        # Manually set last check time to simulate a previous call
        notion_client._last_scrapers_check = datetime(2025, 6, 20, 10, 0, 0)

        # Mock the database query to return changes
        with patch.object(
            notion_client.client.databases, "query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = {
                "results": [{"id": "changed_record"}]
            }  # Has changes

            result = await notion_client.check_config_changes()

            assert result == True
            # Verify the query was called with the correct filter
            mock_query.assert_called_once()
            call_args = mock_query.call_args
            assert call_args[1]["filter"]["property"] == "Last edited time"

    @pytest.mark.asyncio
    async def test_check_config_changes_false(self, notion_client):
        """Test config changes detection when no changes exist."""
        from datetime import datetime

        # Manually set last check time to simulate a previous call
        notion_client._last_scrapers_check = datetime(2025, 6, 20, 10, 0, 0)

        # Mock the database query to return no changes
        with patch.object(
            notion_client.client.databases, "query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = {"results": []}  # No changes

            result = await notion_client.check_config_changes()

            assert result == False
            # Verify the query was called with the correct filter
            mock_query.assert_called_once()
            call_args = mock_query.call_args
            assert call_args[1]["filter"]["property"] == "Last edited time"

    @pytest.mark.asyncio
    async def test_load_scrapers_config_with_invalid_json(self, notion_client):
        """Test loading scrapers config with invalid JSON in fetch_params."""
        mock_response = {
            "results": [
                {
                    "properties": {
                        "Name": {"title": [{"plain_text": "Test Scraper"}]},
                        "Status": {"select": {"name": "Active"}},
                        "Fetcher": {"select": {"name": "rsshub"}},
                        "Hub Root": {"url": "https://example.com"},
                        "Route": {"rich_text": [{"plain_text": "/test"}]},
                        "Priority": {"number": 1},
                        "Fetch Params": {"rich_text": [{"plain_text": "invalid json"}]},
                    }
                }
            ]
        }

        with patch.object(
            notion_client.client.databases, "query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_response

            scrapers = await notion_client.load_scrapers_config()

            assert len(scrapers) == 1
            assert scrapers[0].fetch_params is None  # Should be None for invalid JSON


class TestScraperConfigFromNotionRecord:
    def test_from_notion_record_complete(self):
        """Test creating ScraperConfig from complete Notion record."""
        record = {
            "properties": {
                "Name": {"title": [{"plain_text": "Test Scraper"}]},
                "Status": {"select": {"name": "Active"}},
                "Fetcher": {"select": {"name": "rsshub"}},
                "Hub Root": {"url": "https://example.com"},
                "Route": {"rich_text": [{"plain_text": "/test/route"}]},
                "Priority": {"number": 5},
                "Fetch Params": {"rich_text": [{"plain_text": '{"key": "value"}'}]},
            }
        }

        scraper = ScraperConfig.from_notion_record(record)

        assert scraper.name == "Test Scraper"
        assert scraper.status == "Active"
        assert scraper.fetcher == "rsshub"
        assert scraper.hub_root == "https://example.com"
        assert scraper.route == "/test/route"
        assert scraper.priority == 5
        assert scraper.fetch_params == {"key": "value"}

    def test_from_notion_record_minimal(self):
        """Test creating ScraperConfig with minimal data."""
        record = {
            "properties": {
                "Name": {"title": [{"plain_text": "Minimal Scraper"}]},
                "Status": {"select": {"name": "Inactive"}},
                "Fetcher": {"select": {"name": "direct_rss"}},
                "Hub Root": {"url": ""},
                "Route": {"rich_text": [{"plain_text": ""}]},
                "Priority": {"number": None},
                "Fetch Params": {"rich_text": [{"plain_text": ""}]},
            }
        }

        scraper = ScraperConfig.from_notion_record(record)

        assert scraper.name == "Minimal Scraper"
        assert scraper.status == "Inactive"
        assert scraper.fetcher == "direct_rss"
        assert scraper.hub_root == ""
        assert scraper.route == ""
        assert scraper.priority == 5  # Default value
        assert scraper.fetch_params is None

    def test_from_notion_record_missing_fields(self):
        """Test creating ScraperConfig with missing fields."""
        record = {"properties": {}}

        scraper = ScraperConfig.from_notion_record(record)

        assert scraper.name == ""
        assert scraper.status == "Inactive"
        assert scraper.fetcher == "rsshub"
        assert scraper.hub_root == ""
        assert scraper.route == ""
        assert scraper.priority == 5
        assert scraper.fetch_params is None
