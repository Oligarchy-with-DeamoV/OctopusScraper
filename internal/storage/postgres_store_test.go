package storage

import (
	"context"
	"io"
	"log/slog"
	"testing"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/config"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
	pgxmock "github.com/pashagolub/pgxmock/v4"
)

func TestNewPostgresStoreConfiguration(t *testing.T) {
	if _, err := NewPostgresStore(
		config.DatabaseConfig{URL: "://invalid"},
		nil,
	); err == nil {
		t.Fatal("expected invalid PostgreSQL URL error")
	}
	store, err := NewPostgresStore(config.DatabaseConfig{
		URL:            "postgres://user:password@localhost/database",
		PoolSize:       2,
		MaxOverflow:    3,
		ConnectTimeout: time.Second,
	}, slog.New(slog.NewTextHandler(io.Discard, nil)))
	if err != nil {
		t.Fatal(err)
	}
	store.Close()
	var nilStore *PostgresStore
	nilStore.Close()
}

func TestPostgresStoreInitializeAndPing(t *testing.T) {
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatal(err)
	}
	defer mock.Close()
	store := newPostgresStoreWithPool(mock)
	store.logger = slog.New(slog.NewTextHandler(io.Discard, nil))
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT pg_advisory_xact_lock`).WithArgs(migrationLockKey).
		WillReturnResult(pgxmock.NewResult("SELECT", 1))
	mock.ExpectExec(`CREATE TABLE IF NOT EXISTS schema_migrations`).
		WillReturnResult(pgxmock.NewResult("CREATE", 0))
	mock.ExpectExec(`CREATE TABLE IF NOT EXISTS contents`).
		WillReturnResult(pgxmock.NewResult("CREATE", 0))
	mock.ExpectExec(`CREATE INDEX IF NOT EXISTS ix_contents_notion_sync_status`).
		WillReturnResult(pgxmock.NewResult("CREATE", 0))
	mock.ExpectExec(`INSERT INTO schema_migrations`).WithArgs(SchemaVersion).
		WillReturnResult(pgxmock.NewResult("INSERT", 1))
	mock.ExpectCommit()
	if err := store.Initialize(context.Background()); err != nil {
		t.Fatal(err)
	}
	mock.ExpectPing()
	if err := store.Ping(context.Background()); err != nil {
		t.Fatal(err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresStoreExistingContentIDsChunksRequests(t *testing.T) {
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatalf("pgxmock.NewPool() error = %v", err)
	}
	defer mock.Close()
	store := newPostgresStoreWithPool(mock)
	store.chunkSize = 2
	mock.ExpectQuery(`SELECT content_id FROM contents WHERE content_id = ANY\(\$1\)`).WithArgs([]string{"a", "b"}).WillReturnRows(pgxmock.NewRows([]string{"content_id"}).AddRow("a"))
	mock.ExpectQuery(`SELECT content_id FROM contents WHERE content_id = ANY\(\$1\)`).WithArgs([]string{"c"}).WillReturnRows(pgxmock.NewRows([]string{"content_id"}).AddRow("c"))

	ids, err := store.ExistingContentIDs(context.Background(), []string{"a", "b", "a", "c"})
	if err != nil {
		t.Fatalf("ExistingContentIDs() error = %v", err)
	}
	if _, ok := ids["a"]; !ok {
		t.Fatalf("missing existing id a: %#v", ids)
	}
	if _, ok := ids["c"]; !ok {
		t.Fatalf("missing existing id c: %#v", ids)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("ExpectationsWereMet() error = %v", err)
	}
}

func TestPostgresStoreEmptyOperations(t *testing.T) {
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatal(err)
	}
	defer mock.Close()
	store := newPostgresStoreWithPool(mock)
	ids, err := store.ExistingContentIDs(context.Background(), nil)
	if err != nil || len(ids) != 0 {
		t.Fatalf("unexpected IDs: %#v, %v", ids, err)
	}
	stats, err := store.StoreContents(context.Background(), nil)
	if err != nil || stats.Requested != 0 || stats.Duplicates != 0 {
		t.Fatalf("unexpected stats: %#v, %v", stats, err)
	}
}

func TestBuildInsertContentsQueryStoresEmptyCollectionsAsArrays(t *testing.T) {
	_, args, err := buildInsertContentsQuery([]content.Content{
		{
			ContentID: "one",
			Title:     "Title",
			Link:      "https://example.com/one",
			Summary:   "Summary",
			Content:   "Body",
			Published: "2026-08-18T11:00:00Z",
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	if args[7] != "[]" || args[8] != "[]" {
		t.Fatalf("collection JSON = %q, %q; want [], []", args[7], args[8])
	}
}

func TestPostgresStoreStoreContentsDeduplicatesAndReportsStats(t *testing.T) {
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatalf("pgxmock.NewPool() error = %v", err)
	}
	defer mock.Close()
	store := newPostgresStoreWithPool(mock)
	mock.ExpectBegin()
	mock.ExpectExec(`INSERT INTO contents`).WithArgs(anyArgs(24)...).WillReturnResult(pgxmock.NewResult("INSERT", 1))
	mock.ExpectCommit()

	stats, err := store.StoreContents(context.Background(), []content.Content{testContent("one"), testContent("one"), testContent("two")})
	if err != nil {
		t.Fatalf("StoreContents() error = %v", err)
	}
	if stats.Requested != 3 || stats.Inserted != 1 || stats.Duplicates != 2 {
		t.Fatalf("stats = %#v", stats)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("ExpectationsWereMet() error = %v", err)
	}
}

func TestPostgresStoreStoreContentsChunksLargeBatches(t *testing.T) {
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatal(err)
	}
	defer mock.Close()
	store := newPostgresStoreWithPool(mock)
	store.chunkSize = 1
	mock.ExpectBegin()
	mock.ExpectExec(`INSERT INTO contents`).
		WithArgs(anyArgs(12)...).
		WillReturnResult(pgxmock.NewResult("INSERT", 1))
	mock.ExpectExec(`INSERT INTO contents`).
		WithArgs(anyArgs(12)...).
		WillReturnResult(pgxmock.NewResult("INSERT", 1))
	mock.ExpectCommit()

	stats, err := store.StoreContents(
		context.Background(),
		[]content.Content{testContent("one"), testContent("two")},
	)
	if err != nil {
		t.Fatal(err)
	}
	if stats.Inserted != 2 || stats.Duplicates != 0 {
		t.Fatalf("stats = %#v", stats)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresStoreClaimContentsReturnsRows(t *testing.T) {
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatalf("pgxmock.NewPool() error = %v", err)
	}
	defer mock.Close()
	store := newPostgresStoreWithPool(mock)
	rows := pgxmock.NewRows([]string{"content_id", "title", "link", "summary", "content", "published", "author", "keywords_json", "tags_json", "scraper_name"}).
		AddRow("one", "Title", "https://example.com/one", "Summary", "Body", "2026-08-18T11:00:00Z", "Alice", `["k"]`, `["t"]`, "Feed")
	mock.ExpectQuery(`WITH due AS`).WithArgs(SyncPending, SyncRetry, 3, SyncProcessing, 1, "worker-1", 60).WillReturnRows(rows)

	claimed, err := store.ClaimContents(context.Background(), "worker-1", 1, time.Minute, 3)
	if err != nil {
		t.Fatalf("ClaimContents() error = %v", err)
	}
	if len(claimed) != 1 || claimed[0].ContentID != "one" {
		t.Fatalf("claimed = %#v", claimed)
	}
	if claimed[0].Author == nil || *claimed[0].Author != "Alice" {
		t.Fatalf("claimed author = %#v", claimed[0].Author)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("ExpectationsWereMet() error = %v", err)
	}
}

func TestPostgresStoreMarkSyncFailedAndCounts(t *testing.T) {
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatalf("pgxmock.NewPool() error = %v", err)
	}
	defer mock.Close()
	store := newPostgresStoreWithPool(mock)
	mock.ExpectQuery(`SELECT notion_sync_attempts`).WithArgs("one", "worker-1", SyncProcessing).WillReturnRows(pgxmock.NewRows([]string{"notion_sync_attempts"}).AddRow(0))
	mock.ExpectExec(`UPDATE contents`).WithArgs(1, SyncRetry, "temporary", 60, "one", "worker-1", SyncProcessing, 0).WillReturnResult(pgxmock.NewResult("UPDATE", 1))
	updated, err := store.MarkSyncFailed(context.Background(), "one", "worker-1", "temporary", 3)
	if err != nil {
		t.Fatalf("MarkSyncFailed() error = %v", err)
	}
	if !updated {
		t.Fatalf("MarkSyncFailed() = false")
	}
	countRows := pgxmock.NewRows([]string{"notion_sync_status", "count"}).AddRow(SyncRetry, int64(2)).AddRow(SyncSynced, int64(1))
	mock.ExpectQuery(`SELECT notion_sync_status, COUNT\(content_id\)`).WillReturnRows(countRows)
	counts, err := store.SyncCounts(context.Background())
	if err != nil {
		t.Fatalf("SyncCounts() error = %v", err)
	}
	if counts[SyncRetry] != 2 || counts[SyncSynced] != 1 || counts[SyncPending] != 0 {
		t.Fatalf("counts = %#v", counts)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("ExpectationsWereMet() error = %v", err)
	}
}

func TestPostgresStoreClaimLifecycle(t *testing.T) {
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatal(err)
	}
	defer mock.Close()
	store := newPostgresStoreWithPool(mock)
	mock.ExpectExec(`UPDATE contents`).
		WithArgs(60, "one", "worker-1", SyncProcessing).
		WillReturnResult(pgxmock.NewResult("UPDATE", 1))
	renewed, err := store.RenewClaim(
		context.Background(),
		"one",
		"worker-1",
		time.Minute,
	)
	if err != nil || !renewed {
		t.Fatalf("unexpected renew result: %t, %v", renewed, err)
	}
	mock.ExpectExec(`UPDATE contents`).
		WithArgs(SyncSynced, "one", "worker-1", SyncProcessing).
		WillReturnResult(pgxmock.NewResult("UPDATE", 1))
	marked, err := store.MarkSynced(context.Background(), "one", "worker-1")
	if err != nil || !marked {
		t.Fatalf("unexpected mark result: %t, %v", marked, err)
	}
	mock.ExpectQuery(`SELECT notion_sync_attempts`).
		WithArgs("missing", "worker-1", SyncProcessing).
		WillReturnRows(pgxmock.NewRows([]string{"notion_sync_attempts"}))
	marked, err = store.MarkSyncFailed(
		context.Background(),
		"missing",
		"worker-1",
		"failed",
		3,
	)
	if err != nil || marked {
		t.Fatalf("unexpected missing claim result: %t, %v", marked, err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestNextRetryDelayCapsAtOneHour(t *testing.T) {
	if got := nextRetryDelay(1); got != time.Minute {
		t.Fatalf("nextRetryDelay(1) = %s", got)
	}
	if got := nextRetryDelay(7); got != time.Hour {
		t.Fatalf("nextRetryDelay(7) = %s", got)
	}
}

func testContent(id string) content.Content {
	scraperName := "Feed"
	return content.Content{
		ContentID:   id,
		Title:       "Title " + id,
		Link:        "https://example.com/" + id,
		Summary:     "Summary",
		Content:     "Body",
		Published:   "2026-08-18T11:00:00Z",
		Keywords:    []string{"keyword"},
		Tags:        []string{"tag"},
		ScraperName: &scraperName,
	}
}

func anyArgs(count int) []any {
	args := make([]any, count)
	for index := range args {
		args[index] = pgxmock.AnyArg()
	}
	return args
}
