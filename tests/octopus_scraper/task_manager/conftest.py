"""
Pytest configuration for task manager tests.
"""

import pytest
import sys
import os

# Add the src directory to Python path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))


@pytest.fixture(autouse=True)
def setup_test_environment():
    """Set up test environment for all task manager tests."""
    # Suppress verbose logging during tests
    import logging

    logging.getLogger("octopus_scraper").setLevel(logging.WARNING)


@pytest.fixture
def mock_content():
    """Create mock content for testing."""
    from octopus_scraper.scrapers.scraper import Content

    return Content(
        content_id="test_content_123",
        title="Test Content Title",
        link="https://example.com/test",
        summary="Test content summary",
        content="Test content body",
        published="2025-07-18T10:00:00Z",
    )
