import pytest

from octopus_scraper.octopus import Octopus


@pytest.mark.need_external_service
def test_octopus_initialization(octopus_config):
    octopus = Octopus(octopus_config)
    assert len(octopus._scrapers) == 4


@pytest.mark.integrate_test
def test_trigger_and_upload_scraper(octopus_config):
    octopus = Octopus(octopus_config)
    octopus.trigger_scraper()
    assert len(octopus._fetched_contents) > 0
    octopus.trigger_upload()
    assert len(octopus._fetched_contents) == 0
