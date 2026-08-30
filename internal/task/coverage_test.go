package task

import (
	"context"
	"database/sql"
	"errors"
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/config"
)

type recordingObserver struct {
	configured, submitted, completed, failed, retried, cancelled, states int
}

type ignoringContextExecutor struct {
	release <-chan struct{}
}

func (e ignoringContextExecutor) Execute(context.Context, ScraperTask) (ExecutionResult, error) {
	<-e.release
	return ExecutionResult{}, nil
}

func (o *recordingObserver) Configure(int, int) { o.configured++ }
func (o *recordingObserver) Submitted()         { o.submitted++ }
func (o *recordingObserver) Completed(time.Duration, int) {
	o.completed++
}
func (o *recordingObserver) Failed(time.Duration) { o.failed++ }
func (o *recordingObserver) Retried()             { o.retried++ }
func (o *recordingObserver) Cancelled()           { o.cancelled++ }
func (o *recordingObserver) State(int, int)       { o.states++ }

func TestPriorityQueueOrderingAndRemoval(t *testing.T) {
	var queue priorityQueue
	queue.pushTask(ScraperTask{ID: "low", Priority: PriorityLow}, 1)
	queue.pushTask(ScraperTask{ID: "high", Priority: PriorityHigh}, 2)
	queue.pushTask(ScraperTask{ID: "same-first", Priority: PriorityNormal}, 3)
	queue.pushTask(ScraperTask{ID: "same-second", Priority: PriorityNormal}, 4)
	if !queue.removeTask("same-first") || queue.removeTask("missing") {
		t.Fatal("unexpected queue removal result")
	}
	if got := queue.popTask().ID; got != "high" {
		t.Fatalf("first queue item = %q", got)
	}
	if got := queue.popTask().ID; got != "same-second" {
		t.Fatalf("second queue item = %q", got)
	}
	if got := queue.popTask().ID; got != "low" {
		t.Fatalf("third queue item = %q", got)
	}
}

func TestManagerSubmissionDefaultsBatchAndStopping(t *testing.T) {
	block := make(chan struct{})
	observer := &recordingObserver{}
	manager, err := NewManager(
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		&fakeExecutor{failures: map[string]int{}, block: block},
		1, 5, time.Hour, nil, observer,
	)
	if err != nil {
		t.Fatal(err)
	}
	taskID, err := manager.Submit(ScraperTask{Timeout: time.Minute})
	if err != nil || taskID == "" {
		t.Fatalf("Submit() = %q, %v", taskID, err)
	}
	waitForStatus(t, manager, taskID, StatusRunning)
	submitted, err := manager.SubmitBatch("batch", []ScraperTask{
		{ID: "batch-one", Metadata: nil},
		{ID: "batch-two", Metadata: map[string]any{}},
	})
	if err != nil || len(submitted) != 2 {
		t.Fatalf("SubmitBatch() = %#v, %v", submitted, err)
	}
	if result, ok := manager.Result("batch-one"); !ok || result.Metadata["batch_id"] != "batch" {
		t.Fatalf("batch metadata = %#v, %t", result, ok)
	}
	close(block)
	if err := manager.Stop(context.Background()); err != nil {
		t.Fatal(err)
	}
	if _, err := manager.SubmitBatch("stopped", []ScraperTask{{ID: "after"}}); !errors.Is(err, errManagerStopping) {
		t.Fatalf("SubmitBatch after stop = %v", err)
	}
	if observer.configured == 0 || observer.submitted < 3 || observer.states == 0 {
		t.Fatalf("observer callbacks = %#v", observer)
	}
}

