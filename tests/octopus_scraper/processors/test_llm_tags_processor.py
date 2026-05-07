"""
Unit tests for LLM Tags Processor.

This module contains comprehensive tests for the LLMTagsProcessor,
including tag generation, categorization, and error handling.
"""

import os
import sys
from unittest.mock import Mock, patch

import pytest

# Add src to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from octopus_scraper.llm.client import LLMResponse
from octopus_scraper.processors.llm_tags_processor import LLMTagsProcessor
from octopus_scraper.processors.processor_base import ProcessingError
from octopus_scraper.protos import Content


class TestLLMTagsProcessor:
    """Test cases for LLMTagsProcessor."""

    @pytest.fixture
    def sample_config(self):
        """Sample processor configuration."""
        return {
            "model_name": "gpt-3.5-turbo",
            "max_tokens": 1000,
            "temperature": 0.7,
            "timeout": 30,
            "retry_times": 3,
            "max_tags_count": 5,
            "confidence_threshold": 0.5,
            "priority": 100,
        }

    @pytest.fixture
    def sample_content(self):
        """Sample content for testing."""
        return Content(
            content_id="test_123",
            title="人工智能在医疗领域的应用",
            link="https://example.com/test-article",
            summary="",
            content="人工智能技术正在医疗行业中发挥越来越重要的作用。机器学习算法可以帮助医生更准确地分析医学影像，识别早期疾病症状。在药物发现领域，AI可以加速新药的开发过程。",
            published="2025-01-01",
            author="Test Author",
            keywords=None,
            tags=None,
        )

    @patch("octopus_scraper.processors.llm_tags_processor.LLMClient")
    def test_processor_initialization(self, mock_client_class, sample_config):
        """Test processor initialization."""
        mock_client = Mock()
        mock_client.health_check.return_value = True
        mock_client_class.return_value = mock_client

        processor = LLMTagsProcessor(sample_config)

        assert processor.name == "LLMTagsProcessor"
        assert processor.config.max_tags_count == 5
        assert processor.config.confidence_threshold == 0.5
        mock_client_class.assert_called_once()

    def test_invalid_config(self):
        """Test initialization with invalid configuration."""
        invalid_config = {
            "model_name": "gpt-3.5-turbo",
            "max_tags_count": -1,  # Invalid
            "priority": 100,
        }

        with pytest.raises(ProcessingError):
            LLMTagsProcessor(invalid_config)

    @patch("octopus_scraper.processors.llm_tags_processor.LLMClient")
    def test_single_content_processing(
        self, mock_client_class, sample_config, sample_content
    ):
        """Test processing a single content item."""
        mock_llm_client = Mock()
        mock_llm_client.health_check.return_value = True
        mock_llm_client.generate.return_value = LLMResponse(
            success=True,
            content='{"tags": ["人工智能", "医疗", "机器学习", "医学影像", "药物发现"], "confidence": {"人工智能": 0.95, "医疗": 0.90, "机器学习": 0.85, "医学影像": 0.80, "药物发现": 0.75}}',
            metadata={"model": "gpt-3.5-turbo"},
        )
        mock_llm_client.extract_json_from_response.return_value = '{"tags": ["人工智能", "医疗", "机器学习", "医学影像", "药物发现"], "confidence": {"人工智能": 0.95, "医疗": 0.90, "机器学习": 0.85, "医学影像": 0.80, "药物发现": 0.75}}'
        mock_client_class.return_value = mock_llm_client

        processor = LLMTagsProcessor(sample_config)
        result = processor([sample_content])

        assert len(result) == 1
        assert result[0].content_id == sample_content.content_id
        assert result[0].tags is not None
        assert len(result[0].tags) <= 5
        assert "人工智能" in result[0].tags
        assert "医疗" in result[0].tags

    @patch("octopus_scraper.processors.llm_tags_processor.LLMClient")
    def test_multiple_content_processing(self, mock_client_class, sample_config):
        """Test processing multiple content items."""
        mock_llm_client = Mock()
        mock_llm_client.health_check.return_value = True
        mock_llm_client.generate.return_value = LLMResponse(
            success=True,
            content='{"tags": ["技术", "创新", "发展"]}',
            metadata={"model": "gpt-3.5-turbo"},
        )
        mock_llm_client.extract_json_from_response.return_value = (
            '{"tags": ["技术", "创新", "发展"]}'
        )
        mock_client_class.return_value = mock_llm_client

        processor = LLMTagsProcessor(sample_config)

        content_list = [
            Content(
                content_id=f"test_{i}",
                title=f"Test Article {i}",
                link=f"https://example.com/test-{i}",
                summary="",
                content=f"Test content {i} with technology and innovation topics.",
                published="2025-01-01",
                author="Test Author",
                keywords=None,
                tags=None,
            )
            for i in range(3)
        ]

        results = processor(content_list)

        assert len(results) == 3
        for result in results:
            assert result.tags is not None
            assert len(result.tags) > 0

    @patch("octopus_scraper.processors.llm_tags_processor.LLMClient")
    def test_empty_content_list(self, mock_client_class, sample_config):
        """Test processing empty content list."""
        mock_llm_client = Mock()
        mock_client_class.return_value = mock_llm_client

        processor = LLMTagsProcessor(sample_config)
        results = processor([])

        assert len(results) == 0

    @patch("octopus_scraper.processors.llm_tags_processor.LLMClient")
    def test_custom_categorization(self, mock_client_class, sample_content):
        """Test custom tag categorization."""
        config_with_categories = {
            "model_name": "gpt-3.5-turbo",
            "max_tokens": 1000,
            "temperature": 0.7,
            "timeout": 30,
            "retry_times": 3,
            "max_tags_count": 5,
            "confidence_threshold": 0.5,
            "custom_categories": {
                "technology": ["人工智能", "机器学习", "AI"],
                "domain": ["医疗", "healthcare", "medical"],
            },
            "priority": 100,
        }

        mock_llm_client = Mock()
        mock_llm_client.health_check.return_value = True
        mock_llm_client.generate.return_value = LLMResponse(
            success=True,
            content='{"tags": ["人工智能", "医疗", "创新"]}',
            metadata={"model": "gpt-3.5-turbo"},
        )
        mock_llm_client.extract_json_from_response.return_value = (
            '{"tags": ["人工智能", "医疗", "创新"]}'
        )
        mock_client_class.return_value = mock_llm_client

        processor = LLMTagsProcessor(config_with_categories)
        result = processor([sample_content])

        assert len(result) == 1
        tags = result[0].tags
        assert any("technology:" in tag for tag in tags)  # Should have categorized tags
        assert any("domain:" in tag for tag in tags)

    @patch("octopus_scraper.processors.llm_tags_processor.LLMClient")
    def test_confidence_threshold_filtering(self, mock_client_class, sample_content):
        """Test filtering tags by confidence threshold."""
        config_with_threshold = {
            "model_name": "gpt-3.5-turbo",
            "max_tokens": 1000,
            "temperature": 0.7,
            "timeout": 30,
            "retry_times": 3,
            "max_tags_count": 5,
            "confidence_threshold": 0.8,  # High threshold
            "priority": 100,
        }

        mock_llm_client = Mock()
        mock_llm_client.health_check.return_value = True
        mock_llm_client.generate.return_value = LLMResponse(
            success=True,
            content='{"tags": ["高信度标签", "低信度标签"], "confidence": {"高信度标签": 0.9, "低信度标签": 0.6}}',
            metadata={"model": "gpt-3.5-turbo"},
        )
        mock_llm_client.extract_json_from_response.return_value = '{"tags": ["高信度标签", "低信度标签"], "confidence": {"高信度标签": 0.9, "低信度标签": 0.6}}'
        mock_client_class.return_value = mock_llm_client

        processor = LLMTagsProcessor(config_with_threshold)
        result = processor([sample_content])

        assert len(result) == 1
        tags = result[0].tags
        assert "高信度标签" in tags  # Should be included (0.9 > 0.8)
        # Low confidence tag might be filtered out

    @patch("octopus_scraper.processors.llm_tags_processor.LLMClient")
    def test_llm_error_handling(self, mock_client_class, sample_config, sample_content):
        """Test handling LLM errors gracefully."""
        mock_client = Mock()
        mock_client.health_check.return_value = True
        mock_client.generate.return_value = LLMResponse(
            success=False, error="API Error: Rate limit exceeded"
        )
        mock_client_class.return_value = mock_client

        processor = LLMTagsProcessor(sample_config)
        result = processor([sample_content])

        assert len(result) == 1
        assert result[0].tags is not None  # Should have fallback tags
        assert len(result[0].tags) > 0

    @patch("octopus_scraper.processors.llm_tags_processor.LLMClient")
    def test_fallback_tags_creation(self, mock_client_class, sample_config):
        """Test fallback tag creation when LLM fails."""
        mock_llm_client = Mock()
        mock_llm_client.health_check.return_value = True
        mock_llm_client.generate.return_value = LLMResponse(
            success=False, error="Network error"
        )
        mock_client_class.return_value = mock_llm_client

        processor = LLMTagsProcessor(sample_config)

        content = Content(
            content_id="fallback_test",
            title="Machine Learning Applications in Healthcare",
            link="https://example.com/ml-healthcare",
            summary="",
            content="Machine learning algorithms are revolutionizing healthcare by improving diagnostic accuracy and treatment personalization.",
            published="2025-01-01",
            author="ML Expert",
            keywords=None,
            tags=None,
        )

        result = processor([content])

        assert len(result) == 1
        assert result[0].tags is not None
        assert len(result[0].tags) > 0
        # Should contain fallback tags derived from title/content

    @patch("octopus_scraper.processors.llm_tags_processor.LLMClient")
    def test_cache_functionality(
        self, mock_client_class, sample_config, sample_content
    ):
        """Test caching of generated tags."""
        mock_llm_client = Mock()
        mock_llm_client.health_check.return_value = True
        mock_llm_client.generate.return_value = LLMResponse(
            success=True,
            content='{"tags": ["cached", "tags"]}',
            metadata={"model": "gpt-3.5-turbo"},
        )
        mock_llm_client.extract_json_from_response.return_value = (
            '{"tags": ["cached", "tags"]}'
        )
        mock_client_class.return_value = mock_llm_client

        processor = LLMTagsProcessor(sample_config)

        # First call should trigger LLM
        result1 = processor([sample_content])

        # Second call with same content should use cache
        result2 = processor([sample_content])

        assert len(result1) == 1
        assert len(result2) == 1
        assert result1[0].tags == result2[0].tags

        # LLM should only be called once (cached second time)
        assert mock_llm_client.generate.call_count == 1

    @patch("octopus_scraper.processors.llm_tags_processor.LLMClient")
    def test_health_check(self, mock_client_class, sample_config):
        """Test processor health check."""
        mock_llm_client = Mock()
        mock_llm_client.health_check.return_value = True
        mock_client_class.return_value = mock_llm_client

        processor = LLMTagsProcessor(sample_config)

        assert processor.health_check() is True

        # Test unhealthy state
        mock_llm_client.health_check.return_value = False
        assert processor.health_check() is False

    @patch("octopus_scraper.processors.llm_tags_processor.LLMClient")
    def test_get_tags_stats(self, mock_client_class, sample_config):
        """Test getting processor statistics."""
        mock_llm_client = Mock()
        mock_client_class.return_value = mock_llm_client

        processor = LLMTagsProcessor(sample_config)
        stats = processor.get_tags_stats()

        assert stats["processor_name"] == "LLMTagsProcessor"
        assert stats["model_name"] == "gpt-3.5-turbo"
        assert stats["max_tags_count"] == 5
        assert "cache_size" in stats
        assert "config" in stats

    @patch("octopus_scraper.processors.llm_tags_processor.LLMClient")
    def test_clear_cache(self, mock_client_class, sample_config, sample_content):
        """Test clearing the tags cache."""
        mock_llm_client = Mock()
        mock_llm_client.health_check.return_value = True
        mock_llm_client.generate.return_value = LLMResponse(
            success=True,
            content='{"tags": ["test", "tags"]}',
            metadata={"model": "gpt-3.5-turbo"},
        )
        mock_llm_client.extract_json_from_response.return_value = (
            '{"tags": ["test", "tags"]}'
        )
        mock_client_class.return_value = mock_llm_client

        processor = LLMTagsProcessor(sample_config)

        # Generate some cached data
        processor([sample_content])

        # Verify cache has content
        stats_before = processor.get_tags_stats()
        assert stats_before["cache_size"] > 0

        # Clear cache
        processor.clear_cache()

        # Verify cache is empty
        stats_after = processor.get_tags_stats()
        assert stats_after["cache_size"] == 0


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
