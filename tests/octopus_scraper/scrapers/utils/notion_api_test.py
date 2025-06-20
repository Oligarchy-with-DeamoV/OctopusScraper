import uuid
from unittest.mock import Mock, patch

import pytest

from octopus_scraper.scrapers.utils.notion_api import Content, NotionStorage


class TestNotionStorage:
    @pytest.fixture
    def notion_config(self):
        return {
            "api_key": "test_api_key", 
            "database_id": "test_database_id",
        }

    @pytest.fixture
    def notion_storage(self, notion_config):
        with patch('octopus_scraper.scrapers.utils.notion_api.NotionStorage.check_property_exist'):
            return NotionStorage(notion_config)

    def test_store_content(self, notion_storage):
        with patch.object(notion_storage.notion.pages, 'create') as mock_create, \
             patch.object(notion_storage, 'has_content_id') as mock_has_content:
            mock_create.return_value = {"id": "test_page_id"}
            mock_has_content.return_value = False  # Content doesn't exist yet
            
            content = Content(
                title="this is a test",
                link="url_link", 
                summary="summary",
                content_id=uuid.uuid4().hex[:20],
                content="content",
                published="2025-04-06T13:50:59+08:00",
            )
            result = notion_storage.store_content(content)
            assert result == True
            mock_create.assert_called_once()
            mock_has_content.assert_called_once_with(content.content_id)

    def test_check_contentid(self, notion_storage):
        with patch.object(notion_storage.notion.databases, 'query') as mock_query:
            # Test when content exists
            mock_query.return_value = {"results": [{"id": "existing_page"}]}
            
            content_id = "test_content_id"
            result = notion_storage.has_content_id(content_id)
            assert result == True
            
            # Test when content doesn't exist
            mock_query.return_value = {"results": []}
            result = notion_storage.has_content_id(content_id)
            assert result == False
