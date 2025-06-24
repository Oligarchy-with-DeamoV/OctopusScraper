from typing import List
from unittest.mock import Mock, patch

import pytest

from octopus_scraper.scrapers.scraper import Scraper
from octopus_scraper.scrapers.scraper_protos import Content


class MockProcessor:
    """Mock处理器用于测试优先级"""

    def __init__(self, config, processor_name):
        from dataclasses import dataclass

        @dataclass
        class MockConfig:
            priority: int = 100

        # 模拟真实的processor config结构
        if isinstance(config, dict):
            priority = config.get("priority", 100)
            self.config = MockConfig(priority=priority)
        else:
            self.config = MockConfig()

        self.processor_name = processor_name
        self.call_order = []

    def __call__(self, contents: List[Content]) -> List[Content]:
        # 记录调用顺序
        if hasattr(MockProcessor, "global_call_order"):
            MockProcessor.global_call_order.append(self.processor_name)
        else:
            MockProcessor.global_call_order = [self.processor_name]

        # 修改内容以标记处理过
        for content in contents:
            if hasattr(content, "processed_by"):
                content.processed_by.append(self.processor_name)
            else:
                content.processed_by = [self.processor_name]

        return contents


class TestProcessorPriority:
    def setup_method(self):
        """每个测试方法前的设置"""
        MockProcessor.global_call_order = []

    def test_processor_priority_order(self):
        """测试处理器按照优先级顺序执行"""
        config = {
            "fetcher_name": "rsshub",
            "fetcher_config": {
                "hub_root": "https://example.com",
                "route": "/test",
                "fetch_params": {},
            },
            "content_processor_configs": {
                "html_content": {"timeout": 30, "priority": 10},  # 低优先级（后执行）
                "llm": {"prompt": "test prompt", "priority": 5},  # 高优先级（先执行）
                "filter": {"rules": [], "priority": 1},  # 最高优先级（最先执行）
            },
        }

        # Mock处理器
        def create_html_processor(config):
            return MockProcessor(config, "html_content")

        def create_llm_processor(config):
            return MockProcessor(config, "llm")

        def create_filter_processor(config):
            return MockProcessor(config, "filter")

        with patch(
            "octopus_scraper.scrapers.scraper.AVALIABLE_PROCESSOR",
            {
                "html_content": create_html_processor,
                "llm": create_llm_processor,
                "filter": create_filter_processor,
            },
        ):
            scraper = Scraper(config)

            # 验证优先级被正确设置
            assert scraper.processor_priorities["html_content"] == 10
            assert scraper.processor_priorities["llm"] == 5
            assert scraper.processor_priorities["filter"] == 1

            # 创建测试内容
            test_contents = [
                Content(
                    content_id="test1",
                    title="Test Article",
                    link="http://test.com",
                    summary="Test summary",
                    content="Test content",
                    published="2025-04-06T13:50:59+08:00",
                )
            ]

            # 执行处理
            processed_contents = scraper._content_process(test_contents)

            # 验证执行顺序：filter (1) -> llm (5) -> html_content (10)
            expected_order = ["filter", "llm", "html_content"]
            assert MockProcessor.global_call_order == expected_order

            # 验证内容被正确处理
            assert len(processed_contents) == 1
            assert processed_contents[0].processed_by == expected_order

    def test_processor_default_priority(self):
        """测试处理器默认优先级"""
        config = {
            "fetcher_name": "rsshub",
            "fetcher_config": {
                "hub_root": "https://example.com",
                "route": "/test",
                "fetch_params": {},
            },
            "content_processor_configs": {
                "html_content": {
                    "timeout": 30,
                    # 没有指定priority，应该使用默认值100
                },
                "llm": {"prompt": "test prompt", "priority": 50},  # 指定优先级
            },
        }

        def create_html_processor(config):
            return MockProcessor(config, "html_content")

        def create_llm_processor(config):
            return MockProcessor(config, "llm")

        with patch(
            "octopus_scraper.scrapers.scraper.AVALIABLE_PROCESSOR",
            {
                "html_content": create_html_processor,
                "llm": create_llm_processor,
            },
        ):
            scraper = Scraper(config)

            # 验证默认优先级
            assert scraper.processor_priorities["html_content"] == 100  # 默认值
            assert scraper.processor_priorities["llm"] == 50

            # 创建测试内容
            test_contents = [
                Content(
                    content_id="test1",
                    title="Test Article",
                    link="http://test.com",
                    summary="Test summary",
                    content="Test content",
                    published="2025-04-06T13:50:59+08:00",
                )
            ]

            # 执行处理
            processed_contents = scraper._content_process(test_contents)

            # 验证执行顺序：llm (50) -> html_content (100)
            expected_order = ["llm", "html_content"]
            assert MockProcessor.global_call_order == expected_order

    def test_processor_same_priority(self):
        """测试相同优先级的处理器执行顺序（应该保持字典顺序）"""
        config = {
            "fetcher_name": "rsshub",
            "fetcher_config": {
                "hub_root": "https://example.com",
                "route": "/test",
                "fetch_params": {},
            },
            "content_processor_configs": {
                "processor_a": {"priority": 50},
                "processor_b": {"priority": 50},
                "processor_c": {"priority": 50},
            },
        }

        def create_processor_a(config):
            return MockProcessor(config, "processor_a")

        def create_processor_b(config):
            return MockProcessor(config, "processor_b")

        def create_processor_c(config):
            return MockProcessor(config, "processor_c")

        with patch(
            "octopus_scraper.scrapers.scraper.AVALIABLE_PROCESSOR",
            {
                "processor_a": create_processor_a,
                "processor_b": create_processor_b,
                "processor_c": create_processor_c,
            },
        ):
            scraper = Scraper(config)

            # 验证优先级都相同
            assert scraper.processor_priorities["processor_a"] == 50
            assert scraper.processor_priorities["processor_b"] == 50
            assert scraper.processor_priorities["processor_c"] == 50

            # 创建测试内容
            test_contents = [
                Content(
                    content_id="test1",
                    title="Test Article",
                    link="http://test.com",
                    summary="Test summary",
                    content="Test content",
                    published="2025-04-06T13:50:59+08:00",
                )
            ]

            # 执行处理
            processed_contents = scraper._content_process(test_contents)

            # 验证执行顺序保持字典顺序（在Python 3.7+中是插入顺序）
            expected_order = ["processor_a", "processor_b", "processor_c"]
            assert MockProcessor.global_call_order == expected_order

    def test_processor_non_dict_config(self):
        """测试非字典类型的处理器配置（应该使用默认优先级）"""
        config = {
            "fetcher_name": "rsshub",
            "fetcher_config": {
                "hub_root": "https://example.com",
                "route": "/test",
                "fetch_params": {},
            },
            "content_processor_configs": {
                "simple_processor": "simple_config_string"  # 非字典配置
            },
        }

        def create_simple_processor(config):
            return MockProcessor(config, "simple_processor")

        with patch(
            "octopus_scraper.scrapers.scraper.AVALIABLE_PROCESSOR",
            {
                "simple_processor": create_simple_processor,
            },
        ):
            scraper = Scraper(config)

            # 验证默认优先级
            assert scraper.processor_priorities["simple_processor"] == 100

            # 验证处理器被正确初始化
            assert "simple_processor" in scraper.active_content_processor

    def test_realistic_html_llm_priority_scenario(self):
        """测试真实场景：HtmlContentProcessor 应该在 LLMProcessor 之前执行"""
        config = {
            "fetcher_name": "rsshub",
            "fetcher_config": {
                "hub_root": "https://example.com",
                "route": "/test",
                "fetch_params": {},
            },
            "content_processor_configs": {
                "llm": {
                    "prompt": "请总结这篇文章的主要内容",
                    "if_structure_output": False,
                    "priority": 20,  # LLM处理器应该在HTML处理器之后
                },
                "html_content": {
                    "timeout": 30,
                    "user_agent": "Mozilla/5.0",
                    "priority": 10,  # HTML处理器应该先执行
                },
            },
        }

        def create_html_processor(config):
            return MockProcessor(config, "html_content")

        def create_llm_processor(config):
            return MockProcessor(config, "llm")

        with patch(
            "octopus_scraper.scrapers.scraper.AVALIABLE_PROCESSOR",
            {
                "html_content": create_html_processor,
                "llm": create_llm_processor,
            },
        ):
            scraper = Scraper(config)

            # 创建测试内容
            test_contents = [
                Content(
                    content_id="test1",
                    title="Test Article",
                    link="http://test.com",
                    summary="Test summary",
                    content="Test content",
                    published="2025-04-06T13:50:59+08:00",
                )
            ]

            # 执行处理
            processed_contents = scraper._content_process(test_contents)

            # 验证执行顺序：html_content (10) -> llm (20)
            expected_order = ["html_content", "llm"]
            assert MockProcessor.global_call_order == expected_order

            print(f"处理器执行顺序: {MockProcessor.global_call_order}")
            print(
                f"处理器优先级: html_content={scraper.processor_priorities['html_content']}, llm={scraper.processor_priorities['llm']}"
            )
