import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from octopus_scraper.service import admin, health


def _response_payload(response):
    return json.loads(response.body)


async def test_health_check_reports_dependencies_and_reuses_cache():
    now = datetime.now()
    config_status = SimpleNamespace(
        is_healthy=True,
        last_check=now,
        next_check=now + timedelta(seconds=30),
        version=SimpleNamespace(version_id="version-1"),
        scrapers=[
            SimpleNamespace(enabled=True),
            SimpleNamespace(enabled=False),
        ],
        error_message=None,
    )
    config_manager = SimpleNamespace(
        file_settings=SimpleNamespace(directory="/configs"),
        get_status=Mock(return_value=config_status),
        get_file_errors=Mock(return_value={}),
    )
    storage = Mock()
    storage.ping.return_value = True
    octopus = SimpleNamespace(
        _scrapers=[object()],
        get_storage=Mock(return_value=storage),
        get_sync_status=Mock(return_value={"enabled": True, "running": True}),
    )
    request = SimpleNamespace(args={"cache": "true"})
    app = SimpleNamespace(
        ctx=SimpleNamespace(config_manager=config_manager, octopus=octopus)
    )

    health._health_cache["last_check"] = None
    health._health_cache["cached_result"] = None
    try:
        with (
            patch.object(health, "app", app),
            patch.object(health, "_get_memory_usage", return_value={"rss_mb": 12}),
        ):
            response = await health.health_check(request)
            cached_response = await health.health_check(request)

        payload = _response_payload(response)
        assert response.status == 200
        assert payload["status"] == "healthy"
        assert payload["configuration"]["scrapers_count"] == 2
        assert payload["dependencies"]["postgresql"]["status"] == "healthy"
        assert payload["dependencies"]["octopus_instance"]["notion_sync"] == {
            "enabled": True,
            "running": True,
        }
        assert payload["performance"]["memory_usage"] == {"rss_mb": 12}

        cached_payload = _response_payload(cached_response)
        assert cached_response.status == 200
        assert cached_payload["cached"] is True
        storage.ping.assert_called_once()
    finally:
        health._health_cache["last_check"] = None
        health._health_cache["cached_result"] = None


async def test_system_info_reports_runtime_configuration(monkeypatch):
    config_manager = SimpleNamespace(
        file_settings=SimpleNamespace(
            directory="/configs",
            poll_interval_seconds=2.5,
            debounce_seconds=0.5,
        ),
        service_config=SimpleNamespace(
            scraper_timeout=10,
            upload_timeout=15,
            upload_max_retries=3,
            log_level="INFO",
            log_format="json",
        ),
    )
    task_manager = Mock()
    task_manager.get_statistics.return_value = {"completed_tasks": 4}
    octopus = SimpleNamespace(
        _scrapers=[object(), object()],
        _config=SimpleNamespace(max_concurrent_scrapers=7),
        _storage=SimpleNamespace(
            config=SimpleNamespace(url="postgresql://localhost/octopus")
        ),
        get_sync_status=Mock(return_value={"enabled": True}),
        get_task_manager=Mock(return_value=task_manager),
    )
    app = SimpleNamespace(
        ctx=SimpleNamespace(config_manager=config_manager, octopus=octopus)
    )
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("OCTOPUS_DEBUG", "true")

    with (
        patch.object(admin, "app", app),
        patch.object(admin, "_get_memory_usage", return_value={"rss_mb": 24}),
    ):
        response = await admin.get_system_info(SimpleNamespace())

    payload = _response_payload(response)
    system_info = payload["system_info"]
    assert response.status == 200
    assert system_info["service"]["environment"] == "production"
    assert system_info["service"]["debug_mode"] is True
    assert system_info["configuration"]["scraper_config_dir"] == "/configs"
    assert system_info["octopus_instance"]["scrapers_configured"] == 2
    assert system_info["octopus_instance"]["max_concurrent_scrapers"] == 7
    assert system_info["storage"]["database_url_configured"] is True
    assert system_info["task_manager"]["statistics"] == {"completed_tasks": 4}
    assert system_info["memory_usage"] == {"rss_mb": 24}


async def test_config_status_reports_versions_and_scrapers():
    now = datetime.now()
    config_status = SimpleNamespace(
        is_healthy=True,
        last_check=now,
        version=SimpleNamespace(
            version_id="version-2",
            timestamp=now,
            change_summary="Added active scraper",
        ),
        scrapers=[
            SimpleNamespace(
                id="active",
                name="Active",
                status="ready",
                enabled=True,
                fetcher="rsshub",
                source_path="/configs/active.yaml",
            )
        ],
        error_message=None,
    )
    config_manager = SimpleNamespace(
        get_status=Mock(return_value=config_status),
        get_file_errors=Mock(return_value={}),
    )
    app = SimpleNamespace(ctx=SimpleNamespace(config_manager=config_manager))

    with patch.object(admin, "app", app):
        response = await admin.get_config_status(SimpleNamespace())

    payload = _response_payload(response)["config_status"]
    assert response.status == 200
    assert payload["is_healthy"] is True
    assert payload["version"] == {
        "version_id": "version-2",
        "timestamp": now.isoformat(),
        "change_summary": "Added active scraper",
    }
    assert payload["scrapers"] == [
        {
            "id": "active",
            "name": "Active",
            "status": "ready",
            "enabled": True,
            "fetcher": "rsshub",
            "source_path": "/configs/active.yaml",
        }
    ]
    assert payload["file_errors"] == {}


