# Storages 模型文档

## 概述

Storages 是 OctopusScraper 的内容存储模块，负责将抓取到的内容存储到不同的存储系统中。系统采用抽象基类设计，支持多种存储后端，并提供统一的接口和去重功能。

## 模块结构

```
src/octopus_scraper/storages/
├── __init__.py                # 模块初始化
├── base_storage.py            # 存储抽象基类
└── notion_storage.py          # Notion 存储实现
```

## 核心类和接口

### 1. BaseStorage (存储抽象基类)

**模块路径**: `src/octopus_scraper/storages/base_storage.py`

**作用**: 定义存储系统的统一接口，提供批量存储和去重功能

```python
from abc import ABCMeta
from typing import List
from octopus_scraper.scrapers.scraper_protos import Content

class BaseStorage(metaclass=ABCMeta):
    """存储系统抽象基类"""

    def _store_content(self, content: Content) -> bool:
        """存储单个内容到存储系统
        
        Args:
            content (Content): 要存储的内容对象
            
        Returns:
            bool: 存储成功返回 True，失败返回 False
        """
        raise NotImplementedError("Subclasses should implement this method.")

    def _get_all_content_ids(self) -> set:
        """获取存储系统中所有已存在的内容ID
        
        Returns:
            set: 已存在的内容ID集合
        """
        raise NotImplementedError("Subclasses should implement this method.")

    def store_contents(self, contents: List[Content], deduplicate=True) -> List[bool]:
        """批量存储内容到存储系统
        
        Args:
            contents (List[Content]): 要存储的内容列表
            deduplicate (bool): 是否启用去重功能，默认为 True
            
        Returns:
            List[bool]: 每个内容存储结果的列表，True 表示存储成功或已存在
        """
        if not contents:
            return []

        existing_content_ids = self._get_all_content_ids()
        store_contents = []
        
        if deduplicate:
            for content in contents:
                if content.content_id not in existing_content_ids:
                    store_contents.append(content)
        else:
            store_contents = contents

        # 存储新内容
        results = []
        for content in store_contents:
            results.append(self._store_content(content))

        # 为已存在的内容返回 True（表示"处理成功"）
        skipped_count = len(contents) - len(store_contents)
        results.extend([True] * skipped_count)

        return results
```

### 2. NotionStorage (Notion 存储实现)

**模块路径**: `src/octopus_scraper/storages/notion_storage.py`

**作用**: 将内容存储到 Notion 数据库中，支持富文本、链接、代码块等格式

```python
from dataclasses import dataclass
from typing import Dict, List
from notion_client import Client
from octopus_scraper.storages.base_storage import BaseStorage
from octopus_scraper.scrapers.scraper_protos import Content

@dataclass
class NotionAPIConfig:
    """Notion API 配置"""
    api_key: str
    database_id: str

class NotionStorage(BaseStorage):
    """Notion 数据库存储实现
    
    Examples:
    >>> config = {'api_key': 'your_api_key', 'database_id': 'your_db_id'}
    >>> notion_storage = NotionStorage(config)
    >>> notion_storage.store_contents(contents)
    """

    def __init__(self, config: Dict):
        """初始化 Notion 存储
        
        Args:
            config (Dict): 包含 api_key 和 database_id 的配置字典
        """
        self.config = from_dict(
            data_class=NotionAPIConfig,
            data=config,
            config=Config(cast=[str], strict=True),
        )
        
        self.notion = Client(auth=self.config.api_key)
        self._check_property_exist()
```

#### 核心方法

