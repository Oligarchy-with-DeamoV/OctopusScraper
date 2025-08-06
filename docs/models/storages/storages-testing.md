# Storages 测试文档

## 概述

本文档描述了 OctopusScraper Storages 模块的测试策略、测试用例和测试实践。测试覆盖单元测试、集成测试和性能测试等多个层面。

## 测试结构

```
tests/octopus_scraper/storages/
└── notion_storage_test.py     # Notion 存储单元测试
```

## 单元测试

### NotionStorage 测试

**测试文件**: `tests/octopus_scraper/storages/notion_storage_test.py`

#### 测试覆盖范围

1. **初始化测试**
   - 配置验证
   - API 客户端初始化
   - 数据库属性检查

2. **内容存储测试**
   - 单个内容存储
   - 批量内容存储
   - 去重功能测试

3. **内容查询测试**
   - 获取已存在内容ID
   - 分页查询测试
   - 空数据库测试

4. **格式转换测试**
   - Markdown 转 Notion 块
   - 长文本分割
   - 属性构建

5. **错误处理测试**
   - API 错误处理
   - 网络超时处理
   - 重试机制测试

#### 测试用例示例

```python
import pytest
from unittest.mock import Mock, patch, AsyncMock
from octopus_scraper.storages.notion_storage import NotionStorage, NotionAPIConfig
from octopus_scraper.scrapers.scraper_protos import Content

class TestNotionStorage:
    """NotionStorage 单元测试"""

    @pytest.fixture
    def valid_config(self):
        """有效的配置"""
        return {
            'api_key': 'test_api_key',
            'database_id': 'test_database_id'
        }

    @pytest.fixture
    def sample_content(self):
        """示例内容"""
        return Content(
            title="测试标题",
            content="这是测试内容",
            summary="这是测试摘要",
            link="https://example.com",
            content_id="test_123"
        )

    @pytest.fixture
    def notion_storage(self, valid_config):
        """NotionStorage 实例"""
        with patch('octopus_scraper.storages.notion_storage.Client'):
            storage = NotionStorage(valid_config)
            storage.notion = Mock()
            return storage

    def test_init_with_valid_config(self, valid_config):
        """测试使用有效配置初始化"""
        with patch('octopus_scraper.storages.notion_storage.Client') as mock_client:
            storage = NotionStorage(valid_config)
            
            assert storage.config.api_key == 'test_api_key'
            assert storage.config.database_id == 'test_database_id'
            mock_client.assert_called_once_with(auth='test_api_key')

    def test_init_with_invalid_config(self):
        """测试使用无效配置初始化"""
        invalid_config = {'api_key': 'test_key'}  # 缺少 database_id
        
        with pytest.raises(Exception):
            NotionStorage(invalid_config)

    def test_build_properties(self, notion_storage, sample_content):
        """测试构建属性"""
        properties = notion_storage._build_properties(sample_content)
        
        assert 'Name' in properties
        assert 'Summary' in properties
        assert 'URL' in properties
        assert 'ContentId' in properties
        
        assert properties['Name']['title'][0]['text']['content'] == "测试标题"
        assert properties['URL']['url'] == "https://example.com"

    def test_split_text_chunks(self, notion_storage):
        """测试文本分割"""
        text = "段落1\n\n段落2\n\n段落3"
        chunks = notion_storage._split_text_chunks(text, max_len=10)
        
        assert len(chunks) > 0
        for chunk in chunks:
            assert 'type' in chunk
            assert 'text' in chunk
            assert len(chunk['text']['content']) <= 10

    def test_parse_markdown_to_notion_blocks_heading(self, notion_storage):
        """测试 Markdown 标题转换"""
        chunk = {'text': {'content': '# 标题 1'}}
        blocks = notion_storage._parse_markdown_to_notion_blocks(chunk)
        
        assert len(blocks) == 1
        assert blocks[0]['type'] == 'heading_1'
        assert blocks[0]['heading_1']['rich_text'][0]['text']['content'] == '标题 1'

    def test_parse_markdown_to_notion_blocks_list(self, notion_storage):
        """测试 Markdown 列表转换"""
        chunk = {'text': {'content': '- 列表项'}}
        blocks = notion_storage._parse_markdown_to_notion_blocks(chunk)
        
        assert len(blocks) == 1
        assert blocks[0]['type'] == 'bulleted_list_item'
        assert blocks[0]['bulleted_list_item']['rich_text'][0]['text']['content'] == '列表项'

    def test_parse_markdown_to_notion_blocks_link(self, notion_storage):
        """测试 Markdown 链接转换"""
        chunk = {'text': {'content': '[链接文本](https://example.com)'}}
        blocks = notion_storage._parse_markdown_to_notion_blocks(chunk)
        
        assert len(blocks) == 1
        assert blocks[0]['type'] == 'bookmark'
        assert blocks[0]['bookmark']['url'] == 'https://example.com'

    def test_get_all_content_ids_empty(self, notion_storage):
        """测试获取空数据库的内容ID"""
        notion_storage.notion.databases.query.return_value = {
            'results': [],
            'has_more': False
        }
        
        content_ids = notion_storage._get_all_content_ids()
        assert content_ids == set()

    def test_get_all_content_ids_with_data(self, notion_storage):
        """测试获取包含数据的内容ID"""
        notion_storage.notion.databases.query.return_value = {
            'results': [
                {
                    'properties': {
                        'ContentId': {
                            'rich_text': [
                                {'text': {'content': 'id1'}}
                            ]
                        }
                    }
                },
                {
                    'properties': {
                        'ContentId': {
                            'rich_text': [
                                {'text': {'content': 'id2'}}
                            ]
                        }
                    }
                }
            ],
            'has_more': False
        }
        
        content_ids = notion_storage._get_all_content_ids()
        assert content_ids == {'id1', 'id2'}

    def test_get_all_content_ids_pagination(self, notion_storage):
        """测试分页查询内容ID"""
        # 模拟分页响应
        responses = [
            {
                'results': [
                    {
                        'properties': {
                            'ContentId': {
                                'rich_text': [{'text': {'content': 'id1'}}]
                            }
                        }
                    }
                ],
                'has_more': True,
                'next_cursor': 'cursor1'
            },
            {
                'results': [
                    {
                        'properties': {
                            'ContentId': {
                                'rich_text': [{'text': {'content': 'id2'}}]
                            }
                        }
                    }
                ],
                'has_more': False
            }
        ]
        
        notion_storage.notion.databases.query.side_effect = responses
        
        content_ids = notion_storage._get_all_content_ids()
        assert content_ids == {'id1', 'id2'}
        assert notion_storage.notion.databases.query.call_count == 2

    def test_store_content_success(self, notion_storage, sample_content):
        """测试成功存储内容"""
        notion_storage.notion.pages.create.return_value = {'id': 'page_id'}
        
        result = notion_storage._store_content(sample_content)
        assert result is True
        notion_storage.notion.pages.create.assert_called_once()

    def test_store_content_failure(self, notion_storage, sample_content):
        """测试存储内容失败"""
        notion_storage.notion.pages.create.side_effect = Exception("API Error")
        
        result = notion_storage._store_content(sample_content)
        assert result is False

    def test_store_contents_with_deduplication(self, notion_storage):
        """测试启用去重的批量存储"""
        contents = [
            Content(title="内容1", content="", summary="", link="", content_id="id1"),
            Content(title="内容2", content="", summary="", link="", content_id="id2"),
            Content(title="内容3", content="", summary="", link="", content_id="id3")
        ]
        
        # 模拟已存在 id1
        notion_storage._get_all_content_ids = Mock(return_value={'id1'})
        notion_storage._store_content = Mock(return_value=True)
        
        results = notion_storage.store_contents(contents, deduplicate=True)
        
        # 应该只存储 id2 和 id3，id1 被跳过
        assert len(results) == 3
        assert all(results)  # 所有结果都应该是 True
        assert notion_storage._store_content.call_count == 2

    def test_store_contents_without_deduplication(self, notion_storage):
        """测试不启用去重的批量存储"""
        contents = [
            Content(title="内容1", content="", summary="", link="", content_id="id1"),
            Content(title="内容2", content="", summary="", link="", content_id="id2")
        ]
        
        notion_storage._get_all_content_ids = Mock(return_value={'id1'})
        notion_storage._store_content = Mock(return_value=True)
        
        results = notion_storage.store_contents(contents, deduplicate=False)
        
        # 应该存储所有内容，包括重复的
        assert len(results) == 2
        assert all(results)
        assert notion_storage._store_content.call_count == 2

    def test_store_contents_empty_list(self, notion_storage):
        """测试存储空列表"""
        results = notion_storage.store_contents([])
        assert results == []

    def test_summary_truncation(self, notion_storage):
        """测试摘要截断"""
        long_summary = "a" * 3000  # 超过 2000 字符限制
        content = Content(
            title="测试",
            content="",
            summary=long_summary,
            link="",
            content_id="test"
        )
        
        properties = notion_storage._build_properties(content)
        summary_content = properties['Summary']['rich_text'][0]['text']['content']
        
        assert len(summary_content) == 2000
        assert summary_content == long_summary[:2000]

    def test_check_property_exist(self, notion_storage):
        """测试检查数据库属性"""
        notion_storage._check_property_exist()
        
        notion_storage.notion.databases.update.assert_called_once()
        call_args = notion_storage.notion.databases.update.call_args
        
        assert call_args[1]['database_id'] == 'test_database_id'
        assert 'Name' in call_args[1]['properties']
        assert 'Summary' in call_args[1]['properties']
        assert 'URL' in call_args[1]['properties']
        assert 'ContentId' in call_args[1]['properties']
```

