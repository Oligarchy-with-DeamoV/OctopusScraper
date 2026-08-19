package httpapi

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/config"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/observability"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/task"
)

type Runtime interface {
	TriggerScraper(context.Context) (batchID string, sourceCount int, err error)
	TriggerUpload(context.Context) (map[string]any, error)
	StoragePing(context.Context) error
	SyncStatus(context.Context) (map[string]any, error)
	TaskStatistics() task.Statistics
	ListTasks(*task.Status, int) []task.Result
	TaskResult(string) (task.Result, bool)
	ScraperRuntime(string) map[string]any
}

type ConfigManager interface {
	Reload(context.Context) (bool, error)
	Status() config.Status
	CurrentScrapers() []config.ScraperConfig
	AllScrapers() []config.ScraperConfig
}

type healthCache struct {
	mu        sync.Mutex
	checkedAt time.Time
	status    int
	payload   map[string]any
}

type Server struct {
	logger        *slog.Logger
	runtime       Runtime
	configManager ConfigManager
	serviceConfig config.ServiceConfig
	metrics       *observability.Metrics
	version       string
	startedAt     time.Time
	health        healthCache
}

func NewServer(
	logger *slog.Logger,
	runtime Runtime,
	configManager ConfigManager,
	serviceConfig config.ServiceConfig,
	metrics *observability.Metrics,
	version string,
) *Server {
	return &Server{
		logger:        logger,
		runtime:       runtime,
		configManager: configManager,
		serviceConfig: serviceConfig,
		metrics:       metrics,
		version:       version,
		startedAt:     time.Now(),
	}
}

func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("POST /trigger_scraper", s.triggerScraper)
	mux.HandleFunc("POST /trigger_upload", s.triggerUpload)
	mux.HandleFunc("GET /health", s.healthCheck)
	mux.HandleFunc("GET /health/liveness", s.liveness)
	mux.HandleFunc("GET /health/readiness", s.readiness)
	mux.HandleFunc("GET /admin/config/status", s.configStatus)
	mux.HandleFunc("POST /admin/config/refresh", s.configRefresh)
	mux.HandleFunc("GET /admin/system/info", s.systemInfo)
	mux.HandleFunc("GET /admin/scrapers", s.scrapers)
	mux.HandleFunc("GET /admin/tasks/stats", s.taskStats)
	mux.HandleFunc("GET /admin/tasks", s.tasks)
	mux.HandleFunc("GET /admin/tasks/{task_id}", s.taskDetails)
	mux.Handle("GET /metrics", s.metrics.Handler())
	return s.recover(s.accessLog(mux))
}

func (s *Server) triggerScraper(writer http.ResponseWriter, request *http.Request) {
	batchID, sourceCount, err := s.runtime.TriggerScraper(request.Context())
	if err != nil {
		s.logger.Error("Scraping task submission failed", "error", err)
		writeJSON(writer, http.StatusInternalServerError, map[string]any{
			"status":  "error",
			"message": fmt.Sprintf("An unexpected error occurred: %s", err),
			"data":    nil,
		})
		return
	}
	writeJSON(writer, http.StatusOK, map[string]any{
		"status":  "success",
		"message": "Scraper tasks submitted successfully.",
		"data": map[string]any{
			"batch_id":     batchID,
			"source_count": sourceCount,
		},
	})
}

func (s *Server) triggerUpload(writer http.ResponseWriter, request *http.Request) {
	result, err := s.runtime.TriggerUpload(request.Context())
	if err != nil {
		s.logger.Error("Upload task failed", "error", err)
		writeJSON(writer, http.StatusInternalServerError, map[string]any{
			"status":  "error",
			"message": fmt.Sprintf("An unexpected error occurred: %s", err),
			"data":    nil,
		})
		return
	}
	writeJSON(writer, http.StatusOK, map[string]any{
		"status":  "success",
		"message": "Incremental synchronization completed.",
		"data":    result,
	})
}