```python
def _get_all_content_ids(self) -> set:
    """批量获取数据库中所有已存在的 content_id
    
    使用分页查询获取所有内容ID，支持大量数据的处理
    
    Returns:
        set: 已存在的内容ID集合
    """

def _store_content(self, content: Content) -> bool:
    """存储单个内容到 Notion 数据库
    
    Args:
        content (Content): 要存储的内容对象
        
    Returns:
        bool: 存储成功返回 True，失败返回 False
    """

def _build_properties(self, content: Content) -> dict:
    """构建 Notion 页面属性结构
    
    Args:
        content (Content): 内容对象
        
    Returns:
        dict: Notion 页面属性字典
    """

def _split_text_chunks(self, text: str, max_len: int) -> List[Dict]:
    """将长文本按自然段落分割成符合 Notion 限制的块
    
    Args:
        text (str): 要分割的文本
        max_len (int): 每个块的最大长度
        
    Returns:
        List[Dict]: 文本块列表
    """

def _parse_markdown_to_notion_blocks(self, chunk: Dict) -> List[Dict]:
    """将 Markdown 块转换为 Notion 块
    
    支持的 Markdown 格式：
    - 标题（# ## ###）
    - 列表（- *）
    - 代码块（`）
    - 链接（[text](url)）
    
    Args:
        chunk (Dict): 文本块
        
    Returns:
        List[Dict]: Notion 块列表
    """
```

#### 常量定义

```python
MAX_NOTION_SUMMARY_LENGTH = 2000
NOTION_PROPERTIY_TITLE_NAME = "Name"
NOTION_PROPERTIY_SUMMARY_NAME = "Summary"
NOTION_PROPERTIY_CONTENT_ID = "ContentId"
NOTION_PROPERTIY_URL = "URL"
```

## 配置示例

### Notion 存储配置

```yaml
# 在主配置文件中
notion_api_config:
  api_key: "${NOTION_API_KEY}"
  database_id: "${NOTION_CONTENT_DATABASE_ID}"

# 环境变量
NOTION_API_KEY=secret_your_notion_integration_token
NOTION_CONTENT_DATABASE_ID=your_database_id_here
```

### 使用示例

```python
from octopus_scraper.storages.notion_storage import NotionStorage
from octopus_scraper.scrapers.scraper_protos import Content

# 初始化存储
config = {
    'api_key': 'secret_your_notion_integration_token',
    'database_id': 'your_database_id_here'
}
storage = NotionStorage(config)

# 创建内容对象
contents = [
    Content(
        title="示例文章",
        content="这是文章内容...",
        summary="这是摘要",
        link="https://example.com/article",
        content_id="unique_id_123"
    )
]

# 存储内容（启用去重）
results = storage.store_contents(contents, deduplicate=True)
print(f"存储结果: {results}")

# 存储内容（不去重）
results = storage.store_contents(contents, deduplicate=False)
```

## Notion 数据库结构

NotionStorage 会自动创建或更新数据库的属性结构：

| 属性名 | 类型 | 描述 |
|--------|------|------|
| Name | Title | 内容标题 |
| Summary | Rich Text | 内容摘要（最大 2000 字符） |
| URL | URL | 内容链接 |
| ContentId | Rich Text | 唯一内容标识符 |

## 内容格式支持

### Markdown 转换

NotionStorage 支持将 Markdown 格式转换为 Notion 块：

```python
# 支持的格式示例
content = """
# 标题 1
## 标题 2
### 标题 3

- 列表项 1
- 列表项 2

* 另一种列表
* 列表项

`代码块`

