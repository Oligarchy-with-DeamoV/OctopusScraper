"""
LLM Keywords Processor for OctopusScraper.

This module implements intelligent keyword extraction for content using LLM models.
It provides structured keyword extraction with importance scoring and filtering.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Union

import structlog
from dacite import from_dict

from octopus_scraper.llm.client import LLMClient, LLMConfig, LLMProvider, LLMResponse
from octopus_scraper.llm.prompts import KeywordsPromptManager
from octopus_scraper.llm.schemas import KEYWORDS_SCHEMA
from octopus_scraper.processors.processor_base import ProcessingError, ProcessorBase
from octopus_scraper.processors.protos import KeywordsProcessorConfig
from octopus_scraper.processors.llm_structured_helper import (
    StructuredLLMProcessorHelper,
)
from octopus_scraper.protos import Content
from octopus_scraper.utils.text_processor import TextProcessor
from octopus_scraper.utils.validators import DataValidator

logger = structlog.getLogger(__name__)


class LLMKeywordsProcessor(ProcessorBase):
    """
    LLM-powered keywords processor for intelligent keyword extraction.

    This processor uses Large Language Models to extract relevant keywords and phrases
    from content, providing importance scoring and advanced filtering capabilities.

    Features:
    - Intelligent keyword extraction using LLM
    - Importance scoring for each keyword
    - Multi-language support (Chinese, English, Mixed)
    - Advanced stop word filtering
    - Phrase detection and extraction
    - Customizable extraction parameters
    - Content preprocessing and validation

    Attributes:
        config (KeywordsProcessorConfig): Processor configuration
        llm_client (LLMClient): LLM client for keyword extraction
        prompt_manager (KeywordsPromptManager): Prompt management system
        text_processor (TextProcessor): Text preprocessing utilities
        validator (DataValidator): Response validation
        _cache (Dict): Simple cache for repeated requests
    """

    def __init__(self, config: KeywordsProcessorConfig):
        """
        Initialize the LLM keywords processor.

        Args:
            config: Processor configuration containing LLM settings and extraction parameters

        Raises:
            ProcessingError: If initialization fails
        """
        # Convert config to dict for parent class if needed
        if isinstance(config, dict):
            config_dict = config
            self.config = from_dict(KeywordsProcessorConfig, config_dict)
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
            self.prompt_manager = KeywordsPromptManager()
            self.text_processor = TextProcessor()
            self.validator = DataValidator()

            # Simple cache for repeated requests
            self._cache: Dict[str, Any] = {}

            # Initialize stop words for filtering
            self._stop_words = self._load_stop_words()

            # Validate LLM connection
            if not self.llm_client.health_check():
                raise ProcessingError("LLM client health check failed")

            logger.info(
                "LLM keywords processor initialized successfully",
                provider=self.config.llm_provider,
                model=self.config.model_name,
            )

        except Exception as e:
            logger.error("Failed to initialize LLM keywords processor", error=str(e))
            raise ProcessingError(f"Initialization failed: {e}")

    def _parse_config(self, config: Dict[str, Any]) -> KeywordsProcessorConfig:
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
            return from_dict(KeywordsProcessorConfig, config)
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
        Process contents to extract intelligent keywords.

        Args:
            contents: List of Content objects to process

        Returns:
            List of Content objects with extracted keywords

        Raises:
            ProcessingError: If processing fails
        """
        if not contents:
            logger.warning("No contents provided for keyword extraction")
            return []

        processed_contents = []
        for content in contents:
            try:
                processed_content = self._process_single_content(content)
                processed_contents.append(processed_content)

            except Exception as e:
                logger.error(
                    "Failed to process content for keywords",
                    title=content.title,
                    error=str(e),
                )
                if self.config.fail_fast:
                    raise ProcessingError(f"Keyword extraction failed: {e}")
                # Add original content without keywords
                processed_contents.append(content)

        logger.info(
            "Completed keywords processing",
            total=len(contents),
            processed=len(processed_contents),
        )
        return processed_contents

    def _process_single_content(self, content: Content) -> Content:
        """
        Process a single content item to extract keywords.

        Args:
            content: Content object to process

        Returns:
            Content object with extracted keywords
        """
        # Check cache first
        cache_key = self._generate_cache_key(content)
        if cache_key in self._cache:
            logger.debug("Using cached keywords", title=content.title)
            cached_result = self._cache[cache_key]
            return self._apply_keywords_to_content(content, cached_result)

        # Prepare content for processing
        processed_text = self.text_processor.clean_text(content.content)
        if not processed_text or len(processed_text.strip()) < 20:
            logger.warning(
                "Content too short for keyword extraction", title=content.title
            )
            return content

        # Extract keywords using LLM
        try:
            keywords_data = self._generate_llm_keywords(content.title, processed_text)

            # Apply custom filtering
            keywords_data = self._filter_keywords(keywords_data)

            # Filter by importance threshold
            if self.config.min_importance_score > 0:
                keywords_data = self._filter_by_importance(keywords_data)

            # Cache the result
            self._cache[cache_key] = keywords_data

            # Apply keywords to content
            return self._apply_keywords_to_content(content, keywords_data)

        except Exception as e:
            logger.error(
                "Failed to extract keywords", title=content.title, error=str(e)
            )
            return self._handle_fallback(content)

    def _generate_llm_keywords(self, title: str, content_text: str) -> Dict[str, Any]:
        """
        Extract keywords using LLM.

        Args:
            title: Content title
            content_text: Processed content text

        Returns:
            Dictionary containing extracted keywords and metadata
        """
        # Detect language and select appropriate prompt
        language = self.text_processor.detect_language(content_text)

        # Create messages for LLM
        messages = self.prompt_manager.create_messages(
            title=title,
            content=content_text,
            keywords_count=self.config.max_keywords,
            language=language,
            summary_context="",
        )

        return StructuredLLMProcessorHelper.generate_structured_data(
            llm_client=self.llm_client,
            validator=self.validator,
            messages=messages,
            schema=KEYWORDS_SCHEMA,
            fix_response=self._fix_keywords_response,
            invalid_schema_event="Generated keywords don't match schema",
        )

    def _filter_keywords(self, keywords_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply custom filtering to extracted keywords.

        Args:
            keywords_data: Original keywords data

        Returns:
            Filtered keywords data
        """
        keywords = keywords_data.get("keywords", [])
        importance_scores = keywords_data.get("importance_scores", {})

        filtered_keywords = []
        filtered_scores = {}

        for keyword in keywords:
            # Check length constraints
            if not self._is_valid_keyword_length(keyword):
                continue

            # Check if it's a common word
            if self._is_common_word(keyword):
                continue

            # Check custom exclusions
            if self.config.exclude_patterns and self._matches_exclusion_pattern(
                keyword
            ):
                continue

            filtered_keywords.append(keyword)
            if keyword in importance_scores:
                filtered_scores[keyword] = importance_scores[keyword]

        # Limit to max keywords
        if len(filtered_keywords) > self.config.max_keywords:
            # Sort by importance score if available
            if filtered_scores:
                sorted_keywords = sorted(
                    filtered_keywords,
                    key=lambda k: filtered_scores.get(k, 0.5),
                    reverse=True,
                )
                filtered_keywords = sorted_keywords[: self.config.max_keywords]
                filtered_scores = {
                    k: filtered_scores[k]
                    for k in filtered_keywords
                    if k in filtered_scores
                }
            else:
                filtered_keywords = filtered_keywords[: self.config.max_keywords]

        return_data = {
            "keywords": filtered_keywords,
            "importance_scores": filtered_scores,
        }

        # Preserve phrases if they exist in the original data
        if "phrases" in keywords_data:
            return_data["phrases"] = keywords_data["phrases"]

        return return_data

    def _filter_by_importance(self, keywords_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Filter keywords by importance threshold.

        Args:
            keywords_data: Keywords data with importance scores

        Returns:
            Filtered keywords data
        """
        importance_scores = keywords_data.get("importance_scores", {})
        if not importance_scores:
            return keywords_data

        filtered_keywords = []
        filtered_scores = {}

        for keyword in keywords_data.get("keywords", []):
            importance = importance_scores.get(keyword, 0.0)
            if importance >= self.config.min_importance_score:
                filtered_keywords.append(keyword)
                filtered_scores[keyword] = importance

        return_data = {
            "keywords": filtered_keywords,
            "importance_scores": filtered_scores,
        }

        # Preserve phrases if they exist in the original data
        if "phrases" in keywords_data:
            return_data["phrases"] = keywords_data["phrases"]

        return return_data

    def _is_valid_keyword_length(self, keyword: str) -> bool:
        """
        Check if keyword meets length requirements.

        Args:
            keyword: Keyword to check

        Returns:
            True if keyword length is valid
        """
        keyword_len = len(keyword.strip())
        return (
            self.config.min_keyword_length
            <= keyword_len
            <= self.config.max_keyword_length
        )

    def _is_common_word(self, keyword: str) -> bool:
        """
        Check if keyword is a common stop word.

        Args:
            keyword: Keyword to check

        Returns:
            True if keyword is a common word
        """
        keyword_lower = keyword.lower().strip()
        return keyword_lower in self._stop_words

    def _matches_exclusion_pattern(self, keyword: str) -> bool:
        """
        Check if keyword matches any exclusion pattern.

        Args:
            keyword: Keyword to check

        Returns:
            True if keyword matches exclusion pattern
        """
        if not self.config.exclude_patterns:
            return False

        keyword_lower = keyword.lower()
        for pattern in self.config.exclude_patterns:
            if re.search(pattern.lower(), keyword_lower):
                return True
        return False

    def _load_stop_words(self) -> Set[str]:
        """
        Load stop words for filtering.

        Returns:
            Set of stop words
        """
        # Basic stop words in multiple languages
        stop_words = {
            # English stop words
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "this",
            "that",
            "these",
            "those",
            "it",
            "they",
            "we",
            "you",
            "he",
            "she",
            "his",
            "her",
            "their",
            "our",
            "my",
            "your",
            "some",
            "any",
            "all",
            "many",
            "much",
            "more",
            "most",
            "other",
            "such",
            "very",
            "just",
            "only",
            "even",
            "also",
            "still",
            "yet",
            "now",
            "then",
            "here",
            "there",
            "where",
            "when",
            "why",
            "how",
            "what",
            "who",
            "which",
            "can",
            "may",
            "might",
            "must",
            "shall",
            "need",
            "want",
            "get",
            "got",
            "give",
            "gave",
            "take",
            "took",
            "make",
            "made",
            "come",
            "came",
            "go",
            "went",
            "see",
            "saw",
            "know",
            "knew",
            "think",
            "thought",
            "say",
            "said",
            "tell",
            "told",
            "ask",
            "asked",
            "work",
            "worked",
            "play",
            "played",
            "run",
            "ran",
            "walk",
            "walked",
            # Chinese stop words
            "的",
            "了",
            "在",
            "是",
            "我",
            "有",
            "和",
            "就",
            "不",
            "人",
            "都",
            "一",
            "一个",
            "上",
            "也",
            "很",
            "到",
            "说",
            "要",
            "去",
            "你",
            "会",
            "着",
            "没有",
            "看",
            "好",
            "自己",
            "这",
            "那",
            "里",
            "后",
            "以",
            "时",
            "来",
            "用",
            "们",
            "生",
            "大",
            "为",
            "能",
            "作",
            "分",
            "成",
            "者",
            "多",
            "部",
            "可",
            "主",
            "发",
            "年",
            "动",
            "同",
            "工",
            "最",
            "并",
            "没",
            "而",
            "及",
            "之",
            "与",
            "中",
            "更",
            "被",
            "这些",
            "那些",
            "什么",
            "怎么",
            "为什么",
            "哪里",
            "怎样",
            # Common punctuation and numbers that might be extracted
            "1",
            "2",
            "3",
            "4",
            "5",
            "6",
            "7",
            "8",
            "9",
            "0",
            "一",
            "二",
            "三",
            "四",
            "五",
            "!",
            "@",
            "#",
            "$",
            "%",
            "^",
            "&",
            "*",
            "(",
            ")",
            "-",
            "_",
            "=",
            "+",
            "[",
            "]",
            "{",
            "}",
            "|",
            "\\",
            ":",
            ";",
            '"',
            "'",
            "<",
            ">",
            ",",
            ".",
            "?",
            "/",
            "~",
            "`",
        }

        # Add custom stop words from config
        if self.config.custom_stop_words:
            stop_words.update(self.config.custom_stop_words)

        return stop_words

    def _fix_keywords_response(self, keywords_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Attempt to fix malformed keywords response.

        Args:
            keywords_data: Potentially malformed keywords data

        Returns:
            Fixed keywords data
        """
        fixed_data = {"keywords": [], "importance_scores": {}}

        # Extract keywords from various possible formats
        if "keywords" in keywords_data and isinstance(keywords_data["keywords"], list):
            fixed_data["keywords"] = [
                str(kw) for kw in keywords_data["keywords"][: self.config.max_keywords]
            ]
        elif "keyword" in keywords_data:
            # Handle singular form
            if isinstance(keywords_data["keyword"], list):
                fixed_data["keywords"] = [
                    str(kw)
                    for kw in keywords_data["keyword"][: self.config.max_keywords]
                ]
            else:
                fixed_data["keywords"] = [str(keywords_data["keyword"])]

        # Extract phrases if available and configured
        if self.config.include_phrases and "phrases" in keywords_data:
            if isinstance(keywords_data["phrases"], list):
                fixed_data["phrases"] = [
                    str(phrase)
                    for phrase in keywords_data["phrases"][:5]  # Max 5 phrases
                ]

        # Extract importance scores if available
        for score_key in ["importance_scores", "scores", "weights", "confidence"]:
            if score_key in keywords_data and isinstance(
                keywords_data[score_key], dict
            ):
                fixed_data["importance_scores"] = {
                    k: float(v)
                    for k, v in keywords_data[score_key].items()
                    if k in fixed_data["keywords"]
                }
                break

        # Ensure minimum number of keywords
        if len(fixed_data["keywords"]) == 0:
            fixed_data["keywords"] = ["content", "article"]
            fixed_data["importance_scores"] = {"content": 0.5, "article": 0.4}

        return fixed_data

    def _apply_keywords_to_content(
        self, content: Content, keywords_data: Dict[str, Any]
    ) -> Content:
        """
        Apply extracted keywords to content object.

        Args:
            content: Original content object
            keywords_data: Extracted keywords data

        Returns:
            Content object with applied keywords
        """
        # Create a copy of the content
        content_dict = content.__dict__.copy()

        # Start with base keywords
        final_keywords = keywords_data.get("keywords", [])

        # Include phrases if configured to do so
        if self.config.include_phrases and "phrases" in keywords_data:
            phrases = keywords_data.get("phrases", [])
            final_keywords.extend(phrases)

        # Limit to keywords_count if we have too many (when including phrases)
        if len(final_keywords) > self.config.keywords_count:
            final_keywords = final_keywords[: self.config.keywords_count]

        # Add keywords information
        content_dict["keywords"] = final_keywords  # Add metadata
        if "importance_scores" in keywords_data:
            content_dict.setdefault("metadata", {})["keyword_scores"] = keywords_data[
                "importance_scores"
            ]

        # Create new content object
        return from_dict(Content, content_dict)

    def _handle_fallback(self, content: Content) -> Content:
        """
        Handle fallback when keyword extraction fails.

        Args:
            content: Original content object

        Returns:
            Content object with fallback keywords
        """
        if not self.config.enable_fallback:
            return content

        # Simple regex-based keyword extraction as fallback
        fallback_keywords = []
        content_text = content.content

        # Extract words that are likely to be keywords
        # - Capitalized words (proper nouns)
        # - Technical terms (words with numbers/special chars)
        # - Long words (likely to be meaningful)

        words = re.findall(r"\b[A-Za-z\u4e00-\u9fff]+\b", content_text)
        word_freq = {}

        for word in words:
            if (
                len(word) >= 3
                and not self._is_common_word(word)
                and self._is_valid_keyword_length(word)
            ):
                word_freq[word] = word_freq.get(word, 0) + 1

        # Sort by frequency and take top keywords
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        fallback_keywords = [
            word for word, freq in sorted_words[: self.config.max_keywords]
        ]

        if not fallback_keywords:
            fallback_keywords = ["content"]

        # Apply fallback keywords
        content_dict = content.__dict__.copy()
        content_dict["keywords"] = fallback_keywords
        content_dict.setdefault("metadata", {})["keywords_source"] = "fallback"

        return from_dict(Content, content_dict)

    def _generate_cache_key(self, content: Content) -> str:
        """
        Generate cache key for content.

        Args:
            content: Content object

        Returns:
            Cache key string
        """
        return StructuredLLMProcessorHelper.generate_cache_key(
            "llm_keywords",
            content,
            {
                "provider": self.config.llm_provider,
                "model": self.config.model_name,
                "max_keywords": self.config.max_keywords,
                "keywords_count": self.config.keywords_count,
                "min_importance_score": self.config.min_importance_score,
                "include_phrases": self.config.include_phrases,
                "language_preference": self.config.language_preference,
            },
        )

    def get_stats(self) -> Dict[str, Any]:
        """
        Get processor statistics.

        Returns:
            Dictionary containing processor statistics
        """
        return {
            "processor_type": "llm_keywords",
            "processor_name": "LLMKeywordsProcessor",
            "model": self.config.model_name,
            "model_name": self.config.model_name,
            "provider": self.config.llm_provider,
            "cache_size": len(self._cache),
            "max_keywords": self.config.max_keywords,
            "keywords_count": self.config.keywords_count,
            "min_importance_score": self.config.min_importance_score,
            "language_preference": self.config.language_preference,
            "fallback_enabled": self.config.enable_fallback,
            "stop_words_count": len(self._stop_words),
            "config": self.config.__dict__,
        }

    def get_keywords_stats(self) -> Dict[str, Any]:
        """
        Get keywords-specific processor statistics.

        Returns:
            Dictionary containing keywords processor statistics
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
        logger.info("Keywords processor cache cleared")
