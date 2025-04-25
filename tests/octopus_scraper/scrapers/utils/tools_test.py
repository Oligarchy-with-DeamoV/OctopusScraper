import pytest

from octopus_scraper.scrapers.utils.tools import (
    FeedParserDict,
    build_contents,
    convert_contents_to_mk,
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
    expected = "This is __bold__ text.\n\nAnd _italic_ text.\n\n# 欢迎来到我的网页\n\n这是一个简单的HTML段落，用来展示如何使用HTML标签来编写内容。你可以在这里添加任意文本信息。\n\n想了解更多信息，请访问 [我的主页](https://www.example.com)。\n\n3个换行的测试\n\n* 星号处理测试"
    assert markdown.strip() == expected.strip()


def test_build_contents():
    mock_feed = FeedParserDict(
        {
            "entries": [
                FeedParserDict(
                    {
                        "id": "123",
                        "title": "Test Entry",
                        "link": "https://example.com/test",
                        "summary": "<p>This is a <b>summary</b>.</p>",
                        "content": [{"value": "<p>Full <i>content</i> here.</p>"}],
                    }
                )
            ]
        }
    )

    contents = build_contents(mock_feed)
    assert len(contents) == 1
    content = contents[0]

    assert content.content_id == "123"
    assert content.title == "Test Entry"
    assert content.link == "https://example.com/test"
    assert "_summary_" in content.summary
    assert "_content_" in content.content
