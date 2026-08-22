# PostgreSQL 与 Notion 同步

PostgreSQL 保存处理后的权威内容。采集事务提交后，任务即为成功；Notion 的
状态不会改变采集结果。

## Schema version 2

服务启动时创建或迁移到 schema version `2`，并在 `schema_migrations` 中记录
版本。

| 表 | 职责 |
| --- | --- |
| `contents` | 内容正文、摘要、来源、关键词、标签和采集时间 |
| `export_targets` | 导出目标及启用状态 |
| `content_exports` | 每条内容在每个目标上的状态、重试和租约 |
| `schema_migrations` | 已应用的 schema 版本 |

version `1` 数据库会在启动时迁移到 version `2`。迁移把原有 Notion 状态复制到
`content_exports`，确认数量一致后再删除 `contents` 中的旧同步字段。

## 内容写入

一批内容在同一个 PostgreSQL 事务中完成：

1. 按 `content_id` 插入 `contents`，已存在的内容保持不变。
2. 为所有启用的 target 创建 `content_exports` 记录。
3. 提交事务。

任何一步失败都会回滚整批写入。事务提交后，后续 exporter 故障不会删除或回滚
内容。

启用一个新 target 时，服务会为已有内容补建 `pending` 导出记录。关闭 target
只会停止新的导出工作，不会删除内容。

## 导出状态

`content_exports.status` 使用以下状态：

| 状态 | 含义 |
| --- | --- |
| `pending` | 等待首次处理 |
| `processing` | 已被 worker 领取 |
| `retry` | 上次失败，等待下次执行时间 |
| `synced` | 已成功写入目标 |
| `failed` | 已达到最大尝试次数 |

worker 使用 `FOR UPDATE SKIP LOCKED` 领取到期记录，并写入 `claimed_by`、
`claimed_at` 和 `lease_expires_at`。多个服务实例可以并行工作，不会同时处理同一
target 的同一条内容。

交付过程中会续租。完成、失败和续租都要求记录仍由同一 worker 持有。租约过期
后，其他 worker 可以重新领取；原 worker 丢失租约时会取消正在进行的 writer。

失败记录使用递增延迟重试。达到 `NOTION_SYNC_MAX_ATTEMPTS` 后状态变为
`failed`。

## Notion

启用同步：

```env
NOTION_SYNC_ENABLED=true
NOTION_API_KEY=secret
NOTION_CONTENT_DATABASE_ID=database-id
NOTION_SYNC_INTERVAL_SECONDS=60
NOTION_SYNC_BATCH_SIZE=100
NOTION_SYNC_MAX_ATTEMPTS=10
NOTION_SYNC_LEASE_SECONDS=300
```

`POST /trigger_upload` 会立即运行一批同步。后台 worker 还会按
`NOTION_SYNC_INTERVAL_SECONDS` 定时执行。

设置 `NOTION_SYNC_ENABLED=false` 后，服务不会创建 Notion client，也不会调用
Notion API；内容仍会正常写入 PostgreSQL。

服务使用 Notion API version `2026-03-11`。目标 database 必须包含且只包含一个
data source。数量不符合要求时，首次同步会返回明确错误，不影响服务启动和
PostgreSQL 采集。

Notion 全量查询达到 10,000 条上限并返回 incomplete 状态时，去重逻辑会对候选
`content_id` 再执行精确查询，避免因截断结果创建重复页面。

## 任务结果 SQLite

任务历史与内容存储相互独立。默认路径为
`.octopus/task_results.sqlite3`，Compose 使用持久化 volume 中的
`/app/.octopus/task_results.sqlite3`。

服务启动时会把上次中断留下的 `pending`、`running` 和 `retrying` 记录标记为
`failed`。SQLite 文件无法打开、读取或修复时，服务会记录降级信息并继续使用
PostgreSQL 采集，只是不再持久化任务历史。

## 连接配置

`DATABASE_URL` 可以覆盖离散 PostgreSQL 设置。手写 URL 中的凭证需要进行
percent encoding。

`postgresql+psycopg://` 和 `postgresql+psycopg2://` 会自动转换为
`postgresql://`。SQLite URL 会被拒绝。

Docker Desktop 中，`host.docker.internal` 可以访问宿主机上的 PostgreSQL。
连接其他服务器时，将 `DB_HOST` 改为容器可访问的主机名或 IP。

## 升级与回滚

升级前备份外部 PostgreSQL。切换镜像时只运行一个写入实例，避免不同版本同时
执行迁移。

当前服务使用 schema version `2`。回滚镜像必须明确支持 version `2`，不能假设
旧镜像会忽略更高版本的数据库。
