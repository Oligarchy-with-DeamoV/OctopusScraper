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
	SchemaVersion  = 3
)

// StoreStats describes one canonical batch insert.
type StoreStats struct {
	Requested       int `json:"requested"`
	Inserted        int `json:"inserted"`
	Duplicates      int `json:"duplicates"`
	SourcesObserved int `json:"sources_observed"`
}

// ContentSource identifies one scraper that observed canonical content.
type ContentSource struct {
	ContentID   string
	ScraperID   string
	ScraperName string
	ObservedAt  time.Time
}

// ExportTarget identifies one concrete downstream destination.
type ExportTarget struct {
	TargetID               string
	Kind                   string
	DestinationFingerprint string
}

// ContentMetadata is the canonical read-only metadata exposed to consumers.
type ContentMetadata struct {
	ContentID   string
	Title       string
	Link        string
	Summary     string
	Published   string
	PublishedAt *time.Time
	Author      *string
	Keywords    []string
	Tags        []string
	ScraperID   *string
	ScraperName *string
	CollectedAt time.Time
}

// ContentRecord is a canonical content row with its full stored body.
type ContentRecord struct {
	ContentMetadata
	Content string
}

// ContentListCursor identifies a keyset page boundary.
type ContentListCursor struct {
	CollectedAt time.Time
	ContentID   string
}

// ContentListOptions constrains read-only canonical content listing.
type ContentListOptions struct {
	Limit           int
	Cursor          *ContentListCursor
	ScraperID       string
	ScraperName     string
	Tags            []string
	CollectedAfter  *time.Time
	CollectedBefore *time.Time
}

// ContentListPage contains one page of canonical content metadata.
type ContentListPage struct {
	Items      []ContentMetadata
	NextCursor *ContentListCursor
}

// ContentReader exposes read-only canonical content to external consumers.
type ContentReader interface {
	ListContents(context.Context, ContentListOptions) (ContentListPage, error)
	GetContent(context.Context, string) (ContentRecord, bool, error)
}

// CanonicalStore persists scraped content, provenance, and export state.
type CanonicalStore interface {
	ContentReader
	Initialize(context.Context) error
	Ping(context.Context) error
	Close()
	ExistingContentIDs(context.Context, []string) (map[string]struct{}, error)
	StoreContents(context.Context, []content.Content, []ContentSource) (StoreStats, error)
	ReconcileTargets(context.Context, []ExportTarget) error
	Claim(context.Context, string, string, int, time.Duration, int) ([]content.Content, error)
	Renew(context.Context, string, string, string, time.Duration) (bool, error)
	Complete(context.Context, string, string, string) (bool, error)
	Fail(context.Context, string, string, string, string, int) (bool, error)
	SyncCounts(context.Context) (map[string]int64, error)
}
