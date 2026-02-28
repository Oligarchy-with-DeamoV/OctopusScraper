from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Content:
    """Represents a single piece of scraped content."""

    content_id: str
    title: str
    link: str
    summary: str
    content: str
    published: str
    author: Optional[str] = None
    keywords: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    scraper_name: Optional[str] = None  # Source scraper that produced this content
