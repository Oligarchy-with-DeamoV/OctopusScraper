# Scrapers 测试文档

## 概述

Scrapers 测试覆盖了抓取器的核心功能，包括不同类型抓取器的创建、配置验证、数据抓取、内容去重、错误处理等方面，确保抓取系统的可靠性和稳定性。

## 测试文件位置

- **核心抓取器测试**: `tests/octopus_scraper/scrapers/scraper_test.py`
- **处理器优先级测试**: `tests/octopus_scraper/scrapers/test_processor_priority.py`
- **处理器测试**:
  - `tests/octopus_scraper/scrapers/processors/llm_processor_test.py`
  - `tests/octopus_scraper/scrapers/processors/html_content_processor_test.py`
- **工具函数测试**:
  - `tests/octopus_scraper/scrapers/utils/direct_rss_test.py`
  - `tests/octopus_scraper/scrapers/utils/rsshub_test.py`
  - `tests/octopus_scraper/scrapers/utils/notion_api_test.py`
  - `tests/octopus_scraper/scrapers/utils/tools_test.py`
- **集成测试**: `tests/integrate_tests/` 目录下的相关测试

## 测试结构

### Scraper 测试

#### 测试类: `TestScraper`

**文件**: `tests/octopus_scraper/scrapers/scraper_test.py`

该测试类验证 Scraper 类的核心功能：

```python
class TestScraper:
    """核心抓取器测试"""

    @pytest.mark.need_external_service
    def test_scrap_contents(self, sspai_rss_hub_config):
        """测试内容抓取功能"""

    def test_content_processing(self, sspai_rss_hub_config):
        """测试内容处理功能"""

    def test_set_all_content_processors(self, sspai_rss_hub_config):
        """测试设置所有内容处理器"""

    def test_select_content_processor(self, scraper_config):
        """测试选择内容处理器"""
```

### BaseScraper 测试

#### 测试类: `TestBaseScraper`

```python
class TestBaseScraper:
    """基础抓取器测试"""

    def test_base_scraper_abstract(self):
        """测试抽象基类不能直接实例化"""

    def test_scraper_initialization(self):
        """测试抓取器初始化"""

    def test_scraper_config_validation(self):
        """测试配置验证"""

    def test_get_scraper_info(self):
        """测试获取抓取器信息"""
```

### DirectRssScraper 测试

#### 测试类: `TestDirectRssScraper`

```python
class TestDirectRssScraper:
    """RSS 直接抓取器测试"""

    def test_direct_rss_init(self):
        """测试 RSS 抓取器初始化"""

    def test_config_validation(self):
        """测试配置验证"""

    async def test_successful_rss_scraping(self):
        """测试成功的 RSS 抓取"""

    async def test_rss_parsing_with_items(self):
        """测试包含项目的 RSS 解析"""

    async def test_rss_parsing_empty_feed(self):
        """测试空 RSS 源解析"""

    async def test_invalid_rss_url(self):
        """测试无效 RSS URL"""

    async def test_network_error_handling(self):
        """测试网络错误处理"""

    async def test_max_items_limit(self):
        """测试最大项目数限制"""

    def test_date_parsing(self):
        """测试日期解析"""

    def test_tags_extraction(self):
        """测试标签提取"""
```

### RsshubScraper 测试

#### 测试类: `TestRsshubScraper`

```python
class TestRsshubScraper:
    """RSSHub 抓取器测试"""

    def test_rsshub_url_construction(self):
        """测试 RSSHub URL 构造"""

    def test_rsshub_config_validation(self):
        """测试 RSSHub 配置验证"""

    async def test_rsshub_scraping(self):
        """测试 RSSHub 抓取"""

    def test_custom_rsshub_base(self):
        """测试自定义 RSSHub 基础 URL"""

    def test_route_normalization(self):
        """测试路由规范化"""

    def test_get_scraper_info_extended(self):
        """测试获取扩展的抓取器信息"""
```

### NotionApiScraper 测试

#### 测试类: `TestNotionApiScraper`

