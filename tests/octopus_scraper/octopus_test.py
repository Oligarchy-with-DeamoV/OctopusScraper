from octopus_scraper.octopus import Octopus
from octopus_scraper.scrapers.scraper import Content


def test_octopus_initialization(dummy_octopus_config):
    octopus = Octopus(dummy_octopus_config)
    assert len(octopus._scrapers) == 1


def test_trigger_scraper(dummy_octopus_config, patch_scraper_scrap, patch_notion):
    octopus = Octopus(dummy_octopus_config)
    octopus.trigger_scraper()
    assert isinstance(octopus._fetched_contents[0], Content)
    assert len(octopus._fetched_contents) == 1


def test_trigger_upload(dummy_octopus_config, patch_scraper_scrap, patch_notion):
    octopus = Octopus(dummy_octopus_config)
    octopus.trigger_scraper()
    assert len(octopus._fetched_contents) > 0
    octopus.trigger_upload()
    assert len(octopus._fetched_contents) == 0
