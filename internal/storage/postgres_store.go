package storage

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"strings"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/config"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgtype"
	"github.com/jackc/pgx/v5/pgxpool"
)

const (
	migrationLockKey int64 = 739102001
	defaultChunkSize       = 512
)

const (
	createSchemaMigrationsSQL = `
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL
)`
	createContentsSQL = `
CREATE TABLE IF NOT EXISTS contents (
    content_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    link TEXT NOT NULL,
    summary TEXT NOT NULL,
    content TEXT NOT NULL,
    published TEXT NOT NULL,
    author TEXT,
    keywords_json TEXT NOT NULL DEFAULT '[]',
    tags_json TEXT NOT NULL DEFAULT '[]',
    scraper_name VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    notion_sync_status VARCHAR(32) NOT NULL DEFAULT 'pending',
    notion_synced_at TIMESTAMPTZ,
    notion_sync_attempts INTEGER NOT NULL DEFAULT 0,
    notion_sync_error TEXT,
    notion_next_attempt_at TIMESTAMPTZ NOT NULL,
    notion_claimed_by VARCHAR(128),
    notion_claimed_at TIMESTAMPTZ,
    notion_lease_expires_at TIMESTAMPTZ
)`
	createContentIndexesSQL = `
CREATE INDEX IF NOT EXISTS ix_contents_notion_sync_status ON contents (notion_sync_status);
CREATE INDEX IF NOT EXISTS ix_contents_notion_next_attempt_at ON contents (notion_next_attempt_at);
CREATE INDEX IF NOT EXISTS ix_contents_notion_claimed_by ON contents (notion_claimed_by);
CREATE INDEX IF NOT EXISTS ix_contents_notion_lease_expires_at ON contents (notion_lease_expires_at)`
)

type dbPool interface {
	Begin(context.Context) (pgx.Tx, error)
	Ping(context.Context) error
	Close()
	Exec(context.Context, string, ...any) (pgconn.CommandTag, error)
	Query(context.Context, string, ...any) (pgx.Rows, error)
	QueryRow(context.Context, string, ...any) pgx.Row
}

// PostgresStore persists canonical content and Notion sync state in PostgreSQL.
type PostgresStore struct {
	pool      dbPool
	chunkSize int
	logger    *slog.Logger
}

func NewPostgresStore(
	cfg config.DatabaseConfig,
	logger *slog.Logger,
) (*PostgresStore, error) {
	poolConfig, err := pgxpool.ParseConfig(cfg.URL)
	if err != nil {
		return nil, fmt.Errorf("parse postgres config: %w", err)
	}
	if cfg.ConnectTimeout > 0 {
		poolConfig.ConnConfig.ConnectTimeout = cfg.ConnectTimeout
	}
	maxConns := int64(cfg.PoolSize + cfg.MaxOverflow)
	if maxConns <= 0 {
		maxConns = 1
	}
	poolConfig.MaxConns = int32(maxConns)
	pool, err := pgxpool.NewWithConfig(context.Background(), poolConfig)
	if err != nil {
		return nil, fmt.Errorf("create postgres pool: %w", err)
	}
	return &PostgresStore{
		pool:      pool,
		chunkSize: defaultChunkSize,
		logger:    logger,
	}, nil
}

func newPostgresStoreWithPool(pool dbPool) *PostgresStore {
	return &PostgresStore{pool: pool, chunkSize: defaultChunkSize}
}

func (s *PostgresStore) Initialize(ctx context.Context) error {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("begin schema migration: %w", err)
	}
	defer tx.Rollback(ctx)
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock($1)`, migrationLockKey); err != nil {
		return fmt.Errorf("acquire schema migration lock: %w", err)
	}
	for _, statement := range []string{createSchemaMigrationsSQL, createContentsSQL, createContentIndexesSQL} {
		if _, err := tx.Exec(ctx, statement); err != nil {
			return fmt.Errorf("apply schema migration: %w", err)
		}
	}
	if _, err := tx.Exec(ctx, `
