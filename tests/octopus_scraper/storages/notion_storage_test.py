import uuid
from unittest.mock import Mock, patch

import pytest

from octopus_scraper.storages.notion_storage import Content, NotionStorage


class TestNotionStorage:
    @pytest.fixture
    def notion_config(self):
        return {
            "api_key": "test_api_key",
            "database_id": "test_database_id",
        }

    @pytest.fixture
    def notion_storage(self, notion_config):
        with patch(
            "octopus_scraper.storages.notion_storage.NotionStorage._check_property_exist"
        ):
            storage = NotionStorage(notion_config)
            # Mock blocks for tests that need it
            if not hasattr(storage.notion, "blocks"):
                storage.notion.blocks = Mock()
                storage.notion.blocks.children = Mock()
            return storage

    def test_store_content(self, notion_storage):
        with patch.object(notion_storage.notion.pages, "create") as mock_create:
            mock_create.return_value = {"id": "test_page_id"}

            content = Content(
                title="this is a test",
                link="url_link",
                summary="summary",
                content_id=uuid.uuid4().hex[:20],
                content="content",
                published="2025-04-06T13:50:59+08:00",
                scraper_name="test-scraper",
            )
            result = notion_storage._store_content(content)
            assert result == True
            mock_create.assert_called_once()

            # Verify the Source select property is included in the call
            call_kwargs = mock_create.call_args
            properties = call_kwargs.kwargs.get(
                "properties", call_kwargs[1].get("properties", {})
            )
            assert properties["Source"] == {"select": {"name": "test-scraper"}}

            # Verify the Published Date property is included in the call
            assert properties["Published Date"] == {
                "date": {"start": "2025-04-06T13:50:59+08:00"}
            }

    def test_store_contents(self, notion_storage):
        """Test the optimized batch storage method with deduplication"""
        with patch.object(
            notion_storage.notion.pages, "create"
        ) as mock_create, patch.object(
            notion_storage, "get_all_content_ids"
        ) as mock_get_all_ids:
            mock_create.return_value = {"id": "test_page_id"}
            # Mock existing content IDs - first content exists, second doesn't
            mock_get_all_ids.return_value = {"existing_id"}

            contents = [
                Content(
                    title="existing content",
                    link="url_link1",
                    summary="summary1",
                    content_id="existing_id",
                    content="content1",
                    published="2025-04-06T13:50:59+08:00",
                ),
                Content(
                    title="new content",
                    link="url_link2",
                    summary="summary2",
                    content_id="new_id",
                    content="content2",
                    published="2025-04-06T13:50:59+08:00",
                ),
            ]

            results = notion_storage.store_contents(contents, deduplicate=True)

            # Should return success for both (one stored, one skipped)
            assert results == [True, True]
            # Only one should be stored (the new one)
            mock_create.assert_called_once()
            # Should call get_all_content_ids only once for batch dedup
            mock_get_all_ids.assert_called_once()

    def test_build_properties_with_scraper_name(self, notion_storage):
        """Test _build_properties includes Source select when scraper_name is set."""
        content = Content(
            title="test",
            link="https://example.com",
            summary="summary",
            content_id="abc123",
            content="body",
            published="2025-04-06T13:50:59+08:00",
            scraper_name="hacker-news",
        )
        properties = notion_storage._build_properties(content)
        assert properties["Source"] == {"select": {"name": "hacker-news"}}

    def test_build_properties_without_scraper_name(self, notion_storage):
        """Test _build_properties sets Source to null select when scraper_name is None."""
        content = Content(
            title="test",
            link="https://example.com",
            summary="summary",
            content_id="abc123",
            content="body",
            published="2025-04-06T13:50:59+08:00",
        )
        properties = notion_storage._build_properties(content)
        assert properties["Source"] == {"select": None}

    def test_build_properties_with_published_date(self, notion_storage):
        """Test _build_properties includes Published Date when published is a valid date."""
        content = Content(
            title="test",
            link="https://example.com",
            summary="summary",
            content_id="abc123",
            content="body",
            published="2025-04-06T13:50:59+08:00",
        )
        properties = notion_storage._build_properties(content)
        assert properties["Published Date"] == {
            "date": {"start": "2025-04-06T13:50:59+08:00"}
        }

    def test_build_properties_with_empty_published(self, notion_storage):
        """Test _build_properties sets Published Date to null when published is empty."""
        content = Content(
            title="test",
            link="https://example.com",
            summary="summary",
            content_id="abc123",
            content="body",
            published="",
        )
        properties = notion_storage._build_properties(content)
        assert properties["Published Date"] == {"date": None}

    def test_build_properties_with_unparseable_published(self, notion_storage):
        """Test _build_properties handles unparseable published date gracefully."""
        content = Content(
            title="test",
            link="https://example.com",
            summary="summary",
            content_id="abc123",
            content="body",
            published="not-a-valid-date",
        )
        properties = notion_storage._build_properties(content)
        assert properties["Published Date"] == {"date": None}

    def test_get_all_content_ids_basic(self, notion_storage):
        with patch.object(notion_storage.notion.databases, "query") as mock_query:
            # Mock first page response
            mock_query.return_value = {
                "results": [
                    {
                        "properties": {
                            "ContentId": {
                                "rich_text": [{"text": {"content": "content_id_1"}}]
                            }
                        }
                    },
                    {
                        "properties": {
                            "ContentId": {
                                "rich_text": [{"text": {"content": "content_id_2"}}]
                            }
                        }
                    },
                ],
                "has_more": False,
                "next_cursor": None,
            }

            result = notion_storage.get_all_content_ids()

            assert result == {"content_id_1", "content_id_2"}
            mock_query.assert_called_once_with(
                database_id="test_database_id", page_size=100
            )

    def test_get_all_content_ids_with_pagination(self, notion_storage):
        """Test getting all content IDs with pagination"""
        with patch.object(notion_storage.notion.databases, "query") as mock_query:
            # Mock two page responses
            mock_query.side_effect = [
                {
                    "results": [
                        {
                            "properties": {
                                "ContentId": {
                                    "rich_text": [{"text": {"content": "content_id_1"}}]
                                }
                            }
                        }
                    ],
                    "has_more": True,
                    "next_cursor": "next_cursor_token",
                },
                {
                    "results": [
                        {
                            "properties": {
                                "ContentId": {
                                    "rich_text": [{"text": {"content": "content_id_2"}}]
                                }
                            }
                        }
                    ],
                    "has_more": False,
                    "next_cursor": None,
                },
            ]

            result = notion_storage.get_all_content_ids()

            assert result == {"content_id_1", "content_id_2"}
            assert mock_query.call_count == 2

            # Check first call
            mock_query.assert_any_call(database_id="test_database_id", page_size=100)

            # Check second call with cursor
            mock_query.assert_any_call(
                database_id="test_database_id",
                page_size=100,
                start_cursor="next_cursor_token",
            )

    # Validation tests for Notion API edge cases that cause 400 errors

    def test_sanitize_option_name_truncates_long_names(self, notion_storage):
        """Test that option names longer than 100 chars are truncated."""
        long_name = "a" * 150
        sanitized = notion_storage._sanitize_option_name(long_name)
        assert len(sanitized) == 100
        assert sanitized.endswith("...")

    def test_sanitize_option_name_removes_newlines(self, notion_storage):
        """Test that newlines are removed from option names."""
        name_with_newlines = "Line1\nLine2\rLine3"
        sanitized = notion_storage._sanitize_option_name(name_with_newlines)
        assert "\n" not in sanitized
        assert "\r" not in sanitized
        assert sanitized == "Line1 Line2 Line3"

    def test_sanitize_option_name_normalizes_whitespace(self, notion_storage):
        """Test that multiple spaces are normalized to single space."""
        name_with_spaces = "Too    many     spaces"
        sanitized = notion_storage._sanitize_option_name(name_with_spaces)
        assert sanitized == "Too many spaces"

    def test_sanitize_option_name_handles_empty_string(self, notion_storage):
        """Test that empty strings are handled correctly."""
        assert notion_storage._sanitize_option_name("") == ""
        assert notion_storage._sanitize_option_name("   ") == ""

    def test_sanitize_option_name_handles_none(self, notion_storage):
        """Test that None values are handled correctly."""
        assert notion_storage._sanitize_option_name(None) == ""

    def test_validate_url_accepts_valid_urls(self, notion_storage):
        """Test that valid URLs are accepted."""
        valid_urls = [
            "https://example.com",
            "http://example.com/path",
            "https://example.com/path?query=1",
        ]
        for url in valid_urls:
            assert notion_storage._validate_url(url) == url

    def test_validate_url_rejects_malformed_urls(self, notion_storage):
        """Test that malformed URLs are rejected."""
        invalid_urls = [
            "",  # Empty
            "   ",  # Whitespace only
            "example.com",  # No protocol
            "ftp://example.com",  # Wrong protocol
            "https://exam ple.com",  # Space in URL
            "https://exam\nple.com",  # Newline in middle of URL
        ]
        for url in invalid_urls:
            result = notion_storage._validate_url(url)
            assert result is None, f"Expected None for URL: {url}, got: {result}"

    def test_validate_url_strips_trailing_whitespace(self, notion_storage):
        """Test that trailing whitespace is stripped from valid URLs."""
        url_with_trailing = "https://example.com\n"
        result = notion_storage._validate_url(url_with_trailing)
        assert result == "https://example.com"

    def test_validate_url_handles_none(self, notion_storage):
        """Test that None values are handled correctly."""
        assert notion_storage._validate_url(None) is None

    def test_build_properties_with_empty_title(self, notion_storage):
        """Test that empty titles are replaced with 'Untitled'."""
        content = Content(
            content_id="test_id",
            title="",  # Empty title
            link="https://example.com",
            summary="Summary",
            content="Content",
            published="2025-01-01T00:00:00Z",
        )
        properties = notion_storage._build_properties(content)
        title_text = properties["Name"]["title"][0]["text"]["content"]
        assert title_text == "Untitled"

    def test_build_properties_with_whitespace_only_title(self, notion_storage):
        """Test that whitespace-only titles are replaced with 'Untitled'."""
        content = Content(
            content_id="test_id",
            title="   ",  # Whitespace only
            link="https://example.com",
            summary="Summary",
            content="Content",
            published="2025-01-01T00:00:00Z",
        )
        properties = notion_storage._build_properties(content)
        title_text = properties["Name"]["title"][0]["text"]["content"]
        assert title_text == "Untitled"

    def test_build_properties_with_invalid_url(self, notion_storage):
        """Test that invalid URLs are set to None."""
        content = Content(
            content_id="test_id",
            title="Title",
            link="not a valid url",  # Invalid URL
            summary="Summary",
            content="Content",
            published="2025-01-01T00:00:00Z",
        )
        properties = notion_storage._build_properties(content)
        assert properties["URL"]["url"] is None

    def test_build_properties_with_empty_url(self, notion_storage):
        """Test that empty URLs are set to None."""
        content = Content(
            content_id="test_id",
            title="Title",
            link="",  # Empty URL
            summary="Summary",
            content="Content",
            published="2025-01-01T00:00:00Z",
        )
        properties = notion_storage._build_properties(content)
        assert properties["URL"]["url"] is None

    def test_build_properties_with_long_keywords(self, notion_storage):
        """Test that long keywords are truncated."""
        long_keyword = "k" * 150
        content = Content(
            content_id="test_id",
            title="Title",
            link="https://example.com",
            summary="Summary",
            content="Content",
            published="2025-01-01T00:00:00Z",
            keywords=[long_keyword, "normal_keyword"],
        )
        properties = notion_storage._build_properties(content)
        keywords = properties["Keywords"]["multi_select"]
        assert len(keywords) == 2
        assert len(keywords[0]["name"]) == 100
        assert keywords[0]["name"].endswith("...")
        assert keywords[1]["name"] == "normal_keyword"

    def test_build_properties_with_keywords_containing_newlines(self, notion_storage):
        """Test that keywords with newlines are sanitized."""
        content = Content(
            content_id="test_id",
            title="Title",
            link="https://example.com",
            summary="Summary",
            content="Content",
            published="2025-01-01T00:00:00Z",
            keywords=["Multi\nLine\nKeyword", "Normal"],
        )
        properties = notion_storage._build_properties(content)
        keywords = properties["Keywords"]["multi_select"]
        assert len(keywords) == 2
        assert "\n" not in keywords[0]["name"]
        assert keywords[0]["name"] == "Multi Line Keyword"

    def test_build_properties_filters_empty_keywords(self, notion_storage):
        """Test that empty keywords are filtered out."""
        content = Content(
            content_id="test_id",
            title="Title",
            link="https://example.com",
            summary="Summary",
            content="Content",
            published="2025-01-01T00:00:00Z",
            keywords=["", "   ", "valid_keyword"],
        )
        properties = notion_storage._build_properties(content)
        keywords = properties["Keywords"]["multi_select"]
        assert len(keywords) == 1
        assert keywords[0]["name"] == "valid_keyword"

    def test_build_properties_filters_empty_tags(self, notion_storage):
        """Test that empty tags are filtered out."""
        content = Content(
            content_id="test_id",
            title="Title",
            link="https://example.com",
            summary="Summary",
            content="Content",
            published="2025-01-01T00:00:00Z",
            tags=["", "   ", "valid_tag"],
        )
        properties = notion_storage._build_properties(content)
        tags = properties["Tags"]["multi_select"]
        assert len(tags) == 1
        assert tags[0]["name"] == "valid_tag"

    def test_build_properties_with_long_scraper_name(self, notion_storage):
        """Test that long scraper names are truncated."""
        long_scraper_name = "s" * 150
        content = Content(
            content_id="test_id",
            title="Title",
            link="https://example.com",
            summary="Summary",
            content="Content",
            published="2025-01-01T00:00:00Z",
            scraper_name=long_scraper_name,
        )
        properties = notion_storage._build_properties(content)
        source = properties["Source"]["select"]["name"]
        assert len(source) == 100
        assert source.endswith("...")

    def test_build_properties_with_empty_summary(self, notion_storage):
        """Test that empty summaries are replaced with default text."""
        content = Content(
            content_id="test_id",
            title="Title",
            link="https://example.com",
            summary="",  # Empty summary
            content="Content",
            published="2025-01-01T00:00:00Z",
        )
        properties = notion_storage._build_properties(content)
        summary_text = properties["Summary"]["rich_text"][0]["text"]["content"]
        assert summary_text == "[No summary available]"

    def test_build_properties_truncates_long_summary(self, notion_storage):
        """Test that summaries longer than MAX_NOTION_SUMMARY_LENGTH are truncated."""
        long_summary = "x" * 3000
        content = Content(
            content_id="test_id",
            title="Title",
            link="https://example.com",
            summary=long_summary,
            content="Content",
            published="2025-01-01T00:00:00Z",
        )
        properties = notion_storage._build_properties(content)
        summary_text = properties["Summary"]["rich_text"][0]["text"]["content"]
        assert len(summary_text) == 2000  # MAX_NOTION_SUMMARY_LENGTH

    def test_store_content_appends_blocks_when_exceeding_100(self, notion_storage):
        """Test that blocks exceeding 100 are appended in batches after page creation."""
        # Create content with very long text that will generate many blocks (>100)
        long_content = "\n".join([f"Paragraph {i}" for i in range(200)])
        content = Content(
            content_id="test_id",
            title="Title",
            link="https://example.com",
            summary="Summary",
            content=long_content,
            published="2025-01-01T00:00:00Z",
        )

        # Mock the notion.pages.create and notion.blocks.children.append calls
        notion_storage.notion.pages.create = Mock(return_value={"id": "page_123"})
        notion_storage.notion.blocks.children.append = Mock()

        # Call _store_content
        notion_storage._store_content(content)

        # Verify pages.create was called with first 100 blocks
        assert notion_storage.notion.pages.create.called
        create_call_args = notion_storage.notion.pages.create.call_args
        initial_children = create_call_args.kwargs["children"]
        assert len(initial_children) == 100

        # Verify blocks.children.append was called for remaining blocks
        assert notion_storage.notion.blocks.children.append.called

        # Count total blocks appended
        total_appended = 0
        for call in notion_storage.notion.blocks.children.append.call_args_list:
            batch = call.kwargs["children"]
            total_appended += len(batch)
            # Each batch should be <= 100
            assert len(batch) <= 100
            # Verify correct page_id is used
            assert call.kwargs["block_id"] == "page_123"

        # Total blocks should be 200 (100 initial + 100 appended)
        assert len(initial_children) + total_appended == 200

    def test_parse_markdown_code_block_with_language(self, notion_storage):
        """Test that code blocks with language specifier are parsed correctly."""
        chunk = {"type": "text", "text": {"content": "```python\nprint('hello')\n```"}}
        blocks = notion_storage._parse_markdown_to_notion_blocks(chunk)

        assert len(blocks) == 1
        assert blocks[0]["type"] == "code"
        assert blocks[0]["code"]["language"] == "python"
        assert "print('hello')" in blocks[0]["code"]["rich_text"][0]["text"]["content"]

    def test_parse_markdown_code_block_without_language(self, notion_storage):
        """Test that code blocks without language get 'plain text' as default."""
        chunk = {"type": "text", "text": {"content": "```\nsome code\n```"}}
        blocks = notion_storage._parse_markdown_to_notion_blocks(chunk)

        assert len(blocks) == 1
        assert blocks[0]["type"] == "code"
        assert blocks[0]["code"]["language"] == "plain text"
        assert "some code" in blocks[0]["code"]["rich_text"][0]["text"]["content"]

    def test_parse_markdown_inline_code(self, notion_storage):
        """Test that inline code (single backtick) gets 'plain text' language."""
        chunk = {"type": "text", "text": {"content": "`inline code`"}}
        blocks = notion_storage._parse_markdown_to_notion_blocks(chunk)

        assert len(blocks) == 1
        assert blocks[0]["type"] == "code"
        assert blocks[0]["code"]["language"] == "plain text"
        assert blocks[0]["code"]["rich_text"][0]["text"]["content"] == "inline code"
