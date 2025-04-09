import os

from octopus_scraper.scrapers.utils.notion_api import Content, NotionStorage
import pytest


class TestNotionStorage:
    @pytest.fixture
    def notion_config(self):
        notion_api_key = os.environ.get("NOTION_API_KEY")
        database_id = os.environ.get("NOTION_DATABASE_ID")
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
            content_id="content_id",
            content="content",
        )
        assert (
            notion_storage.store_content(content) == True
        ), f"Failed with token {os.environ.get('NOTION_API_KEY')} and {os.environ.get('NOTION_DATABASE_ID')}"

    @pytest.mark.need_external_service
    def test_check_contentid(self, notion_storage):
        content = Content(
            title="this is a test",
            link="url_link",
            summary="summary",
            content_id="conflict_id",
            content="content",
        )
        assert (
            notion_storage.has_content_id(content.content_id) == True
        ), f"Failed with token {os.environ.get('NOTION_API_KEY')} and {os.environ.get('NOTION_DATABASE_ID')}"
