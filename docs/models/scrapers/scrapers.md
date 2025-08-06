# Scrapers 模型文档

## 概述

Scrapers 是 OctopusScraper 的核心模块，负责从各种数据源抓取内容。系统采用模块化架构，由数据获取器(Fetcher)、内容处理器(Processor)和核心抓取器(Scraper)组成，提供统一的接口和配置管理。

## 模块结构

```
src/octopus_scraper/scrapers/
├── __init__.py                 # 模块初始化
├── scraper.py                 # 核心抓取器类
├── scraper_protos.py          # 抓取器协议和数据模型
├── processors/                # 内容处理器模块
│   ├── __init__.py            # 处理器注册
│   ├── protos.py              # 处理器基础协议
│   ├── html_content_processor.py # HTML内容处理器
│   └── llm_processor.py       # LLM内容处理器
└── utils/                     # 抓取工具和辅助函数
    ├── direct_rss.py          # RSS 直接抓取器
    ├── rsshub.py              # RSSHub 抓取器
    └── tools.py               # 抓取工具和辅助函数
```

## 核心数据模型

### Content (内容模型)

**模块路径**: `src/octopus_scraper/scrapers/scraper_protos.py`

```python
@dataclass
class Content:
    content_id: str     # 内容唯一标识符
    title: str          # 内容标题
    link: str           # 内容链接
    summary: str        # 内容摘要
    content: str        # 内容正文
    published: str      # 发布时间
```

这是系统中所有内容的统一数据模型，用于在不同组件之间传递内容信息。

## 核心组件架构

### 1. Scraper (核心抓取器)

**模块路径**: `src/octopus_scraper/scrapers/scraper.py`

核心抓取器是系统的主要协调者，负责整合数据获取器和内容处理器：

```python
@dataclass
class BaseScraperConfig:
    fetcher_name: str                           # 数据获取器名称
    fetcher_config: Any                         # 数据获取器配置
    content_processor_configs: Dict[Text, Any]  # 内容处理器配置字典

class Scraper:
    def __init__(self, config: Dict):
        """初始化抓取器"""
        self.config = from_dict(BaseScraperConfig, config)
        self.storage = None  # 可选的存储器，用于去重
        
        # 初始化数据获取器
        self.activate_fetcher = AVALIABLE_FETCHERS[self.config.fetcher_name](
            self.config.fetcher_config
        )
        
        # 初始化内容处理器
        self.active_content_processor = {}
        self.processor_priorities = {}
        
    def scrap_contents(self, params) -> List[Content]:
        """抓取内容的主要入口方法"""
        
    def set_storage(self, storage):
        """设置存储器用于去重"""
        
    def _content_process(self, contents: List[Content]) -> List[Content]:
        """按优先级处理内容"""
```

**主要功能**:
- 配置和管理数据获取器
- 配置和管理多个内容处理器
- 按优先级顺序执行内容处理
- 与存储器集成实现去重功能

### 2. 数据获取器 (Fetchers)

数据获取器负责从不同的数据源获取原始内容。

#### DirectRSS (直接RSS获取器)

**模块路径**: `src/octopus_scraper/scrapers/utils/direct_rss.py`

```python
@dataclass
class DirectRSSConfig:
    # RSS配置参数

class DirectRSS:
    def __init__(self, config: Dict):
        """初始化RSS获取器"""
        
    def fetch_contents(self, params: dict = {}) -> List[Content]:
        """从RSS源获取内容"""
        
    @staticmethod
    def filter_by_timerange(contents: List[Content], filter_time: int) -> List[Content]:
        """按时间范围过滤内容"""
```

#### RssHub (RSSHub获取器)

**模块路径**: `src/octopus_scraper/scrapers/utils/rsshub.py`

```python
@dataclass
class RssHubConifg:
    # RSSHub配置参数

class RssHub:
    def __init__(self, config: Dict):
        """初始化RSSHub获取器"""
        
    def fetch_contents(self, params: dict = {}) -> List[Content]:
        """从RSSHub获取内容"""
```

**可用获取器注册表**:
```python
AVALIABLE_FETCHERS = {
    "rsshub": RssHub,
    "direct_rss": DirectRSS
}
```

