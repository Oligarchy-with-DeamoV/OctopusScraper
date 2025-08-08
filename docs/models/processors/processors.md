# Processors 模型文档

## 概述

Processors 模块负责对抓取到的内容进行后处理，包括内容清理、格式化、摘要生成等功能。该模块采用**企业级插件化架构设计**，支持动态注册、配置管理、管道处理等高级功能。

> 📢 **架构升级**: Phase 4 完成了处理器系统的重大升级，引入了ProcessorRegistry、ProcessorFactory、ProcessorPipeline等企业级组件，实现了完全模块化的处理器架构。

## 模块结构

```
src/octopus_scraper/processors/
├── __init__.py                     # 处理器注册系统核心 (ProcessorRegistry, ProcessorFactory)
├── processor_base.py               # 抽象基类定义
├── processor_config.py             # 配置管理系统 (ProcessorConfig, ProcessorConfigManager)
├── processor_pipeline.py           # 处理器管道系统 (PipelineBuilder, 依赖解析)
├── html_content_processor.py       # HTML 内容处理器 (适配新架构)
├── llm_processor.py               # AI 大语言模型处理器 (适配新架构)
├── llm_summary_processor.py        # LLM 摘要处理器
├── llm_tags_processor.py           # LLM 标签处理器  
├── llm_keywords_processor.py       # LLM 关键词处理器
└── protos.py                      # 处理器数据模型
```

## 🏗️ 核心架构

### 处理器注册系统 (ProcessorRegistry)

位置: `src/octopus_scraper/processors/__init__.py`

ProcessorRegistry 是处理器系统的核心，提供动态注册、发现和管理功能。

```python
# 全局注册系统实例
_registry = ProcessorRegistry()

class ProcessorRegistry:
    """处理器注册和管理系统"""
    
    def register(self, name: str, processor_class: Type[ProcessorBase]) -> None
    def unregister(self, name: str) -> None
    def get_processor_class(self, name: str) -> Type[ProcessorBase]
    def list_processors(self) -> List[str]
    def create_processor(self, name: str, config: Dict[str, Any]) -> ProcessorBase
    def get_processor_info(self, name: str) -> Dict[str, Any]
```

#### 主要功能

- **动态注册**: 运行时注册和注销处理器
- **类型验证**: 确保注册的类符合ProcessorBase接口
- **元数据管理**: 存储处理器描述、版本等信息
- **内置处理器**: 自动注册html_content、llm、llm_summary、llm_tags、llm_keywords处理器

#### 使用示例

```python
from octopus_scraper.processors import register_processor, create_processor

# 动态注册自定义处理器
register_processor('custom_processor', CustomProcessor)

# 创建处理器实例
processor = create_processor('html_content', {'timeout': 30})

# 获取可用处理器列表
available = get_available_processors()
# 返回: ['html_content', 'llm', 'llm_summary', 'llm_tags', 'llm_keywords']
```

### 处理器工厂 (ProcessorFactory)

ProcessorFactory 提供统一的处理器创建接口，支持配置验证和处理器链创建。

```python
class ProcessorFactory:
    """处理器工厂，统一创建接口"""
    
    def __init__(self, registry: Optional[ProcessorRegistry] = None)
    def create_processor(self, processor_type: str, config: Dict[str, Any]) -> ProcessorBase
    def create_processor_chain(self, processor_configs: List[Dict[str, Any]]) -> List[ProcessorBase]
    def get_available_processors(self) -> List[str]
```

#### 主要功能

- **统一创建**: 提供一致的处理器创建接口
- **处理器链**: 支持批量创建处理器链
- **错误处理**: 优雅处理创建失败情况
- **全局工厂**: 提供全局工厂实例

### 配置管理系统 (ProcessorConfigManager)

位置: `src/octopus_scraper/processors/processor_config.py`

提供结构化的配置管理，支持验证、配置档案等功能。

```python
@dataclass
class ProcessorConfig:
    """处理器配置基类"""
    processor_type: str
    config: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    priority: int = 100
    dependencies: List[str] = field(default_factory=list)

class ProcessorConfigManager:
    """处理器配置管理器"""
    
    def add_config(self, name: str, config: ProcessorConfig) -> None
    def get_config(self, name: str) -> ProcessorConfig
    def remove_config(self, name: str) -> bool
    def create_profile(self, profile_name: str, config_ids: List[str]) -> None
    def get_profile(self, profile_name: str) -> List[ProcessorConfig]
    def validate_configuration(self, configs: List[ProcessorConfig]) -> bool
```

#### 配置类型

系统定义了多种专门的配置类：