func TestManagerHandlesClosedResultStore(t *testing.T) {
	store, err := NewResultStore(filepath.Join(t.TempDir(), "results.sqlite3"))
	if err != nil {
		t.Fatal(err)
	}
	if err := store.Close(); err != nil {
		t.Fatal(err)
	}
	manager, err := NewManager(
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		&fakeExecutor{},
		1, 1, time.Hour, store, nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	if manager.store != nil {
		t.Fatal("closed result store should disable persistence")
	}
	if err := manager.Stop(context.Background()); err != nil {
		t.Fatal(err)
	}
}

func TestManagerSmallInternalBranches(t *testing.T) {
	live, err := NewManager(nil, &fakeExecutor{}, 1, 1, time.Hour, nil, nil)
	if err != nil {
		t.Fatal(err)
	}

	defer live.Stop(context.Background())
	result := Result{Status: StatusCompleted, StartTime: time.Now()}
	if markInterruptedResult(&result, time.Now()) {
		t.Fatal("terminal result was marked interrupted")
	}
	result = Result{Status: StatusRunning, StartTime: time.Now().Add(time.Minute)}
	if !markInterruptedResult(&result, time.Now()) || result.Duration == nil || *result.Duration != 0 {
		t.Fatalf("negative recovery duration = %#v", result.Duration)
	}
	manager := &Manager{
		logger:    slog.New(slog.NewTextHandler(io.Discard, nil)),
		observer:  nopObserver{},
		results:   map[string]*Result{},
		running:   map[string]context.CancelFunc{},
		cancelled: map[string]struct{}{},
	}
	manager.finish(ScraperTask{ID: "missing"}, ExecutionResult{}, errors.New("ignored"))
	manager.results["nil-metadata"] = &Result{TaskID: "nil-metadata", StartTime: time.Now()}
	manager.finish(ScraperTask{ID: "nil-metadata"}, ExecutionResult{
		Metadata: map[string]any{"key": "value"},
	}, nil)
	if manager.results["nil-metadata"].Metadata["key"] != "value" {
		t.Fatal("finish did not initialize metadata")
	}
	manager.stopping = true
	manager.submitScheduledRetry(ScraperTask{ID: "stopping"})
	closedStore, err := NewResultStore(filepath.Join(t.TempDir(), "closed.sqlite3"))
	if err != nil {
		t.Fatal(err)
	}
	if err := closedStore.db.Close(); err != nil {
		t.Fatal(err)
	}
	manager.store = closedStore
	manager.persistLocked(&Result{TaskID: "persist-error"})
	manager.cancelPendingLocked("missing")
	manager.results["completed"] = &Result{TaskID: "completed", Status: StatusCompleted}
	manager.cancelPendingLocked("completed")

	skipped := &Manager{
		logger:      slog.New(slog.NewTextHandler(io.Discard, nil)),
		observer:    nopObserver{},
		results:     map[string]*Result{"cancelled": {TaskID: "cancelled", Status: StatusCancelled}},
		running:     map[string]context.CancelFunc{},
		cancelled:   map[string]struct{}{},
		retryTimers: map[string]*time.Timer{},
		maxQueue:    1,
		workers:     1,
		cleanupDone: make(chan struct{}),
		stopCleanup: make(chan struct{}),
	}
	skipped.cond = sync.NewCond(&skipped.mu)
	skipped.queue.pushTask(ScraperTask{ID: "cancelled", Timeout: time.Minute}, 1)
	skipped.wg.Add(1)
	go skipped.worker()
	deadline := time.Now().Add(time.Second)
	for time.Now().Before(deadline) {
		skipped.mu.Lock()
		empty := skipped.queue.Len() == 0
		skipped.mu.Unlock()
		if empty {
			break
		}
		time.Sleep(time.Millisecond)
	}
	skipped.mu.Lock()
	skipped.stopping = true
	skipped.cond.Broadcast()
	skipped.mu.Unlock()
	skipped.wg.Wait()
	cleaner := &Manager{cleanupDone: make(chan struct{}), stopCleanup: make(chan struct{})}
	close(cleaner.stopCleanup)
	cleaner.cleanupLoop()
}

func TestManagerStopReturnsAfterForcedShutdownWait(t *testing.T) {
	release := make(chan struct{})
	manager, err := NewManager(
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		ignoringContextExecutor{release: release},
		1, 1, time.Hour, nil, nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := manager.Submit(ScraperTask{ID: "stubborn", Timeout: time.Minute}); err != nil {
		t.Fatal(err)
	}
	waitForStatus(t, manager, "stubborn", StatusRunning)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Millisecond)
	defer cancel()
	if err := manager.Stop(ctx); !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("Stop() error = %v", err)
	}
	close(release)
	manager.wg.Wait()
	<-manager.cleanupDone
}

