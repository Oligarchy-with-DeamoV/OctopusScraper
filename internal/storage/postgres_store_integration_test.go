package storage

import (
	"context"
	"crypto/md5"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/url"
	"os"
	"runtime"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/config"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
)

func TestPostgresStoreIntegrationFreshSchemaV3(t *testing.T) {
	store := newPostgresIntegrationStore(t)
	ctx := context.Background()

	if err := store.Initialize(ctx); err != nil {
		t.Fatalf("Initialize fresh schema: %v", err)
	}
	if err := store.Initialize(ctx); err != nil {
		t.Fatalf("Initialize fresh schema twice: %v", err)
	}

	target := ExportTarget{
		TargetID:               "notion:test-destination",
		Kind:                   "notion",
		DestinationFingerprint: strings.Repeat("a", 64),
	}
	if err := store.ReconcileTargets(ctx, []ExportTarget{target}); err != nil {
		t.Fatalf("ReconcileTargets: %v", err)
	}
	if err := store.ReconcileTargets(ctx, []ExportTarget{target}); err != nil {
		t.Fatalf("ReconcileTargets unchanged target: %v", err)
	}

	item := content.Content{
		ContentID:   "content-1",
		Title:       "Title",
		Link:        "https://example.com/1",
		Summary:     "Summary",
		Content:     "Body",
		Published:   "Tue, 06 Apr 2025 13:50:59 +0800",
		Keywords:    []string{"database"},
		Tags:        []string{"go"},
		ScraperID:   stringPointer("feed-1"),
		ScraperName: stringPointer("Feed One"),
	}
	stats, err := store.StoreContents(ctx, []content.Content{item}, []ContentSource{{
		ContentID:   item.ContentID,
		ScraperID:   "feed-1",
		ScraperName: "Feed One",
	}})
	if err != nil {
		t.Fatalf("StoreContents: %v", err)
	}
	if stats.Requested != 1 || stats.Inserted != 1 || stats.Duplicates != 0 || stats.SourcesObserved != 1 {
		t.Fatalf("StoreContents stats = %#v", stats)
	}

	stats, err = store.StoreContents(ctx, []content.Content{item}, []ContentSource{{
		ContentID:   item.ContentID,
		ScraperID:   "feed-2",
		ScraperName: "Feed Two",
	}})
	if err != nil {
		t.Fatalf("StoreContents duplicate observation: %v", err)
	}
	if stats.Requested != 1 || stats.Inserted != 0 || stats.Duplicates != 1 || stats.SourcesObserved != 1 {
		t.Fatalf("duplicate StoreContents stats = %#v", stats)
	}
	stats, err = store.StoreContents(ctx, []content.Content{item}, []ContentSource{{
		ContentID:   item.ContentID,
		ScraperID:   "feed-1",
		ScraperName: "Feed One Renamed",
	}})
	if err != nil {
		t.Fatalf("StoreContents renamed source observation: %v", err)
	}

	var (
		version       int
		keywordsType  string
		publishedAt   time.Time
		primaryName   string
		sourceCount   int
		exportCount   int
		currentStatus string
	)
	if err := store.pool.QueryRow(ctx, `SELECT MAX(version) FROM schema_migrations`).Scan(&version); err != nil {
		t.Fatalf("query schema version: %v", err)
	}
	if version != SchemaVersion {
		t.Fatalf("schema version = %d, want %d", version, SchemaVersion)
	}
	var scraperNameIndexCount int
	if err := store.pool.QueryRow(ctx, `
SELECT COUNT(*)
FROM pg_indexes
WHERE schemaname = current_schema()
  AND tablename = 'content_sources'
  AND indexname = 'ix_content_sources_scraper_name'
`).Scan(&scraperNameIndexCount); err != nil {
		t.Fatalf("query scraper name index: %v", err)
	}
	if scraperNameIndexCount != 1 {
		t.Fatalf("scraper name index count = %d, want 1", scraperNameIndexCount)
	}
	if err := store.pool.QueryRow(ctx, `
SELECT udt_name
FROM information_schema.columns
WHERE table_schema = current_schema()
  AND table_name = 'contents'
  AND column_name = 'keywords_json'
`).Scan(&keywordsType); err != nil {
		t.Fatalf("query keywords type: %v", err)
	}
	if keywordsType != "jsonb" {
		t.Fatalf("keywords_json type = %q, want jsonb", keywordsType)
	}
	if _, err := store.pool.Exec(ctx, `
INSERT INTO contents (
    content_id, title, link, summary, content, published, scraper_name
)
VALUES ('invalid-source', 'Invalid', 'https://example.com/invalid', '', 'Body', '', 'Name')
`); err == nil {
		t.Fatal("incomplete content scraper identity unexpectedly satisfied the schema constraint")
	}
	for _, test := range []struct {
		column string
		value  string
	}{
		{column: "keywords_json", value: `[1]`},
		{column: "tags_json", value: `[{"value":"go"}]`},
	} {
		query := fmt.Sprintf(`
INSERT INTO contents (
    content_id, title, link, summary, content, published, %s
)
VALUES ($1, 'Invalid JSON', 'https://example.com/invalid-json', '', 'Body', '', $2::jsonb)
`, test.column)
		if _, err := store.pool.Exec(
			ctx,
			query,
			"invalid-"+test.column,
			test.value,
		); err == nil {
			t.Fatalf("%s accepted non-string JSON array elements", test.column)
		}
	}
	if err := store.pool.QueryRow(ctx, `
SELECT published_at
FROM contents
WHERE content_id = $1
`, item.ContentID).Scan(&publishedAt); err != nil {
		t.Fatalf("query published_at: %v", err)
	}
	wantPublishedAt := time.Date(2025, time.April, 6, 5, 50, 59, 0, time.UTC)
	if !publishedAt.Equal(wantPublishedAt) {
		t.Fatalf("published_at = %s, want %s", publishedAt, wantPublishedAt)
	}
	if err := store.pool.QueryRow(ctx, `
SELECT scraper_name
FROM contents
WHERE content_id = $1
`, item.ContentID).Scan(&primaryName); err != nil {
		t.Fatalf("query primary scraper name: %v", err)
	}
	if primaryName != "Feed One Renamed" {
		t.Fatalf("primary scraper name = %q, want renamed source", primaryName)
	}
	if err := store.pool.QueryRow(ctx, `
SELECT COUNT(*)
FROM content_sources
WHERE content_id = $1
`, item.ContentID).Scan(&sourceCount); err != nil {
		t.Fatalf("query content sources: %v", err)
	}
	if sourceCount != 2 {
		t.Fatalf("content source count = %d, want 2", sourceCount)
	}
	page, err := store.ListContents(ctx, ContentListOptions{
		Limit:     10,
		ScraperID: "feed-2",
		Tags:      []string{"go"},
	})
	if err != nil {
		t.Fatalf("ListContents: %v", err)
	}
	if len(page.Items) != 1 ||
		page.Items[0].ContentID != item.ContentID ||
		page.Items[0].PublishedAt == nil ||
		!page.Items[0].PublishedAt.Equal(wantPublishedAt) {
		t.Fatalf("ListContents page = %#v", page)
	}
	page, err = store.ListContents(ctx, ContentListOptions{
		Limit:       10,
		ScraperID:   "feed-1",
		ScraperName: "Feed One Renamed",
	})
	if err != nil {
		t.Fatalf("ListContents matching provenance: %v", err)
	}
	if len(page.Items) != 1 || page.Items[0].ContentID != item.ContentID {
		t.Fatalf("matching provenance page = %#v", page)
	}
	page, err = store.ListContents(ctx, ContentListOptions{
		Limit:       10,
		ScraperID:   "feed-1",
		ScraperName: "Feed Two",
	})
	if err != nil {
		t.Fatalf("ListContents mismatched provenance: %v", err)
	}
	if len(page.Items) != 0 {
		t.Fatalf("mismatched provenance page = %#v", page)
	}
	record, found, err := store.GetContent(ctx, item.ContentID)
	if err != nil {
		t.Fatalf("GetContent: %v", err)
	}
	if !found || record.Content != item.Content || record.ContentID != item.ContentID {
		t.Fatalf("GetContent = (%#v, %t)", record, found)
	}
	if err := store.pool.QueryRow(ctx, `
SELECT COUNT(*), MIN(status)
FROM content_exports
WHERE content_id = $1
`, item.ContentID).Scan(&exportCount, &currentStatus); err != nil {
		t.Fatalf("query content exports: %v", err)
	}
	if exportCount != 1 || currentStatus != SyncPending {
		t.Fatalf("content exports = (%d, %q), want (1, %q)", exportCount, currentStatus, SyncPending)
	}
	if _, err := store.pool.Exec(ctx, `
UPDATE content_exports
SET status = 'invalid'
WHERE content_id = $1 AND target_id = $2
`, item.ContentID, target.TargetID); err == nil {
		t.Fatal("invalid export status unexpectedly satisfied the schema constraint")
	}

	claimed, err := store.Claim(ctx, target.TargetID, "worker-1", 10, time.Minute, 3)
	if err != nil {
		t.Fatalf("Claim: %v", err)
	}
	if len(claimed) != 1 || claimed[0].ContentID != item.ContentID {
		t.Fatalf("claimed contents = %#v", claimed)
	}
	renewed, err := store.Renew(
		ctx,
		target.TargetID,
		item.ContentID,
		"worker-1",
		time.Minute,
	)
	if err != nil {
		t.Fatalf("Renew: %v", err)
	}
	if !renewed {
		t.Fatal("Renew did not update the active lease")
	}
	completed, err := store.Complete(ctx, target.TargetID, item.ContentID, "worker-1")
	if err != nil {
		t.Fatalf("Complete: %v", err)
	}
	if !completed {
		t.Fatal("Complete did not finalize the claimed export")
	}
	if err := store.pool.QueryRow(ctx, `
SELECT status
FROM content_exports
WHERE content_id = $1 AND target_id = $2
`, item.ContentID, target.TargetID).Scan(&currentStatus); err != nil {
		t.Fatalf("query completed export: %v", err)
	}
	if currentStatus != SyncSynced {
		t.Fatalf("completed export status = %q, want %q", currentStatus, SyncSynced)
	}

	secondItem := item
	secondItem.ContentID = "content-2"
	secondItem.Link = "https://example.com/2"
	secondItem.ScraperName = stringPointer("Feed One Renamed")
	thirdItem := secondItem
	thirdItem.ContentID = "content-3"
	thirdItem.Link = "https://example.com/3"
	if _, err := store.StoreContents(
		ctx,
		[]content.Content{secondItem, thirdItem},
		[]ContentSource{
			{
				ContentID:   secondItem.ContentID,
				ScraperID:   "feed-1",
				ScraperName: "Feed One Renamed",
			},
			{
				ContentID:   thirdItem.ContentID,
				ScraperID:   "feed-1",
				ScraperName: "Feed One Renamed",
			},
		},
	); err != nil {
		t.Fatalf("StoreContents pending items: %v", err)
	}
	claimed, err = store.Claim(ctx, target.TargetID, "worker-before-disable", 1, time.Minute, 3)
	if err != nil {
		t.Fatalf("Claim before target disable: %v", err)
	}
	if len(claimed) != 1 {
		t.Fatalf("claimed before target disable = %#v", claimed)
	}
	activeContentID := claimed[0].ContentID

	replacementTarget := ExportTarget{
		TargetID:               "notion:replacement-destination",
		Kind:                   "notion",
		DestinationFingerprint: strings.Repeat("b", 64),
	}
	if err := store.ReconcileTargets(ctx, []ExportTarget{replacementTarget}); err != nil {
		t.Fatalf("ReconcileTargets replacement: %v", err)
	}
	var (
		oldTargetEnabled bool
		newTargetStatus  string
	)
	if err := store.pool.QueryRow(ctx, `
SELECT enabled
FROM export_targets
WHERE target_id = $1
`, target.TargetID).Scan(&oldTargetEnabled); err != nil {
		t.Fatalf("query old target: %v", err)
	}
	if oldTargetEnabled {
		t.Fatal("old target remained enabled after destination replacement")
	}
	renewed, err = store.Renew(
		ctx,
		target.TargetID,
		activeContentID,
		"worker-before-disable",
		time.Minute,
	)
	if err != nil {
		t.Fatalf("Renew disabled target: %v", err)
	}
	if renewed {
		t.Fatal("disabled target renewed an active lease")
	}
	claimed, err = store.Claim(ctx, target.TargetID, "stale-worker", 10, time.Minute, 3)
	if err != nil {
		t.Fatalf("Claim disabled target: %v", err)
	}
	if len(claimed) != 0 {
		t.Fatalf("disabled target claimed contents: %#v", claimed)
	}
	if err := store.pool.QueryRow(ctx, `
SELECT status
FROM content_exports
WHERE content_id = $1 AND target_id = $2
`, item.ContentID, replacementTarget.TargetID).Scan(&newTargetStatus); err != nil {
		t.Fatalf("query replacement export: %v", err)
	}
	if newTargetStatus != SyncPending {
		t.Fatalf("replacement export status = %q, want %q", newTargetStatus, SyncPending)
	}
	counts, err := store.SyncCounts(ctx)
	if err != nil {
		t.Fatalf("SyncCounts: %v", err)
	}
	if counts[SyncPending] != 3 || counts[SyncSynced] != 0 {
		t.Fatalf("active target sync counts = %#v", counts)
	}
	conflictingTarget := replacementTarget
	conflictingTarget.DestinationFingerprint = strings.Repeat("c", 64)
	if err := store.ReconcileTargets(ctx, []ExportTarget{conflictingTarget}); err == nil {
		t.Fatal("conflicting target identity unexpectedly reconciled")
	}
	if err := store.pool.QueryRow(ctx, `
SELECT enabled
FROM export_targets
WHERE target_id = $1
`, replacementTarget.TargetID).Scan(&oldTargetEnabled); err != nil {
		t.Fatalf("query replacement target after conflict: %v", err)
	}
	if !oldTargetEnabled {
		t.Fatal("target identity conflict did not roll back reconciliation")
	}
}

