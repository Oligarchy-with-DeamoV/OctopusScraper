import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from octopus_scraper.scrapers.processors.protos import LLMProcessorConfig
from octopus_scraper.scrapers.scraper_protos import Content

# 加载当前目录下的.env文件
current_dir = Path(__file__).parent
env_file = current_dir / ".env"
load_dotenv(env_file)


def check_llm_environment():
    """检查LLM环境变量是否正确设置"""
    required_vars = [
        "GPT_TEMPERATURE",
        "OPENAI_API_BASE",
        "OPENAI_API_VERSION",
        "OPENAI_API_KEY",
        "OPENAI_DEPLOYMENT_NAME",
        "OPENAI_API_TYPE",
        "OPENAI_MODEL_NAME",
    ]

    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)

    return len(missing_vars) == 0, missing_vars


@pytest.fixture(autouse=True)
def setup_llm_environment():
    """自动加载LLM环境变量的fixture"""
    env_ok, missing_vars = check_llm_environment()
    if not env_ok:
        pytest.skip(
            f"Missing required LLM environment variables: {missing_vars}. Please check .env file."
        )


@pytest.fixture
def llm_processor_config():
    """基础的LLM处理器配置"""
    return {
        "prompt": "请总结这篇文章的主要内容，提取关键信息。",
        "if_structure_output": False,
        "json_schema": None,
        "priority": 50,
    }


@pytest.fixture
def structured_llm_processor_config():
    """带结构化输出的LLM处理器配置"""
    json_schema = {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "文章摘要"},
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "关键词",
            },
            "category": {"type": "string", "description": "文章分类"},
        },
        "required": ["summary", "keywords", "category"],
    }

    return {
        "prompt": "请分析这篇文章并以JSON格式返回：1) 文章摘要(summary) 2) 关键词列表(keywords) 3) 文章分类(category)",
        "if_structure_output": True,
        "json_schema": json_schema,
        "priority": 50,
    }


@pytest.fixture
def sample_content():
    """测试用的样本内容"""
    return Content(
        content_id="test_001",
        title="人工智能技术的发展趋势",
        link="https://example.com/ai-trends",
        summary="人工智能技术正在快速发展，深度学习、机器学习等技术在各个领域都有重要应用。本文分析了AI技术的当前状态和未来发展方向，包括自然语言处理、计算机视觉、自动驾驶等重要领域。AI技术的发展将对社会产生深远影响。",
        content="详细的文章内容...",
        published="2024-01-01T00:00:00Z",
    )


@pytest.fixture
def sample_contents(sample_content):
    """多个测试内容的列表"""
    content2 = Content(
        content_id="test_002",
        title="云计算服务的比较分析",
        link="https://example.com/cloud-comparison",
        summary="本文对主流云计算服务提供商进行了详细比较，包括AWS、Azure、Google Cloud等平台的特点、价格、服务质量等方面。帮助企业选择最适合的云计算解决方案。",
        content="详细的云计算分析内容...",
        published="2024-01-02T00:00:00Z",
    )

    return [sample_content, content2]


def check_llm_environment():
    """检查LLM相关的环境变量是否设置"""
    required_env_vars = [
        "GPT_TEMPERATURE",
        "OPENAI_API_BASE",
        "OPENAI_API_VERSION",
        "OPENAI_API_KEY",
        "OPENAI_DEPLOYMENT_NAME",
        "OPENAI_API_TYPE",
        "OPENAI_MODEL_NAME",
    ]

    missing_vars = []
    for var in required_env_vars:
        if not os.getenv(var):
            missing_vars.append(var)

    return len(missing_vars) == 0, missing_vars
