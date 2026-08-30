package task

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"

	_ "modernc.org/sqlite"
)

const taskResultSchemaVersion = 1
const legacyMigrationBatchSize = 128
const interruptedRecoveryBatchSize = 128

const createTaskResultsSQL = `
CREATE TABLE IF NOT EXISTS task_results (
	task_id TEXT PRIMARY KEY,
	status TEXT NOT NULL CHECK (
		status IN ('pending', 'running', 'completed', 'failed', 'cancelled', 'retrying')
	),
	start_time TEXT NOT NULL,
	end_time TEXT,
	duration_seconds REAL,
	items_fetched INTEGER NOT NULL DEFAULT 0 CHECK (items_fetched >= 0),
	items_processed INTEGER NOT NULL DEFAULT 0 CHECK (items_processed >= 0),
	items_uploaded INTEGER NOT NULL DEFAULT 0 CHECK (items_uploaded >= 0),
	error_message TEXT,
	metadata_json TEXT NOT NULL DEFAULT '{}',
	updated_at TEXT NOT NULL
)`

const createTaskResultIndexesSQL = `
CREATE INDEX IF NOT EXISTS ix_task_results_start_time
	ON task_results (start_time DESC);
CREATE INDEX IF NOT EXISTS ix_task_results_end_time
	ON task_results (end_time)
	WHERE end_time IS NOT NULL`

type persistedResultRow struct {
	taskID         string
	status         string
	startTime      string
	endTime        sql.NullString
	duration       sql.NullFloat64
	itemsFetched   int
	itemsProcessed int
	itemsUploaded  int
	errorMessage   sql.NullString
	metadataJSON   string
	updatedAt      string
}

// ResultStore persists task results using the legacy-compatible SQLite schema.
type ResultStore struct {
	db *sql.DB
}

func NewResultStore(path string) (*ResultStore, error) {
	return NewResultStoreContext(context.Background(), path)
}

// NewResultStoreContext opens and migrates task history while honoring cancellation.
func NewResultStoreContext(ctx context.Context, path string) (*ResultStore, error) {
	if path == "" {
		return nil, nil
	}
	if err := ctx.Err(); err != nil {
		return nil, fmt.Errorf("open task result database: %w", err)
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return nil, fmt.Errorf("create task result directory: %w", err)
	}
	db, err := sql.Open("sqlite", path)
	if err != nil {
		return nil, fmt.Errorf("open task result database: %w", err)
	}
	db.SetMaxOpenConns(1)
	db.SetMaxIdleConns(1)
	store := &ResultStore{db: db}
	if err := store.initialize(ctx); err != nil {
		db.Close()
		return nil, err
	}
	return store, nil
}

func (s *ResultStore) initialize(ctx context.Context) error {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("begin task result migration: %w", err)
	}
	defer tx.Rollback()

	var version int
	if err := tx.QueryRowContext(ctx, `PRAGMA user_version`).Scan(&version); err != nil {
		return fmt.Errorf("read task result schema version: %w", err)
	}
	if version > taskResultSchemaVersion {
		return fmt.Errorf(
			"task result schema version %d is newer than supported version %d",
			version,
			taskResultSchemaVersion,
		)
	}
	if version == 0 {
		if err := migrateTaskResultsV0(ctx, tx); err != nil {
			return err
		}
		if _, err := tx.ExecContext(
			ctx,
			fmt.Sprintf("PRAGMA user_version = %d", taskResultSchemaVersion),
		); err != nil {
			return fmt.Errorf("record task result schema version: %w", err)
		}
	}
	if _, err := tx.ExecContext(ctx, createTaskResultsSQL); err != nil {
		return fmt.Errorf("create task result schema: %w", err)
	}
	if _, err := tx.ExecContext(ctx, createTaskResultIndexesSQL); err != nil {
		return fmt.Errorf("create task result indexes: %w", err)
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("commit task result migration: %w", err)
	}
	return nil
}

