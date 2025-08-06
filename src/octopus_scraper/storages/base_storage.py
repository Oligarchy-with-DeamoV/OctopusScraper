from abc import ABCMeta
from typing import List

import structlog

from octopus_scraper.scrapers.scraper_protos import Content

logger = structlog.getLogger(__name__)


class BaseStorage(metaclass=ABCMeta):

    def _store_content(self, content: Content) -> bool:
        """存储单个内容到存储系统"""
        raise NotImplementedError("Subclasses should implement this method.")

    def _get_all_content_ids(self) -> set:
        """获取存储系统中所有已存在的内容ID"""
        raise NotImplementedError("Subclasses should implement this method.")

    def store_contents(self, contents: List[Content], deduplicate=True) -> List[bool]:
        """批量存储内容到 Notion 数据库
        Args:
            contents (List[Content]): 要存储的内容列表
            deduplicate (bool): 是否启用去重功能，默认为 True
        Returns:
            List[bool]: 每个内容存储结果的列表，True 表示存储成功，False 表示有重复内容未上传
        """
        if not contents:
            return []

        existing_content_ids = self._get_all_content_ids()
        store_contents = []
        if deduplicate:
            logger.info("Deduplication enabled, checking existing content IDs...")
            for content in contents:
                if content.content_id not in existing_content_ids:
                    store_contents.append(content)
                else:
                    logger.debug(
                        "Content already exists in storage, skipping",
                        content_id=content.content_id,
                    )
        else:
            store_contents = contents

        # Upload Contents
        results = []
        for content in store_contents:
            results.append(self._store_content(content))

        # 为已存在的内容返回 True（表示"处理成功"）
        skipped_count = len(contents) - len(store_contents)
        results.extend([True] * skipped_count)

        logger.info(
            f"Batch storage completed: {len(store_contents)} stored, {skipped_count} skipped (1 API call for deduplicate check)"
        )
        return results
