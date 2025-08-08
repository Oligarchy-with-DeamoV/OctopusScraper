"""
LLM Summary Processor for OctopusScraper.

This module implements a specialized processor for generating article summaries
using Large Language Models. It supports multiple summary styles, languages,
and quality control features.
"""

from copy import deepcopy
from typing import Any, Dict, List, Optional

import structlog
from dacite import from_dict

from octopus_scraper.llm.client import LLMClient, LLMConfig, LLMProvider
from octopus_scraper.llm.prompts import PromptLanguage, PromptManager, SummaryStyle
from octopus_scraper.llm.utils import LLMUtils
from octopus_scraper.processors.processor_base import (
    ProcessingError,
    ProcessingResult,
    ProcessorBase,
)
from octopus_scraper.processors.protos import SummaryProcessorConfig
from octopus_scraper.protos import Content
from octopus_scraper.utils.text_processor import TextProcessor
from octopus_scraper.utils.validators import DataValidator

logger = structlog.getLogger(__name__)


class LLMSummaryProcessor(ProcessorBase):
    """
    LLM-based summary processor.

    This processor generates high-quality summaries for articles using
    Large Language Models. It supports multiple summary styles, automatic
    language detection, and quality validation.

    Features:
    - Multiple summary styles (concise, detailed, bullet points, executive)
    - Automatic language detection and appropriate prompt selection
    - Length control and quality validation
    - Configurable LLM parameters
    - Robust error handling and fallback mechanisms
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize the summary processor.

        Args:
            config: Processor configuration dictionary

        Raises:
            ProcessingError: If configuration is invalid
        """
        super().__init__(config)

        # Initialize LLM client
        llm_config = LLMConfig(
            provider=LLMProvider.OPENAI,  # Default to OpenAI for GPT models
            model_name=self.config.model_name,
            api_key=self.config.api_key,
            api_base=self.config.api_base,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            timeout=self.config.timeout,
            retry_times=self.config.retry_times,
        )

        try:
            self.llm_client = LLMClient(llm_config)
        except Exception as e:
            raise ProcessingError(f"Failed to initialize LLM client: {e}", self.name)

        # Initialize prompt manager
        self.prompt_manager = PromptManager()

        # Initialize text processor for content preprocessing
        self.text_processor = TextProcessor()

        # Cache for processed summaries (simple in-memory cache)
        self._summary_cache: Dict[str, str] = {}

        self.logger.info(
            "LLM Summary Processor initialized",
            model=self.config.model_name,
            style=self.config.summary_style,
            max_length=self.config.max_summary_length,
        )

    def _parse_config(self, config: Dict[str, Any]) -> SummaryProcessorConfig:
        """
        Parse and validate processor configuration.

        Args:
            config: Raw configuration dictionary

        Returns:
            Parsed SummaryProcessorConfig

        Raises:
            ProcessingError: If configuration is invalid
        """
        try:
            parsed_config = from_dict(SummaryProcessorConfig, config)

            # Validate configuration
            is_valid, error = DataValidator.validate_processor_config(config, "summary")
            if not is_valid:
                raise ProcessingError(
                    f"Invalid configuration: {error}", self.__class__.__name__
                )

            return parsed_config

        except Exception as e:
            raise ProcessingError(
                f"Configuration parsing failed: {e}", self.__class__.__name__
            )

    def __call__(self, contents: List[Content]) -> List[Content]:
        """
        Process a list of content items to generate summaries.

        Args:
            contents: List of content items to process

        Returns:
            List of content items with updated summaries

        Raises:
            ProcessingError: If processing fails for all items
        """
        if not contents:
            self.logger.warning("No content provided for summary processing")
            return []

        processed_contents = []
        success_count = 0

        for i, content in enumerate(contents):
            try:
                self.logger.debug(
                    "Processing content for summary",
                    content_id=content.content_id,
                    index=i,
                    total=len(contents),
                )

                processed_content = self._process_single_content(content)
                processed_contents.append(processed_content)
                success_count += 1

            except Exception as e:
                self.logger.error(
                    "Failed to process content for summary",
                    content_id=content.content_id,
                    error=str(e),
                )
                # Add original content on failure
                processed_contents.append(deepcopy(content))

        self.logger.info(
            "Summary processing completed",
            total_items=len(contents),
            success_count=success_count,
            failure_count=len(contents) - success_count,
        )

        if success_count == 0:
            raise ProcessingError("Failed to process any content items", self.name)

        return processed_contents

    def _process_single_content(self, content: Content) -> Content:
        """
        Process a single content item to generate summary.

        Args:
            content: Content item to process

        Returns:
            Content item with updated summary

        Raises:
            ProcessingError: If processing fails
        """
        # Create a copy to avoid modifying original
        processed_content = deepcopy(content)

        # Check cache first
        cache_key = self._generate_cache_key(content)
        if cache_key in self._summary_cache:
            processed_content.summary = self._summary_cache[cache_key]
            self.logger.debug("Using cached summary", content_id=content.content_id)
            return processed_content

        try:
            # Preprocess content
            title = self._preprocess_text(content.title)
            content_text = self._preprocess_text(content.content)

            # Detect language
            language = self._detect_content_language(title, content_text)

            # Validate content length
            if not self._validate_content_length(content_text):
                # Content too short or too long, create simple summary
                summary = self._create_fallback_summary(title, content_text)
            else:
                # Generate summary using LLM
                summary = self._generate_llm_summary(title, content_text, language)

            # Validate and post-process summary
            final_summary = self._post_process_summary(summary)

            # Cache the result
            self._summary_cache[cache_key] = final_summary

            # Update content
            processed_content.summary = final_summary

            self.logger.debug(
                "Summary generated successfully",
                content_id=content.content_id,
                summary_length=len(final_summary),
                language=language,
            )

            return processed_content

        except Exception as e:
            self.logger.error(
                "Summary generation failed", content_id=content.content_id, error=str(e)
            )
            # Return content with original summary or create a basic one
            if not processed_content.summary:
                processed_content.summary = self._create_fallback_summary(
                    content.title, content.content
                )
            return processed_content

    def _preprocess_text(self, text: str) -> str:
        """
        Preprocess text for LLM consumption.

        Args:
            text: Raw text

        Returns:
            Preprocessed text
        """
        if not text:
            return ""

        # Clean HTML and normalize
        cleaned = self.text_processor.clean_html(text)
        cleaned = self.text_processor.normalize_whitespace(cleaned)
        cleaned = self.text_processor.normalize_unicode(cleaned)

        # Truncate if too long for LLM context
        max_content_tokens = self.config.max_tokens - 500  # Reserve tokens for response
        cleaned = LLMUtils.truncate_text(cleaned, max_content_tokens)

        return cleaned

    def _detect_content_language(self, title: str, content: str) -> PromptLanguage:
        """
        Detect the primary language of content.

        Args:
            title: Article title
            content: Article content

        Returns:
            Detected PromptLanguage
        """
        # Combine title and first part of content for detection
        sample_text = f"{title} {content[:500]}"

        detected = self.text_processor.detect_language(sample_text)

        if detected == "chinese":
            return PromptLanguage.CHINESE
        elif detected == "english":
            return PromptLanguage.ENGLISH
        else:
            return PromptLanguage.MIXED

    def _validate_content_length(self, content: str) -> bool:
        """
        Validate if content length is suitable for LLM processing.

        Args:
            content: Content text

        Returns:
            True if length is suitable
        """
        word_count = self.text_processor.count_words(content, "mixed")

        # Too short: less than 50 words
        if word_count < 50:
            self.logger.debug(
                "Content too short for LLM processing", word_count=word_count
            )
            return False

        # Too long: more than 5000 words (rough limit)
        if word_count > 5000:
            self.logger.debug(
                "Content too long for LLM processing", word_count=word_count
            )
            return False

        return True

    def _generate_llm_summary(
        self, title: str, content: str, language: PromptLanguage
    ) -> str:
        """
        Generate summary using LLM.

        Args:
            title: Article title
            content: Article content
            language: Detected language

        Returns:
            Generated summary

        Raises:
            ProcessingError: If LLM generation fails
        """
        try:
            # Create messages using prompt manager
            messages = self.prompt_manager.create_summary_messages(
                title=title,
                content=content,
                style=self.config.summary_style,
                language=language.value,
                max_length=self.config.max_summary_length,
                max_points=5,  # For bullet points style
            )

            # Generate summary
            response = self.llm_client.generate(
                messages=messages,
                max_tokens=min(
                    self.config.max_tokens, self.config.max_summary_length * 2
                ),
                temperature=self.config.temperature,
            )

            if not response.success:
                raise ProcessingError(f"LLM generation failed: {response.error}")

            return response.content.strip()

        except Exception as e:
            raise ProcessingError(f"Summary generation failed: {e}")

    def _create_fallback_summary(self, title: str, content: str) -> str:
        """
        Create a fallback summary when LLM processing is not suitable.

        Args:
            title: Article title
            content: Article content

        Returns:
            Fallback summary
        """
        if not content.strip():
            return title if title else "无法生成摘要：内容为空"

        # Extract first few sentences as summary
        sentences = self.text_processor.extract_sentences(content, max_sentences=3)

        if sentences:
            summary = " ".join(sentences)
            # Truncate to max length
            summary = self.text_processor.truncate_by_words(
                summary, self.config.max_summary_length, "mixed"
            )
            return summary
        else:
            # Use first part of content
            return self.text_processor.truncate_by_words(
                content, self.config.max_summary_length, "mixed"
            )

    def _post_process_summary(self, summary: str) -> str:
        """
        Post-process and validate generated summary.

        Args:
            summary: Raw generated summary

        Returns:
            Processed and validated summary
        """
        if not summary:
            return "摘要生成失败"

        # Clean and normalize
        cleaned = self.text_processor.normalize_whitespace(summary)
        cleaned = cleaned.strip()

        # Validate length
        word_count = self.text_processor.count_words(cleaned, "mixed")
        if word_count > self.config.max_summary_length:
            # Truncate if too long
            cleaned = self.text_processor.truncate_by_words(
                cleaned, self.config.max_summary_length, "mixed"
            )

        # Ensure minimum quality
        if len(cleaned) < 10:
            return "摘要过短，请检查原文内容"

        return cleaned

    def _generate_cache_key(self, content: Content) -> str:
        """
        Generate cache key for content.

        Args:
            content: Content item

        Returns:
            Cache key string
        """
        # Simple hash based on content and configuration
        key_parts = [
            content.content_id,
            self.config.summary_style,
            str(self.config.max_summary_length),
            self.config.model_name,
        ]
        return "|".join(key_parts)

    def get_summary_stats(self) -> Dict[str, Any]:
        """
        Get statistics about summary processing.

        Returns:
            Dictionary with processing statistics
        """
        return {
            "processor_name": self.name,
            "model_name": self.config.model_name,
            "summary_style": self.config.summary_style,
            "max_summary_length": self.config.max_summary_length,
            "cache_size": len(self._summary_cache),
            "config": {
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
                "preserve_structure": self.config.preserve_structure,
                "include_key_points": self.config.include_key_points,
            },
        }

    def clear_cache(self) -> None:
        """Clear the summary cache."""
        self._summary_cache.clear()
        self.logger.info("Summary cache cleared")

    def health_check(self) -> bool:
        """
        Check if the processor is healthy and ready to process.

        Returns:
            True if healthy
        """
        try:
            # Check LLM client health
            return self.llm_client.health_check()
        except Exception as e:
            self.logger.error("Health check failed", error=str(e))
            return False
