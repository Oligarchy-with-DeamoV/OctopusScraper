"""
Unit tests for LLM Keywords Processor.

This module contains comprehensive tests for the LLMKeywordsProcessor,
including keyword extraction, phrase detection, and error handling.
"""

import os
import sys
from unittest.mock import Mock, patch

import pytest

# Add src to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from octopus_scraper.llm.client import LLMResponse
from octopus_scraper.processors.llm_keywords_processor import LLMKeywordsProcessor
from octopus_scraper.processors.llm_structured_helper import (
    StructuredLLMProcessorHelper,
)
from octopus_scraper.processors.processor_base import ProcessingError
from octopus_scraper.protos import Content


class TestLLMKeywordsProcessor:
    """Test cases for LLMKeywordsProcessor."""

    @pytest.fixture
    def sample_config(self):
        """Sample processor configuration."""
        return {
            "model_name": "gpt-3.5-turbo",
            "max_tokens": 1000,
            "temperature": 0.7,
            "timeout": 30,
            "retry_times": 3,
            "keywords_count": 5,
            "min_keyword_length": 2,
            "max_keyword_length": 20,
            "exclude_common_words": True,
            "include_phrases": True,
            "language_preference": "mixed",
            "priority": 100,
        }

    @pytest.fixture
    def sample_content(self):
        """Sample content for testing."""
        return Content(
            content_id="test_123",
            title="Artificial Intelligence in Healthcare Applications",
            link="https://example.com/test-article",
            summary="",
            content="Artificial intelligence and machine learning algorithms are transforming healthcare by improving diagnostic accuracy, personalizing treatment plans, and accelerating drug discovery. Deep learning models can analyze medical images with unprecedented precision.",
            published="2025-01-01",
            author="Test Author",
            keywords=None,
            tags=None,
        )

    @pytest.fixture
    def chinese_content(self):
        """Sample Chinese content for testing."""
        return Content(
            content_id="test_zh_123",
            title="人工智能在医疗领域的应用",
            link="https://example.com/test-zh-article",
            summary="",
            content="人工智能和机器学习算法正在通过提高诊断准确性、个性化治疗方案和加速药物发现来改变医疗保健。深度学习模型可以以前所未有的精度分析医学图像。",
            published="2025-01-01",
            author="测试作者",
            keywords=None,
            tags=None,
        )

    @patch("octopus_scraper.processors.llm_keywords_processor.LLMClient")
    def test_processor_initialization(self, mock_client_class, sample_config):
        """Test processor initialization."""
        mock_client = Mock()
        mock_client.health_check.return_value = True
        mock_client_class.return_value = mock_client

        processor = LLMKeywordsProcessor(sample_config)

        assert processor.name == "LLMKeywordsProcessor"
        assert processor.config.keywords_count == 5
        assert processor.config.language_preference == "mixed"
        mock_client_class.assert_called_once()

    def test_invalid_config(self):
        """Test initialization with invalid configuration."""
        invalid_config = {
            "model_name": "gpt-3.5-turbo",
            "keywords_count": -1,  # Invalid
            "priority": 100,
        }

        with pytest.raises(ProcessingError):
            LLMKeywordsProcessor(invalid_config)

    @patch("octopus_scraper.processors.llm_keywords_processor.LLMClient")
    def test_single_content_processing(
        self, mock_client_class, sample_config, sample_content
    ):
        """Test processing a single content item."""
        mock_llm_client = Mock()
        mock_llm_client.health_check.return_value = True
        mock_llm_client.generate.return_value = LLMResponse(
            success=True,
            content='{"keywords": ["artificial intelligence", "machine learning", "healthcare", "diagnostic accuracy", "drug discovery"], "phrases": ["deep learning models", "medical images"], "importance_scores": {"artificial intelligence": 0.95, "machine learning": 0.90, "healthcare": 0.85}}',
            metadata={"model": "gpt-3.5-turbo"},
        )
        mock_llm_client.extract_json_from_response.return_value = '{"keywords": ["artificial intelligence", "machine learning", "healthcare", "diagnostic accuracy", "drug discovery"], "phrases": ["deep learning models", "medical images"], "importance_scores": {"artificial intelligence": 0.95, "machine learning": 0.90, "healthcare": 0.85}}'
        mock_client_class.return_value = mock_llm_client

        processor = LLMKeywordsProcessor(sample_config)
        result = processor([sample_content])

        assert len(result) == 1
        assert result[0].content_id == sample_content.content_id
        assert result[0].keywords is not None
        assert len(result[0].keywords) <= 5
        assert (
            "artificial intelligence" in result[0].keywords
            or "machine learning" in result[0].keywords
        )

    @patch("octopus_scraper.processors.llm_keywords_processor.LLMClient")
    def test_chinese_content_processing(
        self, mock_client_class, sample_config, chinese_content
    ):
        """Test processing Chinese content."""
        mock_llm_client = Mock()
        mock_llm_client.health_check.return_value = True
        mock_llm_client.generate.return_value = LLMResponse(
            success=True,
            content='{"keywords": ["人工智能", "机器学习", "医疗保健", "诊断准确性", "药物发现"], "phrases": ["深度学习模型", "医学图像"]}',
            metadata={"model": "gpt-3.5-turbo"},
        )
        mock_llm_client.extract_json_from_response.return_value = '{"keywords": ["人工智能", "机器学习", "医疗保健", "诊断准确性", "药物发现"], "phrases": ["深度学习模型", "医学图像"]}'
        mock_client_class.return_value = mock_llm_client

        processor = LLMKeywordsProcessor(sample_config)
        result = processor([chinese_content])

        assert len(result) == 1
        assert result[0].keywords is not None
        assert len(result[0].keywords) > 0
        # Should contain Chinese keywords
        assert any(
            "人工智能" in keyword or "机器学习" in keyword or "医疗" in keyword
            for keyword in result[0].keywords
        )

    @patch("octopus_scraper.processors.llm_keywords_processor.LLMClient")
    def test_phrase_inclusion(self, mock_client_class, sample_content):
        """Test including phrases in keywords."""
        config_with_phrases = {
            "model_name": "gpt-3.5-turbo",
            "max_tokens": 1000,
            "temperature": 0.7,
            "timeout": 30,
            "retry_times": 3,
            "keywords_count": 5,
            "min_keyword_length": 2,
            "max_keyword_length": 20,
            "exclude_common_words": True,
            "include_phrases": True,
            "language_preference": "en",
            "priority": 100,
        }

        mock_llm_client = Mock()
        mock_llm_client.health_check.return_value = True
        mock_llm_client.generate.return_value = LLMResponse(
            success=True,
            content='{"keywords": ["AI", "healthcare"], "phrases": ["machine learning algorithms", "diagnostic accuracy"]}',
            metadata={"model": "gpt-3.5-turbo"},
        )
        mock_llm_client.extract_json_from_response.return_value = '{"keywords": ["AI", "healthcare"], "phrases": ["machine learning algorithms", "diagnostic accuracy"]}'
        mock_client_class.return_value = mock_llm_client

        processor = LLMKeywordsProcessor(config_with_phrases)
        result = processor([sample_content])

        assert len(result) == 1
        keywords = result[0].keywords
        # Should include both keywords and phrases
        assert "AI" in keywords or "healthcare" in keywords
        assert any("machine learning" in kw for kw in keywords) or any(
            "diagnostic" in kw for kw in keywords
        )

    @patch("octopus_scraper.processors.llm_keywords_processor.LLMClient")
    def test_exclude_phrases(self, mock_client_class, sample_content):
        """Test excluding phrases from keywords."""
        config_no_phrases = {
            "model_name": "gpt-3.5-turbo",
            "max_tokens": 1000,
            "temperature": 0.7,
            "timeout": 30,
            "retry_times": 3,
            "keywords_count": 3,
            "min_keyword_length": 2,
            "max_keyword_length": 20,
            "exclude_common_words": True,
            "include_phrases": False,
            "language_preference": "en",
            "priority": 100,
        }

        mock_llm_client = Mock()
        mock_llm_client.health_check.return_value = True
        mock_llm_client.generate.return_value = LLMResponse(
            success=True,
            content='{"keywords": ["AI", "healthcare", "medicine"], "phrases": ["should not be included"]}',
            metadata={"model": "gpt-3.5-turbo"},
        )
        mock_llm_client.extract_json_from_response.return_value = '{"keywords": ["AI", "healthcare", "medicine"], "phrases": ["should not be included"]}'
        mock_client_class.return_value = mock_llm_client

        processor = LLMKeywordsProcessor(config_no_phrases)
        result = processor([sample_content])

        assert len(result) == 1
        keywords = result[0].keywords
        # Should not include phrases
        assert "should not be included" not in keywords
        assert len(keywords) == 3

    @patch("octopus_scraper.processors.llm_keywords_processor.LLMClient")
    def test_common_words_filtering(
        self, mock_client_class, sample_config, sample_content
    ):
        """Test filtering of common stop words."""
        mock_llm_client = Mock()
        mock_llm_client.health_check.return_value = True
        mock_llm_client.generate.return_value = LLMResponse(
            success=True,
            content='{"keywords": ["the", "is", "AI", "healthcare", "with"], "importance_scores": {"the": 0.1, "is": 0.1, "AI": 0.9, "healthcare": 0.8, "with": 0.2}}',
            metadata={"model": "gpt-3.5-turbo"},
        )
        mock_llm_client.extract_json_from_response.return_value = '{"keywords": ["the", "is", "AI", "healthcare", "with"], "importance_scores": {"the": 0.1, "is": 0.1, "AI": 0.9, "healthcare": 0.8, "with": 0.2}}'
        mock_client_class.return_value = mock_llm_client

        processor = LLMKeywordsProcessor(sample_config)
        result = processor([sample_content])

        assert len(result) == 1
        keywords = result[0].keywords
        # Common words should be filtered out
        assert "the" not in keywords
        assert "is" not in keywords
        assert "with" not in keywords
        # Important words should remain
        assert "AI" in keywords or "healthcare" in keywords

    @patch("octopus_scraper.processors.llm_keywords_processor.LLMClient")
    def test_keyword_length_filtering(self, mock_client_class, sample_content):
        """Test filtering keywords by length."""
        config_length_filter = {
            "model_name": "gpt-3.5-turbo",
            "max_tokens": 1000,
            "temperature": 0.7,
            "timeout": 30,
            "retry_times": 3,
            "keywords_count": 5,
            "min_keyword_length": 3,  # Minimum 3 characters
            "max_keyword_length": 10,  # Maximum 10 characters
            "exclude_common_words": False,
            "include_phrases": True,
            "language_preference": "en",
            "priority": 100,
        }

        mock_llm_client = Mock()
        mock_llm_client.health_check.return_value = True
        mock_llm_client.generate.return_value = LLMResponse(
            success=True,
            content='{"keywords": ["AI", "healthcare", "verylongkeywordthatexceedslimit", "ok"]}',
            metadata={"model": "gpt-3.5-turbo"},
        )
        mock_llm_client.extract_json_from_response.return_value = '{"keywords": ["AI", "healthcare", "verylongkeywordthatexceedslimit", "ok"]}'
        mock_client_class.return_value = mock_llm_client

        processor = LLMKeywordsProcessor(config_length_filter)
        result = processor([sample_content])

        assert len(result) == 1
        keywords = result[0].keywords
        # Short keywords should be filtered out
        assert "AI" not in keywords  # Too short (2 chars < 3)
        assert "ok" not in keywords  # Too short (2 chars < 3)
        # Long keywords should be filtered out
        assert "verylongkeywordthatexceedslimit" not in keywords  # Too long
        # Valid length keywords should remain
        assert "healthcare" in keywords

    @patch("octopus_scraper.processors.llm_keywords_processor.LLMClient")
    def test_llm_error_handling(self, mock_client_class, sample_config, sample_content):
        """Test handling LLM errors gracefully."""
        mock_client = Mock()
        mock_client.health_check.return_value = True
        mock_client.generate.return_value = LLMResponse(
            success=False, error="API Error: Rate limit exceeded"
        )
        mock_client_class.return_value = mock_client

        processor = LLMKeywordsProcessor(sample_config)
        result = processor([sample_content])

        assert len(result) == 1
        assert result[0].keywords is not None  # Should have fallback keywords
        assert len(result[0].keywords) > 0

    @patch("octopus_scraper.processors.llm_keywords_processor.LLMClient")
    def test_fallback_keywords_creation(self, mock_client_class, sample_config):
        """Test fallback keyword creation when LLM fails."""
        mock_llm_client = Mock()
        mock_llm_client.health_check.return_value = True
        mock_llm_client.generate.return_value = LLMResponse(
            success=False, error="Network error"
        )
        mock_client_class.return_value = mock_llm_client

        processor = LLMKeywordsProcessor(sample_config)

        content = Content(
            content_id="fallback_test",
            title="Machine Learning Applications",
            link="https://example.com/ml-apps",
            summary="",
            content="Machine learning algorithms are used in various applications including natural language processing and computer vision.",
            published="2025-01-01",
            author="ML Expert",
            keywords=None,
            tags=None,
        )

        result = processor([content])

        assert len(result) == 1
        assert result[0].keywords is not None
        assert len(result[0].keywords) > 0
        # Should contain fallback keywords derived from title/content

    @patch("octopus_scraper.processors.llm_keywords_processor.LLMClient")
    def test_cache_functionality(
        self, mock_client_class, sample_config, sample_content
    ):
        """Test caching of generated keywords."""
        mock_llm_client = Mock()
        mock_llm_client.health_check.return_value = True
        mock_llm_client.generate.return_value = LLMResponse(
            success=True,
            content='{"keywords": ["cached", "keywords"]}',
            metadata={"model": "gpt-3.5-turbo"},
        )
        mock_llm_client.extract_json_from_response.return_value = (
            '{"keywords": ["cached", "keywords"]}'
        )
        mock_client_class.return_value = mock_llm_client

        processor = LLMKeywordsProcessor(sample_config)

        # First call should trigger LLM
        result1 = processor([sample_content])

        # Second call with same content should use cache
        result2 = processor([sample_content])

        assert len(result1) == 1
        assert len(result2) == 1
        assert result1[0].keywords == result2[0].keywords

        # LLM should only be called once (cached second time)
        assert mock_llm_client.generate.call_count == 1

    @patch("octopus_scraper.processors.llm_keywords_processor.LLMClient")
    def test_cache_key_uses_full_content_not_content_length(
        self, mock_client_class, sample_config, sample_content
    ):
        """Test same-title, same-length content produces distinct stable cache keys."""
        mock_llm_client = Mock()
        mock_llm_client.health_check.return_value = True
        mock_client_class.return_value = mock_llm_client

        processor = LLMKeywordsProcessor(sample_config)
        other_content = Content(
            content_id="same_length",
            title=sample_content.title,
            link=sample_content.link,
            summary=sample_content.summary,
            content="B" * len(sample_content.content),
            published=sample_content.published,
            author=sample_content.author,
            keywords=None,
            tags=None,
        )

        first_key = processor._generate_cache_key(sample_content)
        second_key = processor._generate_cache_key(other_content)

        assert first_key != second_key
        assert first_key == processor._generate_cache_key(sample_content)
        assert len(first_key) == 64

    def test_structured_helper_raises_on_failed_llm_response(self):
        """Test shared structured helper surfaces LLM failures."""
        llm_client = Mock()
        llm_client.generate.return_value = LLMResponse(
            success=False,
            error="rate limit",
        )
        validator = Mock()

        with pytest.raises(ProcessingError, match="rate limit"):
            StructuredLLMProcessorHelper.generate_structured_data(
                llm_client=llm_client,
                validator=validator,
                messages=[],
                schema={},
                fix_response=lambda data: data,
                invalid_schema_event="invalid",
            )

    def test_structured_helper_repairs_invalid_schema_response(self):
        """Test shared structured helper repairs JSON that fails schema validation."""
        llm_client = Mock()
        llm_client.generate.return_value = LLMResponse(
            success=True,
            content='{"keyword": "AI"}',
        )
        llm_client.extract_json_from_response.return_value = '{"keyword": "AI"}'
        validator = Mock()
        validator.validate_json.return_value = False

        result = StructuredLLMProcessorHelper.generate_structured_data(
            llm_client=llm_client,
            validator=validator,
            messages=[],
            schema={"type": "object"},
            fix_response=lambda data: {"keywords": [data["keyword"]]},
            invalid_schema_event="invalid keywords",
        )

        assert result == {"keywords": ["AI"]}

    @patch("octopus_scraper.processors.llm_keywords_processor.LLMClient")
    def test_health_check(self, mock_client_class, sample_config):
        """Test processor health check."""
        mock_llm_client = Mock()
        mock_llm_client.health_check.return_value = True
        mock_client_class.return_value = mock_llm_client

        processor = LLMKeywordsProcessor(sample_config)

        assert processor.health_check() is True

        # Test unhealthy state
        mock_llm_client.health_check.return_value = False
        assert processor.health_check() is False

    @patch("octopus_scraper.processors.llm_keywords_processor.LLMClient")
    def test_get_keywords_stats(self, mock_client_class, sample_config):
        """Test getting processor statistics."""
        mock_llm_client = Mock()
        mock_client_class.return_value = mock_llm_client

        processor = LLMKeywordsProcessor(sample_config)
        stats = processor.get_keywords_stats()

        assert stats["processor_name"] == "LLMKeywordsProcessor"
        assert stats["model_name"] == "gpt-3.5-turbo"
        assert stats["keywords_count"] == 5
        assert stats["language_preference"] == "mixed"
        assert "cache_size" in stats
        assert "config" in stats

    @patch("octopus_scraper.processors.llm_keywords_processor.LLMClient")
    def test_clear_cache(self, mock_client_class, sample_config, sample_content):
        """Test clearing the keywords cache."""
        mock_llm_client = Mock()
        mock_llm_client.health_check.return_value = True
        mock_llm_client.generate.return_value = LLMResponse(
            success=True,
            content='{"keywords": ["test", "keywords"]}',
            metadata={"model": "gpt-3.5-turbo"},
        )
        mock_llm_client.extract_json_from_response.return_value = (
            '{"keywords": ["test", "keywords"]}'
        )
        mock_client_class.return_value = mock_llm_client

        processor = LLMKeywordsProcessor(sample_config)

        # Generate some cached data
        processor([sample_content])

        # Verify cache has content
        stats_before = processor.get_keywords_stats()
        assert stats_before["cache_size"] > 0

        # Clear cache
        processor.clear_cache()

        # Verify cache is empty
        stats_after = processor.get_keywords_stats()
        assert stats_after["cache_size"] == 0


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