func TestPostgresStoreIntegrationNormalizesNULStringArrays(t *testing.T) {
	store := newPostgresIntegrationStore(t)
	ctx := context.Background()
	if err := store.Initialize(ctx); err != nil {
		t.Fatalf("Initialize: %v", err)
	}
	items := []content.Content{
		{
			ContentID: "normal-array",
			Title:     "Normal",
			Keywords:  []string{"normal"},
			Tags:      []string{"tag"},
		},
		{
			ContentID: "nul-array",
			Title:     "NUL",
			Keywords:  []string{"before\x00after"},
			Tags:      []string{"tag\x00value"},
		},
	}
	stats, err := store.StoreContents(ctx, items, nil)
	if err != nil {
		t.Fatalf("StoreContents: %v", err)
	}
	if stats.Inserted != len(items) {
		t.Fatalf("inserted = %d, want %d", stats.Inserted, len(items))
	}
	var keywordsJSON, tagsJSON string
	if err := store.pool.QueryRow(ctx, `
SELECT keywords_json::text, tags_json::text
FROM contents
WHERE content_id = 'nul-array'
`).Scan(&keywordsJSON, &tagsJSON); err != nil {
		t.Fatalf("query normalized arrays: %v", err)
	}
	for raw, expected := range map[string]string{
		keywordsJSON: "before\uFFFDafter",
		tagsJSON:     "tag\uFFFDvalue",
	} {
		var values []string
		if err := json.Unmarshal([]byte(raw), &values); err != nil {
			t.Fatal(err)
		}
		if len(values) != 1 || values[0] != expected {
			t.Fatalf("normalized array = %#v, want %q", values, expected)
		}
	}
}

