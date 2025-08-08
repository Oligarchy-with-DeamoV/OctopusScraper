"""
Simple additional tests for tools module.
"""

from unittest.mock import Mock, patch

import pytest

from octopus_scraper.utils.tools import build_contents, convert_contents_to_mk


class TestToolsSimple:
    """Simple tests to improve coverage."""

    def test_convert_contents_to_mk_empty(self):
        """Test convert with empty content."""
        result = convert_contents_to_mk("")
        assert result == ""

    def test_convert_contents_to_mk_html(self):
        """Test convert with HTML."""
        html = "<p>Hello <strong>world</strong></p>"
        result = convert_contents_to_mk(html)
        assert "Hello" in result

    def test_build_contents_empty(self):
        """Test build contents with empty feed."""
        from feedparser import FeedParserDict

        feed = FeedParserDict()
        feed.entries = []
        result = build_contents(feed)
        assert result == []

    def test_build_contents_with_entries(self):
        """Test build contents with entries."""
        from feedparser import FeedParserDict

        feed = FeedParserDict()
        feed.entries = [
            FeedParserDict(
                {
                    "title": "Test Title",
                    "link": "https://example.com",
                    "summary": "Test summary",
                    "content": [{"value": "Test content"}],
                    "published": "2025-01-01T12:00:00Z",
                    "id": "test_123",
                }
            )
        ]

        result = build_contents(feed)
        assert len(result) == 1
        assert result[0].title == "Test Title"
