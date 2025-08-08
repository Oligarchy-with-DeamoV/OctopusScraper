"""
Data validation utilities for OctopusScraper.

This module provides validation functions for various data types,
including JSON schema validation, content validation, and configuration validation.
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple, Union

import structlog
from jsonschema import ValidationError, draft7_format_checker, validate

logger = structlog.getLogger(__name__)


class ValidationError(Exception):
    """Custom validation error."""

    pass


class DataValidator:
    """Data validation utilities."""

    @staticmethod
    def validate_json_schema(
        data: Union[Dict[str, Any], str], schema: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate data against a JSON schema.

        Args:
            data: Data to validate (dict or JSON string)
            schema: JSON schema to validate against

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Parse JSON string if needed
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except json.JSONDecodeError as e:
                    return False, f"Invalid JSON: {str(e)}"

            # Validate against schema
            validate(instance=data, schema=schema, format_checker=draft7_format_checker)
            return True, None

        except ValidationError as e:
            return False, f"Schema validation error: {e.message}"
        except Exception as e:
            return False, f"Validation error: {str(e)}"

    @staticmethod
    def validate_json(
        data: Union[Dict[str, Any], str], schema: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate JSON data against a schema (alias for validate_json_schema).

        Args:
            data: Data to validate (dict or JSON string)
            schema: JSON schema to validate against

        Returns:
            Tuple of (is_valid, error_message)
        """
        return DataValidator.validate_json_schema(data, schema)

    @staticmethod
    def validate_content_structure(
        content: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate content structure.

        Args:
            content: Content dictionary to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        required_fields = ["content_id", "title", "link", "content", "published"]

        for field in required_fields:
            if field not in content:
                return False, f"Missing required field: {field}"

            if not content[field] or not str(content[field]).strip():
                return False, f"Empty required field: {field}"

        # Validate field types
        if not isinstance(content.get("content_id"), str):
            return False, "content_id must be a string"

        if not isinstance(content.get("title"), str):
            return False, "title must be a string"

        if not isinstance(content.get("link"), str):
            return False, "link must be a string"

        # Validate URL format
        url_pattern = r"^https?://[^\s]+$"
        if not re.match(url_pattern, content["link"]):
            return False, "link must be a valid URL"

        # Validate optional fields
        if "keywords" in content and content["keywords"] is not None:
            if not isinstance(content["keywords"], list):
                return False, "keywords must be a list"
            if not all(isinstance(k, str) for k in content["keywords"]):
                return False, "all keywords must be strings"

        if "tags" in content and content["tags"] is not None:
            if not isinstance(content["tags"], list):
                return False, "tags must be a list"
            if not all(isinstance(t, str) for t in content["tags"]):
                return False, "all tags must be strings"

        return True, None

    @staticmethod
    def validate_processor_config(
        config: Dict[str, Any], processor_type: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate processor configuration.

        Args:
            config: Configuration dictionary
            processor_type: Type of processor ("summary", "tags", "keywords")

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Common validation for all processors
        if "priority" in config:
            if not isinstance(config["priority"], int) or config["priority"] < 0:
                return False, "priority must be a non-negative integer"

        # LLM processor specific validation
        llm_configs = [
            "model_name",
            "max_tokens",
            "temperature",
            "timeout",
            "retry_times",
        ]

        for field in llm_configs:
            if field in config:
                if field == "model_name":
                    if not isinstance(config[field], str) or not config[field].strip():
                        return False, f"{field} must be a non-empty string"

                elif field in ["max_tokens", "timeout", "retry_times"]:
                    if not isinstance(config[field], int) or config[field] <= 0:
                        return False, f"{field} must be a positive integer"

                elif field == "temperature":
                    if (
                        not isinstance(config[field], (int, float))
                        or not 0 <= config[field] <= 2
                    ):
                        return False, f"{field} must be a number between 0 and 2"

        # Processor-specific validation
        if processor_type == "summary":
            return DataValidator._validate_summary_config(config)
        elif processor_type == "tags":
            return DataValidator._validate_tags_config(config)
        elif processor_type == "keywords":
            return DataValidator._validate_keywords_config(config)

        return True, None

    @staticmethod
    def _validate_summary_config(config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate summary processor configuration."""
        if "max_summary_length" in config:
            if (
                not isinstance(config["max_summary_length"], int)
                or config["max_summary_length"] <= 0
            ):
                return False, "max_summary_length must be a positive integer"

        if "summary_style" in config:
            valid_styles = ["concise", "detailed", "bullet_points", "executive"]
            if config["summary_style"] not in valid_styles:
                return False, f"summary_style must be one of: {valid_styles}"

        return True, None

    @staticmethod
    def _validate_tags_config(config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate tags processor configuration."""
        if "available_tags" in config:
            if not isinstance(config["available_tags"], list):
                return False, "available_tags must be a list"
            if not all(isinstance(tag, str) for tag in config["available_tags"]):
                return False, "all available_tags must be strings"

        if "max_tags_count" in config:
            if (
                not isinstance(config["max_tags_count"], int)
                or config["max_tags_count"] <= 0
            ):
                return False, "max_tags_count must be a positive integer"

        if "custom_categories" in config:
            if not isinstance(config["custom_categories"], dict):
                return False, "custom_categories must be a dictionary"
            for category, tags in config["custom_categories"].items():
                if not isinstance(category, str):
                    return False, "custom_categories keys must be strings"
                if not isinstance(tags, list):
                    return False, "custom_categories values must be lists"
                if not all(isinstance(tag, str) for tag in tags):
                    return False, "all tags in custom_categories must be strings"

        return True, None

    @staticmethod
    def _validate_keywords_config(config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate keywords processor configuration."""
        if "keywords_count" in config:
            if (
                not isinstance(config["keywords_count"], int)
                or config["keywords_count"] <= 0
            ):
                return False, "keywords_count must be a positive integer"

        if "min_keyword_length" in config:
            if (
                not isinstance(config["min_keyword_length"], int)
                or config["min_keyword_length"] <= 0
            ):
                return False, "min_keyword_length must be a positive integer"

        if "exclude_common_words" in config:
            if not isinstance(config["exclude_common_words"], bool):
                return False, "exclude_common_words must be a boolean"

        return True, None

    @staticmethod
    def validate_llm_response_format(
        response: str, expected_format: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate LLM response format.

        Args:
            response: LLM response to validate
            expected_format: Expected format ("text", "json", "list")

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not response or not response.strip():
            return False, "Empty response"

        if expected_format == "json":
            try:
                json.loads(response)
                return True, None
            except json.JSONDecodeError as e:
                return False, f"Invalid JSON format: {str(e)}"

        elif expected_format == "list":
            # Check for list indicators
            list_indicators = ["-", "•", "1.", "2.", "3.", "*", "–"]
            if not any(indicator in response for indicator in list_indicators):
                return False, "Response does not contain list format indicators"

        # For "text" format, any non-empty response is valid
        return True, None

    @staticmethod
    def sanitize_text_input(text: str, max_length: Optional[int] = None) -> str:
        """
        Sanitize text input by removing potentially harmful content.

        Args:
            text: Text to sanitize
            max_length: Maximum allowed length

        Returns:
            Sanitized text
        """
        if not text:
            return ""

        # Remove control characters except newlines and tabs
        sanitized = "".join(char for char in text if ord(char) >= 32 or char in "\n\t")

        # Limit length if specified
        if max_length and len(sanitized) > max_length:
            sanitized = sanitized[:max_length]

        return sanitized.strip()

    @staticmethod
    def validate_tag_list(
        tags: List[str], max_tags: int = 10, max_tag_length: int = 50
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate a list of tags.

        Args:
            tags: List of tags to validate
            max_tags: Maximum number of tags allowed
            max_tag_length: Maximum length for each tag

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not isinstance(tags, list):
            return False, "Tags must be a list"

        if len(tags) > max_tags:
            return False, f"Too many tags: {len(tags)} > {max_tags}"

        for i, tag in enumerate(tags):
            if not isinstance(tag, str):
                return False, f"Tag {i} must be a string"

            if not tag.strip():
                return False, f"Tag {i} is empty"

            if len(tag) > max_tag_length:
                return False, f"Tag {i} too long: {len(tag)} > {max_tag_length}"

            # Check for invalid characters
            if re.search(r'[<>{}"\']', tag):
                return False, f"Tag {i} contains invalid characters"

        return True, None

    @staticmethod
    def validate_keyword_list(
        keywords: List[str], max_keywords: int = 10, min_keyword_length: int = 2
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate a list of keywords.

        Args:
            keywords: List of keywords to validate
            max_keywords: Maximum number of keywords allowed
            min_keyword_length: Minimum length for each keyword

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not isinstance(keywords, list):
            return False, "Keywords must be a list"

        if len(keywords) > max_keywords:
            return False, f"Too many keywords: {len(keywords)} > {max_keywords}"

        for i, keyword in enumerate(keywords):
            if not isinstance(keyword, str):
                return False, f"Keyword {i} must be a string"

            if len(keyword.strip()) < min_keyword_length:
                return (
                    False,
                    f"Keyword {i} too short: must be at least {min_keyword_length} characters",
                )

            # Check for invalid characters (more restrictive than tags)
            if not re.match(r"^[\w\s\u4e00-\u9fff]+$", keyword):
                return False, f"Keyword {i} contains invalid characters"

        return True, None


# Convenience function for external use
def validate_json_schema(
    data: Union[Dict[str, Any], str], schema: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """
    Validate data against a JSON schema.

    This is a convenience function that calls DataValidator.validate_json_schema.

    Args:
        data: Data to validate
        schema: JSON schema

    Returns:
        Tuple of (is_valid, error_message)
    """
    return DataValidator.validate_json_schema(data, schema)
