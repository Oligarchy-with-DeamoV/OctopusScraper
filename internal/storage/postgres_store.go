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
    updated_at TIMESTAMPTZ NOT NULL
)`
	createExporterTablesSQL = `
CREATE TABLE IF NOT EXISTS export_targets (
    exporter_id VARCHAR(128) PRIMARY KEY,
    enabled BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS content_exports (
    content_id TEXT NOT NULL REFERENCES contents(content_id) ON DELETE CASCADE,
    exporter_id VARCHAR(128) NOT NULL REFERENCES export_targets(exporter_id) ON DELETE CASCADE,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    claimed_by VARCHAR(128),
    claimed_at TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (content_id, exporter_id)
)`
	createExporterIndexesSQL = `
CREATE INDEX IF NOT EXISTS ix_content_exports_due
    ON content_exports (exporter_id, status, next_attempt_at);
CREATE INDEX IF NOT EXISTS ix_content_exports_claim
    ON content_exports (exporter_id, claimed_by);
CREATE INDEX IF NOT EXISTS ix_content_exports_lease
    ON content_exports (exporter_id, lease_expires_at)`
	migrateV1ToV2SQL = `
INSERT INTO export_targets (exporter_id, enabled)
VALUES ('notion', TRUE)
ON CONFLICT (exporter_id) DO NOTHING;
INSERT INTO content_exports (
    content_id, exporter_id, status, attempts, error, next_attempt_at,
    completed_at, claimed_by, claimed_at, lease_expires_at, updated_at
)
SELECT content_id, 'notion', notion_sync_status, notion_sync_attempts,
       notion_sync_error, notion_next_attempt_at, notion_synced_at,
       notion_claimed_by, notion_claimed_at, notion_lease_expires_at, updated_at
FROM contents
ON CONFLICT (content_id, exporter_id) DO NOTHING;
DO $$
BEGIN
    IF (SELECT COUNT(*) FROM contents) <>
       (SELECT COUNT(*) FROM content_exports WHERE exporter_id = 'notion') THEN
        RAISE EXCEPTION 'notion export migration count mismatch';
    END IF;
END $$;
DROP INDEX IF EXISTS ix_contents_notion_sync_status;
DROP INDEX IF EXISTS ix_contents_notion_next_attempt_at;
DROP INDEX IF EXISTS ix_contents_notion_claimed_by;
DROP INDEX IF EXISTS ix_contents_notion_lease_expires_at;
ALTER TABLE contents
    DROP COLUMN notion_sync_status,
    DROP COLUMN notion_synced_at,
    DROP COLUMN notion_sync_attempts,
    DROP COLUMN notion_sync_error,
    DROP COLUMN notion_next_attempt_at,
    DROP COLUMN notion_claimed_by,
    DROP COLUMN notion_claimed_at,
    DROP COLUMN notion_lease_expires_at`
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
	if _, err := tx.Exec(ctx, createSchemaMigrationsSQL); err != nil {
		return fmt.Errorf("create schema migrations table: %w", err)
	}
	var currentVersion int
	if err := tx.QueryRow(ctx, `SELECT COALESCE(MAX(version), 0) FROM schema_migrations`).Scan(&currentVersion); err != nil {
		return fmt.Errorf("read schema version: %w", err)
	}
	if currentVersion > SchemaVersion {
		return fmt.Errorf("database schema version %d is newer than supported version %d", currentVersion, SchemaVersion)
	}
	if currentVersion == 0 {
		for _, statement := range []string{createContentsSQL, createExporterTablesSQL, createExporterIndexesSQL} {
			if _, err := tx.Exec(ctx, statement); err != nil {
				return fmt.Errorf("create schema version 2: %w", err)
			}
		}
	} else if currentVersion == 1 {
		for _, statement := range []string{createExporterTablesSQL, migrateV1ToV2SQL, createExporterIndexesSQL} {
			if _, err := tx.Exec(ctx, statement); err != nil {
				return fmt.Errorf("migrate schema version 1 to 2: %w", err)
			}
		}
	}
	if currentVersion < SchemaVersion {
		if _, err := tx.Exec(ctx, `
INSERT INTO schema_migrations (version, applied_at)
VALUES ($1, NOW())
ON CONFLICT (version) DO NOTHING
`, SchemaVersion); err != nil {
			return fmt.Errorf("record schema version: %w", err)
		}
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
	contentIDs := make([]string, 0, len(unique))
	for _, item := range unique {
		contentIDs = append(contentIDs, item.ContentID)
	}
	if _, err := tx.Exec(ctx, `
INSERT INTO content_exports (content_id, exporter_id, status, attempts, next_attempt_at)
SELECT c.content_id, t.exporter_id, $1, 0, NOW()
FROM contents c
CROSS JOIN export_targets t
WHERE c.content_id = ANY($2) AND t.enabled
ON CONFLICT (content_id, exporter_id) DO NOTHING
`, SyncPending, contentIDs); err != nil {
		return stats, fmt.Errorf("create content export states: %w", err)
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

func (s *PostgresStore) RegisterTarget(ctx context.Context, exporterID string, enabled bool) error {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("begin exporter registration: %w", err)
	}
	defer tx.Rollback(ctx)
	if _, err := tx.Exec(ctx, `
INSERT INTO export_targets (exporter_id, enabled)
VALUES ($1, $2)
ON CONFLICT (exporter_id) DO UPDATE
SET enabled = EXCLUDED.enabled, updated_at = NOW()
`, exporterID, enabled); err != nil {
		return fmt.Errorf("register exporter target %q: %w", exporterID, err)
	}
	if enabled {
		if _, err := tx.Exec(ctx, `
INSERT INTO content_exports (content_id, exporter_id, status, attempts, next_attempt_at)
SELECT content_id, $1, $2, 0, NOW()
FROM contents
ON CONFLICT (content_id, exporter_id) DO NOTHING
`, exporterID, SyncPending); err != nil {
			return fmt.Errorf("backfill exporter target %q: %w", exporterID, err)
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("commit exporter registration %q: %w", exporterID, err)
	}
	return nil
}

func (s *PostgresStore) ListContents(ctx context.Context, opts ContentListOptions) (ContentListPage, error) {
	query, args := buildListContentsQuery(opts)
	rows, err := s.pool.Query(ctx, query, args...)
	if err != nil {
		return ContentListPage{}, fmt.Errorf("list contents: %w", err)
	}
	defer rows.Close()
	items, err := scanContentMetadata(rows)
	if err != nil {
		return ContentListPage{}, err
	}
	pageLimit := opts.Limit
	if pageLimit <= 0 {
		pageLimit = 0
	}
	if len(items) <= pageLimit {
		return ContentListPage{Items: items}, nil
	}
	if pageLimit == 0 {
		return ContentListPage{}, nil
	}
	items = items[:pageLimit]
	last := items[len(items)-1]
	return ContentListPage{
		Items: items,
		NextCursor: &ContentListCursor{
			CreatedAt: last.CollectedAt,
			ContentID: last.ContentID,
		},
	}, nil
}

func (s *PostgresStore) GetContent(ctx context.Context, contentID string) (ContentRecord, bool, error) {
	var (
		record      ContentRecord
		author      pgtype.Text
		keywordsRaw string
		tagsRaw     string
		scraperName pgtype.Text
	)
	err := s.pool.QueryRow(ctx, `
SELECT content_id, title, link, summary, content, published, author,
       keywords_json, tags_json, scraper_name, created_at
FROM contents
WHERE content_id = $1
`, contentID).Scan(
		&record.ContentID,
		&record.Title,
		&record.Link,
		&record.Summary,
		&record.Content,
		&record.Published,
		&author,
		&keywordsRaw,
		&tagsRaw,
		&scraperName,
		&record.CollectedAt,
	)
	if err != nil {
		if err == pgx.ErrNoRows {
			return ContentRecord{}, false, nil
		}
		return ContentRecord{}, false, fmt.Errorf("get content: %w", err)
	}
	record.Author = pointerFromText(author)
	record.ScraperName = pointerFromText(scraperName)
	if err := decodeStringSlice(keywordsRaw, &record.Keywords, "keywords", contentID); err != nil {
		return ContentRecord{}, false, err
	}
	if err := decodeStringSlice(tagsRaw, &record.Tags, "tags", contentID); err != nil {
		return ContentRecord{}, false, err
	}
	return record, true, nil
}

func (s *PostgresStore) Claim(ctx context.Context, exporterID, workerID string, batchSize int, lease time.Duration, maxAttempts int) ([]content.Content, error) {
	rows, err := s.pool.Query(ctx, `
WITH due AS (
    SELECT content_id, exporter_id
    FROM content_exports
    WHERE (
        exporter_id = $1
        AND status IN ($2, $3)
        AND attempts < $4
        AND next_attempt_at <= NOW()
    ) OR (
        exporter_id = $1
        AND status = $5
        AND lease_expires_at <= NOW()
    )
    ORDER BY next_attempt_at, content_id
    LIMIT $6
    FOR UPDATE SKIP LOCKED
),
claimed AS (
    UPDATE content_exports AS e
    SET status = $5,
        claimed_by = $7,
        claimed_at = NOW(),
        lease_expires_at = NOW() + ($8 * INTERVAL '1 second'),
        updated_at = NOW()
    FROM due
    WHERE e.content_id = due.content_id
      AND e.exporter_id = due.exporter_id
    RETURNING e.content_id
)
SELECT c.content_id, c.title, c.link, c.summary, c.content, c.published,
       c.author, c.keywords_json, c.tags_json, c.scraper_name
FROM contents c
JOIN claimed ON claimed.content_id = c.content_id
`, exporterID, SyncPending, SyncRetry, maxAttempts, SyncProcessing, batchSize, workerID, int(lease.Seconds()))
	if err != nil {
		return nil, fmt.Errorf("claim contents for exporter %q: %w", exporterID, err)
	}
	defer rows.Close()
	claimed, err := scanContents(rows)
	if err != nil {
		return nil, err
	}
	return claimed, nil
}

func (s *PostgresStore) Renew(ctx context.Context, exporterID, contentID, workerID string, lease time.Duration) (bool, error) {
	commandTag, err := s.pool.Exec(ctx, `
UPDATE content_exports
SET lease_expires_at = NOW() + ($1 * INTERVAL '1 second'),
    updated_at = NOW()
WHERE exporter_id = $2
  AND content_id = $3
  AND claimed_by = $4
  AND status = $5
`, int(lease.Seconds()), exporterID, contentID, workerID, SyncProcessing)
	if err != nil {
		return false, fmt.Errorf("renew content claim: %w", err)
	}
	return commandTag.RowsAffected() == 1, nil
}

func (s *PostgresStore) Complete(ctx context.Context, exporterID, contentID, workerID string) (bool, error) {
	commandTag, err := s.pool.Exec(ctx, `
UPDATE content_exports
SET status = $1,
    completed_at = NOW(),
    error = NULL,
    claimed_by = NULL,
    claimed_at = NULL,
    lease_expires_at = NULL,
    updated_at = NOW()
WHERE exporter_id = $2
  AND content_id = $3
  AND claimed_by = $4
  AND status = $5
`, SyncSynced, exporterID, contentID, workerID, SyncProcessing)
	if err != nil {
		return false, fmt.Errorf("mark content synced: %w", err)
	}
	return commandTag.RowsAffected() == 1, nil
}

func (s *PostgresStore) Fail(ctx context.Context, exporterID, contentID, workerID, errorMessage string, maxAttempts int) (bool, error) {
	var attemptsBefore int
	if err := s.pool.QueryRow(ctx, `
SELECT attempts
FROM content_exports
WHERE exporter_id = $1
  AND content_id = $2
  AND claimed_by = $3
  AND status = $4
`, exporterID, contentID, workerID, SyncProcessing).Scan(&attemptsBefore); err != nil {
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
UPDATE content_exports
SET attempts = $1,
    status = $2,
    error = LEFT($3, 2000),
    next_attempt_at = NOW() + ($4 * INTERVAL '1 second'),
    claimed_by = NULL,
    claimed_at = NULL,
    lease_expires_at = NULL,
    updated_at = NOW()
WHERE exporter_id = $5
  AND content_id = $6
  AND claimed_by = $7
  AND status = $8
  AND attempts = $9
`, attempts, status, errorMessage, int(nextRetryDelay(attempts).Seconds()), exporterID, contentID, workerID, SyncProcessing, attemptsBefore)
	if err != nil {
		return false, fmt.Errorf("mark sync failed: %w", err)
	}
	return commandTag.RowsAffected() == 1, nil
}

