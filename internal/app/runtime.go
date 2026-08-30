package app

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/config"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/fetcher"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/processor"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/storage"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/task"
)

type ConfigSource interface {
	CurrentScrapers() []config.ScraperConfig
}

type SyncService interface {
	RunOnce(context.Context) (map[string]any, error)
	Start(context.Context)
	Stop(context.Context) error
}

type Executor struct {
	logger     *slog.Logger
	fetchers   fetcher.Factory
	processors processor.Factory
	store      storage.CanonicalStore
}

func NewExecutor(
	logger *slog.Logger,
	fetchers fetcher.Factory,
	processors processor.Factory,
	store storage.CanonicalStore,
) *Executor {
	return &Executor{
		logger:     logger,
		fetchers:   fetchers,
		processors: processors,
		store:      store,
	}
}

func (e *Executor) Execute(
	ctx context.Context,
	scraperTask task.ScraperTask,
) (task.ExecutionResult, error) {
	fetcherConfig := map[string]any{
		"hub_root":     scraperTask.ScraperConfig.HubRoot,
		"route":        scraperTask.ScraperConfig.Route,
		"fetch_params": scraperTask.ScraperConfig.FetchParams,
	}
	activeFetcher, err := e.fetchers.Create(
		scraperTask.ScraperConfig.Fetcher,
		fetcherConfig,
	)
	if err != nil {
		return task.ExecutionResult{}, err
	}
	started := time.Now()
	contents, err := activeFetcher.Fetch(ctx, scraperTask.FetchParams)
	if err != nil {
		return task.ExecutionResult{}, err
	}
	contents = filterQuality(contents)
	scraperID := strings.TrimSpace(scraperTask.ScraperID)
	if scraperID == "" {
		scraperID = strings.TrimSpace(scraperTask.ScraperConfig.ID)
	}
	scraperName := strings.TrimSpace(scraperTask.ScraperName)
	if scraperName == "" {
		scraperName = strings.TrimSpace(scraperTask.ScraperConfig.Name)
	}
	if scraperID == "" || scraperName == "" {
		return task.ExecutionResult{}, errors.New("scraper ID and name are required")
	}
	observationAt := scraperTask.CreatedAt
	if observationAt.IsZero() {
		observationAt = time.Now().UTC()
	} else {
		observationAt = observationAt.UTC()
	}
	candidateIDs := make([]string, 0, len(contents))
	for index, item := range contents {
		contents[index].ScraperID = &scraperID
		contents[index].ScraperName = &scraperName
		candidateIDs = append(candidateIDs, item.ContentID)
	}
	existing, err := e.store.ExistingContentIDs(ctx, candidateIDs)
	if err != nil {
		return task.ExecutionResult{}, fmt.Errorf("load existing content ids: %w", err)
	}
	sources := make([]storage.ContentSource, 0, len(contents))
	newContents := make([]content.Content, 0, len(contents))
	for _, item := range contents {
		if _, found := existing[item.ContentID]; found {
			sources = append(sources, storage.ContentSource{
				ContentID:   item.ContentID,
				ScraperID:   scraperID,
				ScraperName: scraperName,
				ObservedAt:  observationAt,
			})
			continue
		}
		newContents = append(newContents, item)
	}
	contents = newContents

	type configuredProcessor struct {
		processor processor.Processor
	}
	pipeline := make([]configuredProcessor, 0, len(scraperTask.ScraperConfig.ContentProcessorConfigs))
	for _, name := range orderedProcessorNames(scraperTask.ScraperConfig) {
		rawConfig := scraperTask.ScraperConfig.ContentProcessorConfigs[name]
		activeProcessor, createErr := e.processors.Create(name, rawConfig)
		if createErr != nil {
			return task.ExecutionResult{}, createErr
		}
		processor.SetCustomCategoryOrder(
			activeProcessor,
			scraperTask.ScraperConfig.ProcessorCategoryOrders[name],
		)
		pipeline = append(pipeline, configuredProcessor{processor: activeProcessor})
	}
	sort.SliceStable(pipeline, func(i, j int) bool {
		return pipeline[i].processor.Priority() < pipeline[j].processor.Priority()
	})
	for _, entry := range pipeline {
		contents, err = entry.processor.Process(ctx, contents)
		if err != nil {
			return task.ExecutionResult{}, fmt.Errorf(
				"processor %s failed: %w",
				entry.processor.Name(),
				err,
			)
		}
	}
	for index := range contents {
		contents[index].ScraperID = &scraperID
		contents[index].ScraperName = &scraperName
		contents[index].Keywords = mergeKeywords(
			scraperTask.DefaultKeywords,
			contents[index].Keywords,
		)
		sources = append(sources, storage.ContentSource{
			ContentID:   contents[index].ContentID,
			ScraperID:   scraperID,
			ScraperName: scraperName,
			ObservedAt:  observationAt,
		})
	}
	executionTime := time.Since(started).Seconds()
	stats, err := e.store.StoreContents(ctx, contents, sources)
	if err != nil {
		return task.ExecutionResult{}, err
	}
	return task.ExecutionResult{
		ItemsFetched:   len(contents),
		ItemsProcessed: len(contents),
		ItemsUploaded:  0,
		Metadata: map[string]any{
			"execution_time_seconds": executionTime,
			"scraper_config":         scraperTask.ScraperName,
			"fetch_params":           scraperTask.FetchParams,
			"storage":                stats,
		},
	}, nil
}

