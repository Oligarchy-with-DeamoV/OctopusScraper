"""
LLM module for OctopusScraper.

This module provides LLM-related functionality including client interfaces,
prompt management, schemas, and utilities.
"""

from octopus_scraper.llm.client import LLMClient, LLMConfig, LLMResponse
from octopus_scraper.llm.prompts import (
    KeywordsPromptManager,
    PromptLanguage,
    PromptManager,
    SummaryStyle,
    TagsPromptManager,
)
from octopus_scraper.llm.schemas import SchemaManager
from octopus_scraper.llm.utils import LLMUtils

__all__ = [
    "LLMClient",
    "LLMResponse",
    "LLMConfig",
    "LLMUtils",
    "PromptManager",
    "TagsPromptManager",
    "KeywordsPromptManager",
    "SummaryStyle",
    "PromptLanguage",
    "SchemaManager",
]
