"""
Prompt management system for LLM processors.

This module provides a centralized system for managing prompts used by
different LLM processors, including templates, localization, and customization.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.getLogger(__name__)


class PromptLanguage(Enum):
    """Supported prompt languages."""

    CHINESE = "zh"
    ENGLISH = "en"
    MIXED = "mixed"


class SummaryStyle(Enum):
    """Summary styles for summary processor."""

    CONCISE = "concise"
    DETAILED = "detailed"
    BULLET_POINTS = "bullet_points"
    EXECUTIVE = "executive"


class PromptTemplate:
    """A prompt template with support for variable substitution."""

    def __init__(self, template: str, variables: Optional[List[str]] = None):
        """
        Initialize prompt template.

        Args:
            template: The prompt template string with {variable} placeholders
            variables: List of expected variable names
        """
        self.template = template
        self.variables = variables or []

    def format(self, **kwargs) -> str:
        """
        Format the template with provided variables.

        Args:
            **kwargs: Variables to substitute in template

        Returns:
            Formatted prompt string
        """
        try:
            return self.template.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Missing variable in prompt template: {e}")
            return self.template

    def validate_variables(self, **kwargs) -> bool:
        """
        Validate that all required variables are provided.

        Args:
            **kwargs: Variables to validate

        Returns:
            True if all required variables are present
        """
        missing = [var for var in self.variables if var not in kwargs]
        if missing:
            logger.warning(f"Missing required variables: {missing}")
            return False
        return True


class SummaryPrompts:
    """Prompt templates for summary generation."""

    # Base system prompt for summary generation
    SYSTEM_PROMPT = PromptTemplate(
        """你是一位专业的内容编辑和摘要专家。你的任务是为各种类型的文章生成高质量的摘要。

请遵循以下原则：
1. 准确捕捉文章的核心信息和主要观点
2. 保持摘要的客观性和中性立场
3. 使用清晰、简洁的语言
4. 根据指定的风格和长度要求进行调整
5. 保持原文的语言风格（中文/英文/混合）

你将收到文章的标题、内容，以及具体的摘要要求。请严格按照要求生成摘要。""",
        [],
    )

    # Concise style prompts
    CONCISE_PROMPTS = {
        PromptLanguage.CHINESE: PromptTemplate(
            """请为以下文章生成一个简洁的摘要，长度控制在{max_length}字以内：

标题：{title}

内容：
{content}

要求：
- 突出文章的核心观点
- 使用简洁明了的语言
- 保持信息的准确性
- 长度不超过{max_length}字

摘要：""",
            ["title", "content", "max_length"],
        ),
        PromptLanguage.ENGLISH: PromptTemplate(
            """Please generate a concise summary for the following article, limited to {max_length} words:

Title: {title}

Content:
{content}

Requirements:
- Highlight the core points of the article
- Use clear and concise language
- Maintain information accuracy
- Length should not exceed {max_length} words

Summary:""",
            ["title", "content", "max_length"],
        ),
        PromptLanguage.MIXED: PromptTemplate(
            """请为以下文章生成简洁摘要，长度控制在{max_length}字/词以内：

标题/Title：{title}

内容/Content：
{content}

要求/Requirements：
- 保持原文的语言风格
- 突出核心观点/Highlight key points
- 简洁明了/Clear and concise
- 长度限制/Length limit：{max_length}字/words

摘要/Summary：""",
            ["title", "content", "max_length"],
        ),
    }

    # Detailed style prompts
    DETAILED_PROMPTS = {
        PromptLanguage.CHINESE: PromptTemplate(
            """请为以下文章生成一个详细的摘要，长度控制在{max_length}字以内：

标题：{title}

内容：
{content}

要求：
- 包含文章的主要论点和支撑证据
- 保留重要的细节和例子
- 结构清晰，逻辑连贯
- 长度不超过{max_length}字

详细摘要：""",
            ["title", "content", "max_length"],
        ),
        PromptLanguage.ENGLISH: PromptTemplate(
            """Please generate a detailed summary for the following article, limited to {max_length} words:

