package storage

import (
	"context"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
)

const (
	SyncPending    = "pending"
	SyncProcessing = "processing"
	SyncRetry      = "retry"
	SyncSynced     = "synced"
	SyncFailed     = "failed"
	SchemaVersion  = 2
)

// StoreStats describes one canonical batch insert.
type StoreStats struct {
	Requested  int `json:"requested"`
	Inserted   int `json:"inserted"`
	Duplicates int `json:"duplicates"`
}

// CanonicalStore persists scraped content and Notion synchronization state.
type CanonicalStore interface {
	Initialize(context.Context) error
	Ping(context.Context) error
	Close()
	ExistingContentIDs(context.Context, []string) (map[string]struct{}, error)
	StoreContents(context.Context, []content.Content) (StoreStats, error)
	RegisterTarget(context.Context, string, bool) error
	Claim(context.Context, string, string, int, time.Duration, int) ([]content.Content, error)
	Renew(context.Context, string, string, string, time.Duration) (bool, error)
	Complete(context.Context, string, string, string) (bool, error)
	Fail(context.Context, string, string, string, string, int) (bool, error)
	SyncCounts(context.Context) (map[string]int64, error)
}
