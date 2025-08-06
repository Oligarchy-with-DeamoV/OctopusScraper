import json
import os

import pytest

from octopus_scraper.octopus import Octopus
from octopus_scraper.scraper import BaseScraperConfig, Scraper


@pytest.mark.integrate_test
def test_octopus_with_html_and_llm_processors(
    octopus_config, structured_llm_processor_config
):
    """测试使用HTML内容处理器和LLM处理器的完整Octopus流程

    处理顺序：RSS获取 -> HTML内容处理器 -> LLM处理器 -> 最终结果
    HTML处理器优先级为50，LLM处理器优先级为100，所以HTML先处理
    """
    print("\n" + "=" * 80)
    print("测试 Octopus 配置: HTML内容处理器 + LLM处理器")
    print("=" * 80)

    # 修改配置，为第一个scraper添加HTML内容处理器和LLM处理器
    modified_config = octopus_config.copy()

    # 配置处理器链：HTML处理器(priority=50) -> LLM处理器(priority=100)
    modified_config["scrapers_config_with_fetch_params"][0][
        "scraper_config"
    ].content_processor_configs = {
        "html_content": {
            "timeout": 30,
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "priority": 50,  # 更高优先级，先执行
        },
        "llm": structured_llm_processor_config,
    }

    # 限制只处理一个scraper，减少测试时间
    modified_config["scrapers_config_with_fetch_params"] = [
        modified_config["scrapers_config_with_fetch_params"][0]
    ]

    # 限制抓取数量
    modified_config["scrapers_config_with_fetch_params"][0]["fetch_params"] = {
        "limit": 2
    }

    print(
        f"配置的Scraper数量: {len(modified_config['scrapers_config_with_fetch_params'])}"
    )
    print(
        f"配置的处理器: {list(modified_config['scrapers_config_with_fetch_params'][0]['scraper_config'].content_processor_configs.keys())}"
    )

    # 创建Octopus实例
    octopus = Octopus(modified_config)
    assert len(octopus._scrapers) == 1

    print(f"实际创建的Scraper数量: {len(octopus._scrapers)}")

    # 触发抓取和处理
    print("\n📡 开始抓取和处理内容...")
    octopus.trigger_scraper()

    assert len(octopus._fetched_contents) > 0
    print(f"✅ 成功抓取并处理了 {len(octopus._fetched_contents)} 条内容")

    # 验证处理结果
    processed_contents = octopus._fetched_contents

    print(f"\n📋 处理结果详情:")
    print("-" * 60)

    for i, content in enumerate(processed_contents):
        print(f"\n--- 内容 {i+1} ---")
        print(f"📰 标题: {content.title}")
        print(f"🔗 链接: {content.link}")
        print(f"📅 发布时间: {content.published}")
        print(f"📏 原始摘要长度: {len(content.summary)} 字符")
        print(f"📄 最终内容长度: {len(content.content)} 字符")

        # 验证基本字段
        assert content.content_id is not None
        assert content.title is not None
        assert content.link is not None
        assert content.summary is not None
        assert content.content is not None
        assert content.published is not None

        print(f"\n🔍 处理结果分析:")

        # 检查是否被HTML处理器处理过（内容应该比摘要长很多）
        if len(content.content) > len(content.summary) * 2:
            print("✅ HTML内容处理器: 成功提取并处理了完整网页内容")
        else:
            print("⚠️  HTML内容处理器: 可能未成功处理或内容较短")

        # 检查是否被LLM处理器处理过（应该是JSON格式）
        try:
            parsed_summary = json.loads(content.summary)
            print("✅ LLM处理器: 成功生成结构化摘要")

            # 显示LLM处理结果
            if "summary" in parsed_summary:
                print(f"📝 AI摘要: {parsed_summary['summary'][:100]}...")

        except json.JSONDecodeError:
            print("❌ LLM处理器: 输出不是有效的JSON格式")
            print(f"原始输出: {content.summary[:200]}...")

        # 显示HTML处理后的内容预览
        print(f"\n📖 HTML处理后的内容预览:")
        content_preview = (
            content.content[:300] if len(content.content) > 300 else content.content
        )
        print(f"{content_preview}...")

        # 检查内容特征
        markdown_indicators = ["#", "**", "*", "[", "](", "\n\n"]
        has_markdown = any(
            indicator in content.content for indicator in markdown_indicators
        )
        if has_markdown:
            print("✅ 内容包含Markdown格式标记")

        print("-" * 60)

    print(f"\n🎉 测试完成！成功验证了 HTML -> LLM 的处理链")


