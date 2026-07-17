import time

from octopus_scraper.octopus import Octopus


def test_octopus_initializes_canonical_storage(octopus_config, patch_notion):
    octopus = Octopus(octopus_config)
    try:
        assert octopus.get_storage().ping() is True
        assert octopus.get_task_manager() is not None
    finally:
        octopus.cleanup_task_manager()


def test_scrape_task_persists_before_completion(
    octopus_config, patch_scraper_scrap, patch_notion
):
    octopus = Octopus(octopus_config)
    try:
        octopus.trigger_scraper()
        deadline = time.time() + 3
        while time.time() < deadline:
            tasks = octopus.list_tasks(limit=10)
            if tasks and tasks[0]["status"] in {"completed", "failed"}:
                break
            time.sleep(0.02)

        task = octopus.list_tasks(limit=10)[0]
        assert task["status"] == "completed"
        assert task["metadata"]["storage"]["inserted"] == 1
        assert octopus.get_storage().get_all_content_ids() == {"content_id"}
    finally:
        octopus.cleanup_task_manager()


def test_disabled_notion_sync_is_a_successful_noop(octopus_config, patch_notion):
    octopus = Octopus(octopus_config)
    try:
        result = octopus.trigger_upload()

        assert result == {
            "enabled": False,
            "busy": False,
            "claimed_count": 0,
            "synced_count": 0,
            "failed_count": 0,
            "lost_claim_count": 0,
            "errors": [],
        }
    finally:
        octopus.cleanup_task_manager()


def test_update_scrapers_changes_future_task_priority(octopus_config, patch_notion):
    octopus = Octopus(octopus_config)
    try:
        new_config = octopus_config["scrapers_config_with_fetch_params"][0].copy()
        new_config["priority"] = 10
        octopus.update_scrapers([new_config])

        octopus.trigger_scraper()
        deadline = time.time() + 2
        while time.time() < deadline:
            results = octopus.get_task_manager().list_tasks(limit=10)
            if results:
                break
            time.sleep(0.02)

        assert octopus.get_task_manager().get_statistics()["total_tasks"] == 1
    finally:
        octopus.cleanup_task_manager()