## 集成测试

### Notion API 集成测试

```python
import pytest
import os
from octopus_scraper.storages.notion_storage import NotionStorage
from octopus_scraper.scrapers.scraper_protos import Content

@pytest.mark.integration
class TestNotionStorageIntegration:
    """Notion 存储集成测试"""

    @pytest.fixture
    def real_notion_storage(self):
        """真实的 Notion 存储实例"""
        config = {
            'api_key': os.getenv('NOTION_API_KEY'),
            'database_id': os.getenv('NOTION_TEST_DATABASE_ID')
        }
        
        if not config['api_key'] or not config['database_id']:
            pytest.skip("需要设置 NOTION_API_KEY 和 NOTION_TEST_DATABASE_ID 环境变量")
        
        return NotionStorage(config)

    @pytest.mark.asyncio
    async def test_real_storage_workflow(self, real_notion_storage):
        """测试真实存储工作流"""
        # 创建测试内容
        content = Content(
            title=f"集成测试 {datetime.now().isoformat()}",
            content="这是集成测试内容\n\n包含多个段落。",
            summary="集成测试摘要",
            link="https://example.com/integration-test",
            content_id=f"integration_test_{int(time.time())}"
        )
        
        # 存储内容
        results = real_notion_storage.store_contents([content])
        assert len(results) == 1
        assert results[0] is True
        
        # 验证去重功能
        duplicate_results = real_notion_storage.store_contents([content])
        assert len(duplicate_results) == 1
        assert duplicate_results[0] is True  # 应该跳过重复内容

    @pytest.mark.asyncio
    async def test_batch_storage(self, real_notion_storage):
        """测试批量存储"""
        contents = []
        timestamp = int(time.time())
        
        for i in range(5):
            content = Content(
                title=f"批量测试内容 {i+1}",
                content=f"这是第 {i+1} 个测试内容",
                summary=f"第 {i+1} 个摘要",
                link=f"https://example.com/batch-test-{i+1}",
                content_id=f"batch_test_{timestamp}_{i+1}"
            )
            contents.append(content)
        
        results = real_notion_storage.store_contents(contents)
        assert len(results) == 5
        assert all(results)
```

