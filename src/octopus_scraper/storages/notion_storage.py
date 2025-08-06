import re
from dataclasses import dataclass
from typing import Dict, List

import structlog
from dacite import Config, from_dict
from notion_client import Client
from tenacity import retry, stop_after_attempt, wait_fixed

from octopus_scraper.scrapers.scraper_protos import Content
from octopus_scraper.storages.base_storage import BaseStorage

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


class NotionStorage(BaseStorage):
    """
    Store contents in Notion database

    Examples:
    >>> notion_storage = NotionStorage(config)
    >>> notion_storage.store_content(contents)

    """

    def __init__(self, config: Dict):
        self.config = from_dict(
            data_class=NotionAPIConfig,
            data=config,
            config=Config(cast=[str], strict=True),
        )

        self.notion = Client(auth=self.config.api_key)
        self._check_property_exist()

    @retry(stop=stop_after_attempt(2), wait=wait_fixed(1))
    def _get_all_content_ids(self) -> set:
        """批量获取数据库中所有已存在的 content_id"""
        all_content_ids = set()
        has_more = True
        next_cursor = None

        while has_more:
            query_params = {
                "database_id": self.config.database_id,
                "page_size": 100,  # Notion API 最大支持 100
            }

            if next_cursor:
                query_params["start_cursor"] = next_cursor

            response = self.notion.databases.query(**query_params)

            if isinstance(response, dict):
                results = response.get("results", [])
                for page in results:
                    properties = page.get("properties", {})
                    content_id_prop = properties.get(NOTION_PROPERTIY_CONTENT_ID, {})
                    rich_text = content_id_prop.get("rich_text", [])
                    if rich_text and len(rich_text) > 0:
                        content_id = rich_text[0].get("text", {}).get("content", "")
                        if content_id:
                            all_content_ids.add(content_id)

                has_more = response.get("has_more", False)
                next_cursor = response.get("next_cursor")
            else:
                logger.error("Notion databases query response is not a dict.")
                break

        logger.info(
            f"Retrieved {len(all_content_ids)} existing content IDs from Notion"
        )
        return all_content_ids

    @retry(stop=stop_after_attempt(2), wait=wait_fixed(1))
    def _check_property_exist(self):
        self.notion.databases.update(
            database_id=self.config.database_id,
            properties={
                NOTION_PROPERTIY_TITLE_NAME: {"title": {}},
                NOTION_PROPERTIY_SUMMARY_NAME: {"rich_text": {}},
                NOTION_PROPERTIY_URL: {"url": {}},
                NOTION_PROPERTIY_CONTENT_ID: {"rich_text": {}},
            },
        )

    def _build_properties(self, content: Content) -> dict:
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
            NOTION_PROPERTIY_CONTENT_ID: {
                "rich_text": [{"text": {"content": content.content_id}}]
            },
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
    def _store_content(self, content: Content) -> bool:
        """存储单个内容，不做重复性检查"""
        try:
            content_chunks = self._split_text_chunks(
                content.content, max_len=MAX_NOTION_SUMMARY_LENGTH
            )
            children = []
            for chunk in content_chunks:
                children.extend(self._parse_markdown_to_notion_blocks(chunk))

            # 直接存储，不检查是否存在
            self.notion.pages.create(
                parent={"database_id": self.config.database_id},
                properties=self._build_properties(content),
                children=children,
            )
            logger.info("Content stored successfully", content_id=content.content_id)
            return True
        except Exception as e:
            logger.error(f"存储失败: {e}", content_id=content.content_id)
            return False
