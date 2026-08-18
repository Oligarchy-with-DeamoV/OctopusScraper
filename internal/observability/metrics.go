package observability

import (
	"fmt"
	"net/http"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/task"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

var _ task.Observer = (*Metrics)(nil)

type Metrics struct {
	registry          *prometheus.Registry
	startedAt         time.Time
	buildInfo         *prometheus.GaugeVec
	serviceStart      prometheus.Gauge
	serviceUptime     prometheus.Gauge
	tasksSubmitted    prometheus.Counter
	tasksCompleted    prometheus.Counter
	tasksFailed       prometheus.Counter
	taskRetries       prometheus.Counter
	tasksCancelled    prometheus.Counter
	tasksRunning      prometheus.Gauge
	tasksQueued       prometheus.Gauge
	queueCapacity     prometheus.Gauge
	workerCapacity    prometheus.Gauge
	taskDuration      prometheus.Histogram
	taskItemsFetched  prometheus.Histogram
	uploadItems       *prometheus.CounterVec
	uploadBatch       prometheus.Histogram
	configHealthy     prometheus.Gauge
	configSuccesses   prometheus.Counter
	configFailures    prometheus.Counter
	configLastSuccess prometheus.Gauge
	externalRequests  *prometheus.CounterVec
	externalFailures  *prometheus.CounterVec
	externalDuration  *prometheus.HistogramVec
}

func NewMetrics(version string) *Metrics {
	registry := prometheus.NewRegistry()
	metrics := &Metrics{
		registry:  registry,
		startedAt: time.Now(),
		buildInfo: prometheus.NewGaugeVec(prometheus.GaugeOpts{
			Name: "octopus_build_info",
			Help: "OctopusScraper build information.",
		}, []string{"version"}),
		serviceStart: prometheus.NewGauge(prometheus.GaugeOpts{
			Name: "octopus_service_start_time_seconds",
			Help: "Unix timestamp when the service process started.",
		}),
		serviceUptime: prometheus.NewGauge(prometheus.GaugeOpts{
			Name: "octopus_service_uptime_seconds",
			Help: "Service process uptime in seconds.",
		}),
		tasksSubmitted: prometheus.NewCounter(prometheus.CounterOpts{
			Name: "octopus_tasks_submitted_total",
			Help: "Task attempts accepted by the task manager.",
		}),
		tasksCompleted: prometheus.NewCounter(prometheus.CounterOpts{
			Name: "octopus_tasks_completed_total",
			Help: "Task attempts completed successfully.",
		}),
		tasksFailed: prometheus.NewCounter(prometheus.CounterOpts{
			Name: "octopus_tasks_failed_total",
			Help: "Task attempts that failed.",
		}),
		taskRetries: prometheus.NewCounter(prometheus.CounterOpts{
			Name: "octopus_task_retries_total",
			Help: "Retry task attempts successfully re-enqueued.",
		}),
		tasksCancelled: prometheus.NewCounter(prometheus.CounterOpts{
			Name: "octopus_tasks_cancelled_total",
			Help: "Task attempts cancelled before completion.",
		}),
		tasksRunning: prometheus.NewGauge(prometheus.GaugeOpts{
			Name: "octopus_tasks_running",
			Help: "Task attempts currently running.",
		}),
		tasksQueued: prometheus.NewGauge(prometheus.GaugeOpts{
			Name: "octopus_tasks_queued",
			Help: "Task attempts currently waiting in the queue.",
		}),
		queueCapacity: prometheus.NewGauge(prometheus.GaugeOpts{
			Name: "octopus_task_queue_capacity",
			Help: "Maximum number of queued task attempts.",
		}),
		workerCapacity: prometheus.NewGauge(prometheus.GaugeOpts{
			Name: "octopus_task_worker_capacity",
			Help: "Maximum number of concurrent task workers.",
		}),
		taskDuration: prometheus.NewHistogram(prometheus.HistogramOpts{
			Name:    "octopus_task_duration_seconds",
			Help:    "Task attempt execution duration.",
			Buckets: []float64{1, 5, 15, 30, 60, 120, 300, 600, 1200, 2400},
		}),
		taskItemsFetched: prometheus.NewHistogram(prometheus.HistogramOpts{
			Name:    "octopus_task_items_fetched",
			Help:    "Items fetched by a completed task attempt.",
			Buckets: []float64{0, 1, 5, 10, 25, 50, 100, 250, 500, 1000},
		}),
		uploadItems: prometheus.NewCounterVec(prometheus.CounterOpts{
			Name: "octopus_upload_items_total",
			Help: "Items processed by upload operations.",
		}, []string{"outcome"}),
		uploadBatch: prometheus.NewHistogram(prometheus.HistogramOpts{
			Name:    "octopus_upload_batch_items",
			Help:    "Items included in an upload operation.",
			Buckets: []float64{0, 1, 5, 10, 25, 50, 100, 250, 500, 1000},
		}),
		configHealthy: prometheus.NewGauge(prometheus.GaugeOpts{
			Name: "octopus_config_healthy",
			Help: "Whether the current scraper configuration is healthy.",
		}),
		configSuccesses: prometheus.NewCounter(prometheus.CounterOpts{
			Name: "octopus_config_refresh_success_total",
			Help: "Successful configuration load or refresh operations.",
		}),
		configFailures: prometheus.NewCounter(prometheus.CounterOpts{
			Name: "octopus_config_refresh_failure_total",
			Help: "Failed configuration load or refresh operations.",
		}),
		configLastSuccess: prometheus.NewGauge(prometheus.GaugeOpts{
			Name: "octopus_config_last_success_timestamp_seconds",
			Help: "Unix timestamp of the last successful configuration load or refresh.",
		}),
		externalRequests: prometheus.NewCounterVec(prometheus.CounterOpts{
			Name: "octopus_external_requests_total",
			Help: "External dependency operations.",
		}, []string{"dependency"}),
		externalFailures: prometheus.NewCounterVec(prometheus.CounterOpts{
			Name: "octopus_external_request_failures_total",
			Help: "Failed external dependency operations.",
		}, []string{"dependency"}),
		externalDuration: prometheus.NewHistogramVec(prometheus.HistogramOpts{
			Name:    "octopus_external_request_duration_seconds",
			Help:    "External dependency operation duration.",
			Buckets: []float64{0.1, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 1200},
		}, []string{"dependency"}),
	}
	registry.MustRegister(
		metrics.buildInfo,
		metrics.serviceStart,
		metrics.serviceUptime,
		metrics.tasksSubmitted,
		metrics.tasksCompleted,
		metrics.tasksFailed,
		metrics.taskRetries,
		metrics.tasksCancelled,
		metrics.tasksRunning,
		metrics.tasksQueued,
		metrics.queueCapacity,
		metrics.workerCapacity,
		metrics.taskDuration,
		metrics.taskItemsFetched,
		metrics.uploadItems,
		metrics.uploadBatch,
		metrics.configHealthy,
		metrics.configSuccesses,
		metrics.configFailures,
		metrics.configLastSuccess,
		metrics.externalRequests,
		metrics.externalFailures,
		metrics.externalDuration,
	)
	metrics.buildInfo.WithLabelValues(version).Set(1)
	metrics.serviceStart.Set(float64(metrics.startedAt.Unix()))
	return metrics
}

func (m *Metrics) Handler() http.Handler {
	handler := promhttp.HandlerFor(m.registry, promhttp.HandlerOpts{})
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		m.RefreshUptime()
		handler.ServeHTTP(writer, request)
	})
}