## Mock 测试

### API 调用 Mock

```python
import pytest
from unittest.mock import Mock, patch
from octopus_scraper.storages.notion_storage import NotionStorage

class TestNotionStorageMock:
    """使用 Mock 的测试"""

    @patch('octopus_scraper.storages.notion_storage.Client')
    def test_api_error_handling(self, mock_client_class):
        """测试 API 错误处理"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        # 模拟 API 错误
        mock_client.databases.query.side_effect = Exception("API Rate Limit")
        
        config = {'api_key': 'test', 'database_id': 'test'}
        storage = NotionStorage(config)
        
        # 测试错误是否被正确处理
        with pytest.raises(Exception):
            storage._get_all_content_ids()

    @patch('octopus_scraper.storages.notion_storage.retry')
    def test_retry_mechanism(self, mock_retry):
        """测试重试机制"""
        # 验证重试装饰器被正确应用
        assert mock_retry.called
```

## 性能测试

### 大量数据测试

```python
import pytest
import time
from octopus_scraper.storages.notion_storage import NotionStorage

@pytest.mark.performance
class TestNotionStoragePerformance:
    """性能测试"""

    def test_large_batch_performance(self, notion_storage):
        """测试大批量数据性能"""
        # 创建 1000 个测试内容
        contents = []
        for i in range(1000):
            content = Content(
                title=f"性能测试 {i}",
                content=f"内容 {i}",
                summary=f"摘要 {i}",
                link=f"https://example.com/{i}",
                content_id=f"perf_test_{i}"
            )
            contents.append(content)
        
        # 测试存储时间
        start_time = time.time()
        results = notion_storage.store_contents(contents)
        end_time = time.time()
        
        execution_time = end_time - start_time
        
        # 验证结果
        assert len(results) == 1000
        assert execution_time < 60  # 应在 60 秒内完成
        print(f"存储 1000 条记录耗时: {execution_time:.2f} 秒")

    def test_pagination_performance(self, notion_storage):
        """测试分页查询性能"""
        # 模拟大量已存在的内容
        large_response = {
            'results': [
                {
                    'properties': {
                        'ContentId': {
                            'rich_text': [{'text': {'content': f'id_{i}'}}]
                        }
                    }
                } for i in range(100)
            ],
            'has_more': False
        }
        
        notion_storage.notion.databases.query.return_value = large_response
        
        start_time = time.time()
        content_ids = notion_storage._get_all_content_ids()
        end_time = time.time()
        
        assert len(content_ids) == 100
        assert end_time - start_time < 5  # 应在 5 秒内完成
```

