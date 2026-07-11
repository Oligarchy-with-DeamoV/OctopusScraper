# Prometheus monitoring

OctopusScraper exposes Prometheus metrics at `GET /metrics`. The existing
`GET /admin/monitoring/metrics` JSON response remains available for manual
diagnostics.

The Docker Compose stack includes Prometheus with the scrape configuration in
`prometheus/prometheus.yml` and alert rules in `prometheus/alerts.yml`.
Prometheus evaluates the rules, while the existing Vector service continues to
deliver Feishu alerts during the migration observation period.

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
retry. A Notion upload batch, configuration refresh, RSS fetch, or LLM
generation is one operation.

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
docker run --rm \
  --entrypoint /bin/promtool \
  -v "$PWD/prometheus:/etc/prometheus:ro" \
  prom/prometheus:v3.5.0 \
  check config /etc/prometheus/prometheus.yml
```

Alert delivery must remain on Vector until Prometheus rules have been observed
in production and an Alertmanager receiver provides equivalent Feishu
delivery.
