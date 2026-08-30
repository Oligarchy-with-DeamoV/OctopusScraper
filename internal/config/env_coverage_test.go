package config

import (
	"path/filepath"
	"strings"
	"testing"
	"time"
)

var serviceEnvNames = []string{
	"DATABASE_URL", "DB_PORT", "POSTGRES_USER", "POSTGRES_PASSWORD",
	"DB_HOST", "POSTGRES_DB", "DEBUG", "OCTOPUS_DEBUG",
	"NOTION_SYNC_ENABLED", "MCP_ENABLED", "MCP_API_TOKEN", "SERVICE_PORT",
	"OCTOPUS_PORT", "SCRAPER_CONFIG_POLL_INTERVAL", "SCRAPER_CONFIG_DEBOUNCE_SECONDS",
	"DB_POOL_SIZE", "DB_MAX_OVERFLOW", "DB_CONNECT_TIMEOUT_SECONDS",
	"NOTION_SYNC_INTERVAL_SECONDS", "NOTION_SYNC_BATCH_SIZE",
	"NOTION_SYNC_MAX_ATTEMPTS", "NOTION_SYNC_LEASE_SECONDS",
	"NOTION_UPLOAD_RETRY_DELAY", "TASK_MANAGER_MAX_CONCURRENT",
	"MAX_CONCURRENT_TASKS", "TASK_MANAGER_MAX_QUEUE_SIZE", "MAX_QUEUE_SIZE",
	"RESULT_RETENTION_HOURS", "RSSHUB_CONNECT_TIMEOUT", "RSSHUB_READ_TIMEOUT",
	"OCTOPUS_SUMMARY_MAX_LENGTH", "SCRAPER_TIMEOUT", "UPLOAD_TIMEOUT",
	"UPLOAD_MAX_RETRIES", "LOG_LEVEL", "OCTOPUS_LOG_LEVEL", "LOG_FORMAT",
	"OCTOPUS_LOG_FORMAT", "LOG_FILE", "LOG_RETENTION_DAYS", "SERVICE_HOST",
	"OCTOPUS_HOST", "ENVIRONMENT", "SCRAPER_CONFIG_DIR",
	"OCTOPUS_TASK_RESULT_PATH", "TASK_RESULT_PATH", "TASK_RESULTS_PATH",
	"NOTION_API_KEY", "NOTION_CONTENT_DATABASE_ID",
}

func clearServiceEnv(t *testing.T) {
	t.Helper()
	for _, name := range serviceEnvNames {
		t.Setenv(name, "")
	}
}