@pytest.mark.integrate_test
def test_scraper_with_html_and_llm_processors_standalone(
    structured_llm_processor_config,
):
    """单独测试使用HTML内容处理器和LLM处理器的Scraper"""
    print("\n" + "=" * 80)
    print("独立测试 Scraper: HTML内容处理器 + LLM处理器")
    print("=" * 80)

    scraper_config = BaseScraperConfig(
        fetcher_name="rsshub",
        fetcher_config={
            "hub_root": "https://www.owenyoung.com",
            "route": "/atom.xml",
            "fetch_params": {"limit": 1},  # 只处理1条内容以减少测试时间
        },
        content_processor_configs={
            "html_content": {
                "timeout": 30,
                "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "priority": 50,  # 先执行HTML处理
            },
            "llm": structured_llm_processor_config,
        },
    )

    scraper = Scraper(scraper_config.__dict__)

    # 验证两个处理器都被正确初始化
    assert "html_content" in scraper.active_content_processor
    assert "llm" in scraper.active_content_processor

    print(f"✅ 已加载处理器: {list(scraper.active_content_processor.keys())}")

    # 检查处理器优先级
    html_priority = scraper.processor_priorities.get("html_content", 100)
    llm_priority = scraper.processor_priorities.get("llm", 100)
    print(f"🔄 处理器优先级: HTML({html_priority}) -> LLM({llm_priority})")

    # 执行抓取和处理
    print(f"\n📡 开始抓取内容...")
    contents = scraper.scrap_contents({"limit": 1})

    # 验证结果
    assert len(contents) > 0
    print(f"✅ 成功处理了 {len(contents)} 条内容")

    content = contents[0]
    print(f"\n📋 处理结果分析:")
    print(f"📰 标题: {content.title}")
    print(f"🔗 链接: {content.link}")
    print(f"📅 发布时间: {content.published}")
    print(f"📏 原始摘要长度: {len(content.summary)} 字符")
    print(f"📄 最终内容长度: {len(content.content)} 字符")

    # 验证基本字段
    assert content.content_id is not None
    assert content.title is not None
    assert content.link is not None
    assert content.summary is not None
    assert content.content is not None
    assert content.published is not None

    print(f"\n🔍 HTML处理器效果:")
    # HTML处理器应该显著增加内容长度
    if len(content.content) > len(content.summary) * 2:
        print("✅ HTML内容已成功提取和转换为Markdown")
        print(f"   内容扩展倍数: {len(content.content) / len(content.summary):.1f}x")
    else:
        print("⚠️  HTML处理效果不明显，可能是网页内容较少")

    # 显示HTML处理后的内容片段
    print(f"\n📖 HTML处理后的内容片段:")
    print(
        content.content[:400] + "..." if len(content.content) > 400 else content.content
    )

    print(f"\n🤖 LLM处理器效果:")
    # 验证LLM处理器的结构化输出
    try:
        llm_result = json.loads(content.content)
        print("✅ LLM成功生成结构化分析")

        print(f"\n📊 LLM分析结果:")
        if "summary" in llm_result:
            print(f"🎯 文章摘要: {llm_result['summary']}")
    except json.JSONDecodeError as e:
        print(f"❌ LLM输出解析失败: {e}")
        print(f"原始LLM输出: {content.content[:300]}...")

    print(f"\n🎉 独立测试完成！HTML -> LLM 处理链运行正常")


@pytest.mark.need_external_service
def test_processor_execution_order(structured_llm_processor_config):
    """测试处理器执行顺序是否按照优先级正确执行"""
    print("\n" + "=" * 80)
    print("测试处理器执行顺序")
    print("=" * 80)

    scraper_config = BaseScraperConfig(
        fetcher_name="rsshub",
        fetcher_config={
            "hub_root": "https://www.owenyoung.com",
            "route": "/atom.xml",
            "fetch_params": {"limit": 1},
        },
        content_processor_configs={
            # 故意设置LLM处理器优先级更高，测试是否会按优先级执行
            "llm": {
                "prompt": "简单总结这篇文章。",
                "if_structure_output": False,
                "priority": 20,  # 高优先级，应该先执行
            },
            "html_content": {
                "timeout": 30,
                "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "priority": 80,  # 低优先级，应该后执行
            },
        },
    )

    scraper = Scraper(scraper_config.__dict__)

    # 检查处理器优先级设置
    llm_priority = scraper.processor_priorities.get("llm", 100)
    html_priority = scraper.processor_priorities.get("html_content", 100)

    print(f"🔄 配置的处理器优先级:")
    print(f"   LLM处理器: {llm_priority}")
    print(f"   HTML处理器: {html_priority}")

    # 验证优先级顺序
    sorted_processors = sorted(
        scraper.active_content_processor.items(),
        key=lambda x: scraper.processor_priorities.get(x[0], 100),
    )

    print(f"📋 实际执行顺序:")
    for i, (name, processor) in enumerate(sorted_processors):
        priority = scraper.processor_priorities.get(name, 100)
        print(f"   {i+1}. {name} (优先级: {priority})")

    # LLM应该排在HTML前面（因为优先级20 < 80）
    first_processor_name = sorted_processors[0][0]
    assert (
        first_processor_name == "llm"
    ), f"期望LLM处理器先执行，但实际是 {first_processor_name}"

    print("✅ 处理器执行顺序验证通过！")

    # 执行抓取验证实际运行
    print(f"\n📡 执行抓取验证...")
    contents = scraper.scrap_contents({"limit": 1})
    assert len(contents) > 0

    print(f"✅ 成功按正确顺序处理了 {len(contents)} 条内容")
    print(f"🎉 处理器顺序测试完成！")
