package storage

import (
	"context"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"strings"
	"testing"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/config"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
	"github.com/jackc/pgx/v5"
	pgxmock "github.com/pashagolub/pgxmock/v4"
)

func TestPostgresStoreInitializeFaults(t *testing.T) {
	tests := []struct {
		name  string
		setup func(pgxmock.PgxPoolIface)
	}{
		{"begin", func(m pgxmock.PgxPoolIface) {
			m.ExpectBegin().WillReturnError(errors.New("begin"))
		}},
		{"lock", func(m pgxmock.PgxPoolIface) {
			m.ExpectBegin()
			m.ExpectExec(`SELECT pg_advisory_xact_lock`).WithArgs(migrationLockKey).
				WillReturnError(errors.New("lock"))
			m.ExpectRollback()
		}},
		{"fresh record", func(m pgxmock.PgxPoolIface) {
			expectInitializePrefix(m, 0)
			expectFreshSchema(m, 2)
			m.ExpectExec(`INSERT INTO schema_migrations`).WithArgs(SchemaVersion).
				WillReturnError(errors.New("record"))
			m.ExpectRollback()
		}},
		{"v1 migration second statement", func(m pgxmock.PgxPoolIface) {
			expectInitializePrefix(m, 1)
			m.ExpectExec(`CREATE TABLE IF NOT EXISTS export_targets`).WillReturnResult(pgxmock.NewResult("CREATE", 0))
			m.ExpectExec(`INSERT INTO export_targets`).WillReturnError(errors.New("migration"))
			m.ExpectRollback()
		}},
		{"v2 migration", func(m pgxmock.PgxPoolIface) {
			expectInitializePrefix(m, 2)
			expectNoLegacyStringArrayNormalization(m)
			m.ExpectExec(`DROP INDEX IF EXISTS ix_content_exports_due`).WillReturnError(errors.New("migration"))
			m.ExpectRollback()
		}},
		{"commit", func(m pgxmock.PgxPoolIface) {
			expectInitializePrefix(m, 3)
			m.ExpectCommit().WillReturnError(errors.New("commit"))
			m.ExpectRollback()
		}},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			mock, err := pgxmock.NewPool()
			if err != nil {
				t.Fatal(err)
			}
			defer mock.Close()
			test.setup(mock)
			if err := newPostgresStoreWithPool(mock).Initialize(context.Background()); err == nil {
				t.Fatal("expected initialization error")
			}
			if err := mock.ExpectationsWereMet(); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestPostgresStoreInitializeVersionTwoBackfillAndIndexFaults(t *testing.T) {
	for _, test := range []struct {
		name string
		fail string
	}{
		{"backfill", "UPDATE contents AS content"},
		{"content indexes", `CREATE INDEX IF NOT EXISTS ix_contents_collected`},
		{"export indexes", `CREATE INDEX IF NOT EXISTS ix_content_exports_due`},
	} {
		t.Run(test.name, func(t *testing.T) {
			mock, err := pgxmock.NewPool()
			if err != nil {
				t.Fatal(err)
			}
			defer mock.Close()
			expectInitializePrefix(mock, 2)
			expectNoLegacyStringArrayNormalization(mock)
			mock.ExpectExec(`DROP INDEX IF EXISTS ix_content_exports_due`).
				WillReturnResult(pgxmock.NewResult("ALTER", 0))
			mock.ExpectExec(`DECLARE octopus_published_v2`).
				WillReturnResult(pgxmock.NewResult("DECLARE", 0))
			mock.ExpectQuery(`FETCH FORWARD 512 FROM octopus_published_v2`).
				WillReturnRows(pgxmock.NewRows([]string{"content_id", "published"}).
					AddRow("one", "2026-08-18T11:00:00Z"))
			if test.fail == "UPDATE contents AS content" {
				mock.ExpectExec(`UPDATE contents AS content`).
					WithArgs("one", pgxmock.AnyArg()).
					WillReturnError(errors.New("backfill"))
			} else {
				mock.ExpectExec(`UPDATE contents AS content`).
					WithArgs("one", pgxmock.AnyArg()).
					WillReturnResult(pgxmock.NewResult("UPDATE", 1))
				mock.ExpectExec(`CLOSE octopus_published_v2`).
					WillReturnResult(pgxmock.NewResult("CLOSE", 0))
				if test.fail == `CREATE INDEX IF NOT EXISTS ix_contents_collected` {
					mock.ExpectExec(`CREATE INDEX IF NOT EXISTS ix_contents_collected`).
						WillReturnError(errors.New("index"))
				} else {
					mock.ExpectExec(`CREATE INDEX IF NOT EXISTS ix_contents_collected`).
						WillReturnResult(pgxmock.NewResult("CREATE", 0))
					mock.ExpectExec(`CREATE INDEX IF NOT EXISTS ix_content_exports_due`).
						WillReturnError(errors.New("index"))
				}
			}
			mock.ExpectRollback()
			if err := newPostgresStoreWithPool(mock).Initialize(context.Background()); err == nil {
				t.Fatal("expected version two migration error")
			}
			if err := mock.ExpectationsWereMet(); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestBackfillPublishedAt(t *testing.T) {
	t.Run("updates parsed rows", func(t *testing.T) {
		mock, err := pgxmock.NewPool()
		if err != nil {
			t.Fatal(err)
		}
		defer mock.Close()
		mock.ExpectBegin()
		mock.ExpectExec(`DECLARE octopus_published_v2`).WillReturnResult(pgxmock.NewResult("DECLARE", 0))
		mock.ExpectQuery(`FETCH FORWARD 512`).WillReturnRows(
			pgxmock.NewRows([]string{"content_id", "published"}).
				AddRow("one", "2026-08-18T11:00:00Z").
				AddRow("bad", "not-a-date"),
		)
		mock.ExpectExec(`UPDATE contents AS content`).WithArgs("one", pgxmock.AnyArg()).
			WillReturnResult(pgxmock.NewResult("UPDATE", 1))
		mock.ExpectExec(`CLOSE octopus_published_v2`).WillReturnResult(pgxmock.NewResult("CLOSE", 0))
		if err := backfillPublishedAt(context.Background(), mustBegin(mock)); err != nil {
			t.Fatal(err)
		}
		if err := mock.ExpectationsWereMet(); err != nil {
			t.Fatal(err)
		}
	})
	t.Run("multiple chunks", func(t *testing.T) {
		mock, err := pgxmock.NewPool()
		if err != nil {
			t.Fatal(err)
		}
		defer mock.Close()
		mock.ExpectBegin()
		mock.ExpectExec(`DECLARE octopus_published_v2`).
			WillReturnResult(pgxmock.NewResult("DECLARE", 0))
		rows := pgxmock.NewRows([]string{"content_id", "published"})
		for index := range defaultChunkSize {
			rows.AddRow("content-"+fmt.Sprint(index), "2026-08-18T11:00:00Z")
		}
		mock.ExpectQuery(`FETCH FORWARD 512`).WillReturnRows(rows)
		mock.ExpectExec(`UPDATE contents AS content`).WithArgs(anyArgs(defaultChunkSize * 2)...).
			WillReturnResult(pgxmock.NewResult("UPDATE", defaultChunkSize))
		mock.ExpectQuery(`FETCH FORWARD 512`).WillReturnRows(
			pgxmock.NewRows([]string{"content_id", "published"}),
		)
		mock.ExpectExec(`CLOSE octopus_published_v2`).
			WillReturnResult(pgxmock.NewResult("CLOSE", 0))
		if err := backfillPublishedAt(context.Background(), mustBegin(mock)); err != nil {
			t.Fatal(err)
		}
		if err := mock.ExpectationsWereMet(); err != nil {
			t.Fatal(err)
		}
	})
	tests := []struct {
		name  string
		setup func(pgxmock.PgxPoolIface)
	}{
		{"declare", func(m pgxmock.PgxPoolIface) {
			m.ExpectBegin()
			m.ExpectExec(`DECLARE octopus_published_v2`).WillReturnError(errors.New("declare"))
		}},
		{"fetch", func(m pgxmock.PgxPoolIface) {
			m.ExpectBegin()
			m.ExpectExec(`DECLARE octopus_published_v2`).WillReturnResult(pgxmock.NewResult("DECLARE", 0))
			m.ExpectQuery(`FETCH FORWARD 512`).WillReturnError(errors.New("fetch"))
		}},
		{"scan", func(m pgxmock.PgxPoolIface) {
			m.ExpectBegin()
			m.ExpectExec(`DECLARE octopus_published_v2`).WillReturnResult(pgxmock.NewResult("DECLARE", 0))
			m.ExpectQuery(`FETCH FORWARD 512`).WillReturnRows(
				pgxmock.NewRows([]string{"content_id", "published"}).AddRow("one", nil),
			)
		}},
		{"iterate", func(m pgxmock.PgxPoolIface) {
			m.ExpectBegin()
			m.ExpectExec(`DECLARE octopus_published_v2`).WillReturnResult(pgxmock.NewResult("DECLARE", 0))
			m.ExpectQuery(`FETCH FORWARD 512`).WillReturnRows(
				pgxmock.NewRows([]string{"content_id", "published"}).
					AddRow("one", "2026-08-18T11:00:00Z").
					RowError(1, errors.New("iterate")),
			)
		}},
		{"backfill update", func(m pgxmock.PgxPoolIface) {
			m.ExpectBegin()
			m.ExpectExec(`DECLARE octopus_published_v2`).WillReturnResult(pgxmock.NewResult("DECLARE", 0))
			m.ExpectQuery(`FETCH FORWARD 512`).WillReturnRows(
				pgxmock.NewRows([]string{"content_id", "published"}).AddRow("one", "2026-08-18T11:00:00Z"),
			)
			m.ExpectExec(`UPDATE contents AS content`).WithArgs("one", pgxmock.AnyArg()).
				WillReturnError(errors.New("update"))
		}},
		{"close", func(m pgxmock.PgxPoolIface) {
			m.ExpectBegin()
			m.ExpectExec(`DECLARE octopus_published_v2`).WillReturnResult(pgxmock.NewResult("DECLARE", 0))
			m.ExpectQuery(`FETCH FORWARD 512`).WillReturnRows(pgxmock.NewRows([]string{"content_id", "published"}))
			m.ExpectExec(`CLOSE octopus_published_v2`).WillReturnError(errors.New("close"))
		}},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			mock, err := pgxmock.NewPool()
			if err != nil {
				t.Fatal(err)
			}
			defer mock.Close()
			test.setup(mock)
			if err := backfillPublishedAt(context.Background(), mustBegin(mock)); err == nil {
				t.Fatal("expected backfill error")
			}
			if err := mock.ExpectationsWereMet(); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestPostgresStoreOperationFaults(t *testing.T) {
	t.Run("existing IDs", func(t *testing.T) {
		for _, name := range []string{"query", "scan", "iterate"} {
			mock, err := pgxmock.NewPool()
			if err != nil {
				t.Fatal(err)
			}
			store := newPostgresStoreWithPool(mock)
			switch name {
			case "query":
				mock.ExpectQuery(`SELECT content_id`).WillReturnError(errors.New("query"))
			case "scan":
				mock.ExpectQuery(`SELECT content_id`).WillReturnRows(
					pgxmock.NewRows([]string{"content_id"}).AddRow(nil),
				)
			case "iterate":
				mock.ExpectQuery(`SELECT content_id`).WillReturnRows(
					pgxmock.NewRows([]string{"content_id"}).RowError(0, errors.New("iterate")),
				)
			}
			if _, err := store.ExistingContentIDs(context.Background(), []string{"one"}); err == nil {
				t.Fatalf("%s: expected error", name)
			}
			mock.Close()
		}
	})

	t.Run("store contents", func(t *testing.T) {
		target := []ContentSource{{ContentID: "one", ScraperID: "feed", ScraperName: "Feed"}}
		tests := []struct {
			name  string
			setup func(pgxmock.PgxPoolIface)
		}{
			{"begin", func(m pgxmock.PgxPoolIface) { m.ExpectBegin().WillReturnError(errors.New("begin")) }},
			{"lock", func(m pgxmock.PgxPoolIface) {
				m.ExpectBegin()
				m.ExpectExec(`SELECT pg_advisory_xact_lock_shared`).
					WithArgs(contentTargetLockKey).
					WillReturnError(errors.New("lock"))
				m.ExpectRollback()
			}},
			{"insert", func(m pgxmock.PgxPoolIface) {
				m.ExpectBegin()
				expectContentStoreLock(m)
				m.ExpectExec(`INSERT INTO contents`).WithArgs(anyArgs(12)...).
					WillReturnError(errors.New("insert"))
				m.ExpectRollback()
			}},
			{"sources", func(m pgxmock.PgxPoolIface) {
				m.ExpectBegin()
				expectContentStoreLock(m)
				m.ExpectExec(`INSERT INTO contents`).WithArgs(anyArgs(12)...).
					WillReturnResult(pgxmock.NewResult("INSERT", 1))
				m.ExpectExec(`WITH observed`).WithArgs(anyArgs(4)...).
					WillReturnError(errors.New("sources"))
				m.ExpectRollback()
			}},
			{"primary", func(m pgxmock.PgxPoolIface) {
				m.ExpectBegin()
				expectContentStoreLock(m)
				m.ExpectExec(`INSERT INTO contents`).WithArgs(anyArgs(12)...).
					WillReturnResult(pgxmock.NewResult("INSERT", 1))
				m.ExpectExec(`WITH observed`).WithArgs(anyArgs(4)...).
					WillReturnResult(pgxmock.NewResult("INSERT", 1))
				m.ExpectExec(`UPDATE contents AS content`).
					WithArgs([]string{"one"}).
					WillReturnError(errors.New("primary"))
				m.ExpectRollback()
			}},
			{"exports", func(m pgxmock.PgxPoolIface) {
				m.ExpectBegin()
				expectContentStoreLock(m)
				m.ExpectExec(`INSERT INTO contents`).WithArgs(anyArgs(12)...).
					WillReturnResult(pgxmock.NewResult("INSERT", 1))
				m.ExpectExec(`INSERT INTO content_exports`).WithArgs(anyArgs(2)...).
					WillReturnError(errors.New("exports"))
				m.ExpectRollback()
			}},
			{"commit", func(m pgxmock.PgxPoolIface) {
				m.ExpectBegin()
				expectContentStoreLock(m)
				m.ExpectExec(`INSERT INTO contents`).WithArgs(anyArgs(12)...).
					WillReturnResult(pgxmock.NewResult("INSERT", 1))
				m.ExpectExec(`INSERT INTO content_exports`).WithArgs(anyArgs(2)...).
					WillReturnResult(pgxmock.NewResult("INSERT", 1))
				m.ExpectCommit().WillReturnError(errors.New("commit"))
				m.ExpectRollback()
			}},
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
				sources := target
				if test.name == "begin" || test.name == "lock" || test.name == "insert" || test.name == "sources" || test.name == "primary" || test.name == "exports" || test.name == "commit" {
					if test.name != "sources" && test.name != "primary" {
						sources = nil
					}
				}
				if _, err := store.StoreContents(context.Background(), []content.Content{testContent("one")}, sources); err == nil {
					t.Fatal("expected store error")
				}
				if err := mock.ExpectationsWereMet(); err != nil {
					t.Fatal(err)
				}
			})
		}
		if _, err := newPostgresStoreWithPool(nil).StoreContents(
			context.Background(), []content.Content{{ContentID: "one"}}, []ContentSource{{}},
		); err == nil {
			t.Fatal("expected source validation error")
		}
	})

	t.Run("claim and lifecycle", func(t *testing.T) {
		mock, err := pgxmock.NewPool()
		if err != nil {
			t.Fatal(err)
		}
		defer mock.Close()
		store := newPostgresStoreWithPool(mock)
		mock.ExpectQuery(`WITH due AS`).WithArgs("target", 1, 1, "worker", 60).
			WillReturnError(errors.New("claim"))
		if _, err := store.Claim(context.Background(), "target", "worker", 1, time.Minute, 1); err == nil {
			t.Fatal("expected claim error")
		}
		mock.ExpectQuery(`WITH due AS`).WithArgs("target", 1, 1, "worker", 60).WillReturnRows(
			pgxmock.NewRows(claimedContentColumns()).AddRow("one", "t", "l", "s", "c", "p", nil, `bad`, `[]`, nil, nil),
		)
		if _, err := store.Claim(context.Background(), "target", "worker", 1, time.Minute, 1); err == nil {
			t.Fatal("expected claim scan error")
		}
		mock.ExpectExec(`UPDATE content_exports`).WithArgs(60, "t", "c", "w", SyncProcessing).
			WillReturnError(errors.New("renew"))
		if _, err := store.Renew(context.Background(), "t", "c", "w", time.Minute); err == nil {
			t.Fatal("expected renew error")
		}
		mock.ExpectExec(`UPDATE content_exports`).WithArgs(60, "t", "c", "w", SyncProcessing).
			WillReturnResult(pgxmock.NewResult("UPDATE", 0))
		if ok, err := store.Renew(context.Background(), "t", "c", "w", time.Minute); err != nil || ok {
			t.Fatalf("renew result = %t, %v", ok, err)
		}
		mock.ExpectExec(`UPDATE content_exports`).WithArgs(SyncSynced, "t", "c", "w", SyncProcessing).
			WillReturnError(errors.New("complete"))
		if _, err := store.Complete(context.Background(), "t", "c", "w"); err == nil {
			t.Fatal("expected complete error")
		}
		mock.ExpectExec(`UPDATE content_exports`).WithArgs(SyncSynced, "t", "c", "w", SyncProcessing).
			WillReturnResult(pgxmock.NewResult("UPDATE", 0))
		if ok, err := store.Complete(context.Background(), "t", "c", "w"); err != nil || ok {
			t.Fatalf("complete result = %t, %v", ok, err)
		}
		mock.ExpectQuery(`SELECT attempts`).WithArgs("t", "c", "w", SyncProcessing).
			WillReturnError(errors.New("attempts"))
		if _, err := store.Fail(context.Background(), "t", "c", "w", "e", 1); err == nil {
			t.Fatal("expected attempts error")
		}
		mock.ExpectQuery(`SELECT attempts`).WithArgs("t", "c", "w", SyncProcessing).
			WillReturnRows(pgxmock.NewRows([]string{"attempts"}).AddRow(0))
		mock.ExpectExec(`UPDATE content_exports`).WithArgs(1, SyncFailed, "e", 60, "t", "c", "w", SyncProcessing, 0).
			WillReturnError(errors.New("fail"))
		if _, err := store.Fail(context.Background(), "t", "c", "w", "e", 1); err == nil {
			t.Fatal("expected fail error")
		}
		mock.ExpectQuery(`SELECT attempts`).WithArgs("t", "c", "w", SyncProcessing).
			WillReturnRows(pgxmock.NewRows([]string{"attempts"}).AddRow(0))
		mock.ExpectExec(`UPDATE content_exports`).WithArgs(1, SyncFailed, "e", 60, "t", "c", "w", SyncProcessing, 0).
			WillReturnResult(pgxmock.NewResult("UPDATE", 0))
		if ok, err := store.Fail(context.Background(), "t", "c", "w", "e", 1); err != nil || ok {
			t.Fatalf("fail result = %t, %v", ok, err)
		}
		mock.ExpectQuery(`SELECT export.status`).WillReturnError(errors.New("counts"))
		if _, err := store.SyncCounts(context.Background()); err == nil {
			t.Fatal("expected counts error")
		}
		mock.ExpectQuery(`SELECT export.status`).WillReturnRows(
			pgxmock.NewRows([]string{"status", "count"}).
				AddRow(SyncRetry, int64(1)).
				AddRow(SyncSynced, int64(1)).
				RowError(1, errors.New("iterate")),
		)
		if _, err := store.SyncCounts(context.Background()); err == nil {
			t.Fatal("expected counts iteration error")
		}
		if err := mock.ExpectationsWereMet(); err != nil {
			t.Fatal(err)
		}
	})
}

func TestStoreContentsUsesDefaultChunkSize(t *testing.T) {
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatal(err)
	}
	defer mock.Close()
	store := newPostgresStoreWithPool(mock)
	store.chunkSize = 0
	store.logger = slog.New(slog.NewTextHandler(io.Discard, nil))
	mock.ExpectBegin()
	expectContentStoreLock(mock)
	mock.ExpectExec(`INSERT INTO contents`).WithArgs(anyArgs(12)...).
		WillReturnResult(pgxmock.NewResult("INSERT", 1))
	mock.ExpectExec(`INSERT INTO content_exports`).
		WithArgs(SyncPending, []string{"one"}).
		WillReturnResult(pgxmock.NewResult("INSERT", 1))
	mock.ExpectCommit()
	if _, err := store.StoreContents(context.Background(), []content.Content{testContent("one")}, nil); err != nil {
		t.Fatal(err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestStorageHelpersCoverValidationAndQueries(t *testing.T) {
	store, err := NewPostgresStore(config.DatabaseConfig{URL: "postgres://localhost/database"}, nil)
	if err != nil {
		t.Fatal(err)
	}
	store.Close()
	if query, args := buildPublishedAtBackfillQuery([]publishedAtMigration{
		{contentID: "one", publishedAt: time.Unix(1, 0)},
		{contentID: "two", publishedAt: time.Unix(2, 0)},
	}); !strings.Contains(query, "$1::text") || !strings.Contains(query, ",($3::text,$4::timestamptz)") || len(args) != 4 {
		t.Fatalf("backfill query = %q %#v", query, args)
	}
	if _, err := normalizeExportTargets([]ExportTarget{{TargetID: "a", Kind: "k", DestinationFingerprint: "d"}, {TargetID: "a", Kind: "x", DestinationFingerprint: "e"}}); err == nil {
		t.Fatal("expected duplicate target ID")
	}
	if _, err := normalizeExportTargets([]ExportTarget{{TargetID: "a", Kind: "k", DestinationFingerprint: "d"}, {TargetID: "b", Kind: "k", DestinationFingerprint: "d"}}); err == nil {
		t.Fatal("expected duplicate destination")
	}
	if _, err := normalizeExportTargets([]ExportTarget{{TargetID: strings.Repeat("x", 129), Kind: "k", DestinationFingerprint: "d"}}); err == nil {
		t.Fatal("expected target length error")
	}
	if _, err := normalizeContentSources([]ContentSource{{ContentID: " ", ScraperID: "s", ScraperName: "n"}}); err == nil {
		t.Fatal("expected source identity error")
	}
	if sources, err := normalizeContentSources([]ContentSource{
		{ContentID: "one", ScraperID: "feed", ScraperName: "old"},
		{ContentID: "one", ScraperID: "feed", ScraperName: "new"},
	}); err != nil || len(sources) != 1 || sources[0].ScraperName != "new" {
		t.Fatalf("normalized duplicate sources = %#v, %v", sources, err)
	}
	if got := deduplicateIDs([]string{" ", "one", "one"}); len(got) != 1 || got[0] != "one" {
		t.Fatalf("deduplicateIDs = %#v", got)
	}
	if _, _, err := buildInsertContentsQuery([]content.Content{{ContentID: "one", Keywords: []string{"ok"}}}); err != nil {
		t.Fatal(err)
	}
	if got := nextRetryDelay(0); got != time.Minute {
		t.Fatalf("nextRetryDelay(0) = %s", got)
	}
}

func TestScanStorageRowsReportsFaults(t *testing.T) {
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatal(err)
	}
	defer mock.Close()
	mock.ExpectQuery(`metadata`).WillReturnRows(
		pgxmock.NewRows(contentMetadataColumns()).AddRow("one", "title", "link", "summary", "published", nil, nil, `[]`, `bad`, nil, nil, time.Now()),
	)
	rows, err := mock.Query(context.Background(), "metadata")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := scanContentMetadata(rows); err == nil {
		t.Fatal("expected metadata decode error")
	}
	mock.ExpectQuery(`metadata`).WillReturnRows(
		pgxmock.NewRows(contentMetadataColumns()[:1]).AddRow("one"),
	)
	rows, err = mock.Query(context.Background(), "metadata")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := scanContentMetadata(rows); err == nil {
		t.Fatal("expected metadata scan error")
	}
	mock.ExpectQuery(`metadata`).WillReturnRows(
		pgxmock.NewRows(contentMetadataColumns()).
			AddRow("one", "title", "link", "summary", "published", nil, nil, `[]`, `[]`, nil, nil, time.Now()).
			AddRow("two", "title", "link", "summary", "published", nil, nil, `[]`, `[]`, nil, nil, time.Now()).
			RowError(1, errors.New("iterate")),
	)
	rows, err = mock.Query(context.Background(), "metadata")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := scanContentMetadata(rows); err == nil {
		t.Fatal("expected metadata iteration error")
	}
	mock.ExpectQuery(`content`).WillReturnRows(
		pgxmock.NewRows(claimedContentColumns()).AddRow("one", "title", "link", "summary", "body", "published", nil, `[]`, `bad`, nil, nil),
	)
	rows, err = mock.Query(context.Background(), "content")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := scanContents(rows); err == nil {
		t.Fatal("expected content decode error")
	}
	mock.ExpectQuery(`content`).WillReturnRows(
		pgxmock.NewRows(claimedContentColumns()[:1]).AddRow("one"),
	)
	rows, err = mock.Query(context.Background(), "content")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := scanContents(rows); err == nil {
		t.Fatal("expected content scan error")
	}
	mock.ExpectQuery(`content`).WillReturnRows(
		pgxmock.NewRows(claimedContentColumns()).
			AddRow("one", "title", "link", "summary", "body", "published", nil, `[]`, `[]`, nil, nil).
			AddRow("two", "title", "link", "summary", "body", "published", nil, `[]`, `[]`, nil, nil).
			RowError(1, errors.New("iterate")),
	)
	rows, err = mock.Query(context.Background(), "content")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := scanContents(rows); err == nil {
		t.Fatal("expected content iteration error")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func expectInitializePrefix(mock pgxmock.PgxPoolIface, version int) {
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT pg_advisory_xact_lock`).WithArgs(migrationLockKey).
		WillReturnResult(pgxmock.NewResult("SELECT", 1))
	mock.ExpectExec(`CREATE TABLE IF NOT EXISTS schema_migrations`).
		WillReturnResult(pgxmock.NewResult("CREATE", 0))
	mock.ExpectQuery(`SELECT COALESCE\(MAX\(version\), 0\)`).
		WillReturnRows(pgxmock.NewRows([]string{"version"}).AddRow(version))
}

func expectFreshSchema(mock pgxmock.PgxPoolIface, _ int) {
	for _, query := range []string{
		`CREATE TABLE IF NOT EXISTS contents`,
		`CREATE TABLE IF NOT EXISTS content_sources`,
		`CREATE TABLE IF NOT EXISTS export_targets`,
		`CREATE INDEX IF NOT EXISTS ix_contents_collected`,
		`CREATE INDEX IF NOT EXISTS ix_content_exports_due`,
	} {
		mock.ExpectExec(query).WillReturnResult(pgxmock.NewResult("CREATE", 0))
	}
}

func mustBegin(mock pgxmock.PgxPoolIface) pgx.Tx {
	tx, err := mock.Begin(context.Background())
	if err != nil {
		panic(err)
	}
	return tx
}
