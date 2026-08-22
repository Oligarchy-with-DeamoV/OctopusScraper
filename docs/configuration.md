# 配置参考

OctopusScraper 使用两类配置：

- 环境变量控制服务、数据库、任务、日志、Notion 和 MCP。
- `SCRAPER_CONFIG_DIR` 下的 YAML 文件定义采集源和内容处理器。

进程启动时会读取当前环境，并在仓库根目录存在 `.env` 时加载它。命令行参数
`--host`、`--port`、`--debug`、`--log-level`、`--log-format` 和
`--scraper-config-dir` 可以覆盖对应设置。

可复制的完整示例见 [`.env.example`](../.env.example) 和
[`resources/envs/deploy.prod.env`](../resources/envs/deploy.prod.env)。

## PostgreSQL

PostgreSQL 是权威存储。设置 `DATABASE_URL` 后，离散的 `POSTGRES_*` 和
`DB_*` 连接字段不再参与 URL 构造。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | 空 | 完整 PostgreSQL URL |
| `POSTGRES_DB` | `octopus` | 数据库名 |
| `POSTGRES_USER` | `octopus` | 用户名 |
| `POSTGRES_PASSWORD` | `octopus` | 密码，部署时应修改 |
| `DB_HOST` | `localhost` | 数据库主机，Compose 模板使用 `host.docker.internal` |
| `DB_PORT` | `5432` | 数据库端口 |
| `DB_POOL_SIZE` | `5` | 基础连接数 |
| `DB_MAX_OVERFLOW` | `5` | 额外连接数 |
| `DB_CONNECT_TIMEOUT_SECONDS` | `10` | 建立连接的超时时间 |

`DATABASE_URL` 支持 `postgres://` 和 `postgresql://`。旧 Python 部署使用的
`postgresql+psycopg://`、`postgresql+psycopg2://` 会被归一化。SQLite URL
会被拒绝。

## 服务与任务

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SERVICE_HOST` | `0.0.0.0` | HTTP 监听地址 |
| `SERVICE_PORT` | `8000` | 容器内服务端口 |
| `OCTOPUS_DEBUG` | `false` | 调试模式 |
| `ENVIRONMENT` | `development` | 环境名称，Compose 模板使用 `production` |
| `TASK_MANAGER_MAX_CONCURRENT` | `3` | 并发 worker 数 |
| `TASK_MANAGER_MAX_QUEUE_SIZE` | `1000` | 等待队列容量 |
| `RESULT_RETENTION_HOURS` | `48` | 任务结果保留时间 |
| `OCTOPUS_TASK_RESULT_PATH` | `.octopus/task_results.sqlite3` | 可选的任务历史 SQLite 文件 |
| `SCRAPER_TIMEOUT` | `10` | 单个采集任务超时，单位为秒 |
| `UPLOAD_TIMEOUT` | `15` | Notion HTTP client 超时输入，运行时下限为 30 秒 |
| `UPLOAD_MAX_RETRIES` | `3` | 兼容字段，当前仅在系统信息中显示 |

任务历史持久化不可用时，服务会记录降级信息并继续采集。

## Scraper 配置目录

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SCRAPER_CONFIG_DIR` | `resources/scrapers.d` | YAML 配置目录 |
| `SCRAPER_CONFIG_POLL_INTERVAL` | `1` | 目录轮询间隔，单位为秒 |
| `SCRAPER_CONFIG_DEBOUNCE_SECONDS` | `0.75` | 文件变化防抖时间 |

Compose 将宿主机的 `resources/scrapers.d` 只读挂载到容器内的
`/etc/octopus-scraper/scrapers.d`。

## 抓取与内容处理

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `RSSHUB_CONNECT_TIMEOUT` | `10` | RSSHub 连接超时，单位为秒 |
| `RSSHUB_READ_TIMEOUT` | `1200` | RSSHub 响应读取超时，单位为秒 |
| `OCTOPUS_SUMMARY_MAX_LENGTH` | `500` | feed 摘要的最大长度 |
| `OPENAI_API_KEY` | 空 | OpenAI 兼容处理器的全局密钥 |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | 全局 OpenAI 兼容地址 |
| `OPENAI_MODEL_NAME` | `gpt-3.5-turbo` | 全局默认模型 |

## Notion

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `NOTION_SYNC_ENABLED` | `false` | 是否启动 Notion exporter |
| `NOTION_API_KEY` | 空 | Notion integration token |
| `NOTION_CONTENT_DATABASE_ID` | 空 | 目标 database ID |
| `NOTION_SYNC_INTERVAL_SECONDS` | `60` | 自动同步间隔，单位为秒 |
| `NOTION_SYNC_BATCH_SIZE` | `100` | 每批最多处理的内容数 |
| `NOTION_SYNC_MAX_ATTEMPTS` | `10` | 单条内容的最大尝试次数 |
| `NOTION_SYNC_LEASE_SECONDS` | `300` | worker 租约时间，单位为秒 |
| `NOTION_UPLOAD_RETRY_DELAY` | `30` | Notion HTTP 重试间隔，单位为秒 |

