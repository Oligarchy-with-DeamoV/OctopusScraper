# Scrapers 模型文档

## 概述

Scrapers 是 OctopusScraper 的核心模块，负责从各种数据源抓取内容。系统采用插件化架构，支持多种抓取器类型，并提供统一的接口和配置管理。

## 模块结构

```
src/octopus_scraper/scrapers/
├── __init__.py                 # 模块初始化和抓取器注册
├── scraper.py                 # 核心抓取器类
├── scraper_protos.py          # 抓取器协议和数据模型
├── processors/                # 内容处理器模块
├── utils/                     # 抓取工具和辅助函数
│   ├── direct_rss.py          # RSS 直接抓取器
│   ├── rsshub.py              # RSSHub 抓取器
│   ├── notion_api.py          # Notion API 集成
│   ├── content_deduplicator.py # 内容去重处理器
│   └── tools.py               # 抓取工具和辅助函数
```

## 核心类和接口

### 1. Scraper (核心抓取器类)

**模块路径**: `src/octopus_scraper/scrapers/scraper.py`

**作用**: 抓取器核心实现，整合数据获取器和内容处理器

该类是实际的抓取器实现，不是抽象基类，而是具体的功能类：

```python
class Scraper:
    def __init__(self, config: Dict):
        self.config = from_dict(BaseScraperConfig, config)
        self.storage = None  # 可选的存储器，用于去重
        # 初始化数据获取器和内容处理器
    """抓取器基类，定义了所有抓取器的通用接口"""

    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self.enabled = config.get('enabled', True)

    @abstractmethod
    async def scrape(self) -> ScrapingResult:
        """执行抓取操作，返回抓取结果"""
        pass

    @abstractmethod
    def validate_config(self) -> bool:
        """验证配置是否正确"""
        pass

    def get_scraper_info(self) -> Dict[str, Any]:
        """获取抓取器信息"""
        return {
            'name': self.name,
            'type': self.__class__.__name__,
            'enabled': self.enabled,
            'config_keys': list(self.config.keys())
        }
```

### 2. ScraperRegistry (抓取器注册表)

```python
from typing import Dict, Type, List
from .base_scraper import BaseScraper

class ScraperRegistry:
    """抓取器注册表，管理所有可用的抓取器类型"""

    def __init__(self):
        self._scrapers: Dict[str, Type[BaseScraper]] = {}

    def register(self, scraper_type: str, scraper_class: Type[BaseScraper]):
        """注册抓取器类型"""
        self._scrapers[scraper_type] = scraper_class

    def create_scraper(self, scraper_type: str, name: str, config: Dict[str, Any]) -> BaseScraper:
        """创建抓取器实例"""
        if scraper_type not in self._scrapers:
            raise ValueError(f"Unknown scraper type: {scraper_type}")

        scraper_class = self._scrapers[scraper_type]
        return scraper_class(name, config)

    def get_available_types(self) -> List[str]:
        """获取可用的抓取器类型"""
        return list(self._scrapers.keys())

# 全局注册表实例
scraper_registry = ScraperRegistry()
```

### 3. ScrapingResult (抓取结果模型)

```python
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from datetime import datetime

@dataclass
class ScrapingItem:
    """单个抓取项目"""
    title: str
    url: str
    content: Optional[str] = None
    summary: Optional[str] = None
    author: Optional[str] = None
    published_date: Optional[datetime] = None
    tags: List[str] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.metadata is None:
            self.metadata = {}

@dataclass
class ScrapingResult:
    """抓取结果"""
    scraper_name: str
    success: bool
    items: List[ScrapingItem]
    error_message: Optional[str] = None
    execution_time: float = 0.0
    total_items: int = 0
    new_items: int = 0
    duplicate_items: int = 0

    def __post_init__(self):
        if self.total_items == 0:
            self.total_items = len(self.items)
```

## 内置抓取器实现

### 1. DirectRssScraper (RSS 直接抓取器)

