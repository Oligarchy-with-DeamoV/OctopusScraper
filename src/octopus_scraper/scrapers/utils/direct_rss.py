from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List
from urllib.parse import urljoin

from dacite import from_dict
from dateutil import parser
import feedparser
from feedparser.util import FeedParserDict
import requests
import structlog
from tenacity import retry, stop_after_attempt, wait_fixed

from octopus_scraper.scrapers.scraper_protos import Content
from octopus_scraper.scrapers.utils.tools import build_contents

logger = structlog.getLogger(__name__)


@dataclass
class DirectRSSConfig:
    hub_root: str
    route: str


class DirectRSS:
    """
    Direct 订阅 rss url

    Examples:
    >>> config = DirectRSSConfig(hub_root: "www.github.com", route: "/api")
    >>> rsshub = DirectRSS(asdict(config))
    >>> contents = rsshub.fetch_contents({"filter_time": 60})
    """

    def __init__(self, config: Dict):
        self.config = from_dict(DirectRSSConfig, config)

    @staticmethod
    def filter_by_timerange(contents: List[Content], filter_time: int) -> List[Content]:
        now = datetime.now(timezone.utc)
        filtered_contents = []
        for content in contents:
            try:
                # pub_date example: 2025-04-06T13:50:59+08:00
                if (
                    content.pub_date is not None
                    and (
                        now - parser.isoparse(content.pub_date).astimezone(timezone.utc)
                    ).total_seconds()
                    <= filter_time
                ):
                    filtered_contents.append(content)
            except Exception as e:
                logger.error(
                    "Filter content failed. Bypass content.",
                    content=content,
                    filter_time=filter_time,
                    error=e,
                )
                continue
        return contents

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def fetch_contents(self, params: dict = {}) -> List[Content]:
        """获取 contents

        Args：
            - params (dict): 字典格式的参数，支持以下字段：
                - filter_time (int): 根据发布日期（pubDate）过滤，单位为秒，返回指定时间范围内的内容。没有 pubDate 的项目将不会被过滤。 示例：filter_time=86400（过去一天内发布的内容）
        Returns:
            - return: List[Content]
        """
        rss_url = requests.get(urljoin(self.config.hub_root, self.config.route)).url
        logger.debug("Fetching rss_url.", rss_url=rss_url)
        feed: FeedParserDict = feedparser.parse(rss_url)
        if feed.status == 200:
            contents = build_contents(feed)
            if params.get("filter_time"):
                contents = self.filter_by_timerange(contents, params["filter_tiem"])
            return contents
        raise RuntimeError(f"Failed to get RSS feed. Status code: {feed.status}.")
