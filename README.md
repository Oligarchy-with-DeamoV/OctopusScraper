# OctopusScraper

![Python Version](https://img.shields.io/badge/python-3.9%7C3.10-blue)
![License](https://img.shields.io/badge/license-Apache%202.0-green)

OctopusScraper 是一款多功能信息抓取工具，旨在通过高效的算法分析和处理各种媒体数据。OctopusScraper 的核心在于「采集」而不是二次业务加工，因此涉及到「业务分析」相关的操作应当拒绝不包含在本仓库内。

## 📋 目录

- [安装](#安装)
- [快速开始](#快速开始)
- [基础使用](#基础使用)
- [部署配置](#部署配置)
- [开发指南](#开发指南)
- [测试](#测试)
- [更新日志](CHANGELOG.md)
- [贡献](#贡献)

## ⚡ 快速开始

### 🐳 推荐方式：Docker Compose 部署

**推荐使用 Docker Compose 一键部署，包含 OctopusScraper、PostgreSQL、RSSHub、Redis 和告警服务。**

#### 1. 准备 YAML 抓取配置

每个 Scraper 使用一个 `.yml` 或 `.yaml` 文件，放在
`resources/scrapers.d/`。服务会自动加载新增、修改和删除；无效修改会记录错误并继续使用上一份有效配置。

#### 2. 克隆项目并配置环境变量

```bash
cd OctopusScraper

# 创建 .env 文件
cp resources/envs/deploy.prod.env .env
```

编辑 `.env` 文件，配置 PostgreSQL 和可选的 Notion 同步：

```env
# Notion API Configuration
NOTION_API_KEY="api_key"
NOTION_CONTENT_DATABASE_ID="database_id"
NOTION_SYNC_ENABLED=true

POSTGRES_DB=octopus
POSTGRES_USER=octopus
POSTGRES_PASSWORD="change-me"

# other envs...
```

编辑 `.env` 文件，填入您的飞书 Webhook 配置：

```env
# Vector Monitor
FEISHU_WEBHOOK_URL="your feishu webhook"

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

#### 4. 配置抓取器

```yaml
id: vscode-issues
name: VSCode Issues
enabled: true
fetcher: rsshub
hub_root: http://rsshub:1200
route: /github/issues/microsoft/vscode
fetch_params:
  limit: 20
priority: 1
content_processor_configs: {}
default_keywords:
  - vscode
```

`id` 必须唯一且只能包含小写字母、数字、点、下划线和连字符。未知字段、重复
YAML key、重复 `id`/`name`、未知 fetcher 或 processor 会被拒绝。

#### 5. 使用命令触发拉取和上传

docker-compose 会自动使用 ./scheduler/crontab 中的配置定时执行配置更新和拉取上传指令按需配置。

```bash
# 触发根据配置拉取服务
curl -X POST http://localhost:8000/trigger_scraper

# 触发根据结果上传服务
curl -X POST http://localhost:8000/trigger_upload
```

保留的 HTTP API 面向个人部署的日常运行与排障，避免暴露低频调试/运行时控制接口：

| Method | Path | 用途 |
| ------ | ---- | ---- |
| GET | `/health` | 综合健康检查 |
| GET | `/health/liveness` | 轻量存活检查 |
| GET | `/health/readiness` | 就绪检查 |
| POST | `/trigger_scraper` | 按当前配置提交抓取任务 |
| POST | `/trigger_upload` | 手动触发 PostgreSQL → Notion 增量同步 |
| GET | `/admin/config/status` | 查看当前配置状态 |
| POST | `/admin/config/refresh` | 立即扫描 YAML 配置目录并热更新 |
| GET | `/admin/system/info` | 查看系统与 TaskManager 摘要 |
| GET | `/admin/scrapers` | 查看已配置的 scraper |
| GET | `/admin/tasks/stats` | 查看任务统计 |
| GET | `/admin/tasks` | 查看任务列表，支持 `status` 与 `limit` 查询参数 |
| GET | `/admin/tasks/<task_id>` | 查看单个任务详情 |
| GET | `/metrics` | Prometheus 指标抓取接口 |

Prometheus 抓取配置、告警规则和 Grafana 查询示例见
[`docs/monitoring.md`](docs/monitoring.md)。`/metrics` 已替代原有的
`/admin/monitoring/metrics` JSON 接口；迁移观察期内 Vector 告警服务仍会保留。

PostgreSQL 表结构、同步状态和重试机制见
[`docs/storage.md`](docs/storage.md)。
