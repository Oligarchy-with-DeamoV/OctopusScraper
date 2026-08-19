package config

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"
	"time"
)

func TestConfigManagerLoadAndDisabledFiltering(t *testing.T) {
	directory := t.TempDir()
	writeConfigFile(t, directory, "enabled.yaml", testScraperYAML("enabled", "/feed.xml", true))
	writeConfigFile(t, directory, "disabled.yaml", testScraperYAML("disabled", "/disabled.xml", false))
	manager := newTestConfigManager(directory)
	active, err := manager.LoadInitial(context.Background())
	if err != nil {
		t.Fatalf("LoadInitialConfig() error = %v", err)
	}
	if len(active) != 1 || active[0].ID != "enabled" {
		t.Fatalf("active scrapers = %#v", active)
	}
	all := manager.GetAllScrapers()
	if len(all) != 2 {
		t.Fatalf("all scrapers len = %d", len(all))
	}
}

func TestConfigManagerRetainsLastGoodAndRejectsDuplicates(t *testing.T) {
	directory := t.TempDir()
	_ = writeConfigFile(t, directory, "owner.yaml", testScraperYAML("feed", "/feed.xml", true))
	manager := newTestConfigManager(directory)
	if _, err := manager.LoadInitial(context.Background()); err != nil {
		t.Fatalf("LoadInitialConfig() error = %v", err)
	}
	writeConfigFile(t, directory, "owner.yaml", "id: feed\nname: Broken\n")
	changed, err := manager.Reload(context.Background())
	if err != nil {
		t.Fatalf("ReloadConfigIfChanged() error = %v", err)
	}
	if changed {
		t.Fatalf("changed = true, want false")
	}
	if route := manager.GetCurrentScrapers()[0].Route; route != "/feed.xml" {
		t.Fatalf("route = %q", route)
	}
	duplicatePath := writeConfigFile(t, directory, "duplicate.yaml", testScraperYAMLWithName("feed", "Duplicate", "/dup.xml", true))
	if _, err := manager.Reload(context.Background()); err != nil {
		t.Fatalf("ReloadConfigIfChanged() error = %v", err)
	}
	if got := manager.GetFileErrors()[duplicatePath]; got == "" {
		t.Fatalf("missing duplicate error for %s", duplicatePath)
	}
}

