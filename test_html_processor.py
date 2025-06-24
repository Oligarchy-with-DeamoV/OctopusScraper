#!/usr/bin/env python3
"""
测试HTML内容处理器是否只更新content字段
"""
import os
import sys

sys.path.append("src")

from octopus_scraper.scrapers.processors.html_content_processor import (
    HTMLContentProcessor,
)
from octopus_scraper.scrapers.scraper_protos import Content


def test_html_processor_only_updates_content():
    """验证HTML处理器只更新content字段，不更新summary字段"""

    print("=== 测试HTML内容处理器字段更新行为 ===\n")

    # 创建测试配置
    config = {
        "timeout": 30,
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    }

    # 创建处理器
    processor = HTMLContentProcessor(config)
    print("✓ HTML内容处理器初始化成功")
    print(f"超时设置: {processor.timeout}")
    print(f"User-Agent: {processor.user_agent[:50]}...\n")

    # 创建测试内容
    original_summary = "这是原始摘要内容"
    original_content = "这是原始正文内容"

    test_content = Content(
        content_id="test_001",
        title="测试文章",
        link="https://httpbin.org/html",  # 使用httpbin提供的HTML测试页面
        summary=original_summary,
        content=original_content,
        published="2024-01-01",
    )

    print("测试内容:")
    print(f"  标题: {test_content.title}")
    print(f"  链接: {test_content.link}")
    print(f"  原始summary: '{test_content.summary}'")
    print(f"  原始content: '{test_content.content}'\n")

    # 处理内容
    print("开始处理内容...")
    try:
        processed_contents = processor([test_content])
        print(f"✓ 处理完成，返回 {len(processed_contents)} 条内容\n")

        if processed_contents:
            content = processed_contents[0]

            print("处理结果:")
            print(f"  处理后summary: '{content.summary}' (长度: {len(content.summary)})")
            print(
                f"  处理后content前100字符: '{content.content[:100]}...' (长度: {len(content.content)})\n"
            )

            # 验证summary字段是否保持不变
            if content.summary == original_summary:
                print("✅ PASS: summary字段保持不变")
            else:
                print("❌ FAIL: summary字段被修改了")
                print(f"   期望: '{original_summary}'")
                print(f"   实际: '{content.summary}'")

            # 验证content字段是否被更新
            if content.content != original_content:
                print("✅ PASS: content字段已被HTML处理器更新")
                print(f"   原始长度: {len(original_content)}")
                print(f"   更新后长度: {len(content.content)}")
            else:
                print("⚠️  WARNING: content字段未被更新（可能是网络问题或内容提取失败）")

            # 验证其他字段保持不变
            fields_to_check = ["title", "link", "content_id", "published"]
            for field in fields_to_check:
                original_value = getattr(test_content, field)
                processed_value = getattr(content, field)
                if original_value == processed_value:
                    print(f"✅ PASS: {field}字段保持不变")
                else:
                    print(f"❌ FAIL: {field}字段被修改了")

        else:
            print("❌ FAIL: 未返回任何处理后的内容")

    except Exception as e:
        print(f"❌ FAIL: 处理失败 - {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_html_processor_only_updates_content()
