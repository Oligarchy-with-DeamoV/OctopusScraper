from dataclasses import dataclass
from typing import Dict, List

from dacite import Config, from_dict
import structlog
from tenacity import retry, stop_after_attempt, wait_fixed

from notion_client import Client
from octopus_scraper.scrapers.scraper_protos import Content


logger = structlog.getLogger(__name__)
MAX_NOTION_SUMMARY_LENGTH = 2000
NOTION_PROPERTIY_TITLE_NAME = "Name"
NOTION_PROPERTIY_SUMMARY_NAME = "Summary"
NOTION_PROPERTIY_CONTENT_ID = "ContentId"
NOTION_PROPERTIY_URL = "URL"


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
        self.check_property_exist()

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def has_content_id(self, content_id: str) -> bool:
        query_filter = {
            "property": NOTION_PROPERTIY_CONTENT_ID,
            "url": {"equals": content_id},
        }

        response = self.notion.databases.query(
            database_id=self.config.database_id, filter=query_filter, page_size=1
        )
        return len(response.get("results", [])) > 0

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def check_property_exist(self):
        self.notion.databases.update(
            database_id=self.config.database_id,
            properties={
                NOTION_PROPERTIY_TITLE_NAME: {"title": {}},
                NOTION_PROPERTIY_SUMMARY_NAME: {"rich_text": {}},
                NOTION_PROPERTIY_URL: {"url": {}},
                NOTION_PROPERTIY_CONTENT_ID: {"url": {}},
            },
        )

    def build_properties(self, content: Content) -> dict:
        """构建Notion属性结构"""
        if len(content.summary) > MAX_NOTION_SUMMARY_LENGTH:
            logger.warning(
                f"Content summary return larger than {MAX_NOTION_SUMMARY_LENGTH}. Summary will be cut off."
            )
        return {
            NOTION_PROPERTIY_TITLE_NAME: {
                "title": [{"text": {"content": content.title}}]
            },
            NOTION_PROPERTIY_SUMMARY_NAME: {
                "rich_text": [
                    {"text": {"content": content.summary[:MAX_NOTION_SUMMARY_LENGTH]}}
                ]
            },
            NOTION_PROPERTIY_URL: {"url": content.link},
            NOTION_PROPERTIY_CONTENT_ID: {"url": content.link},
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
                content.content, max_len=MAX_NOTION_SUMMARY_LENGTH
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
            if not self.has_content_id(content.content_id):
                self.notion.pages.create(
                    parent={"database_id": self.config.database_id},
                    properties=self.build_properties(content),
                    children=children,
                )
            else:
                logger.warning(
                    "Found existed content with content id.",
                    content_id=content.content_id,
                )
            return True
        except Exception as e:
            logger.error(f"存储失败: {e}")
            return False
