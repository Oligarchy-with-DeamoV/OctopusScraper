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
    
    with patch('octopus_scraper.scrapers.utils.notion_api.NotionStorage.check_property_exist'):
        octopus = Octopus(config)
        assert octopus is not None


def test_load_trigger_upload():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    full_path = os.path.join(current_dir, "octopus_test_config.yml")
    config = load_yml_config(full_path)
    
    with patch('octopus_scraper.scrapers.utils.notion_api.NotionStorage.check_property_exist'), \
         patch('octopus_scraper.scrapers.utils.notion_api.NotionStorage.store_content') as mock_store:
        mock_store.return_value = True
        
        octopus = Octopus(config)
        octopus.trigger_scraper()
        assert len(octopus._fetched_contents) > 0
        logger.info("Success fetch contents.", contents=octopus._fetched_contents)
        octopus.trigger_upload()
        logger.info("Success uploads.", contents=octopus._fetched_contents)
