# PostgreSQL 与导出状态

PostgreSQL 保存处理后的权威内容。采集事务提交后，任务即为成功；Notion 或其他
导出目标的状态不会改变采集结果。

## Schema version 3

服务启动时创建或迁移到 schema version `3`，并在 `schema_migrations` 中记录
版本。迁移在 PostgreSQL advisory lock 和单个事务内执行；高于当前版本的数据库
会被拒绝。

| 表 | 职责 |
| --- | --- |
| `contents` | 权威正文、原始发布时间、规范化发布时间、主来源和采集时间 |
| `content_sources` | 内容与 scraper 的多来源关系及首次、最近观测时间 |
| `export_targets` | 具体导出目的地、类型、指纹和启用状态 |
| `content_exports` | 每条内容在每个目的地上的状态、重试和租约 |
| `schema_migrations` | 已应用的 schema 版本 |

version `1` 数据库会依次迁移到 version `2` 和 version `3`。version `2` 到
version `3` 的迁移包括：

- 先按字符串数组解码并规范化旧 `keywords_json` 和 `tags_json`，再转为带字符串
  元素数组约束的 `JSONB`。旧 `null` 归一化为空数组，PostgreSQL JSONB 不支持的
  NUL 字符替换为 Unicode replacement character。
- 保留原始 `published`，并把可解析值写入 UTC `published_at`；无效旧值保留原文，
  `published_at` 为 `NULL`。
- 将 `created_at` 改名为 `collected_at`，删除 `contents.updated_at`。
- 为已有 `scraper_name` 生成临时稳定 ID，并建立 `content_sources`。
- 将 exporter 标识迁移为具体 target 标识，并为旧 target 保留历史指纹。
- 增加状态、尝试次数、租约字段一致性约束和查询索引。

## 权威内容与来源

`contents.content_id` 仍是全局去重键。已存在的权威内容不会因再次抓取或被另一个
scraper 发现而重写、重新处理。

scraper YAML 中的 `id` 是持久化来源身份，`name` 是展示名称。每个通过质量过滤的
抓取结果都会形成一条来源观测：

```text
scraper id
    |
    v
content_sources ----> contents
 (content_id, scraper_id)
```

新内容经过 processor 后，与来源观测一起写入事务。已存在的 `content_id` 跳过
processor，但仍更新对应来源的 `last_seen_at`。同一内容可关联多个 scraper，不会
丢失后续发现它的来源。乱序完成的任务分别以最早观测更新 `first_seen_at`、以
最新观测更新 `last_seen_at` 和展示名称。

`scraper_name` 保留对应内容最近一次来源观测时的展示名称。scraper 改名后，只在
后续再次观测到的内容上更新名称；需要查询该来源全部历史内容时应使用稳定的
`scraper_id`。

从 version `2` 迁移的来源使用 `legacy:<hash>` ID。真实 scraper 后续以相同名称
观察到该内容时，主来源会提升为 YAML 中的稳定 `id`，对应临时关联会被移除。

`published` 保存 feed 原文，`published_at` 保存可解析的规范化时间。
`collected_at` 表示首次写入 PostgreSQL 的时间。
新写入的 keyword 和 tag 也会在编码为 JSONB 前把 NUL 替换为 Unicode
replacement character，避免单个值使整批采集事务失败。

内容查询使用以下索引：

- `(collected_at DESC, content_id DESC)` 支持 keyset pagination。
- `tags_json` 的 GIN 索引支持标签过滤。
- `(scraper_id, content_id)` 支持来源过滤。
- `(scraper_name, content_id)` 支持按展示名称过滤。

## 内容写入

一批内容在同一个 PostgreSQL 事务中完成：

1. 按 `content_id` 插入尚不存在的 `contents`。
2. 插入或更新本批次的 `content_sources`。
3. 为新内容和所有启用的 target 创建 `content_exports`。
4. 提交事务。

任何一步失败都会回滚整批写入。事务提交后，后续 exporter 故障不会删除或回滚
内容。

## 导出目标身份

`export_targets` 的一行代表一个具体目的地，不只代表 exporter 类型。Notion
target 由规范化 database ID 的 SHA-256 指纹生成：

- `kind` 为 `notion`。
- `target_id` 使用 `notion:<短指纹>`。
- `destination_fingerprint` 保存完整指纹。

database ID 中的大小写、连字符和首尾空白不会改变 target 身份。改用另一个
Notion database 会创建新 target，并为全部历史内容补建 `pending` 记录。旧 target
被禁用，其导出历史保留。

启动时会将数据库中的 target 与当前配置进行事务化对账。未配置的 target 只会被
禁用，不会删除内容或已有导出状态。禁用后不能领取新工作，也不能续租已有工作。
关闭 Notion 同步时，所有现有 target 都会被禁用。

