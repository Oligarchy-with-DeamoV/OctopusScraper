package exporter

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
)

type fakeTarget struct {
	id      string
	err     error
	block   chan struct{}
	started chan struct{}
	mu      sync.Mutex
	items   []string
}

func (t *fakeTarget) ID() string { return t.id }

func (t *fakeTarget) Deliver(ctx context.Context, item content.Content) error {
	if t.started != nil {
		select {
		case t.started <- struct{}{}:
		default:
		}
	}
	if t.block != nil {
		select {
		case <-t.block:
		case <-ctx.Done():
			return ctx.Err()
		}
	}
	t.mu.Lock()
	t.items = append(t.items, item.ContentID)
	t.mu.Unlock()
	return t.err
}

type fakeQueue struct {
	mu               sync.Mutex
	claims           map[string][][]content.Content
	claimErr         error
	renewResults     []bool
	renewErr         error
	completeResult   bool
	completeErr      error
	failResult       bool
	failErr          error
	claimCalls       int
	completeCalls    []string
	failCalls        []string
	renewCalls       int
	registeredTarget []string
}

func (q *fakeQueue) RegisterTarget(_ context.Context, id string, _ bool) error {
	q.mu.Lock()
	defer q.mu.Unlock()
	q.registeredTarget = append(q.registeredTarget, id)
	return nil
}

func (q *fakeQueue) Claim(_ context.Context, exporterID, _ string, _ int, _ time.Duration, _ int) ([]content.Content, error) {
	q.mu.Lock()
	defer q.mu.Unlock()
	q.claimCalls++
	if q.claimErr != nil {
		return nil, q.claimErr
	}
	claims := q.claims[exporterID]
	if len(claims) == 0 {
		return nil, nil
	}
	result := claims[0]
	q.claims[exporterID] = claims[1:]
	return result, nil
}

func (q *fakeQueue) Renew(context.Context, string, string, string, time.Duration) (bool, error) {
	q.mu.Lock()
	defer q.mu.Unlock()
	q.renewCalls++
	if q.renewErr != nil {
		return false, q.renewErr
	}
	if len(q.renewResults) == 0 {
		return true, nil
	}
	result := q.renewResults[0]
	q.renewResults = q.renewResults[1:]
	return result, nil
}

func (q *fakeQueue) Complete(_ context.Context, exporterID, contentID, _ string) (bool, error) {
	q.mu.Lock()
	defer q.mu.Unlock()
	q.completeCalls = append(q.completeCalls, exporterID+":"+contentID)
	if q.completeErr != nil {
		return false, q.completeErr
	}
	if !q.completeResult {
		return false, nil
	}
	return true, nil
}

func (q *fakeQueue) Fail(_ context.Context, exporterID, contentID, _, _ string, _ int) (bool, error) {
	q.mu.Lock()
	defer q.mu.Unlock()
	q.failCalls = append(q.failCalls, exporterID+":"+contentID)
	if q.failErr != nil {
		return false, q.failErr
	}
	if !q.failResult {
		return false, nil
	}
	return true, nil
}

func TestNewManagerValidatesTargets(t *testing.T) {
	if _, err := NewManager(Options{}, nil); err == nil {
		t.Fatal("expected missing queue error")
	}
	queue := &fakeQueue{}
	if _, err := NewManager(Options{}, queue, nil); err == nil {
		t.Fatal("expected nil target error")
	}
	if _, err := NewManager(Options{}, queue, &fakeTarget{}); err == nil {
		t.Fatal("expected empty target ID error")
	}
	target := &fakeTarget{id: "same"}
	if _, err := NewManager(Options{}, queue, target, target); err == nil {
		t.Fatal("expected duplicate target error")
	}
	manager, err := NewManager(Options{}, queue, &fakeTarget{id: "one"})
	if err != nil {
		t.Fatal(err)
	}
	if manager.options.BatchSize != 1 || manager.options.Lease != time.Minute || manager.options.MaxAttempts != 1 {
		t.Fatalf("defaults = %#v", manager.options)
	}
}

