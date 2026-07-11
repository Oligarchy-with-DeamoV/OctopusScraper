# OctopusScraper

![Python Version](https://img.shields.io/badge/python-3.9%7C3.10-blue)
![Test Coverage](https://img.shields.io/badge/coverage-95%25-brightgreen)
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

**推荐使用 Docker Compose 进行一键部署，简单快捷，包含完整的服务栈 [OctopusScraper + RSSHub + Redis]**

#### 1. 准备 Notion 配置

首先需要获取 Notion API 密钥和数据库 ID：

1. **获取 Notion API 密钥**: 参考 [官方文档](https://developers.notion.com/docs/create-a-notion-integration)
2. **获取数据库 ID**: 参考 [官方文档](https://developers.notion.com/docs/working-with-databases)

#### 2. 克隆项目并配置环境变量

```bash
cd OctopusScraper

# 创建 .env 文件
cp resources/envs/deploy.prod.env .env
```

编辑 `.env` 文件，填入您的 Notion 配置：

```env
# Notion API Configuration
NOTION_API_KEY="api_key"
NOTION_CONTENT_DATABASE_ID="database_id"
NOTION_SCRAPERS_DATABASE_ID="scraper_database_id"

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

#### 4. 在 Notion 中配置抓取器

在抓取器配置数据库中添加记录，例如：

| Name          | Status | Fetcher | Hub Root           | Route                           | Priority | Fetch Params  |
| ------------- | ------ | ------- | ------------------ | ------------------------------- | -------- | ------------- |
| VSCode Issues | Active | rsshub  | http://rsshub:1200 | /github/issues/microsoft/vscode | 1        | {"limit": 20} |
| 少数派热门    | Active | rsshub  | http://rsshub:1200 | /sspai/matrix                   | 2        | {"limit": 15} |

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
| POST | `/trigger_upload` | 上传已完成任务产生的内容 |
| GET | `/admin/config/status` | 查看当前配置状态 |
| POST | `/admin/config/refresh` | 从 Notion 刷新配置并重载 Octopus |
| GET | `/admin/system/info` | 查看系统与 TaskManager 摘要 |
| GET | `/admin/scrapers` | 查看已配置的 scraper |
| GET | `/admin/tasks/stats` | 查看任务统计 |
| GET | `/admin/tasks` | 查看任务列表，支持 `status` 与 `limit` 查询参数 |
| GET | `/admin/tasks/<task_id>` | 查看单个任务详情 |
| GET | `/admin/monitoring/metrics` | 查看 JSON 格式运行指标 |