```python
class TestNotionApiScraper:
    """Notion API 抓取器测试"""

    def test_notion_init(self):
        """测试 Notion 抓取器初始化"""

    def test_notion_config_validation(self):
        """测试 Notion 配置验证"""

    async def test_notion_api_scraping(self):
        """测试 Notion API 抓取"""

    async def test_notion_auth_error(self):
        """测试 Notion 认证错误"""

    async def test_notion_invalid_database(self):
        """测试无效数据库ID"""

    def test_parse_notion_page(self):
        """测试解析 Notion 页面"""

    def test_extract_notion_properties(self):
        """测试提取 Notion 属性"""

    async def test_notion_filter_application(self):
        """测试 Notion 过滤器应用"""
```

## 测试用例详解

### ScraperManager 功能测试

```python
async def test_scraper_manager_complete_workflow(self):
    """测试抓取器管理器完整工作流程"""

    # 准备配置
    config = {
        'scrapers': {
            'test_rss': {
                'type': 'direct_rss',
                'enabled': True,
                'rss_url': 'https://example.com/rss.xml',
                'max_items': 10
            },
            'test_rsshub': {
                'type': 'rsshub',
                'enabled': True,
                'route': '/test/route',
                'max_items': 5
            },
            'disabled_scraper': {
                'type': 'direct_rss',
                'enabled': False,
                'rss_url': 'https://disabled.com/rss.xml'
            }
        }
    }

    # 模拟 RSS 响应
    mock_rss_content = """<?xml version="1.0"?>
    <rss version="2.0">
        <channel>
            <title>Test RSS</title>
            <item>
                <title>Test Item 1</title>
                <link>https://example.com/item1</link>
                <description>Test description 1</description>
            </item>
            <item>
                <title>Test Item 2</title>
                <link>https://example.com/item2</link>
                <description>Test description 2</description>
            </item>
        </channel>
    </rss>"""

    with aioresponses() as m:
        # Mock RSS 响应
        m.get('https://example.com/rss.xml', body=mock_rss_content)
        m.get('https://rsshub.app/test/route', body=mock_rss_content)

        # 创建管理器
        manager = ScraperManager(config)

        # 验证加载的抓取器
        scrapers = manager.list_scrapers()
        assert len(scrapers) == 2  # 只有启用的抓取器

        scraper_names = [s['name'] for s in scrapers]
        assert 'test_rss' in scraper_names
        assert 'test_rsshub' in scraper_names
        assert 'disabled_scraper' not in scraper_names

        # 运行单个抓取器
        result = await manager.run_scraper('test_rss')

        assert result.success == True
        assert result.scraper_name == 'test_rss'
        assert len(result.items) == 2
        assert result.items[0].title == 'Test Item 1'
        assert result.items[1].title == 'Test Item 2'

        # 运行所有抓取器
        all_results = await manager.run_all_scrapers()
        assert len(all_results) == 2

        for result in all_results:
            assert result.success == True
            assert len(result.items) == 2

        # 获取抓取器信息
        info = manager.get_scraper_info('test_rss')
        assert info['name'] == 'test_rss'
        assert info['type'] == 'DirectRssScraper'
        assert info['enabled'] == True
```

### 内容去重测试

