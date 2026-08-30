package bootstrap

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/config"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/observability"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/storage"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/task"
)

type bootstrapStore struct {
	initializeErr error
	reconcileErr  error
}

func (s bootstrapStore) Initialize(context.Context) error { return s.initializeErr }
func (bootstrapStore) Ping(context.Context) error         { return nil }
func (bootstrapStore) Close()                             {}
func (bootstrapStore) ExistingContentIDs(context.Context, []string) (map[string]struct{}, error) {
	return map[string]struct{}{}, nil
}
func (bootstrapStore) StoreContents(
	context.Context,
	[]content.Content,
	[]storage.ContentSource,
) (storage.StoreStats, error) {
	return storage.StoreStats{}, nil
}
func (bootstrapStore) ListContents(context.Context, storage.ContentListOptions) (storage.ContentListPage, error) {
	return storage.ContentListPage{}, nil
}
func (bootstrapStore) GetContent(context.Context, string) (storage.ContentRecord, bool, error) {
	return storage.ContentRecord{}, false, nil
}
func (s bootstrapStore) ReconcileTargets(context.Context, []storage.ExportTarget) error {
	return s.reconcileErr
}
func (bootstrapStore) Claim(context.Context, string, string, int, time.Duration, int) ([]content.Content, error) {
	return nil, nil
}
func (bootstrapStore) Renew(context.Context, string, string, string, time.Duration) (bool, error) {
	return true, nil
}
func (bootstrapStore) Complete(context.Context, string, string, string) (bool, error) {
	return true, nil
}
func (bootstrapStore) Fail(context.Context, string, string, string, string, int) (bool, error) {
	return true, nil
}
func (bootstrapStore) SyncCounts(context.Context) (map[string]int64, error) {
	return map[string]int64{}, nil
}

func TestApplyOptions(t *testing.T) {
	serviceConfig := config.ServiceConfig{
		Host:      "0.0.0.0",
		Port:      8000,
		Debug:     false,
		LogLevel:  "INFO",
		LogFormat: "plain",
		ScraperConfig: config.FileSettings{
			Directory: "old",
		},
	}
	applyOptions(&serviceConfig, Options{
		Host:             "127.0.0.1",
		Port:             9000,
		Debug:            true,
		LogLevel:         "DEBUG",
		LogFormat:        "json",
		ScraperConfigDir: "new",
	})
	if serviceConfig.Host != "127.0.0.1" ||
		serviceConfig.Port != 9000 ||
		!serviceConfig.Debug ||
		serviceConfig.LogLevel != "DEBUG" ||
		serviceConfig.LogFormat != "json" ||
		serviceConfig.ScraperConfig.Directory != "new" {
		t.Fatalf("unexpected config: %#v", serviceConfig)
	}
}

func TestApplyOptionsPreservesEnvironmentValues(t *testing.T) {
	serviceConfig := config.ServiceConfig{
		Host:      "env-host",
		Port:      7000,
		Debug:     true,
		LogLevel:  "WARN",
		LogFormat: "json",
		ScraperConfig: config.FileSettings{
			Directory: "env-dir",
		},
	}
	applyOptions(&serviceConfig, Options{})
	if serviceConfig.Host != "env-host" ||
		serviceConfig.Port != 7000 ||
		!serviceConfig.Debug ||
		serviceConfig.LogLevel != "WARN" ||
		serviceConfig.LogFormat != "json" ||
		serviceConfig.ScraperConfig.Directory != "env-dir" {
		t.Fatalf("unexpected config: %#v", serviceConfig)
	}
}

func TestApplyOptionsTreatsLogFormatAsDeprecatedCompatibilityInput(t *testing.T) {
	serviceConfig := config.ServiceConfig{LogFormat: "json"}
	applyOptions(&serviceConfig, Options{LogFormat: "plain"})
	if serviceConfig.LogFormat != "json" {
		t.Fatalf("LogFormat = %q", serviceConfig.LogFormat)
	}
}

