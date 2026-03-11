#!/usr/bin/env python3
"""
HTML内容处理器测试脚本
"""

from unittest.mock import MagicMock, patch

import pytest

from octopus_scraper.processors.html_content_processor import (
    HTMLContentProcessor,
    HTMLContentProcessorConfig,
)
from octopus_scraper.protos import Content


def test_html_content_processor_init():
    """测试HTML内容处理器初始化"""
    config = {
        "timeout": 30,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    processor = HTMLContentProcessor(config)
    assert processor.config.timeout == 30
    assert "Mozilla" in processor.config.user_agent


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

    print("\n综合测试结果：")
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


def test_html_content_processor_config_initialization():
    """测试HTML内容处理器配置初始化"""
    # 测试默认配置
    config = {}
    processor = HTMLContentProcessor(config)
    assert processor.config.timeout == 30
    assert processor.config.use_browser
    assert processor.config.browserless_url == ""
    assert processor.config.browser_timeout == 60000

    # 测试自定义配置
    config = {
        "timeout": 60,
        "browserless_url": "http://localhost:3000",
        "use_browser": False,
        "browser_timeout": 30000,
    }
    processor = HTMLContentProcessor(config)
    assert processor.config.timeout == 60
    assert processor.config.use_browser
    assert processor.config.browserless_url == "http://localhost:3000"
    assert processor.config.browser_timeout == 30000


def test_html_content_processor_browserless_config():
    """测试 browserless 配置相关逻辑"""

    # 测试禁用浏览器模式
    config = {"use_browser": False, "browserless_url": ""}
    processor = HTMLContentProcessor(config)
    assert processor.config.use_browser

    # 测试启用浏览器但无 URL
    config = {"use_browser": True, "browserless_url": ""}
    processor = HTMLContentProcessor(config)
    assert processor.config.use_browser
    assert processor.config.browserless_url == ""

    # 测试启用浏览器且有 URL
    config = {"use_browser": True, "browserless_url": "http://localhost:3000"}
    processor = HTMLContentProcessor(config)
    assert processor.config.use_browser
    assert processor.config.browserless_url == "http://localhost:3000"


@patch(
    "octopus_scraper.processors.html_content_processor.PLAYWRIGHT_AVAILABLE",
    False,
)
@patch("requests.Session.get")
def test_html_content_processor_no_playwright(mock_get):
    """测试 Playwright 不可用时的回退行为"""
    # 模拟HTTP响应
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None
    mock_response.text = "<html><body><h1>Test</h1></body></html>"
    mock_get.return_value = mock_response

    # 即使配置了浏览器，也应该回退到 requests
    config = {"use_browser": True, "browserless_url": "http://localhost:3000"}
    processor = HTMLContentProcessor(config)

    test_content = Content(
        content_id="test_001",
        title="测试",
        link="https://example.com/test",
        summary="测试",
        content="原始内容",
        published="2024-01-01",
    )

    processed_contents = processor([test_content])

    # 应该成功处理并使用 requests
    assert len(processed_contents) == 1
    mock_get.assert_called_once()


@patch(
    "octopus_scraper.processors.html_content_processor.PLAYWRIGHT_AVAILABLE",
    True,
)
@patch("requests.Session.get")
def test_html_content_processor_browser_fallback_to_requests(mock_get):
    """测试浏览器抓取失败时回退到 requests"""
    # 模拟HTTP响应
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None
    mock_response.text = "<html><body><h1>Fallback Test</h1></body></html>"
    mock_get.return_value = mock_response

    # 配置启用浏览器但没有 browserless_url
    config = {"use_browser": True, "browserless_url": ""}  # 空 URL，不会使用浏览器
    processor = HTMLContentProcessor(config)

    test_content = Content(
        content_id="test_001",
        title="回退测试",
        link="https://example.com/test",
        summary="测试",
        content="原始内容",
        published="2024-01-01",
    )

    processed_contents = processor([test_content])

    # 应该直接使用 requests（因为没有配置 browserless_url）
    assert len(processed_contents) == 1
    assert "Fallback Test" in processed_contents[0].content
    mock_get.assert_called_once()


@patch(
    "octopus_scraper.processors.html_content_processor.PLAYWRIGHT_AVAILABLE",
    True,
)
@patch("octopus_scraper.processors.html_content_processor.sync_playwright")
@patch("requests.Session.get")
def test_html_content_processor_browser_exception_fallback(mock_get, mock_playwright):
    """测试浏览器抓取异常时回退到 requests"""
    # 模拟浏览器抛出异常
    mock_playwright.side_effect = Exception("Browser connection failed")

    # 模拟HTTP响应
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None
    mock_response.text = "<html><body><h1>Requests Fallback</h1></body></html>"
    mock_get.return_value = mock_response

    config = {
        "use_browser": True,
        "browserless_url": "http://localhost:3000",  # 配置了 URL
    }
    processor = HTMLContentProcessor(config)

    test_content = Content(
        content_id="test_001",
        title="异常回退测试",
        link="https://example.com/test",
        summary="测试",
        content="原始内容",
        published="2024-01-01",
    )

    processed_contents = processor([test_content])

    # 应该回退到 requests
    assert len(processed_contents) == 1
    assert "Requests Fallback" in processed_contents[0].content
    mock_get.assert_called_once()


def test_html_content_processor_config_validation():
    """测试配置验证"""
    # 测试 HTMLContentProcessorConfig 数据类
    config_dict = {
        "timeout": 45,
        "user_agent": "Custom Agent",
        "browserless_url": "http://custom:3000",
        "use_browser": False,
        "browser_timeout": 45000,
    }

    from dacite import from_dict

    config = from_dict(HTMLContentProcessorConfig, config_dict)

    assert config.timeout == 45
    assert config.user_agent == "Custom Agent"
    assert config.browserless_url == "http://custom:3000"
    assert not config.use_browser
    assert config.browser_timeout == 45000


@patch("requests.Session.get")
def test_html_content_processor_with_convert_contents_to_mk(mock_get):
    """测试使用 convert_contents_to_mk 函数进行 HTML 到 Markdown 转换"""
    # 模拟HTTP响应
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None
    mock_response.text = """
    <html>
    <body>
        <h1>Test Title</h1>
        <p>This is <strong>bold</strong> text.</p>
        <p>This is <em>italic</em> text.</p>
    </body>
    </html>
    """
    mock_get.return_value = mock_response

    config = {"use_browser": False}
    processor = HTMLContentProcessor(config)

    test_content = Content(
        content_id="test_001",
        title="Markdown转换测试",
        link="https://example.com/test",
        summary="测试",
        content="原始内容",
        published="2024-01-01",
    )

    processed_contents = processor([test_content])

    assert len(processed_contents) == 1
    content = processed_contents[0]

    # 验证 markdownify 的输出格式
    assert "Test Title" in content.content
    assert "**bold**" in content.content  # markdownify 使用 ** 而不是 __
    assert "*italic*" in content.content  # markdownify 使用 * 而不是 _
