from typing import List

from feedparser.util import FeedParserDict
from html2markdown import convert
import structlog

from octopus_scraper.scrapers.scraper_protos import Content

logger = structlog.getLogger(__name__)


def convert_contents_to_mk(contents: List) -> str:
    """https://feedparser.readthedocs.io/en/latest/common-atom-elements.html"""
    _parsed_content = ""
    for content in contents:
        _parsed_content = _parsed_content + convert(content.get("value")) + "\n"
    return _parsed_content


def build_contents(feed: FeedParserDict) -> List[Content]:
    contents: List[Content] = []
    for entry in feed.entries:
        logger.debug("Fetch raw entry content.", entry=entry)
        contents.append(
            Content(
                content_id=str(entry.get("id", entry.get("guid", entry.link))),
                title=str(entry.title),
                link=str(entry.link),
                summary=convert(entry.summary) if entry.summary else "",
                content=convert_contents_to_mk(
                    entry.get("content", [])  # pyright: ignore
                ),
                published=str(entry.get("published", "")),
            )
        )
    return contents
