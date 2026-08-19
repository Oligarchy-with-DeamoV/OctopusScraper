package bootstrap

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/config"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/observability"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/storage"
)

type bootstrapStore struct {
	registerErr error
}

func (bootstrapStore) Initialize(context.Context) error { return nil }
func (bootstrapStore) Ping(context.Context) error       { return nil }
func (bootstrapStore) Close()                           {}
func (bootstrapStore) ExistingContentIDs(context.Context, []string) (map[string]struct{}, error) {
	return map[string]struct{}{}, nil
}
func (bootstrapStore) StoreContents(context.Context, []content.Content) (storage.StoreStats, error) {
	return storage.StoreStats{}, nil
}
func (bootstrapStore) ListContents(context.Context, storage.ContentListOptions) (storage.ContentListPage, error) {
	return storage.ContentListPage{}, nil
}
func (bootstrapStore) GetContent(context.Context, string) (storage.ContentRecord, bool, error) {
	return storage.ContentRecord{}, false, nil
}
func (s bootstrapStore) RegisterTarget(context.Context, string, bool) error { return s.registerErr }
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

func TestBuildSyncServiceDisabled(t *testing.T) {
	service, err := buildSyncService(
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
	registerErr := errors.New("register failed")
	if _, err := buildSyncService(
		config.ServiceConfig{},
		bootstrapStore{registerErr: registerErr},
		observability.NewMetrics("test"),
		nil,
	); !errors.Is(err, registerErr) {
		t.Fatalf("disabled registration error = %v", err)
	}
	if _, err := buildSyncService(
		config.ServiceConfig{Notion: config.NotionConfig{Enabled: true}},
		bootstrapStore{},
		observability.NewMetrics("test"),
		nil,
	); err == nil {
		t.Fatal("expected invalid Notion configuration error")
	}
	if _, err := buildSyncService(
		config.ServiceConfig{
			Notion: config.NotionConfig{
				Enabled:    true,
				APIKey:     "secret",
				DatabaseID: "database",
			},
		},
		bootstrapStore{registerErr: registerErr},
		observability.NewMetrics("test"),
		nil,
	); !errors.Is(err, registerErr) {
		t.Fatalf("enabled registration error = %v", err)
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
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	store := openTaskResultStore(
		filepath.Join(blockingPath, "tasks.sqlite3"),
		logger,
	)
	if store != nil {
		_ = store.Close()
		t.Fatal("unavailable task history path should disable persistence")
	}
}
