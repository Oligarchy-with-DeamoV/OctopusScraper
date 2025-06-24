#!/usr/bin/env python3
"""
HTML内容处理器使用示例
演示如何使用 HTMLContentProcessor 从URL获取网页内容并转换为Markdown格式
"""

from octopus_scraper.scrapers.processors.html_content_processor import (
    HTMLContentProcessor,
)
from octopus_scraper.scrapers.scraper_protos import Content


def main():
    """主函数"""
    print("HTML内容处理器使用示例")
    print("=" * 50)

    # 配置处理器
    config = {
        "timeout": 30,
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    }

    # 创建处理器实例
    processor = HTMLContentProcessor(config)

    # 创建测试内容 - 使用一个简单的网页进行测试
    test_contents = [
        Content(
            content_id="example_001",
            title="Python官网",
            link="https://httpbin.org/html",  # 使用httpbin的HTML测试页面
            summary="这是一个测试页面",
            content="原始内容",
            published="2024-01-01",
        )
    ]

    print(f"正在处理 {len(test_contents)} 个URL...")

    # 处理内容
    processed_contents = processor(test_contents)

    print(f"成功处理了 {len(processed_contents)} 个页面")
    print("=" * 50)

    # 显示结果
    for i, content in enumerate(processed_contents, 1):
        print(f"\n页面 {i}:")
        print(f"标题: {content.title}")
        print(f"链接: {content.link}")
        print(f"Markdown内容预览:")
        print("-" * 30)
        # 显示前500个字符
        preview = content.summary[:500]
        if len(content.summary) > 500:
            preview += "..."
        print(preview)
        print("-" * 30)


if __name__ == "__main__":
    main()