func (m *Metrics) RefreshUptime() {
	m.serviceUptime.Set(time.Since(m.startedAt).Seconds())
}

func (m *Metrics) Configure(queueCapacity, workerCapacity int) {
	m.queueCapacity.Set(float64(queueCapacity))
	m.workerCapacity.Set(float64(workerCapacity))
}

func (m *Metrics) Submitted() { m.tasksSubmitted.Inc() }
func (m *Metrics) Retried()   { m.taskRetries.Inc() }
func (m *Metrics) Cancelled() { m.tasksCancelled.Inc() }
func (m *Metrics) Failed(duration time.Duration) {
	m.tasksFailed.Inc()
	m.taskDuration.Observe(duration.Seconds())
}
func (m *Metrics) Completed(duration time.Duration, itemsFetched int) {
	m.tasksCompleted.Inc()
	m.taskDuration.Observe(duration.Seconds())
	m.taskItemsFetched.Observe(float64(itemsFetched))
}
func (m *Metrics) State(queued, running int) {
	m.tasksQueued.Set(float64(queued))
	m.tasksRunning.Set(float64(running))
}

func (m *Metrics) RecordConfig(success bool) {
	m.SetConfigHealth(success)
	if success {
		m.configSuccesses.Inc()
		m.configLastSuccess.SetToCurrentTime()
		return
	}
	m.configFailures.Inc()
}

func (m *Metrics) SetConfigHealth(healthy bool) {
	if healthy {
		m.configHealthy.Set(1)
		return
	}
	m.configHealthy.Set(0)
}

func (m *Metrics) RecordExternal(dependency string, duration time.Duration, success bool) error {
	switch dependency {
	case "rss", "notion", "llm":
	default:
		return fmt.Errorf("unsupported metrics dependency: %s", dependency)
	}
	m.externalRequests.WithLabelValues(dependency).Inc()
	m.externalDuration.WithLabelValues(dependency).Observe(duration.Seconds())
	if !success {
		m.externalFailures.WithLabelValues(dependency).Inc()
	}
	return nil
}

func (m *Metrics) RecordUpload(requested, processed, failed int) {
	m.uploadBatch.Observe(float64(requested))
	if processed > 0 {
		m.uploadItems.WithLabelValues("processed").Add(float64(processed))
	}
	if failed > 0 {
		m.uploadItems.WithLabelValues("failed").Add(float64(failed))
	}
}
