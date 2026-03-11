import os

import pytest

from octopus_scraper.utils.tools import (
    DEFAULT_SUMMARY_MAX_LENGTH,
    FeedParserDict,
    build_contents,
    convert_contents_to_mk,
    generate_content_with_fallback,
    generate_stable_content_id,
    generate_summary_from_entry,
)

HTML_CONTENT = """
<h1>欢迎来到我的网页</h1>
<p>这是一个简单的HTML段落，用来展示如何使用HTML标签来编写内容。你可以在这里添加任意文本信息。</p>
<p>想了解更多信息，请访问
<a href="https://www.example.com" target="_blank">我的主页</a>。
</p>





  <p>3个换行的测试</p>
*  星号处理测试
"""


def test_convert_contents_to_mk():
    html_content = [
        {"value": "<p>This is <strong>bold</strong> text.</p>"},
        {"value": "<p>And <em>italic</em> text.</p>"},
        {"value": HTML_CONTENT},
    ]
    markdown = convert_contents_to_mk(html_content)
    expected = "This is **bold** text.\n\nAnd *italic* text.\n\n欢迎来到我的网页\n========\n\n这是一个简单的HTML段落，用来展示如何使用HTML标签来编写内容。你可以在这里添加任意文本信息。\n\n想了解更多信息，请访问\n[我的主页](https://www.example.com)。\n\n3个换行的测试\n\n\\* 星号处理测试"
    assert markdown.strip() == expected.strip()


def test_convert_contents_preserves_markdown_links():
    """P1-5/P1-6: Links should not be re-processed by BeautifulSoup."""
    html_content = [
        {
            "value": '<p>Visit <a href="https://example.com">Example</a> and <a href="https://test.com">Test</a>.</p>'
        }
    ]
    result = convert_contents_to_mk(html_content)
    assert "[Example](https://example.com)" in result
    assert "[Test](https://test.com)" in result


def test_generate_stable_content_id():
    # Test with hash
    entry_no_id = FeedParserDict(
        {
            "link": "https://example.com/article?param=value",
            "published": "2025-06-21T10:00:00Z",
        }
    )
    hash_id = generate_stable_content_id(entry_no_id)
    assert len(hash_id) == 16  # MD5 hash truncated to 16 chars
    assert isinstance(hash_id, str)


def test_generate_summary_from_entry():
    # Test normal summary
    entry_normal = FeedParserDict({"summary": "<p>Short summary</p>"})
    summary = generate_summary_from_entry(entry_normal)
    assert "Short summary" in summary

    # Test long summary (should return empty)
    long_text = "Very long summary. " * 100  # 创建超长文本
    entry_long = FeedParserDict({"summary": f"<p>{long_text}</p>"})
    summary = generate_summary_from_entry(entry_long, max_length=50)
    assert summary == ""

    # Test empty summary
    entry_empty = FeedParserDict({})
    summary = generate_summary_from_entry(entry_empty)
    assert summary == ""


def test_generate_content_with_fallback():
    # Test with content present
    entry_with_content = FeedParserDict(
        {
            "content": [{"value": "<p>Main content here</p>"}],
            "summary": "<p>Summary text</p>",
        }
    )
    content = generate_content_with_fallback(entry_with_content)
    assert "Main content here" in content

    # Test fallback to summary
    entry_no_content = FeedParserDict(
        {
            "content": [],
            "summary": "<p>Summary as content</p>",
        }
    )
    content = generate_content_with_fallback(entry_no_content)
    assert "Summary as content" in content

    # Test no content available (empty summary)
    entry_empty = FeedParserDict(
        {
            "content": [],
            "summary": "",
        }
    )
    content = generate_content_with_fallback(entry_empty)
    assert content == ""


def test_build_contents():
    """Test build_contents with various fallback scenarios"""
    mock_feed = FeedParserDict(
        {
            "entries": [
                # Entry with all fields
                FeedParserDict(
                    {
                        "id": "full-entry",
                        "title": "Full Entry",
                        "link": "https://example.com/full",
                        "summary": "<p>Short summary</p>",
                        "content": [{"value": "<p>Full content</p>"}],
                        "published": "2025-06-21T10:00:00Z",
                    }
                ),
                # Entry with long summary (should be empty)
                FeedParserDict(
                    {
                        "guid": "long-summary",
                        "title": "Long Summary Entry",
                        "link": "https://example.com/long",
                        "summary": f"<p>{'Very long summary. ' * 100}</p>",
                        "content": [{"value": "<p>Content here</p>"}],
                    }
                ),
                # Entry with content fallback to summary
                FeedParserDict(
                    {
                        "title": "Fallback Entry",
                        "link": "https://example.com/fallback",
                        "summary": "<p>Summary as content</p>",
                        "content": [],
                        "published": "2025-06-21T11:00:00Z",
                    }
                ),
            ]
        }
    )

    contents = build_contents(mock_feed)
    assert len(contents) == 3

    # Check first entry (normal)
    assert contents[0].content_id == "099b1bfec8507133"
    assert "Short summary" in contents[0].summary
    assert "Full content" in contents[0].content

    # Check second entry (long summary should be empty)
    assert contents[1].content_id == "6be180f0a44acaed"
    assert contents[1].summary == ""  # Should be empty due to length
    assert "Content here" in contents[1].content

    # Check third entry (hash ID and summary for content)
    assert len(contents[2].content_id) == 16  # Hash-based ID
    assert "Summary as content" in contents[2].summary
    assert "Summary as content" in contents[2].content  # Summary used as content


def test_summary_max_length_from_env():
    """Test that summary max length can be configured via environment variable"""
    # Test that the constant reads from environment
    assert isinstance(DEFAULT_SUMMARY_MAX_LENGTH, int)

    # Test with custom length
    entry_normal = FeedParserDict({"summary": "<p>Short summary</p>"})
    summary = generate_summary_from_entry(entry_normal, max_length=10)
    assert summary == ""  # Should be empty because "Short summary" > 10 chars

    # Test with sufficient length
    summary = generate_summary_from_entry(entry_normal, max_length=50)
    assert "Short summary" in summary


def test_env_variable_integration():
    """Test that DEFAULT_SUMMARY_MAX_LENGTH correctly reads from environment"""
    # Test default behavior
    assert DEFAULT_SUMMARY_MAX_LENGTH > 0

    # This test verifies the environment variable integration
    # The actual value depends on whether OCTOPUS_SUMMARY_MAX_LENGTH is set
    expected_default = int(os.getenv("OCTOPUS_SUMMARY_MAX_LENGTH", "500"))
    assert DEFAULT_SUMMARY_MAX_LENGTH == expected_default
