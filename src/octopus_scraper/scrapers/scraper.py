from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Text

import structlog
from dacite import from_dict

from octopus_scraper.scrapers.processors import AVALIABLE_PROCESSOR
from octopus_scraper.scrapers.scraper_protos import Content
from octopus_scraper.scrapers.utils.direct_rss import DirectRSS
from octopus_scraper.scrapers.utils.rsshub import RssHub
from octopus_scraper.scrapers.utils.content_deduplicator import (
    ContentDeduplicator,
)

AVALIABLE_FETCHERS = {"rsshub": RssHub, "direct_rss": DirectRSS}

logger = structlog.getLogger(__name__)


@dataclass
class BaseScraperConfig:
    fetcher_name: str
    fetcher_config: Any
    content_processor_configs: Dict[Text, Any]


class Scraper:
    def __init__(self, config: Dict):
        self.config = from_dict(BaseScraperConfig, config)
        self.storage = None  # 可选的存储器，用于去重
        try:
            self.activate_fetcher = AVALIABLE_FETCHERS[self.config.fetcher_name](
                self.config.fetcher_config
            )
        except Exception as e:
            logger.error(
                f"Activate_fetcher init failed with exception: {e}.",
                config=self.config,
                avaliable_fetcher_names=AVALIABLE_FETCHERS.keys(),
            )
        self.active_content_processor = {
            key: AVALIABLE_PROCESSOR[key](config)
            for key, config in self.config.content_processor_configs.items()
        }

    def _content_process(self, contents: List[Content]) -> List[Content]:
        for key, _processor in self.active_content_processor.items():
            logger.debug(f"Proccess content with proccessor: {key}")
            contents = _processor(contents)
        return contents

    def set_storage(self, storage):
        """设置存储器（用于去重）"""
        self.storage = storage

    def scrap_contents(self, params) -> List[Content]:
        """抓取配置的信息源中的信息，并进行去重
        return:
            contents: List[Content]
        """

        contents = self.activate_fetcher.fetch_contents(params)
        if self.storage:
            deduplicator = ContentDeduplicator(self.storage)
            new_contents = deduplicator.filter_new_contents(contents)

            # 存储新内容
            stored_count = 0
            for content in new_contents:
                stored_count += 1

            logger.info(
                f"Processed {len(contents)} contents, "
                f"stored {stored_count} new contents"
            )
            return self._content_process(new_contents)

        return self._content_process(contents)
