# HTTP API 与 MCP

Docker Compose 默认将服务映射到 `http://localhost:8001`。Go 服务本身默认监听
`0.0.0.0:8000`。

除 MCP 外，当前 HTTP 接口没有内置身份认证。生产部署应放在受信网络中，或通过
反向代理增加访问控制。

## 采集与同步

| Method | Path | 用途 |
| --- | --- | --- |
| `POST` | `/trigger_scraper` | 为当前全部启用的 scraper 提交一批任务 |
| `POST` | `/trigger_upload` | 立即执行一批 PostgreSQL 到导出目标的同步 |

```bash
curl -X POST http://localhost:8001/trigger_scraper
curl -X POST http://localhost:8001/trigger_upload
```

任务提交受队列容量限制。当前批次无法完整进入队列时，请求会返回错误，不会静默
丢弃部分 scraper。

## 健康检查

| Method | Path | 用途 |
| --- | --- | --- |
| `GET` | `/health` | 配置、PostgreSQL 和同步状态的综合检查 |
| `GET` | `/health/liveness` | 仅检查进程是否存活 |
| `GET` | `/health/readiness` | 检查配置和 PostgreSQL 是否可以接收任务 |

`/health` 默认缓存 30 秒。排查实时状态时可以绕过缓存：

```bash
curl "http://localhost:8001/health?cache=false"
```

## 管理接口

| Method | Path | 用途 |
| --- | --- | --- |
| `GET` | `/admin/config/status` | 当前配置版本、scraper 和文件错误 |
| `POST` | `/admin/config/refresh` | 立即扫描并应用配置目录 |
| `GET` | `/admin/system/info` | 版本、运行时间、配置和任务统计 |
| `POST` | `/admin/system/log-level` | 运行时修改日志级别 |
| `GET` | `/admin/scrapers` | 全部 scraper 及其运行信息 |
| `GET` | `/admin/tasks/stats` | 队列、worker 和任务统计 |
| `GET` | `/admin/tasks` | 查询任务结果 |
| `GET` | `/admin/tasks/{task_id}` | 查询单个任务 |

修改日志级别：

```bash
curl -X POST http://localhost:8001/admin/system/log-level \
  -H "Content-Type: application/json" \
  -d '{"level":"debug"}'
```

任务列表默认返回 50 条，最多返回 200 条。可以使用 `status` 和 `limit`：

```bash
curl "http://localhost:8001/admin/tasks?status=failed&limit=20"
```

任务状态包括 `pending`、`running`、`completed`、`failed`、`cancelled` 和
`retrying`。

## Prometheus

| Method | Path | 用途 |
| --- | --- | --- |
| `GET` | `/metrics` | Prometheus 文本格式指标 |

指标和 Grafana 查询见 [日志与监控](monitoring.md)。

## MCP

`POST /mcp` 仅在以下配置同时满足时注册：

```env
MCP_ENABLED=true
MCP_API_TOKEN=replace-with-a-strong-token
```

客户端必须发送 Bearer token：

```http
Authorization: Bearer <token>
```

MCP endpoint 是无状态、只读的 JSON 响应接口，提供两个工具：

| 工具 | 用途 |
| --- | --- |
| `list_contents` | 按 scraper、标签和采集时间分页查询内容元数据 |
| `get_content` | 按 `content_id` 分段读取正文 |

`list_contents` 默认返回 20 条，最多返回 50 条。`get_content` 默认返回
20,000 个字符，单次最多返回 50,000 个字符。接口拒绝带 `Origin` header 的
浏览器请求。单个查询默认最多执行 5 秒，同时最多处理 4 个查询；服务停机时会
取消进行中的查询。
