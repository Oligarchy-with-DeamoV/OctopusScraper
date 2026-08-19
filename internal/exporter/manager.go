package exporter

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"sync"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
)

const (
	StatusPending    = "pending"
	StatusProcessing = "processing"
	StatusRetry      = "retry"
	StatusSynced     = "synced"
	StatusFailed     = "failed"
)

const claimUpdateTimeout = 5 * time.Second

type Target interface {
	ID() string
	Deliver(context.Context, content.Content) error
}

type Queue interface {
	RegisterTarget(context.Context, string, bool) error
	Claim(context.Context, string, string, int, time.Duration, int) ([]content.Content, error)
	Renew(context.Context, string, string, string, time.Duration) (bool, error)
	Complete(context.Context, string, string, string) (bool, error)
	Fail(context.Context, string, string, string, string, int) (bool, error)
}

type Options struct {
	BatchSize   int
	Interval    time.Duration
	Lease       time.Duration
	MaxAttempts int
}

type SyncError struct {
	ExporterID string `json:"exporter_id,omitempty"`
	ContentID  string `json:"content_id,omitempty"`
	Message    string `json:"message"`
}

type BatchStats struct {
	Enabled        bool                   `json:"enabled"`
	Busy           bool                   `json:"busy"`
	ClaimedCount   int                    `json:"claimed_count"`
	SyncedCount    int                    `json:"synced_count"`
	FailedCount    int                    `json:"failed_count"`
	LostClaimCount int                    `json:"lost_claim_count"`
	Errors         []SyncError            `json:"errors,omitempty"`
	Targets        map[string]TargetStats `json:"targets,omitempty"`
}

type TargetStats struct {
	Enabled        bool        `json:"enabled"`
	Busy           bool        `json:"busy"`
	ClaimedCount   int         `json:"claimed_count"`
	SyncedCount    int         `json:"synced_count"`
	FailedCount    int         `json:"failed_count"`
	LostClaimCount int         `json:"lost_claim_count"`
	Errors         []SyncError `json:"errors,omitempty"`
}

type Manager struct {
	options Options
	queue   Queue

	mu      sync.Mutex
	workers map[string]*targetWorker
}

func NewManager(options Options, queue Queue, targets ...Target) (*Manager, error) {
	if queue == nil {
		return nil, errors.New("exporter queue is required")
	}
	if options.BatchSize <= 0 {
		options.BatchSize = 1
	}
	if options.Lease <= 0 {
		options.Lease = time.Minute
	}
	if options.MaxAttempts <= 0 {
		options.MaxAttempts = 1
	}
	manager := &Manager{
		options: options,
		queue:   queue,
		workers: make(map[string]*targetWorker, len(targets)),
	}
	for _, target := range targets {
		if err := manager.addTarget(target); err != nil {
			return nil, err
		}
	}
	return manager, nil
}

func (m *Manager) Start(ctx context.Context) {
	m.mu.Lock()
	workers := make([]*targetWorker, 0, len(m.workers))
	for _, worker := range m.workers {
		workers = append(workers, worker)
	}
	m.mu.Unlock()
	for _, worker := range workers {
		worker.start(ctx)
	}
}

func (m *Manager) Stop(ctx context.Context) error {
	m.mu.Lock()
	workers := make([]*targetWorker, 0, len(m.workers))
	for _, worker := range m.workers {
		workers = append(workers, worker)
	}
	m.mu.Unlock()
	errs := make([]error, 0, len(workers))
	for _, worker := range workers {
		if err := worker.stop(ctx); err != nil {
			errs = append(errs, fmt.Errorf("stop exporter %s: %w", worker.id, err))
		}
	}
	return errors.Join(errs...)
}