func TestConfigManagerRetainsRenamedLastGoodAfterInvalidEdit(t *testing.T) {
	t.Parallel()

	directory := t.TempDir()
	originalPath := writeConfigFile(
		t,
		directory,
		"original.yaml",
		testScraperYAML("feed", "/feed.xml", true),
	)
	manager := newTestConfigManager(directory)
	if _, err := manager.LoadInitial(context.Background()); err != nil {
		t.Fatal(err)
	}
	renamedPath := filepath.Join(directory, "renamed.yaml")
	if err := os.Rename(originalPath, renamedPath); err != nil {
		t.Fatal(err)
	}
	changed, err := manager.Reload(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if changed {
		t.Fatal("path-only rename changed the semantic configuration")
	}
	writeConfigFile(t, directory, "renamed.yaml", "id: feed\nname: Broken\n")
	changed, err = manager.Reload(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if changed {
		t.Fatal("invalid renamed edit changed the active configuration")
	}
	scrapers := manager.GetCurrentScrapers()
	if len(scrapers) != 1 || scrapers[0].Route != "/feed.xml" {
		t.Fatalf("last-good scraper = %#v", scrapers)
	}
	if manager.GetFileErrors()[renamedPath] == "" {
		t.Fatal("missing error for invalid renamed configuration")
	}
}

func TestConfigManagerResolvesCascadingDuplicateRestores(t *testing.T) {
	directory := t.TempDir()
	writeConfigFile(
		t,
		directory,
		"a.yaml",
		testScraperYAMLWithName("a", "A", "/a.xml", true),
	)
	writeConfigFile(
		t,
		directory,
		"b.yaml",
		testScraperYAMLWithName("b", "B", "/b.xml", true),
	)
	writeConfigFile(
		t,
		directory,
		"c.yaml",
		testScraperYAMLWithName("c", "C", "/c.xml", true),
	)
	manager := newTestConfigManager(directory)
	if _, err := manager.LoadInitial(context.Background()); err != nil {
		t.Fatal(err)
	}

	writeConfigFile(
		t,
		directory,
		"a.yaml",
		testScraperYAMLWithName("b", "A", "/changed-a.xml", true),
	)
	writeConfigFile(
		t,
		directory,
		"b.yaml",
		testScraperYAMLWithName("c", "B", "/changed-b.xml", true),
	)
	changed, err := manager.Reload(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if changed {
		t.Fatal("cascading duplicate changes should retain the last-good snapshot")
	}
	scrapers := manager.GetCurrentScrapers()
	if len(scrapers) != 3 {
		t.Fatalf("scrapers = %#v", scrapers)
	}
	for index, expectedID := range []string{"a", "b", "c"} {
		if scrapers[index].ID != expectedID {
			t.Fatalf("scraper IDs = %#v", scrapers)
		}
	}
}

func TestConfigManagerDebouncesAndRollsBackRejectedCallback(t *testing.T) {
	directory := t.TempDir()
	manager := newTestConfigManager(directory)
	if _, err := manager.LoadInitial(context.Background()); err != nil {
		t.Fatalf("LoadInitialConfig() error = %v", err)
	}
	writeConfigFile(t, directory, "feed.yaml", testScraperYAML("feed", "/feed.xml", true))
	changed, err := manager.PollOnce(context.Background())
	if err != nil {
		t.Fatalf("PollOnce() error = %v", err)
	}
	if changed {
		t.Fatalf("first poll unexpectedly changed configuration")
	}
	time.Sleep(60 * time.Millisecond)
	changed, err = manager.PollOnce(context.Background())
	if err != nil {
		t.Fatalf("PollOnce() error = %v", err)
	}
	if !changed {
		t.Fatalf("second poll did not apply debounced configuration")
	}
	manager.SetOnConfigChanged(func(context.Context, []ScraperConfig) error {
		return errors.New("reject")
	})
	writeConfigFile(t, directory, "feed.yaml", testScraperYAML("feed", "/rejected.xml", true))
	if _, err := manager.Reload(context.Background()); err == nil {
		t.Fatalf("ReloadConfigIfChanged() unexpectedly succeeded")
	}
	if route := manager.GetCurrentScrapers()[0].Route; route != "/feed.xml" {
		t.Fatalf("route = %q", route)
	}
	if manager.GetStatus().Healthy {
		t.Fatalf("status should be unhealthy after callback rejection")
	}
}

func TestLoadServiceConfigFromEnvUsesPythonDefaultsAndAliases(t *testing.T) {
	home := t.TempDir()
	t.Setenv("HOME", home)
	t.Setenv("OCTOPUS_HOST", "127.0.0.1")
	t.Setenv("SERVICE_PORT", "8080")
	t.Setenv("OCTOPUS_LOG_LEVEL", "DEBUG")
	t.Setenv("SCRAPER_CONFIG_DIR", "~/scrapers")
	t.Setenv("TASK_MANAGER_MAX_CONCURRENT", "4")
	t.Setenv("MAX_QUEUE_SIZE", "42")
	t.Setenv("OCTOPUS_TASK_RESULT_PATH", "~/tasks.sqlite3")
	t.Setenv("POSTGRES_USER", "octo")
	t.Setenv("POSTGRES_PASSWORD", "secret")
	t.Setenv("DB_HOST", "db")
	t.Setenv("POSTGRES_DB", "news")
	config, err := LoadServiceConfig()
	if err != nil {
		t.Fatalf("LoadServiceConfigFromEnv() error = %v", err)
	}
	if config.Host != "127.0.0.1" || config.Port != 8080 {
		t.Fatalf("service address = %s:%d", config.Host, config.Port)
	}
	if config.LogLevel != "DEBUG" {
		t.Fatalf("LogLevel = %q", config.LogLevel)
	}
	if config.MaxConcurrentTasks != 4 || config.MaxQueueSize != 42 {
		t.Fatalf("task manager config = max=%d queue=%d", config.MaxConcurrentTasks, config.MaxQueueSize)
	}
	if config.Database.URL != "postgres://octo:secret@db:5432/news" {
		t.Fatalf("database URL = %q", config.Database.URL)
	}
	if config.ScraperConfig.Directory != filepath.Join(home, "scrapers") {
		t.Fatalf("scraper directory = %q", config.ScraperConfig.Directory)
	}
	if config.TaskResultPath != filepath.Join(home, "tasks.sqlite3") {
		t.Fatalf("task result path = %q", config.TaskResultPath)
	}
	if config.SummaryMaxLength != 500 || config.RSSReadTimeout != 1200*time.Second {
		t.Fatalf("defaults were not preserved: %#v", config)
	}
}

func TestConfigManagerReportsHealthTransitions(t *testing.T) {
	directory := filepath.Join(t.TempDir(), "scrapers")
	manager := NewManager(FileSettings{Directory: directory}, nil)
	observed := make([]bool, 0, 2)
	manager.SetHealthObserver(func(healthy bool) {
		observed = append(observed, healthy)
	})
	if _, err := manager.LoadInitial(context.Background()); err == nil {
		t.Fatal("expected missing directory error")
	}
	if err := os.MkdirAll(directory, 0o755); err != nil {
		t.Fatal(err)
	}
	writeConfigFile(t, directory, "feed.yaml", testScraperYAML(
		"feed",
		"/feed.xml",
		true,
	))
	if _, err := manager.LoadInitial(context.Background()); err != nil {
		t.Fatal(err)
	}
	if len(observed) < 2 || observed[0] || !observed[len(observed)-1] {
		t.Fatalf("unexpected health transitions: %#v", observed)
	}
}

func TestLoadServiceConfigRejectsInvalidPorts(t *testing.T) {
	tests := []struct {
		name  string
		field string
		value string
	}{
		{name: "service text", field: "SERVICE_PORT", value: "invalid"},
		{name: "service range", field: "SERVICE_PORT", value: "65536"},
		{name: "database text", field: "DB_PORT", value: "invalid"},
		{name: "database range", field: "DB_PORT", value: "65536"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			t.Setenv("DATABASE_URL", "")
			t.Setenv(test.field, test.value)
			if _, err := LoadServiceConfig(); err == nil {
				t.Fatalf("expected %s=%q to fail", test.field, test.value)
			}
		})
	}
}

func TestLoadServiceConfigBuildsIPv6DatabaseURL(t *testing.T) {
	t.Setenv("DATABASE_URL", "")
	t.Setenv("DB_HOST", "::1")
	serviceConfig, err := LoadServiceConfig()
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(serviceConfig.Database.URL, "@[::1]:5432/") {
		t.Fatalf("database URL = %q", serviceConfig.Database.URL)
	}
}

func TestLoadServiceConfigNormalizesLegacyPostgresDatabaseURL(t *testing.T) {
	t.Setenv(
		"DATABASE_URL",
		"postgresql+psycopg://octopus:secret@db:5432/news?sslmode=require",
	)
	serviceConfig, err := LoadServiceConfig()
	if err != nil {
		t.Fatal(err)
	}
	if serviceConfig.Database.URL !=
		"postgresql://octopus:secret@db:5432/news?sslmode=require" {
		t.Fatalf("database URL = %q", serviceConfig.Database.URL)
	}
}

func TestLoadServiceConfigRejectsLegacySQLiteDatabaseURL(t *testing.T) {
	t.Setenv("DATABASE_URL", "sqlite:///contents.sqlite3")
	if _, err := LoadServiceConfig(); err == nil ||
		!strings.Contains(err.Error(), "requires PostgreSQL") {
		t.Fatalf("LoadServiceConfig() error = %v", err)
	}
}

func TestConfigManagerReloadsOrderOnlyChanges(t *testing.T) {
	t.Run("processor order", func(t *testing.T) {
		directory := t.TempDir()
		path := writeConfigFile(t, directory, "feed.yaml", `
id: feed
name: Feed
enabled: true
fetcher: direct_rss
hub_root: https://example.com
route: /feed.xml
content_processor_configs:
  html_content:
    priority: 5
  llm_summary:
    priority: 5
`)
		manager := newTestConfigManager(directory)
		if _, err := manager.LoadInitial(context.Background()); err != nil {
			t.Fatal(err)
		}
		writeConfigFile(t, directory, filepath.Base(path), `
id: feed
name: Feed
enabled: true
fetcher: direct_rss
hub_root: https://example.com
route: /feed.xml
content_processor_configs:
  llm_summary:
    priority: 5
  html_content:
    priority: 5
`)
		changed, err := manager.Reload(context.Background())
		if err != nil {
			t.Fatal(err)
		}
		if !changed {
			t.Fatal("processor order-only edit was not applied")
		}
		order := manager.GetCurrentScrapers()[0].ContentProcessorOrder
		if len(order) != 2 ||
			order[0] != "llm_summary" ||
			order[1] != "html_content" {
			t.Fatalf("processor order = %v", order)
		}
	})

	t.Run("category order", func(t *testing.T) {
		directory := t.TempDir()
		writeConfigFile(t, directory, "feed.yaml", `
id: feed
name: Feed
enabled: true
fetcher: direct_rss
hub_root: https://example.com
route: /feed.xml
content_processor_configs:
  llm_tags:
    custom_categories:
      finance:
        - market
      technology:
        - software
`)
		manager := newTestConfigManager(directory)
		if _, err := manager.LoadInitial(context.Background()); err != nil {
			t.Fatal(err)
		}
		writeConfigFile(t, directory, "feed.yaml", `
id: feed
name: Feed
enabled: true
fetcher: direct_rss
hub_root: https://example.com
route: /feed.xml
content_processor_configs:
  llm_tags:
    custom_categories:
      technology:
        - software
      finance:
        - market
`)
		changed, err := manager.Reload(context.Background())
		if err != nil {
			t.Fatal(err)
		}
		if !changed {
			t.Fatal("category order-only edit was not applied")
		}
		order := manager.GetCurrentScrapers()[0].
			ProcessorCategoryOrders["llm_tags"]
		if len(order) != 2 ||
			order[0] != "technology" ||
			order[1] != "finance" {
			t.Fatalf("category order = %v", order)
		}
		diff := manager.GetLastDiff()
		if diff == nil ||
			len(diff.Modified) != 1 ||
			!slices.Contains(
				diff.Modified[0].Fields,
				"content_processor_configs",
			) {
			t.Fatalf("diff = %#v", diff)
		}
	})
}

func TestLoadServiceConfigRejectsInvalidScalarValues(t *testing.T) {
	tests := []struct {
		name  string
		field string
		value string
	}{
		{name: "debug boolean", field: "DEBUG", value: "sometimes"},
		{name: "notion boolean", field: "NOTION_SYNC_ENABLED", value: "enabled"},
		{name: "non-finite timeout", field: "RSSHUB_READ_TIMEOUT", value: "NaN"},
		{name: "duration overflow", field: "RESULT_RETENTION_HOURS", value: "999999999999"},
		{name: "pool overflow", field: "DB_POOL_SIZE", value: "2147483648"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			t.Setenv(test.field, test.value)
			if _, err := LoadServiceConfig(); err == nil {
				t.Fatalf("expected %s=%q to fail", test.field, test.value)
			}
		})
	}
}

func TestLoaderAndStartExposeIntegrationAPI(t *testing.T) {
	directory := t.TempDir()
	writeConfigFile(t, directory, "feed.yaml", testScraperYAML("feed", "/feed.xml", true))

	loader := NewLoader()
	if _, err := loader.Load(filepath.Join(directory, "feed.yaml")); err != nil {
		t.Fatalf("Loader.Load() error = %v", err)
	}

	manager := NewManager(FileSettings{
		Directory:    directory,
		PollInterval: 10 * time.Millisecond,
		Debounce:     5 * time.Millisecond,
	}, nil)
	if _, err := manager.LoadInitial(context.Background()); err != nil {
		t.Fatalf("LoadInitial() error = %v", err)
	}

	started := make(chan struct{}, 1)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go func() {
		_ = manager.Start(ctx, func(scrapers []ScraperConfig) error {
			if len(scrapers) == 1 && scrapers[0].Route == "/updated.xml" {
				select {
				case started <- struct{}{}:
				default:
				}
				cancel()
			}
			return nil
		})
	}()
	writeConfigFile(t, directory, "feed.yaml", testScraperYAML("feed", "/updated.xml", true))
	select {
	case <-started:
	case <-time.After(time.Second):
		t.Fatal("Start() did not invoke callback after config update")
	}

	if len(manager.CurrentScrapers()) != 1 || len(manager.AllScrapers()) != 1 {
		t.Fatalf("manager scrapers = %#v %#v", manager.CurrentScrapers(), manager.AllScrapers())
	}
	if manager.Status().FileErrors == nil || manager.FileErrors() == nil {
		t.Fatal("status/file errors should be available")
	}
}

func newTestConfigManager(directory string) *ConfigManager {
	return NewManager(FileSettings{
		Directory:    directory,
		PollInterval: 20 * time.Millisecond,
		Debounce:     40 * time.Millisecond,
	}, nil)
}
