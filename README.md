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
-  **智能重试**: 支持指数退避和最大重试次数的智能重试机制
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
- **[任务管理系统](docs/models/task_manager/)** - TaskManager详细文档
- **[内容处理系统](docs/models/processors/)** - 处理器架构和开发指南
- **[配置管理](docs/models/config/)** - 配置系统详细说明
- **[Web服务接口](docs/interface/web_service/)** - API文档和管理界面
- **[CLI工具](docs/interface/cli/)** - 命令行工具使用指南

## ⚡ 快速开始

### 🐳 推荐方式：Docker Compose 部署

**推荐使用 Docker Compose 进行一键部署，简单快捷，包含完整的服务栈 [OctopusScraper + RSSHub + Redis]**

#### 1. 准备 Notion 配置

首先需要获取 Notion API 密钥和数据库 ID：

1. **获取 Notion API 密钥**: 参考 [官方文档](https://developers.notion.com/docs/create-a-notion-integration)
2. **获取数据库 ID**: 参考 [官方文档](https://developers.notion.com/docs/working-with-databases)

#### 2. 克隆项目并配置环境变量

```bash
cd OctopusScraper

# 创建 .env 文件
cp envs/deploy.prod.env .env
```

编辑 `.env` 文件，填入您的 Notion 配置：

```env
# Notion API Configuration
NOTION_API_KEY="api_key"
NOTION_CONTENT_DATABASE_ID="database_id"
NOTION_SCRAPERS_DATABASE_ID="scraper_database_id"

# other envs...
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

#### 4. 在 Notion 中配置抓取器

在抓取器配置数据库中添加记录，例如：

| Name          | Status | Fetcher | Hub Root           | Route                           | Priority | Fetch Params  |
| ------------- | ------ | ------- | ------------------ | ------------------------------- | -------- | ------------- |
| VSCode Issues | Active | rsshub  | http://rsshub:1200 | /github/issues/microsoft/vscode | 1        | {"limit": 20} |
| 少数派热门    | Active | rsshub  | http://rsshub:1200 | /sspai/matrix                   | 2        | {"limit": 15} |

#### 5. 使用命令触发拉取和上传

TODO: 这部分的操作完全没有必要人工来，只是为了系统的解耦做的。计划后续再 docker-compose 中增加一个服务每隔十分钟触发一次。

```bash
# 触发根据配置拉取服务
curl -X POST http://localhost:8000/trigger_scraper

# 触发根据结果上传服务
curl -X POST http://localhost:8000/trigger_upload
```