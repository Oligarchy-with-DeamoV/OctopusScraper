# OctopusScraper

![Python Version](https://img.shields.io/badge/python-3.9%7C3.10-blue)
![Test Coverage](https://img.shields.io/badge/coverage-82%25-brightgreen)
![License](https://img.shields.io/badge/license-Apache%202.0-green)

OctopusScraper 是一款多功能信息抓取工具，旨在通过高效的算法分析和处理各种媒体数据。它隶属于 [Podcast 矩阵生成项目](https://www.notion.so/1a2fee3943728058be3be79b782e1cf4?pvs=4)，但具备广泛的应用潜力，可以作为中间件为其他项目提供数据抓取和分析能力。OctopusScraper 灵活高效，能够为后续项目提供强大的支持，助力快速实现数据整合与分析，为各类项目赋能。

## ✨ 特性

- 🕷️ **多源数据抓取**: 支持 RSS、RSSHub、直接网页抓取等多种数据源
- 🔧 **灵活配置**: 基于 Notion 数据库的动态配置管理，支持环境变量覆盖
- 🚀 **高性能**: 异步处理，支持并发抓取
- 📊 **智能存储**: 自动去重，支持 Notion 数据库存储
- 🎯 **智能内容处理**: 可配置的摘要长度控制，内容回退机制
- 🔄 **实时监控**: 内置 Web 服务，提供配置管理和状态监控
- �️ **管理界面**: 完整的 Web 管理界面，支持配置热重载、抓取器测试、系统监控
- �🏥 **企业级健康检查**: 三层健康检查体系，支持容器环境存活/就绪探针，智能缓存机制
- 📈 **性能监控**: 内存使用监控、响应时间跟踪、依赖项状态检查
- 🧪 **高测试覆盖**: 82%+ 测试覆盖率，确保代码质量
- 🛠️ **易于扩展**: 模块化设计，支持自定义处理器和存储后端
- 📱 **CLI 工具**: 提供 `octopus_go` 和 `octopus_service` 命令行工具
- ⚙️ **配置热更新**: 支持动态配置刷新，无需重启服务
- 🎛️ **任务管理系统**: 统一的任务队列、优先级调度、并发控制和监控
- 📅 **定时调度**: 基于 Cron 表达式的自动任务调度
- 🔄 **任务重试**: 智能重试机制，支持指数退避和最大重试次数
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
USE_TASK_MANAGER=true
TASK_MANAGER_MAX_CONCURRENT=8
TASK_MANAGER_MAX_QUEUE_SIZE=1000
SERVICE_HOST=0.0.0.0
SERVICE_PORT=8000
DEBUG=false
ENVIRONMENT=production
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
      content_processor_configs: {}
    fetch_params:
      limit: 10
```

## ⚙️ 配置

### 配置文件结构

OctopusScraper 使用现代化的任务管理系统配置格式。推荐直接复制 [config.example.yml](config.example.yml) 文件开始使用。

#### 推荐配置（现代格式）

```yaml
# 使用最新任务管理系统的配置格式
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

# 任务管理配置
use_task_manager: true
task_manager_config:
  max_concurrent_tasks: 8
  max_queue_size: 1000
  result_retention_hours: 48

service:
  host: "0.0.0.0"
  port: 8000
  debug: false

# 任务管理配置
task_management:
  enabled: true
  max_workers: 4
  max_queue_size: 1000
  enable_retry: true
  max_retry_attempts: 3
  retry_delay: 5
  max_retry_delay: 300
  retry_backoff_factor: 2.0

# 调度器配置
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

OctopusScraper 提供了一个强大的任务管理系统，支持统一的任务队列、优先级调度、并发控制和监控。

### TaskManager

TaskManager 是任务管理系统的核心组件，提供基于优先级队列的并发任务执行。

#### 主要特性

- **优先级队列**: 支持高、中、低三种优先级
- **并发控制**: 可配置的工作线程数量
- **任务重试**: 智能重试机制，支持指数退避
- **统计监控**: 实时任务状态跟踪和性能指标
- **生命周期钩子**: 任务开始、完成、失败时的回调

#### 使用示例

```python
from octopus_scraper.task_manager import TaskManager, ScraperTask, TaskPriority

# 创建任务管理器
task_manager = TaskManager(
    max_workers=4,
    max_queue_size=1000,
    enable_retry=True,
    max_retry_attempts=3
)

# 创建任务
task = ScraperTask(
    name="example_task",
    scraper_name="example_scraper",
    priority=TaskPriority.HIGH,
    timeout=60,
    retry_count=0,
    max_retries=3
)

# 提交任务
task_manager.submit_task(task)

# 启动任务管理器
task_manager.start()

# 获取统计信息
stats = task_manager.get_stats()
print(f"已完成任务: {stats.completed_tasks}")
print(f"失败任务: {stats.failed_tasks}")
```

### TaskScheduler

TaskScheduler 提供基于 Cron 表达式的自动任务调度功能。

#### 主要特性

- **Cron 表达式**: 支持标准的 Cron 时间表达式
- **任务调度**: 自动创建和提交定时任务
- **调度管理**: 添加、删除、暂停调度任务
- **优雅关闭**: 正确处理调度器关闭和清理

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

在配置文件中启用任务管理系统：

```yaml
# Task Management Configuration
task_management:
  enabled: true
  max_workers: 4
  max_queue_size: 1000
  enable_retry: true
  max_retry_attempts: 3
  retry_delay: 5
  max_retry_delay: 300
  retry_backoff_factor: 2.0

# Scheduler Configuration
scheduler:
  enabled: true
  schedules:
    - name: "daily_news"
      scraper_name: "news_scraper"
      cron_expression: "0 8 * * *"
      priority: "high"
      timeout: 300
      max_retries: 2

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
curl http://localhost:8080/tasks/stats

# 获取活跃任务
curl http://localhost:8080/tasks/active

# 获取调度器状态
curl http://localhost:8080/scheduler/status
```

## 🔌 API 文档

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
GET /admin/runtime/scrapers    # 获取运行时抓取器列表
POST /admin/scrapers/test/{scraper_name}  # 测试指定抓取器
```

#### 系统管理

```http
POST /admin/cache/clear        # 清理缓存
POST /admin/system/gc          # 强制垃圾回收
GET /admin/system/state        # 导出系统状态
POST /admin/config/watcher/restart  # 重启配置监控
```

#### 监控接口

```http
GET /admin/monitoring/metrics  # 获取监控指标
GET /admin/tasks/stats         # 任务统计信息
GET /admin/tasks/list          # 任务列表
POST /admin/tasks/submit       # 提交单个任务
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
GET /tasks/stats
```

**响应示例：**

```json
{
  "status": "success",
  "data": {
    "total_tasks": 150,
    "completed_tasks": 120,
    "failed_tasks": 5,
    "pending_tasks": 25,
    "active_tasks": 3,
    "queue_size": 22,
    "workers_count": 4,
    "uptime_seconds": 3600,
    "tasks_per_minute": 2.5,
    "average_task_duration": 45.2,
    "success_rate": 0.96
  }
}
```

#### 获取活跃任务列表

```http
GET /tasks/active
```

**响应示例：**

```json
{
  "status": "success",
  "data": {
    "active_tasks": [
      {
        "id": "task_123",
        "name": "news_scraper",
        "scraper_name": "daily_news",
        "status": "running",
        "priority": "high",
        "started_at": "2025-01-20T10:30:00Z",
        "timeout": 300,
        "retry_count": 0,
        "worker_id": "worker_1"
      }
    ]
  }
}
```

#### 提交新任务

```http
POST /tasks/submit
```

**请求体：**

```json
{
  "name": "custom_task",
  "scraper_name": "example_scraper",
  "priority": "normal",
  "timeout": 120,
  "max_retries": 2,
  "params": {
    "custom_param": "value"
  }
}
```

**响应示例：**

```json
{
  "status": "success",
  "message": "Task submitted successfully",
  "data": {
    "task_id": "task_456",
    "name": "custom_task",
    "status": "queued",
    "priority": "normal",
    "created_at": "2025-01-20T10:35:00Z"
  }
}
```

#### 获取调度器状态

```http
GET /scheduler/status
```

**响应示例：**

```json
{
  "status": "success",
  "data": {
    "scheduler_running": true,
    "schedules_count": 3,
    "next_run_times": [
      {
        "name": "daily_news",
        "next_run": "2025-01-21T08:00:00Z",
        "cron_expression": "0 8 * * *"
      },
      {
        "name": "hourly_updates",
        "next_run": "2025-01-20T11:00:00Z",
        "cron_expression": "0 * * * *"
      }
    ]
  }
}
```

#### 添加调度任务

```http
POST /scheduler/add
```

**请求体：**

```json
{
  "name": "weekly_report",
  "scraper_name": "report_scraper",
  "cron_expression": "0 9 * * 1",
  "priority": "normal",
  "timeout": 600,
  "max_retries": 1
}
```

**响应示例：**

```json
{
  "status": "success",
  "message": "Schedule added successfully",
  "data": {
    "name": "weekly_report",
    "next_run": "2025-01-27T09:00:00Z"
  }
}
```

## 🛠️ 开发指南

### 项目结构

```
src/octopus_scraper/
├── cli/                    # CLI 相关代码
├── config/                 # 配置管理
│   ├── config_manager.py   # 配置管理器
│   ├── models.py          # 数据模型
│   └── notion_config.py   # Notion 配置客户端
├── scrapers/              # 抓取器模块
│   ├── processors/        # 内容处理器
│   ├── utils/            # 工具类
│   │   ├── direct_rss.py  # 直接 RSS 抓取
│   │   ├── notion_api.py  # Notion API 封装
│   │   ├── rsshub.py     # RSSHub 抓取
│   │   └── tools.py      # 通用工具
│   └── scraper.py        # 抓取器基类
├── task_manager/          # 任务管理系统
│   ├── __init__.py       # 模块导出
│   ├── models.py         # 任务数据模型
│   ├── task_manager.py   # 任务管理器
│   └── scheduler.py      # 任务调度器
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
from octopus_scraper.scrapers.scraper_protos import Content

class CustomScraper(Scraper):
    def scrap_contents(self) -> List[Content]:
        # 实现自定义抓取逻辑
        pass
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
USE_TASK_MANAGER=true
TASK_MANAGER_MAX_CONCURRENT=8
TASK_MANAGER_MAX_QUEUE_SIZE=1000
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

### 内容处理配置

| 变量名                       | 说明                   | 必需 | 默认值 |
| ---------------------------- | ---------------------- | ---- | ------ |
| `OCTOPUS_SUMMARY_MAX_LENGTH` | RSS 摘要最大长度(字符) | 否   | `500`  |

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
