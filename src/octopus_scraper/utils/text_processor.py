"""
Text processing utilities for OctopusScraper.

This module provides utilities for text preprocessing, cleaning, and manipulation
used across different processors.
"""

import html
import re
import unicodedata
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.getLogger(__name__)


class TextProcessor:
    """Text processing utilities for content preprocessing."""

    @staticmethod
    def clean_html(text: str) -> str:
        """
        Remove HTML tags and decode HTML entities from text.

        Args:
            text: Text containing HTML

        Returns:
            Clean text without HTML
        """
        if not text:
            return ""

        # Decode HTML entities
        text = html.unescape(text)

        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", text)

        # Clean up extra whitespace
        text = re.sub(r"\s+", " ", text)

        return text.strip()

    @staticmethod
    def normalize_whitespace(text: str) -> str:
        """
        Normalize whitespace in text.

        Args:
            text: Text to normalize

        Returns:
            Text with normalized whitespace
        """
        if not text:
            return ""

        # Replace multiple whitespace characters with single space
        text = re.sub(r"\s+", " ", text)

        return text.strip()

    @staticmethod
    def normalize_unicode(text: str) -> str:
        """
        Normalize unicode characters in text.

        Args:
            text: Text to normalize

        Returns:
            Text with normalized unicode
        """
        if not text:
            return ""

        # Normalize unicode to NFKC form
        text = unicodedata.normalize("NFKC", text)

        return text

    @staticmethod
    def clean_text(text: str) -> str:
        """
        Comprehensive text cleaning for content processing.

        Args:
            text: Text to clean

        Returns:
            Cleaned text
        """
        if not text:
            return ""

        # Clean HTML and decode entities
        text = TextProcessor.clean_html(text)

        # Normalize unicode characters
        text = TextProcessor.normalize_unicode(text)

        # Normalize whitespace
        text = TextProcessor.normalize_whitespace(text)

        # Remove excessive punctuation
        text = re.sub(r"[.]{3,}", "...", text)
        text = re.sub(r"[!]{2,}", "!", text)
        text = re.sub(r"[?]{2,}", "?", text)

        # Clean up quotes
        text = re.sub(r'["""]', '"', text)
        text = re.sub(r"['']", "'", text)

        return text.strip()

    @staticmethod
    def remove_special_characters(text: str, keep_chinese: bool = True) -> str:
        """
        Remove special characters from text.

        Args:
            text: Text to clean
            keep_chinese: Whether to keep Chinese characters

        Returns:
            Text with special characters removed
        """
        if not text:
            return ""

        if keep_chinese:
            # Keep alphanumeric, Chinese characters, and basic punctuation
            pattern = r"[^\w\s\u4e00-\u9fff.,!?;:\-'" "]"
        else:
            # Keep only alphanumeric and basic punctuation
            pattern = r"[^\w\s.,!?;:\-'" "]"

        text = re.sub(pattern, "", text)
        text = TextProcessor.normalize_whitespace(text)

        return text

    @staticmethod
    def extract_sentences(text: str, max_sentences: Optional[int] = None) -> List[str]:
        """
        Extract sentences from text.

        Args:
            text: Text to extract sentences from
            max_sentences: Maximum number of sentences to return

        Returns:
            List of sentences
        """
        if not text:
            return []

        # Split on sentence endings, keeping common abbreviations in mind
        sentence_pattern = r"(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\!|\?)\s+"
        sentences = re.split(sentence_pattern, text)

        # Clean and filter sentences
        cleaned_sentences = []
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) > 10:  # Filter out very short "sentences"
                cleaned_sentences.append(sentence)

        if max_sentences:
            return cleaned_sentences[:max_sentences]

        return cleaned_sentences

    @staticmethod
    def extract_paragraphs(text: str, min_length: int = 50) -> List[str]:
        """
        Extract paragraphs from text.

        Args:
            text: Text to extract paragraphs from
            min_length: Minimum length for a paragraph

        Returns:
            List of paragraphs
        """
        if not text:
            return []

        # Split on double newlines or more
        paragraphs = re.split(r"\n\s*\n+", text)

        # Filter paragraphs by length and clean them
        cleaned_paragraphs = []
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if len(paragraph) >= min_length:
                cleaned_paragraphs.append(paragraph)

        return cleaned_paragraphs

    @staticmethod
    def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
        """
        Truncate text to maximum length.

        Args:
            text: Text to truncate
            max_length: Maximum length allowed
            suffix: Suffix to add when truncating

        Returns:
            Truncated text
        """
        if not text or len(text) <= max_length:
            return text

        if len(suffix) >= max_length:
            return text[:max_length]

        truncated_length = max_length - len(suffix)
        return text[:truncated_length] + suffix

    @staticmethod
    def count_words(text: str, language: str = "mixed") -> int:
        """
        Count words in text.

        Args:
            text: Text to count words in
            language: Language of the text (chinese, english, mixed)

        Returns:
            Word count
        """
        if not text:
            return 0

        text = TextProcessor.clean_text(text)

        if language == "chinese":
            # For Chinese, count characters excluding punctuation and whitespace
            chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
            return len(chinese_chars)
        elif language == "english":
            # For English, split by whitespace
            words = text.split()
            return len([word for word in words if re.match(r"[a-zA-Z]+", word)])
        else:
            # Mixed: count both words and Chinese characters
            english_words = len(re.findall(r"\b[a-zA-Z]+\b", text))
            chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
            return english_words + chinese_chars

    @staticmethod
    def truncate_by_words(text: str, max_words: int, language: str = "mixed") -> str:
        """
        Truncate text by word count.

        Args:
            text: Text to truncate
            max_words: Maximum number of words/characters to keep
            language: Language of the text (chinese, english, mixed)

        Returns:
            Truncated text
        """
        if not text or max_words <= 0:
            return ""

        current_words = TextProcessor.count_words(text, language)
        if current_words <= max_words:
            return text

        # Truncate by breaking at word boundaries
        if language == "chinese":
            # For Chinese, truncate by characters
            chinese_chars = re.findall(r"[\u4e00-\u9fff]|[^\u4e00-\u9fff\s]+", text)
            if len(chinese_chars) <= max_words:
                return text
            return "".join(chinese_chars[:max_words])

        elif language == "english":
            # For English, truncate by words
            words = text.split()
            word_count = 0
            result_words = []

            for word in words:
                if re.match(r"[a-zA-Z]+", word):
                    if word_count >= max_words:
                        break
                    word_count += 1
                result_words.append(word)

            return " ".join(result_words)

        else:
            # Mixed: truncate by combined count
            parts = re.findall(
                r"[\u4e00-\u9fff]|\b[a-zA-Z]+\b|[^\u4e00-\u9fff\w\s]+|\s+", text
            )
            word_count = 0
            result_parts = []

            for part in parts:
                if re.match(r"[\u4e00-\u9fff]", part):
                    # Chinese character
                    if word_count >= max_words:
                        break
                    word_count += 1
                elif re.match(r"\b[a-zA-Z]+\b", part):
                    # English word
                    if word_count >= max_words:
                        break
                    word_count += 1

                result_parts.append(part)

            return "".join(result_parts).strip()

    @staticmethod
    def detect_language(text: str) -> str:
        """
        Detect the primary language of text.

        Args:
            text: Text to analyze

        Returns:
            Detected language: 'chinese', 'english', or 'mixed'
        """
        if not text:
            return "mixed"

        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        english_words = len(re.findall(r"\b[a-zA-Z]+\b", text))

        total_content = chinese_chars + english_words
        if total_content == 0:
            return "mixed"

        chinese_ratio = chinese_chars / total_content
        english_ratio = english_words / total_content

        if chinese_ratio > 0.7:
            return "chinese"
        elif english_ratio > 0.7:
            return "english"
        else:
            return "mixed"

    @staticmethod
    def extract_keywords_basic(text: str, top_k: int = 5) -> List[str]:
        """
        Extract basic keywords using simple frequency analysis.

        Args:
            text: Text to extract keywords from
            top_k: Number of top keywords to return

        Returns:
            List of keywords
        """
        if not text:
            return []

        # Clean and normalize text
        text = TextProcessor.clean_text(text)

        # Common stop words (basic list)
        stop_words = {
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
            "这",
            "的",
            "是",
            "在",
            "了",
            "和",
            "与",
            "或",
            "但",
            "如果",
            "因为",
            "所以",
            "可以",
            "能够",
            "应该",
            "会",
            "将",
            "已经",
            "正在",
        }

        # Extract words
        words = re.findall(r"\b\w+\b", text.lower())

        # Filter stop words and short words
        filtered_words = [
            word for word in words if len(word) > 2 and word not in stop_words
        ]

        # Count frequency
        word_freq = {}
        for word in filtered_words:
            word_freq[word] = word_freq.get(word, 0) + 1

        # Sort by frequency and return top k
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        return [word for word, freq in sorted_words[:top_k]]

    @staticmethod
    def generate_summary_basic(text: str, max_sentences: int = 3) -> str:
        """
        Generate a basic summary using sentence extraction.

        Args:
            text: Text to summarize
            max_sentences: Maximum number of sentences in summary

        Returns:
            Basic summary
        """
        if not text:
            return ""

        sentences = TextProcessor.extract_sentences(text)
        if not sentences:
            return ""

        # For basic summary, take the first few sentences
        # In a more sophisticated implementation, this would use
        # actual summarization algorithms
        summary_sentences = sentences[:max_sentences]
        return " ".join(summary_sentences)

    @staticmethod
    def validate_content(content: str, min_length: int = 10) -> bool:
        """
        Validate that content meets minimum requirements.

        Args:
            content: Content to validate
            min_length: Minimum content length

        Returns:
            True if content is valid
        """
        if not content:
            return False

        cleaned_content = TextProcessor.clean_text(content)
        return len(cleaned_content) >= min_length

    @staticmethod
    def preprocess_for_llm(
        text: str,
        max_length: Optional[int] = None,
        remove_extra_whitespace: bool = True,
        normalize_quotes: bool = True,
    ) -> str:
        """
        Preprocess text for LLM input.

        Args:
            text: Text to preprocess
            max_length: Maximum length to truncate to
            remove_extra_whitespace: Whether to normalize whitespace
            normalize_quotes: Whether to normalize quote characters

        Returns:
            Preprocessed text
        """
        if not text:
            return ""

        # Clean HTML and entities
        text = TextProcessor.clean_html(text)

        # Normalize unicode
        text = TextProcessor.normalize_unicode(text)

        if remove_extra_whitespace:
            text = TextProcessor.normalize_whitespace(text)

        if normalize_quotes:
            # Normalize quote characters
            text = re.sub(r'["""]', '"', text)
            text = re.sub(r"['']", "'", text)

        if max_length:
            text = TextProcessor.truncate_text(text, max_length)

        return text.strip()