INSERT INTO schema_migrations (version, applied_at)
VALUES ($1, NOW())
ON CONFLICT (version) DO NOTHING
`, SchemaVersion); err != nil {
		return fmt.Errorf("record schema version: %w", err)
	}
	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("commit schema migration: %w", err)
	}
	if s.logger != nil {
		s.logger.Info("initialized postgres store schema", "schema_version", SchemaVersion)
	}
	return nil
}

func (s *PostgresStore) Ping(ctx context.Context) error {
	return s.pool.Ping(ctx)
}

func (s *PostgresStore) Close() {
	if s == nil || s.pool == nil {
		return
	}
	s.pool.Close()
}

func (s *PostgresStore) ExistingContentIDs(ctx context.Context, contentIDs []string) (map[string]struct{}, error) {
	ids := deduplicateIDs(contentIDs)
	result := make(map[string]struct{}, len(ids))
	if len(ids) == 0 {
		return result, nil
	}
	for start := 0; start < len(ids); start += s.chunkSize {
		end := start + s.chunkSize
		if end > len(ids) {
			end = len(ids)
		}
		rows, err := s.pool.Query(ctx, `SELECT content_id FROM contents WHERE content_id = ANY($1)`, ids[start:end])
		if err != nil {
			return nil, fmt.Errorf("query existing content IDs: %w", err)
		}
		for rows.Next() {
			var contentID string
			if err := rows.Scan(&contentID); err != nil {
				rows.Close()
				return nil, fmt.Errorf("scan existing content ID: %w", err)
			}
			result[contentID] = struct{}{}
		}
		if err := rows.Err(); err != nil {
			rows.Close()
			return nil, fmt.Errorf("iterate existing content IDs: %w", err)
		}
		rows.Close()
	}
	return result, nil
}

func (s *PostgresStore) StoreContents(ctx context.Context, contents []content.Content) (StoreStats, error) {
	stats := StoreStats{Requested: len(contents)}
	unique := uniqueContents(contents)
	if len(unique) == 0 {
		stats.Duplicates = len(contents)
		return stats, nil
	}
	chunkSize := s.chunkSize
	if chunkSize <= 0 {
		chunkSize = defaultChunkSize
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return stats, fmt.Errorf("begin content batch: %w", err)
	}
	defer tx.Rollback(ctx)
	for start := 0; start < len(unique); start += chunkSize {
		end := min(start+chunkSize, len(unique))
		query, args, err := buildInsertContentsQuery(unique[start:end])
		if err != nil {
			return stats, err
		}
		commandTag, err := tx.Exec(ctx, query, args...)
		if err != nil {
			return stats, fmt.Errorf("insert contents: %w", err)
		}
		stats.Inserted += int(commandTag.RowsAffected())
	}
	if err := tx.Commit(ctx); err != nil {
		return stats, fmt.Errorf("commit content batch: %w", err)
	}
	stats.Duplicates = len(contents) - stats.Inserted
	if s.logger != nil {
		s.logger.Debug(
			"stored contents batch",
			"requested", stats.Requested,
			"inserted", stats.Inserted,
			"duplicates", stats.Duplicates,
		)
	}
	return stats, nil
}

func (s *PostgresStore) ClaimContents(ctx context.Context, workerID string, batchSize int, lease time.Duration, maxAttempts int) ([]content.Content, error) {
	rows, err := s.pool.Query(ctx, `
WITH due AS (
    SELECT content_id
    FROM contents
    WHERE (
        notion_sync_status IN ($1, $2)
        AND notion_sync_attempts < $3
        AND notion_next_attempt_at <= NOW()
    ) OR (
        notion_sync_status = $4
        AND notion_lease_expires_at <= NOW()
    )
    ORDER BY created_at, content_id
    LIMIT $5
    FOR UPDATE SKIP LOCKED
)
UPDATE contents AS c
SET notion_sync_status = $4,
    notion_claimed_by = $6,
    notion_claimed_at = NOW(),
    notion_lease_expires_at = NOW() + ($7 * INTERVAL '1 second'),
    updated_at = NOW()
FROM due
WHERE c.content_id = due.content_id
RETURNING c.content_id, c.title, c.link, c.summary, c.content, c.published,
          c.author, c.keywords_json, c.tags_json, c.scraper_name
`, SyncPending, SyncRetry, maxAttempts, SyncProcessing, batchSize, workerID, int(lease.Seconds()))
	if err != nil {
		return nil, fmt.Errorf("claim contents: %w", err)
	}
	defer rows.Close()
	claimed, err := scanContents(rows)
	if err != nil {
		return nil, err
	}
	return claimed, nil
}

func (s *PostgresStore) RenewClaim(ctx context.Context, contentID, workerID string, lease time.Duration) (bool, error) {
	commandTag, err := s.pool.Exec(ctx, `
