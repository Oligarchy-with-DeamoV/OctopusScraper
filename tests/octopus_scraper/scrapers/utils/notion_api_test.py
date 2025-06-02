import os
import uuid

from dotenv import load_dotenv
from octopus_scraper.scrapers.utils.notion_api import Content, NotionStorage
import pytest

load_dotenv()


class TestNotionStorage:
    @pytest.fixture
    def notion_config(self):
        notion_api_key = os.getenv("NOTION_API_KEY", "")
        database_id = os.getenv("NOTION_DATABASE_ID", "")
        if not (notion_api_key and database_id):
            raise ValueError(
                "NOTION_API_KEY and NOTION_DATABASE_ID does not found in environ settings."
            )
        return {
            "api_key": notion_api_key,
            "database_id": database_id,
        }

    @pytest.fixture
    def notion_storage(self, notion_config):
        return NotionStorage(notion_config)

    @pytest.mark.need_external_service
    def test_store_content(self, notion_storage):
        content = Content(
            title="this is a test",
            link="url_link",
            summary="summary",
            content_id=uuid.uuid4().hex[:20],
            content="content",
            published="2025-04-06T13:50:59+08:00",
        )
        assert (
            notion_storage.store_content(content) == True
        ), f"Failed with token {os.getenv('NOTION_API_KEY', '')} and {os.getenv('NOTION_DATABASE_ID', '')}"

    @pytest.mark.need_external_service
    def test_check_contentid(self, notion_storage):
        content = Content(
            title="this is a test",
            link="url_link",
            summary="summary",
            content_id="conflict_id",
            content="content",
            published="2025-04-06T13:50:59+08:00",
        )
        assert (
            notion_storage.has_content_id(content.content_id) == True
        ), f"Failed with token {os.getenv('NOTION_API_KEY', '')} and {os.getenv('NOTION_DATABASE_ID', '')}"
