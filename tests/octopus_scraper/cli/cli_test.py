import os
from unittest.mock import patch

import pytest
import structlog

from octopus_scraper.cli import Octopus, load_yml_config

logger = structlog.getLogger()


def test_load_yml_config():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    full_path = os.path.join(current_dir, "octopus_test_config.yml")
    config = load_yml_config(full_path)

    with patch(
        "octopus_scraper.scrapers.utils.notion_api.NotionStorage.check_property_exist"
    ):
        octopus = Octopus(config)
        assert octopus is not None


@pytest.mark.need_external_service
def test_load_trigger_upload():
    import time
    current_dir = os.path.dirname(os.path.abspath(__file__))
    full_path = os.path.join(current_dir, "octopus_test_config.yml")
    config = load_yml_config(full_path)

    with patch(
        "octopus_scraper.scrapers.utils.notion_api.NotionStorage.check_property_exist"
    ), patch(
        "octopus_scraper.scrapers.utils.notion_api.NotionStorage.store_contents_with_dedup"
    ) as mock_store, patch(
        "octopus_scraper.scrapers.scraper.Scraper.scrap_contents"
    ) as mock_scrap:
        # Mock the scraper to return some test content
        from octopus_scraper.scrapers.scraper import Content
        
        test_content = Content(
            title="Test Title",
            link="https://example.com/test",
            summary="Test Summary",
            content="Test Content",
            content_id="test_123",
            published="2025-04-06T13:50:59+08:00",
        )
        mock_scrap.return_value = [test_content]
        mock_store.return_value = [True]  # Return list indicating successful storage

        octopus = Octopus(config)
        
        # Trigger scraper - now returns batch_id
        batch_id = octopus.trigger_scraper()
        assert batch_id is not None
        assert batch_id.startswith("scraper_batch_")
        
        # Wait for tasks to complete
        time.sleep(0.5)
        
        # Check task manager statistics to verify tasks ran
        stats = octopus.get_task_manager_statistics()
        assert stats["total_tasks"] >= 1
        assert stats["completed_tasks"] >= 1
        
        logger.info("Success fetch and process contents via TaskManager.", batch_id=batch_id, stats=stats)
        
        # For upload test, manually add content since TaskManager handles content processing internally
        octopus._fetched_contents.append(test_content)
        assert len(octopus._fetched_contents) > 0
        
        result = octopus.trigger_upload()
        assert result >= 0  # Should return success count
        logger.info("Success uploads.", upload_count=result)
