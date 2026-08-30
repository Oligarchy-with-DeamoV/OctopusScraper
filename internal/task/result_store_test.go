package task

import (
	"context"
	"database/sql"
	"errors"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"
)

func TestNewResultStoreContextHonorsCancellation(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	store, err := NewResultStoreContext(
		ctx,
		filepath.Join(t.TempDir(), "cancelled.sqlite3"),
	)
	if store != nil {
		store.Close()
		t.Fatal("NewResultStoreContext returned a store for a cancelled context")
	}
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("NewResultStoreContext error = %v", err)
	}
}

func TestResultStoreRejectsNewerSchema(t *testing.T) {
	path := filepath.Join(t.TempDir(), "newer.sqlite3")
	db, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(`PRAGMA user_version = 2`); err != nil {
		t.Fatal(err)
	}
	if err := db.Close(); err != nil {
		t.Fatal(err)
	}

	store, err := NewResultStore(path)
	if store != nil {
		store.Close()
		t.Fatal("NewResultStore returned a store for a newer schema")
	}
	if err == nil || !strings.Contains(err.Error(), "newer than supported") {
		t.Fatalf("NewResultStore error = %v", err)
	}
}

func TestResultStoreRejectsMalformedLegacyRows(t *testing.T) {
	testCases := []struct {
		name      string
		status    string
		startTime string
		wantError string
	}{
		{
			name:      "unsupported status",
			status:    "unknown",
			startTime: "2025-04-06T05:50:59",
			wantError: "unsupported status",
		},
		{
			name:      "malformed timestamp",
			status:    string(StatusCompleted),
			startTime: "not-a-time",
			wantError: "normalize task",
		},
	}
	for _, testCase := range testCases {
		t.Run(testCase.name, func(t *testing.T) {
			path := filepath.Join(t.TempDir(), "legacy.sqlite3")
			createLegacyTaskResultDatabase(
				t,
				path,
				testCase.status,
				testCase.startTime,
				0,
			)

			store, err := NewResultStore(path)
			if store != nil {
				store.Close()
				t.Fatal("NewResultStore returned a store for malformed legacy data")
			}
			if err == nil || !strings.Contains(err.Error(), testCase.wantError) {
				t.Fatalf("NewResultStore error = %v", err)
			}
			assertLegacyTaskResultDatabaseUnchanged(t, path, 0)
		})
	}
}

func TestResultStoreLegacyMigrationIncludesNonPositiveRowIDs(t *testing.T) {
	path := filepath.Join(t.TempDir(), "legacy.sqlite3")
	createLegacyTaskResultDatabase(
		t,
		path,
		string(StatusCompleted),
		"2025-04-06T05:50:59",
		0,
	)
	db, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(`UPDATE task_results SET rowid = 0 WHERE task_id = 'legacy'`); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(`
INSERT INTO task_results (
	rowid, task_id, status, start_time, metadata_json, updated_at
) VALUES (-1, 'negative-rowid', ?, '2025-04-06T05:50:59', '{}', '2025-04-06T05:50:59')
`, StatusCompleted); err != nil {
		t.Fatal(err)
	}
	if err := db.Close(); err != nil {
		t.Fatal(err)
	}

	store, err := NewResultStore(path)
	if err != nil {
		t.Fatal(err)
	}
	defer store.Close()
	var count int
	if err := store.db.QueryRow(`
SELECT COUNT(*)
FROM task_results
WHERE task_id IN ('legacy', 'negative-rowid')
`).Scan(&count); err != nil {
		t.Fatal(err)
	}
	if count != 2 {
		t.Fatalf("migrated non-positive rowid count = %d, want 2", count)
	}
}

func TestResultStoreLegacyMigrationRollsBackOnConstraintFailure(t *testing.T) {
	path := filepath.Join(t.TempDir(), "legacy.sqlite3")
	createLegacyTaskResultDatabase(
		t,
		path,
		string(StatusCompleted),
		"2025-04-06T05:50:59",
		-1,
	)

	store, err := NewResultStore(path)
	if store != nil {
		store.Close()
		t.Fatal("NewResultStore returned a store after a failed migration")
	}
	if err == nil || !strings.Contains(err.Error(), "copy legacy task result") {
		t.Fatalf("NewResultStore error = %v", err)
	}
	assertLegacyTaskResultDatabaseUnchanged(t, path, -1)
}

