"""
LLM Tags Processor for OctopusScraper.

This module implements intelligent tag generation for content using LLM models.
It provides structured tag extraction with confidence scoring and custom categorization.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Union

import structlog
from dacite import from_dict

from octopus_scraper.llm.client import LLMClient, LLMConfig, LLMProvider, LLMResponse
from octopus_scraper.llm.prompts import TagsPromptManager
from octopus_scraper.llm.schemas import TAGS_SCHEMA
from octopus_scraper.processors.processor_base import ProcessingError, ProcessorBase
from octopus_scraper.processors.protos import TagsProcessorConfig
from octopus_scraper.protos import Content
from octopus_scraper.utils.text_processor import TextProcessor
from octopus_scraper.utils.validators import DataValidator

logger = structlog.getLogger(__name__)


class LLMTagsProcessor(ProcessorBase):
    """
    LLM-powered tags processor for intelligent content tagging.

    This processor uses Large Language Models to generate relevant tags for content,
    supporting custom categorization systems, confidence scoring, and multilingual content.

    Features:
    - Intelligent tag generation using LLM
    - Custom tag categorization system
    - Confidence scoring for generated tags
    - Multi-language support (Chinese, English, Mixed)
    - Caching and fallback mechanisms
    - Content preprocessing and filtering

    Attributes:
        config (TagsProcessorConfig): Processor configuration
        llm_client (LLMClient): LLM client for tag generation
        prompt_manager (TagsPromptManager): Prompt management system
        text_processor (TextProcessor): Text preprocessing utilities
        validator (DataValidator): Response validation
        _cache (Dict): Simple cache for repeated requests
    """

    def __init__(self, config: TagsProcessorConfig):
        """
        Initialize the LLM tags processor.

        Args:
            config: Processor configuration containing LLM settings and tag parameters

        Raises:
            ProcessingError: If initialization fails
        """
        # Convert config to dict for parent class if needed
        if isinstance(config, dict):
            config_dict = config
            self.config = from_dict(TagsProcessorConfig, config_dict)
        else:
            config_dict = config.__dict__
            self.config = config

        # Initialize parent class
        super().__init__(config_dict)

        try:
            # Initialize LLM client
            llm_config = LLMConfig(
                provider=LLMProvider(self.config.llm_provider),
                model_name=self.config.model_name,
                api_key=self.config.api_key,
                api_base=self.config.base_url or self.config.api_base,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                timeout=self.config.timeout_seconds,
                retry_times=self.config.retry_times,
            )
            self.llm_client = LLMClient(llm_config)

            # Initialize prompt manager and utilities
            self.prompt_manager = TagsPromptManager()
            self.text_processor = TextProcessor()
            self.validator = DataValidator()

            # Simple cache for repeated requests
            self._cache: Dict[str, Any] = {}

            # Validate LLM connection
            if not self.llm_client.health_check():
                raise ProcessingError("LLM client health check failed")

            logger.info(
                "LLM tags processor initialized successfully",
                provider=self.config.llm_provider,
                model=self.config.model_name,
            )

        except Exception as e:
            logger.error("Failed to initialize LLM tags processor", error=str(e))
            raise ProcessingError(f"Initialization failed: {e}")

    def _parse_config(self, config: Dict[str, Any]) -> TagsProcessorConfig:
        """
        Parse and validate the configuration for this processor.

        Args:
            config: Raw configuration dictionary

        Returns:
            Parsed configuration object

        Raises:
            ValidationError: If configuration is invalid
        """
        try:
            return from_dict(TagsProcessorConfig, config)
        except Exception as e:
            raise ValueError(f"Invalid configuration: {e}")

    def __call__(self, contents: List[Content]) -> List[Content]:
        """
        Process a list of content items.

        Args:
            contents: List of content items to process

        Returns:
            List of processed content items

        Raises:
            ProcessingError: If processing fails
        """
        return self.process(contents)

    def process(self, contents: List[Content]) -> List[Content]:
        """
        Process contents to generate intelligent tags.

        Args:
            contents: List of Content objects to process

        Returns:
            List of Content objects with generated tags

        Raises:
            ProcessingError: If processing fails
        """
        if not contents:
            logger.warning("No contents provided for tag processing")
            return []

        processed_contents = []
        for content in contents:
            try:
                processed_content = self._process_single_content(content)
                processed_contents.append(processed_content)

            except Exception as e:
                logger.error(
                    "Failed to process content for tags",
                    title=content.title,
                    error=str(e),
                )
                if self.config.fail_fast:
                    raise ProcessingError(f"Tag processing failed: {e}")
                # Add original content without tags
                processed_contents.append(content)

        logger.info(
            "Completed tags processing",
            total=len(contents),
            processed=len(processed_contents),
        )
        return processed_contents

    def _process_single_content(self, content: Content) -> Content:
        """
        Process a single content item to generate tags.

        Args:
            content: Content object to process

        Returns:
            Content object with generated tags
        """
        # Check cache first
        cache_key = self._generate_cache_key(content)
        if cache_key in self._cache:
            logger.debug("Using cached tags", title=content.title)
            cached_result = self._cache[cache_key]
            return self._apply_tags_to_content(content, cached_result)

        # Prepare content for processing
        processed_text = self.text_processor.clean_text(content.content)
        if not processed_text or len(processed_text.strip()) < 10:
            logger.warning("Content too short for tag generation", title=content.title)
            return content

        # Generate tags using LLM
        try:
            tags_data = self._generate_llm_tags(content.title, processed_text)

            # Apply custom categorization if configured
            if self.config.custom_categories:
                tags_data = self._apply_custom_categorization(tags_data)

            # Filter by confidence threshold
            if self.config.confidence_threshold > 0:
                tags_data = self._filter_by_confidence(tags_data)

            # Cache the result
            self._cache[cache_key] = tags_data

            # Apply tags to content
            return self._apply_tags_to_content(content, tags_data)

        except Exception as e:
            logger.error("Failed to generate tags", title=content.title, error=str(e))
            return self._handle_fallback(content)

    def _generate_llm_tags(self, title: str, content_text: str) -> Dict[str, Any]:
        """
        Generate tags using LLM.

        Args:
            title: Content title
            content_text: Processed content text

        Returns:
            Dictionary containing generated tags and metadata
        """
        # Detect language and select appropriate prompt
        language = self.text_processor.detect_language(content_text)

        # Create messages for LLM
        messages = self.prompt_manager.create_messages(
            title=title,
            content=content_text,
            max_tags=self.config.max_tags,
            language=language,
            summary_context="",
        )

        # Generate response
        response = self.llm_client.generate(messages)

        if not response.success:
            raise ProcessingError(f"LLM generation failed: {response.content}")

        # Extract and validate JSON response
        json_content = self.llm_client.extract_json_from_response(response.content)
        tags_data = json.loads(json_content)

        # Validate against schema
        if not self.validator.validate_json(tags_data, TAGS_SCHEMA):
            logger.warning("Generated tags don't match schema", data=tags_data)
            # Try to fix the response
            tags_data = self._fix_tags_response(tags_data)

        return tags_data

    def _apply_custom_categorization(self, tags_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply custom categorization to generated tags.

        Args:
            tags_data: Original tags data

        Returns:
            Tags data with custom categorization applied
        """
        if not self.config.custom_categories:
            return tags_data

        categorized_tags = {}
        tags = tags_data.get("tags", [])

        for category_name, category_keywords in self.config.custom_categories.items():
            category_tags = []
            for tag in tags:
                # Simple keyword matching for categorization
                tag_lower = tag.lower()
                if any(keyword.lower() in tag_lower for keyword in category_keywords):
                    category_tags.append(tag)

            if category_tags:
                categorized_tags[category_name] = category_tags

        # Add uncategorized tags
        categorized_tag_set = set()
        for cat_tags in categorized_tags.values():
            categorized_tag_set.update(cat_tags)

        uncategorized = [tag for tag in tags if tag not in categorized_tag_set]
        if uncategorized:
            categorized_tags["general"] = uncategorized

        tags_data["categories"] = categorized_tags
        return tags_data

    def _filter_by_confidence(self, tags_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Filter tags by confidence threshold.

        Args:
            tags_data: Tags data with confidence scores

        Returns:
            Filtered tags data
        """
        confidence_scores = tags_data.get("confidence", {})
        if not confidence_scores:
            return tags_data

        filtered_tags = []
        filtered_confidence = {}

        for tag in tags_data.get("tags", []):
            confidence = confidence_scores.get(tag, 0.0)
            if confidence >= self.config.confidence_threshold:
                filtered_tags.append(tag)
                filtered_confidence[tag] = confidence

        tags_data["tags"] = filtered_tags
        tags_data["confidence"] = filtered_confidence

        # Update categories if they exist
        if "categories" in tags_data:
            updated_categories = {}
            for category, category_tags in tags_data["categories"].items():
                filtered_category_tags = [
                    tag for tag in category_tags if tag in filtered_tags
                ]
                if filtered_category_tags:
                    updated_categories[category] = filtered_category_tags
            tags_data["categories"] = updated_categories

        return tags_data

    def _fix_tags_response(self, tags_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Attempt to fix malformed tags response.

        Args:
            tags_data: Potentially malformed tags data

        Returns:
            Fixed tags data
        """
        fixed_data = {"tags": []}

        # Extract tags from various possible formats
        if "tags" in tags_data and isinstance(tags_data["tags"], list):
            fixed_data["tags"] = [
                str(tag) for tag in tags_data["tags"][: self.config.max_tags]
            ]
        elif "tag" in tags_data:
            # Handle singular form
            if isinstance(tags_data["tag"], list):
                fixed_data["tags"] = [
                    str(tag) for tag in tags_data["tag"][: self.config.max_tags]
                ]
            else:
                fixed_data["tags"] = [str(tags_data["tag"])]

        # Extract confidence scores if available
        if "confidence" in tags_data and isinstance(tags_data["confidence"], dict):
            fixed_data["confidence"] = {
                k: float(v)
                for k, v in tags_data["confidence"].items()
                if k in fixed_data["tags"]
            }

        # Ensure minimum number of tags
        if len(fixed_data["tags"]) == 0:
            fixed_data["tags"] = ["general", "content"]

        return fixed_data

    def _apply_tags_to_content(
        self, content: Content, tags_data: Dict[str, Any]
    ) -> Content:
        """
        Apply generated tags to content object.

        Args:
            content: Original content object
            tags_data: Generated tags data

        Returns:
            Content object with applied tags
        """
        # Create a copy of the content
        content_dict = content.__dict__.copy()

        # Format tags with categories if available
        final_tags = []
        categories = tags_data.get("categories", {})

        if categories:
            # Add categorized tags with prefixes
            for category_name, category_tags in categories.items():
                if category_name != "general":  # Don't prefix general category
                    final_tags.extend(
                        [f"{category_name}:{tag}" for tag in category_tags]
                    )
                else:
                    final_tags.extend(category_tags)
        else:
            # Use original tags if no categorization
            final_tags = tags_data.get("tags", [])

        # Add tags information
        content_dict["tags"] = final_tags

        # Add metadata
        if "confidence" in tags_data:
            content_dict.setdefault("metadata", {})["tag_confidence"] = tags_data[
                "confidence"
            ]

        if "categories" in tags_data:
            content_dict.setdefault("metadata", {})["tag_categories"] = tags_data[
                "categories"
            ]

        # Create new content object
        return from_dict(Content, content_dict)

    def _handle_fallback(self, content: Content) -> Content:
        """
        Handle fallback when tag generation fails.

        Args:
            content: Original content object

        Returns:
            Content object with fallback tags
        """
        if not self.config.enable_fallback:
            return content

        # Simple keyword-based fallback
        fallback_tags = []
        content_text = content.content.lower()

        # Basic keyword detection
        keywords_map = {
            "technology": ["tech", "software", "computer", "digital", "ai", "ml"],
            "business": ["business", "company", "market", "finance", "economy"],
            "science": ["research", "study", "analysis", "experiment", "data"],
            "health": ["health", "medical", "healthcare", "disease", "treatment"],
            "education": ["education", "learning", "school", "university", "course"],
        }

        for tag, keywords in keywords_map.items():
            if any(keyword in content_text for keyword in keywords):
                fallback_tags.append(tag)

        if not fallback_tags:
            fallback_tags = ["general"]

        # Apply fallback tags
        content_dict = content.__dict__.copy()
        content_dict["tags"] = fallback_tags
        content_dict.setdefault("metadata", {})["tags_source"] = "fallback"

        return from_dict(Content, content_dict)

    def _generate_cache_key(self, content: Content) -> str:
        """
        Generate cache key for content.

        Args:
            content: Content object

        Returns:
            Cache key string
        """
        # Create a simple hash based on title and content length
        key_data = f"{content.title}:{len(content.content)}:{self.config.max_tags}"
        return str(hash(key_data))

    def get_stats(self) -> Dict[str, Any]:
        """
        Get processor statistics.

        Returns:
            Dictionary containing processor statistics
        """
        return {
            "processor_type": "llm_tags",
            "processor_name": "LLMTagsProcessor",
            "model": self.config.model_name,
            "model_name": self.config.model_name,
            "provider": self.config.llm_provider,
            "cache_size": len(self._cache),
            "max_tags": self.config.max_tags,
            "max_tags_count": self.config.max_tags,
            "confidence_threshold": self.config.confidence_threshold,
            "fallback_enabled": self.config.enable_fallback,
            "config": self.config.__dict__,
        }

    def get_tags_stats(self) -> Dict[str, Any]:
        """
        Get tags-specific processor statistics.

        Returns:
            Dictionary containing tags processor statistics
        """
        return self.get_stats()

    def health_check(self) -> bool:
        """
        Perform health check for the processor.

        Returns:
            True if processor is healthy
        """
        try:
            # Check LLM client health
            if not self.llm_client.health_check():
                return False

            # Check configuration validity
            if not self.config or not self.config.model_name:
                return False

            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def clear_cache(self) -> None:
        """Clear the processor cache."""
        self._cache.clear()
        logger.info("Tags processor cache cleared")
