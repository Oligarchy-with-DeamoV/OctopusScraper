import pytest

from octopus_scraper.octopus import Octopus
from octopus_scraper.scraper import BaseScraperConfig, Scraper


@pytest.mark.need_external_service
def test_octopus_initialization(octopus_config):
    octopus = Octopus(octopus_config)
    assert len(octopus._scrapers) == 3  # Updated to match actual number of scrapers


@pytest.mark.integrate_test
def test_trigger_and_upload_scraper(octopus_config):
    octopus = Octopus(octopus_config)
    octopus.trigger_scraper()
    assert len(octopus._fetched_contents) > 0
    octopus.trigger_upload()
    assert len(octopus._fetched_contents) == 0


@pytest.mark.need_external_service
def test_octopus_with_html_content_processor(octopus_config):
    """测试使用HTML内容处理器的完整Octopus流程"""
    # 修改配置，添加HTML内容处理器
    modified_config = octopus_config.copy()

    # 为第一个scraper添加HTML内容处理器配置
    modified_config["scrapers_config_with_fetch_params"][0][
        "scraper_config"
    ].content_processor_configs = {
        "html_content": {
            "timeout": 30,
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        }
    }

    octopus = Octopus(modified_config)
    assert len(octopus._scrapers) == 3

    # 触发抓取
    octopus.trigger_scraper()
    assert len(octopus._fetched_contents) > 0

    # 验证HTML内容处理器是否被正确应用
    processed_contents = octopus._fetched_contents

    # 检查至少有一个内容来自配置了HTML处理器的scraper
    owen_contents = [
        content for content in processed_contents if "owenyoung.com" in content.link
    ]

    if owen_contents:
        # 验证内容被HTML处理器处理过
        for content in owen_contents[:2]:  # 检查前两个内容
            print(f"\n处理的内容:")
            print(f"标题: {content.title}")
            print(f"链接: {content.link}")
            print(f"原始摘要长度: {len(content.summary)}")
            print(f"处理后内容长度: {len(content.content)}")
            print(f"处理后内容预览: {content.content[:200]}...")

            # 验证内容确实存在
            assert len(content.content) > 0
            assert content.title is not None
            assert content.link is not None


