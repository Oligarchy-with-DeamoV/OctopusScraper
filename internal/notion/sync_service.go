package notion

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/app"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/config"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/storage"
)

var _ app.SyncService = (*SyncService)(nil)

const claimUpdateTimeout = 5 * time.Second

type SyncError struct {
	ContentID string `json:"content_id"`
	Message   string `json:"message"`
}

type BatchStats struct {
	Enabled        bool        `json:"enabled"`
	Busy           bool        `json:"busy"`
	ClaimedCount   int         `json:"claimed_count"`
	SyncedCount    int         `json:"synced_count"`
	FailedCount    int         `json:"failed_count"`
	LostClaimCount int         `json:"lost_claim_count"`
	Errors         []SyncError `json:"errors,omitempty"`
}

type SyncService struct {
	config   config.NotionConfig
	store    storage.CanonicalStore
	uploader Uploader
	workerID string
	now      func() time.Time

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

func NewSyncService(cfg config.NotionConfig, store storage.CanonicalStore, uploader Uploader) *SyncService {
	return &SyncService{
		config:   cfg,
		store:    store,
		uploader: uploader,
		workerID: newToken("notion-sync"),
		now:      time.Now,
		operationCancels: make(
			map[string]context.CancelFunc,
		),
	}
}

func (s *SyncService) Start(ctx context.Context) {
	if !s.config.Enabled {
		return
	}
	s.workerMu.Lock()
	defer s.workerMu.Unlock()
	if s.cancel != nil {
		return
	}
	s.operationMu.Lock()
	s.stopping = false
	s.operationMu.Unlock()
	workerCtx, cancel := context.WithCancel(ctx)
	s.cancel = cancel
	s.done = make(chan struct{})
	go s.runLoop(workerCtx)
}

func (s *SyncService) Stop(ctx context.Context) error {
	s.workerMu.Lock()
	cancel := s.cancel
	done := s.done
	s.cancel = nil
	s.done = nil
	s.workerMu.Unlock()
	if cancel != nil {
		cancel()
	}
	s.operationMu.Lock()
	s.stopping = true
	operationCancels := make(
		[]context.CancelFunc,
		0,
		len(s.operationCancels),
	)
	for _, cancelOperation := range s.operationCancels {
		operationCancels = append(
			operationCancels,
			cancelOperation,
		)
	}
	s.operationMu.Unlock()
	for _, cancelOperation := range operationCancels {
		cancelOperation()
	}

	stopped := make(chan struct{})
	go func() {
		if done != nil {
			<-done
		}
		s.operationWG.Wait()
		close(stopped)
	}()
	select {
	case <-stopped:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

func (s *SyncService) RunOnce(ctx context.Context) (map[string]any, error) {
	stats, err := s.runBatch(ctx)
	return stats.toMap(), err
}

func (s *SyncService) runBatch(ctx context.Context) (BatchStats, error) {
	stats := BatchStats{Enabled: s.config.Enabled}
	var batchErrors []error
	if !s.config.Enabled {
		return stats, nil
	}
	if !s.acquireRun() {
		stats.Busy = true
		return stats, nil
	}
	defer s.releaseRun()
	if s.uploader == nil {
		stats.Errors = append(stats.Errors, SyncError{Message: "notion uploader is nil"})
		return stats, errors.New("notion uploader is nil")
	}

	for processed := 0; processed < s.config.BatchSize; processed++ {
		if ctx.Err() != nil {
			break
		}
		claimID := fmt.Sprintf("%s:%s", s.workerID, newToken("claim"))
		contents, err := s.store.ClaimContents(ctx, claimID, 1, s.config.Lease, s.config.MaxAttempts)
		if err != nil {
			stats.Errors = append(stats.Errors, SyncError{Message: err.Error()})
			batchErrors = append(batchErrors, err)
			break
		}
		if len(contents) == 0 {
			break
		}
		current := contents[0]
		stats.ClaimedCount++
		renewCtx, cancelRenew := claimUpdateContext(ctx)
		renewed, err := s.store.RenewClaim(
			renewCtx,
			current.ContentID,
			claimID,
			s.config.Lease,
		)
		cancelRenew()
		if err != nil {
			stats.Errors = append(stats.Errors, SyncError{ContentID: current.ContentID, Message: err.Error()})
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
			operationCtx, cancelOperation, completeOperation, ok :=
				s.beginClaimOperation(ctx)
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
				s.heartbeatClaims(
					operationCtx,
					contentID,
					claimID,
					claimLost,
					cancelOperation,
				)
			}(current.ContentID)

			results, uploadErr := s.uploader.StoreContents(
				operationCtx,
				[]content.Content{current},
				true,
			)
			cancelOperation()
			heartbeatWG.Wait()
			var heartbeatErr error
			select {
			case heartbeatErr = <-claimLost:
			default:
			}
			if heartbeatErr != nil {
				stats.LostClaimCount++
				stats.Errors = append(
					stats.Errors,
					SyncError{
						ContentID: current.ContentID,
						Message:   heartbeatErr.Error(),
					},
				)
				return
			}
			success := uploadErr == nil &&
				len(results) == 1 &&
				results[0]
			if success {
				updateCtx, cancelUpdate := claimUpdateContext(ctx)
				marked, err := s.store.MarkSynced(
					updateCtx,
					current.ContentID,
					claimID,
				)
				cancelUpdate()
				if err != nil {
					stats.Errors = append(stats.Errors, SyncError{
						ContentID: current.ContentID,
						Message:   err.Error(),
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
			message := "Notion upload failed"
			if uploadErr != nil {
				message = uploadErr.Error()
			}
			updateCtx, cancelUpdate := claimUpdateContext(ctx)
			marked, err := s.store.MarkSyncFailed(
				updateCtx,
				current.ContentID,
				claimID,
				message,
				s.config.MaxAttempts,
			)
			cancelUpdate()
			if err != nil {
				stats.Errors = append(stats.Errors, SyncError{
					ContentID: current.ContentID,
					Message:   err.Error(),
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
				ContentID: current.ContentID,
				Message:   message,
			})
		}()
		if haltBatch {
			break
		}
	}
	return stats, joinErrors(batchErrors)
}

func (s *SyncService) beginClaimOperation(
	ctx context.Context,
) (
	context.Context,
	context.CancelFunc,
	func(),
	bool,
) {
	operationCtx, cancelOperation := context.WithCancel(
		context.WithoutCancel(ctx),
	)
	operationID := newToken("operation")
	s.operationMu.Lock()
	if s.stopping {
		s.operationMu.Unlock()
		cancelOperation()
		return nil, nil, nil, false
	}
	s.operationCancels[operationID] = cancelOperation
	s.operationWG.Add(1)
	s.operationMu.Unlock()

	var completeOnce sync.Once
	completeOperation := func() {
		completeOnce.Do(func() {
			cancelOperation()
			s.operationMu.Lock()
			delete(s.operationCancels, operationID)
			s.operationMu.Unlock()
			s.operationWG.Done()
		})
	}
	return operationCtx, cancelOperation, completeOperation, true
}

func claimUpdateContext(ctx context.Context) (
	context.Context,
	context.CancelFunc,
) {
	return context.WithTimeout(context.WithoutCancel(ctx), claimUpdateTimeout)
}

func (s *SyncService) heartbeatClaims(
	ctx context.Context,
	contentID string,
	claimID string,
	lost chan<- error,
	cancelOperation context.CancelFunc,
) {
	interval := s.config.Lease / 3
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
			renewed, err := s.store.RenewClaim(ctx, contentID, claimID, s.config.Lease)
			if ctx.Err() != nil {
				return
			}
			if err != nil {
				select {
				case lost <- fmt.Errorf("renew Notion synchronization claim: %w", err):
				default:
				}
				cancelOperation()
				return
			}
			if !renewed {
				select {
				case lost <- errors.New("Notion synchronization claim was lost"):
				default:
				}
				cancelOperation()
				return
			}
		}
	}
}

func (s *SyncService) runLoop(ctx context.Context) {
	defer close(s.done)
	interval := s.config.Interval
	if interval <= 0 {
		interval = time.Second
	}
	ticker := time.NewTicker(interval)
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

func (s *SyncService) acquireRun() bool {
	s.runMu.Lock()
	defer s.runMu.Unlock()
	if s.running {
		return false
	}
	s.running = true
	return true
}

func (s *SyncService) releaseRun() {
	s.runMu.Lock()
	s.running = false
	s.runMu.Unlock()
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
		errors := make([]map[string]any, 0, len(s.Errors))
		for _, syncErr := range s.Errors {
			entry := map[string]any{
				"error": syncErr.Message,
			}
			if syncErr.ContentID != "" {
				entry["content_id"] = syncErr.ContentID
			}
			errors = append(errors, entry)
		}
		result["errors"] = errors
	}
	return result
}
