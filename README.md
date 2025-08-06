# OctopusScraper

![Python Version](https://img.shields.io/badge/python-3.9%7C3.10-blue)
![Test Coverage](https://img.shields.io/badge/coverage-82%25-brightgreen)
![License](https://img.shields.io/badge/license-Apache%202.0-green)

OctopusScraper 是一款多功能信息抓取工具，旨在通过高效的算法分析和处理各种媒体数据。它隶属于 [Podcast 矩阵生成项目](https://www.notion.so/1a2fee3943728058be3be79b782e1cf4?pvs=4)，但具备广泛的应用潜力，可以作为中间件为其他项目提供数据抓取和分析能力。OctopusScraper 灵活高效，能够为后续项目提供强大的支持，助力快速实现数据整合与分析，为各类项目赋能。

> 📢 **架构升级**: TaskManager 现已成为统一的任务执行引擎，为所有抓取操作提供优先级调度、并发控制和实时监控。详见 [TaskManager 更新指南](docs/TASK_MANAGER_UPDATES.md)

## ✨ 特性

- 🕷️ **多源数据抓取**: 支持 RSS、RSSHub、直接网页抓取等多种数据源
- 🔧 **灵活配置**: 基于 Notion 数据库的动态配置管理，支持环境变量覆盖
- 🚀 **高性能**: 异步处理，支持并发抓取
- 📊 **智能存储**: 自动去重，支持 Notion 数据库存储
- 🎯 **智能内容处理**: 可配置的摘要长度控制，内容回退机制，支持 HTML 清理和 LLM 增强
- 🔧 **内容处理器**: 模块化的内容处理架构，支持 HTML 解析、LLM 智能增强等
- 🔄 **实时监控**: 内置 Web 服务，提供配置管理和状态监控
- �️ **管理界面**: 完整的 Web 管理界面，支持配置热重载、抓取器测试、系统监控
- �🏥 **企业级健康检查**: 三层健康检查体系，支持容器环境存活/就绪探针，智能缓存机制
- 📈 **性能监控**: 内存使用监控、响应时间跟踪、依赖项状态检查
- 🧪 **高测试覆盖**: 82%+ 测试覆盖率，确保代码质量
- 🛠️ **易于扩展**: 模块化设计，支持自定义处理器和存储后端
- 📱 **CLI 工具**: 提供 `octopus_go` 和 `octopus_service` 命令行工具
- ⚙️ **配置热更新**: 支持动态配置刷新，无需重启服务
- 🎛️ **统一任务管理**: 默认启用的 TaskManager 系统，提供任务队列、优先级调度、并发控制和监控
- 📅 **定时调度**: 基于 Cron 表达式的自动任务调度
- 🔄 **智能重试**: 支持指数退避和最大重试次数的智能重试机制
- 📊 **任务监控**: 实时任务状态跟踪、统计信息和性能指标

## 📋 目录

- [安装](#安装)
- [快速开始](#快速开始)
- [配置](#配置)
- [使用方法](#使用方法)
- [任务管理系统](#任务管理系统)
  - [TaskManager](#taskmanager)
  - [TaskScheduler](#taskscheduler)
  - [配置示例](#任务管理配置示例)
- [内容处理系统](#内容处理系统)
  - [HTMLContentProcessor](#htmlcontentprocessor)
  - [LLMProcessor](#llmprocessor)
  - [自定义处理器](#自定义处理器)
- [API 文档](#api-文档)
- [部署配置](#部署配置)
- [开发指南](#开发指南)
- [测试](#测试)
- [更新日志](CHANGELOG.md)
- [贡献](#贡献)

## 🚀 安装

### 系统要求

- Python 3.9 - 3.10
- Poetry (推荐) 或 pip

### 使用 Poetry (推荐)

```bash
# 克隆项目
git clone https://github.com/your-repo/OctopusScraper.git
cd OctopusScraper

# 安装依赖
poetry install

# 激活虚拟环境
poetry shell
```

### 使用 pip

```bash
# 克隆项目
git clone https://github.com/your-repo/OctopusScraper.git
cd OctopusScraper

# 安装依赖
pip install -r requirements.txt
```

> 💡 **提示**: 使用 `-vvv` 参数可以获取详细的安装信息以便调试。

## ⚡ 快速开始

### 🐳 推荐方式：Docker Compose 部署

**推荐使用 Docker Compose 进行一键部署，简单快捷，包含完整的服务栈（OctopusScraper + RSSHub + Redis + Browserless）。**

#### 1. 准备 Notion 配置

首先需要获取 Notion API 密钥和数据库 ID：

1. **获取 Notion API 密钥**: 参考 [官方文档](https://developers.notion.com/docs/create-a-notion-integration)
2. **获取数据库 ID**: 参考 [官方文档](https://developers.notion.com/docs/working-with-databases)

#### 2. 克隆项目并配置环境变量

```bash
# 克隆项目
git clone https://github.com/your-repo/OctopusScraper.git
cd OctopusScraper

# 创建 .env 文件
cp .env.example .env
```

编辑 `.env` 文件，填入您的 Notion 配置：

```env
# Notion 配置 (必需)
NOTION_API_KEY=your_notion_api_key_here
NOTION_SCRAPERS_DATABASE_ID=your_scrapers_database_id
NOTION_CONTENT_DATABASE_ID=your_content_database_id

# 服务配置 (可选，有默认值)
LOG_LEVEL=INFO
LOG_FORMAT=json
CONFIG_REFRESH_INTERVAL=300

# TaskManager 配置 (默认启用)
MAX_CONCURRENT_TASKS=8
MAX_QUEUE_SIZE=1000
RESULT_RETENTION_HOURS=48

# 调度器配置 (可选)
ENABLE_SCHEDULER=false
AUTO_START_SCHEDULER=false
MAX_CONCURRENT_SCHEDULES=10
SCHEDULE_CHECK_INTERVAL=60

# 服务运行配置
SERVICE_HOST=0.0.0.0
SERVICE_PORT=8000
DEBUG=false
ENVIRONMENT=production

# 健康检查配置
HEALTHCHECK_SKIP_NOTION=false
```

#### 3. 一键启动服务

```bash
# 启动完整服务栈 (推荐)
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f octopus-service
```

#### 4. 访问服务

服务启动后，访问以下端点：

- **管理界面**: http://localhost:8000/admin
- **健康检查**: http://localhost:8000/health
- **RSSHub 服务**: http://localhost:1200 (可选，用于 RSS 数据源)

#### 5. 在 Notion 中配置抓取器

在抓取器配置数据库中添加记录，例如：

| Name          | Status | Fetcher | Hub Root           | Route                           | Priority | Fetch Params  |
| ------------- | ------ | ------- | ------------------ | ------------------------------- | -------- | ------------- |
| VSCode Issues | Active | rsshub  | http://rsshub:1200 | /github/issues/microsoft/vscode | 1        | {"limit": 20} |
| 少数派热门    | Active | rsshub  | http://rsshub:1200 | /sspai/matrix                   | 2        | {"limit": 15} |

### 🛠️ 本地开发方式

如果您需要进行开发或自定义，可以使用以下方式：

#### 1. 准备 Notion 配置

首先需要获取 Notion API 密钥和数据库 ID：

1. **获取 Notion API 密钥**: 参考 [官方文档](https://developers.notion.com/docs/create-a-notion-integration)
2. **获取数据库 ID**: 参考 [官方文档](https://developers.notion.com/docs/working-with-databases)

#### 2. 本地环境设置

```bash
# 克隆项目
git clone https://github.com/your-repo/OctopusScraper.git
cd OctopusScraper

# 安装依赖
poetry install

# 激活虚拟环境
poetry shell
```

#### 3. 配置设置

```bash
# 复制配置文件
cp config.example.yml config.yml

# 设置环境变量
export NOTION_API_KEY="your_notion_api_key"
export NOTION_CONTENT_DATABASE_ID="your_database_id"

# 可选：配置内容处理参数
export OCTOPUS_SUMMARY_MAX_LENGTH="500"  # RSS 摘要最大长度
```

#### 4. 启动服务

```bash
# 启动 Web 服务 (推荐)
poetry run octopus_service

# 或者直接运行抓取
poetry run octopus_go --config config.yml --notion_upload

# 查看 CLI 工具帮助信息
poetry run octopus_go --help
poetry run octopus_service --help
```

### 4. 管理界面

服务启动后，访问以下端点：

- **管理界面**: http://localhost:8000/admin
- **健康检查**: http://localhost:8000/health
- **API 文档**: 参考下方 [API 文档](#api-文档) 部分

### 5. 默认配置说明

`config.example.yml` 包含以下开箱即用的配置：

#### 默认抓取器

- **VS Code Issues**: GitHub Issues 抓取
- **少数派热门**: 热门文章抓取
- **技术博客**: 阮一峰的博客 RSS
- **HackerNews**: 热门新闻

#### 任务管理配置

- 最大并发任务数: 8
- 队列大小: 1000
- 结果保留时间: 48 小时

#### 服务配置

- 监听地址: 0.0.0.0:8000
- 日志级别: INFO
- 配置刷新间隔: 5 分钟

### 6. 自定义配置

修改 `config.yml` 中的 `scrapers_config_with_fetch_params` 部分添加你自己的抓取源：

```yaml
scrapers_config_with_fetch_params:
  - scraper_config:
      fetcher_name: "rsshub"
      fetcher_config:
        hub_root: "https://rsshub.app"
        route: "/your/custom/route"
      content_processor_configs:
        html_content:
          remove_tags: ["script", "style", "nav"]
          preserve_formatting: true
        llm:
          provider: "openai"
          model: "gpt-3.5-turbo"
          max_tokens: 500
    fetch_params:
      limit: 10
```

## ⚙️ 配置

### 配置文件结构

OctopusScraper 使用统一的任务管理系统，TaskManager 现已成为默认且唯一的任务执行方式。推荐直接复制 [config.example.yml](config.example.yml) 文件开始使用。

> 🔧 **重要更新**: 从最新版本开始，TaskManager 已成为默认且唯一的任务管理方式，不再需要手动配置 `use_task_manager` 参数。

#### 基础配置

```yaml
# 抓取器配置 - 使用统一的任务管理系统
scrapers_config_with_fetch_params:
  - scraper_config:
      fetcher_name: "rsshub"
      fetcher_config:
        hub_root: "https://rsshub.app"
        route: "/github/issues/microsoft/vscode"
      content_processor_configs: {}
    fetch_params:
      limit: 20

# Notion 配置
notion_api_config:
  api_key: "${NOTION_API_KEY}"
  database_id: "${NOTION_CONTENT_DATABASE_ID}"

# TaskManager 配置 (默认启用)
task_manager_config:
  max_concurrent_tasks: 8
  max_queue_size: 1000
  result_retention_hours: 48

service:
  host: "0.0.0.0"
  port: 8000
  debug: false

# TaskManager 配置 (默认启用，无需手动开启)
task_management:
  # TaskManager 现已默认启用，以下为高级配置选项
  max_workers: 4 # 工作线程数
  max_queue_size: 1000 # 队列最大容量
  enable_retry: true # 启用任务重试
  max_retry_attempts: 3 # 最大重试次数
  retry_delay: 5 # 重试间隔(秒)
  max_retry_delay: 300 # 最大重试间隔(秒)
  retry_backoff_factor: 2.0 # 重试退避因子

# 调度器配置 (可选)
scheduler:
  enabled: true # 启用定时调度
  schedules:
    - name: "daily_news"
      scraper_name: "news_scraper"
      cron_expression: "0 8 * * *"
      priority: "high"
      timeout: 300
      max_retries: 2
```

#### Notion 数据库配置

在 Notion 中创建以下结构的数据库：

| 字段名       | 类型      | 说明                           |
| ------------ | --------- | ------------------------------ |
| Name         | Title     | 抓取器名称                     |
| Status       | Select    | 状态 (Active/Inactive)         |
| Fetcher      | Select    | 抓取器类型 (rsshub/direct_rss) |
| Hub Root     | URL       | 根 URL                         |
| Route        | Rich Text | 路由路径                       |
| Priority     | Number    | 优先级                         |
| Fetch Params | Rich Text | JSON 格式的参数                |

## 📖 使用方法

### CLI 模式

```bash
# 基本用法
poetry run octopus_go --config config.yml

# 抓取内容并上传到 Notion
poetry run octopus_go --config config.yml --notion_upload

# 查看帮助信息
poetry run octopus_go --help
```

### Web 服务模式

推荐使用 `octopus_service` 命令行工具启动服务：

```bash
# 使用默认配置启动服务
poetry run octopus_service

# 自定义配置启动
poetry run octopus_service --host 127.0.0.1 --port 8080 --debug

# 完整的命令行选项
poetry run octopus_service \
  --host 0.0.0.0 \
  --port 8000 \
  --debug \
  --log-level DEBUG \
  --log-format json \
  --single-process

# 查看所有可用选项
poetry run octopus_service --help
```

#### 传统方式启动 (不推荐)

```bash
# 直接运行服务文件
poetry run python src/octopus_scraper/octopus_service.py

# 或使用环境变量
SERVICE_HOST=0.0.0.0 SERVICE_PORT=8080 DEBUG=true poetry run python src/octopus_scraper/octopus_service.py
```

## 🎛️ 任务管理系统

OctopusScraper 采用统一的任务管理系统，TaskManager 已成为默认且唯一的任务执行方式，为所有抓取操作提供优先级调度、并发控制和监控功能。

> 📢 **架构更新**: 从最新版本开始，TaskManager 已完全替代传统抓取方式，成为统一的任务执行引擎。无需手动配置启用，所有任务都将通过 TaskManager 执行。

### TaskManager

TaskManager 是任务管理系统的核心组件，现已成为 OctopusScraper 的默认任务执行引擎。

#### 主要特性

- **统一任务执行**: 所有抓取操作都通过 TaskManager 执行
- **优先级队列**: 支持高、中、低三种优先级调度
- **并发控制**: 可配置的工作线程数量和队列容量
- **智能重试**: 支持指数退避的重试机制
- **实时监控**: 任务状态跟踪和性能指标统计
- **生命周期管理**: 完整的任务开始、完成、失败回调

#### 配置示例

TaskManager 现已默认启用，可通过环境变量或配置文件进行调优：

```python
# 环境变量配置
MAX_CONCURRENT_TASKS=8        # 最大并发任务数
MAX_QUEUE_SIZE=1000          # 队列最大容量
RESULT_RETENTION_HOURS=48    # 结果保留时间

# 配置文件配置
task_manager_config:
  max_concurrent_tasks: 8
  max_queue_size: 1000
  result_retention_hours: 48
```

#### 使用示例

TaskManager 现已自动集成到所有抓取操作中：

```python
from octopus_scraper import Octopus

# TaskManager 已自动启用，无需手动配置
octopus = Octopus(config_path="config.yml")

# 所有抓取操作都将通过 TaskManager 执行
# 支持优先级调度、并发控制和监控
contents = await octopus.trigger_scraper()

# 获取任务统计信息
stats = octopus.get_task_manager_stats()
print(f"已完成任务: {stats.completed_tasks}")
print(f"活跃任务: {stats.active_tasks}")
```

### TaskScheduler

TaskScheduler 提供基于 Cron 表达式的自动任务调度功能，可通过环境变量动态配置启用。

#### 主要特性

- **Cron 表达式**: 支持标准的 Cron 时间表达式
- **任务调度**: 自动创建和提交定时任务
- **调度管理**: 添加、删除、暂停调度任务
- **优雅关闭**: 正确处理调度器关闭和清理
- **动态配置**: 支持环境变量控制启用/禁用
- **自动启动**: 可配置服务启动时自动启动调度器

#### 环境变量配置

```bash
# 调度器配置
ENABLE_SCHEDULER=true              # 启用调度器功能
AUTO_START_SCHEDULER=true          # 服务启动时自动启动调度器
MAX_CONCURRENT_SCHEDULES=10        # 最大并发调度任务数
SCHEDULE_CHECK_INTERVAL=60         # 调度检查间隔（秒）
```

#### 使用示例

```python
from octopus_scraper.task_manager import TaskScheduler, TaskScheduleConfig

# 创建任务调度器
scheduler = TaskScheduler(task_manager)

# 创建调度配置
schedule_config = TaskScheduleConfig(
    name="daily_scrape",
    scraper_name="daily_scraper",
    cron_expression="0 8 * * *",  # 每天8点执行
    priority=TaskPriority.NORMAL,
    timeout=300,
    max_retries=2
)

# 添加调度任务
scheduler.add_schedule(schedule_config)

# 启动调度器
scheduler.start()

# 便捷方法：添加每日任务
scheduler.add_daily_task(
    name="morning_news",
    scraper_name="news_scraper",
    hour=9,
    minute=0
)
```

### 任务管理配置示例

#### 环境变量配置（推荐）

```bash
# TaskManager 配置（默认启用）
MAX_CONCURRENT_TASKS=8          # 最大并发任务数
MAX_QUEUE_SIZE=1000            # 任务队列容量
RESULT_RETENTION_HOURS=48      # 结果保留时间

# 调度器配置（可选）
ENABLE_SCHEDULER=true          # 启用调度器
AUTO_START_SCHEDULER=true      # 自动启动调度器
MAX_CONCURRENT_SCHEDULES=10    # 最大并发调度数
SCHEDULE_CHECK_INTERVAL=60     # 检查间隔（秒）
```

#### 配置文件配置

在配置文件中启用任务管理系统：

```yaml
# Task Management Configuration (Always Enabled)
task_manager_config:
  max_concurrent_tasks: 8
  max_queue_size: 1000
  result_retention_hours: 48

# Scheduler Configuration (Optional)
scheduler_config:
  enable_scheduler: true
  auto_start_scheduler: true
  max_concurrent_schedules: 10
  schedule_check_interval: 60

# Legacy Scheduler Configuration (For Notion-based schedules)
scheduler:
  enabled: true
  schedules:
    - name: "daily_news"
      scraper_name: "news_scraper"
      cron_expression: "0 8 * * *"
      priority: "high"
      timeout: 300
      max_retries: 2
```

    - name: "hourly_updates"
      scraper_name: "update_scraper"
      cron_expression: "0 * * * *"
      priority: "normal"
      timeout: 120
      max_retries: 1
```

### 任务状态监控

通过 Web API 获取任务状态和统计信息：

```bash
# 获取任务统计
curl http://localhost:8000/admin/tasks/stats

# 获取任务列表
curl http://localhost:8000/admin/tasks/list

# 提交新任务
curl -X POST http://localhost:8000/admin/tasks/submit \
  -H "Content-Type: application/json" \
  -d '{"scraper_name": "example_scraper", "fetch_params": {"limit": 10}}'
```

## � 内容处理系统

OctopusScraper 提供了模块化的内容处理架构，支持多种内容处理器的组合使用，实现智能内容清理、格式化和增强。

> 📌 **位置**: `src/octopus_scraper/processors/`

### 架构特性

- **模块化设计**: 支持多个处理器链式处理
- **可插拔架构**: 易于扩展和自定义处理器
- **配置驱动**: 通过配置文件灵活控制处理行为
- **错误容错**: 处理器失败时的优雅降级机制

### HTMLContentProcessor

HTMLContentProcessor 专门用于 HTML 内容的解析、清理和格式化。

#### 主要功能

- **HTML 标签清理**: 移除不需要的标签和属性
- **内容提取**: 提取纯文本或保留特定格式
- **格式标准化**: 统一 HTML 格式和编码
- **安全清理**: 移除潜在的恶意代码

#### 配置示例

```yaml
content_processor_configs:
  html_content:
    remove_tags: ["script", "style", "nav", "footer"]
    preserve_formatting: true
    max_content_length: 10000
    encoding: "utf-8"
    extract_text_only: false
```

#### 使用示例

```python
from octopus_scraper.processors import HTMLContentProcessor

# 创建处理器
config = {
    "remove_tags": ["script", "style"],
    "preserve_formatting": True
}
processor = HTMLContentProcessor(config)

# 处理 HTML 内容
cleaned_content = processor.process(html_content)
```

### LLMProcessor

LLMProcessor 利用大语言模型对内容进行智能增强和处理。

#### 主要功能

- **智能摘要**: 自动生成内容摘要
- **内容增强**: 改善内容质量和可读性
- **多模型支持**: 支持 OpenAI、Claude 等多种 LLM
- **定制提示**: 可配置的处理提示词

#### 配置示例

```yaml
content_processor_configs:
  llm:
    provider: "openai"
    model: "gpt-3.5-turbo"
    api_key: "${OPENAI_API_KEY}"
    max_tokens: 500
    temperature: 0.3
    custom_prompt: "请为以下内容生成简洁的摘要："
    fallback_on_error: true
```

#### 使用示例

```python
from octopus_scraper.processors import LLMProcessor

# 创建处理器
config = {
    "provider": "openai",
    "model": "gpt-3.5-turbo",
    "max_tokens": 300
}
processor = LLMProcessor(config)

# 处理内容
enhanced_content = processor.process(original_content)
```

### 处理器组合使用

多个处理器可以链式组合使用：

```yaml
scrapers_config_with_fetch_params:
  - scraper_config:
      fetcher_name: "rsshub"
      fetcher_config:
        hub_root: "https://rsshub.app"
        route: "/tech/news"
      content_processor_configs:
        # 第一步：HTML 清理
        html_content:
          remove_tags: ["script", "style", "ads"]
          preserve_formatting: true
        # 第二步：LLM 增强
        llm:
          provider: "openai"
          model: "gpt-3.5-turbo"
          max_tokens: 400
          custom_prompt: "生成技术新闻摘要"
    fetch_params:
      limit: 20
```

### 自定义处理器

创建自定义内容处理器：

```python
from octopus_scraper.processors.protos import ProcessorConfig
from octopus_scraper.scrapers.protos import Content

class CustomProcessorConfig(ProcessorConfig):
    """自定义处理器配置"""
    custom_param: str = ""
    max_length: int = 1000

class CustomProcessor:
    """自定义内容处理器"""
    
    def __init__(self, config: dict):
        self.config = from_dict(CustomProcessorConfig, config)
    
    def process(self, content: Content) -> Content:
        """处理内容的核心逻辑"""
        # 实现自定义处理逻辑
        processed_content = self._custom_processing(content.content)
        
        # 返回处理后的内容
        return Content(
            title=content.title,
            content=processed_content,
            url=content.url,
            publish_date=content.publish_date
        )
    
    def _custom_processing(self, text: str) -> str:
        """自定义处理逻辑"""
        # 实现具体的处理算法
        return text

# 注册自定义处理器
from octopus_scraper.processors import AVALIABLE_PROCESSOR
AVALIABLE_PROCESSOR["custom"] = CustomProcessor
```

### 错误处理和回退机制

```yaml
content_processor_configs:
  llm:
    provider: "openai"
    model: "gpt-3.5-turbo"
    fallback_on_error: true  # 处理失败时使用原始内容
    retry_attempts: 2        # 重试次数
    timeout: 30             # 超时时间(秒)
```

### 性能优化建议

1. **合理配置处理器顺序**: 先进行轻量级处理(如HTML清理)，再进行重量级处理(如LLM)
2. **设置合适的超时时间**: 避免LLM处理时间过长
3. **使用回退机制**: 确保处理失败时有备选方案
4. **批量处理**: 对于大量内容，考虑批量提交给LLM处理

更多详细文档请参考：
- [Processors 模型文档](docs/models/processors/processors.md)
- [Processors 测试文档](docs/models/processors/processors-testing.md)

## �🔌 API 文档

Web 服务提供以下 API 端点：

### 健康检查

OctopusScraper 提供了三个专业的健康检查端点，适用于不同的监控场景：

#### 1. 全面健康检查

```http
GET /health
```

提供完整的系统健康状态，包括依赖项检查、配置状态、性能指标等。

**查询参数：**

- `cache` (可选): `true`/`false` - 是否使用缓存，默认 `true`

**响应示例：**

```json
{
  "status": "healthy",
  "timestamp": "2025-07-18T15:56:22.080523",
  "service": {
    "name": "OctopusService",
    "version": "0.1.2",
    "uptime_seconds": 1234.56
  },
  "dependencies": {
    "notion_api": {
      "status": "healthy",
      "scrapers_database": {
        "id": "your_scrapers_db_id",
        "accessible": true
      },
      "content_database": {
        "id": "your_content_db_id",
        "accessible": true
      }
    },
    "octopus_instance": {
      "status": "healthy",
      "scrapers_configured": 3,
      "fetched_contents_cached": 15
    }
  },
  "configuration": {
    "status": "healthy",
    "last_check": "2025-07-18T15:56:20.123456",
    "next_check": "2025-07-18T16:01:20.123456",
    "version": "v20250718_155620_abc123",
    "scrapers_count": 3,
    "active_scrapers": 2,
    "error": null
  },
  "performance": {
    "response_time_ms": 45.67,
    "memory_usage": {
      "rss_mb": 128.5
    }
  },
  "cached": false
}
```

#### 2. 存活探针 (Liveness Probe)

```http
GET /health/liveness
```

轻量级健康检查，适用于 Docker 等容器环境的存活探针。

**响应示例：**

```json
{
  "status": "alive",
  "timestamp": "2025-07-18T15:56:22.080523",
  "service": {
    "name": "OctopusService",
    "version": "0.1.2"
  }
}
```

#### 3. 就绪探针 (Readiness Probe)

```http
GET /health/readiness
```

检查服务是否准备好接收流量，包含关键依赖项验证。

**查询参数：**

- `skip_notion` (可选): `true`/`false` - 是否跳过 Notion API 检查，默认 `false`

**响应示例：**

```json
{
  "status": "ready",
  "timestamp": "2025-07-18T15:56:22.080523",
  "service": {
    "name": "OctopusService",
    "version": "0.1.2"
  },
  "dependencies": {
    "notion_api": {
      "status": "healthy",
      "checked": true
    },
    "octopus_instance": {
      "status": "healthy"
    }
  }
}
```

**健康检查状态码：**

- `200 OK`: 健康/就绪
- `503 Service Unavailable`: 不健康/未就绪
- `500 Internal Server Error`: 检查过程出错

**缓存机制：**
全面健康检查支持智能缓存（30 秒），减少重复检查的性能开销。可通过 `?cache=false` 参数禁用缓存获取实时状态。

### 抓取器管理

```http
POST /trigger_scraper    # 触发抓取
POST /trigger_upload     # 触发上传
```

**抓取器响应示例：**

```json
{
  "status": "success",
  "message": "Scraping completed.",
  "data": {
    "source_count": 3,
    "item_count": 18
  }
}
```

**上传响应示例：**

```json
{
  "status": "success",
  "message": "Upload completed.",
  "data": {
    "uploaded_count": 18
  }
}
```

### 配置管理

```http
GET /admin/config/status       # 获取配置状态
POST /admin/config/refresh     # 刷新配置
POST /admin/config/validate    # 验证配置
POST /admin/config/hotreload   # 热重载配置
```

**配置状态响应示例：**

```json
{
  "is_healthy": true,
  "last_check": "2025-06-20T17:34:47.123456",
  "error_message": null,
  "current_version": {
    "version_id": "v20250620_173447_abc123",
    "timestamp": "2025-06-20T17:34:47.123456",
    "config_hash": "abc123def456",
    "scrapers_count": 3
  },
  "scrapers": [
    {
      "name": "示例抓取器",
      "status": "Active",
      "fetcher": "rsshub",
      "priority": 1
    }
  ]
}
```

### 管理接口

#### 管理面板概览

```http
GET /admin                     # 管理界面概览
```

**响应示例：**

```json
{
  "status": "success",
  "service_info": {
    "name": "OctopusService",
    "version": "0.1.4",
    "uptime_seconds": 3600
  },
  "quick_stats": {
    "scrapers_configured": 4,
    "tasks_completed": 120,
    "active_tasks": 3,
    "health_status": "healthy"
  },
  "available_actions": [
    "config_hotreload",
    "clear_cache",
    "force_gc",
    "test_scrapers"
  ]
}
```

#### 抓取器管理

```http
GET /admin/scrapers/list           # 获取抓取器列表
POST /admin/scrapers/test/{scraper_name}  # 测试指定抓取器
```

#### 系统管理

```http
POST /admin/cache/clear            # 清理缓存
POST /admin/runtime/gc             # 强制垃圾回收
POST /admin/debug/dump-state       # 导出系统状态
GET /admin/runtime/config-watcher  # 获取配置监控状态
POST /admin/runtime/config-watcher # 重启配置监控
```

#### 监控接口

```http
GET /admin/monitoring/metrics      # 获取监控指标
GET /admin/tasks/stats            # 任务统计信息
GET /admin/tasks/list             # 任务列表
POST /admin/tasks/submit          # 提交单个任务
```

**配置刷新响应示例：**

```json
{
  "status": "success",
  "message": "Configuration refreshed successfully",
  "config_changed": true,
  "current_version": "v20250620_173447_abc123",
  "scrapers_count": 3
}
```

### 任务管理 API

#### 获取任务统计信息

```http
GET /admin/tasks/stats
```

**响应示例：**

```json
{
  "status": "success",
  "statistics": {
    "total_tasks": 150,
    "completed_tasks": 120,
    "failed_tasks": 5,
    "pending_tasks": 25,
    "running_tasks_count": 3,
    "current_queue_size": 22,
    "max_concurrent_tasks": 8,
    "queue_capacity": 1000,
    "uptime_seconds": 3600,
    "tasks_per_minute": 2.5,
    "average_task_duration": 45.2,
    "success_rate": 0.96,
    "task_manager_enabled": true,
    "legacy_mode": false,
    "uptime_info": {
      "queue_capacity_usage": "22/1000",
      "worker_utilization": "3/8"
    },
    "timestamp": "2025-07-28T10:30:00.123456"
  }
}
```

#### 获取任务列表

```http
GET /admin/tasks/list
```

**响应示例：**

```json
{
  "status": "success",
  "tasks": [
    {
      "task_id": "task_123",
      "name": "news_scraper",
      "scraper_name": "daily_news",
      "status": "running",
      "priority": "high",
      "created_at": "2025-01-20T10:30:00Z",
      "started_at": "2025-01-20T10:30:05Z",
      "timeout": 300,
      "retry_count": 0
    }
  ],
  "filters": {
    "status": null,
    "limit": 50
  },
  "total_returned": 1,
  "task_manager_enabled": true
}
```

#### 提交新任务

```http
POST /admin/tasks/submit
```

**请求体：**

```json
{
  "scraper_name": "example_scraper",
  "fetch_params": {
    "limit": 20,
    "custom_param": "value"
  }
}
```

**响应示例：**

```json
{
  "status": "success",
  "message": "Task submitted successfully",
  "task_id": "task_456",
  "scraper_name": "example_scraper",
  "fetch_params": {
    "limit": 20,
    "custom_param": "value"
  }
}
```

#### 获取任务详情

```http
GET /admin/tasks/{task_id}
```

**响应示例：**

```json
{
  "status": "success",
  "task": {
    "task_id": "task_123",
    "name": "news_scraper",
    "scraper_name": "daily_news",
    "status": "completed",
    "priority": "high",
    "created_at": "2025-01-20T10:30:00Z",
    "started_at": "2025-01-20T10:30:05Z",
    "completed_at": "2025-01-20T10:32:15Z",
    "retry_count": 0,
    "result": "Task completed successfully"
  }
}
```

### 调度器管理 API

> **注意**: 调度器功能需要通过环境变量 `ENABLE_SCHEDULER=true` 启用。

#### 获取调度器状态

```http
GET /admin/scheduler/status
```

**响应示例：**

```json
{
  "status": "success",
  "scheduler_status": {
    "enabled": true,
    "running": true,
    "total_schedules": 5,
    "enabled_schedules": 3,
    "running_scheduled_tasks": 2,
    "next_run": "2025-08-04T09:00:00.000Z",
    "schedules_by_status": {
      "enabled": 3,
      "disabled": 2
    }
  },
  "configuration": {
    "max_concurrent_schedules": 10,
    "schedule_check_interval": 60,
    "auto_start_scheduler": true
  }
}
```

#### 启动/停止调度器

```http
POST /admin/scheduler/start     # 启动调度器
POST /admin/scheduler/stop      # 停止调度器
POST /admin/scheduler/restart   # 重启调度器
```

**响应示例：**

```json
{
  "status": "success",
  "message": "Scheduler started successfully",
  "scheduler_running": true,
  "timestamp": "2025-08-04T10:00:00.000Z"
}
```

#### 获取调度任务列表

```http
GET /admin/scheduler/schedules
```

**查询参数：**
- `status` (可选): `enabled`/`disabled` - 按状态过滤
- `limit` (可选): 限制返回数量，默认50

**响应示例：**

```json
{
  "status": "success",
  "schedules": [
    {
      "id": "schedule_1",
      "name": "daily_news",
      "scraper_name": "news_scraper",
      "cron_expression": "0 9 * * *",
      "enabled": true,
      "next_run": "2025-08-05T09:00:00.000Z",
      "last_run": "2025-08-04T09:00:00.000Z",
      "last_run_status": "success",
      "priority": "normal",
      "timeout": 300,
      "max_retries": 2
    }
  ],
  "total_schedules": 5,
  "enabled_schedules": 3
}
```

#### 添加调度任务

```http
POST /admin/scheduler/schedules
```

**请求体：**

```json
{
  "name": "weekly_report",
  "scraper_name": "report_scraper",
  "cron_expression": "0 8 * * 1",
  "enabled": true,
  "priority": "high",
  "timeout": 600,
  "max_retries": 3,
  "fetch_params": {
    "report_type": "weekly"
  }
}
```

**响应示例：**

```json
{
  "status": "success",
  "message": "Schedule added successfully",
  "schedule": {
    "id": "schedule_6",
    "name": "weekly_report",
    "next_run": "2025-08-05T08:00:00.000Z"
  }
}
```

#### 更新调度任务

```http
PUT /admin/scheduler/schedules/{schedule_id}
```

#### 删除调度任务

```http
DELETE /admin/scheduler/schedules/{schedule_id}
```

#### 手动触发调度任务

```http
POST /admin/scheduler/schedules/{schedule_id}/trigger
```

**响应示例：**

```json
{
  "status": "success",
  "message": "Schedule triggered successfully",
  "task_id": "task_789",
  "schedule": {
    "id": "schedule_1",
    "name": "daily_news",
    "triggered_at": "2025-08-04T10:15:00.000Z"
  }
}
```

> **配置说明**: 调度器功能可通过环境变量动态配置。设置 `ENABLE_SCHEDULER=true` 和 `AUTO_START_SCHEDULER=true` 可在服务启动时自动启用调度器。

## 🛠️ 开发指南

### 项目结构

```
src/octopus_scraper/
├── cli/                    # CLI 相关代码
├── config/                 # 配置管理
│   ├── config_manager.py   # 配置管理器
│   ├── models.py          # 数据模型
│   └── notion_config.py   # Notion 配置客户端
├── processors/            # 内容处理器模块 [新增]
│   ├── __init__.py        # 处理器导出
│   ├── html_content_processor.py  # HTML 内容处理器
│   ├── llm_processor.py   # LLM 智能处理器
│   └── protos.py         # 处理器数据模型
├── scrapers/              # 抓取器模块
│   ├── utils/            # 工具类
│   │   ├── direct_rss.py  # 直接 RSS 抓取
│   │   ├── notion_api.py  # Notion API 封装
│   │   ├── rsshub.py     # RSSHub 抓取
│   │   └── tools.py      # 通用工具
│   ├── protos.py         # 抓取器数据模型
│   └── scraper.py        # 抓取器基类
├── storages/              # 存储模块
│   └── notion_storage.py  # Notion 存储实现
├── task_manager/          # 任务管理系统 [统一架构]
│   ├── __init__.py       # 模块导出
│   ├── models.py         # 任务数据模型
│   ├── task_manager.py   # 任务管理器 (默认启用)
│   └── scheduler.py      # 任务调度器 (可选)
├── utils/                 # 通用工具
├── octopus.py            # 核心抓取逻辑
├── octopus_service.py    # Web 服务
└── service_models.py     # 服务模型
```

### 开发环境设置

1. **安装开发依赖**

   ```bash
   poetry install --with dev
   ```

2. **安装 Pre-commit Hook**

   ```bash
   brew install pre-commit  # macOS
   pre-commit install
   ```

3. **手动运行代码检查**
   ```bash
   pre-commit run --all-files
   ```

### 自定义抓取器

创建自定义抓取器：

```python
from octopus_scraper.scrapers.scraper import Scraper
from octopus_scraper.scrapers.protos import Content

class CustomScraper(Scraper):
    def scrap_contents(self) -> List[Content]:
        # 实现自定义抓取逻辑
        contents = []
        
        # 示例：抓取自定义数据源
        for item in self._fetch_data():
            content = Content(
                title=item['title'],
                content=item['content'],
                url=item['url'],
                publish_date=item['date']
            )
            contents.append(content)
        
        return contents
    
    def _fetch_data(self):
        # 实现具体的数据获取逻辑
        pass
```

### 自定义内容处理器

创建自定义内容处理器（详见[内容处理系统](#内容处理系统)）：

```python
from octopus_scraper.processors.protos import ProcessorConfig

class CustomProcessor:
    def __init__(self, config: dict):
        self.config = config
    
    def process(self, content: Content) -> Content:
        # 实现自定义内容处理逻辑
        processed_content = self._process_content(content.content)
        return Content(
            title=content.title,
            content=processed_content,
            url=content.url,
            publish_date=content.publish_date
        )
```

## 🚀 部署配置

### 🐳 推荐方式：Docker Compose 部署

**Docker Compose 是推荐的部署方式**，提供完整的服务栈，包括：

- **OctopusScraper**: 主服务
- **RSSHub**: RSS 数据源服务
- **Redis**: 缓存服务
- **Browserless**: 浏览器服务 (用于复杂网页抓取)

#### 快速部署

```bash
# 1. 克隆项目
git clone https://github.com/your-repo/OctopusScraper.git
cd OctopusScraper

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入你的 Notion 配置

# 3. 启动服务栈
docker-compose up -d

# 4. 查看服务状态
docker-compose ps

# 5. 查看日志
docker-compose logs -f octopus-service
```

#### 环境变量配置

创建 `.env` 文件：

```env
# Notion 配置 (必需)
NOTION_API_KEY=your_notion_api_key_here
NOTION_SCRAPERS_DATABASE_ID=your_scrapers_database_id
NOTION_CONTENT_DATABASE_ID=your_content_database_id

# 服务配置 (可选，有默认值)
LOG_LEVEL=INFO
LOG_FORMAT=json
CONFIG_REFRESH_INTERVAL=300
# TaskManager 配置 (默认启用)
MAX_CONCURRENT_TASKS=8
MAX_QUEUE_SIZE=1000
RESULT_RETENTION_HOURS=48
SERVICE_HOST=0.0.0.0
SERVICE_PORT=8000
DEBUG=false
ENVIRONMENT=production
```

#### 服务访问

- **OctopusScraper 管理界面**: http://localhost:8000/admin
- **健康检查**: http://localhost:8000/health
- **RSSHub 服务**: http://localhost:1200（需要手动 expose 端口）

#### 服务管理

```bash
# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 更新服务 (重新构建)
docker-compose up -d --build

# 查看特定服务日志
docker-compose logs -f octopus-service
docker-compose logs -f rsshub

# 清理未使用的资源
docker-compose down -v  # 包含数据卷
```

### 🐳 单容器 Docker 部署

如果您只需要 OctopusScraper 服务，可以使用单容器部署：

```bash
# 构建镜像
docker build -f dockerfiles/Dockerfile -t octopus-scraper .

# 运行容器
docker run -d \
  --name octopus-service \
  -p 8000:8000 \
  -e NOTION_API_KEY="your_api_key" \
  -e NOTION_SCRAPERS_DATABASE_ID="your_scrapers_db_id" \
  -e NOTION_CONTENT_DATABASE_ID="your_content_db_id" \
  -v $(pwd)/logs:/app/logs \
  octopus-scraper
```

### 🛠️ 本地开发部署

对于开发环境，推荐使用本地 Python 环境：

```bash
# 使用 Poetry (推荐)
poetry install
poetry shell
poetry run octopus_service

# 或使用 pip
pip install -r requirements.txt
python -m octopus_scraper.octopus_service
```

### ⚙️ 生产环境配置

#### Nginx 反向代理配置

如果您需要使用 Nginx 作为反向代理，可以取消注释 docker-compose.yml 中的 nginx 服务：

````nginx
events {
    worker_connections 1024;
}

http {
    upstream octopus_backend {
        server octopus-service:8000;
    }

    server {
        listen 80;
        server_name localhost;

        # 健康检查端点
        location /health {
            proxy_pass http://octopus_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            access_log off;
        }

        # API 端点
        location / {
            proxy_pass http://octopus_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_connect_timeout 30s;
            proxy_send_timeout 30s;
            proxy_read_timeout 30s;
        }
    }
}

### 监控配置

#### 健康检查脚本

创建健康检查脚本用于监控：

```bash
#!/bin/bash
# health_check.sh

SERVICE_URL="http://localhost:8000"

# 检查存活探针
liveness_check() {
    response=$(curl -s -o /dev/null -w "%{http_code}" "$SERVICE_URL/health/liveness")
    if [ "$response" = "200" ]; then
        echo "✅ Liveness check passed"
        return 0
    else
        echo "❌ Liveness check failed (HTTP $response)"
        return 1
    fi
}

# 检查就绪探针
readiness_check() {
    response=$(curl -s -o /dev/null -w "%{http_code}" "$SERVICE_URL/health/readiness")
    if [ "$response" = "200" ]; then
        echo "✅ Readiness check passed"
        return 0
    else
        echo "❌ Readiness check failed (HTTP $response)"
        return 1
    fi
}

# 全面健康检查
health_check() {
    curl -s "$SERVICE_URL/health?cache=false" | jq '.'
}

# 执行检查
echo "=== OctopusService Health Check ==="
liveness_check && readiness_check && echo "=== Full Health Status ===" && health_check
````

#### Prometheus 监控 (可选)

如果需要 Prometheus 监控，可以在 docker-compose.yml 中添加：

```yaml
# 在 docker-compose.yml 中添加 Prometheus
prometheus:
  image: prom/prometheus:latest
  container_name: octopus-prometheus
  ports:
    - "9090:9090"
  volumes:
    - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro
  command:
    - "--config.file=/etc/prometheus/prometheus.yml"
    - "--storage.tsdb.path=/prometheus"
    - "--web.console.libraries=/etc/prometheus/console_libraries"
    - "--web.console.templates=/etc/prometheus/consoles"
  networks:
    - octopus-network
```

**prometheus.yml 配置：**

```yaml
# prometheus.yml
global:
  scrape_interval: 30s

scrape_configs:
  - job_name: "octopus-service"
    static_configs:
      - targets: ["octopus-service:8000"]
    metrics_path: "/health"
    params:
      cache: ["false"] # 获取实时状态
    scrape_interval: 30s
```

## 🧪 测试

### 运行测试

```bash
# 运行所有测试
poetry run pytest

# 运行测试并生成覆盖率报告
poetry run pytest --cov=octopus_scraper --cov-report=html

# 运行特定测试
poetry run pytest tests/octopus_scraper/scrapers/

# 运行非集成测试
poetry run pytest -m "not integrate_test" --cov=octopus_scraper --cov-fail-under=80 ./tests/ -n auto
```

### 测试分类

- `not integrate_test`: 单元测试，不需要外部服务
- `integrate_test`: 集成测试，需要真实的外部服务

### 测试覆盖率要求

项目要求测试覆盖率不低于 **80%**，当前覆盖率为 **84%**。

## 📝 环境变量

### 基础配置

| 变量名                        | 说明                | 必需 | 默认值 |
| ----------------------------- | ------------------- | ---- | ------ |
| `NOTION_API_KEY`              | Notion API 密钥     | 是   | -      |
| `NOTION_SCRAPERS_DATABASE_ID` | 抓取器配置数据库 ID | 是   | -      |
| `NOTION_CONTENT_DATABASE_ID`  | 内容存储数据库 ID   | 是   | -      |

### 服务配置 (CLI 工具)

| 变量名                   | 说明               | 必需 | 默认值    |
| ------------------------ | ------------------ | ---- | --------- |
| `OCTOPUS_HOST`           | 服务监听地址 (CLI) | 否   | `0.0.0.0` |
| `OCTOPUS_PORT`           | 服务监听端口 (CLI) | 否   | `8000`    |
| `OCTOPUS_DEBUG`          | 调试模式 (CLI)     | 否   | `false`   |
| `OCTOPUS_LOG_LEVEL`      | 日志级别 (CLI)     | 否   | `INFO`    |
| `OCTOPUS_LOG_FORMAT`     | 日志格式 (CLI)     | 否   | `plain`   |
| `OCTOPUS_WORKERS`        | 工作进程数 (CLI)   | 否   | `1`       |
| `OCTOPUS_SINGLE_PROCESS` | 单进程模式 (CLI)   | 否   | `false`   |

### 服务配置 (直接启动)

| 变量名                    | 说明                                | 必需 | 默认值    |
| ------------------------- | ----------------------------------- | ---- | --------- |
| `SERVICE_HOST`            | 服务监听地址                        | 否   | `0.0.0.0` |
| `SERVICE_PORT`            | 服务监听端口                        | 否   | `8000`    |
| `DEBUG`                   | 调试模式                            | 否   | `false`   |
| `LOG_LEVEL`               | 日志级别 (DEBUG/INFO/WARNING/ERROR) | 否   | `INFO`    |
| `LOG_FORMAT`              | 日志格式 (plain/json)               | 否   | `plain`   |
| `CONFIG_REFRESH_INTERVAL` | 配置刷新间隔(秒)                    | 否   | `300`     |
| `SCRAPER_TIMEOUT`         | 抓取超时时间(秒)                    | 否   | `10`      |
| `UPLOAD_TIMEOUT`          | 上传超时时间(秒)                    | 否   | `15`      |
| `UPLOAD_MAX_RETRIES`      | 上传最大重试次数                    | 否   | `3`       |

### TaskManager 配置 (默认启用)

| 变量名                   | 说明                   | 必需 | 默认值 |
| ------------------------ | ---------------------- | ---- | ------ |
| `MAX_CONCURRENT_TASKS`   | 最大并发任务数         | 否   | `8`    |
| `MAX_QUEUE_SIZE`         | 任务队列最大容量       | 否   | `1000` |
| `RESULT_RETENTION_HOURS` | 任务结果保留时间(小时) | 否   | `48`   |

### 内容处理配置

| 变量名                       | 说明                   | 必需 | 默认值 |
| ---------------------------- | ---------------------- | ---- | ------ |
| `OCTOPUS_SUMMARY_MAX_LENGTH` | RSS 摘要最大长度(字符) | 否   | `500`  |
| `OPENAI_API_KEY`             | OpenAI API 密钥        | 否   | -      |
| `LLM_PROVIDER`               | LLM 服务提供商         | 否   | -      |
| `LLM_MODEL`                  | 使用的 LLM 模型        | 否   | -      |
| `LLM_MAX_TOKENS`             | LLM 最大 token 数      | 否   | `500`  |

> 💡 **说明**: 当 RSS 摘要超过指定长度时，将设为空并交由 LLM 处理器生成摘要。

## 🤝 贡献

我们欢迎所有形式的贡献！

### 贡献步骤

1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add some amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

### 贡献指南

- 确保所有测试通过
- 保持测试覆盖率不低于 80%
- 遵循现有的代码风格
- 添加必要的文档

## 📄 许可证

本项目采用 Apache License 2.0 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 📧 联系

- 作者: Duan-JM
- 邮箱: vincent.duan95@gmail.com
- 项目链接: [https://github.com/your-repo/OctopusScraper](https://github.com/your-repo/OctopusScraper)

## 🙏 致谢

- [Notion API](https://developers.notion.com/) - 提供强大的数据库服务
- [RSSHub](https://rsshub.app/) - 提供丰富的 RSS 源
- [Sanic](https://sanic.dev/) - 高性能异步 Web 框架

---

⭐ 如果这个项目对您有帮助，请给我们一个 Star！