```python
import feedparser
import aiohttp
from typing import List, Dict, Any
from .base_scraper import BaseScraper
from ..service_models import ScrapingResult, ScrapingItem

class DirectRssScraper(BaseScraper):
    """直接从 RSS 源抓取内容"""

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        self.rss_url = config['rss_url']
        self.max_items = config.get('max_items', 50)

    def validate_config(self) -> bool:
        """验证配置"""
        required_keys = ['rss_url']
        return all(key in self.config for key in required_keys)

    async def scrape(self) -> ScrapingResult:
        """执行 RSS 抓取"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.rss_url) as response:
                    content = await response.text()

            feed = feedparser.parse(content)
            items = []

            for entry in feed.entries[:self.max_items]:
                item = ScrapingItem(
                    title=entry.get('title', ''),
                    url=entry.get('link', ''),
                    content=entry.get('description', ''),
                    author=entry.get('author', ''),
                    published_date=self._parse_date(entry.get('published')),
                    tags=self._extract_tags(entry)
                )
                items.append(item)

            return ScrapingResult(
                scraper_name=self.name,
                success=True,
                items=items
            )

        except Exception as e:
            return ScrapingResult(
                scraper_name=self.name,
                success=False,
                items=[],
                error_message=str(e)
            )

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """解析日期字符串"""
        # 实现日期解析逻辑
        pass

    def _extract_tags(self, entry) -> List[str]:
        """提取标签"""
        # 实现标签提取逻辑
        pass
```

### 2. RsshubScraper (RSSHub 抓取器)

```python
from typing import Dict, Any, List
from .direct_rss import DirectRssScraper

class RsshubScraper(DirectRssScraper):
    """通过 RSSHub 抓取内容"""

    def __init__(self, name: str, config: Dict[str, Any]):
        # 构造 RSSHub URL
        rsshub_base = config.get('rsshub_base', 'https://rsshub.app')
        route = config['route']
        rss_url = f"{rsshub_base.rstrip('/')}/{route.lstrip('/')}"

        # 更新配置
        config = config.copy()
        config['rss_url'] = rss_url

        super().__init__(name, config)
        self.route = route
        self.rsshub_base = rsshub_base

    def validate_config(self) -> bool:
        """验证 RSSHub 配置"""
        required_keys = ['route']
        return all(key in self.config for key in required_keys)

    def get_scraper_info(self) -> Dict[str, Any]:
        """获取抓取器信息"""
        info = super().get_scraper_info()
        info.update({
            'rsshub_base': self.rsshub_base,
            'route': self.route,
            'generated_url': self.rss_url
        })
        return info
```

### 3. NotionApiScraper (Notion API 抓取器)

```python
import aiohttp
from typing import Dict, Any, List
from .base_scraper import BaseScraper
from ..service_models import ScrapingResult, ScrapingItem

class NotionApiScraper(BaseScraper):
    """通过 Notion API 抓取数据库内容"""

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        self.database_id = config['database_id']
        self.integration_token = config['integration_token']
        self.filter_config = config.get('filter', {})

    def validate_config(self) -> bool:
        """验证 Notion 配置"""
        required_keys = ['database_id', 'integration_token']
        return all(key in self.config for key in required_keys)

    async def scrape(self) -> ScrapingResult:
        """执行 Notion 抓取"""
        try:
            headers = {
                'Authorization': f'Bearer {self.integration_token}',
                'Content-Type': 'application/json',
                'Notion-Version': '2022-06-28'
            }

            query_body = {
                'filter': self.filter_config,
                'page_size': self.config.get('max_items', 50)
            }

            async with aiohttp.ClientSession() as session:
                url = f"https://api.notion.com/v1/databases/{self.database_id}/query"
                async with session.post(url, json=query_body, headers=headers) as response:
                    data = await response.json()

            items = []
            for page in data.get('results', []):
                item = self._parse_notion_page(page)
                if item:
                    items.append(item)

            return ScrapingResult(
                scraper_name=self.name,
                success=True,
                items=items
            )

        except Exception as e:
            return ScrapingResult(
                scraper_name=self.name,
                success=False,
                items=[],
                error_message=str(e)
            )

    def _parse_notion_page(self, page: Dict[str, Any]) -> Optional[ScrapingItem]:
        """解析 Notion 页面数据"""
        try:
            properties = page.get('properties', {})

            # 提取标题
            title_prop = properties.get('Title') or properties.get('Name')
            title = self._extract_notion_text(title_prop)

            # 提取 URL
            url_prop = properties.get('URL') or properties.get('Link')
            url = self._extract_notion_url(url_prop)

            # 提取其他属性
            content = self._extract_notion_text(properties.get('Content'))
            author = self._extract_notion_text(properties.get('Author'))

            return ScrapingItem(
                title=title,
                url=url,
                content=content,
                author=author,
                metadata={'notion_page_id': page.get('id')}
            )

        except Exception:
            return None

    def _extract_notion_text(self, prop: Dict[str, Any]) -> str:
        """从 Notion 属性中提取文本"""
        # 实现 Notion 文本提取逻辑
        pass

    def _extract_notion_url(self, prop: Dict[str, Any]) -> str:
        """从 Notion 属性中提取 URL"""
        # 实现 Notion URL 提取逻辑
        pass
```