func TestPostgresStoreIntegrationMigratesV2ToV3(t *testing.T) {
	store := newPostgresIntegrationStore(t)
	ctx := context.Background()

	if _, err := store.pool.Exec(ctx, `
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO schema_migrations (version) VALUES (2);

CREATE TABLE contents (
    content_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    link TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    published TEXT NOT NULL DEFAULT '',
    author TEXT,
    keywords_json TEXT NOT NULL DEFAULT '[]',
    tags_json TEXT NOT NULL DEFAULT '[]',
    scraper_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE export_targets (
    exporter_id TEXT PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE content_exports (
    content_id TEXT NOT NULL REFERENCES contents(content_id) ON DELETE CASCADE,
    exporter_id TEXT NOT NULL REFERENCES export_targets(exporter_id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    claimed_by TEXT,
    claimed_at TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (content_id, exporter_id)
);

INSERT INTO contents (
    content_id, title, link, published, keywords_json, tags_json, scraper_name,
    created_at, updated_at
)
VALUES
    (
        'legacy-rss', 'Legacy RSS', 'https://example.com/rss',
        'Tue, 06 Apr 2025 13:50:59 +0800', '["rss"]', '["legacy"]', 'Legacy Feed',
        '2025-04-07T00:00:00Z', '2025-04-07T01:00:00Z'
    ),
    (
        'legacy-rfc3339', 'Legacy RFC3339', 'https://example.com/rfc3339',
        '2025-04-06T05:50:59Z', '[]', '[]', 'Legacy Feed',
        '2025-04-08T00:00:00Z', '2025-04-08T01:00:00Z'
    ),
    (
        'legacy-invalid', 'Legacy Invalid', 'https://example.com/invalid',
        'not-a-time', '[]', '[]', NULL,
        '2025-04-09T00:00:00Z', '2025-04-09T01:00:00Z'
    ),
    (
        'legacy-json-normalization', 'Legacy JSON', 'https://example.com/json',
        '', '["before\u0000after"]', 'null', NULL,
        '2025-04-10T00:00:00Z', '2025-04-10T01:00:00Z'
    );

INSERT INTO export_targets (exporter_id) VALUES ('notion');
INSERT INTO content_exports (
    content_id, exporter_id, status, attempts, completed_at
)
VALUES ('legacy-rss', 'notion', 'synced', 1, '2025-04-07T02:00:00Z');
`); err != nil {
		t.Fatalf("seed v2 schema: %v", err)
	}
	if _, err := store.pool.Exec(ctx, `SET TIME ZONE 'Asia/Shanghai'`); err != nil {
		t.Fatalf("set migration session timezone: %v", err)
	}
	baseTime := time.Date(2025, time.April, 6, 5, 50, 59, 0, time.UTC)
	migrationFormats := []struct {
		value string
		want  time.Time
	}{
		{value: "2025-04-06T05:50:59.123456789Z", want: baseTime.Add(123456000)},
		{value: "2025-04-06T05:50:59Z", want: baseTime},
		{value: "Sun, 06 Apr 2025 13:50:59 +0800", want: baseTime},
		{value: "Sun, 06 Apr 2025 05:50:59 GMT", want: baseTime},
		{value: "06 Apr 25 13:50 +0800", want: baseTime.Truncate(time.Minute)},
		{value: "06 Apr 25 05:50 GMT", want: baseTime.Truncate(time.Minute)},
		{value: "Sunday, 06-Apr-25 05:50:59 GMT", want: baseTime},
		{value: "Sun Apr 06 13:50:59 +0800 2025", want: baseTime},
		{value: "2025-04-06 13:50:59+08:00", want: baseTime},
		{value: "2025-04-06 05:50:59 +0000 UTC", want: baseTime},
		{value: "2025-04-06 13:50:59 +0800", want: baseTime},
		{value: "2025-04-06 05:50:59", want: baseTime},
		{value: "2025-04-06", want: time.Date(2025, time.April, 6, 0, 0, 0, 0, time.UTC)},
		{value: "Sun Apr  6 05:50:59 2025", want: baseTime},
	}
	for index, migrationFormat := range migrationFormats {
		if _, ok := content.ParsePublishedTime(migrationFormat.value); !ok {
			t.Fatalf("test publication format is unsupported: %q", migrationFormat.value)
		}
		if _, err := store.pool.Exec(ctx, `
INSERT INTO contents (
    content_id, title, link, published, keywords_json, tags_json,
    created_at, updated_at
)
VALUES ($1, $2, $3, $4, '[]', '[]', NOW(), NOW())
`,
			fmt.Sprintf("migration-format-%d", index),
			fmt.Sprintf("Migration Format %d", index),
			fmt.Sprintf("https://example.com/format/%d", index),
			migrationFormat.value,
		); err != nil {
			t.Fatalf("seed publication format %q: %v", migrationFormat.value, err)
		}
	}

	if err := store.Initialize(ctx); err != nil {
		t.Fatalf("Initialize v2 schema: %v", err)
	}

	var (
		version                int
		rssPublishedAt         *time.Time
		rfc3339PublishedAt     *time.Time
		invalidPublishedAt     *time.Time
		scraperID              *string
		sourceCount            int
		targetKind             string
		targetFingerprint      string
		targetEnabled          bool
		exportStatus           string
		legacyUpdatedAtColumns int
		normalizedKeywordsJSON string
		normalizedTagsJSON     string
	)
	if err := store.pool.QueryRow(ctx, `SELECT MAX(version) FROM schema_migrations`).Scan(&version); err != nil {
		t.Fatalf("query migrated schema version: %v", err)
	}
	if version != SchemaVersion {
		t.Fatalf("schema version = %d, want %d", version, SchemaVersion)
	}
	var scraperNameIndexCount int
	if err := store.pool.QueryRow(ctx, `
SELECT COUNT(*)
FROM pg_indexes
WHERE schemaname = current_schema()
  AND tablename = 'content_sources'
  AND indexname = 'ix_content_sources_scraper_name'
`).Scan(&scraperNameIndexCount); err != nil {
		t.Fatalf("query migrated scraper name index: %v", err)
	}
	if scraperNameIndexCount != 1 {
		t.Fatalf("migrated scraper name index count = %d, want 1", scraperNameIndexCount)
	}
	if err := store.pool.QueryRow(ctx, `
SELECT published_at, scraper_id
FROM contents
WHERE content_id = 'legacy-rss'
`).Scan(&rssPublishedAt, &scraperID); err != nil {
		t.Fatalf("query migrated RSS row: %v", err)
	}
	if rssPublishedAt == nil || !rssPublishedAt.Equal(time.Date(2025, time.April, 6, 5, 50, 59, 0, time.UTC)) {
		t.Fatalf("legacy RSS published_at = %v", rssPublishedAt)
	}
	wantLegacyScraperID := legacyIdentifier("Legacy Feed")
	if scraperID == nil || *scraperID != wantLegacyScraperID {
		t.Fatalf("legacy scraper_id = %v, want %q", scraperID, wantLegacyScraperID)
	}
	if err := store.pool.QueryRow(ctx, `
SELECT published_at
FROM contents
WHERE content_id = 'legacy-rfc3339'
`).Scan(&rfc3339PublishedAt); err != nil {
		t.Fatalf("query migrated RFC3339 row: %v", err)
	}
	if rfc3339PublishedAt == nil || !rfc3339PublishedAt.Equal(time.Date(2025, time.April, 6, 5, 50, 59, 0, time.UTC)) {
		t.Fatalf("legacy RFC3339 published_at = %v", rfc3339PublishedAt)
	}
	if err := store.pool.QueryRow(ctx, `
SELECT published_at
FROM contents
WHERE content_id = 'legacy-invalid'
`).Scan(&invalidPublishedAt); err != nil {
		t.Fatalf("query migrated invalid row: %v", err)
	}
	if invalidPublishedAt != nil {
		t.Fatalf("invalid legacy published_at = %v, want nil", invalidPublishedAt)
	}
	if err := store.pool.QueryRow(ctx, `
SELECT keywords_json::text, tags_json::text
FROM contents
WHERE content_id = 'legacy-json-normalization'
`).Scan(&normalizedKeywordsJSON, &normalizedTagsJSON); err != nil {
		t.Fatalf("query normalized legacy JSON: %v", err)
	}
	var (
		normalizedKeywords []string
		normalizedTags     []string
	)
	if err := json.Unmarshal([]byte(normalizedKeywordsJSON), &normalizedKeywords); err != nil {
		t.Fatalf("decode normalized keywords: %v", err)
	}
	if err := json.Unmarshal([]byte(normalizedTagsJSON), &normalizedTags); err != nil {
		t.Fatalf("decode normalized tags: %v", err)
	}
	if len(normalizedKeywords) != 1 ||
		normalizedKeywords[0] != "before\uFFFDafter" ||
		len(normalizedTags) != 0 {
		t.Fatalf(
			"normalized legacy JSON = (%#v, %#v)",
			normalizedKeywords,
			normalizedTags,
		)
	}
	for index, migrationFormat := range migrationFormats {
		var migratedTime *time.Time
		if err := store.pool.QueryRow(ctx, `
SELECT published_at
FROM contents
WHERE content_id = $1
`, fmt.Sprintf("migration-format-%d", index)).Scan(&migratedTime); err != nil {
			t.Fatalf("query publication format %q: %v", migrationFormat.value, err)
		}
		if migratedTime == nil || !migratedTime.Equal(migrationFormat.want) {
			t.Fatalf(
				"publication format %q migrated to %v, want %s",
				migrationFormat.value,
				migratedTime,
				migrationFormat.want,
			)
		}
	}
	if err := store.pool.QueryRow(ctx, `
SELECT COUNT(*)
FROM content_sources
WHERE scraper_id = $1
`, wantLegacyScraperID).Scan(&sourceCount); err != nil {
		t.Fatalf("query migrated sources: %v", err)
	}
	if sourceCount != 2 {
		t.Fatalf("migrated source count = %d, want 2", sourceCount)
	}
	if err := store.pool.QueryRow(ctx, `
SELECT kind, destination_fingerprint, enabled
FROM export_targets
WHERE target_id = 'notion'
`).Scan(&targetKind, &targetFingerprint, &targetEnabled); err != nil {
		t.Fatalf("query migrated target: %v", err)
	}
	if targetKind != "notion" ||
		targetFingerprint != legacyIdentifier("notion") ||
		!targetEnabled {
		t.Fatalf(
			"migrated target = (%q, %q, %t)",
			targetKind,
			targetFingerprint,
			targetEnabled,
		)
	}
	if err := store.pool.QueryRow(ctx, `
SELECT status
FROM content_exports
WHERE content_id = 'legacy-rss' AND target_id = 'notion'
`).Scan(&exportStatus); err != nil {
		t.Fatalf("query migrated export: %v", err)
	}
	if exportStatus != SyncSynced {
		t.Fatalf("migrated export status = %q, want %q", exportStatus, SyncSynced)
	}
	if err := store.pool.QueryRow(ctx, `
SELECT COUNT(*)
FROM information_schema.columns
WHERE table_schema = current_schema()
  AND table_name = 'contents'
  AND column_name = 'updated_at'
`).Scan(&legacyUpdatedAtColumns); err != nil {
		t.Fatalf("query legacy updated_at columns: %v", err)
	}
	if legacyUpdatedAtColumns != 0 {
		t.Fatalf("legacy updated_at column count = %d, want 0", legacyUpdatedAtColumns)
	}
}

