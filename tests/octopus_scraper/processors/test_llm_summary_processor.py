"""
Unit tests for LLM Summary Processor.

This module contains comprehensive tests for the LLMSummaryProcessor,
including functionality tests, error handling, and edge cases.
"""

import os
import sys
from copy import deepcopy
from unittest.mock import MagicMock, Mock, patch

import pytest

# Add src to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from octopus_scraper.llm.client import LLMResponse
from octopus_scraper.llm.prompts import PromptLanguage
from octopus_scraper.processors.llm_summary_processor import LLMSummaryProcessor
from octopus_scraper.processors.protos import SummaryProcessorConfig
from octopus_scraper.protos import Content


class TestLLMSummaryProcessor:
    """Test cases for LLMSummaryProcessor."""

    @pytest.fixture
    def sample_config(self):
        """Sample processor configuration."""
        return {
            "model_name": "gpt-3.5-turbo",
            "max_tokens": 1000,
            "temperature": 0.7,
            "timeout": 30,
            "retry_times": 3,
            "max_summary_length": 200,
            "summary_style": "concise",
            "preserve_structure": False,
            "include_key_points": True,
            "priority": 100,
        }

    @pytest.fixture
    def sample_content(self):
        """Sample content for testing."""
        return Content(
            content_id="test_123",
            title="Test Article Title",
            link="https://example.com/test-article",
            summary="Original summary",
            content="This is a test article content with enough text to generate a meaningful summary. "
            * 10,
            published="2025-01-01",
            author="Test Author",
        )

    @pytest.fixture
    def mock_llm_client(self):
        """Mock LLM client."""
        mock_client = Mock()
        mock_client.health_check.return_value = True
        mock_client.generate.return_value = LLMResponse(
            success=True,
            content="This is a generated summary of the test article.",
            metadata={"model": "gpt-3.5-turbo"},
        )
        return mock_client

    def test_processor_initialization(self, sample_config):
        """Test processor initialization with valid config."""
        with patch(
            "octopus_scraper.processors.llm_summary_processor.LLMClient"
        ) as mock_client_class:
            mock_client_class.return_value = Mock()

            processor = LLMSummaryProcessor(sample_config)

            assert processor.name == "LLMSummaryProcessor"
            assert processor.config.max_summary_length == 200
            assert processor.config.summary_style == "concise"
            mock_client_class.assert_called_once()

    def test_invalid_config(self):
        """Test processor initialization with invalid config."""
        invalid_config = {
            "model_name": "",  # Invalid empty model name
            "max_tokens": -1,  # Invalid negative tokens
        }

        with pytest.raises(Exception):  # Should raise ProcessingError
            LLMSummaryProcessor(invalid_config)

    def test_single_content_processing(
        self, sample_config, sample_content, mock_llm_client
    ):
        """Test processing a single content item."""
        with patch(
            "octopus_scraper.processors.llm_summary_processor.LLMClient",
            return_value=mock_llm_client,
        ):
            processor = LLMSummaryProcessor(sample_config)

            result = processor([sample_content])

            assert len(result) == 1
            assert result[0].content_id == sample_content.content_id
            assert result[0].summary != sample_content.summary  # Should be updated
            assert len(result[0].summary) > 0

    def test_multiple_content_processing(self, sample_config, mock_llm_client):
        """Test processing multiple content items."""
        with patch(
            "octopus_scraper.processors.llm_summary_processor.LLMClient",
            return_value=mock_llm_client,
        ):
            processor = LLMSummaryProcessor(sample_config)

            contents = []
            for i in range(3):
                content = Content(
                    content_id=f"test_{i}",
                    title=f"Test Title {i}",
                    link=f"https://example.com/test-{i}",
                    summary="",
                    content=f"Test content {i} " * 20,
                    published="2025-01-01",
                )
                contents.append(content)

            results = processor(contents)

            assert len(results) == 3
            for i, result in enumerate(results):
                assert result.content_id == f"test_{i}"
                assert len(result.summary) > 0

    def test_empty_content_list(self, sample_config, mock_llm_client):
        """Test processing empty content list."""
        with patch(
            "octopus_scraper.processors.llm_summary_processor.LLMClient",
            return_value=mock_llm_client,
        ):
            processor = LLMSummaryProcessor(sample_config)

            result = processor([])

            assert result == []

    def test_language_detection(self, sample_config, mock_llm_client):
        """Test language detection functionality."""
        with patch(
            "octopus_scraper.processors.llm_summary_processor.LLMClient",
            return_value=mock_llm_client,
        ):
            processor = LLMSummaryProcessor(sample_config)

            # Test Chinese content
            chinese_content = Content(
                content_id="test_zh",
                title="测试文章标题",
                link="https://example.com/zh",
                summary="",
                content="这是一篇中文测试文章的内容。" * 20,
                published="2025-01-01",
            )

            # Process and check if appropriate language is detected
            language = processor._detect_content_language(
                chinese_content.title, chinese_content.content
            )
            assert language == PromptLanguage.CHINESE

    def test_content_preprocessing(self, sample_config, mock_llm_client):
        """Test content preprocessing functionality."""
        with patch(
            "octopus_scraper.processors.llm_summary_processor.LLMClient",
            return_value=mock_llm_client,
        ):
            processor = LLMSummaryProcessor(sample_config)

            # Test HTML cleaning
            html_text = "<p>This is <b>bold</b> text with <a href='link'>links</a>.</p>"
            cleaned = processor._preprocess_text(html_text)

            assert "<p>" not in cleaned
            assert "<b>" not in cleaned
            assert "bold" in cleaned
            assert "links" in cleaned

    def test_fallback_summary_creation(self, sample_config, mock_llm_client):
        """Test fallback summary creation for edge cases."""
        with patch(
            "octopus_scraper.processors.llm_summary_processor.LLMClient",
            return_value=mock_llm_client,
        ):
            processor = LLMSummaryProcessor(sample_config)

            # Test with short content
            short_content = "Short text."
            title = "Test Title"

            fallback = processor._create_fallback_summary(title, short_content)

            assert len(fallback) > 0
            assert fallback != title  # Should process the content

    def test_llm_error_handling(self, sample_config, sample_content):
        """Test handling of LLM errors."""
        mock_client = Mock()
        mock_client.health_check.return_value = True
        mock_client.generate.return_value = LLMResponse(
            success=False, error="API request failed"
        )

        with patch(
            "octopus_scraper.processors.llm_summary_processor.LLMClient",
            return_value=mock_client,
        ):
            processor = LLMSummaryProcessor(sample_config)

            # Should handle error gracefully
            results = processor([sample_content])

            assert len(results) == 1
            assert results[0].content_id == sample_content.content_id
            # Should have some summary (fallback)
            assert len(results[0].summary) > 0

    def test_summary_length_validation(self, sample_config, mock_llm_client):
        """Test summary length validation and truncation."""
        # Mock LLM to return very long summary
        mock_llm_client.generate.return_value = LLMResponse(
            success=True,
            content="Very long summary " * 100,  # Much longer than max_length
        )

        with patch(
            "octopus_scraper.processors.llm_summary_processor.LLMClient",
            return_value=mock_llm_client,
        ):
            processor = LLMSummaryProcessor(sample_config)

            content = Content(
                content_id="test_long",
                title="Test Title",
                link="https://example.com",
                summary="",
                content="Test content " * 50,
                published="2025-01-01",
            )

            result = processor([content])

            # Summary should be truncated to max length
            word_count = processor.text_processor.count_words(
                result[0].summary, "mixed"
            )
            assert word_count <= sample_config["max_summary_length"]

    def test_cache_functionality(self, sample_config, sample_content, mock_llm_client):
        """Test summary caching functionality."""
        with patch(
            "octopus_scraper.processors.llm_summary_processor.LLMClient",
            return_value=mock_llm_client,
        ):
            processor = LLMSummaryProcessor(sample_config)

            # Process same content twice
            result1 = processor([sample_content])
            result2 = processor([sample_content])

            # Should generate same summary (from cache)
            assert result1[0].summary == result2[0].summary

            # LLM should only be called once (second time uses cache)
            assert mock_llm_client.generate.call_count == 1

    def test_different_summary_styles(self, mock_llm_client):
        """Test different summary styles."""
        styles = ["concise", "detailed", "bullet_points", "executive"]

        for style in styles:
            config = {
                "model_name": "gpt-3.5-turbo",
                "max_tokens": 1000,
                "temperature": 0.7,
                "timeout": 30,
                "retry_times": 3,
                "max_summary_length": 200,
                "summary_style": style,
                "preserve_structure": False,
                "include_key_points": True,
                "priority": 100,
            }

            with patch(
                "octopus_scraper.processors.llm_summary_processor.LLMClient",
                return_value=mock_llm_client,
            ):
                processor = LLMSummaryProcessor(config)
                assert processor.config.summary_style == style

    def test_health_check(self, sample_config, mock_llm_client):
        """Test processor health check."""
        with patch(
            "octopus_scraper.processors.llm_summary_processor.LLMClient",
            return_value=mock_llm_client,
        ):
            processor = LLMSummaryProcessor(sample_config)

            # Should return True when LLM client is healthy
            assert processor.health_check() is True

            # Test unhealthy client
            mock_llm_client.health_check.return_value = False
            assert processor.health_check() is False

    def test_get_summary_stats(self, sample_config, mock_llm_client):
        """Test getting processor statistics."""
        with patch(
            "octopus_scraper.processors.llm_summary_processor.LLMClient",
            return_value=mock_llm_client,
        ):
            processor = LLMSummaryProcessor(sample_config)

            stats = processor.get_summary_stats()

            assert "processor_name" in stats
            assert "model_name" in stats
            assert "summary_style" in stats
            assert "cache_size" in stats
            assert stats["processor_name"] == "LLMSummaryProcessor"

    def test_clear_cache(self, sample_config, sample_content, mock_llm_client):
        """Test cache clearing functionality."""
        with patch(
            "octopus_scraper.processors.llm_summary_processor.LLMClient",
            return_value=mock_llm_client,
        ):
            processor = LLMSummaryProcessor(sample_config)

            # Process content to populate cache
            processor([sample_content])

            # Verify cache has items
            stats_before = processor.get_summary_stats()
            assert stats_before["cache_size"] > 0

            # Clear cache
            processor.clear_cache()

            # Verify cache is empty
            stats_after = processor.get_summary_stats()
            assert stats_after["cache_size"] == 0


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