### 3. 内容处理器 (Processors)

内容处理器负责对获取的原始内容进行处理和增强。

#### 处理器基础协议

**模块路径**: `src/octopus_scraper/scrapers/processors/protos.py`

```python
@dataclass
class ProcessorConfig:
    priority: int = 100  # 处理器优先级，数值越小优先级越高

@dataclass
class LLMProcessorConfig(ProcessorConfig):
    # LLM处理器特定配置
```

#### HTMLContentProcessor (HTML内容处理器)

**模块路径**: `src/octopus_scraper/scrapers/processors/html_content_processor.py`

```python
@dataclass
class HTMLContentProcessorConfig(ProcessorConfig):
    # HTML处理器配置

class HTMLContentProcessor:
    def __init__(self, config: Dict):
        """初始化HTML内容处理器"""
        
    def __call__(self, contents: List[Content]) -> List[Content]:
        """处理内容列表"""
        
    def _fetch_html_with_browser(self, url: str) -> str:
        """使用浏览器获取HTML内容"""
        
    def _fetch_html_content(self, url: str) -> str:
        """获取HTML内容"""
        
    def _extract_readable_content(self, html: str, url: str) -> str:
        """提取可读内容"""
        
    def _html_to_markdown(self, html: str) -> str:
        """将HTML转换为Markdown"""
```

#### LLMProcessor (LLM内容处理器)

**模块路径**: `src/octopus_scraper/scrapers/processors/llm_processor.py`

```python
class LLMProcessor:
    def __init__(self, configs: Dict):
        """初始化LLM处理器"""
        
    def __call__(self, contents: List[Content]) -> List[Content]:
        """使用LLM处理内容"""
        
    def _create_single_content_input(self, content: Content) -> List[Dict]:
        """为单个内容创建LLM输入"""
        
    def _parse_json_output(self, llm_raw_output: str) -> str:
        """解析LLM的JSON输出"""

def extract_markdown_json_code(markdown_text: str):
    """从Markdown中提取JSON代码块"""
```

**可用处理器注册表**:
```python
AVALIABLE_PROCESSOR = {
    "llm": LLMProcessor,
    "html_content": HTMLContentProcessor
}
```

## 工具函数

### tools.py

**模块路径**: `src/octopus_scraper/scrapers/utils/tools.py`

```python
def convert_contents_to_mk(contents: List) -> str:
    """将内容列表转换为Markdown格式"""

def build_contents(feed: FeedParserDict) -> List[Content]:
    """从RSS feed构建内容列表"""

def generate_stable_content_id(entry) -> str:
    """生成稳定的内容ID"""

def generate_summary_from_entry(entry) -> str:
    """从RSS条目生成摘要"""

def generate_content_with_fallback(entry) -> str:
    """生成内容，带有回退机制"""
```

## 配置格式

### 抓取器配置结构

```yaml
# 实际配置格式示例
scrapers_config_with_fetch_params:
  sspai_scraper:
    fetcher_name: "rsshub"
    fetcher_config:
      rsshub_base: "https://rsshub.app"
      route: "/sspai/series"
    content_processor_configs:
      html_content:
        priority: 1
        # HTML处理器特定配置
      llm:
        priority: 2
        # LLM处理器特定配置

  tech_blog:
    fetcher_name: "direct_rss"
    fetcher_config:
      rss_url: "https://example.com/feed.xml"
    content_processor_configs:
      html_content:
        priority: 1
```

### 获取器配置说明

#### DirectRSS 配置
```yaml
fetcher_name: "direct_rss"
fetcher_config:
  rss_url: "https://example.com/feed.xml"  # RSS源URL
  # 其他DirectRSS特定配置
```

#### RssHub 配置
```yaml
fetcher_name: "rsshub"
fetcher_config:
  rsshub_base: "https://rsshub.app"  # RSSHub实例地址
  route: "/sspai/series"             # RSSHub路由
  # 其他RSSHub特定配置
```

### 处理器配置说明

#### HTML内容处理器配置
```yaml
content_processor_configs:
  html_content:
    priority: 1  # 优先级，数值越小越优先
    # HTML处理器特定配置
```