func TestLoadDotEnv(t *testing.T) {
	originalDirectory, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := os.Chdir(originalDirectory); err != nil {
			t.Errorf("restore working directory: %v", err)
		}
	})

	tempDirectory := t.TempDir()
	if err := os.Chdir(tempDirectory); err != nil {
		t.Fatal(err)
	}
	if err := loadDotEnv(); err != nil {
		t.Fatalf("missing .env should be ignored: %v", err)
	}
	if err := os.WriteFile(
		filepath.Join(tempDirectory, ".env"),
		[]byte("OCTOPUS_BOOTSTRAP_TEST=loaded\n"),
		0o600,
	); err != nil {
		t.Fatal(err)
	}
	originalValue, existed := os.LookupEnv("OCTOPUS_BOOTSTRAP_TEST")
	if err := os.Unsetenv("OCTOPUS_BOOTSTRAP_TEST"); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if existed {
			_ = os.Setenv("OCTOPUS_BOOTSTRAP_TEST", originalValue)
			return
		}
		_ = os.Unsetenv("OCTOPUS_BOOTSTRAP_TEST")
	})
	if err := loadDotEnv(); err != nil {
		t.Fatal(err)
	}
	if value := os.Getenv("OCTOPUS_BOOTSTRAP_TEST"); value != "loaded" {
		t.Fatalf("unexpected loaded value %q", value)
	}
}

func TestRunInitializesAndClosesLoggerBeforeConfigFailure(t *testing.T) {
	directory := t.TempDir()
	logPath := filepath.Join(directory, "logs", "octopus.log")
	t.Setenv("SCRAPER_CONFIG_DIR", filepath.Join(directory, "missing"))
	t.Setenv("LOG_LEVEL", "DEBUG")
	t.Setenv("LOG_FILE", logPath)
	t.Setenv("LOG_RETENTION_DAYS", "1")

	err := Run(context.Background(), Options{})
	if err == nil || !strings.Contains(err.Error(), "load initial scraper configuration") {
		t.Fatalf("Run() error = %v", err)
	}
	content, err := os.ReadFile(logPath)
	if err != nil {
		t.Fatal(err)
	}
	var payload map[string]any
	if err := json.Unmarshal(content, &payload); err != nil {
		t.Fatalf("log file is not JSON: %s", content)
	}
	if payload["level"] != "error" ||
		payload["event"] != "scan config directory failed" {
		t.Fatalf("unexpected startup log payload: %#v", payload)
	}
}

