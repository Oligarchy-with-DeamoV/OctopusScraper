package app

import (
	"context"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/config"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/fetcher"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/processor"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/storage"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/task"
)

type staticFetcher struct {
	items []content.Content
}

func (f staticFetcher) Fetch(context.Context, map[string]any) ([]content.Content, error) {
	return append([]content.Content(nil), f.items...), nil
}

type staticFetcherFactory struct {
	fetcher fetcher.Fetcher
}

func (f staticFetcherFactory) Create(string, map[string]any) (fetcher.Fetcher, error) {
	return f.fetcher, nil
}

type noProcessorFactory struct{}

func (noProcessorFactory) Create(string, map[string]any) (processor.Processor, error) {
	panic("unexpected processor")
}
func (noProcessorFactory) Supported(string) bool { return false }

type memoryStore struct {
	existing map[string]struct{}
	stored   []content.Content
	closed   atomic.Bool
	pingErr  error
	syncErr  error
}

func (s *memoryStore) Initialize(context.Context) error { return nil }
func (s *memoryStore) Ping(context.Context) error       { return s.pingErr }
func (s *memoryStore) Close()                           { s.closed.Store(true) }
func (s *memoryStore) ExistingContentIDs(
	context.Context,
	[]string,
) (map[string]struct{}, error) {
	return s.existing, nil
}
func (s *memoryStore) StoreContents(
	_ context.Context,
	items []content.Content,
) (storage.StoreStats, error) {
	s.stored = append([]content.Content(nil), items...)
	return storage.StoreStats{
		Requested: len(items),
		Inserted:  len(items),
	}, nil
}
func (s *memoryStore) ClaimContents(
	context.Context,
	string,
	int,
	time.Duration,
	int,
) ([]content.Content, error) {
	return nil, nil
}
func (s *memoryStore) RenewClaim(
	context.Context,
	string,
	string,
	time.Duration,
) (bool, error) {
	return true, nil
}
func (s *memoryStore) MarkSynced(context.Context, string, string) (bool, error) {
	return true, nil
}
func (s *memoryStore) MarkSyncFailed(
	context.Context,
	string,
	string,
	string,
	int,
) (bool, error) {
	return true, nil
}
func (s *memoryStore) SyncCounts(context.Context) (map[string]int64, error) {
	return map[string]int64{"pending": 2}, s.syncErr
}

