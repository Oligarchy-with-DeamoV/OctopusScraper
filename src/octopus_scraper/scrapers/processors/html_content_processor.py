from copy import deepcopy
from typing import Dict, List

import requests
import structlog
from tenacity import retry, stop_after_attempt, wait_fixed

try:
    from readability import Document

    READABILITY_AVAILABLE = True
except ImportError:
    READABILITY_AVAILABLE = False

try:
    import html2text

    HTML2TEXT_AVAILABLE = True
except ImportError:
    HTML2TEXT_AVAILABLE = False

from octopus_scraper.scrapers.processors.protos import ProcessorConfig
from octopus_scraper.scrapers.scraper_protos import Content

logger = structlog.getLogger(__name__)


class HTMLContentProcessorConfig(ProcessorConfig):
    """HTML内容处理器配置"""

    def __init__(self, timeout: int = 30, user_agent: str = None):
        self.timeout = timeout
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )


class HTMLContentProcessor:
    """
    HTML内容处理器

    从Content中的link获取网页内容，使用readability提取主要内容，
    并将HTML转换为Markdown格式

    Examples:
    >>> config = {"timeout": 30}
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
        self.config = HTMLContentProcessorConfig(**config)
        # 为了兼容测试，也直接设置属性
        self.timeout = self.config.timeout
        self.user_agent = self.config.user_agent
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.config.user_agent})

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def _fetch_html_content(self, url: str) -> str:
        """
        获取网页HTML内容

        Args:
            url (str): 网页URL

        Returns:
            str: HTML内容

        Raises:
            requests.RequestException: 网络请求异常
        """
        try:
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
                    "readability not available, using simple HTML processing"
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
            if HTML2TEXT_AVAILABLE:
                h = html2text.HTML2Text()
                h.ignore_links = False
                h.ignore_images = False
                h.body_width = 0  # 不限制行宽
                return h.handle(html)
            else:
                # 如果没有html2text，使用简单的替换
                logger.warning("html2text not available, using simple conversion")
                return self._simple_html_to_markdown(html)
        except Exception as e:
            logger.error(f"Error converting HTML to markdown: {e}")
            return self._simple_html_to_markdown(html)

    def _simple_html_to_markdown(self, html: str) -> str:
        """
        简单的HTML到Markdown转换

        Args:
            html (str): HTML内容

        Returns:
            str: Markdown格式内容
        """
        import re
        from html import unescape

        # 移除HTML标签，保留文本内容
        text = re.sub(r"<script.*?</script>", "", html, flags=re.DOTALL)
        text = re.sub(r"<style.*?</style>", "", text, flags=re.DOTALL)

        # 转换常见的HTML标签到Markdown
        text = re.sub(r"<h1.*?>(.*?)</h1>", r"# \1\n", text)
        text = re.sub(r"<h2.*?>(.*?)</h2>", r"## \1\n", text)
        text = re.sub(r"<h3.*?>(.*?)</h3>", r"### \1\n", text)
        text = re.sub(r"<h4.*?>(.*?)</h4>", r"#### \1\n", text)
        text = re.sub(r"<h5.*?>(.*?)</h5>", r"##### \1\n", text)
        text = re.sub(r"<h6.*?>(.*?)</h6>", r"###### \1\n", text)

        text = re.sub(r"<strong.*?>(.*?)</strong>", r"**\1**", text)
        text = re.sub(r"<b.*?>(.*?)</b>", r"**\1**", text)
        text = re.sub(r"<em.*?>(.*?)</em>", r"*\1*", text)
        text = re.sub(r"<i.*?>(.*?)</i>", r"*\1*", text)

        text = re.sub(r'<a\s+href="([^"]*)"[^>]*>(.*?)</a>', r"[\2](\1)", text)
        text = re.sub(r'<img\s+src="([^"]*)"[^>]*>', r"![](\1)", text)

        text = re.sub(r"<p.*?>", "\n", text)
        text = re.sub(r"</p>", "\n", text)
        text = re.sub(r"<br.*?>", "\n", text)

        # 移除剩余的HTML标签
        text = re.sub(r"<[^>]+>", "", text)

        # 解码HTML实体
        text = unescape(text)

        # 清理多余的空行
        text = re.sub(r"\n\s*\n", "\n\n", text)

        return text.strip()

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
