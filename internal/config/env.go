package config

import (
	"errors"
	"fmt"
	"math"
	"net"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

const defaultTaskResultPath = ".octopus/task_results.sqlite3"

const (
	defaultMCPQueryTimeoutSeconds = 5
	defaultMCPConcurrentQueries   = 4
)

// LoadServiceConfigFromEnv resolves runtime defaults and env aliases.
func LoadServiceConfigFromEnv() (ServiceConfig, error) {
	databaseURL, err := databaseURLFromEnv()
	if err != nil {
		return ServiceConfig{}, err
	}
	debug, err := booleanValue(
		firstNonEmptyEnv("DEBUG", "OCTOPUS_DEBUG"),
		false,
		"DEBUG",
	)
	if err != nil {
		return ServiceConfig{}, err
	}
	notionEnabled, err := booleanValue(
		firstNonEmptyEnv("NOTION_SYNC_ENABLED"),
		false,
		"NOTION_SYNC_ENABLED",
	)
	if err != nil {
		return ServiceConfig{}, err
	}
	mcpEnabled, err := booleanValue(
		firstNonEmptyEnv("MCP_ENABLED"),
		false,
		"MCP_ENABLED",
	)
	if err != nil {
		return ServiceConfig{}, err
	}
	mcpToken := firstNonEmptyEnv("MCP_API_TOKEN")
	if mcpEnabled && mcpToken == "" {
		return ServiceConfig{}, errors.New("MCP_API_TOKEN is required when MCP_ENABLED=true")
	}
	servicePort, err := networkPort(
		firstNonEmptyEnv("SERVICE_PORT", "OCTOPUS_PORT"),
		8000,
		"SERVICE_PORT",
	)
	if err != nil {
		return ServiceConfig{}, err
	}
	pollInterval, err := positiveFloatDuration(firstNonEmptyEnv("SCRAPER_CONFIG_POLL_INTERVAL"), 1.0, "SCRAPER_CONFIG_POLL_INTERVAL")
	if err != nil {
		return ServiceConfig{}, err
	}
	debounce, err := positiveFloatDuration(firstNonEmptyEnv("SCRAPER_CONFIG_DEBOUNCE_SECONDS"), 0.75, "SCRAPER_CONFIG_DEBOUNCE_SECONDS")
	if err != nil {
		return ServiceConfig{}, err
	}
	poolSize, err := positiveInt(firstNonEmptyEnv("DB_POOL_SIZE"), 5, "DB_POOL_SIZE")
	if err != nil {
		return ServiceConfig{}, err
	}
	maxOverflow, err := nonNegativeInt(firstNonEmptyEnv("DB_MAX_OVERFLOW"), 5, "DB_MAX_OVERFLOW")
	if err != nil {
		return ServiceConfig{}, err
	}
	const maxPoolConnections = int64(1<<31 - 1)
	if int64(poolSize) > maxPoolConnections ||
		int64(maxOverflow) > maxPoolConnections ||
		int64(poolSize) > maxPoolConnections-int64(maxOverflow) {
		return ServiceConfig{}, fmt.Errorf(
			"DB_POOL_SIZE + DB_MAX_OVERFLOW must not exceed %d",
			maxPoolConnections,
		)
	}
	connectTimeout, err := positiveIntDuration(firstNonEmptyEnv("DB_CONNECT_TIMEOUT_SECONDS"), 10, "DB_CONNECT_TIMEOUT_SECONDS")
	if err != nil {
		return ServiceConfig{}, err
	}
	notionInterval, err := positiveIntDuration(firstNonEmptyEnv("NOTION_SYNC_INTERVAL_SECONDS"), 60, "NOTION_SYNC_INTERVAL_SECONDS")
	if err != nil {
		return ServiceConfig{}, err
	}
	notionBatchSize, err := positiveInt(firstNonEmptyEnv("NOTION_SYNC_BATCH_SIZE"), 100, "NOTION_SYNC_BATCH_SIZE")
	if err != nil {
		return ServiceConfig{}, err
	}
	notionMaxAttempts, err := positiveInt(firstNonEmptyEnv("NOTION_SYNC_MAX_ATTEMPTS"), 10, "NOTION_SYNC_MAX_ATTEMPTS")
	if err != nil {
		return ServiceConfig{}, err
	}
	notionLease, err := positiveIntDuration(firstNonEmptyEnv("NOTION_SYNC_LEASE_SECONDS"), 300, "NOTION_SYNC_LEASE_SECONDS")
	if err != nil {
		return ServiceConfig{}, err
	}
	notionRetryDelay, err := positiveIntDuration(firstNonEmptyEnv("NOTION_UPLOAD_RETRY_DELAY"), 30, "NOTION_UPLOAD_RETRY_DELAY")
	if err != nil {
		return ServiceConfig{}, err
	}
	maxConcurrentTasks, err := positiveInt(firstNonEmptyEnv("TASK_MANAGER_MAX_CONCURRENT", "MAX_CONCURRENT_TASKS"), 3, "TASK_MANAGER_MAX_CONCURRENT")
	if err != nil {
		return ServiceConfig{}, err
	}
	maxQueueSize, err := positiveInt(firstNonEmptyEnv("TASK_MANAGER_MAX_QUEUE_SIZE", "MAX_QUEUE_SIZE"), 1000, "TASK_MANAGER_MAX_QUEUE_SIZE")
	if err != nil {
		return ServiceConfig{}, err
	}
	resultRetention, err := positiveDuration(
		firstNonEmptyEnv("RESULT_RETENTION_HOURS"),
		48,
		"RESULT_RETENTION_HOURS",
		time.Hour,
	)
	if err != nil {
		return ServiceConfig{}, err
	}
	rssConnectTimeout, err := positiveFloatDuration(firstNonEmptyEnv("RSSHUB_CONNECT_TIMEOUT"), 10, "RSSHUB_CONNECT_TIMEOUT")
	if err != nil {
		return ServiceConfig{}, err
	}
	rssReadTimeout, err := positiveFloatDuration(firstNonEmptyEnv("RSSHUB_READ_TIMEOUT"), 1200, "RSSHUB_READ_TIMEOUT")
	if err != nil {
		return ServiceConfig{}, err
	}
	summaryMaxLength, err := positiveInt(firstNonEmptyEnv("OCTOPUS_SUMMARY_MAX_LENGTH"), 500, "OCTOPUS_SUMMARY_MAX_LENGTH")
	if err != nil {
		return ServiceConfig{}, err
	}
	scraperTimeout, err := positiveIntDuration(firstNonEmptyEnv("SCRAPER_TIMEOUT"), 10, "SCRAPER_TIMEOUT")
	if err != nil {
		return ServiceConfig{}, err
	}
	uploadTimeout, err := positiveIntDuration(firstNonEmptyEnv("UPLOAD_TIMEOUT"), 15, "UPLOAD_TIMEOUT")
	if err != nil {
		return ServiceConfig{}, err
	}
	uploadMaxRetries, err := positiveInt(firstNonEmptyEnv("UPLOAD_MAX_RETRIES"), 3, "UPLOAD_MAX_RETRIES")
	if err != nil {
		return ServiceConfig{}, err
	}

	serviceConfig := ServiceConfig{
		Host:        firstEnvOrDefault([]string{"SERVICE_HOST", "OCTOPUS_HOST"}, "0.0.0.0"),
		Port:        servicePort,
		Debug:       debug,
		LogLevel:    firstEnvOrDefault([]string{"LOG_LEVEL", "OCTOPUS_LOG_LEVEL"}, "INFO"),
		LogFormat:   firstEnvOrDefault([]string{"LOG_FORMAT", "OCTOPUS_LOG_FORMAT"}, "plain"),
		Environment: firstEnvOrDefault([]string{"ENVIRONMENT"}, "development"),
		ScraperConfig: FileSettings{
			Directory:    expandPath(firstEnvOrDefault([]string{"SCRAPER_CONFIG_DIR"}, "resources/scrapers.d")),
			PollInterval: pollInterval,
			Debounce:     debounce,
		},
		Database: DatabaseConfig{
			URL:            databaseURL,
			PoolSize:       int32(poolSize),
			MaxOverflow:    int32(maxOverflow),
			ConnectTimeout: connectTimeout,
		},
		Notion: NotionConfig{
			Enabled:     notionEnabled,
			APIKey:      firstEnvOrDefault([]string{"NOTION_API_KEY"}, ""),
			DatabaseID:  firstEnvOrDefault([]string{"NOTION_CONTENT_DATABASE_ID"}, ""),
			Interval:    notionInterval,
			BatchSize:   notionBatchSize,
			MaxAttempts: notionMaxAttempts,
			Lease:       notionLease,
			RetryDelay:  notionRetryDelay,
		},
		MCP: MCPConfig{
			Enabled:              mcpEnabled,
			APIToken:             mcpToken,
			QueryTimeout:         time.Duration(defaultMCPQueryTimeoutSeconds) * time.Second,
			MaxConcurrentQueries: defaultMCPConcurrentQueries,
		},
		MaxConcurrentTasks: maxConcurrentTasks,
		MaxQueueSize:       maxQueueSize,
		ResultRetention:    resultRetention,
		TaskResultPath:     expandPath(firstEnvOrDefault([]string{"OCTOPUS_TASK_RESULT_PATH", "TASK_RESULT_PATH", "TASK_RESULTS_PATH"}, defaultTaskResultPath)),
		RSSConnectTimeout:  rssConnectTimeout,
		RSSReadTimeout:     rssReadTimeout,
		SummaryMaxLength:   summaryMaxLength,
		ScraperTimeout:     scraperTimeout,
		UploadTimeout:      uploadTimeout,
		UploadMaxRetries:   uploadMaxRetries,
	}
	return serviceConfig, nil
}

// LoadServiceConfig resolves runtime defaults and env aliases.
func LoadServiceConfig() (ServiceConfig, error) {
	return LoadServiceConfigFromEnv()
}

func databaseURLFromEnv() (string, error) {
	if databaseURL := strings.TrimSpace(os.Getenv("DATABASE_URL")); databaseURL != "" {
		return normalizeDatabaseURL(databaseURL)
	}
	port, err := networkPort(firstNonEmptyEnv("DB_PORT"), 5432, "DB_PORT")
	if err != nil {
		return "", err
	}
	value := &url.URL{
		Scheme: "postgres",
		User: url.UserPassword(
			firstEnvOrDefault([]string{"POSTGRES_USER"}, "octopus"),
			firstEnvOrDefault([]string{"POSTGRES_PASSWORD"}, "octopus"),
		),
		Host: net.JoinHostPort(
			firstEnvOrDefault([]string{"DB_HOST"}, "localhost"),
			strconv.Itoa(port),
		),
		Path: firstEnvOrDefault([]string{"POSTGRES_DB"}, "octopus"),
	}
	return value.String(), nil
}

func normalizeDatabaseURL(databaseURL string) (string, error) {
	scheme, remainder, found := strings.Cut(databaseURL, "://")
	if !found {
		return databaseURL, nil
	}
	switch strings.ToLower(scheme) {
	case "postgres", "postgresql":
		return databaseURL, nil
	case "postgresql+psycopg", "postgresql+psycopg2":
		return "postgresql://" + remainder, nil
	case "sqlite", "sqlite3":
		return "", errors.New(
			"DATABASE_URL uses SQLite; the Go runtime requires PostgreSQL canonical storage",
		)
	default:
		return "", fmt.Errorf(
			"DATABASE_URL has unsupported scheme %q; expected PostgreSQL",
			scheme,
		)
	}
}

func firstNonEmptyEnv(names ...string) string {
	for _, name := range names {
		if value, ok := os.LookupEnv(name); ok && strings.TrimSpace(value) != "" {
			return strings.TrimSpace(value)
		}
	}
	return ""
}

func firstEnvOrDefault(names []string, fallback string) string {
	if value := firstNonEmptyEnv(names...); value != "" {
		return value
	}
	return fallback
}

func positiveInt(raw string, fallback int, field string) (int, error) {
	if raw == "" {
		return fallback, nil
	}
	value, err := strconv.Atoi(raw)
	if err != nil {
		return 0, fmt.Errorf("parse %s: %w", field, err)
	}
	if value <= 0 {
		return 0, fmt.Errorf("%s must be greater than zero", field)
	}
	return value, nil
}

func nonNegativeInt(raw string, fallback int, field string) (int, error) {
	if raw == "" {
		return fallback, nil
	}
	value, err := strconv.Atoi(raw)
	if err != nil {
		return 0, fmt.Errorf("parse %s: %w", field, err)
	}
	if value < 0 {
		return 0, fmt.Errorf("%s must be zero or greater", field)
	}
	return value, nil
}

func positiveFloatDuration(raw string, fallback float64, field string) (time.Duration, error) {
	if raw == "" {
		return time.Duration(fallback * float64(time.Second)), nil
	}
	value, err := strconv.ParseFloat(raw, 64)
	if err != nil {
		return 0, fmt.Errorf("parse %s: %w", field, err)
	}
	if value <= 0 {
		return 0, fmt.Errorf("%s must be greater than zero", field)
	}
	if math.IsNaN(value) || math.IsInf(value, 0) {
		return 0, fmt.Errorf("%s must be finite", field)
	}
	if value > float64(time.Duration(1<<63-1)/time.Second) {
		return 0, fmt.Errorf("%s is too large", field)
	}
	duration := time.Duration(value * float64(time.Second))
	if duration <= 0 {
		return 0, fmt.Errorf("%s is below one nanosecond", field)
	}
	return duration, nil
}

func positiveIntDuration(raw string, fallback int, field string) (time.Duration, error) {
	return positiveDuration(raw, fallback, field, time.Second)
}

func positiveDuration(
	raw string,
	fallback int,
	field string,
	unit time.Duration,
) (time.Duration, error) {
	value, err := positiveInt(raw, fallback, field)
	if err != nil {
		return 0, err
	}
	maxValue := time.Duration(1<<63-1) / unit
	if int64(value) > int64(maxValue) {
		return 0, fmt.Errorf("%s is too large", field)
	}
	return time.Duration(value) * unit, nil
}

func booleanValue(raw string, fallback bool, field string) (bool, error) {
	if raw == "" {
		return fallback, nil
	}
	value, err := strconv.ParseBool(raw)
	if err != nil {
		return false, fmt.Errorf("parse %s: %w", field, err)
	}
	return value, nil
}

func networkPort(raw string, fallback int, field string) (int, error) {
	value, err := positiveInt(raw, fallback, field)
	if err != nil {
		return 0, err
	}
	if value > 65535 {
		return 0, fmt.Errorf("%s must be between 1 and 65535", field)
	}
	return value, nil
}

func expandPath(path string) string {
	if path == "" {
		return path
	}
	if strings.HasPrefix(path, "~/") {
		home, err := os.UserHomeDir()
		if err == nil {
			return filepath.Join(home, strings.TrimPrefix(path, "~/"))
		}
	}
	return path
}
