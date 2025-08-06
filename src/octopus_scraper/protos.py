from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Content:
    content_id: str
    title: str
    link: str
    summary: str
    content: str
    published: str
    author: Optional[str] = None
    keywords: Optional[List[str]] = None
    tags: Optional[List[str]] = None
