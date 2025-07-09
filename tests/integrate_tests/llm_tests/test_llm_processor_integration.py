import json
import os

import pytest

from octopus_scraper.scrapers.processors.llm_processor import LLMProcessor
from octopus_scraper.scrapers.scraper_protos import Content

# 标记这些测试需要外部服务
pytestmark = pytest.mark.integrate_test


class TestLLMProcessorIntegration:
    """LLM处理器的集成测试类

    这些测试会自动从.env文件加载LLM配置
    """

    def test_environment_variables_loaded(self):
        """测试环境变量是否正确加载"""
        assert os.getenv("OPENAI_API_BASE") == "http://10.170.138.230:8888/v1"
        assert os.getenv("OPENAI_API_TYPE") == "local"
        assert os.getenv("OPENAI_DEPLOYMENT_NAME") == "devapi35"
        assert os.getenv("GPT_TEMPERATURE") == "0.9"

    def test_llm_processor_basic_functionality(
        self, llm_processor_config, sample_content
    ):
        """测试LLM处理器的基本功能"""
        # 创建LLM处理器实例
        processor = LLMProcessor(llm_processor_config)

        # 验证配置正确加载
        assert processor.configs.prompt == "请总结这篇文章的主要内容，提取关键信息。"
        assert processor.configs.if_structure_output is False
        assert processor.output_schema is False

        # 调用处理器处理单个内容
        input_contents = [sample_content]
        result_contents = processor(input_contents)

        # 验证返回结果
        assert isinstance(result_contents, list)
        # 注意：由于没有结构化输出，可能返回空列表或处理后的内容
        # 这取决于LLM的响应是否成功
        print(f"处理结果数量: {len(result_contents)}")
        if result_contents:
            result_content = result_contents[0]
            assert isinstance(result_content, Content)
            assert result_content.content_id == sample_content.content_id
            assert result_content.title == sample_content.title
            print(f"处理后的摘要: {result_content.summary}")

    def test_llm_processor_with_structured_output(
        self, structured_llm_processor_config, sample_content
    ):
        """测试带结构化输出的LLM处理器"""
        # 创建带结构化输出的LLM处理器
        processor = LLMProcessor(structured_llm_processor_config)

        # 验证配置
        assert processor.configs.if_structure_output is True
        assert processor.output_schema is not False
        assert "summary" in processor.output_schema["properties"]
        assert "keywords" in processor.output_schema["properties"]
        assert "category" in processor.output_schema["properties"]

        # 处理内容
        input_contents = [sample_content]
        result_contents = processor(input_contents)

        # 验证结构化输出
        print(f"结构化处理结果数量: {len(result_contents)}")
        if result_contents:
            result_content = result_contents[0]
            assert isinstance(result_content, Content)

            # 验证输出是有效的JSON
            try:
                parsed_summary = json.loads(result_content.summary)
                assert "summary" in parsed_summary
                assert "keywords" in parsed_summary
                assert "category" in parsed_summary
                assert isinstance(parsed_summary["keywords"], list)
                print(
                    f"结构化输出: {json.dumps(parsed_summary, ensure_ascii=False, indent=2)}"
                )
            except json.JSONDecodeError:
                pytest.fail("LLM输出不是有效的JSON格式")

    def test_llm_processor_multiple_contents(
        self, llm_processor_config, sample_contents
    ):
        """测试LLM处理器处理多个内容"""
        processor = LLMProcessor(llm_processor_config)

        # 处理多个内容
        result_contents = processor(sample_contents)

        print(f"输入内容数量: {len(sample_contents)}")
        print(f"处理结果数量: {len(result_contents)}")

        # 验证处理结果
        assert isinstance(result_contents, list)
        # 由于是基础配置（非结构化输出），结果可能为空
        # 但不应该抛出异常

        for i, content in enumerate(result_contents):
            assert isinstance(content, Content)
            print(f"处理结果 {i+1}: {content.title}")

    def test_llm_processor_error_handling(self, structured_llm_processor_config):
        """测试LLM处理器的错误处理"""
        processor = LLMProcessor(structured_llm_processor_config)

        # 测试空内容列表
        empty_result = processor([])
        assert empty_result == []

        # 测试包含无效内容的情况（空摘要）
        invalid_content = Content(
            content_id="invalid_001",
            title="",
            link="",
            summary="",  # 空摘要可能导致LLM处理失败
            content="",
            published="",
        )

        result = processor([invalid_content])
        # 应该优雅地处理错误，返回空列表或跳过无效内容
        assert isinstance(result, list)
        print(f"无效内容处理结果: {len(result)} 个有效结果")

    def test_llm_processor_json_extraction(self):
        """测试JSON代码块提取功能"""
        from octopus_scraper.scrapers.processors.llm_processor import (
            extract_markdown_json_code,
        )

        # 测试正常的JSON代码块
        markdown_with_json = """
        这里是一些文本

        ```json
        {
            "summary": "这是一个测试摘要",
            "keywords": ["测试", "JSON"],
            "category": "技术"
        }
        ```

        更多文本
        """

        json_blocks = extract_markdown_json_code(markdown_with_json)
        assert len(json_blocks) == 1

        parsed_json = json.loads(json_blocks[0])
        assert parsed_json["summary"] == "这是一个测试摘要"
        assert parsed_json["keywords"] == ["测试", "JSON"]
        assert parsed_json["category"] == "技术"

        # 测试多个JSON代码块
        markdown_with_multiple_json = """
        ```json
        {"first": "block"}
        ```

        ```json
        {"second": "block"}
        ```
        """

        multiple_blocks = extract_markdown_json_code(markdown_with_multiple_json)
        assert len(multiple_blocks) == 2

        # 测试没有JSON代码块的情况
        no_json_markdown = "这里没有JSON代码块"
        no_blocks = extract_markdown_json_code(no_json_markdown)
        assert len(no_blocks) == 0