UPDATE contents
SET notion_lease_expires_at = NOW() + ($1 * INTERVAL '1 second'),
    updated_at = NOW()
WHERE content_id = $2
  AND notion_claimed_by = $3
  AND notion_sync_status = $4
`, int(lease.Seconds()), contentID, workerID, SyncProcessing)
	if err != nil {
		return false, fmt.Errorf("renew content claim: %w", err)
	}
	return commandTag.RowsAffected() == 1, nil
}

func (s *PostgresStore) MarkSynced(ctx context.Context, contentID, workerID string) (bool, error) {
	commandTag, err := s.pool.Exec(ctx, `
UPDATE contents
SET notion_sync_status = $1,
    notion_synced_at = NOW(),
    notion_sync_error = NULL,
    notion_claimed_by = NULL,
    notion_claimed_at = NULL,
    notion_lease_expires_at = NULL,
    updated_at = NOW()
WHERE content_id = $2
  AND notion_claimed_by = $3
  AND notion_sync_status = $4
`, SyncSynced, contentID, workerID, SyncProcessing)
	if err != nil {
		return false, fmt.Errorf("mark content synced: %w", err)
	}
	return commandTag.RowsAffected() == 1, nil
}

func (s *PostgresStore) MarkSyncFailed(ctx context.Context, contentID, workerID, errorMessage string, maxAttempts int) (bool, error) {
	var attemptsBefore int
	if err := s.pool.QueryRow(ctx, `
SELECT notion_sync_attempts
FROM contents
WHERE content_id = $1
  AND notion_claimed_by = $2
  AND notion_sync_status = $3
`, contentID, workerID, SyncProcessing).Scan(&attemptsBefore); err != nil {
		if err == pgx.ErrNoRows {
			return false, nil
		}
		return false, fmt.Errorf("load sync attempts: %w", err)
	}
	attempts := attemptsBefore + 1
	status := SyncRetry
	if attempts >= maxAttempts {
		status = SyncFailed
	}
	commandTag, err := s.pool.Exec(ctx, `
UPDATE contents
SET notion_sync_attempts = $1,
    notion_sync_status = $2,
    notion_sync_error = LEFT($3, 2000),
    notion_next_attempt_at = NOW() + ($4 * INTERVAL '1 second'),
    notion_claimed_by = NULL,
    notion_claimed_at = NULL,
    notion_lease_expires_at = NULL,
    updated_at = NOW()
WHERE content_id = $5
  AND notion_claimed_by = $6
  AND notion_sync_status = $7
  AND notion_sync_attempts = $8
`, attempts, status, errorMessage, int(nextRetryDelay(attempts).Seconds()), contentID, workerID, SyncProcessing, attemptsBefore)
	if err != nil {
		return false, fmt.Errorf("mark sync failed: %w", err)
	}
	return commandTag.RowsAffected() == 1, nil
}

func (s *PostgresStore) SyncCounts(ctx context.Context) (map[string]int64, error) {
	rows, err := s.pool.Query(ctx, `
SELECT notion_sync_status, COUNT(content_id)
FROM contents
GROUP BY notion_sync_status
`)
	if err != nil {
		return nil, fmt.Errorf("query sync counts: %w", err)
	}
	defer rows.Close()
	counts := map[string]int64{
		SyncPending:    0,
		SyncProcessing: 0,
		SyncRetry:      0,
		SyncSynced:     0,
		SyncFailed:     0,
	}
	for rows.Next() {
		var status string
		var count int64
		if err := rows.Scan(&status, &count); err != nil {
			return nil, fmt.Errorf("scan sync count: %w", err)
		}
		counts[status] = count
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate sync counts: %w", err)
	}
	return counts, nil
}

func nextRetryDelay(attempt int) time.Duration {
	if attempt <= 0 {
		attempt = 1
	}
	seconds := 60
	for index := 1; index < attempt; index++ {
		seconds *= 2
		if seconds >= 3600 {
			seconds = 3600
			break
		}
	}
	return time.Duration(seconds) * time.Second
}

func buildInsertContentsQuery(contents []content.Content) (string, []any, error) {
	var builder strings.Builder
	builder.WriteString(`