func TestPostgresStoreIntegrationMigratesV1ToV3(t *testing.T) {
	store := newPostgresIntegrationStore(t)
	ctx := context.Background()

	if _, err := store.pool.Exec(ctx, `
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO schema_migrations (version) VALUES (1);

CREATE TABLE contents (
    content_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    link TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    published TEXT NOT NULL DEFAULT '',
    author TEXT,
    keywords_json TEXT NOT NULL DEFAULT '[]',
    tags_json TEXT NOT NULL DEFAULT '[]',
    scraper_name TEXT,
    notion_sync_status TEXT NOT NULL DEFAULT 'pending',
    notion_synced_at TIMESTAMPTZ,
    notion_sync_attempts INTEGER NOT NULL DEFAULT 0,
    notion_sync_error TEXT,
    notion_next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notion_claimed_by TEXT,
    notion_claimed_at TIMESTAMPTZ,
    notion_lease_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO contents (
    content_id, title, link, published, scraper_name, notion_sync_status,
    notion_synced_at, notion_sync_attempts, created_at, updated_at
)
VALUES (
    'legacy-v1', 'Legacy V1', 'https://example.com/v1',
    '2025-04-06T05:50:59Z', 'Legacy V1 Feed', 'synced',
    '2025-04-07T00:00:00Z', 2,
    '2025-04-06T06:00:00Z', '2025-04-07T00:00:00Z'
);
`); err != nil {
		t.Fatalf("seed v1 schema: %v", err)
	}

	if err := store.Initialize(ctx); err != nil {
		t.Fatalf("Initialize v1 schema: %v", err)
	}

	var (
		version             int
		exportStatus        string
		exportAttempts      int
		completedAt         *time.Time
		legacyNotionColumns int
		sourceCount         int
	)
	if err := store.pool.QueryRow(ctx, `SELECT MAX(version) FROM schema_migrations`).Scan(&version); err != nil {
		t.Fatalf("query migrated schema version: %v", err)
	}
	if version != SchemaVersion {
		t.Fatalf("schema version = %d, want %d", version, SchemaVersion)
	}
	if err := store.pool.QueryRow(ctx, `
SELECT status, attempts, completed_at
FROM content_exports
WHERE content_id = 'legacy-v1' AND target_id = 'notion'
`).Scan(&exportStatus, &exportAttempts, &completedAt); err != nil {
		t.Fatalf("query migrated v1 export: %v", err)
	}
	if exportStatus != SyncSynced || exportAttempts != 2 || completedAt == nil {
		t.Fatalf(
			"migrated v1 export = (%q, %d, %v)",
			exportStatus,
			exportAttempts,
			completedAt,
		)
	}
	if err := store.pool.QueryRow(ctx, `
SELECT COUNT(*)
FROM information_schema.columns
WHERE table_schema = current_schema()
  AND table_name = 'contents'
  AND column_name LIKE 'notion_%'
`).Scan(&legacyNotionColumns); err != nil {
		t.Fatalf("query legacy Notion columns: %v", err)
	}
	if legacyNotionColumns != 0 {
		t.Fatalf("legacy Notion column count = %d, want 0", legacyNotionColumns)
	}
	if err := store.pool.QueryRow(ctx, `
SELECT COUNT(*)
FROM content_sources
WHERE content_id = 'legacy-v1'
`).Scan(&sourceCount); err != nil {
		t.Fatalf("query migrated v1 source: %v", err)
	}
	if sourceCount != 1 {
		t.Fatalf("migrated v1 source count = %d, want 1", sourceCount)
	}
}