[链接文本](https://example.com)

普通段落文本
"""
```

### 长文本处理

- 自动分割超长文本
- 按自然段落分割
- 保持文本完整性
- 符合 Notion API 限制

## 错误处理和重试

### 重试机制

```python
from tenacity import retry, stop_after_attempt, wait_fixed

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def _store_content(self, content: Content) -> bool:
    """存储内容，支持自动重试"""

@retry(stop=stop_after_attempt(2), wait=wait_fixed(1))
def _get_all_content_ids(self) -> set:
    """获取内容ID，支持自动重试"""
```

### 错误类型

- **配置错误**: API 密钥或数据库 ID 无效
- **网络错误**: Notion API 连接失败
- **权限错误**: 集成没有数据库访问权限
- **格式错误**: 内容格式不符合 Notion 要求

## 性能优化

### 批量操作

- 批量获取已存在的内容 ID
- 减少 API 调用次数
- 支持大量内容的高效处理

### 分页查询

```python
# 分页获取所有内容ID
while has_more:
    query_params = {
        "database_id": self.config.database_id,
        "page_size": 100,  # Notion API 最大支持 100
    }
    if next_cursor:
        query_params["start_cursor"] = next_cursor
        
    response = self.notion.databases.query(**query_params)
    # 处理响应...
```

### 去重机制

- 在存储前检查内容是否已存在
- 使用 content_id 进行唯一性判断
- 避免重复存储，节省 API 配额

## 扩展存储后端

### 创建新的存储实现

```python
from octopus_scraper.storages.base_storage import BaseStorage
from octopus_scraper.scrapers.scraper_protos import Content

class CustomStorage(BaseStorage):
    """自定义存储实现示例"""

    def __init__(self, config: Dict):
        self.config = config
        # 初始化存储连接

    def _store_content(self, content: Content) -> bool:
        """实现具体的存储逻辑"""
        try:
            # 存储逻辑
            return True
        except Exception as e:
            logger.error(f"存储失败: {e}")
            return False

    def _get_all_content_ids(self) -> set:
        """实现获取已存在内容ID的逻辑"""
        try:
            # 查询逻辑
            return set()
        except Exception as e:
            logger.error(f"查询失败: {e}")
            return set()
```

### 注册存储后端

```python
# 存储注册表（可扩展）
class StorageRegistry:
    def __init__(self):
        self._storages = {}

    def register(self, name: str, storage_class: type):
        self._storages[name] = storage_class

    def create_storage(self, name: str, config: Dict):
        if name in self._storages:
            return self._storages[name](config)
        raise ValueError(f"Unknown storage type: {name}")

# 注册内置存储
storage_registry = StorageRegistry()
storage_registry.register('notion', NotionStorage)
```

## 与其他模块集成

### 与 Scrapers 集成

```python
from octopus_scraper.scrapers import ScraperManager
from octopus_scraper.storages.notion_storage import NotionStorage

# 在抓取器中使用存储
class ScraperWithStorage:
    def __init__(self, scraper_config, storage_config):
        self.scraper = ScraperManager(scraper_config)
        self.storage = NotionStorage(storage_config)

    async def scrape_and_store(self):
        # 执行抓取
        results = await self.scraper.run_all_scrapers()
        
        # 存储内容
        for result in results:
            if result.success and result.items:
                contents = [self._convert_to_content(item) for item in result.items]
                self.storage.store_contents(contents)
```

### 与任务管理器集成

```python
from octopus_scraper.task_manager import Task, TaskResult, TaskStatus

class StorageTask(Task):
    """存储任务"""

    def __init__(self, contents: List[Content], storage: BaseStorage):
        super().__init__(task_type="storage")
        self.contents = contents
        self.storage = storage

    async def execute(self) -> TaskResult:
        """执行存储任务"""
        try:
            results = self.storage.store_contents(self.contents)
            success_count = sum(results)
            
            return TaskResult(
                task_id=self.task_id,
                status=TaskStatus.COMPLETED,
                result_data={
                    'total': len(results),
                    'success': success_count,
                    'failed': len(results) - success_count
                }
            )
        except Exception as e:
            return TaskResult(
                task_id=self.task_id,
                status=TaskStatus.FAILED,
                error_message=str(e)
            )
```

## 最佳实践

### 配置管理

1. **环境变量**: 敏感信息使用环境变量
2. **配置验证**: 启动时验证存储配置
3. **连接测试**: 定期测试存储连接状态

### 错误处理

1. **重试机制**: 对临时性错误进行重试
2. **日志记录**: 详细记录存储操作日志
3. **优雅降级**: 存储失败时的备用方案

### 性能优化

1. **批量操作**: 尽量使用批量API
2. **去重检查**: 避免重复存储相同内容
3. **分页查询**: 处理大量数据时使用分页

### 监控和调试

```python
import structlog

# 配置结构化日志
logger = structlog.getLogger(__name__)

# 在存储操作中添加详细日志
logger.info("Content stored successfully", 
           content_id=content.content_id,
           storage_type="notion")

logger.error("Storage failed", 
            content_id=content.content_id,
            error=str(e),
            storage_type="notion")
```

## 相关文档

- [Scrapers Models](../scrapers/scrapers.md)
- [Config Manager Models](../config/config-manager.md)
- [Task Manager Models](../task_manager/task-manager.md)
- [Service Models](../service/service-models.md)
- [Storages Testing](./storages-testing.md)