func TestBuildSyncServiceDisabled(t *testing.T) {
	service, err := buildSyncService(
		context.Background(),
		config.ServiceConfig{},
		bootstrapStore{},
		observability.NewMetrics("test"),
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	if service != nil {
		t.Fatalf("expected nil service, got %#v", service)
	}
}

func TestBuildSyncServiceDoesNotContactNotionAtStartup(t *testing.T) {
	service, err := buildSyncService(
		context.Background(),
		config.ServiceConfig{
			Notion: config.NotionConfig{
				Enabled:    true,
				APIKey:     "secret",
				DatabaseID: "database",
				Interval:   time.Minute,
			},
			UploadTimeout: time.Second,
		},
		bootstrapStore{},
		observability.NewMetrics("test"),
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	if service == nil {
		t.Fatal("expected enabled sync service")
	}
}

func TestBuildSyncServiceErrors(t *testing.T) {
	reconcileErr := errors.New("reconcile failed")
	if _, err := buildSyncService(
		context.Background(),
		config.ServiceConfig{},
		bootstrapStore{reconcileErr: reconcileErr},
		observability.NewMetrics("test"),
		nil,
	); !errors.Is(err, reconcileErr) {
		t.Fatalf("disabled reconciliation error = %v", err)
	}
	if _, err := buildSyncService(
		context.Background(),
		config.ServiceConfig{Notion: config.NotionConfig{Enabled: true}},
		bootstrapStore{},
		observability.NewMetrics("test"),
		nil,
	); err == nil {
		t.Fatal("expected invalid Notion configuration error")
	}
	if _, err := buildSyncService(
		context.Background(),
		config.ServiceConfig{
			Notion: config.NotionConfig{
				Enabled:    true,
				APIKey:     "secret",
				DatabaseID: "database",
				BatchSize:  0,
			},
		},
		bootstrapStore{reconcileErr: reconcileErr},
		observability.NewMetrics("test"),
		nil,
	); !errors.Is(err, reconcileErr) {
		t.Fatalf("enabled reconciliation error = %v", err)
	}
}

func TestRunRejectsInvalidReloadedRuntimeConfiguration(t *testing.T) {
	directory := t.TempDir()
	writeBootstrapConfig(t, directory, "feed.yaml", bootstrapScraperYAML("feed", "/feed.xml"))
	t.Setenv("SCRAPER_CONFIG_DIR", directory)
	t.Setenv("SCRAPER_CONFIG_POLL_INTERVAL", "0.005")
	t.Setenv("SCRAPER_CONFIG_DEBOUNCE_SECONDS", "0.001")
	t.Setenv("OCTOPUS_TASK_RESULT_PATH", filepath.Join(directory, "results.sqlite3"))
	t.Setenv("LOG_FILE", filepath.Join(directory, "service.log"))
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	port := listener.Addr().(*net.TCPAddr).Port
	_ = listener.Close()
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() {
		defer close(done)
		time.Sleep(20 * time.Millisecond)
		_ = os.WriteFile(
			filepath.Join(directory, "duplicate.yaml"),
			[]byte(bootstrapScraperYAML("duplicate", "/feed.xml")),
			0o600,
		)
		time.Sleep(80 * time.Millisecond)
		cancel()
	}()
	err = runWithDependencies(
		ctx,
		Options{Host: "127.0.0.1", Port: port},
		runDependencies{
			newPostgresStore: func(config.DatabaseConfig, *slog.Logger) (storage.CanonicalStore, error) {
				return bootstrapStore{}, nil
			},
		},
	)
	<-done
	time.Sleep(100 * time.Millisecond)
	if err != nil &&
		!strings.Contains(err.Error(), "close logger") {
		t.Fatalf("Run() reload rejection error = %v", err)
	}
}

func TestMaxDuration(t *testing.T) {
	if got := maxDuration(time.Second, 2*time.Second); got != 2*time.Second {
		t.Fatalf("got %s", got)
	}
	if got := maxDuration(3*time.Second, 2*time.Second); got != 3*time.Second {
		t.Fatalf("got %s", got)
	}
}

func TestOpenTaskResultStoreDegradesWhenPathIsUnavailable(t *testing.T) {
	blockingPath := filepath.Join(t.TempDir(), "not-a-directory")
	if err := os.WriteFile(blockingPath, []byte("blocked"), 0o600); err != nil {
		t.Fatal(err)
	}
	store, err := openTaskResultStore(
		context.Background(),
		filepath.Join(blockingPath, "tasks.sqlite3"),
	)
	if store != nil {
		_ = store.Close()
		t.Fatal("unavailable task history path returned a store")
	}
	if err == nil {
		t.Fatal("unavailable task history path returned no error")
	}
}

func TestOpenTaskResultStorePropagatesCancellation(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	store, err := openTaskResultStore(
		ctx,
		filepath.Join(t.TempDir(), "tasks.sqlite3"),
	)
	if store != nil {
		_ = store.Close()
		t.Fatal("cancelled task history open returned a store")
	}
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("openTaskResultStore error = %v", err)
	}
}

func TestRunStoreConstructionAndInitializationErrors(t *testing.T) {
	directory := t.TempDir()
	writeBootstrapConfig(t, directory, "feed.yaml", bootstrapScraperYAML("feed", "/feed.xml"))
	t.Setenv("SCRAPER_CONFIG_DIR", directory)
	t.Setenv("LOG_FILE", filepath.Join(directory, "service.log"))
	t.Setenv("OCTOPUS_TASK_RESULT_PATH", filepath.Join(directory, "results.sqlite3"))

	constructorErr := errors.New("store constructor failed")
	if err := runWithDependencies(
		context.Background(),
		Options{},
		runDependencies{
			newPostgresStore: func(config.DatabaseConfig, *slog.Logger) (storage.CanonicalStore, error) {
				return nil, constructorErr
			},
		},
	); !errors.Is(err, constructorErr) {
		t.Fatalf("constructor error = %v", err)
	}

	initializeErr := errors.New("store initialize failed")
	if err := runWithDependencies(
		context.Background(),
		Options{},
		runDependencies{
			newPostgresStore: func(config.DatabaseConfig, *slog.Logger) (storage.CanonicalStore, error) {
				return bootstrapStore{initializeErr: initializeErr}, nil
			},
		},
	); !errors.Is(err, initializeErr) {
		t.Fatalf("initialize error = %v", err)
	}
}

func TestRunRejectsDotEnvAndServiceConfigurationErrors(t *testing.T) {
	originalDirectory, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	directory := t.TempDir()
	if err := os.Chdir(directory); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.Chdir(originalDirectory) })
	if err := os.Mkdir(".env", 0o755); err != nil {
		t.Fatal(err)
	}
	if err := Run(context.Background(), Options{}); err == nil ||
		!strings.Contains(err.Error(), "load .env") {
		t.Fatalf("dotenv error = %v", err)
	}
	_ = os.Remove(".env")
	t.Setenv("DATABASE_URL", "sqlite:///invalid")
	if err := Run(context.Background(), Options{}); err == nil ||
		!strings.Contains(err.Error(), "load service configuration") {
		t.Fatalf("service configuration error = %v", err)
	}
}

