from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from octopus_scraper.config import (
    DatabaseConfig,
    FileConfigSettings,
    NotionSyncConfig,
    ScraperConfig,
    ServiceConfig,
)
from octopus_scraper.octopus_service import (
    app,
    cleanup_octopus,
    create_config_from_env,
    readiness_check,
    reload_octopus_config,
    setup_octopus,
    trigger_upload,
)


def test_create_config_from_env_defaults():
    with patch.dict("os.environ", {}, clear=True):
        file_config, database, sync, service, task_manager = create_config_from_env()

    assert file_config.directory == Path("resources/scrapers.d")
    assert database.url.startswith("postgresql+psycopg://")
    assert sync.enabled is False
    assert service.port == 8000
    assert task_manager["max_concurrent_tasks"] == 8


def test_create_config_from_env_values():
    env = {
        "SCRAPER_CONFIG_DIR": "/tmp/scrapers",
        "DATABASE_URL": "sqlite:///contents.sqlite3",
        "NOTION_SYNC_ENABLED": "true",
        "NOTION_API_KEY": "key",
        "NOTION_CONTENT_DATABASE_ID": "db",
        "TASK_MANAGER_MAX_CONCURRENT": "12",
    }
    with patch.dict("os.environ", env, clear=True):
        file_config, database, sync, _, task_manager = create_config_from_env()

    assert str(file_config.directory) == "/tmp/scrapers"
    assert database.url == "sqlite:///contents.sqlite3"
    assert sync.api_key == "key"
    assert task_manager["max_concurrent_tasks"] == 12


def test_registered_routes_match_service_surface():
    registered_routes = {
        (route.path, tuple(sorted(route.methods)))
        for route in app.router.routes_all.values()
    }
    assert ("trigger_upload", ("POST",)) in registered_routes
    assert ("admin/config/refresh", ("POST",)) in registered_routes
    assert ("health/readiness", ("GET",)) in registered_routes


@pytest.mark.asyncio
async def test_setup_octopus_registers_callback_before_watcher(tmp_path):
    mock_app = Mock()
    mock_app.ctx = Mock()
    manager = Mock()
    manager.load_initial_config = AsyncMock(return_value=[])
    manager.get_current_version.return_value = Mock(version_id="v1")
    octopus = Mock()

    with patch(
        "octopus_scraper.service.lifecycle.create_config_from_env",
        return_value=(
            FileConfigSettings(tmp_path),
            DatabaseConfig(f"sqlite:///{tmp_path / 'contents.sqlite3'}"),
            NotionSyncConfig(enabled=False),
            ServiceConfig(),
            {"max_concurrent_tasks": 1},
        ),
    ), patch(
        "octopus_scraper.service.lifecycle.ConfigManager", return_value=manager
    ), patch(
        "octopus_scraper.service.lifecycle.Octopus", return_value=octopus
    ):
        await setup_octopus(mock_app, None)

    manager.set_on_config_changed.assert_called_once()
    manager.start_config_watcher.assert_called_once()
    octopus.start_background_services.assert_called_once()


@pytest.mark.asyncio
async def test_reload_octopus_config_uses_active_yaml_scrapers():
    mock_app = Mock()
    manager = Mock()
    manager.get_current_scrapers.return_value = [
        ScraperConfig(
            id="feed",
            name="Feed",
            enabled=True,
            fetcher="direct_rss",
            hub_root="https://example.com",
            route="/feed.xml",
            priority=7,
        )
    ]
    manager.get_current_version.return_value = Mock(version_id="v2")
    mock_app.ctx.config_manager = manager
    mock_app.ctx.octopus = Mock()
    mock_app.ctx.octopus.update_scrapers.return_value = 1

    assert await reload_octopus_config(mock_app) is True
    payload = mock_app.ctx.octopus.update_scrapers.call_args.args[0]
    assert payload[0]["scraper_id"] == "feed"
    assert payload[0]["priority"] == 7


@pytest.mark.asyncio
async def test_cleanup_stops_config_and_octopus():
    mock_app = Mock()
    mock_app.ctx.config_manager = Mock()
    mock_app.ctx.octopus = Mock()

    await cleanup_octopus(mock_app, None)

    mock_app.ctx.config_manager.stop_config_watcher.assert_called_once()
    mock_app.ctx.octopus.cleanup_task_manager.assert_called_once()


@pytest.mark.asyncio
async def test_readiness_depends_on_postgresql():
    mock_request = Mock()
    with patch("octopus_scraper.service.health.app") as health_app:
        health_app.ctx.config_manager.get_status.return_value = Mock(is_healthy=True)
        health_app.ctx.octopus.get_storage.return_value.ping.return_value = True

        response = await readiness_check(mock_request)

    assert response.status == 200


@pytest.mark.asyncio
async def test_readiness_rejects_unhealthy_configuration():
    mock_request = Mock()
    with patch("octopus_scraper.service.health.app") as health_app:
        health_app.ctx.config_manager.get_status.return_value = Mock(is_healthy=False)
        health_app.ctx.octopus.get_storage.return_value.ping.return_value = True

        response = await readiness_check(mock_request)

    assert response.status == 503


@pytest.mark.asyncio
async def test_trigger_upload_returns_incremental_sync_result():
    mock_request = Mock()
    sync_result = {
        "enabled": False,
        "busy": False,
        "claimed_count": 0,
        "synced_count": 0,
        "failed_count": 0,
        "lost_claim_count": 0,
        "errors": [],
    }
    with patch("octopus_scraper.service.routes.app") as routes_app:
        routes_app.ctx.octopus.trigger_upload.return_value = sync_result
        response = await trigger_upload(mock_request)

    assert response.status == 200
    assert b'"claimed_count":0' in response.body
