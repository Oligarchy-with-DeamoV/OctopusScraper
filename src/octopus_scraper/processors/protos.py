from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ProcessorConfig:
    """Base configuration for all processors."""

    priority: int = field(default=100)  # 默认优先级为100，数值越小优先级越高


@dataclass
class LLMProcessorConfig(ProcessorConfig):
    """Legacy LLM processor configuration (deprecated)."""

    prompt: str = field(default="")  # 设置默认值避免dataclass错误
    if_structure_output: bool = field(default=False)
    json_schema: Optional[Dict] = field(default=None)


@dataclass
class BaseLLMProcessorConfig(ProcessorConfig):
    """Base configuration for new LLM processors."""

    model_name: str = field(default="gpt-3.5-turbo")
    max_tokens: int = field(default=1000)
    temperature: float = field(default=0.7)
    timeout: int = field(default=30)
    timeout_seconds: int = field(default=30)
    retry_times: int = field(default=3)
    api_key: Optional[str] = field(default=None)
    api_base: Optional[str] = field(default=None)
    base_url: Optional[str] = field(default=None)
    llm_provider: str = field(default="openai")
    fail_fast: bool = field(default=False)
    enable_fallback: bool = field(default=True)


@dataclass
class SummaryProcessorConfig(BaseLLMProcessorConfig):
    """Configuration for summary processor."""

    max_summary_length: int = field(default=200)
    summary_style: str = field(default="concise")  # concise, detailed, bullet_points
    preserve_structure: bool = field(default=False)
    include_key_points: bool = field(default=True)


@dataclass
class TagsProcessorConfig(BaseLLMProcessorConfig):
    """Configuration for tags processor."""

    available_tags: List[str] = field(default_factory=list)
    max_tags_count: int = field(default=5)
    max_tags: int = field(default=5)
    custom_categories: Dict[str, List[str]] = field(default_factory=dict)
    allow_new_tags: bool = field(default=True)
    confidence_threshold: float = field(default=0.5)


@dataclass
class KeywordsProcessorConfig(BaseLLMProcessorConfig):
    """Configuration for keywords processor."""

    keywords_count: int = field(default=3)
    max_keywords: int = field(default=10)
    min_keyword_length: int = field(default=2)
    max_keyword_length: int = field(default=20)
    exclude_common_words: bool = field(default=True)
    include_phrases: bool = field(default=True)
    language_preference: str = field(default="mixed")  # en, zh, mixed
    exclude_patterns: Optional[List[str]] = field(default=None)
    custom_stop_words: Optional[List[str]] = field(default=None)
    min_importance_score: float = field(default=0.0)