```python
# HTML处理器配置
@dataclass
class HTMLContentProcessorConfig(ProcessorConfig):
    timeout: int = 30
    user_agent: str = "..."
    browserless_url: str = ""
    use_browser: bool = True
    browser_timeout: int = 60000

# LLM基础配置
@dataclass
class BaseLLMProcessorConfig(ProcessorConfig):
    model_name: str = "gpt-3.5-turbo"
    max_tokens: int = 1000
    temperature: float = 0.7
    timeout: int = 30
    retry_times: int = 3
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    llm_provider: str = "openai"

# 摘要处理器配置
@dataclass
class SummaryProcessorConfig(BaseLLMProcessorConfig):
    max_summary_length: int = 200
    summary_style: str = "concise"
    preserve_structure: bool = False
    include_key_points: bool = True

# 标签处理器配置
@dataclass
class TagsProcessorConfig(BaseLLMProcessorConfig):
    available_tags: List[str] = field(default_factory=list)
    max_tags_count: int = 5
    custom_categories: Dict[str, List[str]] = field(default_factory=dict)
    allow_new_tags: bool = True
    confidence_threshold: float = 0.5

# 关键词处理器配置
@dataclass
class KeywordsProcessorConfig(BaseLLMProcessorConfig):
    keywords_count: int = 3
    max_keywords: int = 10
    min_keyword_length: int = 2
    max_keyword_length: int = 20
    exclude_common_words: bool = True
    include_phrases: bool = True
    language_preference: str = "mixed"
```

### 处理器管道系统 (ProcessorPipeline)

位置: `src/octopus_scraper/processors/processor_pipeline.py`

支持复杂的处理器依赖关系和执行流程管理。

```python
@dataclass
class PipelineResult:
    """管道执行结果"""
    success: bool
    results: Dict[str, Any]
    errors: List[Exception]
    execution_time: float
    processor_results: Dict[str, Any]

class ProcessorPipeline:
    """处理器管道执行器"""
    
    def __init__(self, name: str = "default", factory: Optional[ProcessorFactory] = None)
    def add_processor(self, name: str, config: ProcessorConfig, dependencies: Optional[List[str]] = None) -> None
    def execute(self, content: Any) -> PipelineResult
    def execute_parallel(self, content: Any) -> PipelineResult
    def execute_sequential(self, content: Any) -> PipelineResult
```

#### 使用示例

```python
from octopus_scraper.processors.processor_pipeline import ProcessorPipeline
from octopus_scraper.processors.processor_config import ProcessorConfig

# 创建管道
pipeline = ProcessorPipeline("content_processing")

# 添加处理器
html_config = ProcessorConfig(processor_type="html_content", config={"timeout": 30})
pipeline.add_processor("html", html_config)

summary_config = ProcessorConfig(processor_type="llm_summary", config={"model_name": "gpt-3.5-turbo"})
pipeline.add_processor("summary", summary_config, dependencies=["html"])

# 执行管道
result = pipeline.execute(content)
```

## 📦 内置处理器

### HTMLContentProcessor

位置: `src/octopus_scraper/processors/html_content_processor.py`

**功能特性**: 从Content中的link获取网页内容，支持动态网站抓取。

#### 主要功能

- **HTML 清理**: 使用readability提取主要内容
- **内容提取**: 提取主要文本内容并转换为Markdown格式
- **浏览器支持**: 支持Playwright和browserless服务进行动态网站抓取
- **回退机制**: 浏览器失败时自动回退到requests方式

#### 配置示例

```python
from octopus_scraper.processors import create_processor

config = {
    "timeout": 30,
    "user_agent": "Custom User Agent",
    "use_browser": True,
    "browser_timeout": 60000,
    "browserless_url": "http://localhost:3000"  # 可选，为空则使用Playwright
}
processor = create_processor('html_content', config)
```
### LLMProcessor 系列

基于大语言模型的专门化处理器，每个处理器专注于特定的AI增强功能。

#### LLMSummaryProcessor
```python
# 专门的摘要生成处理器
config = {
    "model_name": "gpt-3.5-turbo", 
    "max_tokens": 300,
    "temperature": 0.3,
    "max_summary_length": 200,
    "summary_style": "concise"  # concise, detailed, bullet_points, executive
}
summary_processor = create_processor('llm_summary', config)
```

#### LLMTagsProcessor  
```python
# 智能标签生成处理器
config = {
    "model_name": "gpt-3.5-turbo",
    "max_tags_count": 5,
    "available_tags": ["tech", "news", "tutorial"],
    "allow_new_tags": True,
    "confidence_threshold": 0.5
}
tags_processor = create_processor('llm_tags', config)
```

