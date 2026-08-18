package task

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/config"
)

func TestNewManagerValidatesDependencies(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	if _, err := NewManager(logger, nil, 1, 1, time.Hour, nil, nil); err == nil {
		t.Fatal("expected missing executor error")
	}

	for _, capacities := range [][2]int{{0, 1}, {1, 0}, {-1, 1}} {
		if _, err := NewManager(
			logger,
			&fakeExecutor{},
			capacities[0],
			capacities[1],
			time.Hour,
			nil,
			nil,
		); err == nil {
			t.Fatalf("expected invalid capacity error for %v", capacities)
		}
	}
}

func TestNewTaskFromConfigMapsFieldsAndPriority(t *testing.T) {
	for priority, expected := range map[int]Priority{
		1: PriorityLow, 4: PriorityNormal, 7: PriorityHigh, 9: PriorityCritical,
	} {
		task := NewTaskFromConfig(config.ScraperConfig{
			Name:            "Feed",
			Fetcher:         "rsshub",
			HubRoot:         "https://example.com",
			Route:           "/feed",
			Priority:        priority,
			FetchParams:     map[string]any{"limit": 10},
			DefaultKeywords: []string{"go"},
		}, 42*time.Second)
		if task.ID == "" || task.Priority != expected || task.ScraperName != "Feed" {
			t.Fatalf("unexpected task: %#v", task)
		}
		if task.Timeout != 42*time.Second {
			t.Fatalf("task timeout = %s", task.Timeout)
		}
		if task.Metadata["fetcher"] != "rsshub" ||
			task.FetchParams["limit"] != 10 ||
			len(task.DefaultKeywords) != 1 {
			t.Fatalf("unexpected task data: %#v", task)
		}
	}
}

type fakeExecutor struct {
	mu       sync.Mutex
	order    []string
	failures map[string]int
	block    <-chan struct{}
}

func (e *fakeExecutor) Execute(
	ctx context.Context,
	task ScraperTask,
) (ExecutionResult, error) {
	if e.block != nil {
		select {
		case <-e.block:
		case <-ctx.Done():
			return ExecutionResult{}, ctx.Err()
		}
	}
	e.mu.Lock()
	defer e.mu.Unlock()
	e.order = append(e.order, task.ID)
	if e.failures[task.ID] > 0 {
		e.failures[task.ID]--
		return ExecutionResult{}, errors.New("failed")
	}
	return ExecutionResult{
		ItemsFetched:   2,
		ItemsProcessed: 2,
		Metadata:       map[string]any{"storage": map[string]any{"inserted": 2}},
	}, nil
}

type retrySaturationExecutor struct {
	block <-chan struct{}
}

func (e retrySaturationExecutor) Execute(
	ctx context.Context,
	task ScraperTask,
) (ExecutionResult, error) {
	if task.ID == "retry" {
		return ExecutionResult{}, errors.New("planned failure")
	}
	if strings.HasPrefix(task.ID, "block-") {
		select {
		case <-e.block:
		case <-ctx.Done():
			return ExecutionResult{}, ctx.Err()
		}
	}
	return ExecutionResult{}, nil
}