func TestPostgresStoreIntegrationUsesNewestObservation(t *testing.T) {
	store := newPostgresIntegrationStore(t)
	ctx := context.Background()
	if err := store.Initialize(ctx); err != nil {
		t.Fatalf("Initialize: %v", err)
	}

	newObservedAt := time.Date(2026, 8, 30, 4, 0, 0, 0, time.UTC)
	oldObservedAt := newObservedAt.Add(-time.Hour)
	item := content.Content{
		ContentID: "observed-order",
		Title:     "Observed order",
		Link:      "https://example.com/observed-order",
		Summary:   "Summary",
		Content:   "Body",
		Published: "2026-08-30T04:00:00Z",
	}
	if _, err := store.StoreContents(ctx, []content.Content{item}, []ContentSource{{
		ContentID:   item.ContentID,
		ScraperID:   "feed",
		ScraperName: "New name",
		ObservedAt:  newObservedAt,
	}}); err != nil {
		t.Fatalf("StoreContents new observation: %v", err)
	}
	if _, err := store.StoreContents(ctx, []content.Content{item}, []ContentSource{{
		ContentID:   item.ContentID,
		ScraperID:   "feed",
		ScraperName: "Old name",
		ObservedAt:  oldObservedAt,
	}}); err != nil {
		t.Fatalf("StoreContents old observation: %v", err)
	}

	var (
		sourceName  string
		firstSeen   time.Time
		lastSeen    time.Time
		primaryID   string
		primaryName string
	)
	if err := store.pool.QueryRow(ctx, `
SELECT scraper_name, first_seen_at, last_seen_at
FROM content_sources
WHERE content_id = $1 AND scraper_id = $2
`, item.ContentID, "feed").Scan(&sourceName, &firstSeen, &lastSeen); err != nil {
		t.Fatalf("query observed source: %v", err)
	}
	if sourceName != "New name" ||
		!firstSeen.Equal(oldObservedAt) ||
		!lastSeen.Equal(newObservedAt) {
		t.Fatalf(
			"source observation = (%q, %s, %s), want (%q, %s, %s)",
			sourceName, firstSeen, lastSeen, "New name", oldObservedAt, newObservedAt,
		)
	}
	if err := store.pool.QueryRow(ctx, `
SELECT scraper_id, scraper_name
FROM contents
WHERE content_id = $1
`, item.ContentID).Scan(&primaryID, &primaryName); err != nil {
		t.Fatalf("query primary observation: %v", err)
	}
	if primaryID != "feed" || primaryName != "New name" {
		t.Fatalf("primary observation = (%q, %q)", primaryID, primaryName)
	}
}