## 内容去重处理

### ContentDeduplicator

```python
import hashlib
from typing import List, Set, Dict, Any
from ..service_models import ScrapingItem, ScrapingResult

class ContentDeduplicator:
    """内容去重处理器"""

    def __init__(self, storage_backend: str = 'memory'):
        self.storage_backend = storage_backend
        self._memory_cache: Set[str] = set()

    def deduplicate_items(self, items: List[ScrapingItem]) -> List[ScrapingItem]:
        """对抓取项目进行去重"""
        unique_items = []

        for item in items:
            item_hash = self._calculate_hash(item)

            if not self._is_duplicate(item_hash):
                unique_items.append(item)
                self._store_hash(item_hash)

        return unique_items

    def process_result(self, result: ScrapingResult) -> ScrapingResult:
        """处理抓取结果，添加去重信息"""
        original_count = len(result.items)
        unique_items = self.deduplicate_items(result.items)

        result.items = unique_items
        result.new_items = len(unique_items)
        result.duplicate_items = original_count - len(unique_items)

        return result

    def _calculate_hash(self, item: ScrapingItem) -> str:
        """计算项目哈希值"""
        # 使用标题和URL计算哈希
        content = f"{item.title}|{item.url}"
        return hashlib.md5(content.encode()).hexdigest()

    def _is_duplicate(self, item_hash: str) -> bool:
        """检查是否重复"""
        if self.storage_backend == 'memory':
            return item_hash in self._memory_cache
        # 可以扩展其他存储后端
        return False

    def _store_hash(self, item_hash: str):
        """存储哈希值"""
        if self.storage_backend == 'memory':
            self._memory_cache.add(item_hash)

    def clear_cache(self):
        """清空缓存"""
        if self.storage_backend == 'memory':
            self._memory_cache.clear()
```

## 抓取器管理

### ScraperManager

