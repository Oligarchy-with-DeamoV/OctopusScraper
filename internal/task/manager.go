package task

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/config"
	"github.com/google/uuid"
)

var (
	ErrQueueFull       = errors.New("task queue is full")
	errManagerStopping = errors.New("task manager is stopping")
)

const (
	interruptedTaskMessage = "Task interrupted by service restart"
	forcedShutdownWait     = time.Second
	retryAdmissionDelay    = 100 * time.Millisecond
)

// ExecutionResult reports one scraper attempt.
type ExecutionResult struct {
	ItemsFetched   int
	ItemsProcessed int
	ItemsUploaded  int
	Metadata       map[string]any
}

// Executor runs one scraper task.
type Executor interface {
	Execute(context.Context, ScraperTask) (ExecutionResult, error)
}

// Observer receives task-manager metric updates.
type Observer interface {
	Configure(queueCapacity, workerCapacity int)
	Submitted()
	Completed(duration time.Duration, itemsFetched int)
	Failed(duration time.Duration)
	Retried()
	Cancelled()
	State(queued, running int)
}

type nopObserver struct{}

func (nopObserver) Configure(int, int)           {}
func (nopObserver) Submitted()                   {}
func (nopObserver) Completed(time.Duration, int) {}
func (nopObserver) Failed(time.Duration)         {}
func (nopObserver) Retried()                     {}
func (nopObserver) Cancelled()                   {}
func (nopObserver) State(int, int)               {}

// Statistics is the admin task-manager response contract.
type Statistics struct {
	TotalTasks                int64   `json:"total_tasks"`
	CompletedTasks            int64   `json:"completed_tasks"`
	FailedTasks               int64   `json:"failed_tasks"`
	CancelledTasks            int64   `json:"cancelled_tasks"`
	CurrentQueueSize          int     `json:"current_queue_size"`
	RunningTasksCount         int     `json:"running_tasks_count"`
	PersistedTaskResultsCount int     `json:"persisted_task_results_count"`
	SuccessRatePercent        float64 `json:"success_rate_percent"`
	AverageTaskDuration       float64 `json:"average_task_duration_seconds"`
	RecentTasksCount          int     `json:"recent_tasks_count"`
	QueueCapacity             int     `json:"queue_capacity"`
	MaxConcurrentTasks        int     `json:"max_concurrent_tasks"`
}

type counters struct {
	total     int64
	completed int64
	failed    int64
	cancelled int64
	persisted int
}

// Manager owns the bounded priority queue and worker lifecycle.
type Manager struct {
	logger    *slog.Logger
	executor  Executor
	observer  Observer
	maxQueue  int
	workers   int
	retention time.Duration
	store     *ResultStore

	mu          sync.RWMutex
	cond        *sync.Cond
	queue       priorityQueue
	results     map[string]*Result
	running     map[string]context.CancelFunc
	cancelled   map[string]struct{}
	retryTimers map[string]*time.Timer
	stopping    bool
	sequence    uint64
	counters    counters
	wg          sync.WaitGroup
	cleanupDone chan struct{}
	stopCleanup chan struct{}
}

