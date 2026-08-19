package httpapi

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/config"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/observability"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/storage"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/task"
)

type fakeContentReader struct{}

func (fakeContentReader) ListContents(context.Context, storage.ContentListOptions) (storage.ContentListPage, error) {
	return storage.ContentListPage{}, nil
}

func (fakeContentReader) GetContent(context.Context, string) (storage.ContentRecord, bool, error) {
	return storage.ContentRecord{}, false, nil
}

type fakeRuntime struct{}

func (fakeRuntime) TriggerScraper(context.Context) (string, int, error) {
	return "scraper_batch_1", 2, nil
}
func (fakeRuntime) TriggerUpload(context.Context) (map[string]any, error) {
	return map[string]any{"enabled": false, "claimed_count": 0}, nil
}
func (fakeRuntime) StoragePing(context.Context) error { return nil }
func (fakeRuntime) SyncStatus(context.Context) (map[string]any, error) {
	return map[string]any{"enabled": false, "counts": map[string]int{}}, nil
}
func (fakeRuntime) TaskStatistics() task.Statistics {
	return task.Statistics{QueueCapacity: 1000, MaxConcurrentTasks: 3}
}
func (fakeRuntime) ListTasks(*task.Status, int) []task.Result { return []task.Result{} }
func (fakeRuntime) TaskResult(string) (task.Result, bool)     { return task.Result{}, false }
func (fakeRuntime) ScraperRuntime(string) map[string]any {
	return map[string]any{
		"initialized":      true,
		"fetcher_type":     "RssHub",
		"has_storage":      true,
		"processors_count": 0,
	}
}

type failingSyncRuntime struct {
	fakeRuntime
}

func (failingSyncRuntime) SyncStatus(context.Context) (map[string]any, error) {
	return nil, errors.New("sync counts unavailable")
}

type fakeConfigManager struct {
	scrapers []config.ScraperConfig
}

func (m *fakeConfigManager) Reload(context.Context) (bool, error) { return false, nil }
func (m *fakeConfigManager) CurrentScrapers() []config.ScraperConfig {
	return append([]config.ScraperConfig(nil), m.scrapers...)
}
func (m *fakeConfigManager) AllScrapers() []config.ScraperConfig {
	return append([]config.ScraperConfig(nil), m.scrapers...)
}
func (m *fakeConfigManager) Status() config.Status {
	now := time.Now()
	return config.Status{
		Scrapers:   m.scrapers,
		LastCheck:  now,
		NextCheck:  now.Add(time.Second),
		Healthy:    true,
		FileErrors: map[string]string{},
	}
}

func TestTriggerScraperContract(t *testing.T) {
	server := newTestServer()
	request := httptest.NewRequest(http.MethodPost, "/trigger_scraper", nil)
	response := httptest.NewRecorder()
	server.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("unexpected status: %d", response.Code)
	}
	var payload map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &payload); err != nil {
		t.Fatal(err)
	}
	if payload["status"] != "success" {
		t.Fatalf("unexpected payload: %+v", payload)
	}
	data := payload["data"].(map[string]any)
	if data["batch_id"] != "scraper_batch_1" || data["source_count"] != float64(2) {
		t.Fatalf("unexpected data: %+v", data)
	}
}

func TestHealthAndReadinessContracts(t *testing.T) {
	server := newTestServer()
	for _, path := range []string{"/health", "/health/liveness", "/health/readiness"} {
		request := httptest.NewRequest(http.MethodGet, path, nil)
		response := httptest.NewRecorder()
		server.Handler().ServeHTTP(response, request)
		if response.Code != http.StatusOK {
			t.Fatalf("%s returned %d: %s", path, response.Code, response.Body.String())
		}
	}
}

func TestAdministrativeRouteContracts(t *testing.T) {
	server := newTestServer()
	tests := []struct {
		method string
		path   string
	}{
		{http.MethodPost, "/trigger_upload"},
		{http.MethodGet, "/admin/config/status"},
		{http.MethodPost, "/admin/config/refresh"},
		{http.MethodGet, "/admin/system/info"},
		{http.MethodGet, "/admin/scrapers"},
		{http.MethodGet, "/admin/tasks/stats"},
		{http.MethodGet, "/admin/tasks?status=completed&limit=25"},
		{http.MethodGet, "/metrics"},
	}
	for _, test := range tests {
		t.Run(test.method+" "+test.path, func(t *testing.T) {
			request := httptest.NewRequest(test.method, test.path, nil)
			response := httptest.NewRecorder()
			server.Handler().ServeHTTP(response, request)
			if response.Code != http.StatusOK {
				t.Fatalf("returned %d: %s", response.Code, response.Body.String())
			}
			if response.Body.Len() == 0 {
				t.Fatal("empty response body")
			}
		})
	}
}

