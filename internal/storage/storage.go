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
	SchemaVersion  = 1
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
	ClaimContents(context.Context, string, int, time.Duration, int) ([]content.Content, error)
	RenewClaim(context.Context, string, string, time.Duration) (bool, error)
	MarkSynced(context.Context, string, string) (bool, error)
	MarkSyncFailed(context.Context, string, string, string, int) (bool, error)
	SyncCounts(context.Context) (map[string]int64, error)
}
