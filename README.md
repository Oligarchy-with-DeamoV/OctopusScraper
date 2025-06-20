# OctopusScraper

![Python Version](https://img.shields.io/badge/python-3.9%7C3.10-blue)
![Test Coverage](https://img.shields.io/badge/coverage-84%25-brightgreen)
![License](https://img.shields.io/badge/license-Apache%202.0-green)

OctopusScraper 是一款多功能信息抓取工具，旨在通过高效的算法分析和处理各种媒体数据。它隶属于 [Podcast 矩阵生成项目](https://www.notion.so/1a2fee3943728058be3be79b782e1cf4?pvs=4)，但具备广泛的应用潜力，可以作为中间件为其他项目提供数据抓取和分析能力。OctopusScraper 灵活高效，能够为后续项目提供强大的支持，助力快速实现数据整合与分析，为各类项目赋能。

## ✨ 特性

- 🕷️ **多源数据抓取**: 支持 RSS、RSSHub、直接网页抓取等多种数据源
- 🔧 **灵活配置**: 基于 Notion 数据库的动态配置管理
- 🚀 **高性能**: 异步处理，支持并发抓取
- 📊 **智能存储**: 自动去重，支持 Notion 数据库存储
- 🔄 **实时监控**: 内置 Web 服务，提供配置管理和状态监控
- 🧪 **高测试覆盖**: 84%+ 测试覆盖率，确保代码质量
- 🛠️ **易于扩展**: 模块化设计，支持自定义处理器和存储后端
- 📱 **CLI 工具**: 提供 `octopus_go` 和 `octopus_service` 命令行工具
- ⚙️ **配置热更新**: 支持动态配置刷新，无需重启服务

## 📋 目录

- [安装](#安装)
- [快速开始](#快速开始)
- [配置](#配置)
- [使用方法](#使用方法)
- [API 文档](#api-文档)
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

### 1. 准备 Notion 配置

首先需要获取 Notion API 密钥和数据库 ID：

1. **获取 Notion API 密钥**: 参考 [官方文档](https://developers.notion.com/docs/create-a-notion-integration)
2. **获取数据库 ID**: 参考 [官方文档](https://developers.notion.com/docs/working-with-databases)

### 2. 环境变量配置

```bash
# 设置环境变量
export NOTION_API_KEY="your_notion_api_key"
export NOTION_SCRAPERS_DATABASE_ID="your_scrapers_database_id"
export NOTION_CONTENT_DATABASE_ID="your_content_database_id"
```

### 3. 运行示例

```bash
# 查看 CLI 工具帮助信息
poetry run octopus_go --help
poetry run octopus_service --help

# 仅抓取内容（不上传）
poetry run octopus_go --config ./tests/octopus_scraper/cli/octopus_test_config.yml

# 抓取内容并上传到 Notion
poetry run octopus_go --config ./tests/octopus_scraper/cli/octopus_test_config.yml --notion_upload

# 启动 Web 服务 (推荐使用命令行工具)
poetry run octopus_service

# 启动 Web 服务 (自定义配置)
poetry run octopus_service --host 127.0.0.1 --port 8080 --debug --single-process

# 或者直接运行服务文件 (不推荐)
poetry run python src/octopus_scraper/octopus_service.py
```

## ⚙️ 配置

### 配置文件结构

OctopusScraper 支持两种配置方式：

1. **YAML 配置文件** (适用于 CLI 模式)
2. **Notion 数据库配置** (适用于 Web 服务模式)

#### YAML 配置示例

参考 [config.example.yml](config.example.yml) 文件：

```yaml
# config.yml
scrapers:
  - name: "示例抓取器"
    fetcher: "rsshub"
    hub_root: "https://rsshub.app"
    route: "/example/route"
    priority: 1
    fetch_params:
      limit: 10

notion:
  api_key: "${NOTION_API_KEY}"
  content_database_id: "${NOTION_CONTENT_DATABASE_ID}"

service:
  host: "0.0.0.0"
  port: 8000
  debug: false
```

#### Notion 数据库配置

在 Notion 中创建以下结构的数据库：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| Name | Title | 抓取器名称 |
| Status | Select | 状态 (Active/Inactive) |
| Fetcher | Select | 抓取器类型 (rsshub/direct_rss) |
| Hub Root | URL | 根 URL |
| Route | Rich Text | 路由路径 |
| Priority | Number | 优先级 |
| Fetch Params | Rich Text | JSON 格式的参数 |

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

## 🔌 API 文档

Web 服务提供以下 API 端点：

### 健康检查
```http
GET /health
```

**响应示例：**
```json
{
  "status": "ok"
}
```

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

| 变量名 | 说明 | 必需 | 默认值 |
|--------|------|------|--------|
| `NOTION_API_KEY` | Notion API 密钥 | 是 | - |
| `NOTION_SCRAPERS_DATABASE_ID` | 抓取器配置数据库 ID | 是 | - |
| `NOTION_CONTENT_DATABASE_ID` | 内容存储数据库 ID | 是 | - |

### 服务配置 (CLI 工具)

| 变量名 | 说明 | 必需 | 默认值 |
|--------|------|------|--------|
| `OCTOPUS_HOST` | 服务监听地址 (CLI) | 否 | `0.0.0.0` |
| `OCTOPUS_PORT` | 服务监听端口 (CLI) | 否 | `8000` |
| `OCTOPUS_DEBUG` | 调试模式 (CLI) | 否 | `false` |
| `OCTOPUS_LOG_LEVEL` | 日志级别 (CLI) | 否 | `INFO` |
| `OCTOPUS_LOG_FORMAT` | 日志格式 (CLI) | 否 | `plain` |
| `OCTOPUS_WORKERS` | 工作进程数 (CLI) | 否 | `1` |
| `OCTOPUS_SINGLE_PROCESS` | 单进程模式 (CLI) | 否 | `false` |

### 服务配置 (直接启动)

| 变量名 | 说明 | 必需 | 默认值 |
|--------|------|------|--------|
| `SERVICE_HOST` | 服务监听地址 | 否 | `0.0.0.0` |
| `SERVICE_PORT` | 服务监听端口 | 否 | `8000` |
| `DEBUG` | 调试模式 | 否 | `false` |
| `LOG_LEVEL` | 日志级别 (DEBUG/INFO/WARNING/ERROR) | 否 | `INFO` |
| `LOG_FORMAT` | 日志格式 (plain/json) | 否 | `plain` |
| `CONFIG_REFRESH_INTERVAL` | 配置刷新间隔(秒) | 否 | `300` |
| `SCRAPER_TIMEOUT` | 抓取超时时间(秒) | 否 | `10` |
| `UPLOAD_TIMEOUT` | 上传超时时间(秒) | 否 | `15` |
| `UPLOAD_MAX_RETRIES` | 上传最大重试次数 | 否 | `3` |

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
