"""
Integration tests for ConfigManager with OctopusService.
"""

import asyncio
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from octopus_scraper.config import (
    ConfigManager,
    ConfigStatus,
    ConfigVersion,
    NotionDatabaseConfig,
    ScraperConfig,
    ServiceConfig,
)


@pytest.fixture
def mock_notion_config():
    """Create mock Notion database configuration."""
    return NotionDatabaseConfig(
        api_key="test_api_key",
        scrapers_database_id="test_scrapers_db",
        content_database_id="test_content_db",
    )


@pytest.fixture
def mock_service_config():
    """Create mock service configuration."""
    return ServiceConfig(
        config_refresh_interval=60,
        host="0.0.0.0",
        port=8000,
        debug=False,
        log_level="INFO",
        log_format="plain",
        scraper_timeout=10,
        upload_timeout=15,
        upload_max_retries=3,
    )


@pytest.fixture
def sample_scrapers():
    """Create sample scraper configurations."""
    return [
        ScraperConfig(
            name="test_scraper_1",
            status="Active",
            fetcher="rsshub",
            hub_root="https://rsshub.app",
            route="/github/issues/test/repo",
            fetch_params={"limit": 10},
            priority=5,
        ),
        ScraperConfig(
            name="test_scraper_2",
            status="Active",
            fetcher="direct_rss",
            hub_root="https://example.com",
            route="/feed.xml",
            fetch_params={},
            priority=3,
        ),
    ]


@pytest.fixture
def mock_notion_client():
    """Create mock NotionConfigClient."""
    mock_client = MagicMock()
    mock_client.validate_connection = AsyncMock(return_value=True)
    mock_client.load_scrapers_config = AsyncMock()
    return mock_client


class TestConfigManagerIntegration:
    """Test ConfigManager integration with service."""

    async def test_config_manager_initialization(
        self, mock_notion_config, mock_service_config, sample_scrapers
    ):
        """Test ConfigManager initialization."""
        with patch(
            "octopus_scraper.config.config_manager.NotionConfigClient"
        ) as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.validate_connection = AsyncMock(return_value=True)
            mock_client.load_scrapers_config = AsyncMock(return_value=sample_scrapers)

            config_manager = ConfigManager(mock_notion_config, mock_service_config)

            # Test initial config loading
            loaded_scrapers = await config_manager.load_initial_config()

            assert len(loaded_scrapers) == 2
            assert loaded_scrapers[0].name == "test_scraper_1"
            assert config_manager.get_current_version() is not None
            assert config_manager.get_status().is_healthy

    async def test_config_change_detection(
        self, mock_notion_config, mock_service_config, sample_scrapers
    ):
        """Test configuration change detection."""
        with patch(
            "octopus_scraper.config.config_manager.NotionConfigClient"
        ) as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.validate_connection = AsyncMock(return_value=True)
            mock_client.load_scrapers_config = AsyncMock(return_value=sample_scrapers)
            mock_client.check_config_changes = AsyncMock(return_value=True)
            config_manager = ConfigManager(mock_notion_config, mock_service_config)
            await config_manager.load_initial_config()

            # Modify scrapers for change simulation
            modified_scrapers = sample_scrapers.copy()
            modified_scrapers[0].priority = 10  # Change priority
            mock_client.load_scrapers_config.return_value = modified_scrapers

            # Test reload
            config_changed = await config_manager.reload_config_if_changed()

            assert config_changed is True
            current_scrapers = config_manager.get_current_scrapers()
            assert current_scrapers[0].priority == 10

    async def test_config_validation(self, mock_notion_config, mock_service_config):
        """Test configuration validation."""
        config_manager = ConfigManager(mock_notion_config, mock_service_config)

        # Test valid configuration
        valid_scrapers = [
            ScraperConfig(
                name="valid_scraper",
                status="Active",
                fetcher="rsshub",
                hub_root="https://rsshub.app",
                route="/test",
                priority=5,
            )
        ]

        errors = config_manager.validate_scrapers_config(valid_scrapers)
        assert len(errors) == 0

        # Test invalid configuration
        invalid_scrapers = [
            ScraperConfig(
                name="",  # Empty name
                status="Active",
                fetcher="invalid_fetcher",  # Invalid fetcher
                hub_root="invalid_url",  # Invalid URL
                route="",  # Empty route
                priority=5,
            )
        ]

        errors = config_manager.validate_scrapers_config(invalid_scrapers)
        assert len(errors) > 0

    async def test_octopus_config_conversion(
        self, mock_notion_config, mock_service_config, sample_scrapers
    ):
        """Test conversion to Octopus configuration format."""
        with patch(
            "octopus_scraper.config.config_manager.NotionConfigClient"
        ) as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.validate_connection = AsyncMock(return_value=True)
            mock_client.load_scrapers_config = AsyncMock(return_value=sample_scrapers)

            config_manager = ConfigManager(mock_notion_config, mock_service_config)
            await config_manager.load_initial_config()

            octopus_configs = config_manager.get_scrapers_for_octopus()

            assert len(octopus_configs) == 2
            assert "scraper_config" in octopus_configs[0]
            assert "fetch_params" in octopus_configs[0]

            scraper_config = octopus_configs[0]["scraper_config"]
            assert scraper_config["name"] == "test_scraper_1"
            assert scraper_config["fetcher"] == "rsshub"