#### LLMKeywordsProcessor
```python
# 关键词提取处理器  
config = {
    "model_name": "gpt-3.5-turbo",
    "keywords_count": 3,
    "min_keyword_length": 2,
    "max_keywords": 10,
    "exclude_common_words": True,
    "language_preference": "mixed"  # en, zh, mixed
}
keywords_processor = create_processor('llm_keywords', config)
```

#### LLMProcessor (Legacy)
```python
# 传统LLM处理器，仍然可用但推荐使用专门化处理器
config = {
    "prompt": "Summarize this article:",
    "if_structure_output": False,
    "json_schema": None
}
llm_processor = create_processor('llm', config)
```

## 📊 数据模型

### 处理器配置模型

详见 `src/octopus_scraper/processors/protos.py`

```python
@dataclass
class ProcessorConfig:
    """处理器配置基类"""
    priority: int = field(default=100)  # 优先级，数值越小优先级越高

@dataclass
class HTMLContentProcessorConfig(ProcessorConfig):
    """HTML内容处理器配置"""
    timeout: int = field(default=30)
    user_agent: str = field(default="...")
    browserless_url: str = field(default="")
    use_browser: bool = field(default=True)
    browser_timeout: int = field(default=60000)

@dataclass
class BaseLLMProcessorConfig(ProcessorConfig):
    """LLM处理器基础配置"""
    model_name: str = field(default="gpt-3.5-turbo")
    max_tokens: int = field(default=1000)
    temperature: float = field(default=0.7)
    timeout: int = field(default=30)
    retry_times: int = field(default=3)
    api_key: Optional[str] = field(default=None)
    llm_provider: str = field(default="openai")
```

### 处理结果模型

```python
@dataclass
class ProcessingResult:
    """处理结果数据模型"""
    success: bool
    content: Optional[Content] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
```

## 💡 使用示例

### 基本使用

```python
from octopus_scraper.processors import (
    register_processor, create_processor, get_available_processors
)

# 获取可用处理器
available = get_available_processors()
print(available)  
# ['html_content', 'llm', 'llm_summary', 'llm_tags', 'llm_keywords']

# 创建处理器实例
html_processor = create_processor('html_content', {
    'timeout': 30,
    'use_browser': True
})

# 处理内容
contents = [Content(...)]  # 内容列表
result = html_processor(contents)
```

### 处理器管道使用

```python
from octopus_scraper.processors.processor_pipeline import ProcessorPipeline
from octopus_scraper.processors.processor_config import ProcessorConfig

# 构建处理器管道
pipeline = ProcessorPipeline("content_processing")

# 添加HTML处理器
html_config = ProcessorConfig(
    processor_type="html_content",
    config={"timeout": 30, "use_browser": True}
)
pipeline.add_processor("html", html_config)

# 添加摘要处理器（依赖HTML处理器）
summary_config = ProcessorConfig(
    processor_type="llm_summary",
    config={"model_name": "gpt-3.5-turbo", "max_summary_length": 200}
)
pipeline.add_processor("summary", summary_config, dependencies=["html"])

# 执行管道
result = pipeline.execute(content)
print(f"处理成功: {result.success}")
print(f"执行时间: {result.execution_time:.2f}s")
```

### 配置管理使用

```python
from octopus_scraper.processors.processor_config import ProcessorConfigManager, ProcessorConfig

# 创建配置管理器
config_manager = ProcessorConfigManager()

# 添加配置
html_config = ProcessorConfig(
    processor_type="html_content",
    config={"timeout": 30, "use_browser": True}
)
config_manager.add_config("html_fast", html_config)

llm_config = ProcessorConfig(
    processor_type="llm_summary",
    config={"model_name": "gpt-4", "max_tokens": 500}
)
config_manager.add_config("llm_premium", llm_config)

# 创建配置档案
config_manager.create_profile("premium_processing", ["html_fast", "llm_premium"])

# 获取配置档案
profile_configs = config_manager.get_profile("premium_processing")
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
          timeout: 30
          use_browser: true
          browser_timeout: 60000
        llm_summary:
          model_name: "gpt-3.5-turbo"
          max_tokens: 300
          temperature: 0.3
          max_summary_length: 200
        llm_tags:
          model_name: "gpt-3.5-turbo"
          max_tags_count: 5
          available_tags: ["tech", "github", "vscode"]
        llm_keywords:
          model_name: "gpt-3.5-turbo"
          keywords_count: 3
          max_keywords: 10
    fetch_params:
      limit: 20
```

## 🔧 处理器开发

### 创建自定义处理器

