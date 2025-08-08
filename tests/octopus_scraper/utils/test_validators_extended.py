"""
Comprehensive tests for data validation utilities.
"""

import json
import os
import sys

import pytest

# Add src to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from octopus_scraper.utils.validators import (
    DataValidator,
    ValidationError,
    validate_json_schema,
)


class TestDataValidator:
    """Test cases for DataValidator utility methods."""

    def test_validate_json_schema_valid_dict(self):
        """Test JSON schema validation with valid dictionary."""
        data = {"name": "John", "age": 30}
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "number"}},
            "required": ["name", "age"],
        }

        is_valid, error = DataValidator.validate_json_schema(data, schema)

        assert is_valid is True
        assert error is None

    def test_validate_json_schema_invalid_dict(self):
        """Test JSON schema validation with invalid dictionary."""
        data = {"name": "John", "age": "thirty"}  # age should be number
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "number"}},
            "required": ["name", "age"],
        }

        is_valid, error = DataValidator.validate_json_schema(data, schema)

        assert is_valid is False
        assert error is not None
        assert "validation" in error.lower()  # More flexible error message check

    def test_validate_json_schema_valid_json_string(self):
        """Test JSON schema validation with valid JSON string."""
        data = '{"name": "John", "age": 30}'
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "number"}},
        }

        is_valid, error = DataValidator.validate_json_schema(data, schema)

        assert is_valid is True
        assert error is None

    def test_validate_json_schema_invalid_json_string(self):
        """Test JSON schema validation with invalid JSON string."""
        data = '{"name": "John", "age":}'  # Invalid JSON
        schema = {"type": "object"}

        is_valid, error = DataValidator.validate_json_schema(data, schema)

        assert is_valid is False
        assert error is not None
        assert "Invalid JSON" in error

    def test_validate_json_schema_missing_required(self):
        """Test JSON schema validation with missing required field."""
        data = {"name": "John"}  # Missing required age
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "number"}},
            "required": ["name", "age"],
        }

        is_valid, error = DataValidator.validate_json_schema(data, schema)

        assert is_valid is False
        assert error is not None

    def test_validate_content_structure_valid(self):
        """Test content structure validation with valid content."""
        content = {
            "content_id": "test_123",
            "title": "Test Title",
            "link": "https://example.com/test",
            "content": "Test content body",
            "published": "2025-01-01",
        }

        is_valid, error = DataValidator.validate_content_structure(content)

        assert is_valid is True
        assert error is None

    def test_validate_content_structure_missing_field(self):
        """Test content structure validation with missing required field."""
        content = {
            "content_id": "test_123",
            "title": "Test Title",
            # Missing required 'link' field
            "content": "Test content body",
            "published": "2025-01-01",
        }

        is_valid, error = DataValidator.validate_content_structure(content)

        assert is_valid is False
        assert error is not None
        assert "Missing required field: link" in error

    def test_validate_content_structure_empty_field(self):
        """Test content structure validation with empty required field."""
        content = {
            "content_id": "test_123",
            "title": "",  # Empty title
            "link": "https://example.com/test",
            "content": "Test content body",
            "published": "2025-01-01",
        }

        is_valid, error = DataValidator.validate_content_structure(content)

        assert is_valid is False
        assert error is not None
        assert "Empty required field: title" in error

    def test_validate_content_structure_invalid_url(self):
        """Test content structure validation with invalid URL."""
        content = {
            "content_id": "test_123",
            "title": "Test Title",
            "link": "not-a-valid-url",
            "content": "Test content body",
            "published": "2025-01-01",
        }

        is_valid, error = DataValidator.validate_content_structure(content)

        assert is_valid is False
        assert error is not None
        assert "link must be a valid URL" in error

    def test_validate_content_structure_invalid_field_type(self):
        """Test content structure validation with invalid field type."""
        content = {
            "content_id": 123,  # Should be string
            "title": "Test Title",
            "link": "https://example.com/test",
            "content": "Test content body",
            "published": "2025-01-01",
        }

        is_valid, error = DataValidator.validate_content_structure(content)

        assert is_valid is False
        assert error is not None
        assert "content_id must be a string" in error

    def test_validate_content_structure_with_valid_keywords(self):
        """Test content structure validation with valid keywords."""
        content = {
            "content_id": "test_123",
            "title": "Test Title",
            "link": "https://example.com/test",
            "content": "Test content body",
            "published": "2025-01-01",
            "keywords": ["keyword1", "keyword2"],
        }

        is_valid, error = DataValidator.validate_content_structure(content)

        assert is_valid is True
        assert error is None

    def test_validate_content_structure_with_invalid_keywords(self):
        """Test content structure validation with invalid keywords."""
        content = {
            "content_id": "test_123",
            "title": "Test Title",
            "link": "https://example.com/test",
            "content": "Test content body",
            "published": "2025-01-01",
            "keywords": "not-a-list",  # Should be list
        }

        is_valid, error = DataValidator.validate_content_structure(content)

        assert is_valid is False
        assert error is not None
        assert "keywords must be a list" in error

    def test_validate_content_structure_with_invalid_keyword_types(self):
        """Test content structure validation with invalid keyword types."""
        content = {
            "content_id": "test_123",
            "title": "Test Title",
            "link": "https://example.com/test",
            "content": "Test content body",
            "published": "2025-01-01",
            "keywords": ["valid", 123, "another"],  # 123 is not string
        }

        is_valid, error = DataValidator.validate_content_structure(content)

        assert is_valid is False
        assert error is not None
        assert "all keywords must be strings" in error

    def test_validate_processor_config_valid_basic(self):
        """Test processor config validation with valid basic config."""
        config = {
            "priority": 100,
            "model_name": "gpt-3.5-turbo",
            "max_tokens": 1000,
            "temperature": 0.7,
        }

        is_valid, error = DataValidator.validate_processor_config(config, "summary")

        assert is_valid is True
        assert error is None

    def test_validate_processor_config_invalid_priority(self):
        """Test processor config validation with invalid priority."""
        config = {
            "priority": -1,  # Should be non-negative
            "model_name": "gpt-3.5-turbo",
        }

        is_valid, error = DataValidator.validate_processor_config(config, "summary")

        assert is_valid is False
        assert error is not None
        assert "priority must be a non-negative integer" in error

    def test_validate_processor_config_invalid_model_name(self):
        """Test processor config validation with invalid model name."""
        config = {"model_name": "", "max_tokens": 1000}  # Empty model name

        is_valid, error = DataValidator.validate_processor_config(config, "summary")

        assert is_valid is False
        assert error is not None
        assert "model_name must be a non-empty string" in error

    def test_validate_processor_config_invalid_temperature(self):
        """Test processor config validation with invalid temperature."""
        config = {
            "model_name": "gpt-3.5-turbo",
            "temperature": 3.0,  # Should be between 0 and 2
        }

        is_valid, error = DataValidator.validate_processor_config(config, "summary")

        assert is_valid is False
        assert error is not None
        assert "temperature must be a number between 0 and 2" in error

    def test_validate_summary_config_valid(self):
        """Test summary processor config validation."""
        config = {"max_summary_length": 200, "summary_style": "concise"}

        is_valid, error = DataValidator._validate_summary_config(config)

        assert is_valid is True
        assert error is None

    def test_validate_summary_config_invalid_length(self):
        """Test summary processor config validation with invalid length."""
        config = {"max_summary_length": -100}  # Should be positive

        is_valid, error = DataValidator._validate_summary_config(config)

        assert is_valid is False
        assert error is not None
        assert "max_summary_length must be a positive integer" in error

    def test_validate_summary_config_invalid_style(self):
        """Test summary processor config validation with invalid style."""
        config = {"summary_style": "invalid_style"}

        is_valid, error = DataValidator._validate_summary_config(config)

        assert is_valid is False
        assert error is not None
        assert "summary_style must be one of" in error

    def test_validate_tags_config_valid(self):
        """Test tags processor config validation."""
        config = {
            "available_tags": ["tag1", "tag2"],
            "max_tags_count": 5,
            "custom_categories": {
                "tech": ["ai", "ml"],
                "science": ["physics", "chemistry"],
            },
        }

        is_valid, error = DataValidator._validate_tags_config(config)

        assert is_valid is True
        assert error is None

    def test_validate_tags_config_invalid_available_tags(self):
        """Test tags processor config validation with invalid available tags."""
        config = {"available_tags": "not-a-list"}  # Should be list

        is_valid, error = DataValidator._validate_tags_config(config)

        assert is_valid is False
        assert error is not None
        assert "available_tags must be a list" in error

    def test_validate_keywords_config_valid(self):
        """Test keywords processor config validation."""
        config = {
            "keywords_count": 10,
            "min_keyword_length": 3,
            "exclude_common_words": True,
        }

        is_valid, error = DataValidator._validate_keywords_config(config)

        assert is_valid is True
        assert error is None

    def test_validate_keywords_config_invalid_count(self):
        """Test keywords processor config validation with invalid count."""
        config = {"keywords_count": 0}  # Should be positive

        is_valid, error = DataValidator._validate_keywords_config(config)

        assert is_valid is False
        assert error is not None
        assert "keywords_count must be a positive integer" in error

    def test_validate_llm_response_format_text(self):
        """Test LLM response format validation for text."""
        response = "This is a valid text response."

        is_valid, error = DataValidator.validate_llm_response_format(response, "text")

        assert is_valid is True
        assert error is None

    def test_validate_llm_response_format_json_valid(self):
        """Test LLM response format validation for valid JSON."""
        response = '{"key": "value", "number": 123}'

        is_valid, error = DataValidator.validate_llm_response_format(response, "json")

        assert is_valid is True
        assert error is None

    def test_validate_llm_response_format_json_invalid(self):
        """Test LLM response format validation for invalid JSON."""
        response = '{"key": "value", "number":}'  # Invalid JSON

        is_valid, error = DataValidator.validate_llm_response_format(response, "json")

        assert is_valid is False
        assert error is not None
        assert "Invalid JSON format" in error

    def test_validate_llm_response_format_list_valid(self):
        """Test LLM response format validation for valid list format."""
        response = "1. First item\n2. Second item\n- Third item"

        is_valid, error = DataValidator.validate_llm_response_format(response, "list")

        assert is_valid is True
        assert error is None

    def test_validate_llm_response_format_list_invalid(self):
        """Test LLM response format validation for invalid list format."""
        response = "This is just text without list indicators"

        is_valid, error = DataValidator.validate_llm_response_format(response, "list")

        assert is_valid is False
        assert error is not None
        assert "does not contain list format indicators" in error

    def test_validate_llm_response_format_empty(self):
        """Test LLM response format validation with empty response."""
        is_valid, error = DataValidator.validate_llm_response_format("", "text")

        assert is_valid is False
        assert error is not None
        assert "Empty response" in error

    def test_sanitize_text_input_basic(self):
        """Test basic text input sanitization."""
        text = "Normal text with some content."
        result = DataValidator.sanitize_text_input(text)

        assert result == text

    def test_sanitize_text_input_with_control_chars(self):
        """Test text input sanitization with control characters."""
        text = "Text with\x00control\x01chars\x02here"
        result = DataValidator.sanitize_text_input(text)

        assert "\x00" not in result
        assert "\x01" not in result
        assert "\x02" not in result
        assert "Text with" in result
        assert "controlcharshere" in result

    def test_sanitize_text_input_preserve_newlines_tabs(self):
        """Test text input sanitization preserves newlines and tabs."""
        text = "Text with\nnewlines\tand\ttabs"
        result = DataValidator.sanitize_text_input(text)

        assert "\n" in result
        assert "\t" in result

    def test_sanitize_text_input_max_length(self):
        """Test text input sanitization with max length."""
        text = "This is a very long text that should be truncated"
        result = DataValidator.sanitize_text_input(text, max_length=20)

        assert len(result) <= 20
        assert "This is a very long" in result

    def test_sanitize_text_input_empty(self):
        """Test text input sanitization with empty input."""
        assert DataValidator.sanitize_text_input("") == ""
        assert DataValidator.sanitize_text_input(None) == ""

    def test_validate_tag_list_valid(self):
        """Test tag list validation with valid tags."""
        tags = ["tech", "ai", "machine learning"]

        is_valid, error = DataValidator.validate_tag_list(tags)

        assert is_valid is True
        assert error is None

    def test_validate_tag_list_too_many(self):
        """Test tag list validation with too many tags."""
        tags = ["tag" + str(i) for i in range(15)]  # More than default max

        is_valid, error = DataValidator.validate_tag_list(tags, max_tags=10)

        assert is_valid is False
        assert error is not None
        assert "Too many tags" in error

    def test_validate_tag_list_too_long(self):
        """Test tag list validation with too long tags."""
        tags = ["a" * 100]  # Very long tag

        is_valid, error = DataValidator.validate_tag_list(tags, max_tag_length=50)

        assert is_valid is False
        assert error is not None
        assert "too long" in error

    def test_validate_tag_list_invalid_characters(self):
        """Test tag list validation with invalid characters."""
        tags = ["valid_tag", "invalid<tag>"]

        is_valid, error = DataValidator.validate_tag_list(tags)

        assert is_valid is False
        assert error is not None
        assert "invalid characters" in error

    def test_validate_tag_list_empty_tag(self):
        """Test tag list validation with empty tag."""
        tags = ["valid_tag", ""]

        is_valid, error = DataValidator.validate_tag_list(tags)

        assert is_valid is False
        assert error is not None
        assert "is empty" in error

    def test_validate_tag_list_not_list(self):
        """Test tag list validation with non-list input."""
        tags = "not_a_list"

        is_valid, error = DataValidator.validate_tag_list(tags)

        assert is_valid is False
        assert error is not None
        assert "Tags must be a list" in error

    def test_validate_keyword_list_valid(self):
        """Test keyword list validation with valid keywords."""
        keywords = ["machine learning", "artificial intelligence", "deep learning"]

        is_valid, error = DataValidator.validate_keyword_list(keywords)

        assert is_valid is True
        assert error is None

    def test_validate_keyword_list_too_many(self):
        """Test keyword list validation with too many keywords."""
        keywords = ["keyword" + str(i) for i in range(15)]

        is_valid, error = DataValidator.validate_keyword_list(keywords, max_keywords=10)

        assert is_valid is False
        assert error is not None
        assert "Too many keywords" in error

    def test_validate_keyword_list_too_short(self):
        """Test keyword list validation with too short keywords."""
        keywords = ["ml", "a"]  # Too short

        is_valid, error = DataValidator.validate_keyword_list(
            keywords, min_keyword_length=3
        )

        assert is_valid is False
        assert error is not None
        assert "too short" in error

    def test_validate_keyword_list_invalid_characters(self):
        """Test keyword list validation with invalid characters."""
        keywords = ["valid keyword", "invalid@keyword"]

        is_valid, error = DataValidator.validate_keyword_list(keywords)

        assert is_valid is False
        assert error is not None
        assert "invalid characters" in error

    def test_validate_keyword_list_not_list(self):
        """Test keyword list validation with non-list input."""
        keywords = {"not": "a_list"}

        is_valid, error = DataValidator.validate_keyword_list(keywords)

        assert is_valid is False
        assert error is not None
        assert "Keywords must be a list" in error


class TestValidationError:
    """Test cases for ValidationError exception."""

    def test_validation_error_creation(self):
        """Test ValidationError creation."""
        error = ValidationError("Test validation error")

        assert str(error) == "Test validation error"
        assert isinstance(error, Exception)


class TestGlobalValidationFunction:
    """Test cases for global validation function."""

    def test_validate_json_schema_function(self):
        """Test global validate_json_schema function."""
        data = {"test": "value"}
        schema = {"type": "object", "properties": {"test": {"type": "string"}}}

        is_valid, error = validate_json_schema(data, schema)

        assert is_valid is True
        assert error is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
