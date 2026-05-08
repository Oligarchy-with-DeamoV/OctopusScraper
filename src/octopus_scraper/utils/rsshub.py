from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union
from urllib.parse import urljoin

import feedparser
import requests
import structlog
from dacite import from_dict
from feedparser.util import FeedParserDict

from octopus_scraper.protos import Content
from octopus_scraper.utils.tools import build_contents

logger = structlog.getLogger(__name__)


@dataclass
class RssHubConifg:
    hub_root: str
    route: str
    fetch_params: Optional[Dict]
    request_timeout: Union[float, Tuple[float, float]] = field(default=(10, 300))


class RssHub:
    """
    RssHub integration with python

    Examples:
    >>> config = RssHubConfig(hub_root: "root", route: "/api", fetch_params={})
    >>> rsshub = RssHub(asdict(config))
    >>> contents = rsshub.fetch_contents({"filter_title": "打造"})
    """

    def __init__(self, config: Dict):
        self.config = from_dict(RssHubConifg, config)

    def fetch_contents(self, params: Optional[dict] = None) -> List[Content]:
        """获取 contents
        https://docs.rsshub.app/guide/parameters

        Args：
            - route (str): RssHub 中的 route
            - params (dict): 字典格式的参数，支持以下字段：
                - filter (str): 用于过滤内容，支持通过标题、描述、作者、分类、发布日期等进行过滤。多个关键字之间使用 | 分隔。示例：filter="Blue|Yellow|Black"
                - filter_title (str): 仅按标题过滤。 示例：filter_title="Design"
                - filter_description (str): 仅按描述过滤。 示例：filter_description="logo"
                - filter_author (str): 仅按作者过滤。 示例：filter_author="John Doe"
                - filter_category (str): 仅按分类过滤。 示例：filter_category="Art"
                - filter_time (int): 根据发布日期（pubDate）过滤，单位为秒，返回指定时间范围内的内容。没有 pubDate 的项目将不会被过滤。 示例：filter_time=86400（过去一天内发布的内容）
                - filterout (str): 用于排除指定的内容，类似 filter，但该过滤器会排除匹配的项目。 示例：filterout="Blue|Yellow|Black"
                - filterout_title (str): 仅按标题排除内容。 示例：filterout_title="Design"
                - filterout_description (str): 仅按描述排除内容。 示例：filterout_description="logo"
                - filterout_author (str): 仅按作者排除内容。 示例：filterout_author="John Doe"
                - filterout_category (str): 仅按分类排除内容。 示例：filterout_category="Art"
                - filter_case_sensitive (bool, 默认 True): 设置是否区分大小写，适用于所有过滤和排除选项。 示例：filter_case_sensitive=False
                - limit (int): 限制返回的文章数量。 示例：limit=10（返回前 10 条内容）
                - sorted (bool, 默认 True): 控制是否按发布时间 (pubDate) 对结果进行排序。如果为 false，则不排序。 示例：sorted=False
                - mode (str): 开启全文模式，返回完整内容而不仅是简要。 示例：mode="fulltext"
        Returns:
            - return: List[Content]
        """
        params = params or {}
        base_params = self.config.fetch_params or {}
        request_params = {**base_params, **params}

        # Build URL without making an HTTP request
        rss_url = (
            requests.Request(
                "GET",
                urljoin(self.config.hub_root, self.config.route),
                params=request_params,
            )
            .prepare()
            .url
        )

        logger.debug("Fetching rss_url.", rss_url=rss_url)

        # Fetch content with configurable timeout, then parse locally
        response = requests.get(rss_url, timeout=self.config.request_timeout)
        response.raise_for_status()

        feed: FeedParserDict = feedparser.parse(response.content)
        if not feed.bozo or feed.entries:
            return build_contents(feed)

        bozo_exception = getattr(feed, "bozo_exception", None)
        raise RuntimeError(f"Failed to parse RSS feed from {rss_url}: {bozo_exception}")