func TestExecutorFiltersDeduplicatesAndStores(t *testing.T) {
	source := "Feed"
	store := &memoryStore{existing: map[string]struct{}{"existing": {}}}
	executor := NewExecutor(
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		staticFetcherFactory{fetcher: staticFetcher{items: []content.Content{
			{ContentID: "", Title: "invalid", Link: "https://example.com", Content: "body"},
			{ContentID: "existing", Title: "old", Link: "https://example.com/old", Content: "body"},
			{ContentID: "new", Title: "new", Link: "https://example.com/new", Content: "body"},
			{ContentID: "new", Title: "duplicate", Link: "https://example.com/new", Content: "body"},
		}}},
		noProcessorFactory{},
		store,
	)
	result, err := executor.Execute(context.Background(), task.ScraperTask{
		ScraperName: "Feed",
		ScraperConfig: config.ScraperConfig{
			Fetcher:                 "rsshub",
			HubRoot:                 "https://example.com",
			Route:                   "/feed",
			FetchParams:             map[string]any{},
			ContentProcessorConfigs: map[string]map[string]any{},
		},
		DefaultKeywords: []string{"default", "default"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if result.ItemsFetched != 1 || len(store.stored) != 1 {
		t.Fatalf("unexpected result: %+v stored=%+v", result, store.stored)
	}
	if store.stored[0].ScraperName == nil || *store.stored[0].ScraperName != source {
		t.Fatalf("missing source: %+v", store.stored[0])
	}
	if len(store.stored[0].Keywords) != 1 || store.stored[0].Keywords[0] != "default" {
		t.Fatalf("unexpected keywords: %+v", store.stored[0].Keywords)
	}
}

type staticConfigSource struct {
	scrapers []config.ScraperConfig
}

func (s staticConfigSource) CurrentScrapers() []config.ScraperConfig {
	return append([]config.ScraperConfig(nil), s.scrapers...)
}

type runtimeSyncService struct {
	started atomic.Bool
	stopped atomic.Bool
	calls   atomic.Int32
	result  map[string]any
	err     error
}

func (s *runtimeSyncService) RunOnce(context.Context) (map[string]any, error) {
	s.calls.Add(1)
	return s.result, s.err
}

func (s *runtimeSyncService) Start(context.Context) {
	s.started.Store(true)
}

func (s *runtimeSyncService) Stop(context.Context) error {
	s.stopped.Store(true)
	return s.err
}

type successfulExecutor struct {
	tasks chan<- task.ScraperTask
}

func (e successfulExecutor) Execute(
	_ context.Context,
	submitted task.ScraperTask,
) (task.ExecutionResult, error) {
	if e.tasks != nil {
		e.tasks <- submitted
	}
	return task.ExecutionResult{ItemsFetched: 1}, nil
}

func TestRuntimeOperations(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	store := &memoryStore{}
	syncService := &runtimeSyncService{
		result: map[string]any{"enabled": true, "synced_count": 1},
	}
	configSource := staticConfigSource{scrapers: []config.ScraperConfig{
		{
			ID:      "enabled",
			Name:    "Enabled",
			Enabled: true,
			Fetcher: "direct_rss",
			Route:   "https://example.com/feed",
		},
	}}
	runtime := NewRuntime(
		logger,
		configSource,
		store,
		syncService,
		time.Minute,
	)

	if _, _, err := runtime.TriggerScraper(context.Background()); err == nil {
		t.Fatal("expected trigger before task manager setup to fail")
	}
	submittedTasks := make(chan task.ScraperTask, 1)
	manager, err := task.NewManager(
		logger,
		successfulExecutor{tasks: submittedTasks},
		1,
		10,
		time.Hour,
		nil,
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	runtime.SetTaskManager(manager)

	batchID, scraperCount, err := runtime.TriggerScraper(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if batchID == "" || scraperCount != 1 {
		t.Fatalf("unexpected trigger result: %q %d", batchID, scraperCount)
	}
	select {
	case submitted := <-submittedTasks:
		if submitted.Timeout != time.Minute {
			t.Fatalf("submitted timeout = %s", submitted.Timeout)
		}
	case <-time.After(time.Second):
		t.Fatal("scraper task was not executed")
	}
	if result, err := runtime.TriggerUpload(context.Background()); err != nil ||
		result["synced_count"] != 1 {
		t.Fatalf("unexpected upload result: %#v, %v", result, err)
	}
	if err := runtime.StoragePing(context.Background()); err != nil {
		t.Fatal(err)
	}
	status, err := runtime.SyncStatus(context.Background())
	if err != nil || status["enabled"] != true {
		t.Fatalf("unexpected sync status: %#v, %v", status, err)
	}
	if runtime.TaskStatistics().TotalTasks != 1 {
		t.Fatalf("unexpected task statistics: %#v", runtime.TaskStatistics())
	}
	if len(runtime.ListTasks(nil, 10)) != 1 {
		t.Fatalf("unexpected task list: %#v", runtime.ListTasks(nil, 10))
	}
	tasks := manager.List(nil, 10)
	if _, found := runtime.TaskResult(tasks[0].TaskID); !found {
		t.Fatal("task result not found")
	}
	if state := runtime.ScraperRuntime("enabled"); state["initialized"] != true ||
		state["fetcher_type"] != "DirectRSS" {
		t.Fatalf("unexpected scraper runtime: %#v", state)
	}
	if state := runtime.ScraperRuntime("missing"); state["initialized"] != false {
		t.Fatalf("unexpected missing scraper runtime: %#v", state)
	}
	if err := runtime.Stop(context.Background()); err != nil {
		t.Fatal(err)
	}
	if !syncService.stopped.Load() || !store.closed.Load() {
		t.Fatal("runtime dependencies were not stopped")
	}
}

func TestOrderedProcessorNamesPreservesConfiguredOrder(t *testing.T) {
	scraper := config.ScraperConfig{
		ContentProcessorConfigs: map[string]map[string]any{
			"html_content": {},
			"llm_summary":  {},
			"llm_tags":     {},
		},
		ContentProcessorOrder: []string{"llm_tags", "html_content"},
	}
	got := orderedProcessorNames(scraper)
	want := []string{"llm_tags", "html_content", "llm_summary"}
	if fmt.Sprint(got) != fmt.Sprint(want) {
		t.Fatalf("processor order = %v, want %v", got, want)
	}
}

func TestRuntimeDisabledSyncAndErrors(t *testing.T) {
	store := &memoryStore{
		pingErr: errors.New("ping failed"),
		syncErr: errors.New("counts failed"),
	}
	runtime := NewRuntime(
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		staticConfigSource{},
		store,
		nil,
		time.Minute,
	)
	result, err := runtime.TriggerUpload(context.Background())
	if err != nil || result["enabled"] != false {
		t.Fatalf("unexpected disabled result: %#v, %v", result, err)
	}
	if err := runtime.StoragePing(context.Background()); err == nil {
		t.Fatal("expected ping error")
	}
	if _, err := runtime.SyncStatus(context.Background()); err == nil {
		t.Fatal("expected sync status error")
	}
	if _, found := runtime.TaskResult("missing"); found {
		t.Fatal("unexpected task result")
	}
	if len(runtime.ListTasks(nil, 10)) != 0 {
		t.Fatal("expected empty task list")
	}
}

func TestRuntimeKeepsStoreOpenWhenDependencyStopIsIncomplete(t *testing.T) {
	t.Parallel()

	store := &memoryStore{}
	syncService := &runtimeSyncService{
		err: errors.New("stop failed"),
	}
	runtime := NewRuntime(
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		staticConfigSource{},
		store,
		syncService,
		time.Minute,
	)
	if err := runtime.Stop(context.Background()); err == nil {
		t.Fatal("expected dependency stop failure")
	}
	if store.closed.Load() {
		t.Fatal("store closed while a dependency may still be running")
	}
}