INSERT INTO contents (
    content_id, title, link, summary, content, published, author,
    keywords_json, tags_json, scraper_name, created_at, updated_at,
    notion_sync_status, notion_sync_attempts, notion_next_attempt_at
) VALUES `)
	args := make([]any, 0, len(contents)*15)
	placeholder := 1
	for index, item := range contents {
		if index > 0 {
			builder.WriteString(",")
		}
		keywordsJSON, err := json.Marshal(item.Keywords)
		if item.Keywords == nil {
			keywordsJSON = []byte("[]")
		}
		if err != nil {
			return "", nil, fmt.Errorf("marshal keywords for %s: %w", item.ContentID, err)
		}
		tagsJSON, err := json.Marshal(item.Tags)
		if item.Tags == nil {
			tagsJSON = []byte("[]")
		}
		if err != nil {
			return "", nil, fmt.Errorf("marshal tags for %s: %w", item.ContentID, err)
		}
		builder.WriteString(fmt.Sprintf(`
    ($%d,$%d,$%d,$%d,$%d,$%d,$%d,$%d,$%d,$%d,NOW(),NOW(),$%d,$%d,NOW())`,
			placeholder, placeholder+1, placeholder+2, placeholder+3, placeholder+4,
			placeholder+5, placeholder+6, placeholder+7, placeholder+8, placeholder+9,
			placeholder+10, placeholder+11,
		))
		args = append(args,
			item.ContentID,
			item.Title,
			item.Link,
			item.Summary,
			item.Content,
			item.Published,
			item.Author,
			string(keywordsJSON),
			string(tagsJSON),
			item.ScraperName,
			SyncPending,
			0,
		)
		placeholder += 12
	}
	builder.WriteString(`
ON CONFLICT (content_id) DO NOTHING`)
	return builder.String(), args, nil
}

func scanContents(rows pgx.Rows) ([]content.Content, error) {
	contents := make([]content.Content, 0)
	for rows.Next() {
		var (
			item         content.Content
			author       pgtype.Text
			keywordsJSON string
			tagsJSON     string
			scraperName  pgtype.Text
		)
		if err := rows.Scan(
			&item.ContentID,
			&item.Title,
			&item.Link,
			&item.Summary,
			&item.Content,
			&item.Published,
			&author,
			&keywordsJSON,
			&tagsJSON,
			&scraperName,
		); err != nil {
			return nil, fmt.Errorf("scan content row: %w", err)
		}
		item.Author = pointerFromText(author)
		item.ScraperName = pointerFromText(scraperName)
		if err := json.Unmarshal([]byte(keywordsJSON), &item.Keywords); err != nil {
			return nil, fmt.Errorf("decode keywords for %s: %w", item.ContentID, err)
		}
		if item.Keywords == nil {
			item.Keywords = []string{}
		}
		if err := json.Unmarshal([]byte(tagsJSON), &item.Tags); err != nil {
			return nil, fmt.Errorf("decode tags for %s: %w", item.ContentID, err)
		}
		if item.Tags == nil {
			item.Tags = []string{}
		}
		contents = append(contents, item)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate content rows: %w", err)
	}
	return contents, nil
}

func uniqueContents(contents []content.Content) []content.Content {
	seen := make(map[string]struct{}, len(contents))
	unique := make([]content.Content, 0, len(contents))
	for _, item := range contents {
		if _, exists := seen[item.ContentID]; exists {
			continue
		}
		seen[item.ContentID] = struct{}{}
		unique = append(unique, item)
	}
	return unique
}

func deduplicateIDs(contentIDs []string) []string {
	seen := make(map[string]struct{}, len(contentIDs))
	unique := make([]string, 0, len(contentIDs))
	for _, contentID := range contentIDs {
		contentID = strings.TrimSpace(contentID)
		if contentID == "" {
			continue
		}
		if _, exists := seen[contentID]; exists {
			continue
		}
		seen[contentID] = struct{}{}
		unique = append(unique, contentID)
	}
	return unique
}

func pointerFromText(value pgtype.Text) *string {
	if !value.Valid {
		return nil
	}
	text := value.String
	return &text
}