```python
class TestContentDeduplicator:
    """内容去重器测试"""

    def test_deduplicator_initialization(self):
        """测试去重器初始化"""
        dedup = ContentDeduplicator()
        assert dedup.storage_backend == 'memory'
        assert len(dedup._memory_cache) == 0

    def test_hash_calculation(self):
        """测试哈希计算"""
        dedup = ContentDeduplicator()

        item1 = ScrapingItem(title="Test Title", url="https://example.com/1")
        item2 = ScrapingItem(title="Test Title", url="https://example.com/1")
        item3 = ScrapingItem(title="Different Title", url="https://example.com/1")

        hash1 = dedup._calculate_hash(item1)
        hash2 = dedup._calculate_hash(item2)
        hash3 = dedup._calculate_hash(item3)

        assert hash1 == hash2  # 相同标题和URL
        assert hash1 != hash3  # 不同标题

    def test_duplicate_detection(self):
        """测试重复检测"""
        dedup = ContentDeduplicator()

        items = [
            ScrapingItem(title="Item 1", url="https://example.com/1"),
            ScrapingItem(title="Item 2", url="https://example.com/2"),
            ScrapingItem(title="Item 1", url="https://example.com/1"),  # 重复
            ScrapingItem(title="Item 3", url="https://example.com/3"),
        ]

        unique_items = dedup.deduplicate_items(items)

        assert len(unique_items) == 3
        assert unique_items[0].title == "Item 1"
        assert unique_items[1].title == "Item 2"
        assert unique_items[2].title == "Item 3"

    def test_process_result_with_deduplication(self):
        """测试带去重的结果处理"""
        dedup = ContentDeduplicator()

        items = [
            ScrapingItem(title="Item 1", url="https://example.com/1"),
            ScrapingItem(title="Item 2", url="https://example.com/2"),
            ScrapingItem(title="Item 1", url="https://example.com/1"),  # 重复
        ]

        result = ScrapingResult(
            scraper_name="test",
            success=True,
            items=items
        )

        processed_result = dedup.process_result(result)

        assert processed_result.total_items == 3
        assert processed_result.new_items == 2
        assert processed_result.duplicate_items == 1
        assert len(processed_result.items) == 2

    def test_clear_cache(self):
        """测试清空缓存"""
        dedup = ContentDeduplicator()

        item = ScrapingItem(title="Test", url="https://example.com")
        dedup.deduplicate_items([item])

        assert len(dedup._memory_cache) == 1

        dedup.clear_cache()
        assert len(dedup._memory_cache) == 0
```

### RSS 解析测试

```python
async def test_rss_parsing_comprehensive(self):
    """测试全面的 RSS 解析"""

    complex_rss = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
        <channel>
            <title>Test Blog</title>
            <description>A test blog</description>
            <link>https://testblog.com</link>

            <item>
                <title><![CDATA[Article with CDATA]]></title>
                <link>https://testblog.com/article1</link>
                <description><![CDATA[<p>Article description with <strong>HTML</strong></p>]]></description>
                <author>test@example.com (Test Author)</author>
                <pubDate>Wed, 15 Nov 2023 10:00:00 GMT</pubDate>
                <category>Technology</category>
                <category>Programming</category>
                <guid>https://testblog.com/article1</guid>
            </item>

            <item>
                <title>Simple Article</title>
                <link>https://testblog.com/article2</link>
                <description>Simple article description</description>
                <pubDate>Wed, 14 Nov 2023 15:30:00 GMT</pubDate>
            </item>
        </channel>
    </rss>"""

    config = {
        'rss_url': 'https://testblog.com/rss.xml',
        'max_items': 50
    }

    scraper = DirectRssScraper('test_rss', config)

    with aioresponses() as m:
        m.get('https://testblog.com/rss.xml', body=complex_rss)

        result = await scraper.scrape()

        assert result.success == True
        assert len(result.items) == 2

        # 检查第一个项目
        item1 = result.items[0]
        assert item1.title == "Article with CDATA"
        assert item1.url == "https://testblog.com/article1"
        assert "Article description" in item1.content
        assert item1.author == "Test Author"
        assert "Technology" in item1.tags
        assert "Programming" in item1.tags

        # 检查第二个项目
        item2 = result.items[1]
        assert item2.title == "Simple Article"
        assert item2.url == "https://testblog.com/article2"
        assert item2.content == "Simple article description"
```

### 错误处理测试

```python
async def test_network_error_handling(self):
    """测试网络错误处理"""

    config = {
        'rss_url': 'https://nonexistent-site.com/rss.xml',
        'max_items': 10
    }

    scraper = DirectRssScraper('test_rss', config)

    with aioresponses() as m:
        # 模拟网络错误
        m.get('https://nonexistent-site.com/rss.xml',
              exception=aiohttp.ClientError("Connection failed"))

        result = await scraper.scrape()

        assert result.success == False
        assert result.scraper_name == 'test_rss'
        assert len(result.items) == 0
        assert "Connection failed" in result.error_message

async def test_invalid_rss_content(self):
    """测试无效 RSS 内容处理"""

    invalid_rss = "<html><body>This is not RSS</body></html>"

    config = {
        'rss_url': 'https://example.com/invalid.xml',
        'max_items': 10
    }

    scraper = DirectRssScraper('test_rss', config)

    with aioresponses() as m:
        m.get('https://example.com/invalid.xml', body=invalid_rss)

        result = await scraper.scrape()

        # 应该能处理无效内容而不崩溃
        assert result.success == True
        assert len(result.items) == 0  # 没有有效的项目

async def test_timeout_handling(self):
    """测试超时处理"""

    config = {
        'rss_url': 'https://slow-site.com/rss.xml',
        'max_items': 10,
        'timeout': 1  # 1秒超时
    }

    scraper = DirectRssScraper('test_rss', config)

    with aioresponses() as m:
        # 模拟超时
        m.get('https://slow-site.com/rss.xml',
              exception=asyncio.TimeoutError())

        result = await scraper.scrape()

        assert result.success == False
        assert "timeout" in result.error_message.lower()
```

