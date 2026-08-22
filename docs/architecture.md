# 系统架构

OctopusScraper 的运行边界是信息采集和持久化。PostgreSQL 保存权威内容，
Notion、MCP 和其他消费者都位于持久化之后。

## 系统上下文

```text
                                  +----------------------+
                                  | Scraper YAML files   |
                                  +----------+-----------+
                                             |
                                             v
+-----------+       +------------+     +--------------+
| Scheduler | ----> | HTTP API   | --> | Task Manager |
+-----------+       +------------+     +------+-------+
                         |                     |
                         |                     v
                         |              +-------------+
                         |              | Executor    |
                         |              +------+------+
                         |                     |
                         |        +------------+-------------+
                         |        |                          |
                         |        v                          v
                         |   +---------+              +-------------+
                         |   | Fetcher | -----------> | Processors  |
                         |   +---------+              +------+------+
                         |                                  |
                         v                                  v
                   +-------------+                    +------------+
                   | Admin / MCP | <----------------> | PostgreSQL |
                   +-------------+                    +-----+------+
                                                              |
                                                              v
                                                       +-------------+
                                                       | Exporter    |
                                                       +------+------+
                                                              |
                                                              v
                                                          +--------+
                                                          | Notion |
                                                          +--------+
```

Prometheus 指标和结构化日志覆盖配置、抓取、处理、存储、导出和 HTTP 请求。

## 进程启动

`cmd/octopus_service` 解析命令后进入 `internal/bootstrap.Run`。启动顺序如下：

1. 加载 `.env`、环境变量和命令行覆盖项。
2. 创建动态日志级别控制器和 Prometheus registry。
3. 读取 scraper 配置目录，执行 YAML 严格校验和组件可构造性校验。
4. 连接 PostgreSQL，初始化或迁移到 schema version `2`。
5. 创建 fetcher factory、processor registry 和采集 executor。
6. 创建有界任务队列、worker 和可选的 SQLite 任务结果存储。
7. 根据配置注册 Notion exporter，并启动定时同步 worker。
8. 启动 scraper 配置 watcher 和 HTTP server。
9. 在启用 MCP 时，将只读 handler 注册到 `/mcp`。

初始 scraper 配置或 PostgreSQL 初始化失败会阻止服务启动。任务历史 SQLite
不可用时，服务会禁用历史持久化并继续运行。

## 采集链路

`POST /trigger_scraper` 会读取当前已接受且启用的 scraper，创建一个批次并提交到
Task Manager：

```text
accepted config snapshot
        |
        v
bounded priority queue
        |
        v
fetch RSS/Atom
        |
        v
quality filter and content_id deduplication
        |
        v
skip IDs already stored in PostgreSQL
        |
        v
ordered processor pipeline
        |
        v
PostgreSQL transaction
```

任务按优先级从高到低执行，相同优先级按提交顺序执行。队列和 worker 数量均有
上限。批量提交前会检查剩余容量，容量不足时整批返回错误。

每个 worker 为任务创建独立 deadline。失败任务使用有界重试；服务停机后不再
接收新任务，等待中的任务会被取消，运行中的任务会在停机期限内继续执行。

### Fetcher

`internal/fetcher` 提供两个实现：

- `rsshub`：把 `hub_root`、`route` 和 `fetch_params` 组合为 RSSHub 请求。
- `direct_rss`：直接读取 RSS/Atom，并可用 `filter_time` 过滤较早内容。

响应体有大小上限，网络连接和读取都有超时。Feed 被统一转换为
`content.Content`，缺少 ID、标题、链接或正文信息的条目会被过滤，同一批次的
重复 `content_id` 也会被移除。

### Processor

`internal/processor.Registry` 负责构造处理器：

- `html_content`
- `llm_summary`
- `llm_keywords`
- `llm_tags`

处理器按照数字优先级从小到大执行，相同优先级保留 YAML 声明顺序。
`html_content` 可以通过远程 Browserless/CDP 渲染页面，也可以直接使用 HTTP
获取正文。Browserless 失败时会回退到 HTTP，服务镜像不包含 Chromium。

OpenAI 兼容处理器通过注入的 HTTP client 工作。scraper 选择了不同 LLM 地址
时，必须显式提供该地址对应的密钥，避免跨服务复用全局凭证。

### 写入成功边界

Executor 在运行 processor 前查询 PostgreSQL 中已存在的 `content_id`。处理后的
新内容在一个事务中写入 `contents`，并为所有启用的导出目标创建
`content_exports` 状态。

事务提交后，采集任务即为成功。Notion 的状态和可用性不参与这个成功判断。

## 配置热更新

`internal/config.ConfigManager` 定期扫描配置目录，计算文件和配置内容指纹：

1. 文件变化先经过防抖时间。
2. 每个文件独立解析，合法内容形成候选快照。
3. 候选快照经过 fetcher 和 processor 构造校验。
4. 校验通过后原子替换当前快照。
5. 校验失败时恢复替换前的状态，并记录文件错误。