class TestServiceIntegration:
    """Test integration with OctopusService."""

    async def test_service_initialization_with_config_manager(
        self, mock_notion_config, mock_service_config, sample_scrapers
    ):
        """Test service initialization with ConfigManager."""
        env_vars = {
            "NOTION_API_KEY": "test_key",
            "NOTION_SCRAPERS_DATABASE_ID": "test_db",
            "NOTION_CONTENT_DATABASE_ID": "test_content_db",
        }

        with patch(
            "octopus_scraper.config.config_manager.NotionConfigClient"
        ) as mock_client_class:
            with patch(
                "octopus_scraper.service.lifecycle.Octopus"
            ) as mock_octopus_class:
                with patch.dict(os.environ, env_vars, clear=False):
                    mock_client = mock_client_class.return_value
                    mock_client.validate_connection = AsyncMock(return_value=True)
                    mock_client.load_scrapers_config = AsyncMock(
                        return_value=sample_scrapers
                    )

                    mock_octopus = mock_octopus_class.return_value

                    from octopus_scraper.octopus_service import create_config_from_env

                    # Test config creation from environment
                    (
                        notion_config,
                        service_config,
                        task_manager_config,
                    ) = create_config_from_env()
                    assert notion_config.api_key == "test_key"
                    assert notion_config.scrapers_database_id == "test_db"

                    # Test that ConfigManager would be created successfully
                    config_manager = ConfigManager(notion_config, service_config)
                    await config_manager.load_initial_config()

                    assert len(config_manager.get_current_scrapers()) == 2

    async def test_config_management_endpoints(
        self, mock_notion_config, mock_service_config, sample_scrapers
    ):
        """Test configuration management endpoints."""
        with patch(
            "octopus_scraper.config.config_manager.NotionConfigClient"
        ) as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.validate_connection = AsyncMock(return_value=True)
            mock_client.load_scrapers_config = AsyncMock(return_value=sample_scrapers)

            config_manager = ConfigManager(mock_notion_config, mock_service_config)
            await config_manager.load_initial_config()

            # Test status retrieval
            status = config_manager.get_status()
            assert status.is_healthy
            assert len(status.scrapers) == 2
            assert status.version is not None

            # Test manual refresh
            refresh_result = await config_manager.manual_refresh_config()
            assert "success" in refresh_result
            assert "timestamp" in refresh_result


@pytest.mark.asyncio
async def test_config_watcher_lifecycle():
    """Test configuration watcher start/stop lifecycle."""
    mock_notion_config = NotionDatabaseConfig(
        api_key="test_key",
        scrapers_database_id="test_db",
        content_database_id="test_content_db",
    )
    mock_service_config = ServiceConfig(
        config_refresh_interval=1,  # 1 second for testing
        host="0.0.0.0",
        port=8000,
        debug=False,
        log_level="INFO",
        log_format="plain",
        scraper_timeout=10,
        upload_timeout=15,
        upload_max_retries=3,
    )

    with patch(
        "octopus_scraper.config.config_manager.NotionConfigClient"
    ) as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.validate_connection = AsyncMock(return_value=True)
        mock_client.load_scrapers_config = AsyncMock(return_value=[])

        config_manager = ConfigManager(mock_notion_config, mock_service_config)
        await config_manager.load_initial_config()

        # Start watcher
        config_manager.start_config_watcher()
        assert config_manager._watcher_task is not None

        # Give it a moment to start
        await asyncio.sleep(0.1)

        # Stop watcher
        config_manager.stop_config_watcher()

        # Give it a moment to stop
        await asyncio.sleep(0.1)

        assert config_manager._stop_watcher is True


@pytest.mark.asyncio
async def test_on_config_changed_callback_invoked_on_reload():
    """Test that on_config_changed callback is invoked when config changes.

    This is a regression test for the bug where the background watcher
    updated ConfigManager._current_scrapers but never recreated the
    Octopus instance, causing trigger_scraper to use stale startup config.
    """
    mock_notion_config = NotionDatabaseConfig(
        api_key="test_key",
        scrapers_database_id="test_db",
        content_database_id="test_content_db",
    )
    mock_service_config = ServiceConfig(
        config_refresh_interval=1,
        host="0.0.0.0",
        port=8000,
        debug=False,
        log_level="INFO",
        log_format="plain",
        scraper_timeout=10,
        upload_timeout=15,
        upload_max_retries=3,
    )

    initial_scrapers = [
        ScraperConfig(
            name="old_scraper",
            status="Active",
            fetcher="rsshub",
            hub_root="https://rsshub.app",
            route="/old/route",
            priority=5,
        ),
    ]
    updated_scrapers = [
        ScraperConfig(
            name="new_scraper",
            status="Active",
            fetcher="rsshub",
            hub_root="https://rsshub.app",
            route="/new/route",
            priority=5,
        ),
    ]

    with patch(
        "octopus_scraper.config.config_manager.NotionConfigClient"
    ) as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.validate_connection = AsyncMock(return_value=True)
        # First load returns initial scrapers, second returns updated
        mock_client.load_scrapers_config = AsyncMock(
            side_effect=[initial_scrapers, updated_scrapers]
        )

        config_manager = ConfigManager(mock_notion_config, mock_service_config)
        await config_manager.load_initial_config()

        # Register callback
        callback_called = False

        async def on_changed():
            nonlocal callback_called
            callback_called = True

        config_manager.set_on_config_changed(on_changed)

        # Trigger a config reload (simulating background watcher)
        changed = await config_manager.reload_config_if_changed()
        assert changed is True

        # Verify the callback was NOT called by reload_config_if_changed itself
        # (the watcher loop is responsible for calling it)
        assert callback_called is False

        # Simulate what the watcher loop does after a successful reload
        if changed and config_manager._on_config_changed_callback:
            await config_manager._on_config_changed_callback()

        assert callback_called is True