func TestLoadServiceConfigEnvironmentMatrix(t *testing.T) {
	clearServiceEnv(t)
	home := t.TempDir()
	t.Setenv("HOME", home)
	t.Setenv("DATABASE_URL", "postgresql://user:pass@db:5432/app")
	t.Setenv("DEBUG", "true")
	t.Setenv("NOTION_SYNC_ENABLED", "true")
	t.Setenv("MCP_ENABLED", "true")
	t.Setenv("MCP_API_TOKEN", "token")
	t.Setenv("SERVICE_PORT", "8081")
	t.Setenv("SCRAPER_CONFIG_POLL_INTERVAL", "1.5")
	t.Setenv("SCRAPER_CONFIG_DEBOUNCE_SECONDS", "0.25")
	t.Setenv("DB_POOL_SIZE", "8")
	t.Setenv("DB_MAX_OVERFLOW", "2")
	t.Setenv("DB_CONNECT_TIMEOUT_SECONDS", "11")
	t.Setenv("NOTION_SYNC_INTERVAL_SECONDS", "61")
	t.Setenv("NOTION_SYNC_BATCH_SIZE", "12")
	t.Setenv("NOTION_SYNC_MAX_ATTEMPTS", "4")
	t.Setenv("NOTION_SYNC_LEASE_SECONDS", "301")
	t.Setenv("NOTION_UPLOAD_RETRY_DELAY", "31")
	t.Setenv("MAX_CONCURRENT_TASKS", "6")
	t.Setenv("MAX_QUEUE_SIZE", "99")
	t.Setenv("RESULT_RETENTION_HOURS", "24")
	t.Setenv("RSSHUB_CONNECT_TIMEOUT", "2.5")
	t.Setenv("RSSHUB_READ_TIMEOUT", "3.5")
	t.Setenv("OCTOPUS_SUMMARY_MAX_LENGTH", "700")
	t.Setenv("SCRAPER_TIMEOUT", "12")
	t.Setenv("UPLOAD_TIMEOUT", "16")
	t.Setenv("UPLOAD_MAX_RETRIES", "5")
	t.Setenv("LOG_LEVEL", "warning")
	t.Setenv("LOG_FORMAT", "plain")
	t.Setenv("LOG_FILE", "~/service.log")
	t.Setenv("LOG_RETENTION_DAYS", "7")
	t.Setenv("SERVICE_HOST", "127.0.0.1")
	t.Setenv("ENVIRONMENT", "test")
	t.Setenv("SCRAPER_CONFIG_DIR", "~/scrapers")
	t.Setenv("TASK_RESULTS_PATH", "~/results.sqlite3")
	t.Setenv("NOTION_API_KEY", "key")
	t.Setenv("NOTION_CONTENT_DATABASE_ID", "db")

	got, err := LoadServiceConfigFromEnv()
	if err != nil {
		t.Fatal(err)
	}
	if !got.Debug || !got.Notion.Enabled || !got.MCP.Enabled ||
		got.Port != 8081 || got.ScraperConfig.PollInterval != 1500*time.Millisecond ||
		got.ScraperConfig.Debounce != 250*time.Millisecond ||
		got.Database.PoolSize != 8 || got.Database.MaxOverflow != 2 ||
		got.Notion.BatchSize != 12 || got.Notion.MaxAttempts != 4 ||
		got.MaxConcurrentTasks != 6 || got.MaxQueueSize != 99 ||
		got.SummaryMaxLength != 700 || got.UploadMaxRetries != 5 ||
		got.LogLevel != "warning" || got.LogFormat != "json" {
		t.Fatalf("environment matrix not applied: %#v", got)
	}
	if got.LogFile != filepath.Join(home, "service.log") ||
		got.ScraperConfig.Directory != filepath.Join(home, "scrapers") ||
		got.TaskResultPath != filepath.Join(home, "results.sqlite3") ||
		got.Notion.APIKey != "key" || got.Notion.DatabaseID != "db" {
		t.Fatalf("paths and Notion settings not applied: %#v", got)
	}
}

func TestLoadServiceConfigEnvironmentErrors(t *testing.T) {
	tests := []struct {
		name  string
		env   map[string]string
		match string
	}{
		{"database scheme", map[string]string{"DATABASE_URL": "mysql://db/app"}, "unsupported scheme"},
		{"poll interval", map[string]string{"SCRAPER_CONFIG_POLL_INTERVAL": "0"}, "greater than zero"},
		{"debounce", map[string]string{"SCRAPER_CONFIG_DEBOUNCE_SECONDS": "x"}, "parse SCRAPER_CONFIG_DEBOUNCE_SECONDS"},
		{"db pool negative", map[string]string{"DB_POOL_SIZE": "-1"}, "greater than zero"},
		{"db overflow negative", map[string]string{"DB_MAX_OVERFLOW": "-1"}, "zero or greater"},
		{"connect timeout", map[string]string{"DB_CONNECT_TIMEOUT_SECONDS": "x"}, "parse DB_CONNECT_TIMEOUT_SECONDS"},
		{"notion interval", map[string]string{"NOTION_SYNC_INTERVAL_SECONDS": "0"}, "greater than zero"},
		{"notion batch", map[string]string{"NOTION_SYNC_BATCH_SIZE": "x"}, "parse NOTION_SYNC_BATCH_SIZE"},
		{"notion attempts", map[string]string{"NOTION_SYNC_MAX_ATTEMPTS": "0"}, "greater than zero"},
		{"notion lease", map[string]string{"NOTION_SYNC_LEASE_SECONDS": "x"}, "parse NOTION_SYNC_LEASE_SECONDS"},
		{"notion retry", map[string]string{"NOTION_UPLOAD_RETRY_DELAY": "0"}, "greater than zero"},
		{"task concurrency", map[string]string{"TASK_MANAGER_MAX_CONCURRENT": "0"}, "greater than zero"},
		{"task queue", map[string]string{"TASK_MANAGER_MAX_QUEUE_SIZE": "x"}, "parse TASK_MANAGER_MAX_QUEUE_SIZE"},
		{"retention", map[string]string{"RESULT_RETENTION_HOURS": "0"}, "greater than zero"},
		{"rss connect", map[string]string{"RSSHUB_CONNECT_TIMEOUT": "0"}, "greater than zero"},
		{"rss read", map[string]string{"RSSHUB_READ_TIMEOUT": "x"}, "parse RSSHUB_READ_TIMEOUT"},
		{"summary length", map[string]string{"OCTOPUS_SUMMARY_MAX_LENGTH": "0"}, "greater than zero"},
		{"scraper timeout", map[string]string{"SCRAPER_TIMEOUT": "x"}, "parse SCRAPER_TIMEOUT"},
		{"upload timeout", map[string]string{"UPLOAD_TIMEOUT": "0"}, "greater than zero"},
		{"upload retries", map[string]string{"UPLOAD_MAX_RETRIES": "x"}, "parse UPLOAD_MAX_RETRIES"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			clearServiceEnv(t)
			for key, value := range test.env {
				t.Setenv(key, value)
			}
			_, err := LoadServiceConfigFromEnv()
			if err == nil || !strings.Contains(err.Error(), test.match) {
				t.Fatalf("error = %v, want %q", err, test.match)
			}
		})
	}
}