func TestResultStoreLegacyMigrationStreamsAndRollsBackLaterMalformedRow(t *testing.T) {
	path := filepath.Join(t.TempDir(), "legacy.sqlite3")
	db, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(`
CREATE TABLE task_results (
	task_id TEXT PRIMARY KEY,
	status TEXT NOT NULL,
	start_time TEXT NOT NULL,
	end_time TEXT,
	duration_seconds REAL,
	items_fetched INTEGER NOT NULL DEFAULT 0,
	items_processed INTEGER NOT NULL DEFAULT 0,
	items_uploaded INTEGER NOT NULL DEFAULT 0,
	error_message TEXT,
	metadata_json TEXT NOT NULL DEFAULT '{}',
	updated_at TEXT NOT NULL
)
`); err != nil {
		t.Fatal(err)
	}
	const validRows = legacyMigrationBatchSize + 1
	for index := range validRows {
		timestamp := "2025-04-06T05:50:59"
		taskID := "legacy-" + strconv.Itoa(index)
		if index == 0 {
			taskID = "legacy"
		}
		if _, err := db.Exec(`
INSERT INTO task_results (
	task_id, status, start_time, metadata_json, updated_at
) VALUES (?, ?, ?, ?, ?)
`, taskID, StatusCompleted, timestamp, `{"index":1}`, timestamp); err != nil {
			t.Fatal(err)
		}
	}
	if _, err := db.Exec(`
INSERT INTO task_results (
	task_id, status, start_time, metadata_json, updated_at
) VALUES ('malformed', ?, 'not-a-time', '{}', '2025-04-06T05:50:59')
`, StatusCompleted); err != nil {
		t.Fatal(err)
	}
	if err := db.Close(); err != nil {
		t.Fatal(err)
	}

	store, err := NewResultStore(path)
	if store != nil {
		store.Close()
		t.Fatal("NewResultStore returned a store after a failed migration")
	}
	if err == nil || !strings.Contains(err.Error(), `normalize task "malformed"`) {
		t.Fatalf("NewResultStore error = %v", err)
	}
	assertLegacyTaskResultDatabaseUnchanged(t, path, 0)
	assertLegacyTaskResultRowCount(t, path, validRows+1)
}

