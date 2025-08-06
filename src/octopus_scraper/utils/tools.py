import hashlib
import os
import re
from typing import List
from urllib.parse import urlparse

import structlog
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from feedparser.util import FeedParserDict
from markdownify import markdownify

from octopus_scraper.protos import Content

# Load environment variables
load_dotenv()

logger = structlog.getLogger(__name__)

# Configuration constants
DEFAULT_SUMMARY_MAX_LENGTH = int(os.getenv("OCTOPUS_SUMMARY_MAX_LENGTH", "500"))


def convert_contents_to_mk(contents: List) -> str:
    """Convert HTML content to clean Markdown format"""
    content_pieces = []
    for content in contents:
        html_content = content.get("value", "")

        # 先用markdownify统一转换
        markdown_content = markdownify(html_content)

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
        # 清理链接前后的多余换行
        markdown_content = re.sub(r"\n+\[", "[", markdown_content)

        content_pieces.append(markdown_content.strip())

    # Join with double newlines and apply final cleanup
    result = "\n\n".join(content_pieces)
    return result


def build_contents(feed: FeedParserDict) -> List[Content]:
    contents: List[Content] = []
    for entry in feed.entries:
        logger.debug("Fetch raw entry content.", entry=entry)
        contents.append(
            Content(
                content_id=generate_stable_content_id(entry),
                title=str(entry.title),
                link=str(entry.link),
                summary=generate_summary_from_entry(entry),
                content=generate_content_with_fallback(entry),
                published=str(entry.get("published", "")),
            )
        )
    return contents


def generate_stable_content_id(entry) -> str:
    """生成稳定的content_id"""

    # 使用 URL + 发布时间的哈希
    url = str(entry.link)
    published = str(entry.get("published", ""))

    # 规范化URL（移除查询参数中的临时参数）
    parsed_url = urlparse(url)
    clean_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"

    # 生成哈希ID
    content_for_hash = f"{clean_url}|{published}"
    hash_id = hashlib.md5(content_for_hash.encode()).hexdigest()[:16]

    logger.debug(
        "Generated hash-based content_id", url=url, published=published, hash_id=hash_id
    )

    return hash_id


def generate_summary_from_entry(
    entry, max_length: int = DEFAULT_SUMMARY_MAX_LENGTH
) -> str:
    """根据长度限制生成summary，超过限制则返回空字符串"""
    if not hasattr(entry, "summary") or not entry.get("summary"):
        return ""

    summary = convert_contents_to_mk([{"value": entry.summary}])
    # 移除多余的换行和空格
    summary = re.sub(r"\s+", " ", summary).strip()

    if len(summary) > max_length:
        logger.debug(
            f"Summary too long ({len(summary)} chars), setting to empty for processor to handle"
        )
        return ""

    return summary


def generate_content_with_fallback(entry) -> str:
    """内容回退策略：content -> summary -> description"""
    # 优先使用 content
    content = convert_contents_to_mk(entry.get("content", []))
    if content.strip():
        return content

    # 回退到 summary
    if entry.get("summary"):
        summary_content = convert_contents_to_mk([{"value": entry.summary}])
        if summary_content.strip():
            logger.debug("Using summary as content (content was empty)")
            return summary_content

    # 回退到 description
    if entry.get("description"):
        description_content = convert_contents_to_mk([{"value": entry.description}])
        if description_content.strip():
            logger.debug(
                "Using description as content (content and summary were empty)"
            )
            return description_content

    logger.warning(
        "No meaningful content found in entry", entry_id=entry.get("id", "unknown")
    )
    return ""
