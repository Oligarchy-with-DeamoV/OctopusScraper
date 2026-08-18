package task

import (
	"encoding/json"
	"fmt"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/config"
)

type Status string

const (
	StatusPending   Status = "pending"
	StatusRunning   Status = "running"
	StatusCompleted Status = "completed"
	StatusFailed    Status = "failed"
	StatusCancelled Status = "cancelled"
	StatusRetrying  Status = "retrying"
)

type Priority int

const (
	PriorityLow      Priority = 1
	PriorityNormal   Priority = 5
	PriorityHigh     Priority = 8
	PriorityCritical Priority = 10
)

// ScraperTask is one queued scraping attempt.
type ScraperTask struct {
	ID              string
	ScraperName     string
	ScraperConfig   config.ScraperConfig
	FetchParams     map[string]any
	Priority        Priority
	MaxRetries      int
	RetryCount      int
	RetryDelay      time.Duration
	Timeout         time.Duration
	CreatedAt       time.Time
	ScheduledAt     time.Time
	Tags            []string
	Metadata        map[string]any
	DefaultKeywords []string
}

// Result is the public task result contract.
type Result struct {
	TaskID         string         `json:"task_id"`
	Status         Status         `json:"status"`
	StartTime      time.Time      `json:"start_time"`
	EndTime        *time.Time     `json:"end_time"`
	Duration       *float64       `json:"duration_seconds"`
	ItemsFetched   int            `json:"items_fetched"`
	ItemsProcessed int            `json:"items_processed"`
	ItemsUploaded  int            `json:"items_uploaded"`
	ErrorMessage   *string        `json:"error_message"`
	Metadata       map[string]any `json:"metadata"`
}

func (r Result) MarshalJSON() ([]byte, error) {
	type alias Result
	return json.Marshal(struct {
		alias
		StartTime string  `json:"start_time"`
		EndTime   *string `json:"end_time"`
	}{
		alias:     alias(r),
		StartTime: formatTaskTime(r.StartTime),
		EndTime:   formatOptionalTime(r.EndTime),
	})
}

func formatOptionalTime(value *time.Time) *string {
	if value == nil {
		return nil
	}
	formatted := formatTaskTime(*value)
	return &formatted
}

func formatTaskTime(value time.Time) string {
	return value.Format("2006-01-02T15:04:05.999999999")
}

func parseTaskTime(value string) (time.Time, error) {
	for _, layout := range []string{
		time.RFC3339Nano,
		"2006-01-02T15:04:05.999999999",
	} {
		parsed, err := time.ParseInLocation(layout, value, time.Local)
		if err == nil {
			return parsed, nil
		}
	}
	return time.Time{}, fmt.Errorf("unsupported task timestamp %q", value)
}
