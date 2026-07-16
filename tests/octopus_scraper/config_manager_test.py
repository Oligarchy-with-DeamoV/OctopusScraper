import asyncio
from pathlib import Path

import pytest

from octopus_scraper.config import ConfigManager, FileConfigSettings, ServiceConfig


def _yaml(scraper_id: str, route: str = "/feed.xml", enabled: bool = True) -> str:
    return f"""
id: {scraper_id}
name: {scraper_id.title()}
enabled: {str(enabled).lower()}
fetcher: direct_rss
hub_root: https://example.com
route: {route}
content_processor_configs: {{}}
"""


def _manager(path: Path) -> ConfigManager:
    return ConfigManager(
        FileConfigSettings(
            directory=path,
            poll_interval_seconds=0.01,
            debounce_seconds=0.01,
        ),
        ServiceConfig(config_refresh_interval=0.01),
    )


async def test_initial_load_and_disabled_filtering(tmp_path):
    (tmp_path / "enabled.yaml").write_text(_yaml("enabled"), encoding="utf-8")
    (tmp_path / "disabled.yaml").write_text(
        _yaml("disabled", enabled=False), encoding="utf-8"
    )
    manager = _manager(tmp_path)

    active = await manager.load_initial_config()

    assert [config.id for config in active] == ["enabled"]
    assert [config.id for config in manager.get_all_scrapers()] == [
        "disabled",
        "enabled",
    ]


async def test_add_modify_delete_and_callback(tmp_path):
    first = tmp_path / "first.yaml"
    first.write_text(_yaml("first"), encoding="utf-8")
    manager = _manager(tmp_path)
    await manager.load_initial_config()
    callback_count = 0

    async def callback():
        nonlocal callback_count
        callback_count += 1

    manager.set_on_config_changed(callback)
    second = tmp_path / "second.yaml"
    second.write_text(_yaml("second"), encoding="utf-8")
    assert await manager.reload_config_if_changed() is True
    first.write_text(_yaml("first", route="/updated.xml"), encoding="utf-8")
    assert await manager.reload_config_if_changed() is True
    second.unlink()
    assert await manager.reload_config_if_changed() is True

    assert callback_count == 3
    assert manager.get_current_scrapers()[0].route == "/updated.xml"


async def test_invalid_modification_retains_last_good(tmp_path):
    path = tmp_path / "feed.yaml"
    path.write_text(_yaml("feed"), encoding="utf-8")
    manager = _manager(tmp_path)
    await manager.load_initial_config()

    path.write_text("id: feed\nname: Broken\n", encoding="utf-8")
    changed = await manager.reload_config_if_changed()

    assert changed is False
    assert manager.get_current_scrapers()[0].route == "/feed.xml"
    assert str(path) in manager.get_file_errors()
    assert manager.get_status().is_healthy is True
    assert await manager.reload_config_if_changed() is False
    assert manager.get_status().is_healthy is True


async def test_duplicate_id_is_rejected_without_replacing_owner(tmp_path):
    owner = tmp_path / "owner.yaml"
    owner.write_text(_yaml("feed"), encoding="utf-8")
    manager = _manager(tmp_path)
    await manager.load_initial_config()

    duplicate = tmp_path / "duplicate.yaml"
    duplicate.write_text(
        _yaml("feed").replace("name: Feed", "name: Duplicate"),
        encoding="utf-8",
    )
    await manager.reload_config_if_changed()

    assert [config.name for config in manager.get_all_scrapers()] == ["Feed"]
    assert "Duplicate scraper id" in manager.get_file_errors()[str(duplicate)]


async def test_watcher_debounces_stable_fingerprint(tmp_path):
    manager = _manager(tmp_path)
    await manager.load_initial_config()
    manager.start_config_watcher()
    try:
        (tmp_path / "feed.yaml").write_text(_yaml("feed"), encoding="utf-8")
        await asyncio.sleep(0.06)
        assert [config.id for config in manager.get_current_scrapers()] == ["feed"]
    finally:
        manager.stop_config_watcher()


async def test_runtime_rejection_rolls_back_manager_state(tmp_path):
    path = tmp_path / "feed.yaml"
    path.write_text(_yaml("feed"), encoding="utf-8")
    manager = _manager(tmp_path)
    await manager.load_initial_config()

    async def reject():
        return False

    manager.set_on_config_changed(reject)
    path.write_text(_yaml("feed", route="/rejected.xml"), encoding="utf-8")

    with pytest.raises(RuntimeError, match="Runtime rejected"):
        await manager.reload_config_if_changed()

    assert manager.get_current_scrapers()[0].route == "/feed.xml"
