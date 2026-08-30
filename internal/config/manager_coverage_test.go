package config

import (
	"context"
	"errors"
	"log/slog"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestConfigManagerObserversStatusAndValidation(t *testing.T) {
	manager := NewConfigManager(FileSettings{PollInterval: time.Second})
	if manager == nil {
		t.Fatal("NewConfigManager returned nil")
	}
	manager.now = func() time.Time { return time.Unix(100, 0) }
	manager.SetRefreshObserver(func(bool) {})
	status := manager.GetStatus()
	if status.LastCheck != time.Unix(100, 0) || !status.NextCheck.Equal(time.Unix(101, 0)) {
		t.Fatalf("status timestamps = %#v", status)
	}
	if got := manager.ValidateScrapersConfig([]ScraperConfig{
		{ID: "same", Name: "duplicate"},
		{ID: "same", Name: "duplicate"},
	}); len(got) != 2 {
		t.Fatalf("validation errors = %v", got)
	}
	if manager.GetCurrentVersion() != nil || manager.GetLastDiff() != nil {
		t.Fatal("empty manager unexpectedly has version or diff")
	}
	if (ScraperConfig{Enabled: true}).Status() != "Active" ||
		(ScraperConfig{}).Status() != "Inactive" {
		t.Fatal("unexpected scraper status")
	}
}

func TestConfigManagerDirectoryFiltersAndOversizeRetention(t *testing.T) {
	directory := t.TempDir()
	writeConfigFile(t, directory, ".hidden.yaml", "invalid")
	writeConfigFile(t, directory, "ignored.txt", "invalid")
	if err := os.Mkdir(filepath.Join(directory, "nested"), 0o755); err != nil {
		t.Fatal(err)
	}
	writeConfigFile(t, directory, "feed.yaml", testScraperYAML("feed", "/feed", true))
	oversize := filepath.Join(directory, "large.yaml")
	if err := os.WriteFile(oversize, make([]byte, MaxConfigFileBytes+1), 0o600); err != nil {
		t.Fatal(err)
	}
	symlink := filepath.Join(directory, "link.yaml")
	if err := os.Symlink(filepath.Join(directory, "feed.yaml"), symlink); err != nil {
		t.Fatal(err)
	}
	manager := NewManager(FileSettings{Directory: directory}, slog.Default())
	if _, err := manager.LoadInitial(context.Background()); err != nil {
		t.Fatal(err)
	}
	if len(manager.GetCurrentScrapers()) != 1 || len(manager.GetFileErrors()) != 1 {
		t.Fatalf("scrapers/errors = %v/%v", manager.GetCurrentScrapers(), manager.GetFileErrors())
	}
	if _, ok := manager.GetFileErrors()[oversize]; !ok {
		t.Fatalf("missing oversize error: %v", manager.GetFileErrors())
	}
	if manager.GetStatus().ErrorMessage == "" {
		t.Fatal("status should expose file errors")
	}
}

func TestConfigManagerWatchAndStartCancellation(t *testing.T) {
	manager := NewManager(FileSettings{PollInterval: time.Millisecond}, nil)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if err := manager.Watch(ctx); !errors.Is(err, context.Canceled) {
		t.Fatalf("Watch() error = %v", err)
	}
	ctx, cancel = context.WithCancel(context.Background())
	cancel()
	if err := manager.Start(ctx, func([]ScraperConfig) error { return nil }); !errors.Is(err, context.Canceled) {
		t.Fatalf("Start() error = %v", err)
	}
	manager = NewManager(FileSettings{Directory: t.TempDir(), PollInterval: time.Millisecond}, slog.Default())
	ctx, cancel = context.WithCancel(context.Background())
	go func() {
		time.Sleep(15 * time.Millisecond)
		cancel()
	}()
	if err := manager.Start(ctx, nil); !errors.Is(err, context.Canceled) {
		t.Fatalf("Start() with logger error = %v", err)
	}
}

func TestConfigManagerAppliesDiffAndCopiesSnapshots(t *testing.T) {
	directory := t.TempDir()
	writeConfigFile(t, directory, "a.yaml", testScraperYAML("a", "/a", true))
	manager := newTestConfigManager(directory)
	if _, err := manager.LoadInitial(context.Background()); err != nil {
		t.Fatal(err)
	}
	writeConfigFile(t, directory, "a.yaml", testScraperYAML("a", "/changed", true))
	writeConfigFile(t, directory, "b.yaml", testScraperYAML("b", "/b", false))
	changed, err := manager.Reload(context.Background())
	if err != nil || !changed {
		t.Fatalf("Reload() = %v, %v", changed, err)
	}
	if manager.GetCurrentVersion() == nil || manager.GetLastDiff() == nil {
		t.Fatal("applied update did not record version/diff")
	}
	diff := manager.GetLastDiff()
	if len(diff.Added) != 1 || diff.Added[0] != "b" ||
		len(diff.Modified) != 1 || diff.Modified[0].ID != "a" {
		t.Fatalf("diff = %#v", diff)
	}
	scrapers := manager.GetAllScrapers()
	scrapers[0].FetchParams["mutated"] = true
	if _, found := manager.GetAllScrapers()[0].FetchParams["mutated"]; found {
		t.Fatal("returned scraper was not cloned")
	}
}

func TestConfigManagerRejectsCallbackAndReportsRefreshObserver(t *testing.T) {
	directory := t.TempDir()
	writeConfigFile(t, directory, "feed.yaml", testScraperYAML("feed", "/old", true))
	manager := newTestConfigManager(directory)
	var refreshes []bool
	manager.SetRefreshObserver(func(success bool) { refreshes = append(refreshes, success) })
	if _, err := manager.LoadInitial(context.Background()); err != nil {
		t.Fatal(err)
	}
	manager.SetOnConfigChanged(func(context.Context, []ScraperConfig) error {
		return errors.New("rejected")
	})
	writeConfigFile(t, directory, "feed.yaml", testScraperYAML("feed", "/new", true))
	if _, err := manager.Reload(context.Background()); err == nil {
		t.Fatal("callback rejection was ignored")
	}
	if got := manager.GetCurrentScrapers()[0].Route; got != "/old" {
		t.Fatalf("route after rejection = %q", got)
	}
	if len(refreshes) < 2 || refreshes[len(refreshes)-1] {
		t.Fatalf("refresh observer values = %v", refreshes)
	}
	manager.SetOnConfigChanged(nil)
	if _, err := manager.Reload(context.Background()); err != nil {
		t.Fatal(err)
	}
}

func TestConfigManagerCoversCandidateAndHashBranches(t *testing.T) {
	manager := NewManager(FileSettings{}, nil)
	path := filepath.Join(t.TempDir(), "feed.yaml")
	scraper := ScraperConfig{ID: "feed", Name: "Feed", Enabled: true}
	manager.acceptedByPath[path] = scraper
	manager.fileHashes[path] = "same"
	candidate, fileErrors := manager.buildCandidate(map[string]string{path: "same"})
	if len(fileErrors) != 0 || candidate[path].ID != "feed" {
		t.Fatalf("unchanged candidate = %#v, %v", candidate, fileErrors)
	}
	oversize := "oversize:123"
	manager.fileHashes[path] = "old"
	candidate, fileErrors = manager.buildCandidate(map[string]string{path: oversize})
	if candidate[path].ID != "feed" || fileErrors[path] == "" {
		t.Fatalf("oversize retention = %#v, %v", candidate, fileErrors)
	}
	manager.loader = configLoaderFunc(func(string) (ScraperConfig, error) {
		return ScraperConfig{}, errors.New("bad load")
	})
	candidate, fileErrors = manager.buildCandidate(map[string]string{path: "changed"})
	if candidate[path].ID != "feed" || fileErrors[path] == "" {
		t.Fatalf("invalid retention = %#v, %v", candidate, fileErrors)
	}
	if _, err := configHash([]ScraperConfig{{FetchParams: map[string]any{"bad": func() {}}}}); err == nil {
		t.Fatal("configHash accepted non-JSON value")
	}
	manager.acceptedByPath = map[string]ScraperConfig{}
	manager.loader = configLoaderFunc(func(path string) (ScraperConfig, error) {
		return ScraperConfig{ID: "same", Name: filepath.Base(path)}, nil
	})
	candidate, fileErrors = manager.buildCandidate(map[string]string{"a": "a", "b": "b"})
	if len(candidate) != 0 || len(fileErrors) != 2 {
		t.Fatalf("duplicate without owner = %#v, %v", candidate, fileErrors)
	}
	if got := sortedScrapers(map[string]ScraperConfig{
		"z": {ID: "z", Priority: 1},
		"a": {ID: "a", Priority: 1},
	}); got[0].ID != "a" {
		t.Fatalf("tie sorting = %#v", got)
	}
	manager.logger = slog.Default()
	manager.acceptedByPath = map[string]ScraperConfig{}
	_, _ = manager.buildCandidate(map[string]string{"a": "a", "b": "b"})
}

type configLoaderFunc func(string) (ScraperConfig, error)

func (f configLoaderFunc) Load(path string) (ScraperConfig, error) {
	return f(path)
}

func TestConfigManagerDiffAndSummaryHelpers(t *testing.T) {
	old := ScraperConfig{ID: "same", Name: "old", ContentProcessorOrder: []string{"a"}}
	current := ScraperConfig{ID: "same", Name: "new", ContentProcessorOrder: []string{"b"}}
	diff := computeScrapersDiff(
		[]ScraperConfig{old, {ID: "removed", Name: "Removed"}},
		[]ScraperConfig{current, {ID: "other", Name: "Other"}, {ID: "added", Name: "Added"}},
	)
	if len(diff.Added) != 2 || len(diff.Removed) != 1 || len(diff.Modified) != 1 {
		t.Fatalf("diff = %#v", diff)
	}
	if summary := createChangeSummary(diff); summary == "" {
		t.Fatal("empty diff summary")
	}
	if summary := createChangeSummary(Diff{}); summary != "Configuration updated" {
		t.Fatalf("empty summary = %q", summary)
	}
	channel := make(chan int)
	if !valuesEqual(channel, channel) {
		t.Fatal("valuesEqual fallback should compare formatted values")
	}
}