func TestPostgresStoreIntegrationPreservesPrimarySourceAcrossObservers(t *testing.T) {
	store := newPostgresIntegrationStore(t)
	ctx := context.Background()
	if err := store.Initialize(ctx); err != nil {
		t.Fatalf("Initialize: %v", err)
	}

	item := content.Content{
		ContentID:   "primary-source",
		Title:       "Primary source",
		Link:        "https://example.com/primary-source",
		Summary:     "Summary",
		Content:     "Body",
		Published:   "2026-08-30T04:00:00Z",
		ScraperID:   stringPointer("feed-a"),
		ScraperName: stringPointer("Feed A"),
	}
	firstObservedAt := time.Date(2026, 8, 30, 4, 0, 0, 0, time.UTC)
	if _, err := store.StoreContents(ctx, []content.Content{item}, []ContentSource{{
		ContentID:   item.ContentID,
		ScraperID:   "feed-a",
		ScraperName: "Feed A",
		ObservedAt:  firstObservedAt,
	}}); err != nil {
		t.Fatalf("StoreContents primary source: %v", err)
	}
	if _, err := store.StoreContents(ctx, nil, []ContentSource{{
		ContentID:   item.ContentID,
		ScraperID:   "feed-b",
		ScraperName: "Feed B",
		ObservedAt:  firstObservedAt.Add(time.Hour),
	}}); err != nil {
		t.Fatalf("StoreContents secondary source: %v", err)
	}

	var primaryID, primaryName string
	if err := store.pool.QueryRow(ctx, `
SELECT scraper_id, scraper_name
FROM contents
WHERE content_id = $1
`, item.ContentID).Scan(&primaryID, &primaryName); err != nil {
		t.Fatalf("query primary source: %v", err)
	}
	if primaryID != "feed-a" || primaryName != "Feed A" {
		t.Fatalf("primary source = (%q, %q), want feed-a/Feed A", primaryID, primaryName)
	}
}

