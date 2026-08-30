package storage

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/config"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgtype"
	"github.com/jackc/pgx/v5/pgxpool"
)

const (
	migrationLockKey int64 = 739102001
	// contentTargetLockKey coordinates content stores (shared) with target
	// reconciliation (exclusive) and is intentionally distinct from the migration lock.
	contentTargetLockKey int64 = 739102002
	defaultChunkSize           = 512
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
    published_at TIMESTAMPTZ,
    author TEXT,
    keywords_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    tags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    scraper_id TEXT,
    scraper_name VARCHAR(255),
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_contents_keywords_array
        CHECK (
            jsonb_typeof(keywords_json) = 'array'
            AND NOT jsonb_path_exists(
                keywords_json,
                '$[*] ? (@.type() != "string")'
            )
        ),
    CONSTRAINT ck_contents_tags_array
        CHECK (
            jsonb_typeof(tags_json) = 'array'
            AND NOT jsonb_path_exists(
                tags_json,
                '$[*] ? (@.type() != "string")'
            )
        ),
    CONSTRAINT ck_contents_scraper_identity
        CHECK (
            (scraper_id IS NULL AND scraper_name IS NULL)
            OR (
                scraper_id IS NOT NULL
                AND scraper_id <> ''
                AND scraper_name IS NOT NULL
                AND scraper_name <> ''
            )
        )
)`
	createContentSourcesSQL = `
CREATE TABLE IF NOT EXISTS content_sources (
    content_id TEXT NOT NULL REFERENCES contents(content_id) ON DELETE CASCADE,
    scraper_id TEXT NOT NULL,
    scraper_name VARCHAR(255) NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (content_id, scraper_id),
    CONSTRAINT ck_content_sources_identity
        CHECK (scraper_id <> '' AND scraper_name <> ''),
    CONSTRAINT ck_content_sources_seen_order
        CHECK (last_seen_at >= first_seen_at)
)`
	createExporterTablesSQL = `
CREATE TABLE IF NOT EXISTS export_targets (
    target_id VARCHAR(128) PRIMARY KEY,
    kind VARCHAR(128) NOT NULL,
    destination_fingerprint VARCHAR(80) NOT NULL,
    enabled BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_export_targets_destination
        UNIQUE (kind, destination_fingerprint),
    CONSTRAINT ck_export_targets_identity
        CHECK (
            target_id <> ''
            AND kind <> ''
            AND destination_fingerprint <> ''
        )
);
CREATE TABLE IF NOT EXISTS content_exports (
    content_id TEXT NOT NULL REFERENCES contents(content_id) ON DELETE CASCADE,
    target_id VARCHAR(128) NOT NULL REFERENCES export_targets(target_id) ON DELETE CASCADE,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    claimed_by VARCHAR(128),
    claimed_at TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (content_id, target_id),
    CONSTRAINT ck_content_exports_status
        CHECK (status IN ('pending', 'processing', 'retry', 'synced', 'failed')),
    CONSTRAINT ck_content_exports_attempts
        CHECK (attempts >= 0),
    CONSTRAINT ck_content_exports_claim
        CHECK (
            (
                status = 'processing'
                AND claimed_by IS NOT NULL
                AND claimed_at IS NOT NULL
                AND lease_expires_at IS NOT NULL
            )
            OR
            (
                status <> 'processing'
                AND claimed_by IS NULL
                AND claimed_at IS NULL
                AND lease_expires_at IS NULL
            )
        )
)`
	createContentIndexesSQL = `
CREATE INDEX IF NOT EXISTS ix_contents_collected
    ON contents (collected_at DESC, content_id DESC);
CREATE INDEX IF NOT EXISTS ix_contents_tags
    ON contents USING GIN (tags_json);
CREATE INDEX IF NOT EXISTS ix_content_sources_scraper
    ON content_sources (scraper_id, content_id);
CREATE INDEX IF NOT EXISTS ix_content_sources_scraper_name
    ON content_sources (scraper_name, content_id)`
	createExporterIndexesSQL = `
CREATE INDEX IF NOT EXISTS ix_content_exports_due
    ON content_exports (target_id, next_attempt_at, content_id)
    WHERE status IN ('pending', 'retry');