func migrateTaskResultsV0(ctx context.Context, tx *sql.Tx) error {
	var tableName string
	err := tx.QueryRowContext(ctx, `
SELECT name
FROM sqlite_master
WHERE type = 'table' AND name = 'task_results'
`).Scan(&tableName)
	if err != nil {
		if err == sql.ErrNoRows {
			if _, err := tx.ExecContext(ctx, createTaskResultsSQL); err != nil {
				return fmt.Errorf("create task result schema: %w", err)
			}
			return nil
		}
		return fmt.Errorf("inspect task result schema: %w", err)
	}

	if _, err := tx.ExecContext(
		ctx,
		`ALTER TABLE task_results RENAME TO task_results_v0`,
	); err != nil {
		return fmt.Errorf("rename legacy task result table: %w", err)
	}
	if _, err := tx.ExecContext(ctx, createTaskResultsSQL); err != nil {
		return fmt.Errorf("create migrated task result schema: %w", err)
	}

	var (
		lastRowID int64
		hasCursor bool
	)
	for {
		query := `
SELECT rowid, task_id, status, start_time, end_time, duration_seconds,
       items_fetched, items_processed, items_uploaded,
       error_message, metadata_json, updated_at
FROM task_results_v0
ORDER BY rowid
LIMIT ?
`
		args := []any{legacyMigrationBatchSize}
		if hasCursor {
			query = `
SELECT rowid, task_id, status, start_time, end_time, duration_seconds,
       items_fetched, items_processed, items_uploaded,
       error_message, metadata_json, updated_at
FROM task_results_v0
WHERE rowid > ?
ORDER BY rowid
LIMIT ?
`
			args = []any{lastRowID, legacyMigrationBatchSize}
		}
		rows, err := tx.QueryContext(ctx, query, args...)
		if err != nil {
			return fmt.Errorf("read legacy task results: %w", err)
		}
		results := make([]persistedResultRow, 0, legacyMigrationBatchSize)
		for rows.Next() {
			var (
				rowID  int64
				result persistedResultRow
			)
			if err := rows.Scan(
				&rowID,
				&result.taskID,
				&result.status,
				&result.startTime,
				&result.endTime,
				&result.duration,
				&result.itemsFetched,
				&result.itemsProcessed,
				&result.itemsUploaded,
				&result.errorMessage,
				&result.metadataJSON,
				&result.updatedAt,
			); err != nil {
				rows.Close()
				return fmt.Errorf("scan legacy task result: %w", err)
			}
			if !validTaskStatus(Status(result.status)) {
				rows.Close()
				return fmt.Errorf(
					"legacy task result %q has unsupported status %q",
					result.taskID,
					result.status,
				)
			}
			startTime, err := normalizeTaskTimeText(result.startTime)
			if err != nil {
				rows.Close()
				return fmt.Errorf("normalize task %q start time: %w", result.taskID, err)
			}
			result.startTime = startTime
			if result.endTime.Valid {
				endTime, err := normalizeTaskTimeText(result.endTime.String)
				if err != nil {
					rows.Close()
					return fmt.Errorf("normalize task %q end time: %w", result.taskID, err)
				}
				result.endTime.String = endTime
			}
			updatedAt, err := normalizeTaskTimeText(result.updatedAt)
			if err != nil {
				rows.Close()
				return fmt.Errorf("normalize task %q update time: %w", result.taskID, err)
			}
			result.updatedAt = updatedAt
			results = append(results, result)
			lastRowID = rowID
			hasCursor = true
		}
		if err := rows.Err(); err != nil {
			rows.Close()
			return fmt.Errorf("iterate legacy task results: %w", err)
		}
		if err := rows.Close(); err != nil {
			return fmt.Errorf("close legacy task results: %w", err)
		}
		if len(results) == 0 {
			break
		}
		for _, result := range results {
			if _, err := tx.ExecContext(ctx, `
INSERT INTO task_results (
	task_id, status, start_time, end_time, duration_seconds,
	items_fetched, items_processed, items_uploaded,
	error_message, metadata_json, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
`,
				result.taskID,
				result.status,
				result.startTime,
				result.endTime,
				result.duration,
				result.itemsFetched,
				result.itemsProcessed,
				result.itemsUploaded,
				result.errorMessage,
				result.metadataJSON,
				result.updatedAt,
			); err != nil {
				return fmt.Errorf("copy legacy task result %q: %w", result.taskID, err)
			}
		}
	}
	var legacyCount, migratedCount int64
	if err := tx.QueryRowContext(ctx, `
SELECT
    (SELECT COUNT(*) FROM task_results_v0),
    (SELECT COUNT(*) FROM task_results)
`).Scan(&legacyCount, &migratedCount); err != nil {
		return fmt.Errorf("verify migrated task result count: %w", err)
	}
	if migratedCount != legacyCount {
		return fmt.Errorf(
			"verify migrated task result count: copied %d of %d rows",
			migratedCount,
			legacyCount,
		)
	}
	if _, err := tx.ExecContext(ctx, `DROP TABLE task_results_v0`); err != nil {
		return fmt.Errorf("drop legacy task result table: %w", err)
	}
	return nil
}

