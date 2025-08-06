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
            return NotionStorage(notion_config)

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
            )
            result = notion_storage._store_content(content)
            assert result == True
            mock_create.assert_called_once()

    def test_store_contents(self, notion_storage):
        """Test the optimized batch storage method with deduplication"""
        with patch.object(
            notion_storage.notion.pages, "create"
        ) as mock_create, patch.object(
            notion_storage, "_get_all_content_ids"
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

    def test_get_all_content_ids(self, notion_storage):
        """Test getting all content IDs from Notion database"""
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

            result = notion_storage._get_all_content_ids()

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

            result = notion_storage._get_all_content_ids()

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