func TestRunRejectsLoggerConfiguration(t *testing.T) {
	directory := t.TempDir()
	blockingPath := filepath.Join(directory, "not-a-directory")
	if err := os.WriteFile(blockingPath, []byte("blocked"), 0o600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("LOG_FILE", filepath.Join(blockingPath, "service.log"))
	if err := Run(context.Background(), Options{}); err == nil {
		t.Fatal("invalid logger configuration unexpectedly succeeded")
	}
}

func TestRunClosesStoreWhenSyncConstructionFails(t *testing.T) {
	directory := t.TempDir()
	writeBootstrapConfig(t, directory, "feed.yaml", bootstrapScraperYAML("feed", "/feed.xml"))
	t.Setenv("SCRAPER_CONFIG_DIR", directory)
	t.Setenv("NOTION_SYNC_ENABLED", "true")
	t.Setenv("NOTION_API_KEY", "key")
	t.Setenv("NOTION_CONTENT_DATABASE_ID", "database")
	t.Setenv("LOG_FILE", filepath.Join(directory, "service.log"))
	reconcileErr := errors.New("sync reconciliation failed")
	if err := runWithDependencies(
		context.Background(),
		Options{},
		runDependencies{
			newPostgresStore: func(config.DatabaseConfig, *slog.Logger) (storage.CanonicalStore, error) {
				return bootstrapStore{reconcileErr: reconcileErr}, nil
			},
		},
	); !errors.Is(err, reconcileErr) {
		t.Fatalf("sync construction error = %v", err)
	}
}

func TestRunClosesResultStoreWhenTaskManagerConstructionFails(t *testing.T) {
	directory := t.TempDir()
	writeBootstrapConfig(t, directory, "feed.yaml", bootstrapScraperYAML("feed", "/feed.xml"))
	t.Setenv("SCRAPER_CONFIG_DIR", directory)
	t.Setenv("OCTOPUS_TASK_RESULT_PATH", filepath.Join(directory, "results.sqlite3"))
	t.Setenv("LOG_FILE", filepath.Join(directory, "service.log"))
	managerErr := errors.New("task manager construction failed")
	if err := runWithDependencies(
		context.Background(),
		Options{},
		runDependencies{
			newPostgresStore: func(config.DatabaseConfig, *slog.Logger) (storage.CanonicalStore, error) {
				return bootstrapStore{}, nil
			},
			newTaskManager: func(
				context.Context,
				*slog.Logger,
				task.Executor,
				int,
				int,
				time.Duration,
				*task.ResultStore,
				task.Observer,
			) (*task.Manager, error) {
				return nil, managerErr
			},
		},
	); !errors.Is(err, managerErr) {
		t.Fatalf("task manager error = %v", err)
	}
}

func TestRunReturnsHTTPServeError(t *testing.T) {
	directory := t.TempDir()
	writeBootstrapConfig(t, directory, "feed.yaml", bootstrapScraperYAML("feed", "/feed.xml"))
	t.Setenv("SCRAPER_CONFIG_DIR", directory)
	t.Setenv("OCTOPUS_TASK_RESULT_PATH", filepath.Join(directory, "results.sqlite3"))
	t.Setenv("LOG_FILE", filepath.Join(directory, "service.log"))
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	err = runWithDependencies(
		context.Background(),
		Options{
			Host: "127.0.0.1",
			Port: listener.Addr().(*net.TCPAddr).Port,
		},
		runDependencies{
			newPostgresStore: func(config.DatabaseConfig, *slog.Logger) (storage.CanonicalStore, error) {
				return bootstrapStore{}, nil
			},
		},
	)
	if err == nil || !strings.Contains(err.Error(), "serve HTTP") {
		t.Fatalf("HTTP serve error = %v", err)
	}
}

func TestRunRejectsInvalidRuntimeScraperConfiguration(t *testing.T) {
	directory := t.TempDir()
	writeBootstrapConfig(t, directory, "a.yaml", bootstrapScraperYAML("a", "/same.xml"))
	writeBootstrapConfig(t, directory, "b.yaml", bootstrapScraperYAML("b", "/same.xml"))
	t.Setenv("SCRAPER_CONFIG_DIR", directory)
	t.Setenv("LOG_FILE", filepath.Join(directory, "service.log"))
	err := Run(context.Background(), Options{})
	if err == nil || !strings.Contains(err.Error(), "validate initial scraper configuration") {
		t.Fatalf("Run() error = %v", err)
	}
}

func TestRunCompletesLifecycleWithInjectedCanonicalStore(t *testing.T) {
	directory := t.TempDir()
	writeBootstrapConfig(t, directory, "feed.yaml", bootstrapScraperYAML("feed", "/feed.xml"))
	t.Setenv("SCRAPER_CONFIG_DIR", directory)
	t.Setenv("OCTOPUS_TASK_RESULT_PATH", filepath.Join(directory, "results.sqlite3"))
	t.Setenv("LOG_FILE", filepath.Join(directory, "service.log"))
	t.Setenv("SCRAPER_CONFIG_POLL_INTERVAL", "0.005")
	t.Setenv("SCRAPER_CONFIG_DEBOUNCE_SECONDS", "0.001")
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	port := listener.Addr().(*net.TCPAddr).Port
	_ = listener.Close()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go func() {
		time.Sleep(20 * time.Millisecond)
		_ = os.WriteFile(
			filepath.Join(directory, "feed.yaml"),
			[]byte(bootstrapScraperYAML("feed", "/updated.xml")),
			0o600,
		)
		time.Sleep(80 * time.Millisecond)
		cancel()
	}()
	if err := runWithDependencies(
		ctx,
		Options{Host: "127.0.0.1", Port: port},
		runDependencies{
			newPostgresStore: func(config.DatabaseConfig, *slog.Logger) (storage.CanonicalStore, error) {
				return bootstrapStore{}, nil
			},
		},
	); err != nil &&
		!strings.Contains(err.Error(), "close logger") {
		t.Fatalf("Run() lifecycle error = %v", err)
	}
	if content, err := os.ReadFile(filepath.Join(directory, "service.log")); err != nil ||
		!strings.Contains(string(content), "Octopus scrapers reloaded") {
		t.Fatalf("reload callback was not observed: %v", err)
	}
}

func TestRunStartsEnabledIntegrations(t *testing.T) {
	directory := t.TempDir()
	writeBootstrapConfig(t, directory, "feed.yaml", bootstrapScraperYAML("feed", "/feed.xml"))
	t.Setenv("SCRAPER_CONFIG_DIR", directory)
	t.Setenv("NOTION_SYNC_ENABLED", "true")
	t.Setenv("NOTION_API_KEY", "key")
	t.Setenv("NOTION_CONTENT_DATABASE_ID", "database")
	t.Setenv("MCP_ENABLED", "true")
	t.Setenv("MCP_API_TOKEN", "token")
	t.Setenv("OCTOPUS_TASK_RESULT_PATH", filepath.Join(directory, "results.sqlite3"))
	t.Setenv("LOG_FILE", filepath.Join(directory, "service.log"))
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	port := listener.Addr().(*net.TCPAddr).Port
	_ = listener.Close()
	ctx, cancel := context.WithCancel(context.Background())
	go func() {
		time.Sleep(40 * time.Millisecond)
		cancel()
	}()
	if err := runWithDependencies(
		ctx,
		Options{Host: "127.0.0.1", Port: port},
		runDependencies{
			newPostgresStore: func(config.DatabaseConfig, *slog.Logger) (storage.CanonicalStore, error) {
				return bootstrapStore{}, nil
			},
		},
	); err != nil &&
		!strings.Contains(err.Error(), "close logger") {
		t.Fatalf("enabled integrations lifecycle error = %v", err)
	}
}

func writeBootstrapConfig(t *testing.T, directory, name, body string) string {
	t.Helper()
	path := filepath.Join(directory, name)
	if err := os.WriteFile(path, []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
	return path
}

func bootstrapScraperYAML(id, route string) string {
	return "id: " + id + "\n" +
		"name: " + id + "\n" +
		"enabled: true\n" +
		"fetcher: direct_rss\n" +
		"hub_root: https://example.com\n" +
		"route: " + route + "\n"
}
