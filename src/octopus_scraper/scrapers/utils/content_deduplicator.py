from typing import List, Protocol

import structlog

from octopus_scraper.scrapers.scraper_protos import Content

logger = structlog.getLogger(__name__)


class ContentExistenceChecker(Protocol):
    """检查内容是否存在的协议"""

    def has_content_id(self, content_id: str) -> bool:
        """检查指定的content_id是否已存在"""
        ...


class ContentDeduplicator:
    """内容去重器，依赖于存储层的存在性检查"""

    def __init__(self, existence_checker: ContentExistenceChecker):
        self.existence_checker = existence_checker

    def filter_new_contents(self, contents: List[Content]) -> List[Content]:
        """过滤出新的内容（未在存储中存在的）"""
        new_contents = []
        for content in contents:
            if not self.existence_checker.has_content_id(content.content_id):
                new_contents.append(content)
            else:
                logger.debug(
                    "Content already exists in storage, skipping",
                    content_id=content.content_id,
                )

        logger.info(f"Filtered {len(contents)} contents, {len(new_contents)} are new")
        return new_contents
