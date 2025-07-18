"""
Tests for octopus_service.py module.
"""
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sanic import Sanic

from octopus_scraper.config import NotionDatabaseConfig, ServiceConfig
from octopus_scraper.octopus_service import (
    app,
    cleanup_octopus,
    create_config_from_env,
    get_config_status,
    health_check,
    refresh_config,
    reload_octopus_config,
    setup_octopus,
    trigger_scraper,
    trigger_upload,
    validate_config,
)


class TestConfigCreation:
    def test_create_config_from_env_with_defaults(self):
        """Test config creation with default values."""
        with patch.dict("os.environ", {}, clear=True):
            notion_config, service_config = create_config_from_env()

            assert notion_config.api_key == ""
            assert notion_config.scrapers_database_id == ""
            assert notion_config.content_database_id == ""

            assert service_config.host == "0.0.0.0"
            assert service_config.port == 8000
            assert service_config.debug == False
            assert service_config.log_level == "INFO"
            assert service_config.config_refresh_interval == 300

    def test_create_config_from_env_with_values(self):
        """Test config creation with environment variables."""
        env_vars = {
            "NOTION_API_KEY": "test_key",
            "NOTION_SCRAPERS_DATABASE_ID": "test_scrapers_db",
            "NOTION_CONTENT_DATABASE_ID": "test_content_db",
            "SERVICE_HOST": "127.0.0.1",
            "SERVICE_PORT": "9000",
            "DEBUG": "true",
            "LOG_LEVEL": "DEBUG",
            "CONFIG_REFRESH_INTERVAL": "600",
        }

        with patch.dict("os.environ", env_vars):
            notion_config, service_config = create_config_from_env()

            assert notion_config.api_key == "test_key"
            assert notion_config.scrapers_database_id == "test_scrapers_db"
            assert notion_config.content_database_id == "test_content_db"

            assert service_config.host == "127.0.0.1"
            assert service_config.port == 9000
            assert service_config.debug == True
            assert service_config.log_level == "DEBUG"
            assert service_config.config_refresh_interval == 600