func TestPostgresStoreIntegrationSerializesContentAndTargetChanges(t *testing.T) {
	for _, first := range []string{"content", "target"} {
		t.Run(first+"-first", func(t *testing.T) {
			store := newPostgresIntegrationStore(t)
			peer := newPostgresIntegrationPeerStore(t, store)
			ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
			defer cancel()
			if err := store.Initialize(ctx); err != nil {
				t.Fatalf("Initialize: %v", err)
			}

			oldTarget := ExportTarget{
				TargetID:               "target:old",
				Kind:                   "notion",
				DestinationFingerprint: strings.Repeat("a", 64),
			}
			newTarget := ExportTarget{
				TargetID:               "target:new",
				Kind:                   "notion",
				DestinationFingerprint: strings.Repeat("b", 64),
			}
			if err := store.ReconcileTargets(ctx, []ExportTarget{oldTarget}); err != nil {
				t.Fatalf("seed old target: %v", err)
			}
			blocker, err := peer.pool.Begin(ctx)
			if err != nil {
				t.Fatalf("begin coordination blocker: %v", err)
			}
			defer blocker.Rollback(context.Background())
			if _, err := blocker.Exec(ctx,
				`SELECT pg_advisory_xact_lock($1)`, contentTargetLockKey,
			); err != nil {
				t.Fatalf("acquire coordination blocker: %v", err)
			}

			item := content.Content{
				ContentID: "serialized-content",
				Title:     "Serialized content",
				Link:      "https://example.com/serialized-content",
				Summary:   "Summary",
				Content:   "Body",
				Published: "2026-08-30T04:00:00Z",
			}
			results := make(chan error, 2)
			startContent := func() {
				go func() {
					_, err := peer.StoreContents(ctx, []content.Content{item}, []ContentSource{{
						ContentID:   item.ContentID,
						ScraperID:   "feed",
						ScraperName: "Feed",
						ObservedAt:  time.Date(2026, 8, 30, 4, 0, 0, 0, time.UTC),
					}})
					results <- err
				}()
			}
			startTarget := func() {
				go func() {
					results <- store.ReconcileTargets(ctx, []ExportTarget{newTarget})
				}()
			}
			if first == "content" {
				startContent()
				if err := waitForContentTargetWaiters(ctx, store, 1); err != nil {
					t.Fatalf("wait for content waiter: %v", err)
				}
				startTarget()
			} else {
				startTarget()
				if err := waitForContentTargetWaiters(ctx, peer, 1); err != nil {
					t.Fatalf("wait for target waiter: %v", err)
				}
				startContent()
			}
			if err := waitForContentTargetWaiters(ctx, store, 2); err != nil {
				t.Fatalf("wait for both waiters: %v", err)
			}
			if err := blocker.Rollback(ctx); err != nil {
				t.Fatalf("release coordination blocker: %v", err)
			}
			for range 2 {
				select {
				case err := <-results:
					if err != nil {
						t.Fatalf("serialized operation: %v", err)
					}
				case <-ctx.Done():
					t.Fatalf("serialized operations did not finish: %v", ctx.Err())
				}
			}

			var oldExportCount int
			if err := store.pool.QueryRow(ctx, `
SELECT COUNT(*)
FROM content_exports
WHERE content_id = $1 AND target_id = $2
`, item.ContentID, oldTarget.TargetID).Scan(&oldExportCount); err != nil {
				t.Fatalf("query old target export: %v", err)
			}
			var replacementExportCount int
			if err := store.pool.QueryRow(ctx, `
SELECT COUNT(*)
FROM content_exports
WHERE content_id = $1 AND target_id = $2
`, item.ContentID, newTarget.TargetID).Scan(&replacementExportCount); err != nil {
				t.Fatalf("query replacement target export: %v", err)
			}
			if replacementExportCount != 1 {
				t.Fatalf("replacement target export count = %d, want 1", replacementExportCount)
			}
			if first == "content" && oldExportCount != 1 {
				t.Fatalf("content-first old target export count = %d, want 1", oldExportCount)
			}
			if first == "target" && oldExportCount != 0 {
				t.Fatalf("target-first old target export count = %d, want 0", oldExportCount)
			}
		})
	}
}