Title: {title}

Content:
{content}

Requirements:
- Include main arguments and supporting evidence
- Preserve important details and examples
- Maintain clear structure and logical flow
- Length should not exceed {max_length} words

Detailed Summary:""",
            ["title", "content", "max_length"],
        ),
    }

    # Bullet points style prompts
    BULLET_POINTS_PROMPTS = {
        PromptLanguage.CHINESE: PromptTemplate(
            """请为以下文章生成要点式摘要，用项目符号列出{max_points}个主要要点：

标题：{title}

内容：
{content}

要求：
- 每个要点简洁明了
- 按重要性排序
- 涵盖文章的核心信息
- 最多{max_points}个要点

要点摘要：""",
            ["title", "content", "max_points"],
        ),
        PromptLanguage.ENGLISH: PromptTemplate(
            """Please generate a bullet-point summary for the following article, listing {max_points} main points:

Title: {title}

Content:
{content}

Requirements:
- Each point should be clear and concise
- Order by importance
- Cover core information
- Maximum {max_points} points

Bullet-Point Summary:""",
            ["title", "content", "max_points"],
        ),
    }

    # Executive style prompts (for business/technical content)
    EXECUTIVE_PROMPTS = {
        PromptLanguage.CHINESE: PromptTemplate(
            """请为以下文章生成执行摘要，适用于管理层阅读，长度控制在{max_length}字以内：

标题：{title}

内容：
{content}

要求：
- 突出关键发现和建议
- 包含actionable insights
- 适合决策者快速了解
- 重点关注影响和结果
- 长度不超过{max_length}字

执行摘要：""",
            ["title", "content", "max_length"],
        ),
        PromptLanguage.ENGLISH: PromptTemplate(
            """Please generate an executive summary for the following article, suitable for management review, limited to {max_length} words:

Title: {title}

Content:
{content}

Requirements:
- Highlight key findings and recommendations
- Include actionable insights
- Suitable for decision-makers
- Focus on impact and outcomes
- Length should not exceed {max_length} words

Executive Summary:""",
            ["title", "content", "max_length"],
        ),
    }

    @classmethod
    def get_prompt(
        cls, style: SummaryStyle, language: PromptLanguage
    ) -> Optional[PromptTemplate]:
        """
        Get prompt template for specific style and language.

        Args:
            style: Summary style
            language: Prompt language

        Returns:
            PromptTemplate or None if not found
        """
        style_mapping = {
            SummaryStyle.CONCISE: cls.CONCISE_PROMPTS,
            SummaryStyle.DETAILED: cls.DETAILED_PROMPTS,
            SummaryStyle.BULLET_POINTS: cls.BULLET_POINTS_PROMPTS,
            SummaryStyle.EXECUTIVE: cls.EXECUTIVE_PROMPTS,
        }

        prompts = style_mapping.get(style, {})
        return prompts.get(language)

    @classmethod
    def get_all_styles(cls) -> List[SummaryStyle]:
        """Get all available summary styles."""
        return list(SummaryStyle)

    @classmethod
    def get_supported_languages(cls, style: SummaryStyle) -> List[PromptLanguage]:
        """
        Get supported languages for a specific style.

        Args:
            style: Summary style

        Returns:
            List of supported languages
        """
        style_mapping = {
            SummaryStyle.CONCISE: cls.CONCISE_PROMPTS,
            SummaryStyle.DETAILED: cls.DETAILED_PROMPTS,
            SummaryStyle.BULLET_POINTS: cls.BULLET_POINTS_PROMPTS,
            SummaryStyle.EXECUTIVE: cls.EXECUTIVE_PROMPTS,
        }

        prompts = style_mapping.get(style, {})
        return list(prompts.keys())


class TagsPrompts:
    """
    Prompt templates for tag generation processor.

    This class contains all prompts related to intelligent tag generation
    for content classification and organization.
    """

    SYSTEM_PROMPT = PromptTemplate(
        """你是一个专业的内容标签分析师。你的任务是为给定的文章内容生成准确、相关的标签。