func TestManagerCleanupRemovesExpiredResultsAndReportsStoreErrors(t *testing.T) {
	store, err := NewResultStore(filepath.Join(t.TempDir(), "results.sqlite3"))
	if err != nil {
		t.Fatal(err)
	}
	if err := store.db.Close(); err != nil {
		t.Fatal(err)
	}
	manager := &Manager{
		logger:    slog.New(slog.NewTextHandler(io.Discard, nil)),
		retention: time.Hour,
		store:     store,
		results: map[string]*Result{"expired": {
			TaskID:  "expired",
			EndTime: ptrTime(time.Now().Add(-2 * time.Hour)),
		}},
		cleanupDone: make(chan struct{}),
		stopCleanup: make(chan struct{}),
	}
	manager.cleanupExpiredResults()
	manager.mu.RLock()
	_, exists := manager.results["expired"]
	manager.mu.RUnlock()
	if exists {
		t.Fatal("expired result was not removed")
	}
}

func TestNewScraperTaskDefaultsAndClonesInput(t *testing.T) {
	input := map[string]any{"key": "value"}
	task := NewScraperTask(configScraper{
		Config: config.ScraperConfig{ID: "id"},
		ID:     "id", Name: "name", Priority: 10, Fetcher: "rss",
		DefaultKeywords: []string{"one"},
	}, input, 0)
	input["key"] = "changed"
	if task.Timeout != 5*time.Minute || task.Priority != PriorityCritical ||
		task.FetchParams["key"] != "value" || task.Tags[0] != "rss" {
		t.Fatalf("task defaults = %#v", task)
	}
}

func TestResultStoreNilAndClosedErrors(t *testing.T) {
	var nilStore *ResultStore
	if store, err := NewResultStore(""); store != nil || err != nil {
		t.Fatalf("empty result store = %#v, %v", store, err)
	}
	if err := nilStore.Save(context.Background(), Result{}); err != nil {
		t.Fatal(err)
	}
	if results, err := nilStore.LoadRecent(context.Background(), time.Hour); err != nil || results != nil {
		t.Fatalf("nil LoadRecent = %#v, %v", results, err)
	}
	if deleted, err := nilStore.DeleteOlderThan(context.Background(), time.Now()); err != nil || deleted != 0 {
		t.Fatalf("nil DeleteOlderThan = %d, %v", deleted, err)
	}
	if err := nilStore.Close(); err != nil {
		t.Fatal(err)
	}
	parent := filepath.Join(t.TempDir(), "parent-file")
	if err := os.WriteFile(parent, []byte("file"), 0o644); err != nil {
		t.Fatal(err)
	}
	if _, err := NewResultStore(filepath.Join(parent, "results.sqlite3")); err == nil {
		t.Fatal("expected result directory error")
	}

	store, err := NewResultStore(filepath.Join(t.TempDir(), "results.sqlite3"))
	if err != nil {
		t.Fatal(err)
	}
	if err := store.db.Close(); err != nil {
		t.Fatal(err)
	}
	if err := store.Save(context.Background(), Result{TaskID: "one", Metadata: map[string]any{"bad": func() {}}}); err == nil {
		t.Fatal("expected metadata marshal error")
	}
	if err := store.Save(context.Background(), Result{TaskID: "one"}); err == nil {
		t.Fatal("expected closed database save error")
	}
	if _, err := store.LoadRecent(context.Background(), time.Hour); err == nil {
		t.Fatal("expected closed database load error")
	}
	if _, err := store.DeleteOlderThan(context.Background(), time.Now()); err == nil {
		t.Fatal("expected closed database delete error")
	}
	if err := store.Close(); err != nil {
		t.Fatal(err)
	}
}