func TestEnvironmentHelperMatrices(t *testing.T) {
	t.Run("database normalization", func(t *testing.T) {
		cases := []struct {
			input string
			want  string
			err   string
		}{
			{"postgres://db/app", "postgres://db/app", ""},
			{"POSTGRESQL://db/app", "POSTGRESQL://db/app", ""},
			{"postgresql+psycopg://db/app", "postgresql://db/app", ""},
			{"postgresql+psycopg2://db/app", "postgresql://db/app", ""},
			{"db/app", "db/app", ""},
			{"sqlite://db", "", "SQLite"},
		}
		for _, test := range cases {
			got, err := normalizeDatabaseURL(test.input)
			if test.err != "" {
				if err == nil || !strings.Contains(err.Error(), test.err) {
					t.Fatalf("normalizeDatabaseURL(%q) error = %v", test.input, err)
				}
				continue
			}
			if err != nil || got != test.want {
				t.Fatalf("normalizeDatabaseURL(%q) = %q, %v", test.input, got, err)
			}
		}
	})
	t.Run("numeric helpers", func(t *testing.T) {
		if _, err := nonNegativeInt("x", 1, "FIELD"); err == nil {
			t.Fatal("nonNegativeInt accepted text")
		}
		for _, raw := range []string{"NaN", "+Inf", "-Inf"} {
			if _, err := positiveFloatDuration(raw, 1, "FIELD"); err == nil {
				t.Fatalf("positiveFloatDuration accepted %q", raw)
			}
		}
		if _, err := positiveFloatDuration("0.0000000001", 1, "FIELD"); err == nil {
			t.Fatal("sub-nanosecond duration accepted")
		}
		if _, err := positiveFloatDuration("1e30", 1, "FIELD"); err == nil {
			t.Fatal("overflow duration accepted")
		}
		if _, err := positiveDuration("999999999999", 1, "FIELD", time.Hour); err == nil {
			t.Fatal("overflow positiveDuration accepted")
		}
	})
	t.Run("aliases and defaults", func(t *testing.T) {
		clearServiceEnv(t)
		t.Setenv("OCTOPUS_DEBUG", "true")
		t.Setenv("OCTOPUS_PORT", "8123")
		t.Setenv("OCTOPUS_LOG_LEVEL", "ERROR")
		t.Setenv("OCTOPUS_LOG_FORMAT", "plain")
		t.Setenv("MAX_CONCURRENT_TASKS", "2")
		t.Setenv("MAX_QUEUE_SIZE", "3")
		got, err := LoadServiceConfig()
		if err != nil {
			t.Fatal(err)
		}
		if !got.Debug || got.Port != 8123 || got.LogLevel != "ERROR" ||
			got.MaxConcurrentTasks != 2 || got.MaxQueueSize != 3 {
			t.Fatalf("aliases not applied: %#v", got)
		}
	})
}

func TestFirstNonEmptyEnvIgnoresWhitespace(t *testing.T) {
	t.Setenv("OCTOPUS_TEST_EMPTY", "  ")
	t.Setenv("OCTOPUS_TEST_VALUE", " value ")
	if got := firstNonEmptyEnv("OCTOPUS_TEST_EMPTY", "OCTOPUS_TEST_VALUE"); got != "value" {
		t.Fatalf("firstNonEmptyEnv() = %q", got)
	}
	if got := firstEnvOrDefault([]string{"OCTOPUS_TEST_EMPTY"}, "fallback"); got != "fallback" {
		t.Fatalf("firstEnvOrDefault() = %q", got)
	}
}