请遵循以下原则：
1. 标签应该准确反映文章的主要主题和内容
2. 优先选择具体且有意义的标签，避免过于宽泛的标签
3. 标签应该有助于内容的分类和检索
4. 支持中英文标签，保持与原文语言的一致性
5. 标签长度控制在1-3个词之间

输出格式要求：
- 返回JSON格式的结构化数据
- 包含tags数组，每个标签为字符串
- 可选择包含confidence置信度评分
- 标签按重要性排序""",
        [],
    )

    # Chinese prompts
    GENERATE_TAGS_ZH = PromptTemplate(
        """请为以下文章生成{max_tags}个最相关的标签：

标题：{title}

内容：{content}

{summary_context}

要求：
1. 生成{max_tags}个标签，按重要性排序
2. 标签要准确反映文章主题
3. 优先使用中文标签
4. 避免过于宽泛或模糊的标签
5. 标签应具有分类和检索价值

请以JSON格式返回结果：
{{
    "tags": ["标签1", "标签2", "标签3"],
    "confidence": {{
        "标签1": 0.95,
        "标签2": 0.87,
        "标签3": 0.76
    }}
}}""",
        ["title", "content", "max_tags"],
    )

    # English prompts
    GENERATE_TAGS_EN = PromptTemplate(
        """Please generate {max_tags} most relevant tags for the following article:

Title: {title}

Content: {content}

{summary_context}

Requirements:
1. Generate {max_tags} tags, ordered by importance
2. Tags should accurately reflect the article's themes
3. Use specific and meaningful tags, avoid overly broad ones
4. Tags should be valuable for classification and retrieval
5. Keep tags concise (1-3 words)

Please return in JSON format:
{{
    "tags": ["tag1", "tag2", "tag3"],
    "confidence": {{
        "tag1": 0.95,
        "tag2": 0.87,
        "tag3": 0.76
    }}
}}""",
        ["title", "content", "max_tags"],
    )

    # Mixed language prompts
    GENERATE_TAGS_MIXED = PromptTemplate(
        """Generate {max_tags} relevant tags for this article (支持中英文标签):

标题/Title: {title}

内容/Content: {content}

{summary_context}

要求/Requirements:
1. 生成{max_tags}个标签 / Generate {max_tags} tags
2. 标签可以是中文或英文 / Tags can be in Chinese or English
3. 选择最能代表文章主题的标签 / Choose tags that best represent the article's theme
4. 标签应有分类价值 / Tags should have classification value

Please return in JSON format:
{{
    "tags": ["标签1", "tag2", "标签3"],
    "confidence": {{
        "标签1": 0.95,
        "tag2": 0.87,
        "标签3": 0.76
    }}
}}""",
        ["title", "content", "max_tags"],
    )


class KeywordsPrompts:
    """
    Prompt templates for keywords extraction processor.

    This class contains all prompts related to keyword extraction
    and phrase identification from content.
    """

    SYSTEM_PROMPT = PromptTemplate(
        """你是一个专业的关键词提取专家。你的任务是从文章内容中提取最重要的关键词和短语。

请遵循以下原则：
1. 提取能够代表文章核心内容的关键词
2. 包含专业术语、人名、地名、机构名等重要实体
3. 优先选择具有检索价值的词汇
4. 避免停用词和过于常见的词汇
5. 支持中英文关键词提取

输出格式要求：
- 返回JSON格式的结构化数据
- 包含keywords数组
- 提供重要性评分
- 按重要性排序""",
        [],
    )

    # Chinese prompts
    EXTRACT_KEYWORDS_ZH = PromptTemplate(
        """请从以下文章中提取{keywords_count}个最重要的关键词：

标题：{title}

内容：{content}

{summary_context}

