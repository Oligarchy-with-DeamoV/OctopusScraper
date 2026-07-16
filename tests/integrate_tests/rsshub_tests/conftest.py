import os
from dataclasses import asdict
from pathlib import Path

import pytest
from dotenv import load_dotenv

from octopus_scraper.scraper import BaseScraperConfig

# 加载环境变量，包括LLM配置
load_dotenv()

# 也尝试加载LLM测试的.env文件
llm_env_file = Path(__file__).parent.parent / "llm_tests" / ".env"
if llm_env_file.exists():
    load_dotenv(llm_env_file)


@pytest.fixture
def owen_scraper_config():
    return BaseScraperConfig(
        fetcher_name="rsshub",
        fetcher_config={
            "hub_root": "https://www.owenyoung.com",
            "route": "/atom.xml",
            "fetch_params": {},
        },
        content_processor_configs={},
    )


@pytest.fixture
def machine_heart_scraper_config():
    return BaseScraperConfig(
        fetcher_name="rsshub",
        fetcher_config={
            "hub_root": "https://raw.githubusercontent.com",
            "route": "/osnsyc/Wechat-Scholar/main/channels/gh_dbc0a5474692.xml",
            "fetch_params": {},
        },
        content_processor_configs={},
    )


@pytest.fixture
def qbitai_scraper_config():
    return BaseScraperConfig(
        fetcher_name="rsshub",
        fetcher_config={
            "hub_root": "https://rss.owo.nz",
            "route": "/qbitai/category/资讯",
            "fetch_params": {"limit": 1},
        },
        content_processor_configs={},
    )


@pytest.fixture
def octopus_config(
    owen_scraper_config,
    machine_heart_scraper_config,
    qbitai_scraper_config,
    tmp_path,
):
    return {
        "scrapers_config_with_fetch_params": [
            {
                "scraper_config": asdict(owen_scraper_config),
                "fetch_params": {},
                "scraper_id": "owen",
            },
            {
                "scraper_config": asdict(machine_heart_scraper_config),
                "fetch_params": {},
                "scraper_id": "machine-heart",
            },
            {
                "scraper_config": asdict(qbitai_scraper_config),
                "fetch_params": {"limit": 1},
                "scraper_id": "qbitai",
            },
        ],
        "database_config": {
            "url": os.getenv(
                "DATABASE_URL",
                f"sqlite:///{tmp_path / 'integration-contents.sqlite3'}",
            )
        },
        "notion_sync_config": {
            "enabled": bool(os.getenv("NOTION_API_KEY")),
            "api_key": os.getenv("NOTION_API_KEY", ""),
            "database_id": os.getenv("NOTION_CONTENT_DATABASE_ID", ""),
        },
        "task_manager_config": {
            "persistence_path": str(tmp_path / "integration-tasks.sqlite3")
        },
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
        "priority": 100,
    }
