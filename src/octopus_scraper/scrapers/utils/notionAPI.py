"""
This is a sample code to parse RSS feed and extract article links.
"""

import feedparser
import requests
import feedparser
import requests
from dacite import from_dict, Config
from requests import Response
from tenacity import retry, stop_after_attempt, wait_fixed
from notion_client import Client
from typing import List, Optional, Dict
import json
from dataclasses import dataclass

@dataclass
class Content:
    title: str
    url: str
    content: str
    fetch_params: Optional[Dict] = None

@dataclass
class NotionAPIConfig:
    api_key: str
    database_id: str
    fetch_params: Optional[Dict] = None


class NotionStorage:
    """
    Store contents in Notion database

    Examples:

    """

    def __init__(self, config: Dict):
        self.config = from_dict(
            data_class=NotionAPIConfig,
            data=config,
            config=Config(cast=[str], strict=True)
        )

        self.notion = Client(auth=self.config.api_key)

    # 新增 RSS 解析方法
    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def parse_rss_feed(self, rss_url: str, max_entries: int = 10) -> List[str]:
        """解析 RSS 订阅源并获取文章链接"""
        feed = feedparser.parse(rss_url)
        return [entry.link for entry in feed.entries[:max_entries]]

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def _parse_custom_content(self, input_str: str) -> dict:
        """解析包含标题、URL和Markdown内容的字符串"""
        result = {"title": "", "url": "", "content": ""}
        lines = input_str.split('\n')

        current_section = None
        for line in lines:
            line = line.strip()
            if line.startswith("Title: "):
                result["title"] = line.replace("Title: ", "", 1).strip()
            elif line.startswith("URL Source: "):
                result["url"] = line.replace("URL Source: ", "", 1).strip()
            elif line.startswith("Markdown Content:"):
                current_section = "content"
            elif current_section == "content":
                result["content"] += line + "\n"

        # 清理多余空行
        result["content"] = result["content"].strip()
        return result

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def parse_article_content(self, article_url: str) -> Response:
        """使用 Jina Reader 解析文章内容"""
        jina_url = f"https://r.jina.ai/{article_url}"
        response = requests.get(jina_url)
        content = from_dict(
            data_class=Content,
            data=self._parse_custom_content(response.text)
        )
        return content

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def build_properties(self, content: Content) -> dict:
        """构建Notion属性结构"""
        return {
            "Title": {"title": [{"text": {"content": content.title}}]},
            # "Summary": {"rich_text": [{"text": {"content": content.summary[:2000]}}]},  # 限制摘要长度
            "URL": {"url": content.url}
        }

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def _split_text_chunks(self, text: str, max_len: int = 2000) -> List[Dict]:
        """将长文本分割成符合Notion限制的块"""
        return [{"text": {"content": text[i:i + max_len]}} for i in range(0, len(text), max_len)]

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def store_content(self, content: Content) -> bool:
        try:
            #分割长文本，notion文本块最大长度为2000
            content_chunks = self._split_text_chunks(content.content, max_len=500)
            children = []
            for chunk in content_chunks:
                children.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [chunk]
                    }
                })
            self.notion.pages.create(
                parent={"database_id": self.config.database_id},
                properties=self.build_properties(content),
                children=children
            )
            return True
        except Exception as e:
            print(f"存储失败: {e}")
            return False