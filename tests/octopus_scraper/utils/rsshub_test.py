from unittest.mock import Mock, patch

import pytest
import requests
from feedparser.util import FeedParserDict

from octopus_scraper.protos import Content
from octopus_scraper.utils.rsshub import RssHub


class TestRssHub:
    @pytest.fixture
    def sspai_rsshub(self):
        """Fixture to create a mock RssHub instance."""
        config = {
            "hub_root": "https://rss.owo.nz",
            "route": "/sspai/matrix",
            "fetch_params": {"limit": 1},
        }
        return RssHub(config)

    @pytest.mark.need_external_service
    def test_fetch_sspai_matrix_contents(self, sspai_rsshub):
        contents = sspai_rsshub.fetch_contents()
        assert len(contents) == 1

    @patch("octopus_scraper.utils.rsshub.feedparser.parse")
    @patch("octopus_scraper.utils.rsshub.requests.get")
    def test_fetch_contents_success(self, mock_requests_get, mock_feedparser):
        """测试成功获取内容"""
        # Mock requests.get response
        mock_response = Mock()
        mock_response.content = b"<rss>...</rss>"
        mock_response.raise_for_status = Mock()
        mock_requests_get.return_value = mock_response

        # Mock feedparser
        mock_feed = FeedParserDict()
        mock_feed.bozo = 0
        mock_feed.entries = [
            {
                "title": "Test Entry",
                "summary": "Test Summary",
                "link": "http://example.com/entry",
                "published": "2023-01-01T00:00:00Z",
            }
        ]
        mock_feedparser.return_value = mock_feed

        rsshub = RssHub(
            {
                "hub_root": "http://example.com",
                "route": "/test",
                "fetch_params": {"limit": 1},
            }
        )

        with patch("octopus_scraper.utils.rsshub.build_contents") as mock_build:
            mock_build.return_value = [
                Content(
                    title="Test Content",
                    summary="Test Summary",
                    content="Test Content",
                    link="http://example.com/entry",
                    published="2023-01-01T00:00:00Z",
                    content_id="test_id",
                )
            ]

            contents = rsshub.fetch_contents()
            assert len(contents) == 1
            assert contents[0].title == "Test Content"

            # Verify requests.get was called once (no double request)
            mock_requests_get.assert_called_once()
            mock_feedparser.assert_called_once_with(mock_response.content)

    @patch("octopus_scraper.utils.rsshub.feedparser.parse")
    @patch("octopus_scraper.utils.rsshub.requests.get")
    def test_fetch_contents_with_params(self, mock_requests_get, mock_feedparser):
        """测试带参数的内容获取"""
        # Mock requests.get response
        mock_response = Mock()
        mock_response.content = b"<rss>...</rss>"
        mock_response.raise_for_status = Mock()
        mock_requests_get.return_value = mock_response

        # Mock feedparser
        mock_feed = FeedParserDict()
        mock_feed.bozo = 0
        mock_feed.entries = []
        mock_feedparser.return_value = mock_feed

        rsshub = RssHub(
            {
                "hub_root": "http://example.com",
                "route": "/test",
                "fetch_params": {"limit": 5},
            }
        )

        with patch("octopus_scraper.utils.rsshub.build_contents") as mock_build:
            mock_build.return_value = []

            contents = rsshub.fetch_contents({"filter_title": "test"})
            assert len(contents) == 0

            mock_requests_get.assert_called_once()
            mock_feedparser.assert_called_once()

    @patch("octopus_scraper.utils.rsshub.feedparser.parse")
    @patch("octopus_scraper.utils.rsshub.requests.get")
    def test_fetch_contents_parse_failure(self, mock_requests_get, mock_feedparser):
        """测试解析RSS失败的情况"""
        mock_response = Mock()
        mock_response.content = b"<invalid>not rss</invalid>"
        mock_response.raise_for_status = Mock()
        mock_requests_get.return_value = mock_response

        mock_feed = FeedParserDict()
        mock_feed.bozo = 1
        mock_feed.bozo_exception = Exception("not well-formed")
        mock_feed.entries = []
        mock_feedparser.return_value = mock_feed

        rsshub = RssHub(
            {"hub_root": "http://example.com", "route": "/test", "fetch_params": None}
        )

        with pytest.raises(RuntimeError, match="Failed to parse RSS feed"):
            rsshub.fetch_contents()

    @patch("octopus_scraper.utils.rsshub.requests.get")
    def test_fetch_contents_http_error(self, mock_requests_get):
        """测试HTTP错误直接抛出"""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
        mock_requests_get.return_value = mock_response

        rsshub = RssHub(
            {"hub_root": "http://example.com", "route": "/test", "fetch_params": None}
        )

        with pytest.raises(requests.HTTPError):
            rsshub.fetch_contents()

        assert mock_requests_get.call_count == 1

    @patch("octopus_scraper.utils.rsshub.requests.get")
    def test_fetch_contents_timeout(self, mock_requests_get):
        """测试超时直接抛出，由系统级重试处理"""
        mock_requests_get.side_effect = requests.Timeout("Connection timed out")

        rsshub = RssHub(
            {"hub_root": "http://example.com", "route": "/test", "fetch_params": None}
        )

        with pytest.raises(requests.Timeout):
            rsshub.fetch_contents()

        # No fetcher-level retry, only 1 call
        assert mock_requests_get.call_count == 1

    def test_fetch_contents_does_not_mutate_config_params(self):
        """测试 fetch_contents 不会修改 config.fetch_params"""
        config = {
            "hub_root": "http://example.com",
            "route": "/test",
            "fetch_params": {"limit": 5},
        }
        rsshub = RssHub(config)

        with patch("octopus_scraper.utils.rsshub.requests.get") as mock_get:
            mock_response = Mock()
            mock_response.content = b"<rss></rss>"
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            with patch("octopus_scraper.utils.rsshub.feedparser.parse") as mock_parse:
                mock_feed = FeedParserDict()
                mock_feed.bozo = 0
                mock_feed.entries = []
                mock_parse.return_value = mock_feed

                with patch(
                    "octopus_scraper.utils.rsshub.build_contents", return_value=[]
                ):
                    rsshub.fetch_contents({"filter_title": "test"})

        assert rsshub.config.fetch_params == {"limit": 5}

    def test_config_initialization(self):
        """测试配置初始化"""
        config = {
            "hub_root": "http://example.com",
            "route": "/test",
            "fetch_params": {"limit": 10},
        }

        rsshub = RssHub(config)
        assert rsshub.config.hub_root == "http://example.com"
        assert rsshub.config.route == "/test"
        assert rsshub.config.fetch_params == {"limit": 10}
        assert rsshub.config.request_timeout == (10, 300)

    def test_config_initialization_no_fetch_params(self):
        """测试没有fetch_params的配置初始化"""
        config = {
            "hub_root": "http://example.com",
            "route": "/test",
            "fetch_params": None,
        }

        rsshub = RssHub(config)
        assert rsshub.config.hub_root == "http://example.com"
        assert rsshub.config.route == "/test"
        assert rsshub.config.fetch_params is None

    def test_config_custom_timeout(self):
        """测试自定义超时配置"""
        config = {
            "hub_root": "http://example.com",
            "route": "/test",
            "fetch_params": None,
            "request_timeout": 600,
        }

        rsshub = RssHub(config)
        assert rsshub.config.request_timeout == 600