要求：
1. 提取{keywords_count}个关键词，按重要性排序
2. 关键词应该是文章的核心概念
3. 包含专业术语、实体名称等
4. 避免常见的停用词
5. 优先选择有检索价值的词汇

请以JSON格式返回结果：
{{
    "keywords": ["关键词1", "关键词2", "关键词3"],
    "importance_scores": {{
        "关键词1": 0.95,
        "关键词2": 0.87,
        "关键词3": 0.76
    }}
}}""",
        ["title", "content", "keywords_count"],
    )

    # English prompts
    EXTRACT_KEYWORDS_EN = PromptTemplate(
        """Please extract {keywords_count} most important keywords from the following article:

Title: {title}

Content: {content}

{summary_context}

Requirements:
1. Extract {keywords_count} keywords, ordered by importance
2. Keywords should represent core concepts of the article
3. Include technical terms, entity names, etc.
4. Avoid common stop words
5. Prioritize words with search value

Please return in JSON format:
{{
    "keywords": ["keyword1", "keyword2", "keyword3"],
    "importance_scores": {{
        "keyword1": 0.95,
        "keyword2": 0.87,
        "keyword3": 0.76
    }}
}}""",
        ["title", "content", "keywords_count"],
    )

    # Mixed language prompts
    EXTRACT_KEYWORDS_MIXED = PromptTemplate(
        """Extract {keywords_count} important keywords from this article (支持中英文关键词):

标题/Title: {title}

内容/Content: {content}

{summary_context}

要求/Requirements:
1. 提取{keywords_count}个关键词 / Extract {keywords_count} keywords
2. 关键词可以是中文或英文 / Keywords can be in Chinese or English
3. 选择最能代表文章核心的词汇 / Choose words that best represent the article's core
4. 包含专业术语和实体 / Include technical terms and entities