CREATE INDEX IF NOT EXISTS ix_content_exports_lease
    ON content_exports (target_id, lease_expires_at, content_id)
    WHERE status = 'processing'`
	createV2ExporterTablesSQL = `
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
	migrateV2ToV3SQL = `
DROP INDEX IF EXISTS ix_content_exports_due;
DROP INDEX IF EXISTS ix_content_exports_claim;
DROP INDEX IF EXISTS ix_content_exports_lease;

ALTER TABLE contents
    RENAME COLUMN created_at TO collected_at;
ALTER TABLE contents
    ADD COLUMN published_at TIMESTAMPTZ,
    ADD COLUMN scraper_id TEXT;
ALTER TABLE contents
    ALTER COLUMN keywords_json DROP DEFAULT,
    ALTER COLUMN tags_json DROP DEFAULT;
ALTER TABLE contents
    ALTER COLUMN keywords_json TYPE JSONB USING keywords_json::jsonb,
    ALTER COLUMN keywords_json SET DEFAULT '[]'::jsonb,
    ALTER COLUMN tags_json TYPE JSONB USING tags_json::jsonb,
    ALTER COLUMN tags_json SET DEFAULT '[]'::jsonb;
ALTER TABLE contents
    ADD CONSTRAINT ck_contents_keywords_array
        CHECK (
            jsonb_typeof(keywords_json) = 'array'
            AND NOT jsonb_path_exists(
                keywords_json,
                '$[*] ? (@.type() != "string")'
            )
        ),
    ADD CONSTRAINT ck_contents_tags_array
        CHECK (
            jsonb_typeof(tags_json) = 'array'
            AND NOT jsonb_path_exists(
                tags_json,
                '$[*] ? (@.type() != "string")'
            )
        );
UPDATE contents
SET scraper_id = 'legacy:' || md5(scraper_name)
WHERE scraper_name IS NOT NULL
  AND scraper_id IS NULL;
ALTER TABLE contents
    ADD CONSTRAINT ck_contents_scraper_identity
        CHECK (
            (scraper_id IS NULL AND scraper_name IS NULL)
            OR (
                scraper_id IS NOT NULL
                AND scraper_id <> ''
                AND scraper_name IS NOT NULL
                AND scraper_name <> ''
            )
        );
ALTER TABLE contents
    DROP COLUMN updated_at;

ALTER TABLE export_targets
    RENAME COLUMN exporter_id TO target_id;
ALTER TABLE content_exports
    RENAME COLUMN exporter_id TO target_id;
ALTER TABLE export_targets
    ADD COLUMN kind VARCHAR(128),
    ADD COLUMN destination_fingerprint VARCHAR(80);
UPDATE export_targets
SET kind = CASE WHEN target_id = 'notion' THEN 'notion' ELSE target_id END,
    destination_fingerprint = 'legacy:' || md5(target_id);
ALTER TABLE export_targets
    ALTER COLUMN kind SET NOT NULL,
    ALTER COLUMN destination_fingerprint SET NOT NULL;
ALTER TABLE export_targets
    ADD CONSTRAINT uq_export_targets_destination
        UNIQUE (kind, destination_fingerprint),
    ADD CONSTRAINT ck_export_targets_identity
        CHECK (
            target_id <> ''
            AND kind <> ''
            AND destination_fingerprint <> ''
        );

CREATE TABLE content_sources (
    content_id TEXT NOT NULL REFERENCES contents(content_id) ON DELETE CASCADE,
    scraper_id TEXT NOT NULL,
    scraper_name VARCHAR(255) NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (content_id, scraper_id),
    CONSTRAINT ck_content_sources_identity
        CHECK (scraper_id <> '' AND scraper_name <> ''),
    CONSTRAINT ck_content_sources_seen_order
        CHECK (last_seen_at >= first_seen_at)
);
INSERT INTO content_sources (
    content_id, scraper_id, scraper_name, first_seen_at, last_seen_at
)
SELECT content_id, scraper_id, scraper_name, collected_at, collected_at
FROM contents
WHERE scraper_id IS NOT NULL
  AND scraper_name IS NOT NULL;

ALTER TABLE content_exports
    ADD CONSTRAINT ck_content_exports_status
        CHECK (status IN ('pending', 'processing', 'retry', 'synced', 'failed')),
    ADD CONSTRAINT ck_content_exports_attempts
        CHECK (attempts >= 0),
    ADD CONSTRAINT ck_content_exports_claim
        CHECK (
            (
                status = 'processing'
                AND claimed_by IS NOT NULL
                AND claimed_at IS NOT NULL
                AND lease_expires_at IS NOT NULL
            )
            OR
            (
                status <> 'processing'
                AND claimed_by IS NULL
                AND claimed_at IS NULL
                AND lease_expires_at IS NULL
            )
        );
`
)

type dbPool interface {
	Begin(context.Context) (pgx.Tx, error)
	Ping(context.Context) error
	Close()
	Exec(context.Context, string, ...any) (pgconn.CommandTag, error)
	Query(context.Context, string, ...any) (pgx.Rows, error)
	QueryRow(context.Context, string, ...any) pgx.Row
}