### 配置验证测试

```python
class TestScraperConfigValidation:
    """抓取器配置验证测试"""

    def test_direct_rss_valid_config(self):
        """测试有效的 RSS 配置"""
        config = {
            'rss_url': 'https://example.com/rss.xml',
            'max_items': 20
        }

        scraper = DirectRssScraper('test', config)
        assert scraper.validate_config() == True

    def test_direct_rss_missing_url(self):
        """测试缺少 URL 的配置"""
        config = {'max_items': 20}

        scraper = DirectRssScraper('test', config)
        assert scraper.validate_config() == False

    def test_rsshub_valid_config(self):
        """测试有效的 RSSHub 配置"""
        config = {
            'route': '/sspai/series',
            'rsshub_base': 'https://rsshub.app'
        }

        scraper = RsshubScraper('test', config)
        assert scraper.validate_config() == True

    def test_rsshub_missing_route(self):
        """测试缺少路由的 RSSHub 配置"""
        config = {'rsshub_base': 'https://rsshub.app'}

        scraper = RsshubScraper('test', config)
        assert scraper.validate_config() == False

    def test_notion_valid_config(self):
        """测试有效的 Notion 配置"""
        config = {
            'database_id': 'test-database-id',
            'integration_token': 'test-token'
        }

        scraper = NotionApiScraper('test', config)
        assert scraper.validate_config() == True

    def test_notion_missing_credentials(self):
        """测试缺少凭据的 Notion 配置"""
        config = {'database_id': 'test-database-id'}

        scraper = NotionApiScraper('test', config)
        assert scraper.validate_config() == False
```

## Mock 和 Fixture

### 通用 Fixture

```python
@pytest.fixture
def sample_rss_content():
    """示例 RSS 内容"""
    return """<?xml version="1.0"?>
    <rss version="2.0">
        <channel>
            <title>Test RSS Feed</title>
            <item>
                <title>Test Article 1</title>
                <link>https://example.com/article1</link>
                <description>Description for article 1</description>
                <pubDate>Wed, 15 Nov 2023 10:00:00 GMT</pubDate>
                <author>Author 1</author>
                <category>Tech</category>
            </item>
            <item>
                <title>Test Article 2</title>
                <link>https://example.com/article2</link>
                <description>Description for article 2</description>
                <pubDate>Wed, 14 Nov 2023 15:30:00 GMT</pubDate>
                <author>Author 2</author>
                <category>Programming</category>
            </item>
        </channel>
    </rss>"""

@pytest.fixture
def sample_scraper_config():
    """示例抓取器配置"""
    return {
        'scrapers': {
            'test_rss': {
                'type': 'direct_rss',
                'enabled': True,
                'rss_url': 'https://example.com/rss.xml',
                'max_items': 10
            },
            'test_rsshub': {
                'type': 'rsshub',
                'enabled': True,
                'route': '/test/route',
                'max_items': 5
            }
        }
    }

@pytest.fixture
def scraper_manager(sample_scraper_config):
    """抓取器管理器 fixture"""
    return ScraperManager(sample_scraper_config)

@pytest.fixture
def content_deduplicator():
    """内容去重器 fixture"""
    return ContentDeduplicator()
```

### Mock 响应