func TestPostgresStoreIntegrationSerializesConcurrentReconciliations(t *testing.T) {
	store := newPostgresIntegrationStore(t)
	peerA := newPostgresIntegrationPeerStore(t, store)
	peerB := newPostgresIntegrationPeerStore(t, store)
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	if err := store.Initialize(ctx); err != nil {
		t.Fatalf("Initialize: %v", err)
	}
	targetA := ExportTarget{
		TargetID:               "target:a",
		Kind:                   "notion",
		DestinationFingerprint: strings.Repeat("a", 64),
	}
	targetB := ExportTarget{
		TargetID:               "target:b",
		Kind:                   "notion",
		DestinationFingerprint: strings.Repeat("b", 64),
	}
	blocker, err := store.pool.Begin(ctx)
	if err != nil {
		t.Fatalf("begin coordination blocker: %v", err)
	}
	defer blocker.Rollback(context.Background())
	if _, err := blocker.Exec(ctx,
		`SELECT pg_advisory_xact_lock($1)`, contentTargetLockKey,
	); err != nil {
		t.Fatalf("acquire coordination blocker: %v", err)
	}
	results := make(chan error, 2)
	go func() {
		results <- peerA.ReconcileTargets(ctx, []ExportTarget{targetA})
	}()
	if err := waitForContentTargetWaiters(ctx, peerB, 1); err != nil {
		t.Fatalf("wait for reconciliation A: %v", err)
	}
	go func() {
		results <- peerB.ReconcileTargets(ctx, []ExportTarget{targetB})
	}()
	if err := waitForContentTargetWaiters(ctx, store, 2); err != nil {
		t.Fatalf("wait for reconciliation B: %v", err)
	}
	if err := blocker.Rollback(ctx); err != nil {
		t.Fatalf("release coordination blocker: %v", err)
	}
	for range 2 {
		select {
		case err := <-results:
			if err != nil {
				t.Fatalf("concurrent reconciliation: %v", err)
			}
		case <-ctx.Done():
			t.Fatalf("concurrent reconciliations did not finish: %v", ctx.Err())
		}
	}
	var enabledCount int
	if err := store.pool.QueryRow(ctx, `
SELECT COUNT(*)
FROM export_targets
WHERE enabled
`).Scan(&enabledCount); err != nil {
		t.Fatalf("query enabled targets: %v", err)
	}
	if enabledCount != 1 {
		t.Fatalf("enabled target count = %d, want 1", enabledCount)
	}
	var targetAEnabled, targetBEnabled bool
	if err := store.pool.QueryRow(ctx,
		`SELECT enabled FROM export_targets WHERE target_id = $1`, targetA.TargetID,
	).Scan(&targetAEnabled); err != nil {
		t.Fatalf("query target A: %v", err)
	}
	if err := store.pool.QueryRow(ctx,
		`SELECT enabled FROM export_targets WHERE target_id = $1`, targetB.TargetID,
	).Scan(&targetBEnabled); err != nil {
		t.Fatalf("query target B: %v", err)
	}
	if targetAEnabled || !targetBEnabled {
		t.Fatalf("target states = A:%t B:%t, want A:false B:true", targetAEnabled, targetBEnabled)
	}
}

func newPostgresIntegrationPeerStore(t *testing.T, primary *PostgresStore) *PostgresStore {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	var schemaName string
	if err := primary.pool.QueryRow(ctx, `SELECT current_schema()`).Scan(&schemaName); err != nil {
		t.Fatalf("query integration schema: %v", err)
	}
	storeURL, err := url.Parse(os.Getenv("TEST_DATABASE_URL"))
	if err != nil {
		t.Fatalf("parse TEST_DATABASE_URL: %v", err)
	}
	query := storeURL.Query()
	query.Set("search_path", schemaName)
	storeURL.RawQuery = query.Encode()
	peer, err := NewPostgresStore(config.DatabaseConfig{
		URL:            storeURL.String(),
		PoolSize:       4,
		ConnectTimeout: 10 * time.Second,
	}, slog.New(slog.NewTextHandler(io.Discard, nil)))
	if err != nil {
		t.Fatalf("create integration peer store: %v", err)
	}
	t.Cleanup(peer.Close)
	return peer
}

func waitForContentTargetWaiters(
	ctx context.Context,
	store *PostgresStore,
	want int,
) error {
	for {
		var count int
		if err := store.pool.QueryRow(ctx, `
SELECT COUNT(*)
FROM pg_locks
WHERE locktype = 'advisory'
  AND classid = 0
  AND objid = $1::oid
  AND NOT granted
`, contentTargetLockKey).Scan(&count); err != nil {
			return err
		}
		if count >= want {
			return nil
		}
		runtime.Gosched()
	}
}

func newPostgresIntegrationStore(t *testing.T) *PostgresStore {
	t.Helper()

	databaseURL := os.Getenv("TEST_DATABASE_URL")
	if databaseURL == "" {
		t.Skip("TEST_DATABASE_URL is not set")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	adminPool, err := pgxpool.New(ctx, databaseURL)
	if err != nil {
		t.Fatalf("open PostgreSQL admin pool: %v", err)
	}
	if err := adminPool.Ping(ctx); err != nil {
		adminPool.Close()
		t.Fatalf("ping PostgreSQL: %v", err)
	}

	schemaName := fmt.Sprintf("octopus_storage_%d", time.Now().UnixNano())
	quotedSchema := pgx.Identifier{schemaName}.Sanitize()
	if _, err := adminPool.Exec(ctx, "CREATE SCHEMA "+quotedSchema); err != nil {
		adminPool.Close()
		t.Fatalf("create PostgreSQL test schema: %v", err)
	}

	storeURL, err := url.Parse(databaseURL)
	if err != nil {
		adminPool.Exec(context.Background(), "DROP SCHEMA "+quotedSchema+" CASCADE")
		adminPool.Close()
		t.Fatalf("parse TEST_DATABASE_URL: %v", err)
	}
	query := storeURL.Query()
	query.Set("search_path", schemaName)
	storeURL.RawQuery = query.Encode()
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	store, err := NewPostgresStore(config.DatabaseConfig{
		URL:            storeURL.String(),
		PoolSize:       4,
		ConnectTimeout: 10 * time.Second,
	}, logger)
	if err != nil {
		adminPool.Exec(context.Background(), "DROP SCHEMA "+quotedSchema+" CASCADE")
		adminPool.Close()
		t.Fatalf("create PostgreSQL store: %v", err)
	}

	t.Cleanup(func() {
		store.Close()
		cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 15*time.Second)
		defer cleanupCancel()
		if _, err := adminPool.Exec(cleanupCtx, "DROP SCHEMA "+quotedSchema+" CASCADE"); err != nil {
			t.Errorf("drop PostgreSQL test schema: %v", err)
		}
		adminPool.Close()
	})
	return store
}

func stringPointer(value string) *string {
	return &value
}

func legacyIdentifier(value string) string {
	return fmt.Sprintf("legacy:%x", md5.Sum([]byte(value)))
}