Please return in JSON format:
{{
    "keywords": ["关键词1", "keyword2", "关键词3"],
    "importance_scores": {{
        "关键词1": 0.95,
        "keyword2": 0.87,
        "关键词3": 0.76
    }}
}}""",
        ["title", "content", "keywords_count"],
    )


class TagsPromptManager:
    """Manager for tags generation prompts."""

    def __init__(self):
        self.prompts = TagsPrompts()

    def get_prompt(self, language: PromptLanguage) -> PromptTemplate:
        """Get appropriate prompt based on language."""
        if language == PromptLanguage.CHINESE:
            return self.prompts.GENERATE_TAGS_ZH
        elif language == PromptLanguage.ENGLISH:
            return self.prompts.GENERATE_TAGS_EN
        else:  # MIXED
            return self.prompts.GENERATE_TAGS_MIXED

    def create_messages(
        self,
        title: str,
        content: str,
        max_tags: int = 5,
        language: PromptLanguage = PromptLanguage.CHINESE,
        summary_context: str = "",
    ) -> List[Dict[str, str]]:
        """Create complete message list for tag generation."""
        user_prompt = self.get_prompt(language).format(
            title=title,
            content=content,
            max_tags=max_tags,
            summary_context=summary_context or "",
        )

        messages = [
            {"role": "system", "content": self.prompts.SYSTEM_PROMPT.format()},
            {"role": "user", "content": user_prompt},
        ]

        return messages


class KeywordsPromptManager:
    """Manager for keywords extraction prompts."""

    def __init__(self):
        self.prompts = KeywordsPrompts()

    def get_prompt(self, language: PromptLanguage) -> PromptTemplate:
        """Get appropriate prompt based on language."""
        if language == PromptLanguage.CHINESE:
            return self.prompts.EXTRACT_KEYWORDS_ZH
        elif language == PromptLanguage.ENGLISH:
            return self.prompts.EXTRACT_KEYWORDS_EN
        else:  # MIXED
            return self.prompts.EXTRACT_KEYWORDS_MIXED

    def create_messages(
        self,
        title: str,
        content: str,
        keywords_count: int = 10,
        language: PromptLanguage = PromptLanguage.CHINESE,
        summary_context: str = "",
    ) -> List[Dict[str, str]]:
        """Create complete message list for keywords extraction."""
        user_prompt = self.get_prompt(language).format(
            title=title,
            content=content,
            keywords_count=keywords_count,
            summary_context=summary_context or "",
        )

        messages = [
            {"role": "system", "content": self.prompts.SYSTEM_PROMPT.format()},
            {"role": "user", "content": user_prompt},
        ]

        return messages


class PromptManager:
    """Central manager for all prompt templates."""

    def __init__(self):
        """Initialize the prompt manager."""
        self.summary_prompts = SummaryPrompts()
        self.tags_prompt_manager = TagsPromptManager()
        self.keywords_prompt_manager = KeywordsPromptManager()

    def get_summary_prompt(
        self, style: str, language: str = "zh"
    ) -> Optional[PromptTemplate]:
        """
        Get summary prompt template.

        Args:
            style: Summary style string
            language: Language code

        Returns:
            PromptTemplate or None
        """
        try:
            style_enum = SummaryStyle(style)
            lang_enum = PromptLanguage(language)
            return self.summary_prompts.get_prompt(style_enum, lang_enum)
        except ValueError as e:
            logger.error(f"Invalid style or language: {e}")
            return None

    def create_summary_messages(
        self,
        title: str,
        content: str,
        style: str = "concise",
        language: str = "zh",
        max_length: int = 200,
        max_points: int = 5,
    ) -> List[Dict[str, str]]:
        """
        Create complete message list for summary generation.

        Args:
            title: Article title
            content: Article content
            style: Summary style
            language: Language preference
            max_length: Maximum summary length
            max_points: Maximum points for bullet style

        Returns:
            List of message dictionaries for LLM
        """
        prompt_template = self.get_summary_prompt(style, language)
        if not prompt_template:
            # Fallback to concise Chinese
            prompt_template = self.get_summary_prompt("concise", "zh")

        if not prompt_template:
            raise ValueError("No suitable prompt template found")

        # Prepare variables
        variables = {
            "title": title,
            "content": content,
            "max_length": max_length,
            "max_points": max_points,
        }

        # Format user prompt
        user_prompt = prompt_template.format(**variables)

        # Create message list
        messages = [
            {"role": "system", "content": SummaryPrompts.SYSTEM_PROMPT.format()},
            {"role": "user", "content": user_prompt},
        ]

        return messages

    def create_tags_messages(
        self,
        title: str,
        content: str,
        max_tags: int = 5,
        language: str = "zh",
        summary_context: str = "",
    ) -> List[Dict[str, str]]:
        """Create messages for tag generation."""
        lang_enum = PromptLanguage(language)
        return self.tags_prompt_manager.create_messages(
            title=title,
            content=content,
            max_tags=max_tags,
            language=lang_enum,
            summary_context=summary_context,
        )

    def create_keywords_messages(
        self,
        title: str,
        content: str,
        keywords_count: int = 10,
        language: str = "zh",
        summary_context: str = "",
    ) -> List[Dict[str, str]]:
        """Create messages for keywords extraction."""
        lang_enum = PromptLanguage(language)
        return self.keywords_prompt_manager.create_messages(
            title=title,
            content=content,
            keywords_count=keywords_count,
            language=lang_enum,
            summary_context=summary_context,
        )

    def validate_prompt_variables(self, style: str, language: str, **kwargs) -> bool:
        """
        Validate that all required variables are provided for a prompt.

        Args:
            style: Summary style
            language: Language code
            **kwargs: Variables to validate

        Returns:
            True if valid
        """
        prompt_template = self.get_summary_prompt(style, language)
        if not prompt_template:
            return False

        return prompt_template.validate_variables(**kwargs)

    def get_available_styles(self) -> List[str]:
        """Get list of available summary styles."""
        return [style.value for style in SummaryStyle]

    def get_available_languages(self) -> List[str]:
        """Get list of available languages."""
        return [lang.value for lang in PromptLanguage]