```python
@pytest.fixture
def mock_notion_response():
    """Mock Notion API 响应"""
    return {
        "results": [
            {
                "id": "test-page-1",
                "properties": {
                    "Title": {
                        "title": [{"plain_text": "Test Notion Page 1"}]
                    },
                    "URL": {
                        "url": "https://example.com/notion1"
                    },
                    "Content": {
                        "rich_text": [{"plain_text": "Content for page 1"}]
                    }
                }
            },
            {
                "id": "test-page-2",
                "properties": {
                    "Title": {
                        "title": [{"plain_text": "Test Notion Page 2"}]
                    },
                    "URL": {
                        "url": "https://example.com/notion2"
                    }
                }
            }
        ]
    }

@pytest.fixture
def mock_http_responses():
    """Mock HTTP 响应管理器"""
    with aioresponses() as m:
        yield m
```

## 集成测试

### 与任务管理器集成测试

```python
class TestScraperTaskIntegration:
    """抓取器任务集成测试"""

    async def test_scraper_task_execution(self):
        """测试抓取器任务执行"""

        config = {
            'scrapers': {
                'test_scraper': {
                    'type': 'direct_rss',
                    'enabled': True,
                    'rss_url': 'https://example.com/rss.xml',
                    'max_items': 5
                }
            }
        }

        scraper_manager = ScraperManager(config)
        task_manager = TaskManager()

        await task_manager.start()

        try:
            with aioresponses() as m:
                m.get('https://example.com/rss.xml', body=sample_rss_content)

                # 创建抓取器任务
                task = ScraperTask('test_scraper', scraper_manager)
                task_id = await task_manager.submit_task(task)

                # 等待任务完成
                await asyncio.sleep(1.0)

                # 检查任务状态
                status = task_manager.get_task_status(task_id)
                assert status == TaskStatus.COMPLETED

                # 检查任务结果
                result = task_manager.get_task_result(task_id)
                assert result.result_data.success == True
                assert len(result.result_data.items) > 0

        finally:
            await task_manager.stop()
```

### Web 服务集成测试

```python
async def test_scraper_endpoints_integration(sanic_app):
    """测试抓取器 Web 端点集成"""

    # 测试获取抓取器列表
    request, response = await sanic_app.asgi_client.get('/admin/scrapers')
    assert response.status == 200

    data = response.json
    assert 'scrapers' in data

    # 测试运行抓取器
    with aioresponses() as m:
        m.get('https://example.com/rss.xml', body=sample_rss_content)

        request, response = await sanic_app.asgi_client.post(
            '/admin/scrapers/test_rss/test'
        )
        assert response.status == 200

        result = response.json
        assert result['success'] == True
        assert len(result['items']) > 0
```

## 性能测试

### 并发抓取测试

```python
async def test_concurrent_scraping_performance():
    """测试并发抓取性能"""

    config = {
        'scrapers': {
            f'scraper_{i}': {
                'type': 'direct_rss',
                'enabled': True,
                'rss_url': f'https://example.com/rss{i}.xml',
                'max_items': 10
            }
            for i in range(10)  # 10个抓取器
        }
    }

    manager = ScraperManager(config)

    with aioresponses() as m:
        # Mock 所有请求
        for i in range(10):
            m.get(f'https://example.com/rss{i}.xml', body=sample_rss_content)

        start_time = time.time()

        # 并发运行所有抓取器
        results = await manager.run_all_scrapers()

        end_time = time.time()
        execution_time = end_time - start_time

        # 验证结果
        assert len(results) == 10
        assert all(result.success for result in results)

        # 性能断言 (应该在合理时间内完成)
        assert execution_time < 5.0  # 5秒内完成

        print(f"Concurrent scraping completed in {execution_time:.2f} seconds")

async def test_memory_usage_during_scraping():
    """测试抓取过程中的内存使用"""

    import psutil
    import os

    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss

    # 创建大量项目的 RSS 内容
    large_rss = create_large_rss_content(1000)  # 1000个项目

    config = {
        'scrapers': {
            'large_scraper': {
                'type': 'direct_rss',
                'enabled': True,
                'rss_url': 'https://example.com/large.xml',
                'max_items': 1000
            }
        }
    }

    manager = ScraperManager(config)

    with aioresponses() as m:
        m.get('https://example.com/large.xml', body=large_rss)

        result = await manager.run_scraper('large_scraper')

        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory

        # 验证结果
        assert result.success == True
        assert len(result.items) == 1000

        # 内存使用应在合理范围内 (50MB)
        assert memory_increase < 50 * 1024 * 1024
```