func (m *Manager) RunOnce(ctx context.Context) (map[string]any, error) {
	m.mu.Lock()
	workers := make([]*targetWorker, 0, len(m.workers))
	for _, worker := range m.workers {
		workers = append(workers, worker)
	}
	m.mu.Unlock()
	if len(workers) == 0 {
		return BatchStats{Enabled: false}.toMap(), nil
	}

	type result struct {
		id    string
		stats TargetStats
		err   error
	}
	results := make(chan result, len(workers))
	for _, worker := range workers {
		go func(worker *targetWorker) {
			stats, err := worker.runBatch(ctx)
			results <- result{id: worker.id, stats: stats, err: err}
		}(worker)
	}

	stats := BatchStats{Enabled: true, Targets: make(map[string]TargetStats, len(workers))}
	errs := make([]error, 0)
	for range workers {
		result := <-results
		stats.Targets[result.id] = result.stats
		stats.Busy = stats.Busy || result.stats.Busy
		stats.ClaimedCount += result.stats.ClaimedCount
		stats.SyncedCount += result.stats.SyncedCount
		stats.FailedCount += result.stats.FailedCount
		stats.LostClaimCount += result.stats.LostClaimCount
		stats.Errors = append(stats.Errors, result.stats.Errors...)
		if result.err != nil {
			errs = append(errs, result.err)
		}
	}
	return stats.toMap(), errors.Join(errs...)
}

func (m *Manager) addTarget(target Target) error {
	if target == nil {
		return errors.New("exporter target is nil")
	}
	id := target.ID()
	if id == "" {
		return errors.New("exporter target ID is required")
	}
	if _, exists := m.workers[id]; exists {
		return fmt.Errorf("duplicate exporter target %q", id)
	}
	m.workers[id] = newTargetWorker(id, target, m.queue, m.options)
	return nil
}

type targetWorker struct {
	id       string
	target   Target
	queue    Queue
	options  Options
	workerID string

	runMu   sync.Mutex
	running bool

	workerMu sync.Mutex
	cancel   context.CancelFunc
	done     chan struct{}

	operationMu      sync.Mutex
	operationCancels map[string]context.CancelFunc
	operationWG      sync.WaitGroup
	stopping         bool
}

func newTargetWorker(id string, target Target, queue Queue, options Options) *targetWorker {
	return &targetWorker{
		id:               id,
		target:           target,
		queue:            queue,
		options:          options,
		workerID:         newToken(id + "-exporter"),
		operationCancels: make(map[string]context.CancelFunc),
	}
}

func (w *targetWorker) start(ctx context.Context) {
	w.workerMu.Lock()
	defer w.workerMu.Unlock()
	if w.cancel != nil {
		return
	}
	w.operationMu.Lock()
	w.stopping = false
	w.operationMu.Unlock()
	workerCtx, cancel := context.WithCancel(ctx)
	w.cancel = cancel
	w.done = make(chan struct{})
	go w.runLoop(workerCtx)
}

