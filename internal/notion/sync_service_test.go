package notion

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/config"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/storage"
)

func TestSyncServiceRunOnceSuccess(t *testing.T) {
	t.Parallel()

	store := &fakeCanonicalStore{claims: [][]content.Content{{{ContentID: "id-1", Title: "T"}}}}
	uploader := &fakeUploader{results: []bool{true}}
	service := NewSyncService(config.NotionConfig{Enabled: true, BatchSize: 1, Lease: time.Hour, MaxAttempts: 3}, store, uploader)

	stats, err := service.RunOnce(context.Background())
	if err != nil {
		t.Fatalf("RunOnce returned error: %v", err)
	}
	if stats["claimed_count"] != 1 || stats["synced_count"] != 1 || stats["failed_count"] != 0 || stats["lost_claim_count"] != 0 {
		t.Fatalf("unexpected stats: %+v", stats)
	}
	if len(store.markSyncedCalls) != 1 {
		t.Fatalf("markSyncedCalls = %d, want 1", len(store.markSyncedCalls))
	}
}

func TestSyncServiceRunOnceFailure(t *testing.T) {
	t.Parallel()

	store := &fakeCanonicalStore{claims: [][]content.Content{{{ContentID: "id-2", Title: "T"}}}}
	uploader := &fakeUploader{err: errors.New("boom")}
	service := NewSyncService(config.NotionConfig{Enabled: true, BatchSize: 1, Lease: time.Hour, MaxAttempts: 3}, store, uploader)

	stats, err := service.RunOnce(context.Background())
	if err != nil {
		t.Fatalf("RunOnce error = %v, want per-content failure stats", err)
	}
	errorsValue, ok := stats["errors"].([]map[string]any)
	if !ok || stats["failed_count"] != 1 || len(errorsValue) != 1 {
		t.Fatalf("unexpected failure stats: %+v", stats)
	}
	if len(store.markFailedCalls) != 1 {
		t.Fatalf("markFailedCalls = %d, want 1", len(store.markFailedCalls))
	}
}

func TestSyncServiceReleasesClaimAfterRequestCancellation(t *testing.T) {
	t.Parallel()

	ctx, cancel := context.WithCancel(context.Background())
	store := &fakeCanonicalStore{
		claims: [][]content.Content{{{ContentID: "id-cancelled", Title: "T"}}},
	}
	uploader := &fakeUploader{
		cancel:  cancel,
		results: []bool{true},
	}
	service := NewSyncService(
		config.NotionConfig{
			Enabled:     true,
			BatchSize:   1,
			Lease:       time.Hour,
			MaxAttempts: 3,
		},
		store,
		uploader,
	)

	stats, err := service.RunOnce(ctx)
	if err != nil {
		t.Fatalf("RunOnce error = %v", err)
	}
	if stats["synced_count"] != 1 ||
		stats["failed_count"] != 0 ||
		len(store.markSyncedCalls) != 1 ||
		len(store.markFailedCalls) != 0 {
		t.Fatalf("unexpected cancellation stats: %+v", stats)
	}
	if ctx.Err() != context.Canceled {
		t.Fatalf("request context error = %v", ctx.Err())
	}
}

func TestSyncServiceStopCancelsDetachedClaimOperation(t *testing.T) {
	t.Parallel()

	started := make(chan struct{}, 1)
	store := &fakeCanonicalStore{
		claims: [][]content.Content{{
			{ContentID: "id-shutdown", Title: "T"},
		}},
	}
	service := NewSyncService(
		config.NotionConfig{
			Enabled:     true,
			BatchSize:   1,
			Interval:    time.Hour,
			Lease:       time.Hour,
			MaxAttempts: 3,
		},
		store,
		&fakeUploader{
			results: []bool{true},
			block:   make(chan struct{}),
			started: started,
		},
	)
	service.Start(context.Background())
	select {
	case <-started:
	case <-time.After(time.Second):
		t.Fatal("upload did not start")
	}

	stopCtx, cancel := context.WithTimeout(
		context.Background(),
		time.Second,
	)
	defer cancel()
	if err := service.Stop(stopCtx); err != nil {
		t.Fatal(err)
	}
	if len(store.markFailedCalls) != 1 ||
		store.markFailedCalls[0] != "id-shutdown" {
		t.Fatalf(
			"markFailedCalls = %v",
			store.markFailedCalls,
		)
	}
}

