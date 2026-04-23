from abc import ABCMeta
from typing import List

import structlog

from octopus_scraper.protos import Content

logger = structlog.getLogger(__name__)


class BaseStorage(metaclass=ABCMeta):

    def _store_content(self, content: Content) -> bool:
        """存储单个内容到存储系统"""
        raise NotImplementedError("Subclasses should implement this method.")

    def get_all_content_ids(self) -> set:
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

        # Batch-internal dedup: keep first occurrence of each content_id
        if deduplicate:
            seen_ids: set = set()
            unique_contents: List[Content] = []
            batch_dup_count = 0
            for content in contents:
                if content.content_id not in seen_ids:
                    seen_ids.add(content.content_id)
                    unique_contents.append(content)
                else:
                    batch_dup_count += 1
            if batch_dup_count > 0:
                logger.warning(
                    "Removed batch-internal duplicates",
                    original_count=len(contents),
                    unique_count=len(unique_contents),
                    duplicates_removed=batch_dup_count,
                )
            contents_to_process = unique_contents
        else:
            contents_to_process = contents

        existing_content_ids = self.get_all_content_ids()
        store_contents_list = []
        if deduplicate:
            logger.info("Deduplication enabled, checking existing content IDs...")
            for content in contents_to_process:
                if content.content_id not in existing_content_ids:
                    store_contents_list.append(content)
                else:
                    logger.debug(
                        "Content already exists in storage, skipping",
                        content_id=content.content_id,
                    )
        else:
            store_contents_list = contents_to_process

        # Upload Contents
        results = []
        for content in store_contents_list:
            try:
                results.append(self._store_content(content))
            except Exception as e:
                logger.error(
                    "Failed to store content after retries",
                    content_id=content.content_id,
                    error=str(e),
                )
                results.append(False)

        # Count skipped (both batch-internal dups and storage-existing)
        skipped_count = len(contents) - len(store_contents_list)
        results.extend([True] * skipped_count)

        success_count = sum(1 for r in results if r)
        failure_count = sum(1 for r in results if not r)
        logger.info(
            f"Batch storage completed: {success_count} stored, "
            f"{failure_count} failed, {skipped_count} skipped "
            f"(1 API call for deduplicate check)"
        )
        return results