func (s *Server) healthCheck(writer http.ResponseWriter, request *http.Request) {
	useCache := !strings.EqualFold(request.URL.Query().Get("cache"), "false")
	now := time.Now()
	s.health.mu.Lock()
	if useCache && s.health.payload != nil && now.Sub(s.health.checkedAt) < 30*time.Second {
		payload := cloneMap(s.health.payload)
		payload["cached"] = true
		payload["cache_age_seconds"] = round2(now.Sub(s.health.checkedAt).Seconds())
		status := s.health.status
		s.health.mu.Unlock()
		writeJSON(writer, status, payload)
		return
	}
	s.health.mu.Unlock()

	configStatus := s.configManager.Status()
	storageErr := s.runtime.StoragePing(request.Context())
	syncStatus, syncErr := s.runtime.SyncStatus(request.Context())
	healthy := configStatus.Healthy && storageErr == nil && syncErr == nil
	statusCode := http.StatusOK
	statusText := "healthy"
	if !healthy {
		statusCode = http.StatusServiceUnavailable
		statusText = "unhealthy"
	}
	payload := map[string]any{
		"status":    statusText,
		"timestamp": timestamp(now),
		"service": map[string]any{
			"name":           "OctopusService",
			"version":        s.version,
			"uptime_seconds": time.Since(s.startedAt).Seconds(),
		},
		"dependencies": map[string]any{
			"octopus_instance": map[string]any{
				"status":              "healthy",
				"scrapers_configured": len(s.configManager.CurrentScrapers()),
				"notion_sync":         syncStatus,
			},
			"postgresql": map[string]any{
				"status": healthyLabel(storageErr == nil),
			},
		},
		"configuration": map[string]any{
			"status":          healthyLabel(configStatus.Healthy),
			"last_check":      timestamp(configStatus.LastCheck),
			"next_check":      timestamp(configStatus.NextCheck),
			"version":         versionID(configStatus.Version),
			"scrapers_count":  len(configStatus.Scrapers),
			"active_scrapers": countEnabled(configStatus.Scrapers),
			"error":           optionalError(configStatus.Healthy, configStatus.ErrorMessage),
			"directory":       s.serviceConfig.ScraperConfig.Directory,
			"file_errors":     configStatus.FileErrors,
		},
		"performance": map[string]any{
			"response_time_ms": round2(time.Since(now).Seconds() * 1000),
			"memory_usage":     memoryUsage(),
		},
		"cached":       false,
		"_status_code": statusCode,
	}
	s.health.mu.Lock()
	s.health.checkedAt = now
	s.health.status = statusCode
	s.health.payload = cloneMap(payload)
	s.health.mu.Unlock()
	writeJSON(writer, statusCode, payload)
}

func (s *Server) liveness(writer http.ResponseWriter, _ *http.Request) {
	writeJSON(writer, http.StatusOK, map[string]any{
		"status":    "alive",
		"timestamp": timestamp(time.Now()),
	})
}

func (s *Server) readiness(writer http.ResponseWriter, request *http.Request) {
	configStatus := s.configManager.Status()
	storageReady := s.runtime.StoragePing(request.Context()) == nil
	ready := configStatus.Healthy && storageReady
	statusCode := http.StatusOK
	statusText := "ready"
	if !ready {
		statusCode = http.StatusServiceUnavailable
		statusText = "not_ready"
	}
	writeJSON(writer, statusCode, map[string]any{
		"status":    statusText,
		"timestamp": timestamp(time.Now()),
		"checks": map[string]any{
			"config_manager":   configStatus.Healthy,
			"octopus_instance": true,
			"postgresql":       storageReady,
		},
	})
}

func (s *Server) configStatus(writer http.ResponseWriter, _ *http.Request) {
	status := s.configManager.Status()
	scrapers := make([]map[string]any, 0, len(status.Scrapers))
	for _, scraper := range status.Scrapers {
		scrapers = append(scrapers, map[string]any{
			"id":          scraper.ID,
			"name":        scraper.Name,
			"status":      scraper.Status(),
			"enabled":     scraper.Enabled,
			"fetcher":     scraper.Fetcher,
			"source_path": scraper.SourcePath,
		})
	}
	var version any
	if status.Version != nil {
		version = map[string]any{
			"version_id":     status.Version.ID,
			"timestamp":      timestamp(status.Version.Timestamp),
			"change_summary": status.Version.ChangeSummary,
		}
	}
	writeJSON(writer, http.StatusOK, map[string]any{
		"status": "success",
		"config_status": map[string]any{
			"is_healthy":    status.Healthy,
			"last_check":    timestamp(status.LastCheck),
			"version":       version,
			"scrapers":      scrapers,
			"error_message": emptyAsNil(status.ErrorMessage),
			"file_errors":   status.FileErrors,
		},
	})
}