目标 Notion database 必须包含且只包含一个 data source。同步失败不会回滚
PostgreSQL 中已经提交的内容。

## MCP

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MCP_ENABLED` | `false` | 是否注册 `POST /mcp` |
| `MCP_API_TOKEN` | 空 | Bearer token，启用 MCP 时必须设置 |

MCP 只提供读取工具。接口拒绝带 `Origin` 的浏览器请求，并限制并发查询和单次
响应大小。

## 日志

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | `DEBUG`、`INFO`、`WARNING`、`ERROR` 或 `CRITICAL` |
| `LOG_FORMAT` | `json` | 兼容旧配置；`plain` 和 `json` 最终都输出 JSON |
| `LOG_FILE` | 空 | 可选的日志文件路径 |
| `LOG_RETENTION_DAYS` | `14` | 文件日志保留天数，最高为 `365` |

详细日志和指标说明见 [日志与监控](monitoring.md)。

## Compose 辅助服务

以下变量由 Compose 中的 RSSHub 或 Vector 容器使用，不属于 Go 服务配置：

| 变量 | 用途 |
| --- | --- |
| `XUEQIU_TOKEN` | RSSHub 雪球路由凭证 |
| `FEISHU_WEBHOOK_URL` | Vector 飞书告警地址 |
| `VECTOR_LOG` | Vector 自身日志级别 |

## Scraper YAML

目录中的每个 `.yml` 或 `.yaml` 文件定义一个 scraper：

```yaml
id: my-feed
name: My Feed
enabled: true
fetcher: direct_rss
hub_root: https://example.com
route: /feed.xml
fetch_params:
  filter_time: 86400
priority: 5
content_processor_configs: {}
default_keywords:
  - feed
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `id` | 是 | 全局唯一 ID |
| `name` | 是 | 全局唯一名称 |
| `enabled` | 否 | 是否参与任务提交 |
| `fetcher` | 是 | `rsshub` 或 `direct_rss` |
| `hub_root` | 是 | RSSHub 根地址或 feed 站点根地址 |
| `route` | 是 | RSSHub 路由或 feed 路径 |
| `fetch_params` | 否 | 抓取参数 |
| `priority` | 否 | 任务优先级，值越大越早执行 |
| `content_processor_configs` | 否 | 按名称声明的处理器 |
| `default_keywords` | 否 | 写入每条内容的默认关键词 |

`rsshub` 会把 `fetch_params` 编码到请求查询参数中。`direct_rss` 支持
`filter_time`，值为向前保留内容的秒数。

YAML 使用严格校验：

- 每个文件只能包含一个 YAML 文档。
- 拒绝 alias、重复键、未知字段、无效 URL 和不支持的组件。
- `id` 和 `name` 必须跨文件唯一。
- 无效的新文件不会进入运行配置。
- 已接受文件出现无效修改时，服务继续使用该文件上一份有效配置。
- 配置变更只影响后续提交的任务。

## Processor

支持以下处理器：

| 名称 | 用途 |
| --- | --- |
| `html_content` | 获取原文、提取正文并转换为 Markdown |
| `llm_summary` | 生成摘要 |
| `llm_keywords` | 生成关键词 |
| `llm_tags` | 从标签集合或自定义分类中生成标签 |

数值较小的 `priority` 先执行。相同优先级保持 YAML 中的声明顺序。

HTML 处理器示例：

```yaml
content_processor_configs:
  html_content:
    priority: 10
    use_browser: false
    timeout_seconds: 30
```

设置 `browserless_url` 后可以通过远程 Browserless/CDP 渲染页面。服务镜像不包含
Chromium；Browserless 不可用时，处理器会回退到普通 HTTP 请求。

LLM 处理器示例：

```yaml
content_processor_configs:
  llm_summary:
    priority: 20
    model_name: gpt-4.1-mini
    max_summary_length: 300
    summary_style: concise
```

LLM 处理器支持 `model_name`、`max_tokens`、`temperature`、
`timeout_seconds`、`retry_times`、`api_key`、`base_url`、`fail_fast` 和
`enable_fallback` 等公共字段。

YAML 中选择了不同于 `OPENAI_BASE_URL` 的 `base_url` 或 `api_base` 时，不会
自动继承全局 `OPENAI_API_KEY`。独立网关应在处理器配置中提供自己的
`api_key`。
