# OctopusScraper

![Go Version](https://img.shields.io/badge/go-1.26-blue)
![License](https://img.shields.io/badge/license-Apache%202.0-green)

OctopusScraper 是一个 RSS/Atom 内容采集服务。它从 RSSHub 或直接订阅地址抓取
内容，按需执行 HTML 和 OpenAI 兼容处理器，将结果保存到 PostgreSQL，也可以
继续同步到 Notion。

项目只负责信息采集、处理和持久化。业务分析、知识整理和决策由下游系统完成。

## 主要能力

- 支持 RSSHub 路由和直接 RSS/Atom 地址。
- 支持正文提取、摘要、关键词和标签处理。
- 使用 PostgreSQL 保存权威内容，重复抓取不会重复写入。
- 可选同步到 Notion，Notion 故障不会影响 PostgreSQL 写入。
- 提供任务触发、健康检查、管理接口、MCP 读取接口和 Prometheus 指标。

## 快速开始

### 准备

- Docker 和 Docker Compose。
- 一个可访问的 PostgreSQL 实例。Compose 不会创建 PostgreSQL。
- 一个 RSS/Atom 地址，或可用的 RSSHub 路由。

### 1. 创建运行配置

```bash
cp resources/envs/deploy.prod.env .env
cp resources/scraper.example.yaml resources/scrapers.d/my-feed.yaml
```

编辑 `.env`，至少确认 PostgreSQL 连接信息：

```env
POSTGRES_DB=octopus
POSTGRES_USER=octopus
POSTGRES_PASSWORD=replace-with-a-strong-password
DB_HOST=host.docker.internal
DB_PORT=5432
```

编辑 `resources/scrapers.d/my-feed.yaml`，启用并填写订阅地址：

```yaml
id: my-feed
name: My Feed
enabled: true
fetcher: direct_rss
hub_root: https://example.com
route: /feed.xml
fetch_params: {}
priority: 5
content_processor_configs: {}
default_keywords:
  - feed
```

将示例地址替换为真实订阅地址。RSSHub 和处理器配置见
[`docs/configuration.md`](docs/configuration.md)。

### 2. 启动服务

```bash
docker compose up -d --build
docker compose ps
```

默认情况下，宿主机通过 `http://localhost:8001` 访问服务。

### 3. 检查并触发采集

```bash
curl http://localhost:8001/health/readiness
curl -X POST http://localhost:8001/trigger_scraper
curl "http://localhost:8001/admin/tasks?limit=10"
```

采集任务在 PostgreSQL 写入成功后完成。启用 Notion 同步后，可以手动触发一批
增量同步：

```bash
curl -X POST http://localhost:8001/trigger_upload
```

## 文档

| 内容 | 文档 |
| --- | --- |
| 文档导航 | [`docs/index.md`](docs/index.md) |
| 环境变量、scraper 和处理器配置 | [`docs/configuration.md`](docs/configuration.md) |
| HTTP API 和 MCP | [`docs/api.md`](docs/api.md) |
| 系统架构和运行流程 | [`docs/architecture.md`](docs/architecture.md) |
| PostgreSQL 与 Notion 同步 | [`docs/storage.md`](docs/storage.md) |
| 日志、指标和告警 | [`docs/monitoring.md`](docs/monitoring.md) |
| 本地开发和贡献流程 | [`CONTRIBUTING.md`](CONTRIBUTING.md) |

## 许可证

OctopusScraper 使用 [Apache License 2.0](LICENSE)。