func (s *Server) configRefresh(writer http.ResponseWriter, request *http.Request) {
	oldStatus := s.configManager.Status()
	oldCount := len(s.configManager.CurrentScrapers())
	changed, err := s.configManager.Reload(request.Context())
	if err != nil {
		s.logger.Error("Failed to refresh config", "error", err)
		writeJSON(writer, http.StatusInternalServerError, map[string]any{
			"status":  "error",
			"message": fmt.Sprintf("Configuration refresh failed: %s", err),
		})
		return
	}
	newStatus := s.configManager.Status()
	writeJSON(writer, http.StatusOK, map[string]any{
		"status":           "success",
		"message":          map[bool]string{true: "Configuration directory changes applied", false: "Configuration directory is unchanged"}[changed],
		"config_changed":   changed,
		"reload_performed": changed,
		"changes": map[string]any{
			"old_version":        versionID(oldStatus.Version),
			"new_version":        versionID(newStatus.Version),
			"old_scrapers_count": oldCount,
			"new_scrapers_count": len(s.configManager.CurrentScrapers()),
			"change_summary":     versionSummary(newStatus.Version),
		},
		"file_errors": newStatus.FileErrors,
		"timestamp":   timestamp(time.Now()),
	})
}

func (s *Server) systemInfo(writer http.ResponseWriter, request *http.Request) {
	syncStatus, err := s.runtime.SyncStatus(request.Context())
	if err != nil {
		s.logger.Error("Failed to get system info", "error", err)
		writeJSON(writer, http.StatusInternalServerError, map[string]any{
			"status":  "error",
			"message": fmt.Sprintf("Failed to get system info: %s", err),
		})
		return
	}
	stats := s.runtime.TaskStatistics()
	writeJSON(writer, http.StatusOK, map[string]any{
		"status": "success",
		"system_info": map[string]any{
			"service": map[string]any{
				"name":           "OctopusService",
				"version":        s.version,
				"uptime_seconds": time.Since(s.startedAt).Seconds(),
				"environment":    s.serviceConfig.Environment,
				"debug_mode":     s.serviceConfig.Debug,
			},
			"configuration": map[string]any{
				"scraper_config_dir":           s.serviceConfig.ScraperConfig.Directory,
				"config_poll_interval_seconds": s.serviceConfig.ScraperConfig.PollInterval.Seconds(),
				"config_debounce_seconds":      s.serviceConfig.ScraperConfig.Debounce.Seconds(),
				"scraper_timeout":              s.serviceConfig.ScraperTimeout.Seconds(),
				"upload_timeout":               s.serviceConfig.UploadTimeout.Seconds(),
				"upload_max_retries":           s.serviceConfig.UploadMaxRetries,
				"log_level":                    s.serviceConfig.LogLevel,
				"log_format":                   s.serviceConfig.LogFormat,
			},
			"octopus_instance": map[string]any{
				"scrapers_configured":     len(s.configManager.CurrentScrapers()),
				"max_concurrent_scrapers": s.serviceConfig.MaxConcurrentTasks,
				"use_task_manager":        true,
			},
			"storage": map[string]any{
				"database_url_configured": s.serviceConfig.Database.URL != "",
				"notion_sync":             syncStatus,
			},
			"memory_usage": memoryUsage(),
			"timestamp":    timestamp(time.Now()),
			"task_manager": map[string]any{
				"enabled":    true,
				"statistics": stats,
			},
		},
	})
}

func (s *Server) scrapers(writer http.ResponseWriter, _ *http.Request) {
	configs := s.configManager.AllScrapers()
	items := make([]map[string]any, 0, len(configs))
	distribution := make(map[string]int)
	active := 0
	for index, scraper := range configs {
		if scraper.Enabled {
			active++
		}
		distribution[scraper.Fetcher]++
		items = append(items, map[string]any{
			"index":        index,
			"id":           scraper.ID,
			"name":         scraper.Name,
			"status":       scraper.Status(),
			"enabled":      scraper.Enabled,
			"fetcher":      scraper.Fetcher,
			"hub_root":     scraper.HubRoot,
			"route":        scraper.Route,
			"priority":     scraper.Priority,
			"fetch_params": scraper.FetchParams,
			"is_active":    scraper.Enabled,
			"source_path":  scraper.SourcePath,
			"runtime":      s.runtime.ScraperRuntime(scraper.ID),
		})
	}
	writeJSON(writer, http.StatusOK, map[string]any{
		"status":   "success",
		"scrapers": items,
		"summary": map[string]any{
			"total_count":          len(items),
			"active_count":         active,
			"inactive_count":       len(items) - active,
			"fetcher_distribution": distribution,
		},
	})
}