func TestManagerRunOnceAggregatesIndependentTargets(t *testing.T) {
	queue := &fakeQueue{
		claims: map[string][][]content.Content{
			"notion": {{{ContentID: "one"}}},
			"future": {{{ContentID: "two"}}},
		},
		completeResult: true,
		failResult:     true,
	}
	notion := &fakeTarget{id: "notion"}
	future := &fakeTarget{id: "future", err: errors.New("future failed")}
	manager, err := NewManager(Options{BatchSize: 2, Lease: time.Hour, MaxAttempts: 3}, queue, notion, future)
	if err != nil {
		t.Fatal(err)
	}
	result, err := manager.RunOnce(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if result["claimed_count"] != 2 || result["synced_count"] != 1 || result["failed_count"] != 1 {
		t.Fatalf("result = %#v", result)
	}
	if len(queue.completeCalls) != 1 || len(queue.failCalls) != 1 {
		t.Fatalf("complete=%v fail=%v", queue.completeCalls, queue.failCalls)
	}
	targets := result["targets"].(map[string]any)
	if targets["notion"].(map[string]any)["synced_count"] != 1 {
		t.Fatalf("target results = %#v", targets)
	}
}

func TestManagerDisabledBusyAndInitialLostClaim(t *testing.T) {
	manager, err := NewManager(Options{}, &fakeQueue{})
	if err != nil {
		t.Fatal(err)
	}
	result, err := manager.RunOnce(context.Background())
	if err != nil || result["enabled"] != false {
		t.Fatalf("disabled result=%#v err=%v", result, err)
	}

	started := make(chan struct{}, 1)
	block := make(chan struct{})
	queue := &fakeQueue{
		claims:         map[string][][]content.Content{"one": {{{ContentID: "busy"}}}},
		renewResults:   []bool{true},
		completeResult: true,
	}
	target := &fakeTarget{id: "one", started: started, block: block}
	manager, err = NewManager(Options{Lease: time.Hour}, queue, target)
	if err != nil {
		t.Fatal(err)
	}
	done := make(chan struct{})
	go func() {
		_, _ = manager.RunOnce(context.Background())
		close(done)
	}()
	<-started
	busy, err := manager.RunOnce(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if busy["busy"] != true {
		t.Fatalf("busy result = %#v", busy)
	}
	close(block)
	<-done

	lostQueue := &fakeQueue{
		claims:       map[string][][]content.Content{"lost": {{{ContentID: "lost"}}}},
		renewResults: []bool{false},
	}
	manager, err = NewManager(Options{Lease: time.Hour}, lostQueue, &fakeTarget{id: "lost"})
	if err != nil {
		t.Fatal(err)
	}
	lost, err := manager.RunOnce(context.Background())
	if err != nil || lost["lost_claim_count"] != 1 {
		t.Fatalf("lost result=%#v err=%v", lost, err)
	}
}

func TestManagerCancelsDeliveryAfterHeartbeatLoss(t *testing.T) {
	started := make(chan struct{}, 1)
	queue := &fakeQueue{
		claims:       map[string][][]content.Content{"one": {{{ContentID: "one"}}}},
		renewResults: []bool{true, false},
	}
	manager, err := NewManager(
		Options{Lease: 30 * time.Millisecond},
		queue,
		&fakeTarget{id: "one", started: started, block: make(chan struct{})},
	)
	if err != nil {
		t.Fatal(err)
	}
	finished := make(chan map[string]any, 1)
	go func() {
		result, _ := manager.RunOnce(context.Background())
		finished <- result
	}()
	<-started
	select {
	case result := <-finished:
		if result["lost_claim_count"] != 1 {
			t.Fatalf("result = %#v", result)
		}
	case <-time.After(time.Second):
		t.Fatal("heartbeat loss did not cancel delivery")
	}
}

func TestManagerSurfacesQueueErrorsAndLostFinalization(t *testing.T) {
	queue := &fakeQueue{claimErr: errors.New("claim failed")}
	manager, err := NewManager(Options{}, queue, &fakeTarget{id: "one"})
	if err != nil {
		t.Fatal(err)
	}
	result, err := manager.RunOnce(context.Background())
	if err == nil || len(result["errors"].([]map[string]any)) != 1 {
		t.Fatalf("result=%#v err=%v", result, err)
	}

	for name, queue := range map[string]*fakeQueue{
		"renew error": {
			claims:   map[string][][]content.Content{"one": {{{ContentID: "one"}}}},
			renewErr: errors.New("renew failed"),
		},
		"complete error": {
			claims:         map[string][][]content.Content{"one": {{{ContentID: "one"}}}},
			completeErr:    errors.New("complete failed"),
			completeResult: true,
		},
		"complete lost": {
			claims: map[string][][]content.Content{"one": {{{ContentID: "one"}}}},
		},
		"fail error": {
			claims:     map[string][][]content.Content{"one": {{{ContentID: "one"}}}},
			failErr:    errors.New("fail failed"),
			failResult: true,
		},
		"fail lost": {
			claims: map[string][][]content.Content{"one": {{{ContentID: "one"}}}},
		},
	} {
		t.Run(name, func(t *testing.T) {
			target := &fakeTarget{id: "one"}
			if name == "fail error" || name == "fail lost" {
				target.err = errors.New("delivery failed")
			}
			manager, err := NewManager(Options{Lease: time.Hour}, queue, target)
			if err != nil {
				t.Fatal(err)
			}
			result, runErr := manager.RunOnce(context.Background())
			if result["lost_claim_count"] != 1 {
				t.Fatalf("result=%#v err=%v", result, runErr)
			}
			if (name == "renew error" || name == "complete error" || name == "fail error") && runErr == nil {
				t.Fatalf("expected queue error: %#v", result)
			}
		})
	}
}

func TestManagerStartStopCancelsActiveTarget(t *testing.T) {
	started := make(chan struct{}, 1)
	queue := &fakeQueue{
		claims:     map[string][][]content.Content{"one": {{{ContentID: "one"}}}},
		failResult: true,
	}
	manager, err := NewManager(
		Options{Interval: time.Hour, Lease: time.Hour},
		queue,
		&fakeTarget{id: "one", started: started, block: make(chan struct{})},
	)
	if err != nil {
		t.Fatal(err)
	}
	manager.Start(context.Background())
	manager.Start(context.Background())
	<-started
	stopCtx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	if err := manager.Stop(stopCtx); err != nil {
		t.Fatal(err)
	}
	if len(queue.failCalls) != 1 {
		t.Fatalf("fail calls = %v", queue.failCalls)
	}
	if err := manager.Stop(context.Background()); err != nil {
		t.Fatal(err)
	}
}

func TestStatsMapsOmitEmptyOptionalFields(t *testing.T) {
	stats := BatchStats{Enabled: true, Targets: map[string]TargetStats{"one": {Enabled: true}}}
	result := stats.toMap()
	if len(result["errors"].([]map[string]any)) != 0 {
		t.Fatalf("errors = %#v", result["errors"])
	}
	target := result["targets"].(map[string]any)["one"].(map[string]any)
	if len(target["errors"].([]map[string]any)) != 0 {
		t.Fatalf("target errors = %#v", target["errors"])
	}
}
