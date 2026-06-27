"""
Tests for octopus_service.py module.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from sanic import Sanic

from octopus_scraper.config import NotionDatabaseConfig, ServiceConfig
from octopus_scraper.octopus_service import (  # New admin interface functions
    app,
    cleanup_octopus,
    create_config_from_env,
    get_config_status,
    get_monitoring_metrics,
    get_task_stats,
    health_check,
    list_scrapers,
    list_tasks,
    refresh_config,
    reload_octopus_config,
    setup_octopus,
    trigger_scraper,
    trigger_upload,
)


class TestConfigCreation:
    def test_create_config_from_env_with_defaults(self):
        """Test config creation with default values."""
        with patch.dict("os.environ", {}, clear=True):
            (
                notion_config,
                service_config,
                task_manager_config,
            ) = create_config_from_env()

            assert notion_config.api_key == ""
            assert notion_config.scrapers_database_id == ""
            assert notion_config.content_database_id == ""

            assert service_config.host == "0.0.0.0"
            assert service_config.port == 8000
            assert service_config.debug == False
            assert service_config.log_level == "INFO"
            assert service_config.config_refresh_interval == 300

            # Test TaskManager config defaults
            assert task_manager_config["max_concurrent_tasks"] == 8
            assert task_manager_config["max_queue_size"] == 1000
            assert task_manager_config["result_retention_hours"] == 48

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
            "MAX_CONCURRENT_TASKS": "12",
            "MAX_QUEUE_SIZE": "2000",
            "RESULT_RETENTION_HOURS": "72",
        }

        with patch.dict("os.environ", env_vars):
            (
                notion_config,
                service_config,
                task_manager_config,
            ) = create_config_from_env()

            assert notion_config.api_key == "test_key"
            assert notion_config.scrapers_database_id == "test_scrapers_db"
            assert notion_config.content_database_id == "test_content_db"

            assert service_config.host == "127.0.0.1"
            assert service_config.port == 9000
            assert service_config.debug == True
            assert service_config.log_level == "DEBUG"
            assert service_config.config_refresh_interval == 600

            # Test TaskManager config with custom values
            assert task_manager_config["max_concurrent_tasks"] == 12
            assert task_manager_config["max_queue_size"] == 2000
            assert task_manager_config["result_retention_hours"] == 72


class TestServiceRouteSurface:
    def test_registered_routes_match_slim_api_surface(self):
        """Test only the documented core service routes are registered."""
        registered_routes = {
            (route.path, tuple(sorted(route.methods)))
            for route in app.router.routes_all.values()
        }

        assert registered_routes == {
            ("health", ("GET",)),
            ("health/liveness", ("GET",)),
            ("health/readiness", ("GET",)),
            ("trigger_scraper", ("POST",)),
            ("trigger_upload", ("POST",)),
            ("admin/config/status", ("GET",)),
            ("admin/config/refresh", ("POST",)),
            ("admin/system/info", ("GET",)),
            ("admin/scrapers", ("GET",)),
            ("admin/tasks/stats", ("GET",)),
            ("admin/tasks", ("GET",)),
            ("admin/tasks/<task_id:str>", ("GET",)),
            ("admin/monitoring/metrics", ("GET",)),
        }


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
            "octopus_scraper.service.lifecycle.create_config_from_env"
        ) as mock_create_config, patch(
            "octopus_scraper.service.lifecycle.ConfigManager"
        ) as mock_config_class, patch(
            "octopus_scraper.service.lifecycle.Octopus"
        ) as mock_octopus_class:

            # Setup mocks
            mock_create_config.return_value = (
                NotionDatabaseConfig("test_key", "test_db", "test_content_db"),
                ServiceConfig(),
                {
                    "max_concurrent_tasks": 8,
                    "max_queue_size": 1000,
                    "result_retention_hours": 48,
                },
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
            "octopus_scraper.service.lifecycle.create_config_from_env"
        ) as mock_create_config:
            mock_create_config.return_value = (
                NotionDatabaseConfig("", "", ""),  # Missing required fields
                ServiceConfig(),
                {
                    "max_concurrent_tasks": 8,
                    "max_queue_size": 1000,
                    "result_retention_hours": 48,
                },
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

        with patch("octopus_scraper.service.lifecycle.Octopus") as mock_octopus_class:
            mock_octopus_class.return_value = Mock()

            result = await reload_octopus_config(mock_app)

            assert result == True
            assert mock_app.ctx.octopus is not None


class TestHealthCheck:
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

        with patch("octopus_scraper.service.health.app") as mock_app:
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

        with patch("octopus_scraper.service.health.app") as mock_app:
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
    async def test_readiness_check_skip_notion(self):
        """Test readiness probe with Notion check skipped."""
        from octopus_scraper.octopus_service import readiness_check

        mock_request = Mock()
        mock_status = Mock()
        mock_status.is_healthy = True

        with patch("octopus_scraper.service.health.app") as mock_app:
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

        with patch("octopus_scraper.service.health.app") as mock_app:
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

        with patch("octopus_scraper.service.admin.app") as mock_app:
            mock_manager = Mock()
            mock_manager.get_status.return_value = mock_status
            mock_app.ctx.config_manager = mock_manager

            response = await get_config_status(mock_request)

            assert response.status == 200


class TestAdminEndpoints:
    """Test the new admin interface endpoints."""

    @pytest.fixture
    def mock_app_with_full_context(self):
        """Create a mock app with complete context for admin tests."""
        from datetime import datetime

        from octopus_scraper.config.models import (
            ConfigStatus,
            ConfigVersion,
            ScraperConfig,
        )

        mock_app = Mock()

        # Mock ConfigManager
        mock_config_manager = Mock()
        mock_status = ConfigStatus(
            is_healthy=True,
            last_check=datetime.now(),
            next_check=datetime.now(),
            version=ConfigVersion(
                version_id="test_v1",
                timestamp=datetime.now(),
                config_hash="test_hash_123",
                scrapers_count=1,
                change_summary="Test changes",
            ),
            scrapers=[
                ScraperConfig(
                    name="test_scraper",
                    status="Active",
                    fetcher="rsshub",
                    hub_root="https://example.com",
                    route="/test",
                    fetch_params={"limit": 10},
                    priority=1,
                )
            ],
            error_message=None,
        )
        mock_config_manager.get_status.return_value = mock_status
        mock_config_manager.get_current_version.return_value = mock_status.version
        mock_config_manager.get_current_scrapers.return_value = mock_status.scrapers
        mock_config_manager.service_config = Mock()
        mock_config_manager.service_config.config_refresh_interval = 300
        mock_config_manager.service_config.scraper_timeout = 10
        mock_config_manager.service_config.upload_timeout = 15
        mock_config_manager.service_config.upload_max_retries = 3
        mock_config_manager.service_config.log_level = "INFO"
        mock_config_manager.service_config.log_format = "plain"
        mock_config_manager.notion_config = Mock()
        mock_config_manager.notion_config.api_key = "test_api_key"
        mock_config_manager.notion_config.scrapers_database_id = "test_scrapers_db"
        mock_config_manager.notion_config.content_database_id = "test_content_db"
        mock_config_manager.notion_client = Mock()

        # Create a simple async function that returns True
        async def mock_validate_connection():
            return True

        mock_config_manager.notion_client.validate_connection = mock_validate_connection

        # Mock Octopus
        mock_octopus = Mock()
        mock_octopus._scrapers = [(Mock(), {"limit": 10})]
        mock_octopus._scrapers[0][0].activate_fetcher = Mock()
        mock_octopus._scrapers[0][0].storage = Mock()
        mock_octopus._scrapers[0][0].active_content_processor = []
        mock_octopus._fetched_contents = ["content1", "content2"]
        mock_octopus._config = Mock()
        mock_octopus._config.max_concurrent_scrapers = 5
        mock_octopus._config.use_task_manager = True  # TaskManager 现在默认启用

        # Mock TaskManager (always enabled now)
        mock_task_manager = Mock()
        mock_task_manager.get_statistics.return_value = {
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "running_tasks_count": 0,
            "current_queue_size": 0,
            "max_concurrent_tasks": 8,
            "queue_capacity": 1000,
            "success_rate_percent": 100.0,
            "average_task_duration_seconds": 1.5,
        }
        mock_octopus._task_manager = mock_task_manager
        mock_octopus.get_task_manager.return_value = mock_task_manager

        mock_app.ctx.config_manager = mock_config_manager
        mock_app.ctx.octopus = mock_octopus

        return mock_app

    @pytest.mark.asyncio
    async def test_get_config_status(self, mock_app_with_full_context):
        """Test the config status endpoint."""
        mock_request = Mock()

        with patch("octopus_scraper.service.admin.app", mock_app_with_full_context):
            response = await get_config_status(mock_request)

            assert response.status == 200
            data = response.body
            assert "config_status" in str(data)
            assert "is_healthy" in str(data)

    @pytest.mark.asyncio
    async def test_refresh_config_success(self, mock_app_with_full_context):
        """Test successful configuration refresh and reload."""
        from octopus_scraper.octopus_service import refresh_config

        mock_request = Mock()

        # Setup mock for config change detection
        mock_app_with_full_context.ctx.config_manager.reload_config_if_changed = (
            AsyncMock(return_value=True)
        )

        with patch("octopus_scraper.service.admin.app", mock_app_with_full_context):
            with patch(
                "octopus_scraper.service.admin.reload_octopus_config",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_reload:
                response = await refresh_config(mock_request)

                assert response.status == 200
                data = response.body
                assert "reload_performed" in str(data)
                assert "true" in str(data).lower()
                mock_reload.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_config_no_changes(self, mock_app_with_full_context):
        """Test refresh when no configuration changes are detected.

        Even when ConfigManager reports no changes, the endpoint should
        still reload Octopus to ensure it is in sync (the background
        watcher may have updated ConfigManager without recreating Octopus).
        """
        from octopus_scraper.octopus_service import refresh_config

        mock_request = Mock()

        # Setup mock for no config changes
        mock_app_with_full_context.ctx.config_manager.reload_config_if_changed = (
            AsyncMock(return_value=False)
        )

        with patch("octopus_scraper.service.admin.app", mock_app_with_full_context):
            with patch(
                "octopus_scraper.service.admin.reload_octopus_config",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_reload:
                response = await refresh_config(mock_request)

                assert response.status == 200
                data = response.body
                assert "reload_performed" in str(data)
                assert "true" in str(data).lower()
                # Octopus reload is always performed to stay in sync
                mock_reload.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_scrapers(self, mock_app_with_full_context):
        """Test the scrapers list endpoint."""
        from octopus_scraper.octopus_service import list_scrapers

        mock_request = Mock()

        with patch("octopus_scraper.service.admin.app", mock_app_with_full_context):
            response = await list_scrapers(mock_request)

            assert response.status == 200
            data = response.body
            assert "scrapers" in str(data)
            assert "summary" in str(data)
            assert "test_scraper" in str(data)

    @pytest.mark.asyncio
    async def test_task_stats_with_task_manager(self, mock_app_with_full_context):
        """Test task stats when task manager is enabled (always enabled now)."""
        from octopus_scraper.octopus_service import get_task_stats

        mock_request = Mock()

        # Mock task manager statistics
        mock_task_manager = Mock()
        mock_task_manager.get_statistics.return_value = {
            "total_tasks": 5,
            "completed_tasks": 3,
            "failed_tasks": 1,
            "running_tasks_count": 1,
            "current_queue_size": 2,
            "max_concurrent_tasks": 4,
            "queue_capacity": 100,
        }
        mock_app_with_full_context.ctx.octopus.get_task_manager.return_value = (
            mock_task_manager
        )

        with patch("octopus_scraper.service.admin.app", mock_app_with_full_context):
            response = await get_task_stats(mock_request)

            assert response.status == 200
            data = response.body
            assert "task_manager_enabled" in str(data)
            assert "true" in str(data).lower()
            assert "legacy_mode" in str(data)
            assert "false" in str(data).lower()

    @pytest.mark.asyncio
    async def test_get_monitoring_metrics(self, mock_app_with_full_context):
        """Test monitoring metrics endpoint."""
        from octopus_scraper.octopus_service import get_monitoring_metrics

        mock_request = Mock()

        with patch("octopus_scraper.service.admin.app", mock_app_with_full_context):
            response = await get_monitoring_metrics(mock_request)

            assert response.status == 200
            data = response.body
            assert "metrics" in str(data)
            assert "service" in str(data)
            assert "configuration" in str(data)

    @pytest.mark.asyncio
    async def test_list_tasks_with_task_manager_enabled(
        self, mock_app_with_full_context
    ):
        """Test task listing when task manager is enabled (always enabled now)."""
        from octopus_scraper.octopus_service import list_tasks

        mock_request = Mock()
        mock_request.args.get = Mock(
            side_effect=lambda key, default=None: {"limit": "10"}.get(key, default)
        )

        # Mock the list_tasks method to return a proper list
        task_list = [
            {"task_id": "task_1", "status": "completed"},
            {"task_id": "task_2", "status": "running"},
        ]
        mock_app_with_full_context.ctx.octopus.list_tasks = Mock(return_value=task_list)

        with patch("octopus_scraper.service.admin.app", mock_app_with_full_context):
            response = await list_tasks(mock_request)

            assert response.status == 200
            data = response.body
            assert "task_manager_enabled" in str(data)
            assert "true" in str(data).lower()
            assert "tasks" in str(data)

    @pytest.mark.asyncio
    async def test_list_tasks_with_task_manager(self, mock_app_with_full_context):
        """Test task listing when task manager is enabled."""
        from octopus_scraper.octopus_service import list_tasks

        mock_request = Mock()
        mock_request.args.get = Mock(
            side_effect=lambda key, default=None: {"limit": "10"}.get(key, default)
        )

        # Enable task manager and configure octopus.list_tasks properly
        mock_task_manager = Mock()
        mock_app_with_full_context.ctx.octopus._task_manager = mock_task_manager

        # Use a simple Mock that returns data without creating coroutines
        task_list = [
            {"task_id": "task_1", "status": "completed"},
            {"task_id": "task_2", "status": "running"},
        ]
        mock_app_with_full_context.ctx.octopus.list_tasks = Mock(return_value=task_list)

        with patch("octopus_scraper.service.admin.app", mock_app_with_full_context):
            response = await list_tasks(mock_request)

            assert response.status == 200
            data = response.body
            assert "task_manager_enabled" in str(data)
            assert "true" in str(data).lower()
            assert "tasks" in str(data)