func TestResultStoreLoadMalformedRows(t *testing.T) {
	store, err := NewResultStore(filepath.Join(t.TempDir(), "results.sqlite3"))
	if err != nil {
		t.Fatal(err)
	}
	defer store.Close()
	if _, err := store.db.Exec(`
		INSERT INTO task_results (task_id, status, start_time, metadata_json, updated_at)
		VALUES ('bad-start', 'completed', 'bad', '{}', 'bad')
	`); err != nil {
		t.Fatal(err)
	}
	if _, err := store.LoadRecent(context.Background(), time.Hour); err == nil ||
		!strings.Contains(err.Error(), "parse task start time") {
		t.Fatalf("malformed start error = %v", err)
	}
	if _, err := store.db.Exec(`DELETE FROM task_results`); err != nil {
		t.Fatal(err)
	}
	if _, err := store.db.Exec(`
		INSERT INTO task_results (task_id, status, start_time, end_time, metadata_json, updated_at)
		VALUES ('bad-end', 'completed', ?, 'bad', '{}', ?)
	`, formatTaskTime(time.Now()), formatTaskTime(time.Now())); err != nil {
		t.Fatal(err)
	}
	if _, err := store.LoadRecent(context.Background(), time.Hour); err == nil ||
		!strings.Contains(err.Error(), "parse task end time") {
		t.Fatalf("malformed end error = %v", err)
	}
}

func TestResultStoreInitializationAndLegacyFaults(t *testing.T) {
	store, err := NewResultStore(filepath.Join(t.TempDir(), "results.sqlite3"))
	if err != nil {
		t.Fatal(err)
	}
	if err := store.db.Close(); err != nil {
		t.Fatal(err)
	}
	if err := store.initialize(context.Background()); err == nil ||
		!strings.Contains(err.Error(), "begin task result migration") {
		t.Fatalf("initialize closed database error = %v", err)
	}

	for _, test := range []struct {
		name      string
		endTime   string
		updatedAt string
		want      string
	}{
		{"bad end", "bad", "", "end time"},
		{"bad update", "", "bad", "update time"},
	} {
		t.Run(test.name, func(t *testing.T) {
			path := filepath.Join(t.TempDir(), "legacy.sqlite3")
			createLegacyTaskResultDatabase(t, path, string(StatusCompleted), "2025-04-06T05:50:59", 0)
			db, err := sql.Open("sqlite", path)
			if err != nil {
				t.Fatal(err)
			}
			if test.endTime != "" {
				if _, err := db.Exec(`UPDATE task_results SET end_time = ?`, test.endTime); err != nil {
					t.Fatal(err)
				}
			} else if _, err := db.Exec(`UPDATE task_results SET updated_at = ?`, test.updatedAt); err != nil {
				t.Fatal(err)
			}
			if err := db.Close(); err != nil {
				t.Fatal(err)
			}
			if store, err := NewResultStore(path); store != nil || err == nil ||
				!strings.Contains(err.Error(), test.want) {
				t.Fatalf("legacy %s = %#v, %v", test.name, store, err)
			}
		})
	}

	path := filepath.Join(t.TempDir(), "legacy.sqlite3")
	createLegacyTaskResultDatabase(t, path, string(StatusCompleted), "2025-04-06T05:50:59", 0)
	db, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(`CREATE TABLE task_results_v0 (id TEXT)`); err != nil {
		t.Fatal(err)
	}
	if err := db.Close(); err != nil {
		t.Fatal(err)
	}
	if store, err := NewResultStore(path); store != nil || err == nil ||
		!strings.Contains(err.Error(), "rename legacy task result table") {
		t.Fatalf("rename conflict = %#v, %v", store, err)
	}

	t.Run("fresh schema conflict", func(t *testing.T) {
		path := filepath.Join(t.TempDir(), "view.sqlite3")
		db, err := sql.Open("sqlite", path)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := db.Exec(`CREATE VIEW task_results AS SELECT 1`); err != nil {
			t.Fatal(err)
		}
		if err := db.Close(); err != nil {
			t.Fatal(err)
		}
		if store, err := NewResultStore(path); store != nil || err == nil ||
			!strings.Contains(err.Error(), "create task result indexes") {
			t.Fatalf("view conflict = %#v, %v", store, err)
		}
	})

	t.Run("legacy read schema error", func(t *testing.T) {
		path := filepath.Join(t.TempDir(), "bad-legacy.sqlite3")
		db, err := sql.Open("sqlite", path)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := db.Exec(`CREATE TABLE task_results (task_id TEXT)`); err != nil {
			t.Fatal(err)
		}
		if err := db.Close(); err != nil {
			t.Fatal(err)
		}
		if store, err := NewResultStore(path); store != nil || err == nil ||
			!strings.Contains(err.Error(), "read legacy task results") {
			t.Fatalf("legacy read error = %#v, %v", store, err)
		}
	})

	t.Run("legacy scan error", func(t *testing.T) {
		path := filepath.Join(t.TempDir(), "scan-legacy.sqlite3")
		db, err := sql.Open("sqlite", path)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := db.Exec(`
			CREATE TABLE task_results (
				task_id TEXT, status TEXT, start_time TEXT, end_time TEXT,
				duration_seconds REAL, items_fetched INTEGER, items_processed INTEGER,
				items_uploaded INTEGER, error_message TEXT, metadata_json TEXT,
				updated_at TEXT
			);
			INSERT INTO task_results (status, start_time, metadata_json, updated_at)
			VALUES ('completed', '2025-04-06T05:50:59', '{}', '2025-04-06T05:50:59')
		`); err != nil {
			t.Fatal(err)
		}
		if err := db.Close(); err != nil {
			t.Fatal(err)
		}
		if store, err := NewResultStore(path); store != nil || err == nil ||
			!strings.Contains(err.Error(), "scan legacy task result") {
			t.Fatalf("legacy scan error = %#v, %v", store, err)
		}
	})
	t.Run("legacy end time", func(t *testing.T) {
		path := filepath.Join(t.TempDir(), "end-legacy.sqlite3")
		createLegacyTaskResultDatabase(t, path, string(StatusCompleted), "2025-04-06T05:50:59", 0)
		db, err := sql.Open("sqlite", path)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := db.Exec(`UPDATE task_results SET end_time = ?`, "2025-04-06T06:50:59"); err != nil {
			t.Fatal(err)
		}
		if err := db.Close(); err != nil {
			t.Fatal(err)
		}
		store, err := NewResultStore(path)
		if err != nil {
			t.Fatal(err)
		}
		store.Close()
	})
}

