from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Tuple

import structlog
from dacite import from_dict

from octopus_scraper.scrapers.scraper import BaseScraperConfig, Content, Scraper
from octopus_scraper.scrapers.utils.notion_api import NotionAPIConfig, NotionStorage

logger = structlog.getLogger(__name__)


@dataclass
class ScraperRuntimeConfig:
    scraper_config: BaseScraperConfig
    fetch_params: dict


@dataclass
class OctopusConfig:
    scrapers_config_with_fetch_params: List[ScraperRuntimeConfig]
    notion_api_config: NotionAPIConfig


class Octopus:
    def __init__(self, config: Dict):
        self._config = from_dict(OctopusConfig, config)
        self._scrapers: List[Tuple[Scraper, Dict]] = []
        self._fetched_contents: List[Content] = []
        self._notion_api: NotionStorage = NotionStorage(
            asdict(self._config.notion_api_config)
        )

        try:
            self._setup()
        except Exception as e:
            logger.error(
                f"Activate scrapers init failed with exception: {e}.",
                config=self._config,
            )
            raise RuntimeError(f"Activate scrapers init failed with exception: {e}.")
        self._health_check()

    def _setup(self):
        for scraper_runtime_config in self._config.scrapers_config_with_fetch_params:
            self._setup_single_scrapper(
                scraper_runtime_config.scraper_config,
                scraper_runtime_config.fetch_params,
            )

    def _setup_single_scrapper(self, config: Any, fetch_params: Dict):
        """初始化 scraper，同时设置对应的 fetch_params"""
        self._scrapers.append((Scraper(asdict(config)), fetch_params))

    def _health_check(self):
        """针对设置的 Scraper 和 NotionAPI 进行健康检查"""
        pass

    def trigger_scraper(self):
        """触发一次 Scraper"""
        for _s, _p in self._scrapers:
            self._fetched_contents.extend(_s.scrap_contents(_p))

    def trigger_upload(self):
        """将获取的 Content 批量上传"""
        while self._fetched_contents:
            self._notion_api.store_content(self._fetched_contents.pop())
