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

// ResultStore persists task results using the legacy-compatible SQLite schema.
type ResultStore struct {
	db *sql.DB
}

func NewResultStore(path string) (*ResultStore, error) {
	if path == "" {
		return nil, nil
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
	if err := store.initialize(context.Background()); err != nil {
		db.Close()
		return nil, err
	}
	return store, nil
}

func (s *ResultStore) initialize(ctx context.Context) error {
	_, err := s.db.ExecContext(ctx, `
		CREATE TABLE IF NOT EXISTS task_results (
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
	`)
	if err != nil {
		return fmt.Errorf("initialize task result schema: %w", err)
	}
	return nil
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
		ORDER BY start_time DESC
	`, cutoff)
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
