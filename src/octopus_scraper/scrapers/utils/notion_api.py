from dataclasses import dataclass
from typing import Dict, List, Optional

from dacite import Config, from_dict
import structlog
from tenacity import retry, stop_after_attempt, wait_fixed

from notion_client import Client
from octopus_scraper.scrapers.scraper_protos import Content


logger = structlog.getLogger(__name__)
MAX_NOTION_SUMMARY_LENGTH = 2000


@dataclass
class NotionAPIConfig:
    api_key: str
    database_id: str


class NotionStorage:
    """
    Store contents in Notion database

    Examples:
    >>> notion_storage = NotionStorage(config)
    >>> notion_storage.store_content(content)

    """

    def __init__(self, config: Dict):
        self.config = from_dict(
            data_class=NotionAPIConfig,
            data=config,
            config=Config(cast=[str], strict=True),
        )

        self.notion = Client(auth=self.config.api_key)

    def build_properties(self, content: Content) -> dict:
        """构建Notion属性结构"""
        if len(content.summary) > MAX_NOTION_SUMMARY_LENGTH:
            logger.warning(
                "Content summary return larger than {MAX_NOTION_SUMMARY_LENGTH}. Summary will bi cut off."
            )
        return {
            "Name": {"title": [{"text": {"content": content.title}}]},
            "Summary": {
                "rich_text": [
                    {"text": {"content": content.summary[:MAX_NOTION_SUMMARY_LENGTH]}}
                ]
            },
            "URL": {"url": content.link},
        }

    def _split_text_chunks(self, text: str, max_len: int) -> List[Dict]:
        """将长文本分割成符合Notion限制的块"""
        return [
            {"text": {"content": text[i : i + max_len]}}
            for i in range(0, len(text), max_len)
        ]

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def store_content(self, content: Content) -> bool:
        try:
            # 分割长文本，以符合 notion文本块最大长度限制
            content_chunks = self._split_text_chunks(
                content.summary, max_len=MAX_NOTION_SUMMARY_LENGTH
            )
            children = []
            for chunk in content_chunks:
                children.append(
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text": [chunk]},
                    }
                )
            self.notion.pages.create(
                parent={"database_id": self.config.database_id},
                properties=self.build_properties(content),
                children=children,
            )
            return True
        except Exception as e:
            logger.error(f"存储失败: {e}")
            return False