func NewManager(
	logger *slog.Logger,
	executor Executor,
	maxConcurrentTasks int,
	maxQueueSize int,
	retention time.Duration,
	store *ResultStore,
	observer Observer,
) (*Manager, error) {
	if executor == nil {
		return nil, errors.New("task executor is required")
	}
	if logger == nil {
		logger = slog.Default()
	}
	if maxConcurrentTasks <= 0 || maxQueueSize <= 0 {
		return nil, errors.New("task worker and queue capacities must be positive")
	}
	if observer == nil {
		observer = nopObserver{}
	}
	manager := &Manager{
		logger:      logger,
		executor:    executor,
		observer:    observer,
		maxQueue:    maxQueueSize,
		workers:     maxConcurrentTasks,
		retention:   retention,
		store:       store,
		results:     make(map[string]*Result),
		running:     make(map[string]context.CancelFunc),
		cancelled:   make(map[string]struct{}),
		retryTimers: make(map[string]*time.Timer),
		cleanupDone: make(chan struct{}),
		stopCleanup: make(chan struct{}),
	}
	manager.cond = sync.NewCond(&manager.mu)
	if store != nil {
		persistenceAvailable := true
		results, err := store.LoadRecent(context.Background(), retention)
		if err != nil {
			logger.Error(
				"Task result history unavailable; starting without history",
				"error",
				err,
			)
			persistenceAvailable = false
			results = nil
		}
		recoveredAt := time.Now()
		for index := range results {
			value := results[index]
			if markInterruptedResult(&value, recoveredAt) {
				if err := store.Save(context.Background(), value); err != nil {
					logger.Error(
						"Failed to persist interrupted task recovery",
						"task_id",
						value.TaskID,
						"error",
						err,
					)
					persistenceAvailable = false
				}
				logger.Warn(
					"Recovered interrupted task result",
					"task_id",
					value.TaskID,
					"previous_status",
					results[index].Status,
				)
			}
			manager.results[value.TaskID] = &value
		}
		manager.counters.persisted = len(results)
		if !persistenceAvailable {
			if err := store.Close(); err != nil {
				logger.Error(
					"Failed to close unavailable task result store",
					"error",
					err,
				)
			}
			manager.store = nil
			logger.Warn(
				"Task result persistence disabled after startup failure",
			)
		}
	}
	observer.Configure(maxQueueSize, maxConcurrentTasks)
	for range maxConcurrentTasks {
		manager.wg.Add(1)
		go manager.worker()
	}
	go manager.cleanupLoop()
	logger.Info("TaskManager started")
	return manager, nil
}

func markInterruptedResult(result *Result, recoveredAt time.Time) bool {
	switch result.Status {
	case StatusPending, StatusRunning, StatusRetrying:
	default:
		return false
	}
	duration := recoveredAt.Sub(result.StartTime).Seconds()
	if duration < 0 {
		duration = 0
	}
	message := interruptedTaskMessage
	result.Status = StatusFailed
	result.EndTime = &recoveredAt
	result.Duration = &duration
	result.ErrorMessage = &message
	return true
}

func NewScraperTask(
	scraper configScraper,
	fetchParams map[string]any,
	timeout time.Duration,
) ScraperTask {
	now := time.Now()
	if timeout <= 0 {
		timeout = 5 * time.Minute
	}
	return ScraperTask{
		ID:              uuid.NewString(),
		ScraperName:     scraper.Name,
		ScraperConfig:   scraper.Config,
		FetchParams:     cloneMap(fetchParams),
		Priority:        priorityFromInt(scraper.Priority),
		MaxRetries:      3,
		RetryDelay:      time.Minute,
		Timeout:         timeout,
		CreatedAt:       now,
		ScheduledAt:     now,
		Tags:            []string{scraper.Fetcher},
		DefaultKeywords: append([]string(nil), scraper.DefaultKeywords...),
		Metadata: map[string]any{
			"hub_root": scraper.HubRoot,
			"route":    scraper.Route,
			"fetcher":  scraper.Fetcher,
		},
	}
}

// ConfigScraperInput keeps task creation independent from config internals.
type configScraper struct {
	Config          config.ScraperConfig
	Name            string
	Priority        int
	Fetcher         string
	HubRoot         string
	Route           string
	DefaultKeywords []string
}

func NewTaskFromConfig(
	scraper config.ScraperConfig,
	timeout time.Duration,
) ScraperTask {
	return NewScraperTask(configScraper{
		Config:          scraper,
		Name:            scraper.Name,
		Priority:        scraper.Priority,
		Fetcher:         scraper.Fetcher,
		HubRoot:         scraper.HubRoot,
		Route:           scraper.Route,
		DefaultKeywords: scraper.DefaultKeywords,
	}, scraper.FetchParams, timeout)
}

func (m *Manager) Submit(task ScraperTask) (string, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.submitLocked(task)
}