async def test_config_refresh_reports_applied_changes():
    old_version = SimpleNamespace(version_id="version-1")
    new_version = SimpleNamespace(
        version_id="version-2",
        change_summary="Added active scraper",
    )
    config_manager = SimpleNamespace(
        get_current_version=Mock(side_effect=[old_version, new_version]),
        get_current_scrapers=Mock(side_effect=[[object()], [object(), object()]]),
        reload_config_if_changed=AsyncMock(return_value=True),
        get_file_errors=Mock(return_value={"/configs/broken.yaml": "invalid route"}),
    )
    app = SimpleNamespace(ctx=SimpleNamespace(config_manager=config_manager))

    with patch.object(admin, "app", app):
        response = await admin.refresh_config(SimpleNamespace())

    payload = _response_payload(response)
    assert response.status == 200
    assert payload["config_changed"] is True
    assert payload["reload_performed"] is True
    assert payload["message"] == "Configuration directory changes applied"
    assert payload["changes"] == {
        "old_version": "version-1",
        "new_version": "version-2",
        "old_scrapers_count": 1,
        "new_scrapers_count": 2,
        "change_summary": "Added active scraper",
    }
    assert payload["file_errors"] == {"/configs/broken.yaml": "invalid route"}


async def test_list_scrapers_includes_runtime_state_and_summary():
    active_scraper = SimpleNamespace(
        id="active",
        name="Active",
        status="ready",
        enabled=True,
        fetcher="rsshub",
        hub_root="https://rsshub.example",
        route="/active",
        priority=1,
        fetch_params={"limit": 10},
        source_path="/configs/active.yaml",
    )
    inactive_scraper = SimpleNamespace(
        id="inactive",
        name="Inactive",
        status="disabled",
        enabled=False,
        fetcher="direct_rss",
        hub_root="",
        route="https://example.com/feed.xml",
        priority=2,
        fetch_params={},
        source_path="/configs/inactive.yaml",
    )
    runtime_scraper = SimpleNamespace(
        activate_fetcher=object(),
        storage=object(),
        active_content_processor=[object(), object()],
    )
    config_manager = SimpleNamespace(
        get_all_scrapers=Mock(return_value=[active_scraper, inactive_scraper])
    )
    octopus = SimpleNamespace(_scrapers=[(runtime_scraper, {"limit": 10}, "active", 1)])
    app = SimpleNamespace(
        ctx=SimpleNamespace(config_manager=config_manager, octopus=octopus)
    )

    with patch.object(admin, "app", app):
        response = await admin.list_scrapers(SimpleNamespace())

    payload = _response_payload(response)
    assert response.status == 200
    assert payload["scrapers"][0]["runtime"] == {
        "initialized": True,
        "fetcher_type": "object",
        "has_storage": True,
        "processors_count": 2,
    }
    assert payload["scrapers"][1]["runtime"] == {"initialized": False}
    assert payload["summary"] == {
        "total_count": 2,
        "active_count": 1,
        "inactive_count": 1,
        "fetcher_distribution": {"rsshub": 1, "direct_rss": 1},
    }


async def test_task_stats_reports_capacity_and_utilization():
    task_manager = Mock()
    task_manager.get_statistics.return_value = {
        "current_queue_size": 3,
        "queue_capacity": 100,
        "running_tasks_count": 2,
        "max_concurrent_tasks": 8,
        "completed_tasks": 12,
    }
    octopus = SimpleNamespace(get_task_manager=Mock(return_value=task_manager))
    app = SimpleNamespace(ctx=SimpleNamespace(octopus=octopus))

    with patch.object(admin, "app", app):
        response = await admin.get_task_stats(SimpleNamespace())

    payload = _response_payload(response)["statistics"]
    assert response.status == 200
    assert payload["task_manager_enabled"] is True
    assert payload["legacy_mode"] is False
    assert payload["uptime_info"] == {
        "queue_capacity_usage": "3/100",
        "worker_utilization": "2/8",
    }
    assert payload["completed_tasks"] == 12


async def test_list_tasks_applies_status_filter_and_limit_cap():
    tasks = [{"task_id": "task-1", "status": "completed"}]
    octopus = SimpleNamespace(
        list_tasks=Mock(return_value=tasks),
    )
    app = SimpleNamespace(ctx=SimpleNamespace(octopus=octopus))
    request = SimpleNamespace(args={"status": "completed", "limit": "500"})

    with patch.object(admin, "app", app):
        response = await admin.list_tasks(request)

    payload = _response_payload(response)
    assert response.status == 200
    assert payload["tasks"] == tasks
    assert payload["filters"] == {"status": "completed", "limit": 200}
    assert payload["total_returned"] == 1
    assert payload["task_manager_enabled"] is True
    octopus.list_tasks.assert_called_once_with(status="completed", limit=200)
