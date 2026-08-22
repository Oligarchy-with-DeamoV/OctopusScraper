# 日志与监控

OctopusScraper 在 `GET /metrics` 暴露 Prometheus 指标。Docker Compose
会暴露该 endpoint，但不会启动 Prometheus server。

人工排查可以同时查看：

- `/admin/config/status`
- `/admin/system/info`
- `/admin/tasks/stats`

## 结构化日志

运行时日志始终为 JSON，并使用 `event` 保存消息文本。`LOG_FORMAT=plain` 只保留
旧部署兼容性，输出仍是 JSON。

日志默认写入 stdout。设置 `LOG_FILE` 后，同一份 JSON 会同时写入文件。文件按
100 MiB 和日期轮转，旧文件会压缩，并根据 `LOG_RETENTION_DAYS` 清理。

初始日志级别来自 `LOG_LEVEL`。运行时可以直接修改：

```bash
curl -X POST http://localhost:8001/admin/system/log-level \
  -H "Content-Type: application/json" \
  -d '{"level":"debug"}'
```

启动早期发生的 fatal error 也会输出 JSON，并满足 Vector 的 error filter。
稳定告警信号包括：

```json
{"event":"Task failed","level":"error"}
```

## Prometheus

外部 Prometheus 可以抓取：

```text
octopus-service:8000/metrics
```

从宿主机检查 Compose 端口：

```bash
curl http://localhost:8001/metrics
```

### 指标模型

- Counter：任务、重试、取消、配置刷新、上传结果和外部依赖操作。
- Gauge：启动时间、运行时间、队列、worker 使用量和配置健康状态。
- Histogram：任务耗时、抓取数量、上传批次和外部依赖耗时。

所有 label 都是有界集合。外部操作的 `dependency` 只使用 `rss`、`notion` 和
`llm`。上传结果使用 `processed` 和 `failed`。指标不会包含 task ID、URL、
database ID 或错误文本。

外部请求指标按高层操作计数。一轮 RSS 抓取、Notion 上传批次或 LLM 生成各计为
一次操作，不按内部 HTTP 重试次数重复计数。

### Grafana 查询

| 面板 | PromQL |
| --- | --- |
| 任务成功率 | `sum(rate(octopus_tasks_completed_total[5m])) / clamp_min(sum(rate(octopus_tasks_completed_total[5m]) + rate(octopus_tasks_failed_total[5m])), 0.001)` |
| 队列使用率 | `octopus_tasks_queued / clamp_min(octopus_task_queue_capacity, 1)` |
| Worker 使用率 | `octopus_tasks_running / clamp_min(octopus_task_worker_capacity, 1)` |
| 任务 p95 耗时 | `histogram_quantile(0.95, sum by (le) (rate(octopus_task_duration_seconds_bucket[15m])))` |
| RSS p95 耗时 | `histogram_quantile(0.95, sum by (le) (rate(octopus_external_request_duration_seconds_bucket{dependency="rss"}[15m])))` |
| 依赖失败率 | `sum by (dependency) (rate(octopus_external_request_failures_total[5m]))` |
| 配置健康状态 | `octopus_config_healthy` |
| 最近成功配置刷新的间隔 | `time() - octopus_config_last_success_timestamp_seconds` |

## Vector 告警

Compose 中的 `vector-alert` 读取 Docker 容器日志，并通过
`FEISHU_WEBHOOK_URL` 发送飞书告警。当前过滤器关注：

- RSSHub 的 error 日志。
- OctopusScraper 的 `"Task failed"` error 或 critical 事件。
- logger 初始化前的 fatal error。

修改 `vector.toml` 后应运行 Vector 配置校验。

## 检查

```bash
docker compose config
curl http://localhost:8001/metrics
curl http://localhost:8001/admin/system/info
```