func orderedProcessorNames(scraper config.ScraperConfig) []string {
	names := make([]string, 0, len(scraper.ContentProcessorConfigs))
	seen := make(map[string]struct{}, len(scraper.ContentProcessorConfigs))
	for _, name := range scraper.ContentProcessorOrder {
		if _, exists := scraper.ContentProcessorConfigs[name]; !exists {
			continue
		}
		if _, exists := seen[name]; exists {
			continue
		}
		seen[name] = struct{}{}
		names = append(names, name)
	}
	remaining := make([]string, 0, len(scraper.ContentProcessorConfigs)-len(names))
	for name := range scraper.ContentProcessorConfigs {
		if _, exists := seen[name]; !exists {
			remaining = append(remaining, name)
		}
	}
	sort.Strings(remaining)
	return append(names, remaining...)
}

type Runtime struct {
	logger       *slog.Logger
	configSource ConfigSource
	store        storage.CanonicalStore
	syncService  SyncService
	taskTimeout  time.Duration

	mu      sync.RWMutex
	manager *task.Manager
}

func NewRuntime(
	logger *slog.Logger,
	configSource ConfigSource,
	store storage.CanonicalStore,
	syncService SyncService,
	taskTimeout time.Duration,
) *Runtime {
	return &Runtime{
		logger:       logger,
		configSource: configSource,
		store:        store,
		syncService:  syncService,
		taskTimeout:  taskTimeout,
	}
}

func (r *Runtime) SetTaskManager(manager *task.Manager) {
	r.mu.Lock()
	r.manager = manager
	r.mu.Unlock()
}

func (r *Runtime) TriggerScraper(_ context.Context) (string, int, error) {
	manager, err := r.taskManager()
	if err != nil {
		return "", 0, err
	}
	scrapers := r.configSource.CurrentScrapers()
	tasks := make([]task.ScraperTask, 0, len(scrapers))
	for _, scraper := range scrapers {
		tasks = append(
			tasks,
			task.NewTaskFromConfig(scraper, r.taskTimeout),
		)
	}
	batchID := fmt.Sprintf("scraper_batch_%d", time.Now().Unix())
	submitted, err := manager.SubmitBatch(batchID, tasks)
	r.logger.Info(
		"Scraper tasks submitted to TaskManager",
		"batch_id", batchID,
		"task_count", len(tasks),
		"submitted_count", len(submitted),
	)
	if err != nil {
		return "", len(scrapers), fmt.Errorf("submit scraper batch: %w", err)
	}
	return batchID, len(scrapers), nil
}

func (r *Runtime) TriggerUpload(ctx context.Context) (map[string]any, error) {
	if r.syncService == nil {
		return disabledSyncResult(), nil
	}
	return r.syncService.RunOnce(ctx)
}