func TestResultStoreLoadsOptionalFieldsAndBadMetadata(t *testing.T) {
	store, err := NewResultStore(filepath.Join(t.TempDir(), "results.sqlite3"))
	if err != nil {
		t.Fatal(err)
	}
	defer store.Close()
	now := time.Now().UTC()
	if _, err := store.db.Exec(`
		INSERT INTO task_results (
			task_id, status, start_time, end_time, duration_seconds,
			items_fetched, items_processed, items_uploaded, error_message,
			metadata_json, updated_at
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	`, "full", StatusCompleted, formatTaskTime(now), formatTaskTime(now),
		1.5, 1, 2, 3, "error", "not-json", formatTaskTime(now)); err != nil {
		t.Fatal(err)
	}
	results, err := store.LoadRecent(context.Background(), time.Hour)
	if err != nil {
		t.Fatal(err)
	}
	if len(results) != 1 || results[0].Duration == nil || results[0].ErrorMessage == nil ||
		len(results[0].Metadata) != 0 {
		t.Fatalf("optional fields = %#v", results)
	}
}

func TestResultStoreLoadScanError(t *testing.T) {
	store, err := NewResultStore(filepath.Join(t.TempDir(), "results.sqlite3"))
	if err != nil {
		t.Fatal(err)
	}
	defer store.Close()
	if _, err := store.db.Exec(`DROP TABLE task_results`); err != nil {
		t.Fatal(err)
	}
	if _, err := store.db.Exec(`
		CREATE TABLE task_results (
			task_id TEXT, status TEXT, start_time TEXT, end_time TEXT,
			duration_seconds REAL, items_fetched INTEGER, items_processed INTEGER,
			items_uploaded INTEGER, error_message TEXT, metadata_json TEXT,
			updated_at TEXT
		);
		INSERT INTO task_results (task_id, status, start_time, metadata_json)
		VALUES (NULL, 'completed', ?, '{}')
	`, formatTaskTime(time.Now())); err != nil {
		t.Fatal(err)
	}
	if _, err := store.LoadRecent(context.Background(), time.Hour); err == nil ||
		!strings.Contains(err.Error(), "scan task result") {
		t.Fatalf("scan error = %v", err)
	}
}

func ptrTime(value time.Time) *time.Time {
	return &value
}
