package storage

import (
	"context"
	"encoding/json"
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
	mock.ExpectBegin()
	mock.ExpectExec(`SELECT pg_advisory_xact_lock`).WithArgs(migrationLockKey).
		WillReturnResult(pgxmock.NewResult("SELECT", 1))
	mock.ExpectExec(`CREATE TABLE IF NOT EXISTS schema_migrations`).
		WillReturnResult(pgxmock.NewResult("CREATE", 0))
	mock.ExpectQuery(`SELECT COALESCE\(MAX\(version\), 0\)`).
		WillReturnRows(pgxmock.NewRows([]string{"version"}).AddRow(0))
	mock.ExpectExec(`CREATE TABLE IF NOT EXISTS contents`).
		WillReturnResult(pgxmock.NewResult("CREATE", 0))
	mock.ExpectExec(`CREATE TABLE IF NOT EXISTS content_sources`).
		WillReturnResult(pgxmock.NewResult("CREATE", 0))
	mock.ExpectExec(`CREATE TABLE IF NOT EXISTS export_targets`).
		WillReturnResult(pgxmock.NewResult("CREATE", 0))
	mock.ExpectExec(`CREATE INDEX IF NOT EXISTS ix_contents_collected`).
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
	mock.ExpectExec(`INSERT INTO schema_migrations`).WithArgs(2).
		WillReturnResult(pgxmock.NewResult("INSERT", 1))
	expectNoLegacyStringArrayNormalization(mock)
	mock.ExpectExec(`DROP INDEX IF EXISTS ix_content_exports_due`).
		WillReturnResult(pgxmock.NewResult("ALTER", 0))
	expectNoPublishedAtBackfill(mock)
	mock.ExpectExec(`CREATE INDEX IF NOT EXISTS ix_contents_collected`).
		WillReturnResult(pgxmock.NewResult("CREATE", 0))
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

func TestPostgresStoreMigratesVersionTwoAtomically(t *testing.T) {
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
		WillReturnRows(pgxmock.NewRows([]string{"version"}).AddRow(2))
	expectNoLegacyStringArrayNormalization(mock)
	mock.ExpectExec(`DROP INDEX IF EXISTS ix_content_exports_due`).
		WillReturnResult(pgxmock.NewResult("ALTER", 0))
	expectNoPublishedAtBackfill(mock)
	mock.ExpectExec(`CREATE INDEX IF NOT EXISTS ix_contents_collected`).
		WillReturnResult(pgxmock.NewResult("CREATE", 0))
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
		mock.ExpectExec(`INSERT INTO schema_migrations`).WithArgs(2).
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

func TestPostgresStoreReconcilesAndBackfillsTargets(t *testing.T) {
	target := ExportTarget{
		TargetID:               "target:one",
		Kind:                   "target",
		DestinationFingerprint: "destination",
	}
	for _, test := range []struct {
		name            string
		targets         []ExportTarget
		existingEnabled *bool
		backfill        bool
	}{
		{
			name:     "new target",
			targets:  []ExportTarget{target},
			backfill: true,
		},
		{
			name:            "unchanged target",
			targets:         []ExportTarget{target},
			existingEnabled: boolPointer(true),
		},
		{
			name:            "re-enabled target",
			targets:         []ExportTarget{target},
			existingEnabled: boolPointer(false),
			backfill:        true,
		},
		{name: "disabled", targets: nil},
	} {
		t.Run(test.name, func(t *testing.T) {
			mock, err := pgxmock.NewPool()
			if err != nil {
				t.Fatal(err)
			}
			defer mock.Close()
			store := newPostgresStoreWithPool(mock)
			mock.ExpectBegin()
			expectTargetReconcileLock(mock)
			if len(test.targets) > 0 {
				rows := pgxmock.NewRows(
					[]string{"kind", "destination_fingerprint", "enabled"},
				)
				if test.existingEnabled != nil {
					rows.AddRow(
						target.Kind,
						target.DestinationFingerprint,
						*test.existingEnabled,
					)
				}
				mock.ExpectQuery(`SELECT kind, destination_fingerprint, enabled`).
					WithArgs(target.TargetID).
					WillReturnRows(rows)
				mock.ExpectExec(`INSERT INTO export_targets`).
					WithArgs(
						target.TargetID,
						target.Kind,
						target.DestinationFingerprint,
					).
					WillReturnResult(pgxmock.NewResult("INSERT", 1))
				if test.backfill {
					mock.ExpectExec(`INSERT INTO content_exports`).
						WithArgs(target.TargetID, SyncPending).
						WillReturnResult(pgxmock.NewResult("INSERT", 2))
				}
			}
			targetIDs := []string{}
			if len(test.targets) > 0 {
				targetIDs = []string{target.TargetID}
			}
			mock.ExpectExec(`UPDATE export_targets`).
				WithArgs(targetIDs).
				WillReturnResult(pgxmock.NewResult("UPDATE", 1))
			mock.ExpectCommit()
			if err := store.ReconcileTargets(context.Background(), test.targets); err != nil {
				t.Fatal(err)
			}
			if err := mock.ExpectationsWereMet(); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestPostgresStoreReconcileTargetErrorPaths(t *testing.T) {
	target := ExportTarget{
		TargetID:               "target:one",
		Kind:                   "target",
		DestinationFingerprint: "destination",
	}
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
			name: "disable",
			setup: func(mock pgxmock.PgxPoolIface) {
				mock.ExpectBegin()
				expectTargetReconcileLock(mock)
				mock.ExpectQuery(`SELECT kind, destination_fingerprint, enabled`).
					WithArgs(target.TargetID).
					WillReturnRows(
						pgxmock.NewRows(
							[]string{"kind", "destination_fingerprint", "enabled"},
						),
					)
				mock.ExpectExec(`INSERT INTO export_targets`).
					WithArgs(target.TargetID, target.Kind, target.DestinationFingerprint).
					WillReturnResult(pgxmock.NewResult("INSERT", 1))
				mock.ExpectExec(`INSERT INTO content_exports`).
					WithArgs(target.TargetID, SyncPending).
					WillReturnResult(pgxmock.NewResult("INSERT", 1))
				mock.ExpectExec(`UPDATE export_targets`).
					WithArgs([]string{target.TargetID}).
					WillReturnError(errors.New("disable failed"))
				mock.ExpectRollback()
			},
		},
		{
			name: "lock",
			setup: func(mock pgxmock.PgxPoolIface) {
				mock.ExpectBegin()
				mock.ExpectExec(`SELECT pg_advisory_xact_lock`).
					WithArgs(contentTargetLockKey).
					WillReturnError(errors.New("lock failed"))
				mock.ExpectRollback()
			},
		},
		{
			name: "register",
			setup: func(mock pgxmock.PgxPoolIface) {
				mock.ExpectBegin()
				expectTargetReconcileLock(mock)
				mock.ExpectQuery(`SELECT kind, destination_fingerprint, enabled`).
					WithArgs(target.TargetID).
					WillReturnRows(
						pgxmock.NewRows(
							[]string{"kind", "destination_fingerprint", "enabled"},
						),
					)
				mock.ExpectExec(`INSERT INTO export_targets`).
					WithArgs(target.TargetID, target.Kind, target.DestinationFingerprint).
					WillReturnError(errors.New("register failed"))
				mock.ExpectRollback()
			},
		},
		{
			name: "backfill",
			setup: func(mock pgxmock.PgxPoolIface) {
				mock.ExpectBegin()
				expectTargetReconcileLock(mock)
				mock.ExpectQuery(`SELECT kind, destination_fingerprint, enabled`).
					WithArgs(target.TargetID).
					WillReturnRows(
						pgxmock.NewRows(
							[]string{"kind", "destination_fingerprint", "enabled"},
						),
					)
				mock.ExpectExec(`INSERT INTO export_targets`).
					WithArgs(target.TargetID, target.Kind, target.DestinationFingerprint).
					WillReturnResult(pgxmock.NewResult("INSERT", 1))
				mock.ExpectExec(`INSERT INTO content_exports`).WithArgs(target.TargetID, SyncPending).
					WillReturnError(errors.New("backfill failed"))
				mock.ExpectRollback()
			},
		},
		{
			name: "identity conflict",
			setup: func(mock pgxmock.PgxPoolIface) {
				mock.ExpectBegin()
				expectTargetReconcileLock(mock)
				mock.ExpectQuery(`SELECT kind, destination_fingerprint, enabled`).
					WithArgs(target.TargetID).
					WillReturnRows(
						pgxmock.NewRows(
							[]string{"kind", "destination_fingerprint", "enabled"},
						).AddRow("other", "other", true),
					)
				mock.ExpectRollback()
			},
		},
		{
			name: "identity race",
			setup: func(mock pgxmock.PgxPoolIface) {
				mock.ExpectBegin()
				expectTargetReconcileLock(mock)
				mock.ExpectQuery(`SELECT kind, destination_fingerprint, enabled`).
					WithArgs(target.TargetID).
					WillReturnRows(
						pgxmock.NewRows(
							[]string{"kind", "destination_fingerprint", "enabled"},
						),
					)
				mock.ExpectExec(`INSERT INTO export_targets`).
					WithArgs(target.TargetID, target.Kind, target.DestinationFingerprint).
					WillReturnResult(pgxmock.NewResult("INSERT", 0))
				mock.ExpectRollback()
			},
		},
		{
			name: "commit",
			setup: func(mock pgxmock.PgxPoolIface) {
				mock.ExpectBegin()
				expectTargetReconcileLock(mock)
				mock.ExpectQuery(`SELECT kind, destination_fingerprint, enabled`).
					WithArgs(target.TargetID).
					WillReturnRows(
						pgxmock.NewRows(
							[]string{"kind", "destination_fingerprint", "enabled"},
						),
					)
				mock.ExpectExec(`INSERT INTO export_targets`).
					WithArgs(target.TargetID, target.Kind, target.DestinationFingerprint).
					WillReturnResult(pgxmock.NewResult("INSERT", 1))
				mock.ExpectExec(`INSERT INTO content_exports`).WithArgs(target.TargetID, SyncPending).
					WillReturnResult(pgxmock.NewResult("INSERT", 1))
				mock.ExpectExec(`UPDATE export_targets`).
					WithArgs([]string{target.TargetID}).
					WillReturnResult(pgxmock.NewResult("UPDATE", 0))
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
			if err := store.ReconcileTargets(context.Background(), []ExportTarget{target}); err == nil {
				t.Fatal("expected reconciliation error")
			}
			if err := mock.ExpectationsWereMet(); err != nil {
				t.Fatal(err)
			}
		})
	}
	if err := newPostgresStoreWithPool(nil).ReconcileTargets(
		context.Background(),
		[]ExportTarget{{TargetID: "invalid"}},
	); err == nil {
		t.Fatal("expected invalid target error")
	}
}

func TestNormalizeContentSourcesCountsCharacters(t *testing.T) {
	validName := strings.Repeat("源", 255)
	sources, err := normalizeContentSources([]ContentSource{{
		ContentID:   "content",
		ScraperID:   "source",
		ScraperName: validName,
		ObservedAt:  time.Date(2026, 8, 30, 0, 0, 0, 0, time.UTC),
	}})
	if err != nil {
		t.Fatalf("normalizeContentSources valid name: %v", err)
	}
	if len(sources) != 1 || sources[0].ScraperName != validName {
		t.Fatalf("normalized sources = %#v", sources)
	}
	validID := strings.Repeat("源", 255)
	sources, err = normalizeContentSources([]ContentSource{{
		ContentID:   "content",
		ScraperID:   validID,
		ScraperName: "Source",
	}})
	if err != nil {
		t.Fatalf("normalizeContentSources valid ID: %v", err)
	}
	if len(sources) != 1 || sources[0].ScraperID != validID {
		t.Fatalf("normalized valid ID sources = %#v", sources)
	}
	if _, err := normalizeContentSources([]ContentSource{{
		ContentID:   "content",
		ScraperID:   "source",
		ScraperName: strings.Repeat("源", 256),
	}}); err == nil {
		t.Fatal("normalizeContentSources accepted more than 255 characters")
	}
	if _, err := normalizeContentSources([]ContentSource{{
		ContentID:   "content",
		ScraperID:   strings.Repeat("源", 256),
		ScraperName: "Source",
	}}); err == nil {
		t.Fatal("normalizeContentSources accepted a scraper ID longer than 255 characters")
	}
	legacyID := "legacy:" + strings.Repeat("a", 32)
	sources, err = normalizeContentSources([]ContentSource{{
		ContentID:   "content",
		ScraperID:   legacyID,
		ScraperName: "Legacy",
	}})
	if err != nil {
		t.Fatalf("normalizeContentSources legacy ID: %v", err)
	}
	if len(sources) != 1 || sources[0].ScraperID != legacyID {
		t.Fatalf("normalized legacy ID sources = %#v", sources)
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
	publishedAt := time.Date(2026, 8, 18, 11, 0, 0, 0, time.UTC)
	rows := pgxmock.NewRows(contentMetadataColumns()).
		AddRow("one", "Title one", "https://example.com/one", "Summary", "source-time", publishedAt, "Alice", `["k"]`, `["tag"]`, "feed", "Feed", cursorTime).
		AddRow("two", "Title two", "https://example.com/two", "Summary", "source-time", nil, nil, `[]`, `[]`, nil, nil, cursorTime.Add(-time.Minute)).
		AddRow("three", "Title three", "https://example.com/three", "Summary", "source-time", nil, nil, `[]`, `[]`, nil, nil, cursorTime.Add(-2*time.Minute))
	mock.ExpectQuery(`SELECT content_id, title, link, summary, published, published_at, author,\s+keywords_json, tags_json, scraper_id, scraper_name, collected_at\s+FROM contents`).
		WithArgs("feed", "Feed", after, before, cursorTime, "cursor-id", []string{"tag"}, 3).
		WillReturnRows(rows)
	page, err := store.ListContents(context.Background(), ContentListOptions{
		Limit:           2,
		ScraperID:       "feed",
		ScraperName:     "Feed",
		Tags:            []string{"tag"},
		CollectedAfter:  &after,
		CollectedBefore: &before,
		Cursor: &ContentListCursor{
			CollectedAt: cursorTime,
			ContentID:   "cursor-id",
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(page.Items) != 2 || page.Items[0].ContentID != "one" {
		t.Fatalf("page = %#v", page)
	}
	if page.NextCursor == nil ||
		!page.NextCursor.CollectedAt.Equal(page.Items[1].CollectedAt) ||
		page.NextCursor.ContentID != "two" {
		t.Fatalf("next cursor = %#v", page.NextCursor)
	}
	if page.Items[0].Author == nil || *page.Items[0].Author != "Alice" ||
		page.Items[0].PublishedAt == nil ||
		!page.Items[0].PublishedAt.Equal(publishedAt) ||
		page.Items[0].ScraperID == nil ||
		*page.Items[0].ScraperID != "feed" ||
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
		rows := pgxmock.NewRows(contentMetadataColumns()).
			AddRow("one", "Title", "https://example.com/one", "Summary", "source-time", nil, nil, `[]`, `[]`, nil, nil, collectedAt)
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
		rows := pgxmock.NewRows(contentMetadataColumns()).
			AddRow("one", "Title", "https://example.com/one", "Summary", "source-time", nil, nil, `[]`, `[]`, nil, nil, time.Now())
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
		rows := pgxmock.NewRows(contentMetadataColumns()).
			AddRow("one", "Title", "https://example.com/one", "Summary", "source-time", nil, nil, `bad`, `[]`, nil, nil, time.Now())
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

func TestBuildListContentsQueryRequiresOneSourceForBothFilters(t *testing.T) {
	query, args := buildListContentsQuery(ContentListOptions{
		Limit:       10,
		ScraperID:   "feed",
		ScraperName: "Feed",
	})
	if strings.Count(query, "FROM content_sources AS source") != 1 {
		t.Fatalf("query uses separate provenance subqueries: %s", query)
	}
	if !strings.Contains(query, "source.scraper_id = $1") ||
		!strings.Contains(query, "source.scraper_name = $2") {
		t.Fatalf("query does not bind both filters to one source: %s", query)
	}
	if len(args) != 3 || args[0] != "feed" || args[1] != "Feed" || args[2] != 11 {
		t.Fatalf("query args = %#v", args)
	}
}

func TestNormalizeContentSourcesKeepsLatestObservation(t *testing.T) {
	oldObservedAt := time.Date(2026, 8, 29, 0, 0, 0, 0, time.UTC)
	newObservedAt := oldObservedAt.Add(time.Hour)
	sources, err := normalizeContentSources([]ContentSource{
		{
			ContentID:   "one",
			ScraperID:   "feed",
			ScraperName: "new",
			ObservedAt:  newObservedAt,
		},
		{
			ContentID:   "one",
			ScraperID:   "feed",
			ScraperName: "old",
			ObservedAt:  oldObservedAt,
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(sources) != 1 ||
		sources[0].ScraperName != "new" ||
		!sources[0].ObservedAt.Equal(newObservedAt) {
		t.Fatalf("normalized sources = %#v", sources)
	}
}

func TestBuildUpsertContentSourcesUsesObservationTimestamp(t *testing.T) {
	observedAt := time.Date(2026, 8, 30, 0, 0, 0, 0, time.UTC)
	query, args := buildUpsertContentSourcesQuery([]ContentSource{{
		ContentID:   "one",
		ScraperID:   "feed",
		ScraperName: "Feed",
		ObservedAt:  observedAt,
	}})
	if !strings.Contains(query, "LEAST(") ||
		!strings.Contains(query, "GREATEST(") ||
		!strings.Contains(query, "EXCLUDED.last_seen_at >= content_sources.last_seen_at") {
		t.Fatalf("upsert query lacks ordered observation merge: %s", query)
	}
	if !strings.Contains(query, "$4::timestamptz") {
		t.Fatalf("upsert query lacks timestamp type annotation: %s", query)
	}
	if len(args) != 4 || args[3] != observedAt {
		t.Fatalf("upsert args = %#v", args)
	}
}

func TestNormalizeLegacyStringArrayJSON(t *testing.T) {
	normalized, err := normalizeLegacyStringArrayJSON(
		`["before\u0000after"]`,
		"keywords_json",
		"one",
	)
	if err != nil {
		t.Fatal(err)
	}
	var values []string
	if err := json.Unmarshal([]byte(normalized), &values); err != nil {
		t.Fatal(err)
	}
	if len(values) != 1 || values[0] != "before\uFFFDafter" {
		t.Fatalf("normalized values = %#v", values)
	}
	normalized, err = normalizeLegacyStringArrayJSON(
		`null`,
		"tags_json",
		"one",
	)
	if err != nil || normalized != "[]" {
		t.Fatalf("normalized null = %q, %v", normalized, err)
	}
	if _, err := normalizeLegacyStringArrayJSON(
		`[1]`,
		"tags_json",
		"one",
	); err == nil {
		t.Fatal("non-string legacy array was accepted")
	}
}

func TestContentSourceNameIndexIsPartOfSchemaSetup(t *testing.T) {
	if !strings.Contains(createContentIndexesSQL, "ix_content_sources_scraper_name") {
		t.Fatalf("schema indexes omit scraper name provenance index: %s", createContentIndexesSQL)
	}
	if !strings.Contains(migrateV2ToV3SQL, "CREATE TABLE content_sources") {
		t.Fatalf("v2 to v3 migration does not create content sources")
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
	publishedAt := time.Date(2026, 8, 18, 10, 0, 0, 0, time.UTC)
	rows := pgxmock.NewRows(contentRecordColumns()).
		AddRow("one", "Title", "https://example.com/one", "Summary", "Body", "source-time", publishedAt, "Alice", `["k"]`, `["tag"]`, "feed", "Feed", collectedAt)
	mock.ExpectQuery(`SELECT content_id, title, link, summary, content, published, published_at`).
		WithArgs("one").
		WillReturnRows(rows)
	record, ok, err := store.GetContent(context.Background(), "one")
	if err != nil || !ok {
		t.Fatalf("GetContent() = %#v, %t, %v", record, ok, err)
	}
	if record.Content != "Body" || record.ContentID != "one" ||
		record.Author == nil || *record.Author != "Alice" ||
		record.PublishedAt == nil || !record.PublishedAt.Equal(publishedAt) ||
		record.ScraperID == nil || *record.ScraperID != "feed" ||
		!record.CollectedAt.Equal(collectedAt) {
		t.Fatalf("record = %#v", record)
	}
	mock.ExpectQuery(`SELECT content_id, title, link, summary, content, published, published_at`).
		WithArgs("missing").
		WillReturnRows(pgxmock.NewRows(contentRecordColumns()))
	_, ok, err = store.GetContent(context.Background(), "missing")
	if err != nil || ok {
		t.Fatalf("missing = %t, %v", ok, err)
	}
	mock.ExpectQuery(`SELECT content_id, title, link, summary, content, published, published_at`).
		WithArgs("broken").
		WillReturnError(errors.New("database failed"))
	_, _, err = store.GetContent(context.Background(), "broken")
	if err == nil {
		t.Fatal("expected database error")
	}
	mock.ExpectQuery(`SELECT content_id, title, link, summary, content, published, published_at`).
		WithArgs("bad-json").
		WillReturnRows(pgxmock.NewRows(contentRecordColumns()).
			AddRow("bad-json", "Title", "https://example.com/bad-json", "Summary", "Body", "source-time", nil, nil, `bad`, `[]`, nil, nil, collectedAt))
	_, _, err = store.GetContent(context.Background(), "bad-json")
	if err == nil {
		t.Fatal("expected decode error")
	}
	mock.ExpectQuery(`SELECT content_id, title, link, summary, content, published, published_at`).
		WithArgs("bad-tags").
		WillReturnRows(pgxmock.NewRows(contentRecordColumns()).
			AddRow("bad-tags", "Title", "https://example.com/bad-tags", "Summary", "Body", "source-time", nil, nil, `[]`, `bad`, nil, nil, collectedAt))
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
	stats, err := store.StoreContents(context.Background(), nil, nil)
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
	if args[8] != "[]" || args[9] != "[]" {
		t.Fatalf("collection JSON = %q, %q; want [], []", args[8], args[9])
	}
	_, args, err = buildInsertContentsQuery([]content.Content{{
		ContentID: "nul",
		Title:     "NUL",
		Keywords:  []string{"before\x00after"},
		Tags:      []string{"tag\x00value"},
	}})
	if err != nil {
		t.Fatal(err)
	}
	for index, expected := range []string{"before\uFFFDafter", "tag\uFFFDvalue"} {
		var values []string
		if err := json.Unmarshal([]byte(args[8+index].(string)), &values); err != nil {
			t.Fatal(err)
		}
		if len(values) != 1 || values[0] != expected {
			t.Fatalf("normalized collection %d = %#v", index, values)
		}
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
	expectContentStoreLock(mock)
	mock.ExpectExec(`INSERT INTO contents`).WithArgs(anyArgs(24)...).WillReturnResult(pgxmock.NewResult("INSERT", 1))
	mock.ExpectExec(`WITH observed`).WithArgs(
		"one", "feed", "Feed", pgxmock.AnyArg(),
		"two", "feed", "Feed", pgxmock.AnyArg(),
	).WillReturnResult(pgxmock.NewResult("INSERT", 2))
	mock.ExpectExec(`UPDATE contents AS content`).
		WithArgs([]string{"one", "two"}).
		WillReturnResult(pgxmock.NewResult("UPDATE", 2))
	mock.ExpectExec(`INSERT INTO content_exports`).WithArgs(SyncPending, []string{"one", "two"}).WillReturnResult(pgxmock.NewResult("INSERT", 1))
	mock.ExpectCommit()

	stats, err := store.StoreContents(
		context.Background(),
		[]content.Content{testContent("one"), testContent("one"), testContent("two")},
		[]ContentSource{
			{ContentID: "one", ScraperID: "feed", ScraperName: "Feed"},
			{ContentID: "two", ScraperID: "feed", ScraperName: "Feed"},
		},
	)
	if err != nil {
		t.Fatalf("StoreContents() error = %v", err)
	}
	if stats.Requested != 3 ||
		stats.Inserted != 1 ||
		stats.Duplicates != 2 ||
		stats.SourcesObserved != 2 {
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
	expectContentStoreLock(mock)
	mock.ExpectExec(`INSERT INTO contents`).
		WithArgs(anyArgs(12)...).
		WillReturnResult(pgxmock.NewResult("INSERT", 1))
	mock.ExpectExec(`INSERT INTO contents`).
		WithArgs(anyArgs(12)...).
		WillReturnResult(pgxmock.NewResult("INSERT", 1))
	mock.ExpectExec(`INSERT INTO content_exports`).
		WithArgs(SyncPending, []string{"one", "two"}).
		WillReturnResult(pgxmock.NewResult("INSERT", 2))
	mock.ExpectCommit()

	stats, err := store.StoreContents(
		context.Background(),
		[]content.Content{testContent("one"), testContent("two")},
		nil,
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
	rows := pgxmock.NewRows(claimedContentColumns()).
		AddRow("one", "Title", "https://example.com/one", "Summary", "Body", "2026-08-18T11:00:00Z", "Alice", `["k"]`, `["t"]`, "feed", "Feed")
	mock.ExpectQuery(`WITH due AS`).
		WithArgs("notion", 3, 1, "worker-1", 60).
		WillReturnRows(rows)

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
	if claimed[0].ScraperID == nil || *claimed[0].ScraperID != "feed" {
		t.Fatalf("claimed scraper ID = %#v", claimed[0].ScraperID)
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
	mock.ExpectQuery(`SELECT export.status, COUNT\(export.content_id\)`).WillReturnRows(countRows)
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
	scraperID := "feed"
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
		ScraperID:   &scraperID,
		ScraperName: &scraperName,
	}
}

func contentMetadataColumns() []string {
	return []string{
		"content_id",
		"title",
		"link",
		"summary",
		"published",
		"published_at",
		"author",
		"keywords_json",
		"tags_json",
		"scraper_id",
		"scraper_name",
		"collected_at",
	}
}

func contentRecordColumns() []string {
	return []string{
		"content_id",
		"title",
		"link",
		"summary",
		"content",
		"published",
		"published_at",
		"author",
		"keywords_json",
		"tags_json",
		"scraper_id",
		"scraper_name",
		"collected_at",
	}
}

func claimedContentColumns() []string {
	return []string{
		"content_id",
		"title",
		"link",
		"summary",
		"content",
		"published",
		"author",
		"keywords_json",
		"tags_json",
		"scraper_id",
		"scraper_name",
	}
}

func expectNoPublishedAtBackfill(mock pgxmock.PgxPoolIface) {
	mock.ExpectExec(`DECLARE octopus_published_v2`).
		WillReturnResult(pgxmock.NewResult("DECLARE", 0))
	mock.ExpectQuery(`FETCH FORWARD 512 FROM octopus_published_v2`).
		WillReturnRows(pgxmock.NewRows([]string{"content_id", "published"}))
	mock.ExpectExec(`CLOSE octopus_published_v2`).
		WillReturnResult(pgxmock.NewResult("CLOSE", 0))
}

func expectNoLegacyStringArrayNormalization(mock pgxmock.PgxPoolIface) {
	mock.ExpectQuery(`SELECT content_id, keywords_json, tags_json`).
		WillReturnRows(
			pgxmock.NewRows([]string{"content_id", "keywords_json", "tags_json"}),
		)
}

func expectContentStoreLock(mock pgxmock.PgxPoolIface) {
	mock.ExpectExec(`SELECT pg_advisory_xact_lock_shared`).
		WithArgs(contentTargetLockKey).
		WillReturnResult(pgxmock.NewResult("SELECT", 1))
}

func expectTargetReconcileLock(mock pgxmock.PgxPoolIface) {
	mock.ExpectExec(`SELECT pg_advisory_xact_lock`).
		WithArgs(contentTargetLockKey).
		WillReturnResult(pgxmock.NewResult("SELECT", 1))
}

func anyArgs(count int) []any {
	args := make([]any, count)
	for index := range args {
		args[index] = pgxmock.AnyArg()
	}
	return args
}

func boolPointer(value bool) *bool {
	return &value
}
