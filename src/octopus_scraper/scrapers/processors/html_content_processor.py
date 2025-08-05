from copy import deepcopy
from dataclasses import dataclass, field
from typing import Dict, List

import requests
import structlog
from dacite import from_dict
from tenacity import retry, stop_after_attempt, wait_fixed

try:
    from readability import Document

    READABILITY_AVAILABLE = True
except ImportError:
    READABILITY_AVAILABLE = False

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

from octopus_scraper.scrapers.processors.protos import ProcessorConfig
from octopus_scraper.scrapers.scraper_protos import Content
from octopus_scraper.scrapers.utils.tools import convert_contents_to_mk

logger = structlog.getLogger(__name__)


@dataclass
class HTMLContentProcessorConfig(ProcessorConfig):
    """HTML内容处理器配置"""

    timeout: int = field(default=30)
    user_agent: str = field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )
    browserless_url: str = field(default="")
    use_browser: bool = field(default=True)
    browser_timeout: int = field(default=60000)


class HTMLContentProcessor:
    """
    HTML内容处理器

    从Content中的link获取网页内容，支持动态网站抓取。
    如果配置了远程 browserless 服务，将使用无头浏览器抓取动态内容，
    否则回退到传统的 requests 方式。
    使用readability提取主要内容，并将HTML转换为Markdown格式

    配置参数:
    - timeout: requests超时时间（秒）
    - user_agent: 用户代理字符串
    - browserless_url: browserless服务URL，如 "http://localhost:3000"，为空则不使用浏览器
    - use_browser: 是否启用浏览器模式
    - browser_timeout: 浏览器页面加载超时时间（毫秒）

    Examples:
    >>> # 使用 browserless 服务
    >>> config = {
    ...     "timeout": 30,
    ...     "browserless_url": "http://localhost:3000",
    ...     "use_browser": True
    ... }
    >>> processor = HTMLContentProcessor(config)
    >>>
    >>> # 仅使用 requests
    >>> config = {
    ...     "timeout": 30,
    ...     "browserless_url": "",
    ...     "use_browser": False
    ... }
    >>> processor = HTMLContentProcessor(config)
    >>> contents = [Content(...)]
    >>> processed_contents = processor(contents)
    """

    def __init__(self, config: Dict):
        """
        初始化HTML内容处理器

        Args:
            config (Dict): 配置字典，包含timeout和user_agent等参数
        """
        self.config = from_dict(HTMLContentProcessorConfig, config)
        # 为了兼容测试，也直接设置属性
        self.timeout = self.config.timeout
        self.user_agent = self.config.user_agent
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.config.user_agent})

    def _fetch_html_with_browser(self, url: str) -> str:
        """
        使用远程 browserless 服务获取动态网页内容

        Args:
            url (str): 网页URL

        Returns:
            str: HTML内容

        Raises:
            Exception: 浏览器抓取异常
        """
        if not PLAYWRIGHT_AVAILABLE:
            raise Exception("Playwright not available for browser-based fetching")

        if not self.config.browserless_url:
            raise Exception("Browserless URL not configured")

        try:
            with sync_playwright() as p:
                logger.info(
                    f"Using browserless service at {self.config.browserless_url}"
                )
                browser = p.chromium.connect_over_cdp(self.config.browserless_url)
                context = (
                    browser.contexts[0] if browser.contexts else browser.new_context()
                )

                page = context.new_page()
                page.goto(url, timeout=self.config.browser_timeout)
                html = page.content()
                browser.close()
                return html

        except Exception as e:
            logger.error(f"Browser fetch failed for {url}: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def _fetch_html_content(self, url: str) -> str:
        """
        获取网页HTML内容，支持动态网站抓取

        Args:
            url (str): 网页URL

        Returns:
            str: HTML内容

        Raises:
            requests.RequestException: 网络请求异常
        """
        # 如果启用浏览器模式且配置了 browserless_url，使用远程浏览器服务
        if (
            self.config.use_browser
            and self.config.browserless_url
            and PLAYWRIGHT_AVAILABLE
        ):
            try:
                logger.info(
                    f"Attempting browser fetch with browserless service for {url}"
                )
                return self._fetch_html_with_browser(url)
            except Exception as e:
                logger.warning(
                    f"Browser fetch failed for {url}, falling back to requests: {e}"
                )

        # 使用传统的 requests 方式
        try:
            logger.info(f"Using requests to fetch {url}")
            response = self.session.get(
                url, timeout=self.config.timeout, allow_redirects=True
            )
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logger.error(f"Failed to fetch content from {url}: {e}")
            raise

    def _extract_readable_content(self, html: str, url: str) -> str:
        """
        使用readability提取可读内容并转换为Markdown

        Args:
            html (str): 原始HTML内容
            url (str): 原始URL，用于解决相对链接

        Returns:
            str: Markdown格式的内容
        """
        try:
            if not READABILITY_AVAILABLE:
                logger.warning(
                    "readability not available, using direct HTML to markdown conversion"
                )
                return self._html_to_markdown(html)

            # 使用readability提取主要内容
            doc = Document(html)
            title = doc.title()
            content = doc.summary()

            # 将HTML转换为Markdown
            markdown_content = self._html_to_markdown(content)

            # 检查提取的内容是否有意义（非空且包含实际内容）
            cleaned_content = markdown_content.strip()
            if not cleaned_content or len(cleaned_content) < 10:
                logger.warning(f"Extracted content too short or empty from {url}")
                return ""

            return markdown_content

        except Exception as e:
            logger.error(f"Failed to extract readable content: {e}")
            return ""

    def _html_to_markdown(self, html: str) -> str:
        """
        将HTML转换为Markdown格式

        Args:
            html (str): HTML内容

        Returns:
            str: Markdown格式内容
        """
        try:
            # 使用 tools 中的 convert_contents_to_mk 函数
            return convert_contents_to_mk([{"value": html}])
        except Exception as e:
            logger.error(f"Error converting HTML to markdown: {e}")
            return ""

    def __call__(self, contents: List[Content]) -> List[Content]:
        """
        处理内容列表

        Args:
            contents (List[Content]): 输入的内容列表

        Returns:
            List[Content]: 处理后的内容列表，content字段包含Markdown格式的内容
        """
        processed_contents = []

        for content in contents:
            try:
                logger.info(f"Processing content from URL: {content.link}")

                # 获取HTML内容
                html_content = self._fetch_html_content(content.link)

                # 提取可读内容并转换为Markdown
                markdown_content = self._extract_readable_content(
                    html_content, content.link
                )

                if markdown_content:
                    # 创建新的Content对象，更新 content
                    processed_content = deepcopy(content)
                    processed_content.content = markdown_content
                    processed_contents.append(processed_content)

                    logger.info(f"Successfully processed content from {content.link}")
                else:
                    logger.warning(
                        f"No content extracted from {content.link}, keeping original content"
                    )
                    processed_contents.append(deepcopy(content))

            except Exception as e:
                logger.error(f"Failed to process content from {content.link}: {e}")
                processed_contents.append(deepcopy(content))

        return processed_contents