## 测试运行

### 运行所有 Scrapers 测试

```bash
# 运行所有抓取器测试
poetry run pytest tests/octopus_scraper/scrapers/ -v

# 运行特定抓取器测试
poetry run pytest tests/octopus_scraper/scrapers/direct_rss_test.py -v
poetry run pytest tests/octopus_scraper/scrapers/rsshub_test.py -v

# 运行去重测试
poetry run pytest tests/octopus_scraper/scrapers/content_deduplicator_test.py -v
```

### 运行集成测试

```bash
# 运行抓取器集成测试
poetry run pytest tests/integrate_tests/scraper_integration_test.py -v

# 运行性能测试
poetry run pytest tests/octopus_scraper/scrapers/performance_test.py -v
```

### 运行覆盖率测试

```bash
# 运行带覆盖率的测试
poetry run pytest tests/octopus_scraper/scrapers/ --cov=src/octopus_scraper/scrapers --cov-report=html

# 查看覆盖率报告
open htmlcov/index.html
```

## 测试工具和辅助函数

### 测试数据生成

```python
def create_large_rss_content(num_items: int) -> str:
    """创建大型 RSS 内容用于性能测试"""

    items = []
    for i in range(num_items):
        item = f"""
        <item>
            <title>Article {i}</title>
            <link>https://example.com/article{i}</link>
            <description>Description for article {i}</description>
            <pubDate>Wed, {15 - (i % 30)} Nov 2023 10:00:00 GMT</pubDate>
            <author>Author {i % 10}</author>
            <category>Category {i % 5}</category>
        </item>"""
        items.append(item)

    return f"""<?xml version="1.0"?>
    <rss version="2.0">
        <channel>
            <title>Large RSS Feed</title>
            {''.join(items)}
        </channel>
    </rss>"""

def assert_scraping_result(result: ScrapingResult, **expected):
    """验证抓取结果"""
    for key, value in expected.items():
        actual = getattr(result, key)
        assert actual == value, f"Expected {key}={value}, got {actual}"

def assert_scraping_item(item: ScrapingItem, **expected):
    """验证抓取项目"""
    for key, value in expected.items():
        actual = getattr(item, key)
        assert actual == value, f"Expected {key}={value}, got {actual}"
```

### Mock 辅助函数

```python
def setup_rss_mock(m, url: str, content: str = None):
    """设置 RSS Mock 响应"""
    if content is None:
        content = sample_rss_content
    m.get(url, body=content)

def setup_notion_mock(m, database_id: str, response_data: dict):
    """设置 Notion API Mock 响应"""
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    m.post(url, payload=response_data)

def setup_error_mock(m, url: str, error_type: Exception):
    """设置错误 Mock 响应"""
    m.get(url, exception=error_type)
```

## 故障排除

### 常见测试问题

1. **aioresponses 配置问题**
   ```python
   # 确保正确使用 aioresponses
   with aioresponses() as m:
       m.get('https://example.com', body='response')
       # 测试代码
   ```

2. **异步测试超时**
   ```python
   # 使用适当的超时时间
   await asyncio.wait_for(scraper.scrape(), timeout=10.0)
   ```

3. **Mock 响应不匹配**
   ```python
   # 确保 URL 完全匹配
   m.get('https://example.com/rss.xml', body=rss_content)
   # 不是 'http://example.com/rss.xml'
   ```

## 测试最佳实践

1. **异步测试**: 正确使用 `@pytest.mark.asyncio`
2. **Mock 管理**: 合理使用 aioresponses 和其他 Mock 工具
3. **数据隔离**: 每个测试使用独立的测试数据
4. **错误覆盖**: 测试各种错误和边界情况
5. **性能验证**: 包含性能和内存使用测试
6. **集成测试**: 验证与其他组件的集成

## 相关文档

- [Scrapers Models](./scrapers.md)
- [ConfigManager Testing](../config/config-manager-testing.md)
- [TaskManager Testing](../task_manager/task-manager-testing.md)
- [Web Service Testing](../../interface/web_service/admin-interface-testing.md)