func (m *Manager) submitLocked(task ScraperTask) (string, error) {
	if m.stopping {
		return "", errManagerStopping
	}
	if len(m.queue) >= m.maxQueue {
		return "", ErrQueueFull
	}
	if task.ID == "" {
		task.ID = uuid.NewString()
	}
	if task.CreatedAt.IsZero() {
		task.CreatedAt = time.Now()
	}
	if task.ScheduledAt.IsZero() {
		task.ScheduledAt = task.CreatedAt
	}
	result := &Result{
		TaskID:    task.ID,
		Status:    StatusPending,
		StartTime: time.Now(),
		Metadata:  cloneMap(task.Metadata),
	}
	m.results[task.ID] = result
	m.queue.pushTask(task, atomic.AddUint64(&m.sequence, 1))
	m.counters.total++
	m.persistLocked(result)
	m.observer.Submitted()
	m.observer.State(len(m.queue), len(m.running))
	m.cond.Signal()
	m.logger.Info(
		"Task submitted",
		"task_id", task.ID,
		"scraper_name", task.ScraperName,
		"priority", task.Priority,
		"queue_size", len(m.queue),
	)
	return task.ID, nil
}

func (m *Manager) SubmitBatch(
	batchID string,
	tasks []ScraperTask,
) ([]string, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.stopping {
		return nil, errManagerStopping
	}
	if len(tasks) > m.maxQueue-len(m.queue) {
		return nil, ErrQueueFull
	}
	submitted := make([]string, 0, len(tasks))
	for index := range tasks {
		if tasks[index].Metadata == nil {
			tasks[index].Metadata = map[string]any{}
		}
		tasks[index].Metadata["batch_id"] = batchID
		taskID, err := m.submitLocked(tasks[index])
		if err != nil {
			return submitted, err
		}
		submitted = append(submitted, taskID)
	}
	return submitted, nil
}

func (m *Manager) Cancel(taskID string) bool {
	m.mu.Lock()
	defer m.mu.Unlock()
	if cancel, ok := m.running[taskID]; ok {
		m.cancelled[taskID] = struct{}{}
		cancel()
		return true
	}
	result, ok := m.results[taskID]
	if !ok || result.Status != StatusPending {
		return false
	}
	m.queue.removeTask(taskID)
	now := time.Now()
	duration := now.Sub(result.StartTime).Seconds()
	result.Status = StatusCancelled
	result.EndTime = &now
	result.Duration = &duration
	m.counters.cancelled++
	m.persistLocked(result)
	m.observer.Cancelled()
	m.observer.State(len(m.queue), len(m.running))
	return true
}

func (m *Manager) Result(taskID string) (Result, bool) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	result, ok := m.results[taskID]
	if !ok {
		return Result{}, false
	}
	return cloneResult(*result), true
}

func (m *Manager) List(status *Status, limit int) []Result {
	m.mu.RLock()
	results := make([]Result, 0, len(m.results))
	for _, result := range m.results {
		if status != nil && result.Status != *status {
			continue
		}
		results = append(results, cloneResult(*result))
	}
	m.mu.RUnlock()
	sort.Slice(results, func(i, j int) bool {
		return results[i].StartTime.After(results[j].StartTime)
	})
	if limit < 0 {
		limit = 0
	}
	if limit > len(results) {
		limit = len(results)
	}
	return results[:limit]
}

func (m *Manager) Statistics() Statistics {
	m.mu.RLock()
	defer m.mu.RUnlock()
	finished := m.counters.completed + m.counters.failed
	successRate := 0.0
	if finished > 0 {
		successRate = float64(m.counters.completed) / float64(finished) * 100
	}
	cutoff := time.Now().Add(-time.Hour)
	var recent int
	var totalDuration float64
	for _, result := range m.results {
		if result.EndTime != nil && result.EndTime.After(cutoff) {
			recent++
			if result.Duration != nil {
				totalDuration += *result.Duration
			}
		}
	}
	average := 0.0
	if recent > 0 {
		average = totalDuration / float64(recent)
	}
	return Statistics{
		TotalTasks:                m.counters.total,
		CompletedTasks:            m.counters.completed,
		FailedTasks:               m.counters.failed,
		CancelledTasks:            m.counters.cancelled,
		CurrentQueueSize:          len(m.queue),
		RunningTasksCount:         len(m.running),
		PersistedTaskResultsCount: m.counters.persisted,
		SuccessRatePercent:        round2(successRate),
		AverageTaskDuration:       round2(average),
		RecentTasksCount:          recent,
		QueueCapacity:             m.maxQueue,
		MaxConcurrentTasks:        m.workers,
	}
}