已接受文件出现无效修改时，该路径继续使用上一份有效配置。只有路径变化的重命名
会先转移已有的有效快照。配置字段顺序影响 processor 和自定义分类行为，因此
顺序也参与内容指纹和差异判断。

配置更新不会取消已经提交的任务。新快照只影响更新后创建的任务。

## Task Manager

`internal/task.Manager` 同时维护：

- 有界优先级队列。
- 固定数量的 worker。
- 运行中任务的取消函数。
- 有界重试 timer。
- 内存任务结果。
- 可选的 SQLite 任务历史。

服务启动时会读取保留期内的任务历史。上次进程留下的 `pending`、`running` 或
`retrying` 记录会被标记为 `failed`，避免管理接口展示已经不存在的工作。

SQLite 只保存任务观察数据，不保存采集内容。PostgreSQL 仍是内容的权威存储。

## PostgreSQL 与 exporter

schema version `2` 将内容和导出状态分开：

```text
contents
    |
    +---- content_exports ---- export_targets
```

`contents` 保存处理后的内容。`export_targets` 保存目标是否启用。
`content_exports` 以 `(content_id, exporter_id)` 为主键，保存状态、尝试次数、
错误、下次执行时间和租约。

每个 exporter 拥有独立 worker。worker 使用 PostgreSQL
`FOR UPDATE SKIP LOCKED` 领取到期记录，并在交付过程中维持租约。完成、失败和
续租操作都要求 worker 仍持有同一 claim。租约丢失后，当前 writer 会被取消，
记录等待其他 worker 重新领取。

当前实现注册了 Notion target。导出管理器按 target 隔离，后续目标可以复用同一
状态模型，不需要修改 `contents`。

更完整的状态和恢复说明见 [PostgreSQL 与 Notion 同步](storage.md)。

## HTTP、MCP 与调度

`internal/httpapi` 使用标准库 `http.ServeMux` 暴露触发、健康检查、管理和指标
接口。HTTP handler 只负责协议转换，任务执行和持久化由 Runtime、Task Manager
和 Store 完成。

Compose 中的 scheduler 使用 cron 调用 HTTP trigger。它不读取 scraper 配置，
也不直接访问数据库。

MCP handler 是可选的只读入口。它直接读取 PostgreSQL 中的权威内容，使用
Bearer token、查询 timeout、并发上限、keyset pagination 和正文分段限制请求
成本。

## Docker Compose 拓扑

| 服务 | 职责 |
| --- | --- |
| `octopus-service` | Go 服务、HTTP API、任务执行和 exporter |
| `task-results-init` | 准备 SQLite volume 权限 |
| `scheduler` | 通过 cron 调用 trigger |
| `rsshub` | 提供 RSSHub 路由 |
| `redis` | RSSHub 缓存 |
| `vector-alert` | 收集容器错误日志并发送飞书告警 |

PostgreSQL 由 Compose 外部提供。Browserless 也是可选的远程服务。

## 故障边界

| 故障 | 行为 |
| --- | --- |
| PostgreSQL 初始化失败 | 服务启动失败 |
| PostgreSQL 写入失败 | 当前采集任务失败 |
| Notion 不可用 | PostgreSQL 内容保留，导出状态进入重试或失败 |
| 新 scraper 文件无效 | 文件被忽略并记录错误 |
| 已接受 scraper 修改无效 | 继续使用该文件上一份有效配置 |
| 任务队列已满 | 新批次被拒绝 |
| 任务历史 SQLite 不可用 | 禁用历史持久化，采集继续 |
| Browserless 不可用 | HTML 处理器回退到普通 HTTP |

## 优雅停机

收到 `SIGINT` 或 `SIGTERM` 后：

1. 取消配置 watcher、定时 exporter 和其他运行时后台工作。
2. HTTP server 停止接收新请求，最多等待 30 秒完成当前请求。
3. exporter 和 Task Manager 并行停止。
4. 等待中的采集任务被取消，运行中的任务在 deadline 内排空。
5. exporter 与 Task Manager 都完整停止后关闭 PostgreSQL。

如果运行时组件未能在期限内停止，服务返回明确错误，不会把不完整停机报告为成功。

## 代码目录

| 目录 | 职责 |
| --- | --- |
| `cmd/octopus_service` | 服务和容器 healthcheck 入口 |
| `internal/bootstrap` | 依赖构建、进程启动和停机 |
| `internal/config` | 环境变量、严格 YAML 和热更新 |
| `internal/fetcher` | RSSHub 与直接 RSS/Atom 获取 |
| `internal/processor` | HTML 与 LLM processor |
| `internal/task` | 队列、worker、重试和任务结果 |
| `internal/storage` | PostgreSQL 内容与导出状态 |
| `internal/exporter` | target worker、租约和重试 |
| `internal/exporter/notion` | Notion REST client 和 block 转换 |
| `internal/httpapi` | HTTP API |
| `internal/mcpapi` | 只读 MCP API |
| `internal/observability` | 日志和 Prometheus 指标 |
| `contracts` | 跨语言兼容 fixture |
