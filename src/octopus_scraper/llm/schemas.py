"""
JSON schemas for LLM processor outputs.

This module defines JSON schemas used to validate structured outputs
from LLM processors, ensuring consistent data formats.
"""

from typing import Any, Dict

# Schema for tags processor output
TAGS_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "tags": {
            "type": "array",
            "items": {"type": "string", "minLength": 1, "maxLength": 50},
            "minItems": 1,
            "maxItems": 10,
            "uniqueItems": True,
        },
        "confidence": {
            "type": "object",
            "patternProperties": {".*": {"type": "number", "minimum": 0, "maximum": 1}},
            "additionalProperties": False,
        },
        "categories": {
            "type": "object",
            "patternProperties": {".*": {"type": "array", "items": {"type": "string"}}},
            "additionalProperties": False,
        },
    },
    "required": ["tags"],
    "additionalProperties": False,
}

# Schema for keywords processor output
KEYWORDS_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "keywords": {
            "type": "array",
            "items": {
                "type": "string",
                "minLength": 2,
                "maxLength": 30,
                "pattern": r"^[\w\s\u4e00-\u9fff]+$",
            },
            "minItems": 1,
            "maxItems": 10,
            "uniqueItems": True,
        },
        "phrases": {
            "type": "array",
            "items": {"type": "string", "minLength": 3, "maxLength": 50},
            "maxItems": 5,
            "uniqueItems": True,
        },
        "importance_scores": {
            "type": "object",
            "patternProperties": {".*": {"type": "number", "minimum": 0, "maximum": 1}},
            "additionalProperties": False,
        },
    },
    "required": ["keywords"],
    "additionalProperties": False,
}

# Schema for summary processor output (when structured)
SUMMARY_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "minLength": 10, "maxLength": 1000},
        "key_points": {
            "type": "array",
            "items": {"type": "string", "minLength": 5, "maxLength": 200},
            "maxItems": 10,
        },
        "word_count": {"type": "integer", "minimum": 1},
        "style": {"type": "string", "enum": ["concise", "detailed", "bullet_points"]},
    },
    "required": ["summary"],
    "additionalProperties": False,
}

# Schema for content classification
CONTENT_CLASSIFICATION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "primary_category": {"type": "string", "minLength": 1, "maxLength": 50},
        "secondary_categories": {
            "type": "array",
            "items": {"type": "string", "minLength": 1, "maxLength": 50},
            "maxItems": 3,
        },
        "content_type": {
            "type": "string",
            "enum": [
                "article",
                "news",
                "blog",
                "research",
                "tutorial",
                "review",
                "opinion",
                "other",
            ],
        },
        "audience_level": {
            "type": "string",
            "enum": ["beginner", "intermediate", "advanced", "expert", "general"],
        },
        "language": {"type": "string", "enum": ["en", "zh", "mixed", "other"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["primary_category", "content_type"],
    "additionalProperties": False,
}

# Schema for sentiment analysis
SENTIMENT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "sentiment": {"type": "string", "enum": ["positive", "negative", "neutral"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "emotional_tone": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "happy",
                    "sad",
                    "angry",
                    "excited",
                    "calm",
                    "worried",
                    "hopeful",
                    "disappointed",
                ],
            },
            "maxItems": 3,
        },
        "subjectivity": {
            "type": "string",
            "enum": ["subjective", "objective", "mixed"],
        },
    },
    "required": ["sentiment", "confidence"],
    "additionalProperties": False,
}


class SchemaManager:
    """Manager for JSON schemas used in LLM processors."""

    # Registry of available schemas
    SCHEMAS = {
        "tags": TAGS_SCHEMA,
        "keywords": KEYWORDS_SCHEMA,
        "summary": SUMMARY_SCHEMA,
        "classification": CONTENT_CLASSIFICATION_SCHEMA,
        "sentiment": SENTIMENT_SCHEMA,
    }

    @classmethod
    def get_schema(cls, schema_name: str) -> Dict[str, Any]:
        """
        Get a schema by name.

        Args:
            schema_name: Name of the schema

        Returns:
            JSON schema dictionary

        Raises:
            ValueError: If schema name is not found
        """
        if schema_name not in cls.SCHEMAS:
            available = list(cls.SCHEMAS.keys())
            raise ValueError(
                f"Schema '{schema_name}' not found. Available: {available}"
            )

        return cls.SCHEMAS[schema_name]

    @classmethod
    def get_all_schemas(cls) -> Dict[str, Dict[str, Any]]:
        """
        Get all available schemas.

        Returns:
            Dictionary mapping schema names to schemas
        """
        return cls.SCHEMAS.copy()

    @classmethod
    def register_schema(cls, name: str, schema: Dict[str, Any]) -> None:
        """
        Register a new schema.

        Args:
            name: Name for the schema
            schema: JSON schema dictionary
        """
        cls.SCHEMAS[name] = schema

    @classmethod
    def validate_schema_structure(cls, schema: Dict[str, Any]) -> bool:
        """
        Validate that a schema has the correct structure.

        Args:
            schema: Schema to validate

        Returns:
            True if schema is valid
        """
        required_keys = ["type", "properties"]
        return all(key in schema for key in required_keys)

    @classmethod
    def create_custom_tags_schema(
        cls, available_tags: list, max_tags: int = 5
    ) -> Dict[str, Any]:
        """
        Create a custom tags schema with specific available tags.

        Args:
            available_tags: List of allowed tags
            max_tags: Maximum number of tags

        Returns:
            Custom tags schema
        """
        return {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "string", "enum": available_tags},
                    "minItems": 1,
                    "maxItems": max_tags,
                    "uniqueItems": True,
                }
            },
            "required": ["tags"],
            "additionalProperties": False,
        }

    @classmethod
    def create_custom_keywords_schema(
        cls,
        min_keywords: int = 1,
        max_keywords: int = 5,
        min_length: int = 2,
        max_length: int = 20,
    ) -> Dict[str, Any]:
        """
        Create a custom keywords schema with specific constraints.

        Args:
            min_keywords: Minimum number of keywords
            max_keywords: Maximum number of keywords
            min_length: Minimum keyword length
            max_length: Maximum keyword length

        Returns:
            Custom keywords schema
        """
        return {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "minLength": min_length,
                        "maxLength": max_length,
                        "pattern": r"^[\w\s\u4e00-\u9fff]+$",
                    },
                    "minItems": min_keywords,
                    "maxItems": max_keywords,
                    "uniqueItems": True,
                }
            },
            "required": ["keywords"],
            "additionalProperties": False,
        }