func (m *Manager) Stop(ctx context.Context) error {
	m.mu.Lock()
	if m.stopping {
		m.mu.Unlock()
		return nil
	}
	m.stopping = true
	close(m.stopCleanup)
	for retryID, timer := range m.retryTimers {
		timer.Stop()
		delete(m.retryTimers, retryID)
	}
	for m.queue.Len() > 0 {
		task := m.queue.popTask()
		m.cancelPendingLocked(task.ID)
	}
	m.cond.Broadcast()
	m.mu.Unlock()

	wait := make(chan struct{})
	go func() {
		m.wg.Wait()
		close(wait)
	}()
	var stopErr error
	select {
	case <-wait:
	case <-ctx.Done():
		stopErr = ctx.Err()
		m.mu.Lock()
		for taskID, cancel := range m.running {
			m.cancelled[taskID] = struct{}{}
			cancel()
		}
		m.mu.Unlock()
		timer := time.NewTimer(forcedShutdownWait)
		select {
		case <-wait:
			timer.Stop()
		case <-timer.C:
			return stopErr
		}
	}
	<-m.cleanupDone
	if m.store != nil {
		return errors.Join(stopErr, m.store.Close())
	}
	return stopErr
}

func (m *Manager) worker() {
	defer m.wg.Done()
	for {
		m.mu.Lock()
		for m.queue.Len() == 0 && !m.stopping {
			m.cond.Wait()
		}
		if m.stopping {
			m.mu.Unlock()
			return
		}
		task := m.queue.popTask()
		result := m.results[task.ID]
		if result == nil || result.Status == StatusCancelled {
			m.mu.Unlock()
			continue
		}
		ctx, cancel := context.WithTimeout(context.Background(), task.Timeout)
		m.running[task.ID] = cancel
		result.Status = StatusRunning
		m.persistLocked(result)
		m.observer.State(len(m.queue), len(m.running))
		m.mu.Unlock()

		execution, err := m.executor.Execute(ctx, task)
		cancel()
		m.finish(task, execution, err)
	}
}

func (m *Manager) finish(
	task ScraperTask,
	execution ExecutionResult,
	executionErr error,
) {
	m.mu.Lock()
	defer m.mu.Unlock()
	delete(m.running, task.ID)
	_, cancelled := m.cancelled[task.ID]
	delete(m.cancelled, task.ID)
	result := m.results[task.ID]
	if result == nil {
		return
	}
	now := time.Now()
	duration := now.Sub(result.StartTime).Seconds()
	result.EndTime = &now
	result.Duration = &duration
	if result.Metadata == nil {
		result.Metadata = map[string]any{}
	}
	for key, value := range execution.Metadata {
		result.Metadata[key] = value
	}
	if cancelled {
		result.Status = StatusCancelled
		m.counters.cancelled++
		m.observer.Cancelled()
		m.logger.Info(
			"Task cancelled",
			"task_id", task.ID,
			"scraper_name", task.ScraperName,
		)
	} else if executionErr == nil {
		result.Status = StatusCompleted
		result.ItemsFetched = execution.ItemsFetched
		result.ItemsProcessed = execution.ItemsProcessed
		result.ItemsUploaded = execution.ItemsUploaded
		m.counters.completed++
		m.observer.Completed(time.Duration(duration*float64(time.Second)), execution.ItemsFetched)
		m.logger.Info(
			"Task completed successfully",
			"task_id", task.ID,
			"scraper_name", task.ScraperName,
			"items_fetched", execution.ItemsFetched,
			"duration_seconds", duration,
		)
	} else {
		message := fmt.Sprintf("Task execution failed: %s", executionErr)
		result.Status = StatusFailed
		result.ErrorMessage = &message
		m.counters.failed++
		m.observer.Failed(time.Duration(duration * float64(time.Second)))
		m.logger.Error(
			"Task failed",
			"task_id", task.ID,
			"scraper_name", task.ScraperName,
			"error", message,
			"retry_count", task.RetryCount,
			"max_retries", task.MaxRetries,
		)
		if task.RetryCount < task.MaxRetries && !m.stopping {
			retry := task
			retry.RetryCount++
			retry.ID = fmt.Sprintf("%s_retry_%d", task.ID, retry.RetryCount)
			delay := task.RetryDelay
			retry.ScheduledAt = time.Now().Add(delay)
			if retry.Metadata == nil {
				retry.Metadata = map[string]any{}
			}
			retry.Metadata["original_task_id"] = task.ID
			m.scheduleRetryLocked(retry, delay)
		}
	}
	m.persistLocked(result)
	m.observer.State(len(m.queue), len(m.running))
}