```python
from octopus_scraper.processors.processor_base import ProcessorBase, ProcessingError
from octopus_scraper.processors.protos import ProcessorConfig
from octopus_scraper.protos import Content
from typing import Dict, List, Any
from dataclasses import dataclass, field

@dataclass
class CustomProcessorConfig(ProcessorConfig):
    """自定义处理器配置"""
    custom_param: str = ""
    threshold: float = 0.5

class CustomProcessor(ProcessorBase):
    """自定义内容处理器"""
    
    def _parse_config(self, config: Dict[str, Any]) -> CustomProcessorConfig:
        """解析配置"""
        return CustomProcessorConfig(**config)
    
    def _validate_config(self) -> None:
        """验证配置"""
        super()._validate_config()
        if self.config.threshold < 0 or self.config.threshold > 1:
            raise ValueError("threshold must be between 0 and 1")
    
    def __call__(self, contents: List[Content]) -> List[Content]:
        """处理内容的核心逻辑"""
        processed_contents = []
        
        for content in contents:
            try:
                # 实现自定义处理逻辑
                processed_text = self._custom_processing(content.content)
                
                # 创建新的Content对象
                processed_content = Content(
                    content_id=content.content_id,
                    title=content.title,
                    content=processed_text,
                    link=content.link,
                    pub_date=content.pub_date,
                    author=content.author,
                    tags=content.tags,
                    description=content.description
                )
                processed_contents.append(processed_content)
                
            except Exception as e:
                self.logger.error(
                    "Processing failed", 
                    error=str(e),
                    content_id=content.content_id
                )
                # 根据需要选择是否抛出异常或跳过
                raise ProcessingError(
                    f"Custom processing failed: {e}",
                    processor_name=self.name,
                    content_id=content.content_id
                )
        
        return processed_contents
    
    def _custom_processing(self, text: str) -> str:
        """自定义处理逻辑实现"""
        # 示例：转换为大写
        return text.upper()

# 注册自定义处理器
from octopus_scraper.processors import register_processor
register_processor("custom", CustomProcessor)

# 使用自定义处理器
custom_processor = create_processor("custom", {
    "custom_param": "example",
    "threshold": 0.8
})
```

### 处理器接口规范

所有处理器必须继承自`ProcessorBase`并实现以下接口：

```python
class ProcessorBase(ABC):
    """处理器抽象基类"""
    
    @abstractmethod
    def _parse_config(self, config: Dict[str, Any]) -> ProcessorConfig:
        """解析和验证配置"""
        pass
    
    def _validate_config(self) -> None:
        """验证配置 (可选重写)"""
        pass
    
    @abstractmethod  
    def __call__(self, contents: List[Content]) -> List[Content]:
        """处理内容的核心方法"""
        pass
    
    def process_single(self, content: Content) -> ProcessingResult:
        """单个内容处理 (已实现)"""
        pass
        
    def batch_process(self, contents: List[Content], batch_size: int = 10) -> List[ProcessingResult]:
        """批量处理 (已实现)"""
        pass
```

### 错误处理最佳实践

```python
from octopus_scraper.processors.processor_base import ProcessingError

class RobustProcessor(ProcessorBase):
    def __call__(self, contents: List[Content]) -> List[Content]:
        processed_contents = []
        
        for content in contents:
            try:
                # 处理逻辑
                result = self._risky_processing(content)
                processed_contents.append(result)
            except Exception as e:
                self.logger.error(
                    "Processing failed",
                    content_id=content.content_id,
                    error=str(e),
                    processor=self.__class__.__name__
                )
                
                # 根据配置决定是否回退
                if getattr(self.config, 'fallback_on_error', False):
                    self.logger.warning("Using fallback content")
                    processed_contents.append(content)  # 返回原始内容
                else:
                    raise ProcessingError(
                        f"Processing failed: {e}",
                        processor_name=self.name,
                        content_id=content.content_id,
                        original_error=e
                    )
        
        return processed_contents
```

## 🧪 测试支持

### 处理器测试

```python
import pytest
from octopus_scraper.processors import create_processor
from octopus_scraper.protos import Content

class TestCustomProcessor:
    def test_basic_processing(self):
        processor = create_processor("custom", {
            "custom_param": "test",
            "threshold": 0.5
        })
        
        content = Content(
            content_id="test_1",
            title="Test Title",
            content="Hello World",
            link="https://example.com"
        )
        
        result = processor([content])
        assert len(result) == 1
        assert result[0].content == "HELLO WORLD"
    
    def test_error_handling(self):
        processor = create_processor("custom", {
            "threshold": 2.0  # 无效配置
        })
        
        with pytest.raises(ValueError):
            processor([content])
            
    def test_batch_processing(self):
        processor = create_processor("custom", {"threshold": 0.5})
        
        contents = [
            Content(content_id=f"test_{i}", content=f"Content {i}")
            for i in range(5)
        ]
        
        results = processor(contents)
        assert len(results) == 5
        
    def test_processing_result(self):
        processor = create_processor("custom", {"threshold": 0.5})
        content = Content(content_id="test", content="test content")
        
        result = processor.process_single(content)
        assert result.success
        assert result.content is not None
        assert result.metadata["processor"] == "CustomProcessor"
```

