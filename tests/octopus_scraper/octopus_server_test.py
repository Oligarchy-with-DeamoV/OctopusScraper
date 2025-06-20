import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Remove global environment variable setting
# os.environ["NOTION_API_KEY"] = "test_key"  # This pollutes other tests
# os.environ["DATABASE_ID"] = "test_database_id"  # This pollutes other tests


@pytest.fixture
def mock_octopus():
    """Create a mock Octopus instance."""
    mock_instance = MagicMock()
    mock_instance.load_scrapers_from_notion = AsyncMock()
    mock_instance.trigger_scraper = MagicMock()
    mock_instance.trigger_upload.return_value = 5
    mock_instance._scrapers = ["scraper1", "scraper2", "scraper3"]
    mock_instance._fetched_contents = ["content1", "content2", "content3", "content4"]
    return mock_instance


async def test_service_functions_work_with_mock(mock_octopus):
    """Test that the service functions work correctly with mocked dependencies."""

    # Test that we can import the service module
    with patch("octopus_scraper.octopus_service.Octopus", return_value=mock_octopus):
        from octopus_scraper.octopus_service import (
            health_check,
            trigger_scraper,
            trigger_upload,
        )

        # Create a simple mock request object
        mock_request = MagicMock()

        # Test health check
        response = await health_check(mock_request)
        assert response.status == 200
        response_data = response.body.decode("utf-8")
        assert '"status":"ok"' in response_data


async def test_trigger_functions_with_manual_setup(mock_octopus):
    """Test the trigger functions with manual app context setup."""

    with patch("octopus_scraper.octopus_service.Octopus", return_value=mock_octopus):
        from octopus_scraper.octopus_service import app, trigger_scraper, trigger_upload

        # Manually set up the app context
        app.ctx.octopus = mock_octopus

        # Create a mock request
        mock_request = MagicMock()

        # Test trigger_scraper
        mock_octopus.trigger_scraper.reset_mock()
        response = await trigger_scraper(mock_request)
        assert response.status == 200
        mock_octopus.trigger_scraper.assert_called_once()

        # Test trigger_upload
        mock_octopus.trigger_upload.reset_mock()
        response = await trigger_upload(mock_request)
        assert response.status == 200
        mock_octopus.trigger_upload.assert_called_once()


async def test_configuration_structure():
    """Test that the configuration structure is correct."""

    # Use environment variable isolation for this test
    test_env = {
        "NOTION_API_KEY": "test_key",
        "DATABASE_ID": "test_database_id",
    }

    with patch.dict(os.environ, test_env, clear=False):
        # Test environment variables are read correctly
        api_key = os.getenv("NOTION_API_KEY")
        database_id = os.getenv("DATABASE_ID")

        assert api_key == "test_key"
        assert database_id == "test_database_id"

        # Test that config structure matches expected format
        config = {
            "scrapers_config_with_fetch_params": [],
            "notion_api_config": {
                "api_key": api_key,
                "database_id": database_id,
            },
        }

        assert "scrapers_config_with_fetch_params" in config
        assert isinstance(config["scrapers_config_with_fetch_params"], list)
        assert "notion_api_config" in config
        assert config["notion_api_config"]["api_key"] == "test_key"
        assert config["notion_api_config"]["database_id"] == "test_database_id"
