from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Text

import structlog
from dacite import from_dict

from octopus_scraper.processors import AVAILABLE_PROCESSOR
from octopus_scraper.protos import Content
from octopus_scraper.utils.direct_rss import DirectRSS
from octopus_scraper.utils.rsshub import RssHub

if TYPE_CHECKING:
    from octopus_scraper.storages.base_storage import BaseStorage

AVAILABLE_FETCHERS = {"rsshub": RssHub, "direct_rss": DirectRSS}

# Deprecated alias — will be removed in a future release
AVALIABLE_FETCHERS = AVAILABLE_FETCHERS

logger = structlog.getLogger(__name__)


@dataclass
class BaseScraperConfig:
    """Base configuration for a scraper instance."""

    fetcher_name: str
    fetcher_config: Any
    content_processor_configs: Dict[Text, Any]
    scraper_name: Optional[str] = None  # Human-readable name of the scraper source
    default_keywords: Optional[List[str]] = None  # Default keywords from config


class Scraper:
    def __init__(self, config: Dict):
        self.config = from_dict(BaseScraperConfig, config)
        self.storage = None  # 可选的存储器，用于去重
        try:
            self.activate_fetcher = AVAILABLE_FETCHERS[self.config.fetcher_name](
                self.config.fetcher_config
            )
        except Exception as e:
            logger.error(
                f"Activate_fetcher init failed with exception: {e}.",
                config=self.config,
                available_fetcher_names=AVAILABLE_FETCHERS.keys(),
            )
        self.active_content_processor = {}
        self.processor_priorities = {}

        for key, config in self.config.content_processor_configs.items():
            processor_instance = AVAILABLE_PROCESSOR[key](config)
            self.active_content_processor[key] = processor_instance

            # 从 processor 的配置中获取优先级
            if hasattr(processor_instance, "config") and hasattr(
                processor_instance.config, "priority"
            ):
                self.processor_priorities[key] = processor_instance.config.priority
            else:
                # 兼容旧的配置方式，如果processor没有priority配置，使用默认值
                self.processor_priorities[key] = 100

    def _content_process(self, contents: List[Content]) -> List[Content]:
        # 按照优先级排序处理器（优先级数值越小，优先级越高）
        sorted_processors = sorted(
            self.active_content_processor.items(),
            key=lambda x: self.processor_priorities.get(
                x[0], 100
            ),  # 使用get()避免KeyError
        )

        for key, _processor in sorted_processors:
            priority = self.processor_priorities.get(key, 100)
            logger.debug(
                f"Proccess content with proccessor: {key} (priority: {priority})"
            )
            contents = _processor(contents)
        return contents

    def set_storage(self, storage: "BaseStorage") -> None:
        """设置存储器"""
        self.storage = storage

    def scrap_contents(self, params: dict) -> List[Content]:
        """抓取配置的信息源中的信息，并进行去重
        return:
            contents: List[Content]
        """

        contents = self.activate_fetcher.fetch_contents(params)
        if self.storage:
            # 直接使用存储器的批量去重功能
            existing_content_ids = self.storage.get_all_content_ids()
            new_contents = [
                content
                for content in contents
                if content.content_id not in existing_content_ids
            ]

            logger.info(
                f"Processed {len(contents)} contents, "
                f"{len(new_contents)} are new, "
                f"{len(contents) - len(new_contents)} already exist"
            )
            return self._content_process(new_contents)

        return self._content_process(contents)