target 对账表达的是共享 PostgreSQL 集群的全局期望状态。连接同一数据库的所有
服务实例必须使用相同的 Notion 启用状态和 database ID；配置不一致时，最后一次
启动的实例会成为数据库中的当前 target 集合。

schema version `2` 没有保存 Notion database 指纹，因此首次升级到 version `3`
时无法证明旧 target 与当前配置指向同一目的地。服务会采用安全默认值，把当前
目的地视为新 target 并重新校验全部历史内容；若目的地未改变，Notion 精确去重会
避免重复页面，但升级后会出现一次完整同步积压。

target 对账与内容写入使用 PostgreSQL 事务级共享/排他锁协调。多实例并发时，
内容写入要么先提交并被对账回填，要么在对账提交后读取新的启用 target，不会漏建
`content_exports`。历史全量回填只在 target 首次创建或从禁用状态重新启用时
执行；配置未变化的普通重启不会重复扫描全部内容。

## 导出状态

`content_exports.status` 使用以下状态：

| 状态 | 含义 |
| --- | --- |
| `pending` | 等待首次处理 |
| `processing` | 已被 worker 领取 |
| `retry` | 上次失败，等待下次执行时间 |
| `synced` | 已成功写入目标 |
| `failed` | 已达到最大尝试次数 |

数据库约束只允许这些状态，`attempts` 不能为负数。`processing` 必须同时带有
`claimed_by`、`claimed_at` 和 `lease_expires_at`；其他状态必须清空这三个字段。

worker 使用 `FOR UPDATE SKIP LOCKED` 领取到期记录。待处理和重试记录、过期租约
分别使用与领取条件一致的 partial index。多个服务实例可以并行工作，不会同时
处理同一 target 的同一条内容。

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

target 身份以配置的 database ID 为准。若在同一 database 内删除并重建 data
source 或历史页面，已标记为 `synced` 的记录不会自动重新入队；这类破坏性重建应
使用新的 database ID。

Notion 全量查询达到 10,000 条上限并返回 incomplete 状态时，去重逻辑会对候选
`content_id` 再执行精确查询，避免因截断结果创建重复页面。

## 任务结果 SQLite

任务历史与内容存储相互独立。默认路径为
`.octopus/task_results.sqlite3`，Compose 使用持久化 volume 中的
`/app/.octopus/task_results.sqlite3`。

SQLite schema 使用 `PRAGMA user_version = 1`。时间统一保存为固定宽度 UTC
RFC 3339 Nano 文本，保证字符串排序与时间顺序一致。状态和计数字段带约束，
保留期查询使用 `start_time` 和非空 `end_time` 索引。

旧的未版本化数据库会在事务内读取、校验和规范化，再替换为 version `1` 表。
不支持的状态、无效时间或违反约束的旧记录会使迁移回滚。高于当前版本的 SQLite
文件会被拒绝。旧格式时间不包含时区，迁移沿用服务原有的本地时区解释；迁移进程
应使用旧服务相同的 `TZ`。

服务启动时会分批把上次中断留下的 `pending`、`running` 和 `retrying` 记录标记
为 `failed`。SQLite 打开、迁移、恢复和保留期内历史读取共享 30 秒预算，并响应
服务启动上下文的取消。每个恢复批次独立提交，后续批次超时或包含坏记录时不会
回滚已完成的恢复。SQLite 文件无法打开、读取、迁移、恢复或在限时内完成时，服务
会记录降级信息并继续使用 PostgreSQL 采集，只是不再持久化任务历史。

## 连接配置

`DATABASE_URL` 可以覆盖离散 PostgreSQL 设置。手写 URL 中的凭证需要进行
percent encoding。

`postgresql+psycopg://` 和 `postgresql+psycopg2://` 会自动转换为
`postgresql://`。SQLite URL 会被拒绝。

Docker Desktop 中，`host.docker.internal` 可以访问宿主机上的 PostgreSQL。
连接其他服务器时，将 `DB_HOST` 改为容器可访问的主机名或 IP。

## 升级与回滚

升级前备份外部 PostgreSQL，并安排维护窗口。version `2` 到 version `3` 的
JSONB 转换、约束校验、时间回填和索引创建在一个事务内执行；迁移期间相关表会
持有阻塞读写的锁，耗时随历史数据量增长。迁移本身会串行执行，但切换镜像时仍应
只运行一个应用版本，避免 version `2` 和 version `3` 进程并行写入。

当前服务使用 schema version `3`，没有自动 down migration。回滚到只支持
version `2` 的镜像时，必须恢复升级前备份；旧镜像会拒绝 version `3` 数据库。