func (w *targetWorker) stop(ctx context.Context) error {
	w.workerMu.Lock()
	cancel := w.cancel
	done := w.done
	w.cancel = nil
	w.done = nil
	w.workerMu.Unlock()
	if cancel != nil {
		cancel()
	}
	w.operationMu.Lock()
	w.stopping = true
	operationCancels := make([]context.CancelFunc, 0, len(w.operationCancels))
	for _, cancelOperation := range w.operationCancels {
		operationCancels = append(operationCancels, cancelOperation)
	}
	w.operationMu.Unlock()
	for _, cancelOperation := range operationCancels {
		cancelOperation()
	}

	stopped := make(chan struct{})
	go func() {
		if done != nil {
			<-done
		}
		w.operationWG.Wait()
		close(stopped)
	}()
	select {
	case <-stopped:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

func (w *targetWorker) runBatch(ctx context.Context) (TargetStats, error) {
	stats := TargetStats{Enabled: true}
	var batchErrors []error
	if !w.acquireRun() {
		stats.Busy = true
		return stats, nil
	}
	defer w.releaseRun()

	for processed := 0; processed < w.options.BatchSize; processed++ {
		if ctx.Err() != nil {
			break
		}
		claimID := fmt.Sprintf("%s:%s", w.workerID, newToken("claim"))
		contents, err := w.queue.Claim(ctx, w.id, claimID, 1, w.options.Lease, w.options.MaxAttempts)
		if err != nil {
			stats.Errors = append(stats.Errors, SyncError{ExporterID: w.id, Message: err.Error()})
			batchErrors = append(batchErrors, err)
			break
		}
		if len(contents) == 0 {
			break
		}
		current := contents[0]
		stats.ClaimedCount++
		renewCtx, cancelRenew := claimUpdateContext(ctx)
		renewed, err := w.queue.Renew(renewCtx, w.id, current.ContentID, claimID, w.options.Lease)
		cancelRenew()
		if err != nil {
			stats.Errors = append(stats.Errors, SyncError{ExporterID: w.id, ContentID: current.ContentID, Message: err.Error()})
			stats.LostClaimCount++
			batchErrors = append(batchErrors, err)
			continue
		}
		if !renewed {
			stats.LostClaimCount++
			continue
		}
		haltBatch := false
		func() {
			operationCtx, cancelOperation, completeOperation, ok := w.beginClaimOperation(ctx)
			if !ok {
				haltBatch = true
				return
			}
			defer completeOperation()

			claimLost := make(chan error, 1)
			var heartbeatWG sync.WaitGroup
			heartbeatWG.Add(1)
			go func(contentID string) {
				defer heartbeatWG.Done()
				w.heartbeatClaim(operationCtx, contentID, claimID, claimLost, cancelOperation)
			}(current.ContentID)

			deliverErr := w.target.Deliver(operationCtx, current)
			cancelOperation()
			heartbeatWG.Wait()
			var heartbeatErr error
			select {
			case heartbeatErr = <-claimLost:
			default:
			}
			if heartbeatErr != nil {
				stats.LostClaimCount++
				stats.Errors = append(stats.Errors, SyncError{
					ExporterID: w.id,
					ContentID:  current.ContentID,
					Message:    heartbeatErr.Error(),
				})
				return
			}
			if deliverErr == nil {
				updateCtx, cancelUpdate := claimUpdateContext(ctx)
				marked, err := w.queue.Complete(updateCtx, w.id, current.ContentID, claimID)
				cancelUpdate()
				if err != nil {
					stats.Errors = append(stats.Errors, SyncError{
						ExporterID: w.id,
						ContentID:  current.ContentID,
						Message:    err.Error(),
					})
					stats.LostClaimCount++
					batchErrors = append(batchErrors, err)
					return
				}
				if !marked {
					stats.LostClaimCount++
					return
				}
				stats.SyncedCount++
				return
			}

			updateCtx, cancelUpdate := claimUpdateContext(ctx)
			marked, err := w.queue.Fail(updateCtx, w.id, current.ContentID, claimID, deliverErr.Error(), w.options.MaxAttempts)
			cancelUpdate()
			if err != nil {
				stats.Errors = append(stats.Errors, SyncError{
					ExporterID: w.id,
					ContentID:  current.ContentID,
					Message:    err.Error(),
				})
				stats.LostClaimCount++
				batchErrors = append(batchErrors, err)
				return
			}
			if !marked {
				stats.LostClaimCount++
				return
			}
			stats.FailedCount++
			stats.Errors = append(stats.Errors, SyncError{
				ExporterID: w.id,
				ContentID:  current.ContentID,
				Message:    deliverErr.Error(),
			})
		}()
		if haltBatch {
			break
		}
	}
	return stats, errors.Join(batchErrors...)
}

func (w *targetWorker) beginClaimOperation(ctx context.Context) (context.Context, context.CancelFunc, func(), bool) {
	operationCtx, cancelOperation := context.WithCancel(context.WithoutCancel(ctx))
	operationID := newToken("operation")
	w.operationMu.Lock()
	if w.stopping {
		w.operationMu.Unlock()
		cancelOperation()
		return nil, nil, nil, false
	}
	w.operationCancels[operationID] = cancelOperation
	w.operationWG.Add(1)
	w.operationMu.Unlock()

	var completeOnce sync.Once
	completeOperation := func() {
		completeOnce.Do(func() {
			cancelOperation()
			w.operationMu.Lock()
			delete(w.operationCancels, operationID)
			w.operationMu.Unlock()
			w.operationWG.Done()
		})
	}
	return operationCtx, cancelOperation, completeOperation, true
}

func (w *targetWorker) heartbeatClaim(ctx context.Context, contentID string, claimID string, lost chan<- error, cancelOperation context.CancelFunc) {
	interval := w.options.Lease / 3
	if interval <= 0 {
		interval = 100 * time.Millisecond
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			renewed, err := w.queue.Renew(ctx, w.id, contentID, claimID, w.options.Lease)
			if ctx.Err() != nil {
				return
			}
			if err != nil {
				select {
				case lost <- fmt.Errorf("renew %s exporter claim: %w", w.id, err):
				default:
				}
				cancelOperation()
				return
			}
			if !renewed {
				select {
				case lost <- fmt.Errorf("%s exporter claim was lost", w.id):
				default:
				}
				cancelOperation()
				return
			}
		}
	}
}

func (w *targetWorker) runLoop(ctx context.Context) {
	defer close(w.done)
	interval := w.options.Interval
	if interval <= 0 {
		interval = time.Second
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		_, _ = w.runBatch(ctx)
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (w *targetWorker) acquireRun() bool {
	w.runMu.Lock()
	defer w.runMu.Unlock()
	if w.running {
		return false
	}
	w.running = true
	return true
}

func (w *targetWorker) releaseRun() {
	w.runMu.Lock()
	w.running = false
	w.runMu.Unlock()
}

func claimUpdateContext(ctx context.Context) (context.Context, context.CancelFunc) {
	return context.WithTimeout(context.WithoutCancel(ctx), claimUpdateTimeout)
}

func (s BatchStats) toMap() map[string]any {
	result := map[string]any{
		"enabled":          s.Enabled,
		"busy":             s.Busy,
		"claimed_count":    s.ClaimedCount,
		"synced_count":     s.SyncedCount,
		"failed_count":     s.FailedCount,
		"lost_claim_count": s.LostClaimCount,
		"errors":           []map[string]any{},
	}
	if len(s.Errors) > 0 {
		result["errors"] = syncErrorsToMaps(s.Errors)
	}
	if len(s.Targets) > 0 {
		targets := make(map[string]any, len(s.Targets))
		for id, stats := range s.Targets {
			targets[id] = stats.toMap()
		}
		result["targets"] = targets
	}
	return result
}

func (s TargetStats) toMap() map[string]any {
	result := map[string]any{
		"enabled":          s.Enabled,
		"busy":             s.Busy,
		"claimed_count":    s.ClaimedCount,
		"synced_count":     s.SyncedCount,
		"failed_count":     s.FailedCount,
		"lost_claim_count": s.LostClaimCount,
		"errors":           []map[string]any{},
	}
	if len(s.Errors) > 0 {
		result["errors"] = syncErrorsToMaps(s.Errors)
	}
	return result
}

func syncErrorsToMaps(syncErrors []SyncError) []map[string]any {
	errors := make([]map[string]any, 0, len(syncErrors))
	for _, syncErr := range syncErrors {
		entry := map[string]any{
			"error": syncErr.Message,
		}
		if syncErr.ContentID != "" {
			entry["content_id"] = syncErr.ContentID
		}
		if syncErr.ExporterID != "" {
			entry["exporter_id"] = syncErr.ExporterID
		}
		errors = append(errors, entry)
	}
	return errors
}

func newToken(prefix string) string {
	buffer := make([]byte, 8)
	if _, err := rand.Read(buffer); err != nil {
		return fmt.Sprintf("%s-%d", prefix, time.Now().UnixNano())
	}
	return fmt.Sprintf("%s-%s", prefix, hex.EncodeToString(buffer))
}
