import pytest
import structlog

from octopus_scraper.octopus import Octopus
from octopus_scraper.scrapers.scraper import Content

logger = structlog.getLogger()


@pytest.mark.need_external_service
def test_octopus_initialization(octopus_config):
    octopus = Octopus(octopus_config)
    assert len(octopus._scrapers) == 1


def test_trigger_scraper(octopus_config, patch_scraper_scrap, patch_notion):
    octopus = Octopus(octopus_config)
    logger.error(octopus_config)
    octopus.trigger_scraper()
    assert isinstance(octopus._fetched_contents[0], Content)
    assert len(octopus._fetched_contents) == 1


def test_trigger_upload(octopus_config, patch_scraper_scrap, patch_notion):
    octopus = Octopus(octopus_config)
    octopus.trigger_scraper()
    assert len(octopus._fetched_contents) > 0
    octopus.trigger_upload()
    assert len(octopus._fetched_contents) == 0


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

    octopus.trigger_scraper()
    # 由于我们的mock返回1个content，3个scraper应该返回3个content
    assert len(octopus._fetched_contents) == 3
