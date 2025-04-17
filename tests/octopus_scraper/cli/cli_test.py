import os

import pytest
import structlog

from octopus_scraper.cli import Octopus, load_yml_config

logger = structlog.getLogger()


@pytest.mark.need_external_service
def test_load_yml_config():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    full_path = os.path.join(current_dir, "octopus_test_config.yml")
    config = load_yml_config(full_path)
    octopus = Octopus(config)


@pytest.mark.need_external_service
def test_load_trigger_upload():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    full_path = os.path.join(current_dir, "octopus_test_config.yml")
    config = load_yml_config(full_path)
    octopus = Octopus(config)
    octopus.trigger_scraper()
    assert len(octopus._fetched_contents) > 0
    logger.info("Success fetch contents.", contents=octopus._fetched_contents)
    octopus.trigger_upload()
    logger.info("Success uploads.", contents=octopus._fetched_contents)