func TestSyncServiceBusyAndLostClaim(t *testing.T) {
	t.Parallel()

	store := &fakeCanonicalStore{claims: [][]content.Content{{{ContentID: "id-3", Title: "T"}}}}
	blocking := make(chan struct{})
	uploader := &fakeUploader{results: []bool{true}, block: blocking}
	service := NewSyncService(config.NotionConfig{Enabled: true, BatchSize: 1, Lease: 100 * time.Millisecond, MaxAttempts: 3}, store, uploader)
	store.claimed = make(chan struct{}, 1)

	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
		_, _ = service.RunOnce(context.Background())
	}()
	<-store.claimed
	busy, err := service.RunOnce(context.Background())
	if err != nil {
		t.Fatalf("busy RunOnce returned error: %v", err)
	}
	close(blocking)
	wg.Wait()
	if busy["busy"] != true {
		t.Fatalf("busy stats = %+v, want busy=true", busy)
	}

	lostStore := &fakeCanonicalStore{claims: [][]content.Content{{{ContentID: "id-4", Title: "T"}}}, renewResults: []bool{false}}
	lostService := NewSyncService(config.NotionConfig{Enabled: true, BatchSize: 1, Lease: 100 * time.Millisecond, MaxAttempts: 3}, lostStore, &fakeUploader{results: []bool{true}})
	stats, err := lostService.RunOnce(context.Background())
	if err != nil {
		t.Fatalf("lost claim RunOnce error = %v", err)
	}
	if stats["lost_claim_count"] != 1 {
		t.Fatalf("lost claim stats = %+v, want LostClaimCount=1", stats)
	}
}

type fakeUploader struct {
	results []bool
	err     error
	block   chan struct{}
	cancel  context.CancelFunc
	started chan struct{}
}

func (u *fakeUploader) StoreContents(
	ctx context.Context,
	_ []content.Content,
	_ bool,
) ([]bool, error) {
	if u.started != nil {
		select {
		case u.started <- struct{}{}:
		default:
		}
	}
	if u.block != nil {
		select {
		case <-u.block:
		case <-ctx.Done():
			return nil, ctx.Err()
		}
	}
	if u.cancel != nil {
		u.cancel()
		if err := ctx.Err(); err != nil {
			return nil, err
		}
	}
	if u.err != nil {
		return nil, u.err
	}
	return append([]bool(nil), u.results...), nil
}

type fakeCanonicalStore struct {
	claims          [][]content.Content
	claimed         chan struct{}
	claimCalls      int
	renewResults    []bool
	renewCalls      int
	markSyncedCalls []string
	markFailedCalls []string
}

func (s *fakeCanonicalStore) Initialize(context.Context) error { return nil }
func (s *fakeCanonicalStore) Ping(context.Context) error       { return nil }
func (s *fakeCanonicalStore) Close()                           {}
func (s *fakeCanonicalStore) ExistingContentIDs(context.Context, []string) (map[string]struct{}, error) {
	return nil, nil
}
func (s *fakeCanonicalStore) StoreContents(context.Context, []content.Content) (storage.StoreStats, error) {
	return storage.StoreStats{}, nil
}
func (s *fakeCanonicalStore) ClaimContents(context.Context, string, int, time.Duration, int) ([]content.Content, error) {
	if s.claimCalls >= len(s.claims) {
		return nil, nil
	}
	result := s.claims[s.claimCalls]
	s.claimCalls++
	if s.claimed != nil {
		select {
		case s.claimed <- struct{}{}:
		default:
		}
	}
	return result, nil
}
func (s *fakeCanonicalStore) RenewClaim(context.Context, string, string, time.Duration) (bool, error) {
	if s.renewCalls >= len(s.renewResults) {
		s.renewCalls++
		return true, nil
	}
	result := s.renewResults[s.renewCalls]
	s.renewCalls++
	return result, nil
}
func (s *fakeCanonicalStore) MarkSynced(_ context.Context, contentID string, _ string) (bool, error) {
	s.markSyncedCalls = append(s.markSyncedCalls, contentID)
	return true, nil
}
func (s *fakeCanonicalStore) MarkSyncFailed(_ context.Context, contentID string, _ string, _ string, _ int) (bool, error) {
	s.markFailedCalls = append(s.markFailedCalls, contentID)
	return true, nil
}
func (s *fakeCanonicalStore) SyncCounts(context.Context) (map[string]int64, error) {
	return map[string]int64{}, nil
}