func TestManagerCompletesAndPersistsTask(t *testing.T) {
	databasePath := filepath.Join(t.TempDir(), "tasks.sqlite3")
	store, err := NewResultStore(databasePath)
	if err != nil {
		t.Fatal(err)
	}
	executor := &fakeExecutor{failures: map[string]int{}}
	manager, err := NewManager(
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		executor,
		1,
		10,
		time.Hour,
		store,
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	task := NewTaskFromConfig(config.ScraperConfig{
		ID:          "feed",
		Name:        "Feed",
		Fetcher:     "rsshub",
		HubRoot:     "https://example.com",
		Route:       "/feed",
		Priority:    5,
		FetchParams: map[string]any{},
	}, time.Minute)
	task.MaxRetries = 0
	task.Metadata["batch_id"] = "batch-1"
	taskID, err := manager.Submit(task)
	if err != nil {
		t.Fatal(err)
	}
	result := waitForStatus(t, manager, taskID, StatusCompleted)
	if result.ItemsFetched != 2 || result.ItemsProcessed != 2 {
		t.Fatalf("unexpected task counts: %+v", result)
	}
	if result.Metadata["batch_id"] != "batch-1" {
		t.Fatalf("task metadata was not retained: %#v", result.Metadata)
	}
	if err := manager.Stop(context.Background()); err != nil {
		t.Fatal(err)
	}

	reopened, err := NewResultStore(databasePath)
	if err != nil {
		t.Fatal(err)
	}
	defer reopened.Close()
	results, err := reopened.LoadRecent(context.Background(), time.Hour)
	if err != nil {
		t.Fatal(err)
	}
	if len(results) != 1 || results[0].TaskID != taskID {
		t.Fatalf("unexpected persisted results: %+v", results)
	}
}

func TestManagerTerminalizesInterruptedPersistedTasks(t *testing.T) {
	databasePath := filepath.Join(t.TempDir(), "tasks.sqlite3")
	store, err := NewResultStore(databasePath)
	if err != nil {
		t.Fatal(err)
	}
	startedAt := time.Now().Add(-time.Minute)
	for _, status := range []Status{
		StatusPending,
		StatusRunning,
		StatusRetrying,
	} {
		taskID := string(status) + "-task"
		if err := store.Save(context.Background(), Result{
			TaskID:    taskID,
			Status:    status,
			StartTime: startedAt,
			Metadata:  map[string]any{},
		}); err != nil {
			t.Fatal(err)
		}
	}

	manager, err := NewManager(
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		&fakeExecutor{failures: map[string]int{}},
		1,
		10,
		time.Hour,
		store,
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	for _, status := range []Status{
		StatusPending,
		StatusRunning,
		StatusRetrying,
	} {
		taskID := string(status) + "-task"
		result, ok := manager.Result(taskID)
		if !ok ||
			result.Status != StatusFailed ||
			result.EndTime == nil ||
			result.Duration == nil ||
			result.ErrorMessage == nil ||
			*result.ErrorMessage != interruptedTaskMessage {
			t.Fatalf("recovered result %q = %+v", taskID, result)
		}
	}
	if err := manager.Stop(context.Background()); err != nil {
		t.Fatal(err)
	}

	reopened, err := NewResultStore(databasePath)
	if err != nil {
		t.Fatal(err)
	}
	defer reopened.Close()
	results, err := reopened.LoadRecent(context.Background(), time.Hour)
	if err != nil {
		t.Fatal(err)
	}
	if len(results) != 3 {
		t.Fatalf("persisted results = %+v", results)
	}
	for _, result := range results {
		if result.Status != StatusFailed ||
			result.EndTime == nil ||
			result.ErrorMessage == nil ||
			*result.ErrorMessage != interruptedTaskMessage {
			t.Fatalf("persisted recovery = %+v", result)
		}
	}
}

func TestManagerDegradesWhenPersistedHistoryCannotBeReadOrRepaired(t *testing.T) {
	t.Run("malformed timestamp", func(t *testing.T) {
		store, err := NewResultStore(
			filepath.Join(t.TempDir(), "tasks.sqlite3"),
		)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := store.db.Exec(`
			INSERT INTO task_results (
				task_id, status, start_time, metadata_json, updated_at
			) VALUES (?, ?, ?, ?, ?)
		`, "malformed", StatusRunning, "not-a-time", "{}", "not-a-time"); err != nil {
			t.Fatal(err)
		}
		manager, err := NewManager(
			slog.New(slog.NewTextHandler(io.Discard, nil)),
			&fakeExecutor{failures: map[string]int{}},
			1,
			10,
			time.Hour,
			store,
			nil,
		)
		if err != nil {
			t.Fatal(err)
		}
		if _, exists := manager.Result("malformed"); exists {
			t.Fatal("malformed task history should be quarantined")
		}
		if manager.store != nil {
			t.Fatal("unreadable task persistence should be disabled")
		}
		if err := manager.Stop(context.Background()); err != nil {
			t.Fatal(err)
		}
	})

	t.Run("read-only recovery", func(t *testing.T) {
		store, err := NewResultStore(
			filepath.Join(t.TempDir(), "tasks.sqlite3"),
		)
		if err != nil {
			t.Fatal(err)
		}
		if err := store.Save(context.Background(), Result{
			TaskID:    "interrupted",
			Status:    StatusRunning,
			StartTime: time.Now().Add(-time.Minute),
			Metadata:  map[string]any{},
		}); err != nil {
			t.Fatal(err)
		}
		if _, err := store.db.Exec("PRAGMA query_only = ON"); err != nil {
			t.Fatal(err)
		}
		manager, err := NewManager(
			slog.New(slog.NewTextHandler(io.Discard, nil)),
			&fakeExecutor{failures: map[string]int{}},
			1,
			10,
			time.Hour,
			store,
			nil,
		)
		if err != nil {
			t.Fatal(err)
		}
		result, exists := manager.Result("interrupted")
		if !exists || result.Status != StatusFailed {
			t.Fatalf("recovered result = %+v", result)
		}
		if manager.store != nil {
			t.Fatal("unwritable task persistence should be disabled")
		}
		if err := manager.Stop(context.Background()); err != nil {
			t.Fatal(err)
		}
	})
}

func TestManagerRejectsFullQueue(t *testing.T) {
	block := make(chan struct{})
	manager, err := NewManager(
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		&fakeExecutor{failures: map[string]int{}, block: block},
		1,
		1,
		time.Hour,
		nil,
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		close(block)
		_ = manager.Stop(context.Background())
	}()
	first := ScraperTask{ID: "first", ScraperName: "one", Priority: PriorityNormal, Timeout: time.Minute}
	second := ScraperTask{ID: "second", ScraperName: "two", Priority: PriorityNormal, Timeout: time.Minute}
	third := ScraperTask{ID: "third", ScraperName: "three", Priority: PriorityNormal, Timeout: time.Minute}
	if _, err := manager.Submit(first); err != nil {
		t.Fatal(err)
	}
	waitForStatus(t, manager, first.ID, StatusRunning)
	if _, err := manager.Submit(second); err != nil {
		t.Fatal(err)
	}
	if _, err := manager.Submit(third); !errors.Is(err, ErrQueueFull) {
		t.Fatalf("expected queue full, got %v", err)
	}
}

func TestManagerRejectsBatchUnlessEveryTaskFits(t *testing.T) {
	block := make(chan struct{})
	manager, err := NewManager(
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		&fakeExecutor{failures: map[string]int{}, block: block},
		1,
		2,
		time.Hour,
		nil,
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		close(block)
		_ = manager.Stop(context.Background())
	}()
	running := ScraperTask{
		ID:          "running",
		ScraperName: "running",
		Priority:    PriorityNormal,
		Timeout:     time.Minute,
	}
	pending := ScraperTask{
		ID:          "pending",
		ScraperName: "pending",
		Priority:    PriorityNormal,
		Timeout:     time.Minute,
	}
	if _, err := manager.Submit(running); err != nil {
		t.Fatal(err)
	}
	waitForStatus(t, manager, running.ID, StatusRunning)
	if _, err := manager.Submit(pending); err != nil {
		t.Fatal(err)
	}

	submitted, err := manager.SubmitBatch("batch", []ScraperTask{
		{
			ID:          "batch-a",
			ScraperName: "a",
			Priority:    PriorityNormal,
			Timeout:     time.Minute,
		},
		{
			ID:          "batch-b",
			ScraperName: "b",
			Priority:    PriorityNormal,
			Timeout:     time.Minute,
		},
	})
	if !errors.Is(err, ErrQueueFull) || len(submitted) != 0 {
		t.Fatalf("SubmitBatch() = %v, %v", submitted, err)
	}
	for _, taskID := range []string{"batch-a", "batch-b"} {
		if _, exists := manager.Result(taskID); exists {
			t.Fatalf("rejected task %q was retained", taskID)
		}
	}
}

func TestManagerCancelsRunningTask(t *testing.T) {
	block := make(chan struct{})
	manager, err := NewManager(
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		&fakeExecutor{failures: map[string]int{}, block: block},
		1,
		10,
		time.Hour,
		nil,
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	task := ScraperTask{
		ID:          "cancel-me",
		ScraperName: "feed",
		Priority:    PriorityNormal,
		Timeout:     time.Minute,
	}
	if _, err := manager.Submit(task); err != nil {
		t.Fatal(err)
	}
	waitForStatus(t, manager, task.ID, StatusRunning)
	if !manager.Cancel(task.ID) {
		t.Fatal("expected running task cancellation")
	}
	waitForStatus(t, manager, task.ID, StatusCancelled)
	close(block)
	if err := manager.Stop(context.Background()); err != nil {
		t.Fatal(err)
	}
}

func TestManagerCancelsPendingTaskAndReportsStatistics(t *testing.T) {
	block := make(chan struct{})
	manager, err := NewManager(
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		&fakeExecutor{failures: map[string]int{}, block: block},
		1,
		10,
		time.Hour,
		nil,
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	first := ScraperTask{
		ID: "first", ScraperName: "first", Priority: PriorityNormal,
		Timeout: time.Minute,
	}
	second := ScraperTask{
		ID: "second", ScraperName: "second", Priority: PriorityNormal,
		Timeout: time.Minute,
	}
	if _, err := manager.Submit(first); err != nil {
		t.Fatal(err)
	}
	waitForStatus(t, manager, first.ID, StatusRunning)
	if _, err := manager.Submit(second); err != nil {
		t.Fatal(err)
	}
	if !manager.Cancel(second.ID) {
		t.Fatal("expected pending task cancellation")
	}
	waitForStatus(t, manager, second.ID, StatusCancelled)
	if queueSize := manager.Statistics().CurrentQueueSize; queueSize != 0 {
		t.Fatalf("cancelled task remained queued: %d", queueSize)
	}
	if manager.Cancel("missing") {
		t.Fatal("unexpected missing task cancellation")
	}
	status := StatusCancelled
	if results := manager.List(&status, 10); len(results) != 1 {
		t.Fatalf("unexpected cancelled list: %#v", results)
	}
	if results := manager.List(nil, -1); len(results) != 0 {
		t.Fatalf("negative limit should return no results: %#v", results)
	}
	stats := manager.Statistics()
	if stats.TotalTasks != 2 || stats.CancelledTasks != 1 ||
		stats.QueueCapacity != 10 || stats.MaxConcurrentTasks != 1 {
		t.Fatalf("unexpected statistics: %#v", stats)
	}
	close(block)
	if err := manager.Stop(context.Background()); err != nil {
		t.Fatal(err)
	}
	if err := manager.Stop(context.Background()); err != nil {
		t.Fatal(err)
	}
	if _, err := manager.Submit(ScraperTask{}); err == nil {
		t.Fatal("expected submit after stop to fail")
	}
}

func TestManagerStopDrainsRunningTask(t *testing.T) {
	block := make(chan struct{})
	manager, err := NewManager(
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		&fakeExecutor{failures: map[string]int{}, block: block},
		1,
		10,
		time.Hour,
		nil,
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	task := ScraperTask{
		ID:          "drain-me",
		ScraperName: "feed",
		Priority:    PriorityNormal,
		Timeout:     time.Minute,
	}
	if _, err := manager.Submit(task); err != nil {
		t.Fatal(err)
	}
	waitForStatus(t, manager, task.ID, StatusRunning)

	stopped := make(chan error, 1)
	go func() {
		stopped <- manager.Stop(context.Background())
	}()
	select {
	case err := <-stopped:
		t.Fatalf("Stop returned before running task completed: %v", err)
	case <-time.After(25 * time.Millisecond):
	}
	close(block)
	if err := <-stopped; err != nil {
		t.Fatal(err)
	}
	result, ok := manager.Result(task.ID)
	if !ok || result.Status != StatusCompleted {
		t.Fatalf("drained result = %+v", result)
	}
}

func TestManagerStopCancelsRunningTaskAfterDeadline(t *testing.T) {
	block := make(chan struct{})
	manager, err := NewManager(
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		&fakeExecutor{failures: map[string]int{}, block: block},
		1,
		10,
		time.Hour,
		nil,
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	task := ScraperTask{
		ID:          "force-stop",
		ScraperName: "feed",
		Priority:    PriorityNormal,
		Timeout:     time.Minute,
	}
	if _, err := manager.Submit(task); err != nil {
		t.Fatal(err)
	}
	waitForStatus(t, manager, task.ID, StatusRunning)

	stopCtx, cancel := context.WithTimeout(
		context.Background(),
		25*time.Millisecond,
	)
	defer cancel()
	if err := manager.Stop(stopCtx); !errors.Is(
		err,
		context.DeadlineExceeded,
	) {
		t.Fatalf("Stop error = %v", err)
	}
	result, ok := manager.Result(task.ID)
	if !ok || result.Status != StatusCancelled {
		t.Fatalf("forced-stop result = %+v", result)
	}
}

func TestManagerRetriesFailedTask(t *testing.T) {
	executor := &fakeExecutor{failures: map[string]int{"retry": 1}}
	manager, err := NewManager(
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		executor,
		1,
		10,
		time.Hour,
		nil,
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	task := ScraperTask{
		ID:          "retry",
		ScraperName: "retry",
		Priority:    PriorityNormal,
		MaxRetries:  1,
		RetryDelay:  time.Millisecond,
		Timeout:     time.Second,
	}
	if _, err := manager.Submit(task); err != nil {
		t.Fatal(err)
	}
	waitForStatus(t, manager, task.ID, StatusFailed)
	waitForStatus(t, manager, "retry_retry_1", StatusCompleted)
	stats := manager.Statistics()
	if stats.FailedTasks != 1 || stats.CompletedTasks != 1 ||
		stats.TotalTasks != 2 || stats.SuccessRatePercent != 50 {
		t.Fatalf("unexpected retry statistics: %#v", stats)
	}
	if err := manager.Stop(context.Background()); err != nil {
		t.Fatal(err)
	}
}

func TestManagerRetainsRetryWhileQueueIsFull(t *testing.T) {
	block := make(chan struct{})
	manager, err := NewManager(
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		retrySaturationExecutor{block: block},
		1,
		1,
		time.Hour,
		nil,
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	retry := ScraperTask{
		ID:          "retry",
		ScraperName: "retry",
		Priority:    PriorityNormal,
		MaxRetries:  1,
		RetryDelay:  500 * time.Millisecond,
		Timeout:     2 * time.Second,
	}
	if _, err := manager.Submit(retry); err != nil {
		t.Fatal(err)
	}
	waitForStatus(t, manager, retry.ID, StatusFailed)
	running := ScraperTask{
		ID:          "block-running",
		ScraperName: "block-running",
		Priority:    PriorityNormal,
		Timeout:     time.Second,
	}
	queued := ScraperTask{
		ID:          "block-queued",
		ScraperName: "block-queued",
		Priority:    PriorityNormal,
		Timeout:     time.Second,
	}
	if _, err := manager.Submit(running); err != nil {
		t.Fatal(err)
	}
	waitForStatus(t, manager, running.ID, StatusRunning)
	if _, err := manager.Submit(queued); err != nil {
		t.Fatal(err)
	}
	time.Sleep(retry.RetryDelay + 2*retryAdmissionDelay)
	if _, exists := manager.Result("retry_retry_1"); exists {
		t.Fatal("retry was submitted while the queue was full")
	}

	close(block)
	waitForStatus(t, manager, "retry_retry_1", StatusCompleted)
	if err := manager.Stop(context.Background()); err != nil {
		t.Fatal(err)
	}
}

func TestManagerStopCancelsScheduledRetries(t *testing.T) {
	executor := &fakeExecutor{failures: map[string]int{"retry": 1}}
	manager, err := NewManager(
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		executor,
		1,
		10,
		time.Hour,
		nil,
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	task := ScraperTask{
		ID:          "retry",
		ScraperName: "retry",
		Priority:    PriorityNormal,
		MaxRetries:  1,
		RetryDelay:  20 * time.Millisecond,
		Timeout:     time.Second,
	}
	if _, err := manager.Submit(task); err != nil {
		t.Fatal(err)
	}
	waitForStatus(t, manager, task.ID, StatusFailed)
	if err := manager.Stop(context.Background()); err != nil {
		t.Fatal(err)
	}
	time.Sleep(40 * time.Millisecond)
	if stats := manager.Statistics(); stats.TotalTasks != 1 {
		t.Fatalf("scheduled retry ran after stop: %#v", stats)
	}
}

func TestResultJSONAndHelpers(t *testing.T) {
	end := time.Unix(20, 0).UTC()
	duration := 10.0
	message := "failed"
	result := Result{
		TaskID:       "one",
		Status:       StatusFailed,
		StartTime:    time.Unix(10, 0).UTC(),
		EndTime:      &end,
		Duration:     &duration,
		ErrorMessage: &message,
		Metadata:     map[string]any{"nested": "value"},
	}
	data, err := json.Marshal(result)
	if err != nil {
		t.Fatal(err)
	}
	if string(data) == "" || formatOptionalTime(nil) != nil {
		t.Fatalf("unexpected JSON or optional time: %s", data)
	}
	cloned := cloneResult(result)
	cloned.Metadata["nested"] = "changed"
	if result.Metadata["nested"] != "value" {
		t.Fatal("cloneResult mutated source metadata")
	}
	if round2(1.236) != 1.24 {
		t.Fatalf("unexpected rounding: %v", round2(1.236))
	}
	if _, err := parseTaskTime(time.Now().Format(time.RFC3339Nano)); err != nil {
		t.Fatal(err)
	}
	if _, err := parseTaskTime("invalid"); err == nil {
		t.Fatal("expected invalid task timestamp error")
	}
}

func TestResultStoreLoadsLegacyPythonTimestamps(t *testing.T) {
	store, err := NewResultStore(filepath.Join(t.TempDir(), "legacy.sqlite3"))
	if err != nil {
		t.Fatal(err)
	}
	defer store.Close()
	start := formatTaskTime(time.Now().Add(-time.Minute))
	if _, err := store.db.Exec(`
		INSERT INTO task_results (
			task_id, status, start_time, items_fetched, items_processed,
			items_uploaded, metadata_json, updated_at
		) VALUES (?, ?, ?, 0, 0, 0, '{}', ?)
	`, "legacy", StatusCompleted, start, start); err != nil {
		t.Fatal(err)
	}
	results, err := store.LoadRecent(context.Background(), time.Hour)
	if err != nil {
		t.Fatal(err)
	}
	if len(results) != 1 || results[0].TaskID != "legacy" {
		t.Fatalf("unexpected legacy results: %#v", results)
	}
}

func TestParseStatus(t *testing.T) {
	status, err := ParseStatus("completed")
	if err != nil || status == nil || *status != StatusCompleted {
		t.Fatalf("unexpected status parse: %v %v", status, err)
	}
	if status, err := ParseStatus(""); err != nil || status != nil {
		t.Fatalf("empty status should be unset: %v %v", status, err)
	}
	if _, err := ParseStatus("unknown"); err == nil {
		t.Fatal("expected invalid status error")
	}
}

func waitForStatus(t *testing.T, manager *Manager, taskID string, expected Status) Result {
	t.Helper()
	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		result, ok := manager.Result(taskID)
		if ok && result.Status == expected {
			return result
		}
		time.Sleep(10 * time.Millisecond)
	}
	result, _ := manager.Result(taskID)
	t.Fatalf("task %s did not reach %s: %+v", taskID, expected, result)
	return Result{}
}
