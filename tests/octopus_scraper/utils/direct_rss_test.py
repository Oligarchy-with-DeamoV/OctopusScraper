from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from feedparser.util import FeedParserDict

from octopus_scraper.protos import Content
from octopus_scraper.utils.direct_rss import DirectRSS


class TestRssHub:
    @pytest.fixture
    def owenyoung_rsshub(self):
        """Fixture to create a mock RssHub instance."""
        config = {
            "hub_root": "https://www.owenyoung.com",
            "route": "/atom.xml",
        }
        return DirectRSS(config)

    @pytest.mark.need_external_service
    def test_fetch_owen_contents(self, owenyoung_rsshub):
        contents = owenyoung_rsshub.fetch_contents()
        assert len(contents) > 0

    @pytest.mark.need_external_service
    def test_fetch_own_contents_with_filter_time(self, owenyoung_rsshub):
        contents = owenyoung_rsshub.fetch_contents()
        total_cnt = len(contents)
        contents = owenyoung_rsshub.fetch_contents(
            params={"filter_time": 60 * 60 * 24 * 60}
        )
        assert len(contents) < total_cnt and len(contents) > 0

    def test_filter_by_timerange_recent(self):
        """测试时间过滤功能 - 最近的内容"""
        recent_time = datetime.now(timezone.utc) - timedelta(minutes=30)
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)

        contents = [
            Content(
                title="Recent Content",
                summary="Recent summary",
                content="Recent content",
                link="http://example.com/recent",
                published=recent_time.isoformat(),
                content_id="recent_id",
            ),
            Content(
                title="Old Content",
                summary="Old summary",
                content="Old content",
                link="http://example.com/old",
                published=old_time.isoformat(),
                content_id="old_id",
            ),
        ]

        filtered = DirectRSS.filter_by_timerange(contents, 3600)  # 1 hour
        assert len(filtered) == 1
        assert filtered[0].title == "Recent Content"

    def test_filter_by_timerange_no_published_date(self):
        """测试时间过滤功能 - 没有发布日期的内容"""
        contents = [
            Content(
                title="No Date Content",
                summary="No date summary",
                content="No date content",
                link="http://example.com/nodate",
                published=None,
                content_id="nodate_id",
            ),
        ]

        filtered = DirectRSS.filter_by_timerange(contents, 3600)
        assert len(filtered) == 0

    def test_filter_by_timerange_invalid_date(self):
        """测试时间过滤功能 - 无效日期格式"""
        contents = [
            Content(
                title="Invalid Date Content",
                summary="Invalid date summary",
                content="Invalid date content",
                link="http://example.com/invalid",
                published="invalid-date-format",
                content_id="invalid_id",
            ),
        ]

        filtered = DirectRSS.filter_by_timerange(contents, 3600)
        assert len(filtered) == 0

    @patch("octopus_scraper.utils.direct_rss.build_contents")
    @patch("octopus_scraper.utils.direct_rss.feedparser.parse")
    @patch("octopus_scraper.utils.direct_rss.requests.get")
    def test_fetch_contents_success(self, mock_requests_get, mock_feedparser, mock_build):
        """测试成功获取内容"""
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

        # Mock build_contents
        mock_build.return_value = [
            Content(
                title="Test Content",
                summary="Test Summary",
                content="Test Content",
                link="http://example.com/entry",
                published=datetime.now(timezone.utc).isoformat(),
                content_id="test_id",
            )
        ]

        direct_rss = DirectRSS(
            {
                "hub_root": "http://example.com",
                "route": "/feed.xml",
            }
        )

        contents = direct_rss.fetch_contents()
        assert len(contents) == 1
        assert contents[0].title == "Test Content"

        # Verify feedparser receives content, not URL
        mock_feedparser.assert_called_once_with(mock_response.content)

    @patch("octopus_scraper.utils.direct_rss.build_contents")
    @patch("octopus_scraper.utils.direct_rss.feedparser.parse")
    @patch("octopus_scraper.utils.direct_rss.requests.get")
    def test_fetch_contents_with_filter_time(
        self, mock_requests_get, mock_feedparser, mock_build
    ):
        """测试带时间过滤的内容获取"""
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

        direct_rss = DirectRSS(
            {
                "hub_root": "http://example.com",
                "route": "/feed.xml",
            }
        )

        recent_time = datetime.now(timezone.utc) - timedelta(minutes=30)
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)

        # Mock build_contents to return test contents
        mock_build.return_value = [
            Content(
                title="Recent Content",
                summary="Recent summary",
                content="Recent content",
                link="http://example.com/recent",
                published=recent_time.isoformat(),
                content_id="recent_id",
            ),
            Content(
                title="Old Content",
                summary="Old summary",
                content="Old content",
                link="http://example.com/old",
                published=old_time.isoformat(),
                content_id="old_id",
            ),
        ]

        contents = direct_rss.fetch_contents({"filter_time": 3600})  # 1 hour
        assert len(contents) == 1
        assert contents[0].title == "Recent Content"

    @patch("octopus_scraper.utils.direct_rss.feedparser.parse")
    @patch("octopus_scraper.utils.direct_rss.requests.get")
    def test_fetch_contents_failure(self, mock_requests_get, mock_feedparser):
        """测试解析RSS失败的情况"""
        # Mock requests.get response (HTTP succeeds)
        mock_response = Mock()
        mock_response.content = b"<invalid>not rss</invalid>"
        mock_response.raise_for_status = Mock()
        mock_requests_get.return_value = mock_response

        # Mock feedparser with bozo error and no entries
        mock_feed = FeedParserDict()
        mock_feed.bozo = 1
        mock_feed.bozo_exception = Exception("not well-formed")
        mock_feed.entries = []
        mock_feedparser.return_value = mock_feed

        direct_rss = DirectRSS(
            {
                "hub_root": "http://example.com",
                "route": "/feed.xml",
            }
        )

        with pytest.raises(RuntimeError, match="Failed to parse RSS feed"):
            direct_rss.fetch_contents()
