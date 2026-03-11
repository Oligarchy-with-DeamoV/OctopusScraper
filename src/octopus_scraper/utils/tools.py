import hashlib
import os
import re
from typing import List
from urllib.parse import urlparse

import structlog
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

        # Use markdownify to convert HTML to Markdown
        markdown_content = markdownify(html_content)

        # Clean up formatting
        markdown_content = re.sub(r"^\*\s+", "* ", markdown_content, flags=re.MULTILINE)
        markdown_content = re.sub(r"\n{3,}", "\n\n", markdown_content)

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
    """Generate summary from entry, truncating if it exceeds max_length."""
    if not hasattr(entry, "summary") or not entry.get("summary"):
        return ""

    summary = convert_contents_to_mk([{"value": entry.summary}])
    # Remove extra whitespace
    summary = re.sub(r"\s+", " ", summary).strip()

    if len(summary) > max_length:
        logger.debug(
            f"Summary too long ({len(summary)} chars), truncating to {max_length}",
        )
        summary = summary[: max_length - 3] + "..."

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
