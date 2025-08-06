# Processors 模型文档

## 概述

Processors 模块负责对抓取到的内容进行后处理，包括内容清理、格式化、摘要生成等功能。该模块采用可插拔的架构设计，支持多种不同类型的内容处理器。

## 模块结构

```
src/octopus_scraper/processors/
├── __init__.py                    # 模块初始化和处理器注册
├── html_content_processor.py      # HTML 内容处理器
├── llm_processor.py              # AI 大语言模型处理器
└── protos.py                     # 处理器数据模型
```

## 核心架构

### 处理器注册系统

位置: `src/octopus_scraper/processors/__init__.py`

```python
AVALIABLE_PROCESSOR = {
    "llm": LLMProcessor, 
    "html_content": HTMLContentProcessor
}
```

#### 主要功能

- **处理器注册**: 自动注册可用的内容处理器
- **动态加载**: 根据配置动态加载对应的处理器
- **扩展支持**: 支持添加自定义处理器

### HTMLContentProcessor

位置: `src/octopus_scraper/processors/html_content_processor.py`

#### 主要功能

- **HTML 清理**: 去除无用的 HTML 标签和属性
- **内容提取**: 提取主要文本内容
- **格式标准化**: 统一内容格式

#### 核心方法

```python
class HTMLContentProcessor:
    def __init__(self, config: Dict[str, Any])
    
    def process(self, content: Content) -> Content
    def clean_html(self, html_content: str) -> str
    def extract_text(self, html_content: str) -> str
    def normalize_whitespace(self, text: str) -> str
```

#### 配置选项

```python
html_processor_config = {
    "remove_tags": ["script", "style", "nav", "footer"],
    "preserve_links": True,
    "extract_images": False,
    "max_content_length": 10000
}
```

### LLMProcessor

位置: `src/octopus_scraper/processors/llm_processor.py`

#### 主要功能

- **AI 摘要**: 使用大语言模型生成内容摘要
- **标签生成**: 自动生成内容标签
- **内容增强**: 提供额外的元数据信息

#### 核心方法

```python
class LLMProcessor:
    def __init__(self, config: Dict[str, Any])
    
    def process(self, content: Content) -> Content
    def generate_summary(self, content: str) -> str
    def generate_tags(self, content: str) -> List[str]
    def enhance_metadata(self, content: Content) -> Dict[str, Any]
```

#### 配置选项

```python
llm_processor_config = {
    "model_name": "gpt-3.5-turbo",
    "api_key": "your_openai_api_key",
    "max_tokens": 150,
    "temperature": 0.7,
    "generate_summary": True,
    "generate_tags": True,
    "max_content_length": 5000
}
```

## 数据模型

### 处理器配置模型

```python
@dataclass
class ProcessorConfig:
    processor_type: str
    config: Dict[str, Any]
    enabled: bool = True
    priority: int = 0
```

### 内容处理结果

```python
@dataclass
class ProcessingResult:
    processed_content: Content
    metadata: Dict[str, Any]
    processing_time: float
    processor_name: str
    success: bool
    error_message: Optional[str] = None
```

## 使用示例

### 基本使用

```python
from octopus_scraper.processors import AVALIABLE_PROCESSOR

# 创建 HTML 内容处理器
html_config = {
    "remove_tags": ["script", "style"],
    "preserve_links": True
}
html_processor = AVALIABLE_PROCESSOR["html_content"](html_config)

# 处理内容
processed_content = html_processor.process(content)
```

### 在 Scraper 配置中使用

```yaml
scrapers_config_with_fetch_params:
  - scraper_config:
      fetcher_name: "rsshub"
      fetcher_config:
        hub_root: "https://rsshub.app"
        route: "/github/issues/microsoft/vscode"
      content_processor_configs:
        html_content:
          remove_tags: ["script", "style", "nav"]
          preserve_links: true
          max_content_length: 8000
        llm:
          generate_summary: true
          generate_tags: true
          max_tokens: 100
    fetch_params:
      limit: 20
```

### 程序化使用

```python
from octopus_scraper.processors import HTMLContentProcessor, LLMProcessor

# 配置处理器链
processors = [
    HTMLContentProcessor({
        "remove_tags": ["script", "style"],
        "preserve_links": True
    }),
    LLMProcessor({
        "generate_summary": True,
        "generate_tags": True,
        "model_name": "gpt-3.5-turbo"
    })
]

# 处理内容
for processor in processors:
    content = processor.process(content)
```

## 处理器链

### 处理器执行顺序

处理器按照以下顺序执行：

1. **HTMLContentProcessor** - 清理和标准化 HTML 内容
2. **LLMProcessor** - AI 增强和摘要生成

### 错误处理

```python
try:
    processed_content = processor.process(content)
except ProcessorError as e:
    logger.error(f"处理器执行失败: {e}")
    # 继续使用原始内容
    processed_content = content
```

## 扩展性

### 添加自定义处理器

```python
class CustomProcessor:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
    
    def process(self, content: Content) -> Content:
        # 自定义处理逻辑
        processed_content = self.custom_processing(content)
        return processed_content
    
    def custom_processing(self, content: Content) -> Content:
        # 实现具体的处理逻辑
        pass

# 注册自定义处理器
AVALIABLE_PROCESSOR["custom"] = CustomProcessor
```

### 处理器接口

```python
from abc import ABC, abstractmethod

class BaseProcessor(ABC):
    @abstractmethod
    def __init__(self, config: Dict[str, Any]):
        pass
    
    @abstractmethod
    def process(self, content: Content) -> Content:
        pass
```

## 性能特性

### HTMLContentProcessor

- **解析器**: 使用 BeautifulSoup 进行 HTML 解析
- **缓存**: 内置解析结果缓存机制
- **批量处理**: 支持批量内容处理
- **内存优化**: 自动清理大型 HTML 文档

### LLMProcessor

- **API 限制**: 智能处理 API 速率限制
- **错误重试**: 自动重试失败的 API 调用
- **内容切分**: 自动处理超长内容
- **缓存策略**: 缓存常见内容的处理结果

## 监控和日志

### 日志记录

```python
import structlog

logger = structlog.get_logger(__name__)

# 处理开始
logger.info("Starting content processing", 
           processor=processor_name,
           content_id=content.content_id)

# 处理完成
logger.info("Content processing completed",
           processor=processor_name,
           processing_time=processing_time,
           content_length=len(processed_content.content))
```

### 性能监控

```python
# 处理时间统计
@monitor_processing_time
def process(self, content: Content) -> Content:
    # 处理逻辑
    pass

# 错误率监控
@track_processing_errors
def process(self, content: Content) -> Content:
    # 处理逻辑
    pass
```

## 最佳实践

### 1. 配置管理

- 使用环境变量存储敏感信息（如 API 密钥）
- 为不同环境配置不同的处理器参数
- 定期验证处理器配置的有效性

### 2. 错误处理

- 实现优雅的降级机制
- 记录详细的错误信息用于调试
- 对 LLM API 调用实现重试机制

### 3. 性能优化

- 合理设置内容长度限制
- 使用批量处理提高效率
- 监控处理器性能指标

### 4. 扩展开发

- 遵循统一的处理器接口
- 提供详细的配置文档
- 实现完整的单元测试

## 相关文档

- [Scrapers 模型文档](../scrapers/scrapers.md) - 了解抓取器如何使用处理器
- [ConfigManager 文档](../config/config-manager.md) - 了解处理器配置管理
- [TaskManager 文档](../task_manager/task-manager.md) - 了解处理器在任务中的执行
- [Processors 测试文档](./processors-testing.md) - 了解处理器的测试方法
