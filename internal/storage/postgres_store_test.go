package storage

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"slices"
	"strings"
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
	mock.ExpectQuery(`SELECT COALESCE\(MAX\(version\), 0\)`).
		WillReturnRows(pgxmock.NewRows([]string{"version"}).AddRow(0))
	mock.ExpectExec(`CREATE TABLE IF NOT EXISTS contents`).
		WillReturnResult(pgxmock.NewResult("CREATE", 0))
	mock.ExpectExec(`CREATE TABLE IF NOT EXISTS export_targets`).
		WillReturnResult(pgxmock.NewResult("CREATE", 0))
	mock.ExpectExec(`CREATE INDEX IF NOT EXISTS ix_content_exports_due`).
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

func TestPostgresStoreMigratesVersionOneAtomically(t *testing.T) {
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatal(err)
	}
	defer mock.Close()
	store := newPostgresStoreWithPool(mock)
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT pg_advisory_xact_lock`).WithArgs(migrationLockKey).
		WillReturnResult(pgxmock.NewResult("SELECT", 1))
	mock.ExpectExec(`CREATE TABLE IF NOT EXISTS schema_migrations`).
		WillReturnResult(pgxmock.NewResult("CREATE", 0))
	mock.ExpectQuery(`SELECT COALESCE\(MAX\(version\), 0\)`).
		WillReturnRows(pgxmock.NewRows([]string{"version"}).AddRow(1))
	mock.ExpectExec(`CREATE TABLE IF NOT EXISTS export_targets`).
		WillReturnResult(pgxmock.NewResult("CREATE", 0))
	mock.ExpectExec(`INSERT INTO export_targets`).
		WillReturnResult(pgxmock.NewResult("ALTER", 0))
	mock.ExpectExec(`CREATE INDEX IF NOT EXISTS ix_content_exports_due`).
		WillReturnResult(pgxmock.NewResult("CREATE", 0))
	mock.ExpectExec(`INSERT INTO schema_migrations`).WithArgs(SchemaVersion).
		WillReturnResult(pgxmock.NewResult("INSERT", 1))
	mock.ExpectCommit()
	if err := store.Initialize(context.Background()); err != nil {
		t.Fatal(err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresStoreMigrationFailureRollsBack(t *testing.T) {
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatal(err)
	}
	defer mock.Close()
	store := newPostgresStoreWithPool(mock)
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT pg_advisory_xact_lock`).WithArgs(migrationLockKey).
		WillReturnResult(pgxmock.NewResult("SELECT", 1))
	mock.ExpectExec(`CREATE TABLE IF NOT EXISTS schema_migrations`).
		WillReturnResult(pgxmock.NewResult("CREATE", 0))
	mock.ExpectQuery(`SELECT COALESCE\(MAX\(version\), 0\)`).
		WillReturnRows(pgxmock.NewRows([]string{"version"}).AddRow(1))
	mock.ExpectExec(`CREATE TABLE IF NOT EXISTS export_targets`).
		WillReturnResult(pgxmock.NewResult("CREATE", 0))
	mock.ExpectExec(`INSERT INTO export_targets`).
		WillReturnError(errors.New("injected migration failure"))
	mock.ExpectRollback()
	if err := store.Initialize(context.Background()); err == nil {
		t.Fatal("expected migration failure")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresStoreRejectsNewerSchema(t *testing.T) {
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatal(err)
	}
	defer mock.Close()
	store := newPostgresStoreWithPool(mock)
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT pg_advisory_xact_lock`).WithArgs(migrationLockKey).
		WillReturnResult(pgxmock.NewResult("SELECT", 1))
	mock.ExpectExec(`CREATE TABLE IF NOT EXISTS schema_migrations`).
		WillReturnResult(pgxmock.NewResult("CREATE", 0))
	mock.ExpectQuery(`SELECT COALESCE\(MAX\(version\), 0\)`).
		WillReturnRows(pgxmock.NewRows([]string{"version"}).AddRow(SchemaVersion + 1))
	mock.ExpectRollback()
	if err := store.Initialize(context.Background()); err == nil {
		t.Fatal("expected newer schema error")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresStoreInitializeErrorPaths(t *testing.T) {
	t.Run("create migration table", func(t *testing.T) {
		mock, err := pgxmock.NewPool()
		if err != nil {
			t.Fatal(err)
		}
		defer mock.Close()
		store := newPostgresStoreWithPool(mock)
		mock.ExpectBegin()
		mock.ExpectExec(`SELECT pg_advisory_xact_lock`).WithArgs(migrationLockKey).
			WillReturnResult(pgxmock.NewResult("SELECT", 1))
		mock.ExpectExec(`CREATE TABLE IF NOT EXISTS schema_migrations`).
			WillReturnError(errors.New("create failed"))
		mock.ExpectRollback()
		if err := store.Initialize(context.Background()); err == nil {
			t.Fatal("expected create error")
		}
		if err := mock.ExpectationsWereMet(); err != nil {
			t.Fatal(err)
		}
	})
	t.Run("read version", func(t *testing.T) {
		mock, err := pgxmock.NewPool()
		if err != nil {
			t.Fatal(err)
		}
		defer mock.Close()
		store := newPostgresStoreWithPool(mock)
		mock.ExpectBegin()
		mock.ExpectExec(`SELECT pg_advisory_xact_lock`).WithArgs(migrationLockKey).
			WillReturnResult(pgxmock.NewResult("SELECT", 1))
		mock.ExpectExec(`CREATE TABLE IF NOT EXISTS schema_migrations`).
			WillReturnResult(pgxmock.NewResult("CREATE", 0))
		mock.ExpectQuery(`SELECT COALESCE\(MAX\(version\), 0\)`).
			WillReturnError(errors.New("query failed"))
		mock.ExpectRollback()
		if err := store.Initialize(context.Background()); err == nil {
			t.Fatal("expected version query error")
		}
		if err := mock.ExpectationsWereMet(); err != nil {
			t.Fatal(err)
		}
	})
	t.Run("create fresh schema", func(t *testing.T) {
		mock, err := pgxmock.NewPool()
		if err != nil {
			t.Fatal(err)
		}
		defer mock.Close()
		store := newPostgresStoreWithPool(mock)
		mock.ExpectBegin()
		mock.ExpectExec(`SELECT pg_advisory_xact_lock`).WithArgs(migrationLockKey).
			WillReturnResult(pgxmock.NewResult("SELECT", 1))
		mock.ExpectExec(`CREATE TABLE IF NOT EXISTS schema_migrations`).
			WillReturnResult(pgxmock.NewResult("CREATE", 0))
		mock.ExpectQuery(`SELECT COALESCE\(MAX\(version\), 0\)`).
			WillReturnRows(pgxmock.NewRows([]string{"version"}).AddRow(0))
		mock.ExpectExec(`CREATE TABLE IF NOT EXISTS contents`).
			WillReturnError(errors.New("schema failed"))
		mock.ExpectRollback()
		if err := store.Initialize(context.Background()); err == nil {
			t.Fatal("expected fresh schema error")
		}
		if err := mock.ExpectationsWereMet(); err != nil {
			t.Fatal(err)
		}
	})
	t.Run("record version", func(t *testing.T) {
		mock, err := pgxmock.NewPool()
		if err != nil {
			t.Fatal(err)
		}
		defer mock.Close()
		store := newPostgresStoreWithPool(mock)
		mock.ExpectBegin()
		mock.ExpectExec(`SELECT pg_advisory_xact_lock`).WithArgs(migrationLockKey).
			WillReturnResult(pgxmock.NewResult("SELECT", 1))
		mock.ExpectExec(`CREATE TABLE IF NOT EXISTS schema_migrations`).
			WillReturnResult(pgxmock.NewResult("CREATE", 0))
		mock.ExpectQuery(`SELECT COALESCE\(MAX\(version\), 0\)`).
			WillReturnRows(pgxmock.NewRows([]string{"version"}).AddRow(1))
		mock.ExpectExec(`CREATE TABLE IF NOT EXISTS export_targets`).
			WillReturnResult(pgxmock.NewResult("CREATE", 0))
		mock.ExpectExec(`INSERT INTO export_targets`).
			WillReturnResult(pgxmock.NewResult("ALTER", 0))
		mock.ExpectExec(`CREATE INDEX IF NOT EXISTS ix_content_exports_due`).
			WillReturnResult(pgxmock.NewResult("CREATE", 0))
		mock.ExpectExec(`INSERT INTO schema_migrations`).WithArgs(SchemaVersion).
			WillReturnError(errors.New("record failed"))
		mock.ExpectRollback()
		if err := store.Initialize(context.Background()); err == nil {
			t.Fatal("expected record error")
		}
		if err := mock.ExpectationsWereMet(); err != nil {
			t.Fatal(err)
		}
	})
}

func TestPostgresStoreRegistersAndBackfillsTargets(t *testing.T) {
	for _, test := range []struct {
		name    string
		enabled bool
	}{
		{name: "enabled", enabled: true},
		{name: "disabled", enabled: false},
	} {
		t.Run(test.name, func(t *testing.T) {
			mock, err := pgxmock.NewPool()
			if err != nil {
				t.Fatal(err)
			}
			defer mock.Close()
			store := newPostgresStoreWithPool(mock)
			mock.ExpectBegin()
			mock.ExpectExec(`INSERT INTO export_targets`).
				WithArgs("target", test.enabled).
				WillReturnResult(pgxmock.NewResult("INSERT", 1))
			if test.enabled {
				mock.ExpectExec(`INSERT INTO content_exports`).
					WithArgs("target", SyncPending).
					WillReturnResult(pgxmock.NewResult("INSERT", 2))
			}
			mock.ExpectCommit()
			if err := store.RegisterTarget(context.Background(), "target", test.enabled); err != nil {
				t.Fatal(err)
			}
			if err := mock.ExpectationsWereMet(); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestPostgresStoreRegisterTargetErrorPaths(t *testing.T) {
	tests := []struct {
		name  string
		setup func(pgxmock.PgxPoolIface)
	}{
		{
			name: "begin",
			setup: func(mock pgxmock.PgxPoolIface) {
				mock.ExpectBegin().WillReturnError(errors.New("begin failed"))
			},
		},
		{
			name: "register",
			setup: func(mock pgxmock.PgxPoolIface) {
				mock.ExpectBegin()
				mock.ExpectExec(`INSERT INTO export_targets`).WithArgs("target", true).
					WillReturnError(errors.New("register failed"))
				mock.ExpectRollback()
			},
		},
		{
			name: "backfill",
			setup: func(mock pgxmock.PgxPoolIface) {
				mock.ExpectBegin()
				mock.ExpectExec(`INSERT INTO export_targets`).WithArgs("target", true).
					WillReturnResult(pgxmock.NewResult("INSERT", 1))
				mock.ExpectExec(`INSERT INTO content_exports`).WithArgs("target", SyncPending).
					WillReturnError(errors.New("backfill failed"))
				mock.ExpectRollback()
			},
		},
		{
			name: "commit",
			setup: func(mock pgxmock.PgxPoolIface) {
				mock.ExpectBegin()
				mock.ExpectExec(`INSERT INTO export_targets`).WithArgs("target", true).
					WillReturnResult(pgxmock.NewResult("INSERT", 1))
				mock.ExpectExec(`INSERT INTO content_exports`).WithArgs("target", SyncPending).
					WillReturnResult(pgxmock.NewResult("INSERT", 1))
				mock.ExpectCommit().WillReturnError(errors.New("commit failed"))
				mock.ExpectRollback()
			},
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			mock, err := pgxmock.NewPool()
			if err != nil {
				t.Fatal(err)
			}
			defer mock.Close()
			test.setup(mock)
			store := newPostgresStoreWithPool(mock)
			if err := store.RegisterTarget(context.Background(), "target", true); err == nil {
				t.Fatal("expected registration error")
			}
			if err := mock.ExpectationsWereMet(); err != nil {
				t.Fatal(err)
			}
		})
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

func TestPostgresStoreListContentsUsesParameterizedCanonicalQuery(t *testing.T) {
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatal(err)
	}
	defer mock.Close()
	store := newPostgresStoreWithPool(mock)
	after := time.Date(2026, 8, 19, 9, 0, 0, 0, time.UTC)
	before := time.Date(2026, 8, 19, 12, 0, 0, 0, time.UTC)
	cursorTime := time.Date(2026, 8, 19, 11, 0, 0, 0, time.UTC)
	rows := pgxmock.NewRows([]string{
		"content_id",
		"title",
		"link",
		"summary",
		"published",
		"author",
		"keywords_json",
		"tags_json",
		"scraper_name",
		"created_at",
	}).
		AddRow("one", "Title one", "https://example.com/one", "Summary", "source-time", "Alice", `["k"]`, `["tag"]`, "Feed", cursorTime).
		AddRow("two", "Title two", "https://example.com/two", "Summary", "source-time", nil, `[]`, `[]`, nil, cursorTime.Add(-time.Minute)).
		AddRow("three", "Title three", "https://example.com/three", "Summary", "source-time", nil, `[]`, `[]`, nil, cursorTime.Add(-2*time.Minute))
	mock.ExpectQuery(`SELECT content_id, title, link, summary, published, author,\s+keywords_json, tags_json, scraper_name, created_at\s+FROM contents`).
		WithArgs("Feed", after, before, cursorTime, "cursor-id", []string{"tag"}, 3).
		WillReturnRows(rows)
	page, err := store.ListContents(context.Background(), ContentListOptions{
		Limit:           2,
		ScraperName:     "Feed",
		Tags:            []string{"tag"},
		CollectedAfter:  &after,
		CollectedBefore: &before,
		Cursor: &ContentListCursor{
			CreatedAt: cursorTime,
			ContentID: "cursor-id",
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(page.Items) != 2 || page.Items[0].ContentID != "one" {
		t.Fatalf("page = %#v", page)
	}
	if page.NextCursor == nil ||
		!page.NextCursor.CreatedAt.Equal(page.Items[1].CollectedAt) ||
		page.NextCursor.ContentID != "two" {
		t.Fatalf("next cursor = %#v", page.NextCursor)
	}
	if page.Items[0].Author == nil || *page.Items[0].Author != "Alice" ||
		!slices.Equal(page.Items[0].Keywords, []string{"k"}) ||
		!slices.Equal(page.Items[0].Tags, []string{"tag"}) {
		t.Fatalf("decoded metadata = %#v", page.Items[0])
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresStoreListContentsNoNextCursorAndErrors(t *testing.T) {
	t.Run("no next cursor", func(t *testing.T) {
		mock, err := pgxmock.NewPool()
		if err != nil {
			t.Fatal(err)
		}
		defer mock.Close()
		store := newPostgresStoreWithPool(mock)
		collectedAt := time.Date(2026, 8, 19, 10, 0, 0, 0, time.UTC)
		rows := pgxmock.NewRows([]string{
			"content_id",
			"title",
			"link",
			"summary",
			"published",
			"author",
			"keywords_json",
			"tags_json",
			"scraper_name",
			"created_at",
		}).AddRow("one", "Title", "https://example.com/one", "Summary", "source-time", nil, `[]`, `[]`, nil, collectedAt)
		mock.ExpectQuery(`FROM contents`).
			WithArgs(2).
			WillReturnRows(rows)
		page, err := store.ListContents(context.Background(), ContentListOptions{Limit: 1})
		if err != nil {
			t.Fatal(err)
		}
		if len(page.Items) != 1 || page.NextCursor != nil {
			t.Fatalf("page = %#v", page)
		}
		if err := mock.ExpectationsWereMet(); err != nil {
			t.Fatal(err)
		}
	})
	t.Run("query error", func(t *testing.T) {
		mock, err := pgxmock.NewPool()
		if err != nil {
			t.Fatal(err)
		}
		defer mock.Close()
		store := newPostgresStoreWithPool(mock)
		mock.ExpectQuery(`FROM contents`).
			WithArgs(1).
			WillReturnError(errors.New("database failed"))
		if _, err := store.ListContents(context.Background(), ContentListOptions{}); err == nil {
			t.Fatal("expected query error")
		}
		if err := mock.ExpectationsWereMet(); err != nil {
			t.Fatal(err)
		}
	})
	t.Run("zero limit", func(t *testing.T) {
		mock, err := pgxmock.NewPool()
		if err != nil {
			t.Fatal(err)
		}
		defer mock.Close()
		store := newPostgresStoreWithPool(mock)
		rows := pgxmock.NewRows([]string{
			"content_id",
			"title",
			"link",
			"summary",
			"published",
			"author",
			"keywords_json",
			"tags_json",
			"scraper_name",
			"created_at",
		}).AddRow("one", "Title", "https://example.com/one", "Summary", "source-time", nil, `[]`, `[]`, nil, time.Now())
		mock.ExpectQuery(`FROM contents`).
			WithArgs(1).
			WillReturnRows(rows)
		page, err := store.ListContents(context.Background(), ContentListOptions{})
		if err != nil {
			t.Fatal(err)
		}
		if len(page.Items) != 0 || page.NextCursor != nil {
			t.Fatalf("page = %#v", page)
		}
		if err := mock.ExpectationsWereMet(); err != nil {
			t.Fatal(err)
		}
	})
	t.Run("decode error", func(t *testing.T) {
		mock, err := pgxmock.NewPool()
		if err != nil {
			t.Fatal(err)
		}
		defer mock.Close()
		store := newPostgresStoreWithPool(mock)
		rows := pgxmock.NewRows([]string{
			"content_id",
			"title",
			"link",
			"summary",
			"published",
			"author",
			"keywords_json",
			"tags_json",
			"scraper_name",
			"created_at",
		}).AddRow("one", "Title", "https://example.com/one", "Summary", "source-time", nil, `bad`, `[]`, nil, time.Now())
		mock.ExpectQuery(`FROM contents`).
			WithArgs(2).
			WillReturnRows(rows)
		if _, err := store.ListContents(context.Background(), ContentListOptions{Limit: 1}); err == nil {
			t.Fatal("expected decode error")
		}
		if err := mock.ExpectationsWereMet(); err != nil {
			t.Fatal(err)
		}
	})
}

func TestBuildListContentsQueryExcludesExporterInternals(t *testing.T) {
	query, args := buildListContentsQuery(ContentListOptions{
		Limit:       20,
		ScraperName: "Feed",
		Tags:        []string{"tag"},
	})
	for _, forbidden := range []string{"content_exports", "export_targets", "notion", "lease", "error"} {
		if strings.Contains(query, forbidden) {
			t.Fatalf("query exposes %q: %s", forbidden, query)
		}
	}
	for _, placeholder := range []string{"$1", "$2", "$3"} {
		if !strings.Contains(query, placeholder) {
			t.Fatalf("query missing %s: %s", placeholder, query)
		}
	}
	if len(args) != 3 {
		t.Fatalf("args = %#v", args)
	}
}

func TestBuildListContentsQueryBoundsNonPositiveLimit(t *testing.T) {
	query, args := buildListContentsQuery(ContentListOptions{Limit: -2})
	if !strings.Contains(query, "LIMIT $1") || len(args) != 1 || args[0] != 1 {
		t.Fatalf("query=%q args=%#v", query, args)
	}
}

func TestDecodeStringSliceNormalizesJSONNull(t *testing.T) {
	var values []string
	if err := decodeStringSlice("null", &values, "tags", "one"); err != nil {
		t.Fatal(err)
	}
	if values == nil || len(values) != 0 {
		t.Fatalf("values = %#v, want non-nil empty slice", values)
	}
}

func TestPostgresStoreGetContent(t *testing.T) {
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatal(err)
	}
	defer mock.Close()
	store := newPostgresStoreWithPool(mock)
	collectedAt := time.Date(2026, 8, 19, 10, 0, 0, 0, time.UTC)
	rows := pgxmock.NewRows([]string{
		"content_id",
		"title",
		"link",
		"summary",
		"content",
		"published",
		"author",
		"keywords_json",
		"tags_json",
		"scraper_name",
		"created_at",
	}).AddRow("one", "Title", "https://example.com/one", "Summary", "Body", "source-time", "Alice", `["k"]`, `["tag"]`, "Feed", collectedAt)
	mock.ExpectQuery(`SELECT content_id, title, link, summary, content, published, author`).
		WithArgs("one").
		WillReturnRows(rows)
	record, ok, err := store.GetContent(context.Background(), "one")
	if err != nil || !ok {
		t.Fatalf("GetContent() = %#v, %t, %v", record, ok, err)
	}
	if record.Content != "Body" || record.ContentID != "one" ||
		record.Author == nil || *record.Author != "Alice" ||
		!record.CollectedAt.Equal(collectedAt) {
		t.Fatalf("record = %#v", record)
	}
	mock.ExpectQuery(`SELECT content_id, title, link, summary, content, published, author`).
		WithArgs("missing").
		WillReturnRows(pgxmock.NewRows([]string{
			"content_id",
			"title",
			"link",
			"summary",
			"content",
			"published",
			"author",
			"keywords_json",
			"tags_json",
			"scraper_name",
			"created_at",
		}))
	_, ok, err = store.GetContent(context.Background(), "missing")
	if err != nil || ok {
		t.Fatalf("missing = %t, %v", ok, err)
	}
	mock.ExpectQuery(`SELECT content_id, title, link, summary, content, published, author`).
		WithArgs("broken").
		WillReturnError(errors.New("database failed"))
	_, _, err = store.GetContent(context.Background(), "broken")
	if err == nil {
		t.Fatal("expected database error")
	}
	mock.ExpectQuery(`SELECT content_id, title, link, summary, content, published, author`).
		WithArgs("bad-json").
		WillReturnRows(pgxmock.NewRows([]string{
			"content_id",
			"title",
			"link",
			"summary",
			"content",
			"published",
			"author",
			"keywords_json",
			"tags_json",
			"scraper_name",
			"created_at",
		}).AddRow("bad-json", "Title", "https://example.com/bad-json", "Summary", "Body", "source-time", nil, `bad`, `[]`, nil, collectedAt))
	_, _, err = store.GetContent(context.Background(), "bad-json")
	if err == nil {
		t.Fatal("expected decode error")
	}
	mock.ExpectQuery(`SELECT content_id, title, link, summary, content, published, author`).
		WithArgs("bad-tags").
		WillReturnRows(pgxmock.NewRows([]string{
			"content_id",
			"title",
			"link",
			"summary",
			"content",
			"published",
			"author",
			"keywords_json",
			"tags_json",
			"scraper_name",
			"created_at",
		}).AddRow("bad-tags", "Title", "https://example.com/bad-tags", "Summary", "Body", "source-time", nil, `[]`, `bad`, nil, collectedAt))
	_, _, err = store.GetContent(context.Background(), "bad-tags")
	if err == nil {
		t.Fatal("expected tags decode error")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
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
	mock.ExpectExec(`INSERT INTO contents`).WithArgs(anyArgs(20)...).WillReturnResult(pgxmock.NewResult("INSERT", 1))
	mock.ExpectExec(`INSERT INTO content_exports`).WithArgs(SyncPending, []string{"one", "two"}).WillReturnResult(pgxmock.NewResult("INSERT", 1))
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
		WithArgs(anyArgs(10)...).
		WillReturnResult(pgxmock.NewResult("INSERT", 1))
	mock.ExpectExec(`INSERT INTO contents`).
		WithArgs(anyArgs(10)...).
		WillReturnResult(pgxmock.NewResult("INSERT", 1))
	mock.ExpectExec(`INSERT INTO content_exports`).
		WithArgs(SyncPending, []string{"one", "two"}).
		WillReturnResult(pgxmock.NewResult("INSERT", 2))
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

func TestPostgresStoreClaimReturnsRows(t *testing.T) {
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatalf("pgxmock.NewPool() error = %v", err)
	}
	defer mock.Close()
	store := newPostgresStoreWithPool(mock)
	rows := pgxmock.NewRows([]string{"content_id", "title", "link", "summary", "content", "published", "author", "keywords_json", "tags_json", "scraper_name"}).
		AddRow("one", "Title", "https://example.com/one", "Summary", "Body", "2026-08-18T11:00:00Z", "Alice", `["k"]`, `["t"]`, "Feed")
	mock.ExpectQuery(`WITH due AS`).WithArgs("notion", SyncPending, SyncRetry, 3, SyncProcessing, 1, "worker-1", 60).WillReturnRows(rows)

	claimed, err := store.Claim(context.Background(), "notion", "worker-1", 1, time.Minute, 3)
	if err != nil {
		t.Fatalf("Claim() error = %v", err)
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
	mock.ExpectQuery(`SELECT attempts`).WithArgs("notion", "one", "worker-1", SyncProcessing).WillReturnRows(pgxmock.NewRows([]string{"attempts"}).AddRow(0))
	mock.ExpectExec(`UPDATE content_exports`).WithArgs(1, SyncRetry, "temporary", 60, "notion", "one", "worker-1", SyncProcessing, 0).WillReturnResult(pgxmock.NewResult("UPDATE", 1))
	updated, err := store.Fail(context.Background(), "notion", "one", "worker-1", "temporary", 3)
	if err != nil {
		t.Fatalf("Fail() error = %v", err)
	}
	if !updated {
		t.Fatalf("Fail() = false")
	}
	countRows := pgxmock.NewRows([]string{"status", "count"}).AddRow(SyncRetry, int64(2)).AddRow(SyncSynced, int64(1))
	mock.ExpectQuery(`SELECT status, COUNT\(content_id\)`).WillReturnRows(countRows)
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
	mock.ExpectExec(`UPDATE content_exports`).
		WithArgs(60, "notion", "one", "worker-1", SyncProcessing).
		WillReturnResult(pgxmock.NewResult("UPDATE", 1))
	renewed, err := store.Renew(
		context.Background(),
		"notion",
		"one",
		"worker-1",
		time.Minute,
	)
	if err != nil || !renewed {
		t.Fatalf("unexpected renew result: %t, %v", renewed, err)
	}
	mock.ExpectExec(`UPDATE content_exports`).
		WithArgs(SyncSynced, "notion", "one", "worker-1", SyncProcessing).
		WillReturnResult(pgxmock.NewResult("UPDATE", 1))
	marked, err := store.Complete(context.Background(), "notion", "one", "worker-1")
	if err != nil || !marked {
		t.Fatalf("unexpected mark result: %t, %v", marked, err)
	}
	mock.ExpectQuery(`SELECT attempts`).
		WithArgs("notion", "missing", "worker-1", SyncProcessing).
		WillReturnRows(pgxmock.NewRows([]string{"attempts"}))
	marked, err = store.Fail(
		context.Background(),
		"notion",
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
