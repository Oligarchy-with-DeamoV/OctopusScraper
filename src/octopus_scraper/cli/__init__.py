import argparse

from doraemon.logger.slogger import configure_structlog
import structlog
import yaml

from octopus_scraper.octopus import Octopus

configure_structlog()
logger = structlog.getLogger(__name__)


def create_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=str, required=True, help="Path to YAML config file"
    )
    parser.add_argument(
        "--notion_upload",
        action="store_true",
        help="Trigger Notion upload after scraping",
    )
    return parser.parse_args()


def load_yml_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_octopus_go():
    args = create_args()
    config: dict = load_yml_config(args.config)
    octopus_instance = Octopus(config)
    octopus_instance.trigger_scraper()

    if args.notion_upload:
        octopus_instance.trigger_upload()