#### LLM处理器配置
```yaml
content_processor_configs:
  llm:
    priority: 2  # 优先级，通常在HTML处理器之后
    # LLM处理器特定配置
```

## 处理流程

### 内容抓取和处理流程

1. **初始化阶段**
   - 根据配置创建指定的数据获取器
   - 创建并配置所有内容处理器
   - 设置处理器优先级

2. **数据获取阶段**
   - 调用数据获取器的 `fetch_contents()` 方法
   - 获取原始的 `Content` 对象列表

3. **去重处理阶段**（如果设置了存储器）
   - 从存储器获取已存在的内容ID
   - 过滤掉重复的内容

4. **内容处理阶段**
   - 按优先级顺序执行内容处理器
   - 每个处理器接收 `List[Content]` 并返回处理后的 `List[Content]`

5. **返回结果**
   - 返回最终处理完成的内容列表

### 优先级处理机制

处理器按照优先级数值**从小到大**的顺序执行：
- priority=1 的处理器最先执行
- priority=2 的处理器在 priority=1 之后执行
- 未配置优先级的处理器默认优先级为100

## 使用示例

### 基本使用示例

```python
from octopus_scraper.scrapers.scraper import Scraper

# 配置抓取器
config = {
    "fetcher_name": "rsshub",
    "fetcher_config": {
        "rsshub_base": "https://rsshub.app",
        "route": "/sspai/series"
    },
    "content_processor_configs": {
        "html_content": {
            "priority": 1
        },
        "llm": {
            "priority": 2
        }
    }
}

# 创建抓取器实例
scraper = Scraper(config)

# 执行抓取
contents = scraper.scrap_contents({})

# 查看结果
for content in contents:
    print(f"标题: {content.title}")
    print(f"链接: {content.link}")
    print(f"摘要: {content.summary}")
    print("---")
```

### 与存储器集成使用

```python
from octopus_scraper.scrapers.scraper import Scraper
from octopus_scraper.storages.notion_storage import NotionStorage

# 创建存储器
storage_config = {
    "api_key": "your-notion-api-key",
    "database_id": "your-database-id"
}
storage = NotionStorage(storage_config)

# 创建抓取器并设置存储器
scraper = Scraper(config)
scraper.set_storage(storage)

# 执行抓取（会自动去重）
contents = scraper.scrap_contents({})

print(f"抓取到 {len(contents)} 个新内容")
```

### 自定义获取器扩展

```python
from typing import Dict, List
from octopus_scraper.scrapers.scraper_protos import Content
from octopus_scraper.scrapers.scraper import AVALIABLE_FETCHERS

class CustomFetcher:
    def __init__(self, config: Dict):
        self.config = config
        # 初始化自定义获取器
        
    def fetch_contents(self, params: dict = {}) -> List[Content]:
        """实现自定义抓取逻辑"""
        contents = []
        
        # 实现具体的抓取逻辑
        # ...
        
        return contents

# 注册自定义获取器
AVALIABLE_FETCHERS["custom"] = CustomFetcher
```

### 自定义处理器扩展

```python
from typing import Dict, List
from octopus_scraper.protos import Content
from octopus_scraper.processors import AVALIABLE_PROCESSOR

class CustomProcessor:
    def __init__(self, config: Dict):
        self.config = config
        # 初始化自定义处理器
        
    def __call__(self, contents: List[Content]) -> List[Content]:
        """实现自定义处理逻辑"""
        processed_contents = []
        
        for content in contents:
            # 实现具体的处理逻辑
            processed_content = self._process_single_content(content)
            processed_contents.append(processed_content)
            
        return processed_contents
        
    def _process_single_content(self, content: Content) -> Content:
        """处理单个内容"""
        # 实现处理逻辑
        return content

# 注册自定义处理器
AVALIABLE_PROCESSOR["custom"] = CustomProcessor
```

## 相关文档

- [配置管理文档](../config/config-manager.md) - 了解完整的配置格式和管理
- [存储器文档](../storages/storages.md) - 了解存储器集成和去重机制
- [任务管理器文档](../task_manager/task-manager.md) - 了解如何在任务中使用抓取器
- [测试文档](./scrapers-testing.md) - 了解抓取器的测试方法
