import re
from dataclasses import dataclass
from typing import Dict, List

import structlog
from dacite import Config, from_dict
from notion_client import Client
from tenacity import retry, stop_after_attempt, wait_fixed

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
        if isinstance(response, dict):
            return len(response.get("results", [])) > 0
        else:
            logger.error("Notion databases fetch content id response is not a dict.")
            return False

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
        """将长文本按自然段落分割成符合Notion限制的块"""
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

        chunks = []
        current_chunk = ""

        for para in paragraphs:
            if len(para) + 1 <= max_len:
                current_chunk = f"{para}\n"
                chunks.append({"type": "text", "text": {"content": current_chunk}})
            else:
                for i in range(0, len(para), max_len):
                    chunks.append(
                        {"type": "text", "text": {"content": para[i : i + max_len]}}
                    )

        return chunks

    def _parse_markdown_to_notion_blocks(self, chunk: Dict) -> List[Dict]:
        """将Markdown块转换为Notion块"""
        content = chunk["text"]["content"]

        if match := re.search(r"\[([^\]]+)\]\(([^)]+)\)", content):
            return [
                {
                    "object": "block",
                    "type": "bookmark",
                    "bookmark": {
                        "url": match.group(2).strip(),
                        "caption": [
                            {
                                "type": "text",
                                "text": {"content": match.group(1).strip()},
                            }
                        ],
                    },
                }
            ]

        handlers = {
            "#": lambda c: {
                "object": "block",
                "type": f"heading_{c.count('#', 0, 6)}",
                f"heading_{c.count('#', 0, 6)}": {
                    "rich_text": [{"text": {"content": c.lstrip("#").strip()}}]
                },
            },
            "-": lambda c: {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"text": {"content": c[2:].strip()}}]
                },
            },
            "*": lambda c: {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"text": {"content": c[2:].strip()}}]
                },
            },
            "`": lambda c: {
                "object": "block",
                "type": "code",
                "code": {"rich_text": [{"text": {"content": c.strip("`").strip()}}]},
            },
        }

        for prefix, handler in handlers.items():
            if content.startswith(prefix):
                return [handler(content)]

        return [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [chunk]},
            }
        ]

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def store_content(self, content: Content) -> bool:
        try:
            content_chunks = self._split_text_chunks(
                content.content, max_len=MAX_NOTION_SUMMARY_LENGTH
            )
            children = []
            for chunk in content_chunks:
                children.extend(self._parse_markdown_to_notion_blocks(chunk))

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
