package app

import (
	"bytes"
	"context"
	"errors"
	"log/slog"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/fetcher"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/observability"
)

type failingFetcherFactory struct {
	err error
}

func TestInstrumentedSyncRunsPeriodicBatches(t *testing.T) {
	syncService := &runtimeSyncService{result: map[string]any{
		"claimed_count": 0,
		"synced_count":  0,
		"failed_count":  0,
	}}
	instrumented := &InstrumentedSyncService{
		Service:  syncService,
		Metrics:  observability.NewMetrics("test"),
		Interval: 5 * time.Millisecond,
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	instrumented.Start(ctx)
	instrumented.Start(ctx)
	deadline := time.Now().Add(time.Second)
	for syncService.calls.Load() < 2 && time.Now().Before(deadline) {
		time.Sleep(time.Millisecond)
	}
	if syncService.calls.Load() < 2 {
		t.Fatalf("periodic calls = %d", syncService.calls.Load())
	}
	if err := instrumented.Stop(context.Background()); err != nil {
		t.Fatal(err)
	}
}

func TestInstrumentedSyncStopsUnderlyingServiceBeforeWorkerDrain(t *testing.T) {
	t.Parallel()

	service := &stopReleasingSyncService{
		started:    make(chan struct{}, 1),
		release:    make(chan struct{}),
		stopCalled: make(chan struct{}),
	}
	instrumented := &InstrumentedSyncService{
		Service:  service,
		Metrics:  observability.NewMetrics("test"),
		Interval: time.Hour,
	}
	instrumented.Start(context.Background())
	select {
	case <-service.started:
	case <-time.After(time.Second):
		t.Fatal("periodic upload did not start")
	}

	stopCtx, cancel := context.WithCancel(context.Background())
	cancel()
	_ = instrumented.Stop(stopCtx)
	select {
	case <-service.stopCalled:
	case <-time.After(time.Second):
		t.Fatal("underlying sync service was not stopped")
	}
}

type stopReleasingSyncService struct {
	started    chan struct{}
	release    chan struct{}
	stopCalled chan struct{}
	stopOnce   sync.Once
}

func (s *stopReleasingSyncService) RunOnce(
	context.Context,
) (map[string]any, error) {
	select {
	case s.started <- struct{}{}:
	default:
	}
	<-s.release
	return map[string]any{}, nil
}

func (*stopReleasingSyncService) Start(context.Context) {}

func (s *stopReleasingSyncService) Stop(context.Context) error {
	s.stopOnce.Do(func() {
		close(s.stopCalled)
		close(s.release)
	})
	return nil
}

func (f failingFetcherFactory) Create(
	string,
	map[string]any,
) (fetcher.Fetcher, error) {
	return nil, f.err
}

func TestInstrumentedFactoriesAndSync(t *testing.T) {
	metrics := observability.NewMetrics("test")
	fetchFactory := InstrumentedFetcherFactory{
		Factory: staticFetcherFactory{fetcher: staticFetcher{
			items: []content.Content{{ContentID: "one"}},
		}},
		Metrics: metrics,
	}
	activeFetcher, err := fetchFactory.Create("direct_rss", nil)
	if err != nil {
		t.Fatal(err)
	}
	items, err := activeFetcher.Fetch(context.Background(), nil)
	if err != nil || len(items) != 1 {
		t.Fatalf("unexpected fetch result: %#v, %v", items, err)
	}
	expectedErr := errors.New("factory failed")
	if _, err := (InstrumentedFetcherFactory{
		Factory: failingFetcherFactory{err: expectedErr},
	}).Create("bad", nil); !errors.Is(err, expectedErr) {
		t.Fatalf("unexpected factory error: %v", err)
	}

	syncService := &runtimeSyncService{result: map[string]any{
		"claimed_count":    float64(4),
		"synced_count":     int64(2),
		"failed_count":     1,
		"lost_claim_count": 1,
	}}
	var logs bytes.Buffer
	instrumentedSync := InstrumentedSyncService{
		Service: syncService,
		Metrics: metrics,
		Logger:  slog.New(slog.NewTextHandler(&logs, nil)),
	}
	instrumentedSync.Start(context.Background())
	if _, err := instrumentedSync.RunOnce(context.Background()); err != nil {
		t.Fatal(err)
	}
	if err := instrumentedSync.Stop(context.Background()); err != nil {
		t.Fatal(err)
	}
	recorder := httptest.NewRecorder()
	metrics.Handler().ServeHTTP(recorder, httptest.NewRequest("GET", "/metrics", nil))
	if !strings.Contains(
		recorder.Body.String(),
		`octopus_upload_items_total{outcome="failed"} 2`,
	) {
		t.Fatalf("lost claims were not counted as failed uploads:\n%s", recorder.Body)
	}
	if !syncService.started.Load() || !syncService.stopped.Load() {
		t.Fatal("sync lifecycle was not delegated")
	}
	if !strings.Contains(
		logs.String(),
		"Notion synchronization batch completed with errors",
	) {
		t.Fatalf("missing failed batch log: %s", logs.String())
	}
	for value, expected := range map[any]int{
		1:          1,
		int64(2):   2,
		float64(3): 3,
		"bad":      0,
	} {
		if got := intValue(value); got != expected {
			t.Fatalf("intValue(%v) = %d", value, got)
		}
	}
}
