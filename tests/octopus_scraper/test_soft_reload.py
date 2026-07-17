from octopus_scraper.octopus import Octopus


def _config(tmp_path):
    return {
        "scrapers_config_with_fetch_params": [
            {
                "scraper_config": {
                    "fetcher_name": "direct_rss",
                    "fetcher_config": {
                        "hub_root": "https://example.com",
                        "route": "/feed.xml",
                        "fetch_params": {},
                    },
                    "content_processor_configs": {},
                    "scraper_name": "Feed",
                },
                "fetch_params": {},
                "scraper_id": "feed",
                "priority": 3,
            }
        ],
        "database_config": {
            "url": f"sqlite:///{tmp_path / 'contents.sqlite3'}",
        },
        "notion_sync_config": {"enabled": False},
        "task_manager_config": {
            "persistence_path": str(tmp_path / "tasks.sqlite3"),
        },
    }


def test_update_scrapers_preserves_task_manager_and_storage(tmp_path):
    octopus = Octopus(_config(tmp_path))
    try:
        task_manager = octopus.get_task_manager()
        storage = octopus.get_storage()

        count = octopus.update_scrapers([])

        assert count == 0
        assert octopus.get_task_manager() is task_manager
        assert octopus.get_storage() is storage
    finally:
        octopus.cleanup_task_manager()