func TestSystemInfoReportsSyncStatusFailure(t *testing.T) {
	server := newTestServer()
	server.runtime = failingSyncRuntime{}
	request := httptest.NewRequest(http.MethodGet, "/admin/system/info", nil)
	response := httptest.NewRecorder()
	server.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusInternalServerError {
		t.Fatalf("unexpected status: %d", response.Code)
	}
}

func TestHealthCacheContract(t *testing.T) {
	server := newTestServer()
	first := httptest.NewRecorder()
	server.Handler().ServeHTTP(first, httptest.NewRequest(http.MethodGet, "/health", nil))
	second := httptest.NewRecorder()
	server.Handler().ServeHTTP(second, httptest.NewRequest(http.MethodGet, "/health", nil))
	var payload map[string]any
	if err := json.Unmarshal(second.Body.Bytes(), &payload); err != nil {
		t.Fatal(err)
	}
	if payload["cached"] != true {
		t.Fatalf("expected cached health response: %+v", payload)
	}
}

func TestInvalidTaskLimitReturnsErrorContract(t *testing.T) {
	server := newTestServer()
	request := httptest.NewRequest(http.MethodGet, "/admin/tasks?limit=invalid", nil)
	response := httptest.NewRecorder()
	server.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusInternalServerError {
		t.Fatalf("unexpected status: %d", response.Code)
	}
}

func TestTaskNotFoundContract(t *testing.T) {
	server := newTestServer()
	request := httptest.NewRequest(http.MethodGet, "/admin/tasks/missing", nil)
	response := httptest.NewRecorder()
	server.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusNotFound {
		t.Fatalf("unexpected status: %d", response.Code)
	}
}

func TestMCPDisabledRouteUnavailable(t *testing.T) {
	server := newTestServer()
	request := httptest.NewRequest(http.MethodPost, "/mcp", nil)
	response := httptest.NewRecorder()
	server.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusNotFound {
		t.Fatalf("unexpected status: %d", response.Code)
	}
}

func TestMCPEnabledRouteUsesConfiguredHandler(t *testing.T) {
	server := newTestServer()
	server.serviceConfig.MCP = config.MCPConfig{
		Enabled:              true,
		APIToken:             "secret",
		QueryTimeout:         time.Second,
		MaxConcurrentQueries: 1,
	}
	server.EnableMCP(context.Background(), fakeContentReader{})
	request := httptest.NewRequest(http.MethodPost, "/mcp", nil)
	response := httptest.NewRecorder()
	server.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusUnauthorized)
	}
}

type unhealthyRuntime struct {
	fakeRuntime
}

func (unhealthyRuntime) StoragePing(context.Context) error {
	return errors.New("database unavailable")
}

func TestReadinessFailsWhenDatabaseUnavailable(t *testing.T) {
	server := newTestServer()
	server.runtime = unhealthyRuntime{}
	request := httptest.NewRequest(http.MethodGet, "/health/readiness", nil)
	response := httptest.NewRecorder()
	server.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("unexpected status: %d", response.Code)
	}
}

func newTestServer() *Server {
	return NewServer(
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		fakeRuntime{},
		&fakeConfigManager{scrapers: []config.ScraperConfig{
			{
				ID:          "feed-a",
				Name:        "Feed A",
				Enabled:     true,
				Fetcher:     "rsshub",
				HubRoot:     "https://example.com",
				Route:       "/feed",
				Priority:    5,
				FetchParams: map[string]any{},
			},
		}},
		config.ServiceConfig{
			Environment: "test",
			ScraperConfig: config.FileSettings{
				Directory:    "/tmp",
				PollInterval: time.Second,
				Debounce:     750 * time.Millisecond,
			},
			MaxConcurrentTasks: 3,
		},
		observability.NewMetrics("test"),
		"test-version",
	)
}
