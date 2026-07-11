from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Union
from urllib.parse import urljoin

import feedparser
import requests
import structlog
import time
from dacite import from_dict
from dateutil import parser
from feedparser.util import FeedParserDict

from octopus_scraper.protos import Content
from octopus_scraper.metrics import metrics
from octopus_scraper.utils.tools import build_contents

logger = structlog.getLogger(__name__)


@dataclass
class DirectRSSConfig:
    hub_root: str
    route: str
    request_timeout: Union[float, Tuple[float, float]] = field(default=(10, 60))


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
                # published example: 2025-04-06T13:50:59+08:00
                if (
                    content.published is not None
                    and (
                        now
                        - parser.isoparse(content.published).astimezone(timezone.utc)
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
        return filtered_contents

    def fetch_contents(self, params: Optional[dict] = None) -> List[Content]:
        """获取 contents

        Args：
            - params (dict): 字典格式的参数，支持以下字段：
                - filter_time (int): 根据发布日期（pubDate）过滤，单位为秒，返回指定时间范围内的内容。没有 pubDate 的项目将不会被过滤。 示例：filter_time=86400（过去一天内发布的内容）
        Returns:
            - return: List[Content]
        """
        params = params or {}

        # Build URL without making an HTTP request
        rss_url = urljoin(self.config.hub_root, self.config.route)
        logger.debug("Fetching rss_url.", rss_url=rss_url)

        # Fetch content with configurable timeout, then parse locally
        request_start = time.monotonic()
        try:
            response = requests.get(rss_url, timeout=self.config.request_timeout)
            response.raise_for_status()

            feed: FeedParserDict = feedparser.parse(response.content)
            if not feed.bozo or feed.entries:
                contents = build_contents(feed)
                if params.get("filter_time"):
                    contents = self.filter_by_timerange(contents, params["filter_time"])
                metrics.record_external_request(
                    "rss", time.monotonic() - request_start, success=True
                )
                return contents

            bozo_exception = getattr(feed, "bozo_exception", None)
            raise RuntimeError(
                f"Failed to parse RSS feed from {rss_url}: {bozo_exception}"
            )
        except Exception:
            metrics.record_external_request(
                "rss", time.monotonic() - request_start, success=False
            )
            raise
