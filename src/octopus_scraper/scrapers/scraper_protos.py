from dataclasses import dataclass


@dataclass
class Content:
    content_id: str
    title: str
    link: str
    summary: str
    content: str