func (r *Runtime) StoragePing(ctx context.Context) error {
	return r.store.Ping(ctx)
}

func (r *Runtime) SyncStatus(ctx context.Context) (map[string]any, error) {
	counts, err := r.store.SyncCounts(ctx)
	if err != nil {
		return nil, err
	}
	return map[string]any{
		"enabled": r.syncService != nil,
		"counts":  counts,
	}, nil
}

func (r *Runtime) TaskStatistics() task.Statistics {
	manager, err := r.taskManager()
	if err != nil {
		return task.Statistics{}
	}
	return manager.Statistics()
}

func (r *Runtime) ListTasks(status *task.Status, limit int) []task.Result {
	manager, err := r.taskManager()
	if err != nil {
		return []task.Result{}
	}
	return manager.List(status, limit)
}

func (r *Runtime) TaskResult(taskID string) (task.Result, bool) {
	manager, err := r.taskManager()
	if err != nil {
		return task.Result{}, false
	}
	return manager.Result(taskID)
}

func (r *Runtime) ScraperRuntime(scraperID string) map[string]any {
	for _, scraper := range r.configSource.CurrentScrapers() {
		if scraper.ID == scraperID {
			return map[string]any{
				"initialized":      true,
				"fetcher_type":     legacyFetcherType(scraper.Fetcher),
				"has_storage":      true,
				"processors_count": len(scraper.ContentProcessorConfigs),
			}
		}
	}
	return map[string]any{"initialized": false}
}

func legacyFetcherType(fetcherName string) string {
	switch fetcherName {
	case "rsshub":
		return "RssHub"
	case "direct_rss":
		return "DirectRSS"
	default:
		return fetcherName
	}
}

func (r *Runtime) Stop(ctx context.Context) error {
	type stopResult struct {
		name string
		err  error
	}
	stops := make([]func() stopResult, 0, 2)
	if r.syncService != nil {
		stops = append(stops, func() stopResult {
			return stopResult{
				name: "sync service",
				err:  r.syncService.Stop(ctx),
			}
		})
	}
	manager, err := r.taskManager()
	if err == nil {
		stops = append(stops, func() stopResult {
			return stopResult{
				name: "task manager",
				err:  manager.Stop(ctx),
			}
		})
	}
	results := make(chan stopResult, len(stops))
	for _, stop := range stops {
		go func(stop func() stopResult) {
			results <- stop()
		}(stop)
	}
	var stopErrors []error
	for range stops {
		result := <-results
		if result.err != nil {
			stopErrors = append(
				stopErrors,
				fmt.Errorf("stop %s: %w", result.name, result.err),
			)
		}
	}
	if len(stopErrors) == 0 {
		r.store.Close()
	}
	return errors.Join(stopErrors...)
}

func (r *Runtime) taskManager() (*task.Manager, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	if r.manager == nil {
		return nil, errors.New("task manager is not initialized")
	}
	return r.manager, nil
}

func filterQuality(items []content.Content) []content.Content {
	result := make([]content.Content, 0, len(items))
	seen := make(map[string]struct{}, len(items))
	for _, item := range items {
		contentID := strings.TrimSpace(item.ContentID)
		if contentID == "" ||
			strings.TrimSpace(item.Title) == "" ||
			strings.TrimSpace(item.Link) == "" ||
			(strings.TrimSpace(item.Summary) == "" && strings.TrimSpace(item.Content) == "") {
			continue
		}
		if _, found := seen[contentID]; found {
			continue
		}
		seen[contentID] = struct{}{}
		result = append(result, item)
	}
	return result
}

func mergeKeywords(defaults, existing []string) []string {
	result := make([]string, 0, len(defaults)+len(existing))
	seen := make(map[string]struct{}, len(defaults)+len(existing))
	for _, value := range append(append([]string(nil), defaults...), existing...) {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, found := seen[value]; found {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	return result
}

func disabledSyncResult() map[string]any {
	return map[string]any{
		"enabled":          false,
		"busy":             false,
		"claimed_count":    0,
		"synced_count":     0,
		"failed_count":     0,
		"lost_claim_count": 0,
		"errors":           []any{},
	}
}