func TestResultStoreRetentionUsesNormalizedUTCOrdering(t *testing.T) {
	databasePath := filepath.Join(t.TempDir(), "results.sqlite3")
	store, err := NewResultStore(databasePath)
	if err != nil {
		t.Fatal(err)
	}

	now := time.Now().UTC().Truncate(time.Second)
	oldEnd := now.Add(-2 * time.Hour).In(time.FixedZone("UTC+8", 8*60*60))
	recentEnd := now.Add(-10 * time.Minute).In(time.FixedZone("UTC-7", -7*60*60))
	newestEnd := now.Add(-5 * time.Minute)
	results := []Result{
		{
			TaskID:    "old",
			Status:    StatusCompleted,
			StartTime: oldEnd.Add(-time.Minute),
			EndTime:   &oldEnd,
		},
		{
			TaskID:    "recent",
			Status:    StatusCompleted,
			StartTime: recentEnd.Add(-time.Minute),
			EndTime:   &recentEnd,
		},
		{
			TaskID:    "newest",
			Status:    StatusCompleted,
			StartTime: newestEnd.Add(-time.Minute),
			EndTime:   &newestEnd,
		},
		{
			TaskID:    "old-running",
			Status:    StatusRunning,
			StartTime: now.Add(-3 * time.Hour),
		},
	}
	for _, result := range results {
		if err := store.Save(context.Background(), result); err != nil {
			t.Fatalf("Save(%s): %v", result.TaskID, err)
		}
	}

	recent, err := store.LoadRecent(context.Background(), time.Hour)
	if err != nil {
		t.Fatal(err)
	}
	if len(recent) != 2 ||
		recent[0].TaskID != "newest" ||
		recent[1].TaskID != "recent" {
		t.Fatalf("recent results = %#v", recent)
	}

	manager, err := NewManager(
		nil,
		&fakeExecutor{failures: map[string]int{}},
		1,
		1,
		time.Hour,
		store,
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	if recovered, ok := manager.Result("old-running"); ok {
		t.Fatalf("expired recovered result remained in memory: %#v", recovered)
	}
	if err := manager.Stop(context.Background()); err != nil {
		t.Fatal(err)
	}

	reopened, err := NewResultStore(databasePath)
	if err != nil {
		t.Fatal(err)
	}
	defer reopened.Close()
	var (
		recoveredStatus  Status
		recoveredEnd     sql.NullString
		recoveredMessage sql.NullString
	)
	if err := reopened.db.QueryRow(`
SELECT status, end_time, error_message
FROM task_results
WHERE task_id = 'old-running'
`).Scan(&recoveredStatus, &recoveredEnd, &recoveredMessage); err != nil {
		t.Fatal(err)
	}
	if recoveredStatus != StatusFailed ||
		!recoveredEnd.Valid ||
		!recoveredMessage.Valid ||
		recoveredMessage.String != interruptedTaskMessage {
		t.Fatalf(
			"persisted old running recovery = (%q, %#v, %#v)",
			recoveredStatus,
			recoveredEnd,
			recoveredMessage,
		)
	}
}

func TestResultStoreRecoversInterruptedRowsInBatches(t *testing.T) {
	store, err := NewResultStore(filepath.Join(t.TempDir(), "results.sqlite3"))
	if err != nil {
		t.Fatal(err)
	}
	defer store.Close()
	startedAt := time.Now().Add(-time.Hour)
	for index := range interruptedRecoveryBatchSize + 1 {
		if err := store.Save(context.Background(), Result{
			TaskID:    "interrupted-" + strconv.Itoa(index),
			Status:    StatusRunning,
			StartTime: startedAt,
			Metadata:  map[string]any{},
		}); err != nil {
			t.Fatal(err)
		}
	}
	recovered, err := store.recoverInterrupted(context.Background(), time.Now())
	if err != nil {
		t.Fatal(err)
	}
	if recovered != interruptedRecoveryBatchSize+1 {
		t.Fatalf("recovered count = %d", recovered)
	}
	var remaining int
	if err := store.db.QueryRow(`
SELECT COUNT(*)
FROM task_results
WHERE status IN ('pending', 'running', 'retrying')
`).Scan(&remaining); err != nil {
		t.Fatal(err)
	}
	if remaining != 0 {
		t.Fatalf("remaining interrupted rows = %d", remaining)
	}

	deleted, err := store.DeleteOlderThan(
		context.Background(),
		time.Now().Add(time.Second),
	)
	if err != nil {
		t.Fatal(err)
	}
	if deleted != int64(interruptedRecoveryBatchSize+1) {
		t.Fatalf(
			"deleted rows = %d, want %d",
			deleted,
			interruptedRecoveryBatchSize+1,
		)
	}
	remaining = 0
	if err := store.db.QueryRow(`SELECT COUNT(*) FROM task_results`).Scan(&remaining); err != nil {
		t.Fatal(err)
	}
	if remaining != 0 {
		t.Fatalf("remaining rows = %d, want 0", remaining)
	}
}

func TestResultStoreRecoveryKeepsCommittedBatchesOnLaterError(t *testing.T) {
	store, err := NewResultStore(filepath.Join(t.TempDir(), "results.sqlite3"))
	if err != nil {
		t.Fatal(err)
	}
	defer store.Close()
	startedAt := time.Now().Add(-time.Hour)
	for index := range interruptedRecoveryBatchSize {
		if err := store.Save(context.Background(), Result{
			TaskID:    "valid-" + strconv.Itoa(index),
			Status:    StatusRunning,
			StartTime: startedAt,
			Metadata:  map[string]any{},
		}); err != nil {
			t.Fatal(err)
		}
	}
	if _, err := store.db.Exec(`
INSERT INTO task_results (
	task_id, status, start_time, metadata_json, updated_at
) VALUES ('zzz-malformed', ?, 'not-a-time', '{}', 'not-a-time')
`, StatusRunning); err != nil {
		t.Fatal(err)
	}
	recovered, err := store.recoverInterrupted(context.Background(), time.Now())
	if err == nil {
		t.Fatal("recoverInterrupted accepted malformed later batch")
	}
	if recovered != interruptedRecoveryBatchSize {
		t.Fatalf("recovered count = %d, want %d", recovered, interruptedRecoveryBatchSize)
	}
	var (
		failedCount     int
		malformedStatus Status
	)
	if err := store.db.QueryRow(`
SELECT COUNT(*)
FROM task_results
WHERE task_id LIKE 'valid-%' AND status = 'failed'
`).Scan(&failedCount); err != nil {
		t.Fatal(err)
	}
	if err := store.db.QueryRow(`
SELECT status
FROM task_results
WHERE task_id = 'zzz-malformed'
`).Scan(&malformedStatus); err != nil {
		t.Fatal(err)
	}
	if failedCount != interruptedRecoveryBatchSize ||
		malformedStatus != StatusRunning {
		t.Fatalf(
			"partial recovery = (%d, %q)",
			failedCount,
			malformedStatus,
		)
	}
}

func createLegacyTaskResultDatabase(
	t *testing.T,
	path string,
	status string,
	startTime string,
	itemsFetched int,
) {
	t.Helper()

	db, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	if _, err := db.Exec(`
CREATE TABLE task_results (
	task_id TEXT PRIMARY KEY,
	status TEXT NOT NULL,
	start_time TEXT NOT NULL,
	end_time TEXT,
	duration_seconds REAL,
	items_fetched INTEGER NOT NULL DEFAULT 0,
	items_processed INTEGER NOT NULL DEFAULT 0,
	items_uploaded INTEGER NOT NULL DEFAULT 0,
	error_message TEXT,
	metadata_json TEXT NOT NULL DEFAULT '{}',
	updated_at TEXT NOT NULL
)
`); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(`
INSERT INTO task_results (
	task_id, status, start_time, items_fetched, metadata_json, updated_at
)
VALUES ('legacy', ?, ?, ?, '{}', ?)
`, status, startTime, itemsFetched, startTime); err != nil {
		t.Fatal(err)
	}
}

func assertLegacyTaskResultDatabaseUnchanged(
	t *testing.T,
	path string,
	wantItemsFetched int,
) {
	t.Helper()

	db, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	var (
		version         int
		itemsFetched    int
		migratedTables  int
		legacyTableName string
	)
	if err := db.QueryRow(`PRAGMA user_version`).Scan(&version); err != nil {
		t.Fatal(err)
	}
	if err := db.QueryRow(
		`SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'task_results'`,
	).Scan(&legacyTableName); err != nil {
		t.Fatal(err)
	}
	if err := db.QueryRow(
		`SELECT items_fetched FROM task_results WHERE task_id = 'legacy'`,
	).Scan(&itemsFetched); err != nil {
		t.Fatal(err)
	}
	if err := db.QueryRow(`
SELECT COUNT(*)
FROM sqlite_master
WHERE type = 'table' AND name = 'task_results_v0'
`).Scan(&migratedTables); err != nil {
		t.Fatal(err)
	}
	if version != 0 ||
		legacyTableName != "task_results" ||
		itemsFetched != wantItemsFetched ||
		migratedTables != 0 {
		t.Fatalf(
			"legacy database changed: version=%d table=%q items=%d migrated_tables=%d",
			version,
			legacyTableName,
			itemsFetched,
			migratedTables,
		)
	}
}

func assertLegacyTaskResultRowCount(t *testing.T, path string, want int) {
	t.Helper()

	db, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	var count int
	if err := db.QueryRow(`SELECT COUNT(*) FROM task_results`).Scan(&count); err != nil {
		t.Fatal(err)
	}
	if count != want {
		t.Fatalf("legacy row count = %d, want %d", count, want)
	}
}