func normalizeTaskTimeText(value string) (string, error) {
	parsed, err := parseTaskTime(value)
	if err != nil {
		return "", err
	}
	return formatTaskTime(parsed), nil
}

func validTaskStatus(status Status) bool {
	switch status {
	case StatusPending,
		StatusRunning,
		StatusCompleted,
		StatusFailed,
		StatusCancelled,
		StatusRetrying:
		return true
	default:
		return false
	}
}

func (s *ResultStore) Save(ctx context.Context, result Result) error {
	if s == nil {
		return nil
	}
	metadata, err := json.Marshal(result.Metadata)
	if err != nil {
		return fmt.Errorf("marshal task metadata: %w", err)
	}
	_, err = s.db.ExecContext(ctx, `
		INSERT INTO task_results (
			task_id, status, start_time, end_time, duration_seconds,
			items_fetched, items_processed, items_uploaded,
			error_message, metadata_json, updated_at
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT(task_id) DO UPDATE SET
			status = excluded.status,
			start_time = excluded.start_time,
			end_time = excluded.end_time,
			duration_seconds = excluded.duration_seconds,
			items_fetched = excluded.items_fetched,
			items_processed = excluded.items_processed,
			items_uploaded = excluded.items_uploaded,
			error_message = excluded.error_message,
			metadata_json = excluded.metadata_json,
			updated_at = excluded.updated_at
	`,
		result.TaskID,
		result.Status,
		formatTaskTime(result.StartTime),
		optionalTimeText(result.EndTime),
		result.Duration,
		result.ItemsFetched,
		result.ItemsProcessed,
		result.ItemsUploaded,
		result.ErrorMessage,
		string(metadata),
		formatTaskTime(time.Now()),
	)
	if err != nil {
		return fmt.Errorf("save task result: %w", err)
	}
	return nil
}

func (s *ResultStore) LoadRecent(
	ctx context.Context,
	retention time.Duration,
) ([]Result, error) {
	if s == nil {
		return nil, nil
	}
	cutoff := formatTaskTime(time.Now().Add(-retention))
	rows, err := s.db.QueryContext(ctx, `
		SELECT task_id, status, start_time, end_time, duration_seconds,
		       items_fetched, items_processed, items_uploaded,
		       error_message, metadata_json
		FROM task_results
		WHERE COALESCE(end_time, start_time) >= ?
		  AND (
		      error_message IS NULL
		      OR error_message <> ?
		      OR start_time >= ?
		  )
		ORDER BY start_time DESC
	`, cutoff, interruptedTaskMessage, cutoff)
	if err != nil {
		return nil, fmt.Errorf("load task results: %w", err)
	}
	defer rows.Close()

	var results []Result
	for rows.Next() {
		var (
			result       Result
			startText    string
			endText      sql.NullString
			duration     sql.NullFloat64
			errorMessage sql.NullString
			metadataText string
		)
		if err := rows.Scan(
			&result.TaskID,
			&result.Status,
			&startText,
			&endText,
			&duration,
			&result.ItemsFetched,
			&result.ItemsProcessed,
			&result.ItemsUploaded,
			&errorMessage,
			&metadataText,
		); err != nil {
			return nil, fmt.Errorf("scan task result: %w", err)
		}
		result.StartTime, err = parseTaskTime(startText)
		if err != nil {
			return nil, fmt.Errorf("parse task start time: %w", err)
		}
		if endText.Valid {
			value, parseErr := parseTaskTime(endText.String)
			if parseErr != nil {
				return nil, fmt.Errorf("parse task end time: %w", parseErr)
			}
			result.EndTime = &value
		}
		if duration.Valid {
			value := duration.Float64
			result.Duration = &value
		}
		if errorMessage.Valid {
			value := errorMessage.String
			result.ErrorMessage = &value
		}
		if err := json.Unmarshal([]byte(metadataText), &result.Metadata); err != nil {
			result.Metadata = map[string]any{}
		}
		results = append(results, result)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate task results: %w", err)
	}
	return results, nil
}

