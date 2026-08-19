# Prometheus monitoring

OctopusScraper exposes Prometheus metrics at `GET /metrics`. This endpoint
replaces the removed `GET /admin/monitoring/metrics` JSON snapshot. Use the
remaining `/admin/config/status`, `/admin/system/info`, and `/admin/tasks/stats`
endpoints for human diagnostics.

The Docker Compose stack exposes the endpoint but does not bundle a Prometheus
server. Configure an external Prometheus instance to scrape
`octopus-service:<SERVICE_PORT>/metrics` (`8000` by default). Vector continues
to deliver Feishu alerts from container error logs, including fatal startup
errors emitted before the normal logger is initialized.

Runtime logs are JSON-only and use `event` for the message field, so the
existing Vector filter continues to match `{"event":"Task failed","level":"error"}`
and `critical` variants. `LOG_FILE` is optional; when set, the same JSON lines
are written to stdout and to the file, with 100 MiB plus daily rotation,
compressed archives, and `LOG_RETENTION_DAYS` cleanup.

The initial level comes from `LOG_LEVEL`. Use `POST /admin/system/log-level`
with a JSON body such as `{"level":"debug"}` to adjust the injected logger at
runtime without rebuilding it.

## Metric model

- Counters: task attempts, retries, cancellations, configuration refreshes,
  upload outcomes, and external dependency operations.
- Gauges: service start time and uptime, queue and worker usage, and
  configuration health.
- Histograms: task duration, fetched item count, upload batch size, and
  dependency operation duration.

Only bounded labels are used. External operations use `dependency` with the
fixed values `rss`, `notion`, and `llm`; upload outcomes use `processed` and
`failed`. Metrics never include task IDs, URLs, database IDs, or error text.

External request metrics count high-level operations rather than every HTTP
retry. An RSS fetch, Notion upload batch, or LLM generation is one external
operation. Configuration refreshes use the dedicated configuration metrics.

## Grafana queries

| Panel | PromQL |
| --- | --- |
| Task success rate | `sum(rate(octopus_tasks_completed_total[5m])) / clamp_min(sum(rate(octopus_tasks_completed_total[5m]) + rate(octopus_tasks_failed_total[5m])), 0.001)` |
| Queue utilization | `octopus_tasks_queued / clamp_min(octopus_task_queue_capacity, 1)` |
| Worker utilization | `octopus_tasks_running / clamp_min(octopus_task_worker_capacity, 1)` |
| Task p95 duration | `histogram_quantile(0.95, sum by (le) (rate(octopus_task_duration_seconds_bucket[15m])))` |
| RSS p95 duration | `histogram_quantile(0.95, sum by (le) (rate(octopus_external_request_duration_seconds_bucket{dependency="rss"}[15m])))` |
| Dependency failure rate | `sum by (dependency) (rate(octopus_external_request_failures_total[5m]))` |
| Configuration health | `octopus_config_healthy` |
| Last successful configuration refresh age | `time() - octopus_config_last_success_timestamp_seconds` |

## Validation

```bash
curl http://localhost:8001/metrics
docker compose config
```
