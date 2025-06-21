import pytest
from unittest.mock import Mock, patch
from feedparser.util import FeedParserDict
import tenacity

from octopus_scraper.scrapers.utils.rsshub import RssHub
from octopus_scraper.scrapers.scraper_protos import Content


class TestRssHub:
    @pytest.fixture
    def sspai_rsshub(self):
        """Fixture to create a mock RssHub instance."""
        config = {
            "hub_root": "https://rsshub.thzu.xyz",
            "route": "/sspai/matrix",
            "fetch_params": {"limit": 1},
        }
        return RssHub(config)

    @pytest.mark.need_external_service
    def test_fetch_sspai_matrix_contents(self, sspai_rsshub):
        contents = sspai_rsshub.fetch_contents()
        assert len(contents) == 1

    @patch("octopus_scraper.scrapers.utils.rsshub.feedparser.parse")
    def test_fetch_contents_success(self, mock_feedparser):
        """测试成功获取内容"""
        # Mock feedparser
        mock_feed = FeedParserDict()
        mock_feed.status = 200
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

        with patch(
            "octopus_scraper.scrapers.utils.rsshub.build_contents"
        ) as mock_build:
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

    @patch("octopus_scraper.scrapers.utils.rsshub.feedparser.parse")
    def test_fetch_contents_with_params(self, mock_feedparser):
        """测试带参数的内容获取"""
        # Mock feedparser
        mock_feed = FeedParserDict()
        mock_feed.status = 200
        mock_feed.entries = []
        mock_feedparser.return_value = mock_feed

        rsshub = RssHub(
            {
                "hub_root": "http://example.com",
                "route": "/test",
                "fetch_params": {"limit": 5},
            }
        )

        with patch(
            "octopus_scraper.scrapers.utils.rsshub.build_contents"
        ) as mock_build:
            mock_build.return_value = []

            # 测试有额外参数的情况
            contents = rsshub.fetch_contents({"filter_title": "test"})
            assert len(contents) == 0

            # 验证feedparser被正确调用
            mock_feedparser.assert_called_once()

    @patch("octopus_scraper.scrapers.utils.rsshub.feedparser.parse")
    def test_fetch_contents_failure(self, mock_feedparser):
        """测试获取内容失败的情况"""
        # Mock feedparser with error status
        mock_feed = FeedParserDict()
        mock_feed.status = 404
        mock_feedparser.return_value = mock_feed

        rsshub = RssHub(
            {"hub_root": "http://example.com", "route": "/test", "fetch_params": None}
        )

        with pytest.raises(tenacity.RetryError):
            rsshub.fetch_contents()

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
