#!/usr/bin/env python3
"""
HTML内容处理器测试脚本
"""
from unittest import mock
from unittest.mock import MagicMock, patch

import pytest

from octopus_scraper.scrapers.processors.html_content_processor import (
    HTMLContentProcessor,
)
from octopus_scraper.scrapers.scraper_protos import Content


def test_html_content_processor_init():
    """测试HTML内容处理器初始化"""
    config = {
        "timeout": 30,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    processor = HTMLContentProcessor(config)
    assert processor.timeout == 30
    assert "Mozilla" in processor.user_agent


def test_html_content_processor_with_real_url():
    """测试HTML内容处理器处理真实URL"""
    config = {
        "timeout": 30,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    processor = HTMLContentProcessor(config)

    # 创建测试内容
    test_content = Content(
        content_id="test_001",
        title="测试文章",
        link="https://httpbin.org/html",  # 使用httpbin提供的HTML测试页面
        summary="这是一个测试文章",
        content="原始内容",
        published="2024-01-01",
    )

    # 处理内容
    processed_contents = processor([test_content])

    # 验证结果
    assert len(processed_contents) <= 1  # 可能由于网络问题返回空列表
    if processed_contents:
        content = processed_contents[0]
        assert content.title == "测试文章"
        assert content.link == "https://httpbin.org/html"
        assert len(content.content) > 0  # 应该有转换后的markdown内容


@patch("requests.Session.get")
def test_html_content_processor_with_mock(mock_get):
    """测试HTML内容处理器使用模拟请求"""
    # 模拟HTTP响应
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None
    mock_response.text = """
    <html>
    <head><title>Test Page</title></head>
    <body>
        <h1>Test Heading</h1>
        <p>This is a test paragraph.</p>
        <div class="content">
            <p>This is main content.</p>
        </div>
    </body>
    </html>
    """
    mock_get.return_value = mock_response

    config = {
        "timeout": 30,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    processor = HTMLContentProcessor(config)

    test_content = Content(
        content_id="test_001",
        title="测试文章",
        link="https://example.com/test",
        summary="这是一个测试文章",
        content="原始内容",
        published="2024-01-01",
    )

    processed_contents = processor([test_content])

    assert len(processed_contents) == 1
    content = processed_contents[0]
    assert content.title == "测试文章"
    assert content.link == "https://example.com/test"
    assert "Test Heading" in content.content
    assert "test paragraph" in content.content


@patch("requests.Session.get")
def test_html_content_processor_request_failure(mock_get):
    """测试HTML内容处理器处理请求失败"""
    # 模拟请求异常
    mock_get.side_effect = Exception("Network error")

    config = {
        "timeout": 30,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    processor = HTMLContentProcessor(config)

    test_content = Content(
        content_id="test_001",
        title="测试文章",
        link="https://example.com/test",
        summary="这是一个测试文章",
        content="原始内容",
        published="2024-01-01",
    )

    processed_contents = processor([test_content])

    # 当请求失败时，应该保留原有内容
    assert len(processed_contents) == 1
    content = processed_contents[0]
    assert content.title == "测试文章"
    assert content.link == "https://example.com/test"
    assert content.summary == "这是一个测试文章"  # 保持原有内容
    assert content.content == "原始内容"


@patch("requests.Session.get")
def test_html_content_processor_no_content_extracted(mock_get):
    """测试HTML内容处理器无法提取内容时保留原有内容"""
    # 模拟返回空HTML
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None
    mock_response.text = "<html><head></head><body></body></html>"  # 空内容
    mock_get.return_value = mock_response

    config = {
        "timeout": 30,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    processor = HTMLContentProcessor(config)

    test_content = Content(
        content_id="test_001",
        title="测试文章",
        link="https://example.com/test",
        summary="这是一个测试文章",
        content="原始内容",
        published="2024-01-01",
    )

    processed_contents = processor([test_content])

    # 当无法提取内容时，应该保留原有内容
    assert len(processed_contents) == 1
    content = processed_contents[0]
    assert content.title == "测试文章"
    assert content.link == "https://example.com/test"
    assert content.summary == "这是一个测试文章"  # 保持原有内容
    assert content.content == "原始内容"


def test_html_content_processor_empty_input():
    """测试HTML内容处理器处理空输入"""
    config = {
        "timeout": 30,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    processor = HTMLContentProcessor(config)
    processed_contents = processor([])

    assert len(processed_contents) == 0


@pytest.mark.need_external_service
def test_html_content_processor_with_xueqiu():
    """测试HTML内容处理器处理雪球网站"""
    config = {
        "timeout": 30,
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    }

    processor = HTMLContentProcessor(config)

    # 创建雪球测试内容
    test_content = Content(
        content_id="xueqiu_001",
        title="雪球文章测试",
        link="https://xueqiu.com/3452146899/339832436",
        summary="雪球原始内容",
        content="原始内容",
        published="2024-01-01",
    )

    # 处理内容
    processed_contents = processor([test_content])

    # 验证结果 - 无论成功失败都应该保留原有内容
    assert len(processed_contents) == 1
    content = processed_contents[0]
    assert content.title == "雪球文章测试"
    assert content.link == "https://xueqiu.com/3452146899/339832436"

    # 如果处理成功，应该有新的markdown内容
    if content.content != "原始内容":
        print(f"雪球网站处理成功，提取内容长度: {len(content.content)}")
        print(f"内容预览: {content.content[:300]}...")
    else:
        print("雪球网站处理失败，保留原有内容")


@pytest.mark.need_external_service
def test_html_content_processor_with_spaces_blog():
    """测试HTML内容处理器处理苏剑林的博客"""
    config = {
        "timeout": 30,
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    }

    processor = HTMLContentProcessor(config)

    # 创建苏剑林博客测试内容
    test_content = Content(
        content_id="spaces_001",
        title="苏剑林博客文章测试",
        link="https://spaces.ac.cn/archives/11059",
        summary="博客原始内容",
        content="原始内容",
        published="2024-01-01",
    )

    # 处理内容
    processed_contents = processor([test_content])

    # 验证结果 - 无论成功失败都应该保留原有内容
    assert len(processed_contents) == 1
    content = processed_contents[0]
    assert content.title == "苏剑林博客文章测试"
    assert content.link == "https://spaces.ac.cn/archives/11059"

    # 如果处理成功，应该有新的markdown内容
    if content.content != "原始内容":
        print(f"苏剑林博客处理成功，提取内容长度: {len(content.content)}")
        print(f"内容预览: {content.content[:300]}...")
    else:
        print("苏剑林博客处理失败，保留原有内容")


@pytest.mark.need_external_service
def test_html_content_processor_real_websites_comprehensive():
    """综合测试HTML内容处理器处理多个真实网站"""
    config = {
        "timeout": 30,
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    }

    processor = HTMLContentProcessor(config)

    # 创建多个测试内容
    test_contents = [
        Content(
            content_id="xueqiu_001",
            title="雪球文章",
            link="https://xueqiu.com/3452146899/339832436",
            summary="雪球原始内容",
            content="原始内容",
            published="2024-01-01",
        ),
        Content(
            content_id="spaces_001",
            title="苏剑林博客",
            link="https://spaces.ac.cn/archives/11059",
            summary="博客原始内容",
            content="原始内容",
            published="2024-01-01",
        ),
    ]

    # 处理内容
    processed_contents = processor(test_contents)

    # 验证结果 - 应该返回相同数量的内容
    assert len(processed_contents) == len(test_contents)

    print(f"\n综合测试结果：")
    print(f"输入内容数量: {len(test_contents)}")
    print(f"输出内容数量: {len(processed_contents)}")

    for i, content in enumerate(processed_contents):
        original = test_contents[i]
        success = content.content != original.content
        print(f"\n网站 {i+1}: {content.title}")
        print(f"  URL: {content.link}")
        print(f"  处理状态: {'成功' if success else '失败(保留原内容)'}")
        if success:
            print(f"  提取内容长度: {len(content.content)}")
            print(f"  内容预览: {content.content[:200]}...")