func (s *Server) taskStats(writer http.ResponseWriter, _ *http.Request) {
	stats := s.runtime.TaskStatistics()
	payload := structToMap(stats)
	payload["task_manager_enabled"] = true
	payload["legacy_mode"] = false
	payload["uptime_info"] = map[string]any{
		"queue_capacity_usage": fmt.Sprintf("%d/%d", stats.CurrentQueueSize, stats.QueueCapacity),
		"worker_utilization":   fmt.Sprintf("%d/%d", stats.RunningTasksCount, stats.MaxConcurrentTasks),
	}
	payload["timestamp"] = timestamp(time.Now())
	writeJSON(writer, http.StatusOK, map[string]any{
		"status":     "success",
		"statistics": payload,
	})
}

func (s *Server) tasks(writer http.ResponseWriter, request *http.Request) {
	limit := 50
	if raw := request.URL.Query().Get("limit"); raw != "" {
		parsed, err := strconv.Atoi(raw)
		if err != nil {
			writeJSON(writer, http.StatusInternalServerError, map[string]any{
				"status":  "error",
				"message": fmt.Sprintf("Failed to list tasks: %s", err),
			})
			return
		}
		limit = parsed
	}
	if limit > 200 {
		limit = 200
	}
	statusText := request.URL.Query().Get("status")
	status, err := task.ParseStatus(statusText)
	var results []task.Result
	if err == nil {
		results = s.runtime.ListTasks(status, limit)
	} else {
		results = []task.Result{}
	}
	writeJSON(writer, http.StatusOK, map[string]any{
		"status":               "success",
		"tasks":                results,
		"filters":              map[string]any{"status": emptyAsNil(statusText), "limit": limit},
		"total_returned":       len(results),
		"task_manager_enabled": true,
	})
}

func (s *Server) taskDetails(writer http.ResponseWriter, request *http.Request) {
	taskID := request.PathValue("task_id")
	result, ok := s.runtime.TaskResult(taskID)
	if !ok {
		writeJSON(writer, http.StatusNotFound, map[string]any{
			"status":  "error",
			"message": fmt.Sprintf("Task '%s' not found", taskID),
		})
		return
	}
	writeJSON(writer, http.StatusOK, map[string]any{
		"status": "success",
		"task":   result,
	})
}

func (s *Server) recover(next http.Handler) http.Handler {
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		defer func() {
			if recovered := recover(); recovered != nil {
				s.logger.Error("Unhandled HTTP panic", "error", recovered)
				writeJSON(writer, http.StatusInternalServerError, map[string]any{
					"status":  "error",
					"message": "Internal server error",
				})
			}
		}()
		next.ServeHTTP(writer, request)
	})
}

func (s *Server) accessLog(next http.Handler) http.Handler {
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		started := time.Now()
		next.ServeHTTP(writer, request)
		s.logger.Debug(
			"HTTP request completed",
			"method", request.Method,
			"path", request.URL.Path,
			"duration_ms", time.Since(started).Seconds()*1000,
		)
	})
}

func writeJSON(writer http.ResponseWriter, status int, payload any) {
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(status)
	_ = json.NewEncoder(writer).Encode(payload)
}

func timestamp(value time.Time) string {
	if value.IsZero() {
		return ""
	}
	return value.Format(time.RFC3339Nano)
}

func healthyLabel(healthy bool) string {
	if healthy {
		return "healthy"
	}
	return "unhealthy"
}

func optionalError(healthy bool, message string) any {
	if healthy || message == "" {
		return nil
	}
	return message
}

func emptyAsNil(value string) any {
	if value == "" {
		return nil
	}
	return value
}

func versionID(version *config.Version) any {
	if version == nil {
		return nil
	}
	return version.ID
}

func versionSummary(version *config.Version) any {
	if version == nil {
		return nil
	}
	return version.ChangeSummary
}

func countEnabled(scrapers []config.ScraperConfig) int {
	total := 0
	for _, scraper := range scrapers {
		if scraper.Enabled {
			total++
		}
	}
	return total
}

func memoryUsage() map[string]any {
	var stats runtime.MemStats
	runtime.ReadMemStats(&stats)
	return map[string]any{
		"rss_mb": round2(float64(stats.Sys) / 1024 / 1024),
	}
}

func round2(value float64) float64 {
	return float64(int64(value*100+0.5)) / 100
}

func cloneMap(input map[string]any) map[string]any {
	output := make(map[string]any, len(input))
	for key, value := range input {
		output[key] = value
	}
	return output
}

func structToMap(value any) map[string]any {
	encoded, _ := json.Marshal(value)
	output := map[string]any{}
	_ = json.Unmarshal(encoded, &output)
	return output
}