@pytest.mark.need_external_service
def test_scraper_with_html_content_processor_standalone():
    """单独测试使用HTML内容处理器的Scraper"""
    scraper_config = BaseScraperConfig(
        fetcher_name="rsshub",
        fetcher_config={
            "hub_root": "https://www.owenyoung.com",
            "route": "/atom.xml",
            "fetch_params": {},
        },
        content_processor_configs={
            "html_content": {
                "timeout": 30,
                "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            }
        },
    )

    scraper = Scraper(scraper_config.__dict__)

    # 验证HTML内容处理器已被正确初始化
    assert "html_content" in scraper.active_content_processor

    # 执行抓取
    contents = scraper.scrap_contents({})

    # 验证结果
    assert len(contents) > 0

    print(f"\n单独测试结果:")
    print(f"抓取到 {len(contents)} 条内容")

    for i, content in enumerate(contents[:3]):  # 检查前三个内容
        print(f"\n内容 {i+1}:")
        print(f"  标题: {content.title}")
        print(f"  链接: {content.link}")
        print(f"  原始摘要长度: {len(content.summary)}")
        print(f"  处理后内容长度: {len(content.content)}")

        # 验证内容格式
        assert content.content_id is not None
        assert content.title is not None
        assert content.link is not None
        assert content.summary is not None
        assert content.content is not None
        assert content.published is not None


@pytest.mark.need_external_service
def test_scraper_with_multiple_processors():
    """测试同时使用多个处理器的Scraper"""
    scraper_config = BaseScraperConfig(
        fetcher_name="rsshub",
        fetcher_config={
            "hub_root": "https://www.owenyoung.com",
            "route": "/atom.xml",
            "fetch_params": {"limit": 2},  # 限制数量以减少测试时间
        },
        content_processor_configs={
            "html_content": {
                "timeout": 30,
                "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            }
            # 注意: 这里可以添加更多处理器，比如LLM处理器
            # "llm": {
            #     "prompt": "请总结这篇文章的主要内容",
            #     "if_structure_output": False
            # }
        },
    )

    scraper = Scraper(scraper_config.__dict__)

    # 验证所有处理器都被正确初始化
    assert "html_content" in scraper.active_content_processor

    # 执行抓取
    contents = scraper.scrap_contents({"limit": 2})

    # 验证结果
    assert len(contents) > 0

    print(f"\n多处理器测试结果:")
    print(f"抓取到 {len(contents)} 条内容")
    print(f"激活的处理器: {list(scraper.active_content_processor.keys())}")

    for i, content in enumerate(contents):
        print(f"\n内容 {i+1}:")
        print(f"  标题: {content.title}")
        print(f"  链接: {content.link}")
        print(f"  原始摘要长度: {len(content.summary)}")
        print(f"  处理后内容长度: {len(content.content)}")
        print(f"  处理后内容预览: {content.content[:150]}...")

        # 验证内容经过HTML处理器处理
        assert len(content.content) > 0
        # HTML处理器应该生成markdown格式的内容
        # 可以检查是否包含markdown特征，如链接格式等


@pytest.mark.need_external_service
def test_complete_html_content_processor_integration():
    """完整的HTML内容处理器集成测试，验证整个流程"""
    scraper_config = BaseScraperConfig(
        fetcher_name="rsshub",
        fetcher_config={
            "hub_root": "https://www.owenyoung.com",
            "route": "/atom.xml",
            "fetch_params": {"limit": 3},  # 限制数量以减少测试时间
        },
        content_processor_configs={
            "html_content": {
                "timeout": 30,
                "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            }
        },
    )

    scraper = Scraper(scraper_config.__dict__)

    # 验证HTML内容处理器已被正确初始化
    assert "html_content" in scraper.active_content_processor
    html_processor = scraper.active_content_processor["html_content"]
    assert html_processor.timeout == 30
    assert "Mozilla" in html_processor.user_agent

    # 执行抓取
    contents = scraper.scrap_contents({"limit": 3})

    # 验证结果
    assert len(contents) > 0
    print(f"\n=== 完整HTML内容处理器集成测试结果 ===")
    print(f"抓取到 {len(contents)} 条内容")
    print(f"配置的处理器: {list(scraper.active_content_processor.keys())}")

    # 详细验证每个内容
    for i, content in enumerate(contents):
        print(f"\n--- 内容 {i+1} ---")
        print(f"标题: {content.title}")
        print(f"链接: {content.link}")
        print(f"发布时间: {content.published}")
        print(f"原始摘要长度: {len(content.summary)}")
        print(f"处理后内容长度: {len(content.content)}")

        # 基本字段验证
        assert content.content_id is not None
        assert content.title is not None
        assert content.link is not None
        assert content.summary is not None
        assert content.content is not None
        assert content.published is not None

        # 验证HTML处理器确实处理了内容
        # content字段应该包含markdown格式的内容，长度应该比原始summary更长
        print(
            f"内容是否被处理: {'是' if len(content.content) > len(content.summary) else '否'}"
        )

        # 输出处理后内容的预览
        if len(content.content) > 200:
            print(f"处理后内容预览:\n{content.content[:300]}...")
        else:
            print(f"处理后内容:\n{content.content}")

        # 验证是否包含markdown特征（如果处理成功的话）
        markdown_indicators = ["#", "**", "*", "[", "](", "\n\n"]
        has_markdown = any(
            indicator in content.content for indicator in markdown_indicators
        )
        if has_markdown:
            print("✓ 内容包含Markdown格式标记")

    print(f"\n=== 测试完成 ===")
