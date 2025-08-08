"""
Utility functions for LLM operations.

This module provides helper functions for LLM-related tasks including
text preprocessing, response parsing, and common operations.
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.getLogger(__name__)


class LLMUtils:
    """Utility class for LLM-related operations."""

    @staticmethod
    def clean_text(text: str) -> str:
        """
        Clean text for LLM processing.

        Args:
            text: Raw text to clean

        Returns:
            Cleaned text
        """
        if not text:
            return ""

        # Remove excessive whitespace
        text = re.sub(r"\s+", " ", text)

        # Remove special characters that might confuse LLMs
        text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)

        # Trim whitespace
        text = text.strip()

        return text

    @staticmethod
    def truncate_text(
        text: str, max_tokens: int = 3000, chars_per_token: int = 4
    ) -> str:
        """
        Truncate text to fit within token limit.

        Args:
            text: Text to truncate
            max_tokens: Maximum number of tokens
            chars_per_token: Estimated characters per token

        Returns:
            Truncated text
        """
        max_chars = max_tokens * chars_per_token

        if len(text) <= max_chars:
            return text

        # Try to cut at sentence boundaries
        sentences = text.split(". ")
        truncated = ""

        for sentence in sentences:
            if len(truncated) + len(sentence) + 2 <= max_chars:
                if truncated:
                    truncated += ". " + sentence
                else:
                    truncated = sentence
            else:
                break

        # If no complete sentences fit, just truncate
        if not truncated:
            truncated = text[:max_chars]

        return truncated

    @staticmethod
    def extract_json_blocks(text: str) -> List[Dict[str, Any]]:
        """
        Extract all JSON blocks from text.

        Args:
            text: Text containing JSON blocks

        Returns:
            List of parsed JSON objects
        """
        json_blocks = []

        # Pattern for JSON in code blocks
        code_block_pattern = r"```(?:json)?\s*(.*?)\s*```"
        matches = re.findall(code_block_pattern, text, re.DOTALL | re.IGNORECASE)

        for match in matches:
            try:
                json_obj = json.loads(match.strip())
                json_blocks.append(json_obj)
            except json.JSONDecodeError:
                continue

        # Pattern for standalone JSON objects
        json_pattern = r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}"
        matches = re.findall(json_pattern, text)

        for match in matches:
            try:
                json_obj = json.loads(match)
                # Avoid duplicates
                if json_obj not in json_blocks:
                    json_blocks.append(json_obj)
            except json.JSONDecodeError:
                continue

        return json_blocks

    @staticmethod
    def format_content_for_llm(
        title: str, content: str, summary: Optional[str] = None
    ) -> str:
        """
        Format content for LLM processing.

        Args:
            title: Content title
            content: Main content text
            summary: Optional existing summary

        Returns:
            Formatted text for LLM
        """
        parts = []

        if title:
            parts.append(f"标题: {title}")

        if summary:
            parts.append(f"摘要: {summary}")

        if content:
            parts.append(f"内容:\n{content}")

        return "\n\n".join(parts)

    @staticmethod
    def estimate_processing_cost(
        text: str, model_name: str = "gpt-3.5-turbo"
    ) -> Dict[str, Any]:
        """
        Estimate the cost of processing text with an LLM.

        Args:
            text: Text to process
            model_name: Name of the LLM model

        Returns:
            Cost estimation dictionary
        """
        # Simple token estimation
        estimated_tokens = len(text) // 4 + 1

        # Rough cost estimates (in USD per 1K tokens)
        cost_per_1k_tokens = {
            "gpt-3.5-turbo": 0.0015,
            "gpt-4": 0.03,
            "gpt-4-turbo": 0.01,
            "claude-3-sonnet": 0.003,
            "claude-3-haiku": 0.00025,
        }

        rate = cost_per_1k_tokens.get(model_name, 0.002)  # Default rate
        estimated_cost = (estimated_tokens / 1000) * rate

        return {
            "estimated_tokens": estimated_tokens,
            "model": model_name,
            "cost_per_1k_tokens": rate,
            "estimated_cost_usd": round(estimated_cost, 6),
        }

    @staticmethod
    def create_prompt_with_context(base_prompt: str, context: Dict[str, Any]) -> str:
        """
        Create a prompt with context variables substituted.

        Args:
            base_prompt: Base prompt template with {variable} placeholders
            context: Dictionary of context variables

        Returns:
            Formatted prompt with context
        """
        try:
            return base_prompt.format(**context)
        except KeyError as e:
            logger.warning(f"Missing context variable: {e}")
            return base_prompt

    @staticmethod
    def validate_llm_response(
        response: str, expected_format: str = "text"
    ) -> Tuple[bool, str]:
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
                return True, ""
            except json.JSONDecodeError as e:
                return False, f"Invalid JSON: {str(e)}"

        elif expected_format == "list":
            # Check if response contains list-like content
            if not any(marker in response for marker in ["-", "•", "1.", "2.", "*"]):
                return False, "Response does not contain list format"

        # For "text" format, any non-empty response is valid
        return True, ""

    @staticmethod
    def extract_key_phrases(text: str, max_phrases: int = 10) -> List[str]:
        """
        Extract key phrases from text using simple heuristics.

        Args:
            text: Text to extract phrases from
            max_phrases: Maximum number of phrases to return

        Returns:
            List of key phrases
        """
        if not text:
            return []

        # Simple extraction based on common patterns
        phrases = []

        # Look for noun phrases (simplified)
        noun_pattern = r"\b[A-Z][a-z]+(?:\s+[a-z]+)*\b"
        matches = re.findall(noun_pattern, text)
        phrases.extend(matches[: max_phrases // 2])

        # Look for quoted phrases
        quoted_pattern = r'"([^"]+)"'
        quoted_matches = re.findall(quoted_pattern, text)
        phrases.extend(quoted_matches[: max_phrases // 4])

        # Look for emphasized phrases (words in CAPS)
        caps_pattern = r"\b[A-Z]{2,}\b"
        caps_matches = re.findall(caps_pattern, text)
        phrases.extend(caps_matches[: max_phrases // 4])

        # Remove duplicates and limit
        unique_phrases = list(dict.fromkeys(phrases))
        return unique_phrases[:max_phrases]

    @staticmethod
    def split_long_content(
        content: str, max_chunk_size: int = 2000, overlap: int = 200
    ) -> List[str]:
        """
        Split long content into overlapping chunks.

        Args:
            content: Content to split
            max_chunk_size: Maximum size of each chunk
            overlap: Number of characters to overlap between chunks

        Returns:
            List of content chunks
        """
        if len(content) <= max_chunk_size:
            return [content]

        chunks = []
        start = 0

        while start < len(content):
            end = start + max_chunk_size

            # Try to break at sentence boundary
            if end < len(content):
                # Look for sentence end within the last 10% of the chunk
                search_start = max(start + max_chunk_size - 200, start)
                sentence_end = content.rfind(".", search_start, end)

                if sentence_end > search_start:
                    end = sentence_end + 1

            chunk = content[start:end]
            chunks.append(chunk.strip())

            # Move start position with overlap
            start = max(end - overlap, start + 1)

            if start >= len(content):
                break

        return chunks
