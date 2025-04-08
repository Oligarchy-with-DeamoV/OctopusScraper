from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import urljoin

from dacite import from_dict
import feedparser
from feedparser.util import FeedParserDict
import requests
import structlog
from tenacity import retry, stop_after_attempt, wait_fixed

from octopus_scraper.scrapers.scraper_protos import Content

logger = structlog.getLogger(__name__)


@dataclass
class RssHubConifg:
    hub_root: str
    route: str
    fetch_params: Optional[Dict]


class RssHub:
    """
    RssHub integration with python

    Examples:
    >>> rsshub = RssHub(service_instance_url="https://rsshub.thzu.xyz")
    >>> contents = rsshub.fetch_contents("/sspai/matrix", {"filter_title": "打造"})
    """

    def __init__(self, config: Dict):
        self.config = from_dict(RssHubConifg, config)

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def fetch_contents(self, params: dict = {}) -> List[Content]:
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
        if self.config.fetch_params:
            self.config.fetch_params.update(params)
        _params = self.config.fetch_params
        rss_url = requests.get(
            urljoin(self.config.hub_root, self.config.route), params=_params
        ).url
        logger.debug("Fetching rss_url.", rss_url=rss_url)
        feed: FeedParserDict = feedparser.parse(rss_url)
        contents = []
        if feed.status == 200:
            for entry in feed.entries:
                contents.append(
                    Content(
                        title=str(entry.title),
                        summary=str(entry.summary),
                        link=str(entry.link),
                    )
                )
            return contents
        raise RuntimeError(f"Failed to get RSS feed. Status code: {feed.status}.")
