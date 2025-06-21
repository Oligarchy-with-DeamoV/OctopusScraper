import pytest
from unittest.mock import Mock

from octopus_scraper.scrapers.scraper_protos import Content
from octopus_scraper.scrapers.utils.content_deduplicator import (
    ContentDeduplicator,
    ContentExistenceChecker,
)


def test_content_deduplicator():
    """Test ContentDeduplicator with mock existence checker"""
    # Create mock existence checker
    mock_checker = Mock(spec=ContentExistenceChecker)

    # Setup mock behavior: content_1 exists, content_2 and content_3 don't exist
    def mock_has_content_id(content_id: str) -> bool:
        return content_id == "existing-content-1"

    mock_checker.has_content_id.side_effect = mock_has_content_id

    # Create test contents
    contents = [
        Content(
            content_id="existing-content-1",
            title="Existing Content",
            link="https://example.com/existing",
            summary="Existing summary",
            content="Existing content",
            published="2025-06-21T10:00:00Z",
        ),
        Content(
            content_id="new-content-2",
            title="New Content 2",
            link="https://example.com/new2",
            summary="New summary 2",
            content="New content 2",
            published="2025-06-21T10:30:00Z",
        ),
        Content(
            content_id="new-content-3",
            title="New Content 3",
            link="https://example.com/new3",
            summary="New summary 3",
            content="New content 3",
            published="2025-06-21T11:00:00Z",
        ),
    ]

    # Test deduplication
    deduplicator = ContentDeduplicator(mock_checker)
    new_contents = deduplicator.filter_new_contents(contents)

    # Should return only the 2 new contents
    assert len(new_contents) == 2
    assert new_contents[0].content_id == "new-content-2"
    assert new_contents[1].content_id == "new-content-3"

    # Verify mock was called correctly
    assert mock_checker.has_content_id.call_count == 3
    mock_checker.has_content_id.assert_any_call("existing-content-1")
    mock_checker.has_content_id.assert_any_call("new-content-2")
    mock_checker.has_content_id.assert_any_call("new-content-3")


def test_content_deduplicator_all_new():
    """Test when all contents are new"""
    mock_checker = Mock(spec=ContentExistenceChecker)
    mock_checker.has_content_id.return_value = False  # All contents are new

    contents = [
        Content(
            content_id="new-1",
            title="New Content 1",
            link="https://example.com/new1",
            summary="Summary 1",
            content="Content 1",
            published="2025-06-21T10:00:00Z",
        ),
        Content(
            content_id="new-2",
            title="New Content 2",
            link="https://example.com/new2",
            summary="Summary 2",
            content="Content 2",
            published="2025-06-21T10:30:00Z",
        ),
    ]

    deduplicator = ContentDeduplicator(mock_checker)
    new_contents = deduplicator.filter_new_contents(contents)

    assert len(new_contents) == 2
    assert new_contents == contents


def test_content_deduplicator_all_existing():
    """Test when all contents already exist"""
    mock_checker = Mock(spec=ContentExistenceChecker)
    mock_checker.has_content_id.return_value = True  # All contents exist

    contents = [
        Content(
            content_id="existing-1",
            title="Existing Content 1",
            link="https://example.com/existing1",
            summary="Summary 1",
            content="Content 1",
            published="2025-06-21T10:00:00Z",
        ),
        Content(
            content_id="existing-2",
            title="Existing Content 2",
            link="https://example.com/existing2",
            summary="Summary 2",
            content="Content 2",
            published="2025-06-21T10:30:00Z",
        ),
    ]

    deduplicator = ContentDeduplicator(mock_checker)
    new_contents = deduplicator.filter_new_contents(contents)

    assert len(new_contents) == 0


def test_content_deduplicator_empty_list():
    """Test with empty content list"""
    mock_checker = Mock(spec=ContentExistenceChecker)

    deduplicator = ContentDeduplicator(mock_checker)
    new_contents = deduplicator.filter_new_contents([])

    assert len(new_contents) == 0
    assert mock_checker.has_content_id.call_count == 0
