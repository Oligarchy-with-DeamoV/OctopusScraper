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
