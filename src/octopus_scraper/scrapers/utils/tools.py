import re
from typing import List

import structlog
from bs4 import BeautifulSoup
from feedparser.util import FeedParserDict
from html2markdown import convert

from octopus_scraper.scrapers.scraper_protos import Content

logger = structlog.getLogger(__name__)


def convert_contents_to_mk(contents: List) -> str:
    """Convert HTML content to clean Markdown format"""
    _parsed_content = ""
    for content in contents:
        html_content = content.get("value", "")

        # 先用convert统一转换
        markdown_content = convert(html_content)

        # 后处理：单独处理HTML格式的链接
        soup = BeautifulSoup(markdown_content, "html.parser")
        for a in soup.find_all("a"):
            if a.text.strip():
                href = a.get("href", "").strip()
                if href:
                    # 替换为Markdown格式链接
                    a.replace_with(f"[{a.text}]({href})")

        # 获取最终处理结果
        markdown_content = str(soup)

        # 修复其他格式
        markdown_content = re.sub(r"^\*\s+", "* ", markdown_content, flags=re.MULTILINE)
        markdown_content = re.sub(r"\n{3,}", "\n\n", markdown_content)

        _parsed_content += markdown_content + "\n\n"

    return _parsed_content.strip()


def build_contents(feed: FeedParserDict) -> List[Content]:
    contents: List[Content] = []
    for entry in feed.entries:
        logger.debug("Fetch raw entry content.", entry=entry)
        contents.append(
            Content(
                content_id=str(entry.get("id", entry.get("guid", entry.link))),
                title=str(entry.title),
                link=str(entry.link),
                summary=(
                    convert_contents_to_mk([{"value": entry.summary}])
                    if entry.summary
                    else ""
                ),
                content=convert_contents_to_mk(
                    entry.get("content", [])  # pyright: ignore
                ),
                published=str(entry.get("published", "")),
            )
        )
    return contents
