package app

import (
	"context"
	"log/slog"
	"sync"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/fetcher"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/observability"
)

type InstrumentedFetcherFactory struct {
	Factory fetcher.Factory
	Metrics *observability.Metrics
}

func (f InstrumentedFetcherFactory) Create(
	name string,
	rawConfig map[string]any,
) (fetcher.Fetcher, error) {
	active, err := f.Factory.Create(name, rawConfig)
	if err != nil {
		return nil, err
	}
	return instrumentedFetcher{Fetcher: active, metrics: f.Metrics}, nil
}

type instrumentedFetcher struct {
	fetcher.Fetcher
	metrics *observability.Metrics
}

func (f instrumentedFetcher) Fetch(
	ctx context.Context,
	params map[string]any,
) ([]content.Content, error) {
	started := time.Now()
	items, err := f.Fetcher.Fetch(ctx, params)
	if f.metrics != nil {
		_ = f.metrics.RecordExternal("rss", time.Since(started), err == nil)
	}
	return items, err
}

type InstrumentedSyncService struct {
	Service  SyncService
	Metrics  *observability.Metrics
	Interval time.Duration
	Logger   *slog.Logger

	mu     sync.Mutex
	cancel context.CancelFunc
	done   chan struct{}
}

func (s *InstrumentedSyncService) RunOnce(
	ctx context.Context,
) (map[string]any, error) {
	started := time.Now()
	result, err := s.Service.RunOnce(ctx)
	requested := intValue(result["claimed_count"])
	processed := intValue(result["synced_count"])
	failed := intValue(result["failed_count"])
	lost := intValue(result["lost_claim_count"])
	if s.Metrics != nil {
		_ = s.Metrics.RecordExternal(
			"notion",
			time.Since(started),
			err == nil && failed == 0 && lost == 0,
		)
		s.Metrics.RecordUpload(requested, processed, failed+lost)
	}
	if s.Logger != nil {
		attributes := []any{
			"claimed_count", requested,
			"synced_count", processed,
			"failed_count", failed,
			"lost_claim_count", lost,
			"duration_seconds", time.Since(started).Seconds(),
		}
		switch {
		case err != nil:
			s.Logger.Error(
				"Notion synchronization batch failed",
				append(attributes, "error", err)...,
			)
		case failed > 0 || lost > 0:
			s.Logger.Error(
				"Notion synchronization batch completed with errors",
				append(attributes, "errors", result["errors"])...,
			)
		default:
			s.Logger.Info(
				"Notion synchronization batch completed",
				attributes...,
			)
		}
	}
	return result, err
}

func (s *InstrumentedSyncService) Start(ctx context.Context) {
	if s.Interval <= 0 {
		s.Service.Start(ctx)
		return
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.cancel != nil {
		return
	}
	workerCtx, cancel := context.WithCancel(ctx)
	s.cancel = cancel
	s.done = make(chan struct{})
	go s.runLoop(workerCtx)
}

func (s *InstrumentedSyncService) Stop(ctx context.Context) error {
	s.mu.Lock()
	cancel := s.cancel
	done := s.done
	s.cancel = nil
	s.done = nil
	s.mu.Unlock()
	if cancel != nil {
		cancel()
	}
	if done != nil {
		select {
		case <-done:
		case <-ctx.Done():
			return ctx.Err()
		}
	}
	return s.Service.Stop(ctx)
}

func (s *InstrumentedSyncService) runLoop(ctx context.Context) {
	defer close(s.done)
	ticker := time.NewTicker(s.Interval)
	defer ticker.Stop()
	for {
		_, _ = s.RunOnce(ctx)
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func intValue(value any) int {
	switch typed := value.(type) {
	case int:
		return typed
	case int64:
		return int(typed)
	case float64:
		return int(typed)
	default:
		return 0
	}
}
