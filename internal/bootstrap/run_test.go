package bootstrap

import (
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/config"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/observability"
)

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
		nil,
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
		nil,
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
