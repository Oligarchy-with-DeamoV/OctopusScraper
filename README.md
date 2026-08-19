# OctopusScraper

![Go Version](https://img.shields.io/badge/go-1.26-blue)
![License](https://img.shields.io/badge/license-Apache%202.0-green)

OctopusScraper 是一个面向 RSS 信息源的采集服务。它负责抓取、内容处理、
PostgreSQL 持久化以及可选的 Notion 增量同步，不承载业务分析逻辑。

## 架构

```text
HTTP API -> Task Manager -> RSS Fetcher -> Processor Pipeline -> PostgreSQL
                                                              -> Notion Sync
```

- Go 单进程服务提供 HTTP API、配置热更新、任务调度和 Prometheus 指标。
- PostgreSQL 是内容的唯一事实来源。
- Notion 是可选的下游同步目标，故障不会影响抓取事务。
- RSSHub、Redis、scheduler 和 Vector 由 Docker Compose 独立运行。
- Browserless/Chrome 通过远程 CDP 使用，不打包进服务镜像。

## Docker Compose 部署

```bash
cp resources/envs/deploy.prod.env .env
cp resources/scraper.example.yaml resources/scrapers.d/my-feed.yaml
docker compose up -d
docker compose ps
```

主要配置：

```env
POSTGRES_DB=octopus
POSTGRES_USER=octopus
POSTGRES_PASSWORD=replace-with-a-strong-password
DB_HOST=host.docker.internal
DB_PORT=5432

NOTION_SYNC_ENABLED=false
NOTION_API_KEY=
NOTION_CONTENT_DATABASE_ID=

SERVICE_HOST=0.0.0.0
SERVICE_PORT=8000
LOG_LEVEL=INFO
LOG_FORMAT=plain
SCRAPER_CONFIG_DIR=/etc/octopus-scraper/scrapers.d
TASK_MANAGER_MAX_CONCURRENT=3
TASK_MANAGER_MAX_QUEUE_SIZE=1000
```

目标 Notion database 必须包含且只包含一个 data source。零个或多个 data
source 会在首次同步时返回明确错误，不影响服务启动或 PostgreSQL 抓取。

## Scraper 配置

每个 `.yml` 或 `.yaml` 文件定义一个 scraper：

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

支持的 fetcher：

- `rsshub`
- `direct_rss`

支持的 processor：

- `html_content`
- `llm_summary`
- `llm_keywords`
- `llm_tags`

YAML 中自定义的 LLM `base_url` / `api_base` 不会继承其他主机使用的
`OPENAI_API_KEY`。需要共用全局密钥时，同时设置 `OPENAI_BASE_URL`；独立
网关需在对应 processor 中提供自己的 `api_key`。

配置目录按内容指纹轮询。无效的新文件会被忽略；已加载文件出现无效修改时，
服务继续使用它的上一份有效配置。

## HTTP API

| Method | Path | 用途 |
| --- | --- | --- |
| GET | `/health` | 综合健康检查 |
| GET | `/health/liveness` | 存活检查 |
| GET | `/health/readiness` | 就绪检查 |
| POST | `/trigger_scraper` | 提交全部启用的 scraper |
| POST | `/trigger_upload` | 执行一批 PostgreSQL → Notion 同步 |
| GET | `/admin/config/status` | 配置状态 |
| POST | `/admin/config/refresh` | 立即刷新配置 |
| GET | `/admin/system/info` | 运行信息 |
| GET | `/admin/scrapers` | scraper 列表 |
| GET | `/admin/tasks/stats` | 任务统计 |
| GET | `/admin/tasks` | 任务列表 |
| GET | `/admin/tasks/{task_id}` | 任务详情 |
| GET | `/metrics` | Prometheus 指标 |

```bash
curl -X POST http://localhost:8001/trigger_scraper
curl -X POST http://localhost:8001/trigger_upload
```

## 本地开发

要求 Go 1.26.6、Docker 和可访问的 PostgreSQL。

```bash
go mod download
gofmt -w .
go vet ./...
go test ./...
go test -race ./...
go run ./cmd/octopus_service serve \
  --host 127.0.0.1 \
  --port 8000 \
  --scraper-config-dir resources/scrapers.d
```

构建镜像：

```bash
docker build -f dockerfiles/Dockerfile -t octopus-scraper:latest .
docker image inspect octopus-scraper:latest --format '{{.Size}}'
```

## 数据与故障恢复

PostgreSQL schema、Notion 租约和重试状态见
[`docs/storage.md`](docs/storage.md)。监控指标和 Vector 告警见
[`docs/monitoring.md`](docs/monitoring.md)。

升级前备份 PostgreSQL。Go 服务沿用 schema version `1`，可直接回滚到兼容该
schema 的旧镜像。切换镜像时只运行一个写入实例。