func (s *PostgresStore) SyncCounts(ctx context.Context) (map[string]int64, error) {
	rows, err := s.pool.Query(ctx, `
SELECT status, COUNT(content_id)
FROM content_exports
GROUP BY status
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

func buildListContentsQuery(opts ContentListOptions) (string, []any) {
	var builder strings.Builder
	builder.WriteString(`
SELECT content_id, title, link, summary, published, author,
       keywords_json, tags_json, scraper_name, created_at
FROM contents`)
	where := make([]string, 0, 5)
	args := make([]any, 0, 7)
	addArg := func(value any) string {
		args = append(args, value)
		return fmt.Sprintf("$%d", len(args))
	}
	if opts.ScraperName != "" {
		where = append(where, "scraper_name = "+addArg(opts.ScraperName))
	}
	if opts.CollectedAfter != nil {
		where = append(where, "created_at >= "+addArg(*opts.CollectedAfter))
	}
	if opts.CollectedBefore != nil {
		where = append(where, "created_at <= "+addArg(*opts.CollectedBefore))
	}
	if opts.Cursor != nil {
		createdAtPlaceholder := addArg(opts.Cursor.CreatedAt)
		contentIDPlaceholder := addArg(opts.Cursor.ContentID)
		where = append(where, "(created_at, content_id) < ("+createdAtPlaceholder+", "+contentIDPlaceholder+")")
	}
	if len(opts.Tags) > 0 {
		where = append(where, `EXISTS (
    SELECT 1
    FROM jsonb_array_elements_text(tags_json::jsonb) AS tag(value)
    WHERE tag.value = ANY(`+addArg(opts.Tags)+`::text[])
)`)
	}
	if len(where) > 0 {
		builder.WriteString(`
WHERE `)
		builder.WriteString(strings.Join(where, `
  AND `))
	}
	limit := opts.Limit + 1
	if limit < 1 {
		limit = 1
	}
	builder.WriteString(`
ORDER BY created_at DESC, content_id DESC
LIMIT `)
	builder.WriteString(addArg(limit))
	return builder.String(), args
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

func scanContentMetadata(rows pgx.Rows) ([]ContentMetadata, error) {
	items := make([]ContentMetadata, 0)
	for rows.Next() {
		var (
			item        ContentMetadata
			author      pgtype.Text
			keywordsRaw string
			tagsRaw     string
			scraperName pgtype.Text
		)
		if err := rows.Scan(
			&item.ContentID,
			&item.Title,
			&item.Link,
			&item.Summary,
			&item.Published,
			&author,
			&keywordsRaw,
			&tagsRaw,
			&scraperName,
			&item.CollectedAt,
		); err != nil {
			return nil, fmt.Errorf("scan content metadata row: %w", err)
		}
		item.Author = pointerFromText(author)
		item.ScraperName = pointerFromText(scraperName)
		if err := decodeStringSlice(keywordsRaw, &item.Keywords, "keywords", item.ContentID); err != nil {
			return nil, err
		}
		if err := decodeStringSlice(tagsRaw, &item.Tags, "tags", item.ContentID); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate content metadata rows: %w", err)
	}
	return items, nil
}

func buildInsertContentsQuery(contents []content.Content) (string, []any, error) {
	var builder strings.Builder
	builder.WriteString(`
INSERT INTO contents (
    content_id, title, link, summary, content, published, author,
    keywords_json, tags_json, scraper_name, created_at, updated_at
) VALUES `)
	args := make([]any, 0, len(contents)*10)
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
    ($%d,$%d,$%d,$%d,$%d,$%d,$%d,$%d,$%d,$%d,NOW(),NOW())`,
			placeholder, placeholder+1, placeholder+2, placeholder+3, placeholder+4,
			placeholder+5, placeholder+6, placeholder+7, placeholder+8, placeholder+9,
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
		)
		placeholder += 10
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
		if err := decodeStringSlice(keywordsJSON, &item.Keywords, "keywords", item.ContentID); err != nil {
			return nil, err
		}
		if err := decodeStringSlice(tagsJSON, &item.Tags, "tags", item.ContentID); err != nil {
			return nil, err
		}
		contents = append(contents, item)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate content rows: %w", err)
	}
	return contents, nil
}

func decodeStringSlice(raw string, target *[]string, field, contentID string) error {
	if err := json.Unmarshal([]byte(raw), target); err != nil {
		return fmt.Errorf("decode %s for %s: %w", field, contentID, err)
	}
	if *target == nil {
		*target = []string{}
	}
	return nil
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