class TestServiceLifecycle:
    @pytest.fixture
    def mock_app(self):
        """Create a mock Sanic app."""
        mock_app = Mock()
        mock_app.ctx = Mock()
        return mock_app

    @pytest.fixture
    def mock_config_manager(self):
        """Create a mock ConfigManager."""
        mock_manager = Mock()
        mock_manager.load_initial_config = AsyncMock(return_value=[])
        mock_manager.get_current_version = Mock(return_value=Mock(version_id="test_v1"))
        mock_manager.start_config_watcher = Mock()
        mock_manager.stop_config_watcher = Mock()
        return mock_manager

    @pytest.mark.asyncio
    async def test_setup_octopus_success(self, mock_app, mock_config_manager):
        """Test successful octopus setup."""
        with patch(
            "octopus_scraper.octopus_service.create_config_from_env"
        ) as mock_create_config, patch(
            "octopus_scraper.octopus_service.ConfigManager"
        ) as mock_config_class, patch(
            "octopus_scraper.octopus_service.Octopus"
        ) as mock_octopus_class:

            # Setup mocks
            mock_create_config.return_value = (
                NotionDatabaseConfig("test_key", "test_db", "test_content_db"),
                ServiceConfig(),
            )
            mock_config_class.return_value = mock_config_manager
            mock_octopus_class.return_value = Mock()

            # Test setup
            await setup_octopus(mock_app, None)

            # Verify calls
            assert mock_app.ctx.config_manager == mock_config_manager
            assert mock_app.ctx.octopus is not None
            mock_config_manager.start_config_watcher.assert_called_once()

    @pytest.mark.asyncio
    async def test_setup_octopus_missing_config(self, mock_app):
        """Test setup failure with missing configuration."""
        with patch(
            "octopus_scraper.octopus_service.create_config_from_env"
        ) as mock_create_config:
            mock_create_config.return_value = (
                NotionDatabaseConfig("", "", ""),  # Missing required fields
                ServiceConfig(),
            )

            with pytest.raises(Exception):
                await setup_octopus(mock_app, None)

    @pytest.mark.asyncio
    async def test_cleanup_octopus(self, mock_app, mock_config_manager):
        """Test cleanup process."""
        mock_app.ctx.config_manager = mock_config_manager

        await cleanup_octopus(mock_app, None)

        mock_config_manager.stop_config_watcher.assert_called_once()

    @pytest.mark.asyncio
    async def test_reload_octopus_config(self, mock_app, mock_config_manager):
        """Test configuration reload."""
        mock_app.ctx.config_manager = mock_config_manager
        mock_app.ctx.octopus = Mock()
        mock_app.ctx.octopus._notion_api_config = {
            "api_key": "test",
            "database_id": "test",
        }

        mock_config_manager.get_current_scrapers.return_value = []
        mock_config_manager.get_current_version.return_value = Mock(
            version_id="test_v2"
        )

        with patch("octopus_scraper.octopus_service.Octopus") as mock_octopus_class:
            mock_octopus_class.return_value = Mock()

            result = await reload_octopus_config(mock_app)

            assert result == True
            assert mock_app.ctx.octopus is not None


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_with_config_manager(self):
        """Test health check with config manager available."""
        from datetime import datetime

        mock_request = Mock()
        mock_request.args.get.return_value = "true"  # Mock cache parameter

        mock_status = Mock()
        mock_status.is_healthy = True
        mock_status.last_check = datetime.now()
        mock_status.next_check = datetime.now()
        mock_status.version = Mock(version_id="test_v1")
        mock_status.scrapers = []
        mock_status.error_message = None

        with patch("octopus_scraper.octopus_service.app") as mock_app:
            mock_manager = Mock()
            mock_manager.get_status.return_value = mock_status
            mock_manager.notion_client.validate_connection = AsyncMock(
                return_value=True
            )
            mock_manager.notion_config.scrapers_database_id = "test_scrapers_db"
            mock_manager.notion_config.content_database_id = "test_content_db"
            mock_app.ctx.config_manager = mock_manager
            mock_app.ctx.octopus = Mock()
            mock_app.ctx.octopus._scrapers = []
            mock_app.ctx.octopus._fetched_contents = []

            response = await health_check(mock_request)

            assert response.status == 200

    @pytest.mark.asyncio
    async def test_health_check_without_config_manager(self):
        """Test health check fallback without config manager."""
        mock_request = Mock()
        mock_request.args.get.return_value = "true"  # Mock cache parameter

        with patch.object(app, "ctx", Mock(spec=[])):  # No config_manager attribute
            response = await health_check(mock_request)

            # Without config manager, should still return 200 but with unknown status
            assert response.status == 200

    @pytest.mark.asyncio
    async def test_health_check_with_cache(self):
        """Test health check caching functionality."""
        from datetime import datetime, timedelta

        mock_request = Mock()
        mock_request.args.get.return_value = "true"  # Use cache

        # Mock the cache to simulate cached result
        cache_time = datetime.now() - timedelta(seconds=5)  # 5 seconds ago
        with patch.dict(
            "octopus_scraper.octopus_service._health_cache",
            {
                "cached_result": {
                    "status": "healthy",
                    "timestamp": "2025-07-18T10:00:00.000000",
                    "_status_code": 200,
                },
                "last_check": cache_time,
                "cache_duration": 30,
            },
        ):
            response = await health_check(mock_request)

            assert response.status == 200

    @pytest.mark.asyncio
    async def test_liveness_check(self):
        """Test liveness probe endpoint."""
        from octopus_scraper.octopus_service import liveness_check

        mock_request = Mock()
        response = await liveness_check(mock_request)

        assert response.status == 200

    @pytest.mark.asyncio
    async def test_readiness_check_ready(self):
        """Test readiness probe when service is ready."""
        from octopus_scraper.octopus_service import readiness_check

        mock_request = Mock()
        mock_status = Mock()
        mock_status.is_healthy = True

        with patch("octopus_scraper.octopus_service.app") as mock_app:
            mock_manager = Mock()
            mock_manager.get_status.return_value = mock_status
            mock_manager.notion_client.get_database_info = AsyncMock(
                return_value={"title": "test"}
            )
            mock_app.ctx.config_manager = mock_manager
            mock_app.ctx.octopus = Mock()

            with patch("os.getenv", return_value="false"):  # Don't skip notion check
                response = await readiness_check(mock_request)

            assert response.status == 200

    @pytest.mark.asyncio
    async def test_readiness_check_not_ready(self):
        """Test readiness probe when service is not ready."""
        from octopus_scraper.octopus_service import readiness_check

        mock_request = Mock()

        with patch.object(app, "ctx", Mock(spec=[])):  # No config_manager or octopus
            response = await readiness_check(mock_request)

            assert response.status == 503

    @pytest.mark.asyncio
    async def test_health_check_unhealthy_config(self):
        """Test health check when config manager reports unhealthy status."""
        from datetime import datetime

        mock_request = Mock()
        mock_request.args.get.return_value = "false"  # Disable cache

        mock_status = Mock()
        mock_status.is_healthy = False  # Config is unhealthy
        mock_status.last_check = datetime.now()
        mock_status.next_check = datetime.now()
        mock_status.version = Mock(version_id="test_v1")
        mock_status.scrapers = []
        mock_status.error_message = "Configuration validation failed"

        with patch("octopus_scraper.octopus_service.app") as mock_app:
            mock_manager = Mock()
            mock_manager.get_status.return_value = mock_status
            mock_manager.notion_client.validate_connection = AsyncMock(
                return_value=True
            )
            mock_manager.notion_config.scrapers_database_id = "test_scrapers_db"
            mock_manager.notion_config.content_database_id = "test_content_db"
            mock_app.ctx.config_manager = mock_manager
            mock_app.ctx.octopus = Mock()
            mock_app.ctx.octopus._scrapers = []
            mock_app.ctx.octopus._fetched_contents = []

            response = await health_check(mock_request)

            assert response.status == 503  # Should be unhealthy

    @pytest.mark.asyncio
    async def test_health_check_notion_api_failure(self):
        """Test health check when Notion API is unreachable."""
        from datetime import datetime

        mock_request = Mock()
        mock_request.args.get.return_value = "false"  # Disable cache

        mock_status = Mock()
        mock_status.is_healthy = True
        mock_status.last_check = datetime.now()
        mock_status.next_check = datetime.now()
        mock_status.version = Mock(version_id="test_v1")
        mock_status.scrapers = []
        mock_status.error_message = None

        with patch("octopus_scraper.octopus_service.app") as mock_app:
            mock_manager = Mock()
            mock_manager.get_status.return_value = mock_status
            mock_manager.notion_client.validate_connection = AsyncMock(
                return_value=False
            )  # Notion API fails
            mock_manager.notion_config.scrapers_database_id = "test_scrapers_db"
            mock_manager.notion_config.content_database_id = "test_content_db"
            mock_app.ctx.config_manager = mock_manager
            mock_app.ctx.octopus = Mock()
            mock_app.ctx.octopus._scrapers = []
            mock_app.ctx.octopus._fetched_contents = []

            response = await health_check(mock_request)

            assert response.status == 503  # Should be unhealthy due to Notion failure

    @pytest.mark.asyncio
    async def test_health_check_notion_api_exception(self):
        """Test health check when Notion API validation throws exception."""
        from datetime import datetime

        mock_request = Mock()
        mock_request.args.get.return_value = "false"  # Disable cache

        mock_status = Mock()
        mock_status.is_healthy = True
        mock_status.last_check = datetime.now()
        mock_status.next_check = datetime.now()
        mock_status.version = Mock(version_id="test_v1")
        mock_status.scrapers = []
        mock_status.error_message = None

        with patch("octopus_scraper.octopus_service.app") as mock_app:
            mock_manager = Mock()
            mock_manager.get_status.return_value = mock_status
            mock_manager.notion_client.validate_connection = AsyncMock(
                side_effect=Exception("Connection error")
            )
            mock_manager.notion_config.scrapers_database_id = "test_scrapers_db"
            mock_manager.notion_config.content_database_id = "test_content_db"
            mock_app.ctx.config_manager = mock_manager
            mock_app.ctx.octopus = Mock()
            mock_app.ctx.octopus._scrapers = []
            mock_app.ctx.octopus._fetched_contents = []

            response = await health_check(mock_request)

            assert response.status == 503  # Should be unhealthy due to exception

    @pytest.mark.asyncio
    async def test_health_check_no_cache(self):
        """Test health check with cache disabled."""
        from datetime import datetime

        mock_request = Mock()
        mock_request.args.get.return_value = "false"  # Disable cache

        mock_status = Mock()
        mock_status.is_healthy = True
        mock_status.last_check = datetime.now()
        mock_status.next_check = datetime.now()
        mock_status.version = Mock(version_id="test_v1")
        mock_status.scrapers = []
        mock_status.error_message = None

        with patch("octopus_scraper.octopus_service.app") as mock_app:
            mock_manager = Mock()
            mock_manager.get_status.return_value = mock_status
            mock_manager.notion_client.validate_connection = AsyncMock(
                return_value=True
            )
            mock_manager.notion_config.scrapers_database_id = "test_scrapers_db"
            mock_manager.notion_config.content_database_id = "test_content_db"
            mock_app.ctx.config_manager = mock_manager
            mock_app.ctx.octopus = Mock()
            mock_app.ctx.octopus._scrapers = []
            mock_app.ctx.octopus._fetched_contents = []

            response = await health_check(mock_request)

            assert response.status == 200

    @pytest.mark.asyncio
    async def test_health_check_missing_octopus_with_config_manager(self):
        """Test health check when octopus instance is missing but config manager exists."""
        from datetime import datetime

        mock_request = Mock()
        mock_request.args.get.return_value = "false"  # Disable cache

        mock_status = Mock()
        mock_status.is_healthy = True
        mock_status.last_check = datetime.now()
        mock_status.next_check = datetime.now()
        mock_status.version = Mock(version_id="test_v1")
        mock_status.scrapers = []
        mock_status.error_message = None

        with patch("octopus_scraper.octopus_service.app") as mock_app:
            # Create a mock context that has config_manager but no octopus
            mock_ctx = Mock()
            mock_manager = Mock()
            mock_manager.get_status.return_value = mock_status
            mock_manager.notion_client.validate_connection = AsyncMock(
                return_value=True
            )
            mock_manager.notion_config.scrapers_database_id = "test_scrapers_db"
            mock_manager.notion_config.content_database_id = "test_content_db"
            mock_ctx.config_manager = mock_manager

            # Ensure octopus attribute doesn't exist
            del mock_ctx.octopus  # This will raise AttributeError when accessed
            mock_app.ctx = mock_ctx

            # Make hasattr return False for octopus but True for config_manager
            def mock_hasattr(obj, attr):
                if attr == "octopus":
                    return False
                elif attr == "config_manager":
                    return True
                return False

            with patch("builtins.hasattr", side_effect=mock_hasattr):
                response = await health_check(mock_request)

            assert response.status == 503  # Should be unhealthy due to missing octopus

    @pytest.mark.asyncio
    async def test_health_check_with_scrapers_data(self):
        """Test health check with actual scrapers data."""
        from datetime import datetime

        mock_request = Mock()
        mock_request.args.get.return_value = "false"  # Disable cache

        # Mock scrapers data
        mock_scraper1 = Mock()
        mock_scraper1.status = "Active"
        mock_scraper2 = Mock()
        mock_scraper2.status = "Inactive"

        mock_status = Mock()
        mock_status.is_healthy = True
        mock_status.last_check = datetime.now()
        mock_status.next_check = datetime.now()
        mock_status.version = Mock(version_id="test_v1")
        mock_status.scrapers = [mock_scraper1, mock_scraper2]
        mock_status.error_message = None

        with patch("octopus_scraper.octopus_service.app") as mock_app:
            mock_manager = Mock()
            mock_manager.get_status.return_value = mock_status
            mock_manager.notion_client.validate_connection = AsyncMock(
                return_value=True
            )
            mock_manager.notion_config.scrapers_database_id = "test_scrapers_db"
            mock_manager.notion_config.content_database_id = "test_content_db"
            mock_app.ctx.config_manager = mock_manager
            mock_app.ctx.octopus = Mock()
            mock_app.ctx.octopus._scrapers = ["scraper1", "scraper2"]
            mock_app.ctx.octopus._fetched_contents = [
                "content1",
                "content2",
                "content3",
            ]

            response = await health_check(mock_request)

            assert response.status == 200

    @pytest.mark.asyncio
    async def test_readiness_check_skip_notion(self):
        """Test readiness probe with Notion check skipped."""
        from octopus_scraper.octopus_service import readiness_check

        mock_request = Mock()
        mock_status = Mock()
        mock_status.is_healthy = True

        with patch("octopus_scraper.octopus_service.app") as mock_app:
            mock_manager = Mock()
            mock_manager.get_status.return_value = mock_status
            mock_app.ctx.config_manager = mock_manager
            mock_app.ctx.octopus = Mock()

            with patch("os.getenv", return_value="true"):  # Skip notion check
                response = await readiness_check(mock_request)

            assert response.status == 200

    @pytest.mark.asyncio
    async def test_readiness_check_notion_failure(self):
        """Test readiness probe when Notion check fails."""
        from octopus_scraper.octopus_service import readiness_check

        mock_request = Mock()
        mock_status = Mock()
        mock_status.is_healthy = True

        with patch("octopus_scraper.octopus_service.app") as mock_app:
            mock_manager = Mock()
            mock_manager.get_status.return_value = mock_status
            mock_manager.notion_client.get_database_info = AsyncMock(
                side_effect=Exception("DB error")
            )
            mock_app.ctx.config_manager = mock_manager
            mock_app.ctx.octopus = Mock()

            with patch("os.getenv", return_value="false"):  # Don't skip notion check
                response = await readiness_check(mock_request)

            assert response.status == 503

    @pytest.mark.asyncio
    async def test_health_check_memory_usage_function(self):
        """Test the memory usage helper function."""
        from octopus_scraper.octopus_service import _get_memory_usage

        result = _get_memory_usage()

        assert isinstance(result, dict)
        assert "rss_mb" in result
        # Memory usage should be either a number or "unavailable"
        assert isinstance(result["rss_mb"], (int, float, str))