## 测试配置

### pytest 配置

```ini
# pytest.ini
[tool:pytest]
markers =
    integration: marks tests as integration tests
    performance: marks tests as performance tests
    slow: marks tests as slow running

testpaths = tests
python_files = test_*.py *_test.py
python_classes = Test*
python_functions = test_*

# 跳过集成测试（除非明确指定）
addopts = -m "not integration and not performance"
```

### 环境变量配置

```bash
# 测试环境变量
export NOTION_API_KEY="your_test_api_key"
export NOTION_TEST_DATABASE_ID="your_test_database_id"

# 运行集成测试
pytest -m integration

# 运行性能测试
pytest -m performance

# 运行所有测试
pytest -m ""
```

## 测试数据管理

### 测试数据清理

```python
import pytest
from octopus_scraper.storages.notion_storage import NotionStorage

@pytest.fixture(scope="session")
def test_data_cleanup():
    """测试数据清理"""
    # 测试前清理
    yield
    
    # 测试后清理
    # 这里可以添加清理测试数据的逻辑
    pass

class TestDataManager:
    """测试数据管理"""

    def setup_method(self):
        """每个测试方法前的设置"""
        self.test_content_ids = []

    def teardown_method(self):
        """每个测试方法后的清理"""
        # 清理测试创建的内容
        for content_id in self.test_content_ids:
            # 删除测试内容的逻辑
            pass
```

## 测试覆盖率

### 生成覆盖率报告

```bash
# 安装覆盖率工具
pip install pytest-cov

# 运行测试并生成覆盖率报告
pytest --cov=src/octopus_scraper/storages --cov-report=html

# 查看覆盖率报告
open htmlcov/index.html
```

### 覆盖率目标

- **总体覆盖率**: > 90%
- **分支覆盖率**: > 85%
- **函数覆盖率**: 100%

## 最佳实践

### 测试组织

1. **按功能分组**: 将相关测试放在同一个测试类中
2. **使用 Fixtures**: 重用测试数据和设置
3. **参数化测试**: 使用 `@pytest.mark.parametrize` 测试多种情况
4. **标记测试**: 使用标记区分不同类型的测试

### 测试数据

1. **独立性**: 每个测试应该独立运行
2. **可预测性**: 使用固定的测试数据
3. **清理**: 及时清理测试产生的数据
4. **隔离**: 测试数据不应影响生产环境

### Mock 策略

1. **外部依赖**: Mock 所有外部 API 调用
2. **网络调用**: Mock 网络请求避免真实调用
3. **时间依赖**: Mock 时间相关函数确保一致性
4. **文件操作**: Mock 文件 I/O 操作

### 错误测试

1. **异常情况**: 测试各种异常和错误条件
2. **边界条件**: 测试边界值和极端情况
3. **资源限制**: 测试资源不足的情况
4. **超时处理**: 测试超时和重试机制

## 持续集成

### GitHub Actions 配置

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.8, 3.9, 3.10]

    steps:
    - uses: actions/checkout@v2
    
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v2
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        pip install -e .
        pip install pytest pytest-cov pytest-asyncio
    
    - name: Run unit tests
      run: |
        pytest tests/octopus_scraper/storages/ --cov=src/octopus_scraper/storages
    
    - name: Run integration tests
      if: env.NOTION_API_KEY != ''
      env:
        NOTION_API_KEY: ${{ secrets.NOTION_API_KEY }}
        NOTION_TEST_DATABASE_ID: ${{ secrets.NOTION_TEST_DATABASE_ID }}
      run: |
        pytest -m integration
```

## 相关文档

- [Storages Models](./storages.md)
- [Scrapers Testing](../scrapers/scrapers-testing.md)
- [Config Manager Testing](../config/config-manager-testing.md)
- [Service Models Testing](../service/service-models-testing.md)
