# OctopusScraper

![Python Version](https://img.shields.io/badge/python-3.9%7C3.10-blue)
![Test Coverage](https://img.shields.io/badge/coverage-95%25-brightgreen)
![License](https://img.shields.io/badge/license-Apache%202.0-green)

OctopusScraper 是一款多功能信息抓取工具，旨在通过高效的算法分析和处理各种媒体数据。它隶属于 [Podcast 矩阵生成项目](https://www.notion.so/1a2fee3943728058be3be79b782e1cf4?pvs=4)，但具备广泛的应用潜力，可以作为中间件为其他项目提供数据抓取和分析能力。OctopusScraper 灵活高效，能够为后续项目提供强大的支持，助力快速实现数据整合与分析，为各类项目赋能。

> 项目个人投入暂停：目前 Scraper 处理的 pipeline 需要在 octopus_serivce 中在 config 字典中进行 hardcode。
> 暂停的原因有两个：
> 1、公网中的信息大多为垃圾二手信息没有太多花功夫订阅总结的必要
> 2、个人暂时没有起号，通过流量赚钱的想法
>
> 倘若后续个人或者有朋友愿意继续贡献代码，这边会进行支持

> 📢 **重大架构升级**:
>
> - **TaskManager**: 统一的任务执行引擎，提供优先级调度、并发控制和实时监控
> - **Processor 架构**: Phase 4 完成企业级处理器系统升级，引入ProcessorRegistry、ProcessorFactory、ProcessorPipeline等核心组件

## ✨ 特性

- 🕷️ **多源数据抓取**: 支持 RSS、RSSHub、直接网页抓取等多种数据源
- 🔧 **灵活配置**: 基于 Notion 数据库的动态配置管理，支持环境变量覆盖
- 🚀 **高性能**: 异步处理，支持并发抓取
- 📊 **智能存储**: 自动去重，支持 Notion 数据库存储
- 🎯 **智能内容处理**: 可配置的摘要长度控制，内容回退机制，支持 HTML 清理和 LLM 增强
- 🏗️ **企业级处理器架构**: 模块化插件系统，支持动态注册、配置管理、管道处理
- 🔄 **实时监控**: 内置 Web 服务，提供配置管理和状态监控
- 🖥️ **管理界面**: 完整的 Web 管理界面，支持配置热重载、抓取器测试、系统监控
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
- [基础使用](#基础使用)
- [部署配置](#部署配置)
- [开发指南](#开发指南)
- [测试](#测试)
- [更新日志](CHANGELOG.md)
- [贡献](#贡献)

## 📚 详细文档

- **[完整文档](docs/README.md)** - 系统架构和详细说明
- **[任务管理系统](docs/models/task_manager/)** - TaskManager和TaskScheduler详细文档
- **[内容处理系统](docs/models/processors/)** - 处理器架构和开发指南
- **[配置管理](docs/models/config/)** - 配置系统详细说明
- **[Web服务接口](docs/interface/web_service/)** - API文档和管理界面
- **[CLI工具](docs/interface/cli/)** - 命令行工具使用指南

## 🚀 安装

### 系统要求

- Python 3.9 - 3.10
- Poetry

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

## 📖 基础使用

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

```bash
# 使用默认配置启动服务
poetry run octopus_service

# 自定义配置启动
poetry run octopus_service --host 127.0.0.1 --port 8080 --debug

# 查看所有可用选项
poetry run octopus_service --help
```

### 基础配置

OctopusScraper 使用统一的任务管理系统。推荐直接复制 [config.example.yml](config.example.yml) 文件开始使用。

```yaml
# 抓取器配置
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
```

> 📚 **详细配置**: 查看 **[配置管理文档](docs/models/config/)** 了解完整的配置选项和说明

## 🎛️ 核心特性

### 任务管理系统

OctopusScraper 采用统一的任务管理系统，提供优先级调度、并发控制和实时监控功能。TaskManager 已成为默认且唯一的任务执行方式。

- **统一任务执行**: 所有抓取操作都通过 TaskManager 执行
- **优先级队列**: 支持高、中、低三种优先级调度
- **智能重试**: 支持指数退避的重试机制
- **定时调度**: 基于 Cron 表达式的自动任务调度

> 📚 **详细说明**: 查看 **[任务管理系统文档](docs/models/task_manager/)** 了解完整的功能和配置选项

### 内容处理系统

提供模块化的内容处理架构，支持多种处理器的组合使用，实现智能内容清理、格式化和AI增强。

- **HTML内容处理器**: 支持动态网站抓取和内容清理
- **LLM系列处理器**: AI驱动的摘要生成、标签提取、关键词分析
- **可插拔架构**: 易于扩展和自定义处理器
- **处理器管道**: 支持处理器链式调用和依赖管理

> 📚 **详细说明**: 查看 **[内容处理系统文档](docs/models/processors/)** 了解处理器架构和开发指南

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

````yaml
content_processor_configs:
  llm:
    provider: "openai"
    model: "gpt-3.5-turbo"
## 🔌 API 概览

Web 服务提供以下主要 API 端点：

### 健康检查
- `GET /health` - 完整系统健康状态
- `GET /health/liveness` - 存活探针 (容器环境)
- `GET /health/readiness` - 就绪探针 (负载均衡)

### 抓取器管理
- `POST /trigger_scraper` - 触发抓取
- `POST /trigger_upload` - 触发上传
- `GET /admin/scrapers/list` - 获取抓取器列表

### 任务管理
- `GET /admin/tasks/stats` - 任务统计信息
- `GET /admin/tasks/list` - 任务列表
- `POST /admin/tasks/submit` - 提交任务

### 配置管理
- `GET /admin/config/status` - 配置状态
- `POST /admin/config/refresh` - 刷新配置
- `POST /admin/config/hotreload` - 热重载配置

### 管理界面
- `GET /admin` - Web 管理界面

> 📚 **完整API文档**: 查看 **[Web服务接口文档](docs/interface/web_service/)** 了解详细的API规范和响应格式

## 🚀 部署配置

### 推荐方式：Docker Compose

```bash
# 1. 克隆项目
git clone https://github.com/your-repo/OctopusScraper.git
cd OctopusScraper

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入你的 Notion 配置

# 3. 启动服务栈
docker-compose up -d

# 4. 访问管理界面
# http://localhost:8000/admin
````

### 其他部署方式

- **单容器部署**: 适用于简单场景的单服务部署
- **本地开发**: Poetry环境下的开发调试
- **生产环境**: Nginx反向代理、监控配置等

> 📚 **详细部署指南**: 查看具体的部署配置和生产环境优化说明

## 🛠️ 开发指南

### 快速开始

```bash
# 安装开发依赖
poetry install --with dev

# 安装 Pre-commit Hook
pre-commit install

# 运行代码检查
pre-commit run --all-files
```

### 项目结构

```
src/octopus_scraper/
├── __init__.py
├── cli/                       # CLI 工具模块
│   └── __init__.py
├── config/                    # 配置管理模块
│   ├── __init__.py
│   ├── config_manager.py      # 配置管理器
│   ├── models.py             # 配置数据模型
│   └── notion_config.py      # Notion 配置客户端
├── llm/                      # LLM 集成模块
│   ├── __init__.py
│   ├── client.py             # LLM 客户端
│   ├── prompts.py           # 提示词管理
│   ├── schemas.py           # LLM 数据模式
│   └── utils.py             # LLM 工具函数
├── processors/               # 内容处理器模块
│   ├── __init__.py           # 处理器注册系统
│   ├── processor_base.py     # 处理器抽象基类
│   ├── processor_config.py   # 处理器配置管理
│   ├── processor_pipeline.py # 处理器管道系统
│   ├── html_content_processor.py # HTML 内容处理器
│   ├── llm_processor.py      # LLM 处理器 (Legacy)
│   ├── llm_summary_processor.py  # LLM 摘要处理器
│   ├── llm_tags_processor.py     # LLM 标签处理器
│   ├── llm_keywords_processor.py # LLM 关键词处理器
│   └── protos.py            # 处理器数据模型
├── storages/                # 存储模块
│   ├── __init__.py
│   ├── base_storage.py      # 存储抽象基类
│   └── notion_storage.py    # Notion 存储实现
├── task_manager/            # 任务管理系统
│   ├── __init__.py
│   ├── models.py           # 任务数据模型
│   ├── task_manager.py     # 任务管理器
│   └── scheduler.py        # 任务调度器
├── utils/                   # 通用工具模块
│   ├── __init__.py
│   ├── direct_rss.py       # 直接 RSS 抓取工具
│   ├── rsshub.py          # RSSHub 抓取工具
│   ├── text_processor.py   # 文本处理工具
│   ├── tools.py           # 通用工具函数
│   └── validators.py       # 数据验证工具
├── protos.py               # 核心数据模型
├── scraper.py             # 抓取器核心逻辑
├── octopus.py            # 主要业务逻辑
├── octopus_service.py    # Web 服务入口
└── service_models.py     # 服务数据模型
```

> 📚 **详细开发指南**: 查看完整的开发文档、代码规范和扩展指南

## 🧪 测试

```bash
# 运行测试并生成覆盖率报告
poetry run pytest -m "not need_external_service and not integrate_test" --cov=octopus_scraper --cov-report=html
```

**测试覆盖率**: 84%+ (要求不低于80%)

## 📝 环境变量

### 必需配置

| 变量名                        | 说明                |
| ----------------------------- | ------------------- |
| `NOTION_API_KEY`              | Notion API 密钥     |
| `NOTION_SCRAPERS_DATABASE_ID` | 抓取器配置数据库 ID |
| `NOTION_CONTENT_DATABASE_ID`  | 内容存储数据库 ID   |

### 可选配置

| 变量名                 | 说明             | 默认值    |
| ---------------------- | ---------------- | --------- |
| `SERVICE_HOST`         | 服务监听地址     | `0.0.0.0` |
| `SERVICE_PORT`         | 服务监听端口     | `8000`    |
| `MAX_CONCURRENT_TASKS` | 最大并发任务数   | `8`       |
| `MAX_QUEUE_SIZE`       | 任务队列最大容量 | `1000`    |
| `LOG_LEVEL`            | 日志级别         | `INFO`    |

> � **完整配置**: 查看所有可用的环境变量和配置选项

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

## 🙏 致谢

- [Notion API](https://developers.notion.com/) - 提供强大的数据库服务
- [RSSHub](https://rsshub.app/) - 提供丰富的 RSS 源
- [Sanic](https://sanic.dev/) - 高性能异步 Web 框架

---

⭐ 如果这个项目对您有帮助，请给我们一个 Star！
