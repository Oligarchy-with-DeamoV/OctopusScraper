import time

import pytest
import structlog

from octopus_scraper.octopus import Octopus
from octopus_scraper.scrapers.scraper import Content

logger = structlog.getLogger()


@pytest.mark.need_external_service
def test_octopus_initialization(octopus_config):
    octopus = Octopus(octopus_config)
    assert len(octopus._scrapers) == 1
    # Verify TaskManager is always initialized
    assert octopus._task_manager is not None


def test_trigger_scraper(octopus_config, patch_scraper_scrap, patch_notion):
    octopus = Octopus(octopus_config)
    logger.error(octopus_config)
    
    # Trigger scraper returns batch_id now
    batch_id = octopus.trigger_scraper()
    assert batch_id is not None
    assert batch_id.startswith("scraper_batch_")
    
    # Wait for task completion
    time.sleep(0.5)  # Give tasks time to complete
    
    # Check task manager statistics
    stats = octopus.get_task_manager_statistics()
    assert stats["total_tasks"] >= 1
    assert stats["completed_tasks"] >= 1


def test_trigger_upload(octopus_config, patch_scraper_scrap, patch_notion):
    octopus = Octopus(octopus_config)
    
    # Trigger scraper first
    batch_id = octopus.trigger_scraper()
    time.sleep(0.5)  # Wait for completion
    
    # Now test upload - but since TaskManager handles content separately,
    # we need to manually add some content for upload test
    from octopus_scraper.scrapers.scraper import Content
    test_content = Content(
        title="Test Title",
        link="https://example.com", 
        summary="Test Summary",
        content="Test Content",
        content_id="test_id",
        published="2025-04-06T13:50:59+08:00",
    )
    octopus._fetched_contents.append(test_content)
    
    result = octopus.trigger_upload()
    assert result >= 0  # Should return success count
    assert len(octopus._fetched_contents) == 0  # Should be cleared after upload


def test_set_max_concurrent_scrapers(octopus_config, patch_notion):
    """测试动态设置最大并发数"""
    octopus = Octopus(octopus_config)

    # 测试设置不同的并发数
    octopus.set_max_concurrent_scrapers(3)
    assert octopus._config.max_concurrent_scrapers == 3

    octopus.set_max_concurrent_scrapers(10)
    assert octopus._config.max_concurrent_scrapers == 10


def test_concurrent_scraping(octopus_config, patch_scraper_scrap, patch_notion):
    """测试并发抓取功能"""
    # 添加多个scraper配置用于测试并发
    octopus_config["scrapers_config_with_fetch_params"].extend(
        [
            {
                "scraper_config": octopus_config["scrapers_config_with_fetch_params"][
                    0
                ]["scraper_config"],
                "fetch_params": {"limit": 5},
            },
            {
                "scraper_config": octopus_config["scrapers_config_with_fetch_params"][
                    0
                ]["scraper_config"],
                "fetch_params": {"limit": 3},
            },
        ]
    )

    octopus = Octopus(octopus_config)
    assert len(octopus._scrapers) == 3  # 现在应该有3个scraper

    # Trigger scraper returns batch_id
    batch_id = octopus.trigger_scraper()
    assert batch_id is not None
    
    # Wait for all tasks to complete
    time.sleep(1.0)
    
    # Check task manager statistics - should have 3 completed tasks
    stats = octopus.get_task_manager_statistics()
    assert stats["total_tasks"] == 3
    assert stats["completed_tasks"] == 3