```python
from typing import Dict, List, Any, Optional
from .base_scraper import BaseScraper
from .scraper_protos import scraper_registry
from .content_deduplicator import ContentDeduplicator
from ..service_models import ScrapingResult

class ScraperManager:
    """抓取器管理器"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.scrapers: Dict[str, BaseScraper] = {}
        self.deduplicator = ContentDeduplicator()
        self._load_scrapers()

    def _load_scrapers(self):
        """加载配置中的抓取器"""
        scrapers_config = self.config.get('scrapers', {})

        for name, scraper_config in scrapers_config.items():
            if not scraper_config.get('enabled', True):
                continue

            scraper_type = scraper_config.get('type')
            if not scraper_type:
                continue

            try:
                scraper = scraper_registry.create_scraper(
                    scraper_type, name, scraper_config
                )

                if scraper.validate_config():
                    self.scrapers[name] = scraper
                else:
                    print(f"Invalid config for scraper {name}")

            except Exception as e:
                print(f"Failed to create scraper {name}: {e}")

    async def run_scraper(self, name: str) -> ScrapingResult:
        """运行指定的抓取器"""
        if name not in self.scrapers:
            return ScrapingResult(
                scraper_name=name,
                success=False,
                items=[],
                error_message=f"Scraper {name} not found"
            )

        scraper = self.scrapers[name]
        result = await scraper.scrape()

        # 去重处理
        if result.success:
            result = self.deduplicator.process_result(result)

        return result

    async def run_all_scrapers(self) -> List[ScrapingResult]:
        """运行所有启用的抓取器"""
        results = []

        for name in self.scrapers:
            result = await self.run_scraper(name)
            results.append(result)

        return results

    def get_scraper_info(self, name: str) -> Optional[Dict[str, Any]]:
        """获取抓取器信息"""
        if name in self.scrapers:
            return self.scrapers[name].get_scraper_info()
        return None

    def list_scrapers(self) -> List[Dict[str, Any]]:
        """列出所有抓取器"""
        return [
            {
                'name': name,
                'info': scraper.get_scraper_info()
            }
            for name, scraper in self.scrapers.items()
        ]

    def reload_scraper(self, name: str) -> bool:
        """重新加载抓取器"""
        scraper_config = self.config.get('scrapers', {}).get(name)
        if not scraper_config:
            return False

        try:
            scraper_type = scraper_config.get('type')
            scraper = scraper_registry.create_scraper(
                scraper_type, name, scraper_config
            )

            if scraper.validate_config():
                self.scrapers[name] = scraper
                return True

        except Exception:
            pass

        return False
```

## 工具函数

### tools.py

```python
import aiohttp
import asyncio
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin, urlparse

async def fetch_url(url: str, headers: Optional[Dict[str, str]] = None,
                   timeout: int = 30) -> str:
    """异步获取 URL 内容"""
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=timeout) as response:
            return await response.text()

async def validate_rss_url(url: str) -> bool:
    """验证 RSS URL 是否有效"""
    try:
        content = await fetch_url(url)
        # 简单检查是否包含 RSS 标记
        return '<rss' in content.lower() or '<feed' in content.lower()
    except Exception:
        return False

def extract_domain(url: str) -> str:
    """从 URL 提取域名"""
    parsed = urlparse(url)
    return parsed.netloc

def normalize_url(base_url: str, relative_url: str) -> str:
    """规范化 URL"""
    return urljoin(base_url, relative_url)

async def batch_process(items: List[Any], processor, batch_size: int = 10) -> List[Any]:
    """批量处理项目"""
    results = []

    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        batch_results = await asyncio.gather(
            *[processor(item) for item in batch],
            return_exceptions=True
        )
        results.extend(batch_results)

    return results
```

## 配置示例

### 抓取器概念配置

> **注意**: 以下是抓取器概念层面的配置示例，用于说明不同抓取器类型的参数。实际的配置文件使用 `scrapers_config_with_fetch_params` 格式，请参考 [配置管理文档](../config/config-manager.md) 了解完整的配置格式。

```yaml
# 概念示例 - 说明不同抓取器类型的配置参数
scrapers:
  vscode_blog:
    type: "direct_rss"
    enabled: true
    rss_url: "https://code.visualstudio.com/feed.xml"
    max_items: 20

  sspai_rsshub:
    type: "rsshub"
    enabled: true
    rsshub_base: "https://rsshub.app"
    route: "/sspai/series"
    max_items: 30

  hackernews:
    type: "rsshub"
    enabled: true
    route: "/hackernews/best"
    max_items: 25

  notion_bookmarks:
    type: "notion_api"
    enabled: false
    database_id: "your-database-id"
    integration_token: "${NOTION_TOKEN}"
    max_items: 50
    filter:
      property: "Status"
      select:
        equals: "Published"
```