## 📈 性能和监控

### 性能特性

#### HTMLContentProcessor

- **解析器**: 使用 readability 进行主要内容提取
- **浏览器支持**: 支持Playwright和browserless服务
- **回退机制**: 浏览器失败时自动回退到requests
- **缓存优化**: Session级别的连接复用

#### LLMProcessor系列

- **API 优化**: 智能处理API速率限制
- **错误重试**: 自动重试失败的API调用（可配置重试次数）
- **内容预处理**: 自动处理超长内容
- **提供者支持**: 支持多种LLM提供者（OpenAI等）

### 监控和日志

```python
import structlog

logger = structlog.get_logger(__name__)

# 处理器会自动记录关键事件
logger.info("Processor initialized", processor="HTMLContentProcessor")
logger.info("Processing started", content_id=content.content_id)
logger.info("Processing completed", processing_time=0.25, success=True)
logger.error("Processing failed", error="Connection timeout", content_id="123")
```

### 性能优化建议

```python
# 1. 批量处理优化
processor = create_processor("llm_summary", {
    "model_name": "gpt-3.5-turbo",
    "batch_size": 10  # 批量处理大小
})

# 2. 使用缓存
processor = create_processor("html_content", {
    "timeout": 30,
    "cache_enabled": True  # 启用缓存
})

# 3. 并行处理（适用于无依赖的处理器）
from concurrent.futures import ThreadPoolExecutor

def parallel_process(contents, processor):
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(processor, [content]) for content in contents]
        results = [future.result()[0] for future in futures]
    return results
```

## 🔄 向后兼容性

为确保平滑迁移，新架构保持了向后兼容性：

```python
# 传统API仍然可用
from octopus_scraper.processors import AVALIABLE_PROCESSOR

# 创建处理器 (传统方式)
old_processor = AVALIABLE_PROCESSOR["html_content"]({
    "timeout": 30
})

# 新式API (推荐)
new_processor = create_processor("html_content", {
    "timeout": 30
})

# 两种方式创建的处理器功能相同
assert type(old_processor) == type(new_processor)
```

## 🛠️ 最佳实践

### 1. 配置管理

- 使用环境变量存储敏感信息（如API密钥）
- 为不同环境配置不同的处理器参数
- 定期验证处理器配置的有效性

```python
import os

config = {
    "model_name": "gpt-3.5-turbo",
    "api_key": os.getenv("OPENAI_API_KEY"),
    "timeout": int(os.getenv("LLM_TIMEOUT", "30"))
}
```

### 2. 错误处理

- 实现优雅的降级机制
- 记录详细的错误信息用于调试
- 对LLM API调用实现重试机制

### 3. 性能优化

- 合理设置内容长度限制
- 使用批量处理提高效率
- 监控处理器性能指标

### 4. 扩展开发

- 遵循统一的处理器接口
- 提供详细的配置文档
- 实现完整的单元测试

## 📚 相关文档

- **[处理器测试文档](./processors-testing.md)** - 详细的测试策略和用例
- **[配置管理文档](../config/config-manager.md)** - 配置系统详细说明
- **[任务管理文档](../task_manager/)** - 任务管理系统集成

## 📊 架构特点

### 🏗️ 模块化架构
- **清晰分离**: 注册、配置、管道各司其职
- **插件化设计**: 支持动态扩展和第三方处理器
- **标准接口**: 统一的ProcessorBase抽象基类

### 🚀 功能特性  
- **多种处理器**: 支持HTML处理、LLM摘要、标签提取、关键词提取
- **灵活配置**: 详细的配置选项和验证机制
- **管道支持**: 支持处理器链式调用和依赖管理

### 🛡️ 稳定性保证
- **错误处理**: 完善的异常处理和日志记录
- **优雅降级**: 失败时的回退机制
- **向后兼容**: 保持传统API的兼容性

### 📈 性能优化
- **批量处理**: 支持内容批量处理提高效率
- **智能重试**: LLM处理器支持失败重试
- **缓存机制**: Session级别的连接复用

**OctopusScraper处理器系统提供了企业级的内容处理能力，支持从简单的HTML清理到复杂的AI增强处理！** 🎉
