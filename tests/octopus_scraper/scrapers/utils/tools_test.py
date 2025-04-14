import pytest

from octopus_scraper.scrapers.utils.tools import (
    FeedParserDict,
    build_contents,
    convert_contents_to_mk,
)


def test_convert_contents_to_mk():
    html_content = [
        {"value": "<p>This is <strong>bold</strong> text.</p>"},
        {"value": "<p>And <em>italic</em> text.</p>"},
    ]
    markdown = convert_contents_to_mk(html_content)
    expected = "This is __bold__ text.\nAnd _italic_ text.\n"
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
