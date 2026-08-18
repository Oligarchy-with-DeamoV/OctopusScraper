package observability

import (
	"io"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestMetricsRecordsAndExposesRuntimeState(t *testing.T) {
	metrics := NewMetrics("test-version")
	metrics.RefreshUptime()
	metrics.Configure(100, 4)
	metrics.Submitted()
	metrics.Retried()
	metrics.Cancelled()
	metrics.Failed(2 * time.Second)
	metrics.Completed(3*time.Second, 7)
	metrics.State(5, 2)
	metrics.RecordConfig(true)
	metrics.RecordConfig(false)
	for _, dependency := range []string{"rss", "notion", "llm"} {
		if err := metrics.RecordExternal(
			dependency,
			time.Second,
			dependency != "llm",
		); err != nil {
			t.Fatal(err)
		}
	}
	if err := metrics.RecordExternal("database", time.Second, true); err == nil {
		t.Fatal("expected unsupported dependency error")
	}
	metrics.RecordUpload(5, 4, 1)
	metrics.RecordUpload(0, 0, 0)

	request := httptest.NewRequest("GET", "/metrics", nil)
	response := httptest.NewRecorder()
	metrics.Handler().ServeHTTP(response, request)
	body, err := io.ReadAll(response.Result().Body)
	if err != nil {
		t.Fatal(err)
	}
	output := string(body)
	for _, expected := range []string{
		`octopus_build_info{version="test-version"} 1`,
		"octopus_task_queue_capacity 100",
		"octopus_task_worker_capacity 4",
		"octopus_tasks_submitted_total 1",
		"octopus_tasks_completed_total 1",
		"octopus_tasks_failed_total 1",
		`octopus_external_request_failures_total{dependency="llm"} 1`,
		`octopus_upload_items_total{outcome="processed"} 4`,
	} {
		if !strings.Contains(output, expected) {
			t.Fatalf("missing %q in metrics output", expected)
		}
	}
}