func (s *ResultStore) recoverInterrupted(
	ctx context.Context,
	recoveredAt time.Time,
) (int, error) {
	if s == nil {
		return 0, nil
	}

	recoveredAt = recoveredAt.UTC()
	recovered := 0
	for {
		tx, err := s.db.BeginTx(ctx, nil)
		if err != nil {
			return recovered, fmt.Errorf("begin interrupted task recovery: %w", err)
		}
		rows, err := tx.QueryContext(ctx, `
SELECT task_id, status, start_time
FROM task_results
WHERE status IN ('pending', 'running', 'retrying')
ORDER BY task_id
LIMIT ?
`, interruptedRecoveryBatchSize)
		if err != nil {
			tx.Rollback()
			return recovered, fmt.Errorf("read interrupted task results: %w", err)
		}
		results := make([]Result, 0, interruptedRecoveryBatchSize)
		for rows.Next() {
			var (
				result    Result
				startText string
			)
			if err := rows.Scan(&result.TaskID, &result.Status, &startText); err != nil {
				rows.Close()
				tx.Rollback()
				return recovered, fmt.Errorf("scan interrupted task result: %w", err)
			}
			result.StartTime, err = parseTaskTime(startText)
			if err != nil {
				rows.Close()
				tx.Rollback()
				return recovered, fmt.Errorf(
					"parse interrupted task %q start time: %w",
					result.TaskID,
					err,
				)
			}
			results = append(results, result)
		}
		if err := rows.Err(); err != nil {
			rows.Close()
			tx.Rollback()
			return recovered, fmt.Errorf("iterate interrupted task results: %w", err)
		}
		if err := rows.Close(); err != nil {
			tx.Rollback()
			return recovered, fmt.Errorf("close interrupted task results: %w", err)
		}
		if len(results) == 0 {
			tx.Rollback()
			return recovered, nil
		}
		batchRecovered := 0
		for index := range results {
			result := &results[index]
			if !markInterruptedResult(result, recoveredAt) {
				continue
			}
			update, err := tx.ExecContext(ctx, `
UPDATE task_results
SET status = ?,
    end_time = ?,
    duration_seconds = ?,
    error_message = ?,
    updated_at = ?
WHERE task_id = ?
  AND status IN ('pending', 'running', 'retrying')
`,
				result.Status,
				optionalTimeText(result.EndTime),
				result.Duration,
				result.ErrorMessage,
				formatTaskTime(recoveredAt),
				result.TaskID,
			)
			if err != nil {
				tx.Rollback()
				return recovered, fmt.Errorf(
					"persist interrupted task %q recovery: %w",
					result.TaskID,
					err,
				)
			}
			affected, err := update.RowsAffected()
			if err != nil {
				tx.Rollback()
				return recovered, fmt.Errorf(
					"count interrupted task %q recovery: %w",
					result.TaskID,
					err,
				)
			}
			batchRecovered += int(affected)
		}
		if err := tx.Commit(); err != nil {
			return recovered, fmt.Errorf("commit interrupted task recovery batch: %w", err)
		}
		recovered += batchRecovered
	}
}

func (s *ResultStore) DeleteOlderThan(ctx context.Context, cutoff time.Time) (int64, error) {
	if s == nil {
		return 0, nil
	}
	result, err := s.db.ExecContext(ctx, `
		DELETE FROM task_results
		WHERE end_time IS NOT NULL AND end_time < ?
	`, formatTaskTime(cutoff))
	if err != nil {
		return 0, fmt.Errorf("delete old task results: %w", err)
	}
	return result.RowsAffected()
}

func (s *ResultStore) Close() error {
	if s == nil {
		return nil
	}
	return s.db.Close()
}

func optionalTimeText(value *time.Time) any {
	if value == nil {
		return nil
	}
	return formatTaskTime(*value)
}