func (m *Manager) scheduleRetryLocked(
	retry ScraperTask,
	delay time.Duration,
) {
	retryID := retry.ID
	m.retryTimers[retryID] = time.AfterFunc(delay, func() {
		m.submitScheduledRetry(retry)
	})
}

func (m *Manager) submitScheduledRetry(retry ScraperTask) {
	m.mu.Lock()
	delete(m.retryTimers, retry.ID)
	_, err := m.submitLocked(retry)
	if errors.Is(err, ErrQueueFull) {
		m.scheduleRetryLocked(retry, retryAdmissionDelay)
		m.mu.Unlock()
		return
	}
	m.mu.Unlock()
	if err == nil {
		m.observer.Retried()
		return
	}
	if errors.Is(err, errManagerStopping) {
		return
	}
	m.logger.Error(
		"Failed to submit scheduled retry",
		"task_id", retry.ID,
		"error", err,
	)
}

func (m *Manager) cleanupLoop() {
	ticker := time.NewTicker(time.Hour)
	defer func() {
		ticker.Stop()
		close(m.cleanupDone)
	}()
	for {
		select {
		case <-m.stopCleanup:
			return
		case <-ticker.C:
		}
		m.mu.Lock()
		if m.stopping {
			m.mu.Unlock()
			return
		}
		cutoff := time.Now().Add(-m.retention)
		for taskID, result := range m.results {
			if result.EndTime != nil && result.EndTime.Before(cutoff) {
				delete(m.results, taskID)
			}
		}
		m.mu.Unlock()
		if m.store != nil {
			if _, err := m.store.DeleteOlderThan(context.Background(), cutoff); err != nil {
				m.logger.Error("Failed to clean up persisted task results", "error", err)
			}
		}
	}
}

func (m *Manager) persistLocked(result *Result) {
	if m.store == nil {
		return
	}
	if err := m.store.Save(context.Background(), cloneResult(*result)); err != nil {
		m.logger.Error(
			"Failed to persist task result",
			"task_id", result.TaskID,
			"error", err,
		)
	}
}

func (m *Manager) cancelPendingLocked(taskID string) {
	result := m.results[taskID]
	if result == nil || result.Status != StatusPending {
		return
	}
	now := time.Now()
	duration := now.Sub(result.StartTime).Seconds()
	result.Status = StatusCancelled
	result.EndTime = &now
	result.Duration = &duration
	m.counters.cancelled++
	m.persistLocked(result)
	m.observer.Cancelled()
}

func priorityFromInt(value int) Priority {
	switch {
	case value <= 3:
		return PriorityLow
	case value <= 6:
		return PriorityNormal
	case value <= 8:
		return PriorityHigh
	default:
		return PriorityCritical
	}
}

func cloneResult(result Result) Result {
	result.Metadata = cloneMap(result.Metadata)
	return result
}

func cloneMap(input map[string]any) map[string]any {
	if input == nil {
		return map[string]any{}
	}
	output := make(map[string]any, len(input))
	for key, value := range input {
		output[key] = value
	}
	return output
}

func round2(value float64) float64 {
	return float64(int64(value*100+0.5)) / 100
}

func ParseStatus(value string) (*Status, error) {
	if strings.TrimSpace(value) == "" {
		return nil, nil
	}
	status := Status(value)
	switch status {
	case StatusPending, StatusRunning, StatusCompleted, StatusFailed, StatusCancelled, StatusRetrying:
		return &status, nil
	default:
		return nil, fmt.Errorf("invalid task status: %s", value)
	}
}