## 扩展新抓取器

### 创建自定义抓取器

```python
from typing import Dict, Any
from .base_scraper import BaseScraper
from .scraper_protos import scraper_registry
from ..service_models import ScrapingResult, ScrapingItem

class CustomScraper(BaseScraper):
    """自定义抓取器示例"""

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        # 初始化自定义配置
        self.api_key = config.get('api_key')
        self.endpoint = config.get('endpoint')

    def validate_config(self) -> bool:
        """验证配置"""
        return bool(self.api_key and self.endpoint)

    async def scrape(self) -> ScrapingResult:
        """实现抓取逻辑"""
        try:
            # 实现具体的抓取逻辑
            items = await self._fetch_items()

            return ScrapingResult(
                scraper_name=self.name,
                success=True,
                items=items
            )
        except Exception as e:
            return ScrapingResult(
                scraper_name=self.name,
                success=False,
                items=[],
                error_message=str(e)
            )

    async def _fetch_items(self) -> List[ScrapingItem]:
        """获取项目数据"""
        # 实现数据获取逻辑
        pass

# 注册自定义抓取器
scraper_registry.register('custom', CustomScraper)
```

## 抓取器注册

### 自动注册机制

```python
# __init__.py
from .direct_rss import DirectRssScraper
from .rsshub import RsshubScraper
from .notion_api import NotionApiScraper
from .scraper_protos import scraper_registry

# 注册内置抓取器
def register_builtin_scrapers():
    """注册内置抓取器"""
    scraper_registry.register('direct_rss', DirectRssScraper)
    scraper_registry.register('rsshub', RsshubScraper)
    scraper_registry.register('notion_api', NotionApiScraper)

# 模块初始化时自动注册
register_builtin_scrapers()

# 导出公共接口
__all__ = [
    'BaseScraper',
    'ScraperManager',
    'ScrapingResult',
    'ScrapingItem',
    'ContentDeduplicator',
    'scraper_registry'
]
```

## 使用示例

### 基本使用

```python
from octopus_scraper.scrapers import ScraperManager
from octopus_scraper.config import ConfigManager

# 初始化配置和管理器
config_manager = ConfigManager()
config = config_manager.get_config()

scraper_manager = ScraperManager(config)

# 运行单个抓取器
result = await scraper_manager.run_scraper('vscode_blog')
print(f"抓取结果: {result.total_items} 个项目")

# 运行所有抓取器
all_results = await scraper_manager.run_all_scrapers()
for result in all_results:
    print(f"{result.scraper_name}: {result.total_items} items")

# 获取抓取器信息
scrapers = scraper_manager.list_scrapers()
for scraper in scrapers:
    print(f"Scraper: {scraper['name']}, Type: {scraper['info']['type']}")
```

### 与任务管理器集成

```python
from octopus_scraper.task_manager import TaskManager, Task
from octopus_scraper.scrapers import ScraperManager

class ScraperTask(Task):
    """抓取器任务"""

    def __init__(self, scraper_name: str, scraper_manager: ScraperManager):
        super().__init__(task_type="scraper")
        self.scraper_name = scraper_name
        self.scraper_manager = scraper_manager

    async def execute(self) -> TaskResult:
        """执行抓取任务"""
        result = await self.scraper_manager.run_scraper(self.scraper_name)

        return TaskResult(
            task_id=self.task_id,
            status=TaskStatus.COMPLETED if result.success else TaskStatus.FAILED,
            result_data=result,
            error_message=result.error_message
        )

# 提交抓取任务
task_manager = TaskManager()
scraper_manager = ScraperManager(config)

task = ScraperTask('vscode_blog', scraper_manager)
task_id = await task_manager.submit_task(task)
```

## 相关文档

- [ConfigManager Models](../config/config-manager.md)
- [TaskManager Models](../task_manager/task-manager.md)
- [Service Models](../service/service-models.md)
- [Scrapers Testing](./scrapers-testing.md)