// PostgresStore persists canonical content, provenance, and export state.
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
	recordVersion := func(version int) error {
		if _, err := tx.Exec(ctx, `
INSERT INTO schema_migrations (version, applied_at)
VALUES ($1, NOW())
ON CONFLICT (version) DO NOTHING
`, version); err != nil {
			return fmt.Errorf("record schema version %d: %w", version, err)
		}
		return nil
	}
	if currentVersion == 0 {
		for _, statement := range []string{
			createContentsSQL,
			createContentSourcesSQL,
			createExporterTablesSQL,
			createContentIndexesSQL,
			createExporterIndexesSQL,
		} {
			if _, err := tx.Exec(ctx, statement); err != nil {
				return fmt.Errorf("create schema version %d: %w", SchemaVersion, err)
			}
		}
		if err := recordVersion(SchemaVersion); err != nil {
			return err
		}
		currentVersion = SchemaVersion
	}
	if currentVersion == 1 {
		for _, statement := range []string{createV2ExporterTablesSQL, migrateV1ToV2SQL} {
			if _, err := tx.Exec(ctx, statement); err != nil {
				return fmt.Errorf("migrate schema version 1 to 2: %w", err)
			}
		}
		if err := recordVersion(2); err != nil {
			return err
		}
		currentVersion = 2
	}
	if currentVersion == 2 {
		if err := normalizeLegacyStringArrays(ctx, tx); err != nil {
			return fmt.Errorf("migrate schema version 2 to 3: %w", err)
		}
		if _, err := tx.Exec(ctx, migrateV2ToV3SQL); err != nil {
			return fmt.Errorf("migrate schema version 2 to 3: %w", err)
		}
		if err := backfillPublishedAt(ctx, tx); err != nil {
			return fmt.Errorf("migrate schema version 2 to 3: %w", err)
		}
		for _, statement := range []string{createContentIndexesSQL, createExporterIndexesSQL} {
			if _, err := tx.Exec(ctx, statement); err != nil {
				return fmt.Errorf("migrate schema version 2 to 3: %w", err)
			}
		}
		if err := recordVersion(3); err != nil {
			return err
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

type publishedAtMigration struct {
	contentID   string
	publishedAt time.Time
}

type legacyStringArrayMigration struct {
	contentID   string
	keywordsRaw string
	tagsRaw     string
}

func normalizeLegacyStringArrays(ctx context.Context, tx pgx.Tx) error {
	var (
		cursor    string
		hasCursor bool
	)
	for {
		query := `
SELECT content_id, keywords_json, tags_json
FROM contents
ORDER BY content_id
LIMIT 512
`
		args := []any{}
		if hasCursor {
			query = `
SELECT content_id, keywords_json, tags_json
FROM contents
WHERE content_id > $1
ORDER BY content_id
LIMIT 512
`
			args = []any{cursor}
		}
		rows, err := tx.Query(ctx, query, args...)
		if err != nil {
			return fmt.Errorf("read legacy string arrays: %w", err)
		}
		batch := make([]legacyStringArrayMigration, 0, 512)
		for rows.Next() {
			var item legacyStringArrayMigration
			if err := rows.Scan(&item.contentID, &item.keywordsRaw, &item.tagsRaw); err != nil {
				rows.Close()
				return fmt.Errorf("scan legacy string arrays: %w", err)
			}
			batch = append(batch, item)
			cursor = item.contentID
			hasCursor = true
		}
		if err := rows.Err(); err != nil {
			rows.Close()
			return fmt.Errorf("iterate legacy string arrays: %w", err)
		}
		rows.Close()
		if len(batch) == 0 {
			return nil
		}
		for _, item := range batch {
			keywordsJSON, err := normalizeLegacyStringArrayJSON(
				item.keywordsRaw,
				"keywords_json",
				item.contentID,
			)
			if err != nil {
				return err
			}
			tagsJSON, err := normalizeLegacyStringArrayJSON(
				item.tagsRaw,
				"tags_json",
				item.contentID,
			)
			if err != nil {
				return err
			}
			if keywordsJSON == item.keywordsRaw && tagsJSON == item.tagsRaw {
				continue
			}
			if _, err := tx.Exec(ctx, `
UPDATE contents
SET keywords_json = $2,
    tags_json = $3
WHERE content_id = $1
`, item.contentID, keywordsJSON, tagsJSON); err != nil {
				return fmt.Errorf(
					"normalize legacy string arrays for content %q: %w",
					item.contentID,
					err,
				)
			}
		}
	}
}

func normalizeLegacyStringArrayJSON(raw, field, contentID string) (string, error) {
	var values []string
	if err := json.Unmarshal([]byte(raw), &values); err != nil {
		return "", fmt.Errorf(
			"decode legacy %s for content %q: %w",
			field,
			contentID,
			err,
		)
	}
	if values == nil {
		values = []string{}
	}
	normalized, err := marshalStringArrayJSON(values)
	if err != nil {
		return "", fmt.Errorf(
			"encode legacy %s for content %q: %w",
			field,
			contentID,
			err,
		)
	}
	return normalized, nil
}

func backfillPublishedAt(ctx context.Context, tx pgx.Tx) error {
	const cursorName = "octopus_published_v2"
	if _, err := tx.Exec(ctx, `
DECLARE octopus_published_v2 NO SCROLL CURSOR FOR
SELECT content_id, published
FROM contents
WHERE published <> '' AND published_at IS NULL
ORDER BY content_id
`); err != nil {
		return fmt.Errorf("declare publication time migration cursor: %w", err)
	}
	for {
		rows, err := tx.Query(ctx, `
FETCH FORWARD 512 FROM octopus_published_v2
`)
		if err != nil {
			return fmt.Errorf("fetch publication times for migration: %w", err)
		}
		fetched := 0
		updates := make([]publishedAtMigration, 0, defaultChunkSize)
		for rows.Next() {
			var contentID, published string
			if err := rows.Scan(&contentID, &published); err != nil {
				rows.Close()
				return fmt.Errorf("scan publication time for migration: %w", err)
			}
			fetched++
			if parsed, ok := content.ParsePublishedTime(published); ok {
				updates = append(updates, publishedAtMigration{
					contentID:   contentID,
					publishedAt: parsed,
				})
			}
		}
		if err := rows.Err(); err != nil {
			rows.Close()
			return fmt.Errorf("iterate publication times for migration: %w", err)
		}
		rows.Close()
		if len(updates) > 0 {
			query, args := buildPublishedAtBackfillQuery(updates)
			if _, err := tx.Exec(ctx, query, args...); err != nil {
				return fmt.Errorf("backfill publication times: %w", err)
			}
		}
		if fetched < defaultChunkSize {
			break
		}
	}
	if _, err := tx.Exec(ctx, "CLOSE "+cursorName); err != nil {
		return fmt.Errorf("close publication time migration cursor: %w", err)
	}
	return nil
}

func buildPublishedAtBackfillQuery(
	updates []publishedAtMigration,
) (string, []any) {
	var values strings.Builder
	args := make([]any, 0, len(updates)*2)
	for index, update := range updates {
		if index > 0 {
			values.WriteByte(',')
		}
		placeholder := index*2 + 1
		fmt.Fprintf(
			&values,
			"($%d::text,$%d::timestamptz)",
			placeholder,
			placeholder+1,
		)
		args = append(args, update.contentID, update.publishedAt)
	}
	return `
UPDATE contents AS content
SET published_at = migrated.published_at
FROM (VALUES ` + values.String() + `) AS migrated(content_id, published_at)
WHERE content.content_id = migrated.content_id
`, args
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

func (s *PostgresStore) StoreContents(
	ctx context.Context,
	contents []content.Content,
	sources []ContentSource,
) (StoreStats, error) {
	stats := StoreStats{Requested: len(contents)}
	unique := uniqueContents(contents)
	uniqueSources, err := normalizeContentSources(sources)
	if err != nil {
		return stats, err
	}
	stats.SourcesObserved = len(uniqueSources)
	if len(unique) == 0 && len(uniqueSources) == 0 {
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
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock_shared($1)`, contentTargetLockKey); err != nil {
		return stats, fmt.Errorf("acquire content/target coordination lock: %w", err)
	}
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
	for start := 0; start < len(uniqueSources); start += chunkSize {
		end := min(start+chunkSize, len(uniqueSources))
		query, args := buildUpsertContentSourcesQuery(uniqueSources[start:end])
		if _, err := tx.Exec(ctx, query, args...); err != nil {
			return stats, fmt.Errorf("upsert content sources: %w", err)
		}
	}
	if len(uniqueSources) > 0 {
		contentIDs := make([]string, 0, len(uniqueSources))
		seenContentIDs := make(map[string]struct{}, len(uniqueSources))
		for _, source := range uniqueSources {
			if _, exists := seenContentIDs[source.ContentID]; exists {
				continue
			}
			seenContentIDs[source.ContentID] = struct{}{}
			contentIDs = append(contentIDs, source.ContentID)
		}
		if _, err := tx.Exec(ctx, `
UPDATE contents AS content
SET scraper_id = latest.scraper_id,
    scraper_name = latest.scraper_name
FROM (
    SELECT DISTINCT ON (source.content_id)
           source.content_id, source.scraper_id, source.scraper_name
    FROM content_sources AS source
    JOIN contents AS current
      ON current.content_id = source.content_id
    WHERE source.content_id = ANY($1)
      AND (
          current.scraper_id IS NULL
          OR current.scraper_id = source.scraper_id
          OR (
              current.scraper_id LIKE 'legacy:%'
              AND current.scraper_name = source.scraper_name
          )
      )
    ORDER BY source.content_id,
             CASE WHEN current.scraper_id = source.scraper_id THEN 0 ELSE 1 END,
             source.last_seen_at DESC,
             source.scraper_id
) AS latest
WHERE content.content_id = latest.content_id
`, contentIDs); err != nil {
			return stats, fmt.Errorf("update primary content sources: %w", err)
		}
	}
	if len(unique) > 0 {
		contentIDs := make([]string, 0, len(unique))
		for _, item := range unique {
			contentIDs = append(contentIDs, item.ContentID)
		}
		if _, err := tx.Exec(ctx, `
INSERT INTO content_exports (content_id, target_id, status, attempts, next_attempt_at)
SELECT c.content_id, t.target_id, $1, 0, NOW()
FROM contents c
CROSS JOIN export_targets t
WHERE c.content_id = ANY($2) AND t.enabled
ON CONFLICT (content_id, target_id) DO NOTHING
`, SyncPending, contentIDs); err != nil {
			return stats, fmt.Errorf("create content export states: %w", err)
		}
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
			"sources_observed", stats.SourcesObserved,
		)
	}
	return stats, nil
}

func (s *PostgresStore) ReconcileTargets(ctx context.Context, targets []ExportTarget) error {
	targets, err := normalizeExportTargets(targets)
	if err != nil {
		return err
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("begin export target reconciliation: %w", err)
	}
	defer tx.Rollback(ctx)
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock($1)`, contentTargetLockKey); err != nil {
		return fmt.Errorf("acquire content/target coordination lock: %w", err)
	}
	targetIDs := make([]string, 0, len(targets))
	for _, target := range targets {
		targetIDs = append(targetIDs, target.TargetID)
		needsBackfill := true
		var (
			existingKind        string
			existingFingerprint string
			existingEnabled     bool
		)
		err := tx.QueryRow(ctx, `
SELECT kind, destination_fingerprint, enabled
FROM export_targets
WHERE target_id = $1
`, target.TargetID).Scan(
			&existingKind,
			&existingFingerprint,
			&existingEnabled,
		)
		if err == nil {
			if existingKind != target.Kind ||
				existingFingerprint != target.DestinationFingerprint {
				return fmt.Errorf(
					"export target %q conflicts with its existing destination identity",
					target.TargetID,
				)
			}
			needsBackfill = !existingEnabled
		} else if !errors.Is(err, pgx.ErrNoRows) {
			return fmt.Errorf("read export target %q: %w", target.TargetID, err)
		}
		commandTag, err := tx.Exec(ctx, `
INSERT INTO export_targets (
    target_id, kind, destination_fingerprint, enabled
)
VALUES ($1, $2, $3, TRUE)
ON CONFLICT (target_id) DO UPDATE
SET enabled = TRUE,
    updated_at = NOW()
WHERE export_targets.kind = EXCLUDED.kind
  AND export_targets.destination_fingerprint = EXCLUDED.destination_fingerprint
`, target.TargetID, target.Kind, target.DestinationFingerprint)
		if err != nil {
			return fmt.Errorf("register export target %q: %w", target.TargetID, err)
		}
		if commandTag.RowsAffected() != 1 {
			return fmt.Errorf(
				"export target %q conflicts with its existing destination identity",
				target.TargetID,
			)
		}
		if needsBackfill {
			if _, err := tx.Exec(ctx, `
INSERT INTO content_exports (content_id, target_id, status, attempts, next_attempt_at)
SELECT content_id, $1, $2, 0, NOW()
FROM contents
ON CONFLICT (content_id, target_id) DO NOTHING
`, target.TargetID, SyncPending); err != nil {
				return fmt.Errorf("backfill export target %q: %w", target.TargetID, err)
			}
		}
	}
	if _, err := tx.Exec(ctx, `
UPDATE export_targets
SET enabled = FALSE, updated_at = NOW()
WHERE enabled
  AND (
      cardinality($1::text[]) = 0
      OR NOT (target_id = ANY($1::text[]))
  )
`, targetIDs); err != nil {
		return fmt.Errorf("disable stale export targets: %w", err)
	}
	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("commit export target reconciliation: %w", err)
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
			CollectedAt: last.CollectedAt,
			ContentID:   last.ContentID,
		},
	}, nil
}

func (s *PostgresStore) GetContent(ctx context.Context, contentID string) (ContentRecord, bool, error) {
	var (
		record      ContentRecord
		publishedAt pgtype.Timestamptz
		author      pgtype.Text
		keywordsRaw string
		tagsRaw     string
		scraperID   pgtype.Text
		scraperName pgtype.Text
	)
	err := s.pool.QueryRow(ctx, `
SELECT content_id, title, link, summary, content, published, published_at,
       author, keywords_json, tags_json, scraper_id, scraper_name, collected_at
FROM contents
WHERE content_id = $1
`, contentID).Scan(
		&record.ContentID,
		&record.Title,
		&record.Link,
		&record.Summary,
		&record.Content,
		&record.Published,
		&publishedAt,
		&author,
		&keywordsRaw,
		&tagsRaw,
		&scraperID,
		&scraperName,
		&record.CollectedAt,
	)
	if err != nil {
		if err == pgx.ErrNoRows {
			return ContentRecord{}, false, nil
		}
		return ContentRecord{}, false, fmt.Errorf("get content: %w", err)
	}
	record.PublishedAt = pointerFromTimestamptz(publishedAt)
	record.Author = pointerFromText(author)
	record.ScraperID = pointerFromText(scraperID)
	record.ScraperName = pointerFromText(scraperName)
	if err := decodeStringSlice(keywordsRaw, &record.Keywords, "keywords", contentID); err != nil {
		return ContentRecord{}, false, err
	}
	if err := decodeStringSlice(tagsRaw, &record.Tags, "tags", contentID); err != nil {
		return ContentRecord{}, false, err
	}
	return record, true, nil
}

func (s *PostgresStore) Claim(ctx context.Context, targetID, workerID string, batchSize int, lease time.Duration, maxAttempts int) ([]content.Content, error) {
	rows, err := s.pool.Query(ctx, `
WITH due AS (
    SELECT export.content_id, export.target_id
    FROM content_exports AS export
    JOIN export_targets AS target
      ON target.target_id = export.target_id
     AND target.enabled
    WHERE (
        export.target_id = $1
        AND export.status IN ('pending', 'retry')
        AND export.attempts < $2
        AND export.next_attempt_at <= NOW()
    ) OR (
        export.target_id = $1
        AND export.status = 'processing'
        AND export.lease_expires_at <= NOW()
    )
    ORDER BY export.next_attempt_at, export.content_id
    LIMIT $3
    FOR UPDATE OF export SKIP LOCKED
),
claimed AS (
    UPDATE content_exports AS e
    SET status = 'processing',
        claimed_by = $4,
        claimed_at = NOW(),
        lease_expires_at = NOW() + ($5 * INTERVAL '1 second'),
        updated_at = NOW()
    FROM due
    WHERE e.content_id = due.content_id
      AND e.target_id = due.target_id
    RETURNING e.content_id
)
SELECT c.content_id, c.title, c.link, c.summary, c.content, c.published,
       c.author, c.keywords_json, c.tags_json, c.scraper_id, c.scraper_name
FROM contents c
JOIN claimed ON claimed.content_id = c.content_id
`, targetID, maxAttempts, batchSize, workerID, int(lease.Seconds()))
	if err != nil {
		return nil, fmt.Errorf("claim contents for export target %q: %w", targetID, err)
	}
	defer rows.Close()
	claimed, err := scanContents(rows)
	if err != nil {
		return nil, err
	}
	return claimed, nil
}

func (s *PostgresStore) Renew(ctx context.Context, targetID, contentID, workerID string, lease time.Duration) (bool, error) {
	commandTag, err := s.pool.Exec(ctx, `
UPDATE content_exports AS export
SET lease_expires_at = NOW() + ($1 * INTERVAL '1 second'),
    updated_at = NOW()
FROM export_targets AS target
WHERE target.target_id = export.target_id
  AND target.enabled
  AND export.target_id = $2
  AND export.content_id = $3
  AND export.claimed_by = $4
  AND export.status = $5
`, int(lease.Seconds()), targetID, contentID, workerID, SyncProcessing)
	if err != nil {
		return false, fmt.Errorf("renew content claim: %w", err)
	}
	return commandTag.RowsAffected() == 1, nil
}

func (s *PostgresStore) Complete(ctx context.Context, targetID, contentID, workerID string) (bool, error) {
	commandTag, err := s.pool.Exec(ctx, `
UPDATE content_exports
SET status = $1,
    completed_at = NOW(),
    error = NULL,
    claimed_by = NULL,
    claimed_at = NULL,
    lease_expires_at = NULL,
    updated_at = NOW()
WHERE target_id = $2
  AND content_id = $3
  AND claimed_by = $4
  AND status = $5
`, SyncSynced, targetID, contentID, workerID, SyncProcessing)
	if err != nil {
		return false, fmt.Errorf("mark content synced: %w", err)
	}
	return commandTag.RowsAffected() == 1, nil
}

func (s *PostgresStore) Fail(ctx context.Context, targetID, contentID, workerID, errorMessage string, maxAttempts int) (bool, error) {
	var attemptsBefore int
	if err := s.pool.QueryRow(ctx, `
SELECT attempts
FROM content_exports
WHERE target_id = $1
  AND content_id = $2
  AND claimed_by = $3
  AND status = $4
`, targetID, contentID, workerID, SyncProcessing).Scan(&attemptsBefore); err != nil {
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
WHERE target_id = $5
  AND content_id = $6
  AND claimed_by = $7
  AND status = $8
  AND attempts = $9
`, attempts, status, errorMessage, int(nextRetryDelay(attempts).Seconds()), targetID, contentID, workerID, SyncProcessing, attemptsBefore)
	if err != nil {
		return false, fmt.Errorf("mark sync failed: %w", err)
	}
	return commandTag.RowsAffected() == 1, nil
}

func (s *PostgresStore) SyncCounts(ctx context.Context) (map[string]int64, error) {
	rows, err := s.pool.Query(ctx, `
SELECT export.status, COUNT(export.content_id)
FROM content_exports AS export
JOIN export_targets AS target
  ON target.target_id = export.target_id
WHERE target.enabled
GROUP BY export.status
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
SELECT content_id, title, link, summary, published, published_at, author,
       keywords_json, tags_json, scraper_id, scraper_name, collected_at
FROM contents`)
	where := make([]string, 0, 6)
	args := make([]any, 0, 8)
	addArg := func(value any) string {
		args = append(args, value)
		return fmt.Sprintf("$%d", len(args))
	}
	if opts.ScraperID != "" || opts.ScraperName != "" {
		sourceWhere := []string{"source.content_id = contents.content_id"}
		if opts.ScraperID != "" {
			sourceWhere = append(sourceWhere, "source.scraper_id = "+addArg(opts.ScraperID))
		}
		if opts.ScraperName != "" {
			sourceWhere = append(sourceWhere, "source.scraper_name = "+addArg(opts.ScraperName))
		}
		where = append(where, `EXISTS (
    SELECT 1
    FROM content_sources AS source
    WHERE `+strings.Join(sourceWhere, `
      AND `)+`
)`)
	}
	if opts.CollectedAfter != nil {
		where = append(where, "collected_at >= "+addArg(*opts.CollectedAfter))
	}
	if opts.CollectedBefore != nil {
		where = append(where, "collected_at <= "+addArg(*opts.CollectedBefore))
	}
	if opts.Cursor != nil {
		createdAtPlaceholder := addArg(opts.Cursor.CollectedAt)
		contentIDPlaceholder := addArg(opts.Cursor.ContentID)
		where = append(where, "(collected_at, content_id) < ("+createdAtPlaceholder+", "+contentIDPlaceholder+")")
	}
	if len(opts.Tags) > 0 {
		where = append(where, "tags_json ?| "+addArg(opts.Tags)+"::text[]")
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
ORDER BY collected_at DESC, content_id DESC
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
			publishedAt pgtype.Timestamptz
			author      pgtype.Text
			keywordsRaw string
			tagsRaw     string
			scraperID   pgtype.Text
			scraperName pgtype.Text
		)
		if err := rows.Scan(
			&item.ContentID,
			&item.Title,
			&item.Link,
			&item.Summary,
			&item.Published,
			&publishedAt,
			&author,
			&keywordsRaw,
			&tagsRaw,
			&scraperID,
			&scraperName,
			&item.CollectedAt,
		); err != nil {
			return nil, fmt.Errorf("scan content metadata row: %w", err)
		}
		item.PublishedAt = pointerFromTimestamptz(publishedAt)
		item.Author = pointerFromText(author)
		item.ScraperID = pointerFromText(scraperID)
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
    content_id, title, link, summary, content, published, published_at, author,
    keywords_json, tags_json, scraper_id, scraper_name, collected_at
) VALUES `)
	args := make([]any, 0, len(contents)*12)
	placeholder := 1
	for index, item := range contents {
		if index > 0 {
			builder.WriteString(",")
		}
		keywordsJSON, err := marshalStringArrayJSON(item.Keywords)
		if err != nil {
			return "", nil, fmt.Errorf("marshal keywords for %s: %w", item.ContentID, err)
		}
		tagsJSON, err := marshalStringArrayJSON(item.Tags)
		if err != nil {
			return "", nil, fmt.Errorf("marshal tags for %s: %w", item.ContentID, err)
		}
		var publishedAt any
		if parsed, ok := content.ParsePublishedTime(item.Published); ok {
			publishedAt = parsed
		}
		builder.WriteString(fmt.Sprintf(`
    ($%d,$%d,$%d,$%d,$%d,$%d,$%d,$%d,$%d,$%d,$%d,$%d,NOW())`,
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
			publishedAt,
			item.Author,
			keywordsJSON,
			tagsJSON,
			item.ScraperID,
			item.ScraperName,
		)
		placeholder += 12
	}
	builder.WriteString(`
ON CONFLICT (content_id) DO NOTHING`)
	return builder.String(), args, nil
}

func marshalStringArrayJSON(values []string) (string, error) {
	normalized := make([]string, len(values))
	for index, value := range values {
		normalized[index] = strings.ReplaceAll(value, "\x00", "\uFFFD")
	}
	encoded, err := json.Marshal(normalized)
	if err != nil {
		return "", err
	}
	return string(encoded), nil
}

func buildUpsertContentSourcesQuery(sources []ContentSource) (string, []any) {
	var values strings.Builder
	args := make([]any, 0, len(sources)*4)
	placeholder := 1
	for index, source := range sources {
		if index > 0 {
			values.WriteString(",")
		}
		fmt.Fprintf(
			&values,
			"($%d,$%d,$%d,$%d::timestamptz)",
			placeholder,
			placeholder+1,
			placeholder+2,
			placeholder+3,
		)
		args = append(
			args,
			source.ContentID,
			source.ScraperID,
			source.ScraperName,
			source.ObservedAt,
		)
		placeholder += 4
	}
	return `
WITH observed(content_id, scraper_id, scraper_name, observed_at) AS (
    VALUES ` + values.String() + `
),
removed AS (
    DELETE FROM content_sources AS source
    USING observed
    WHERE source.content_id = observed.content_id
      AND source.scraper_id LIKE 'legacy:%'
      AND source.scraper_id <> observed.scraper_id
      AND source.scraper_name = observed.scraper_name
    RETURNING source.content_id
)
INSERT INTO content_sources (
    content_id, scraper_id, scraper_name, first_seen_at, last_seen_at
)
SELECT content_id, scraper_id, scraper_name, observed_at, observed_at
FROM observed
ON CONFLICT (content_id, scraper_id) DO UPDATE
SET scraper_name = CASE
        WHEN EXCLUDED.last_seen_at >= content_sources.last_seen_at
        THEN EXCLUDED.scraper_name
        ELSE content_sources.scraper_name
    END,
    first_seen_at = LEAST(
        content_sources.first_seen_at,
        EXCLUDED.first_seen_at
    ),
    last_seen_at = GREATEST(
        content_sources.last_seen_at,
        EXCLUDED.last_seen_at
    )
`, args
}

func scanContents(rows pgx.Rows) ([]content.Content, error) {
	contents := make([]content.Content, 0)
	for rows.Next() {
		var (
			item         content.Content
			author       pgtype.Text
			keywordsJSON string
			tagsJSON     string
			scraperID    pgtype.Text
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
			&scraperID,
			&scraperName,
		); err != nil {
			return nil, fmt.Errorf("scan content row: %w", err)
		}
		item.Author = pointerFromText(author)
		item.ScraperID = pointerFromText(scraperID)
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

func normalizeContentSources(sources []ContentSource) ([]ContentSource, error) {
	normalized := make([]ContentSource, 0, len(sources))
	indexes := make(map[string]int, len(sources))
	fallbackObservedAt := time.Now().UTC()
	for _, source := range sources {
		source.ContentID = strings.TrimSpace(source.ContentID)
		source.ScraperID = strings.TrimSpace(source.ScraperID)
		source.ScraperName = strings.TrimSpace(source.ScraperName)
		if source.ContentID == "" || source.ScraperID == "" || source.ScraperName == "" {
			return nil, errors.New("content source requires content ID, scraper ID, and scraper name")
		}
		if utf8.RuneCountInString(source.ScraperName) > 255 {
			return nil, fmt.Errorf("content source scraper name exceeds 255 characters: %q", source.ScraperName)
		}
		if utf8.RuneCountInString(source.ScraperID) > config.MaxScraperIDLength {
			return nil, fmt.Errorf(
				"content source scraper ID exceeds %d characters: %q",
				config.MaxScraperIDLength,
				source.ScraperID,
			)
		}
		if source.ObservedAt.IsZero() {
			source.ObservedAt = fallbackObservedAt
		} else {
			source.ObservedAt = source.ObservedAt.UTC()
		}
		key := source.ContentID + "\x00" + source.ScraperID
		if index, exists := indexes[key]; exists {
			if source.ObservedAt.After(normalized[index].ObservedAt) ||
				source.ObservedAt.Equal(normalized[index].ObservedAt) {
				normalized[index] = source
			}
			continue
		}
		indexes[key] = len(normalized)
		normalized = append(normalized, source)
	}
	return normalized, nil
}

func normalizeExportTargets(targets []ExportTarget) ([]ExportTarget, error) {
	normalized := make([]ExportTarget, 0, len(targets))
	ids := make(map[string]struct{}, len(targets))
	destinations := make(map[string]struct{}, len(targets))
	for _, target := range targets {
		target.TargetID = strings.TrimSpace(target.TargetID)
		target.Kind = strings.TrimSpace(target.Kind)
		target.DestinationFingerprint = strings.TrimSpace(target.DestinationFingerprint)
		if target.TargetID == "" || target.Kind == "" || target.DestinationFingerprint == "" {
			return nil, errors.New("export target requires target ID, kind, and destination fingerprint")
		}
		if len(target.TargetID) > 128 || len(target.Kind) > 128 || len(target.DestinationFingerprint) > 80 {
			return nil, fmt.Errorf("export target %q exceeds database identity limits", target.TargetID)
		}
		if _, exists := ids[target.TargetID]; exists {
			return nil, fmt.Errorf("duplicate export target ID %q", target.TargetID)
		}
		destinationKey := target.Kind + "\x00" + target.DestinationFingerprint
		if _, exists := destinations[destinationKey]; exists {
			return nil, fmt.Errorf(
				"duplicate export destination for kind %q",
				target.Kind,
			)
		}
		ids[target.TargetID] = struct{}{}
		destinations[destinationKey] = struct{}{}
		normalized = append(normalized, target)
	}
	return normalized, nil
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

func pointerFromTimestamptz(value pgtype.Timestamptz) *time.Time {
	if !value.Valid {
		return nil
	}
	timestamp := value.Time
	return &timestamp
}