class TestTriggerEndpoints:
    @pytest.mark.asyncio
    async def test_trigger_scraper_success(self):
        """Test successful scraper trigger."""
        mock_request = Mock()
        mock_octopus = Mock()
        mock_octopus._scrapers = ["scraper1", "scraper2"]
        mock_octopus._fetched_contents = ["content1", "content2", "content3"]

        with patch("octopus_scraper.octopus_service.app") as mock_app, patch(
            "asyncio.to_thread"
        ) as mock_to_thread:

            mock_app.ctx.octopus = mock_octopus
            mock_to_thread.return_value = None

            response = await trigger_scraper(mock_request)

            assert response.status == 200
            mock_to_thread.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_upload_success(self):
        """Test successful upload trigger."""
        mock_request = Mock()
        mock_octopus = Mock()

        with patch("octopus_scraper.octopus_service.app") as mock_app, patch(
            "asyncio.to_thread"
        ) as mock_to_thread:

            mock_app.ctx.octopus = mock_octopus
            mock_to_thread.return_value = 5  # Uploaded count

            response = await trigger_upload(mock_request)

            assert response.status == 200
            mock_to_thread.assert_called_once()


class TestConfigEndpoints:
    @pytest.mark.asyncio
    async def test_get_config_status_success(self):
        """Test config status endpoint."""
        mock_request = Mock()
        mock_status = Mock()
        mock_status.is_healthy = True
        mock_status.last_check = None
        mock_status.error_message = None

        # Create a proper mock version object
        mock_version = Mock()
        mock_version.version_id = "test_v1"
        mock_version.change_summary = "Test changes"

        # Create a proper mock timestamp
        mock_timestamp = Mock()
        mock_timestamp.isoformat.return_value = "2025-01-01T00:00:00"
        mock_version.timestamp = mock_timestamp

        mock_status.version = mock_version
        mock_status.scrapers = []

        with patch("octopus_scraper.octopus_service.app") as mock_app:
            mock_manager = Mock()
            mock_manager.get_status.return_value = mock_status
            mock_app.ctx.config_manager = mock_manager

            response = await get_config_status(mock_request)

            assert response.status == 200

    @pytest.mark.asyncio
    async def test_refresh_config_success(self):
        """Test config refresh endpoint."""
        mock_request = Mock()
        mock_status = Mock()
        mock_status.version = Mock(version_id="test_v1")
        mock_status.scrapers = []

        with patch("octopus_scraper.octopus_service.app") as mock_app, patch(
            "octopus_scraper.octopus_service.reload_octopus_config"
        ) as mock_reload:

            mock_manager = Mock()
            mock_manager.reload_config_if_changed = AsyncMock(return_value=True)
            mock_manager.get_status.return_value = mock_status
            mock_app.ctx.config_manager = mock_manager
            mock_reload.return_value = True

            response = await refresh_config(mock_request)

            assert response.status == 200

    @pytest.mark.asyncio
    async def test_validate_config_success(self):
        """Test config validation endpoint."""
        from octopus_scraper.config.models import ScraperConfig

        mock_request = Mock()
        # Create real ScraperConfig objects instead of Mock objects
        mock_scrapers = [
            ScraperConfig(
                name="test_scraper",
                status="Active",
                fetcher="rsshub",
                hub_root="https://example.com",
                route="/test",
                fetch_params={},
                priority=1,
            )
        ]

        with patch("octopus_scraper.octopus_service.app") as mock_app:
            mock_manager = Mock()
            mock_manager.notion_client.load_scrapers_config = AsyncMock(
                return_value=mock_scrapers
            )
            mock_manager.validate_scrapers_config.return_value = []
            mock_app.ctx.config_manager = mock_manager

            response = await validate_config(mock_request)

            assert response.status == 200
