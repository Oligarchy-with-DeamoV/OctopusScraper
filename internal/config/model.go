package config

import "time"

const (
	MaxConfigFileBytes = 1024 * 1024
	MaxConfigDepth     = 20
	MaxConfigNodes     = 5000
	MaxStringLength    = 100000
)

// ScraperConfig defines one YAML-backed scraper.
type ScraperConfig struct {
	ID                      string                    `yaml:"id" json:"id"`
	Name                    string                    `yaml:"name" json:"name"`
	Enabled                 bool                      `yaml:"enabled" json:"enabled"`
	Fetcher                 string                    `yaml:"fetcher" json:"fetcher"`
	HubRoot                 string                    `yaml:"hub_root" json:"hub_root"`
	Route                   string                    `yaml:"route" json:"route"`
	FetchParams             map[string]any            `yaml:"fetch_params" json:"fetch_params"`
	Priority                int                       `yaml:"priority" json:"priority"`
	ContentProcessorConfigs map[string]map[string]any `yaml:"content_processor_configs" json:"content_processor_configs"`
	ContentProcessorOrder   []string                  `yaml:"-" json:"-"`
	ProcessorCategoryOrders map[string][]string       `yaml:"-" json:"-"`
	DefaultKeywords         []string                  `yaml:"default_keywords" json:"default_keywords"`
	SourcePath              string                    `yaml:"-" json:"source_path,omitempty"`
}

func (c ScraperConfig) Status() string {
	if c.Enabled {
		return "Active"
	}
	return "Inactive"
}

// FileSettings controls directory polling and debounce behavior.
type FileSettings struct {
	Directory    string
	PollInterval time.Duration
	Debounce     time.Duration
}

// DatabaseConfig controls PostgreSQL connectivity.
type DatabaseConfig struct {
	URL            string
	PoolSize       int32
	MaxOverflow    int32
	ConnectTimeout time.Duration
}

// NotionConfig controls optional downstream synchronization.
type NotionConfig struct {
	Enabled     bool
	APIKey      string
	DatabaseID  string
	Interval    time.Duration
	BatchSize   int
	MaxAttempts int
	Lease       time.Duration
	RetryDelay  time.Duration
}

// MCPConfig controls the optional read-only MCP endpoint.
type MCPConfig struct {
	Enabled              bool
	APIToken             string
	QueryTimeout         time.Duration
	MaxConcurrentQueries int
}

// ServiceConfig contains process-wide runtime settings.
type ServiceConfig struct {
	Host               string
	Port               int
	Debug              bool
	LogLevel           string
	LogFormat          string
	LogFile            string
	LogRetentionDays   int
	Environment        string
	ScraperConfig      FileSettings
	Database           DatabaseConfig
	Notion             NotionConfig
	MCP                MCPConfig
	MaxConcurrentTasks int
	MaxQueueSize       int
	ResultRetention    time.Duration
	TaskResultPath     string
	RSSConnectTimeout  time.Duration
	RSSReadTimeout     time.Duration
	SummaryMaxLength   int
	ScraperTimeout     time.Duration
	UploadTimeout      time.Duration
	UploadMaxRetries   int
}

// Version identifies one accepted configuration snapshot.
type Version struct {
	ID            string    `json:"version_id"`
	Timestamp     time.Time `json:"timestamp"`
	ConfigHash    string    `json:"config_hash"`
	ScrapersCount int       `json:"scrapers_count"`
	ChangeSummary string    `json:"change_summary"`
}

// ModifiedScraper describes one changed scraper and the fields that changed.
type ModifiedScraper struct {
	ID     string   `json:"id"`
	Fields []string `json:"fields"`
}

// Diff reports added, removed, and modified scraper IDs for one apply.
type Diff struct {
	Added    []string          `json:"added"`
	Removed  []string          `json:"removed"`
	Modified []ModifiedScraper `json:"modified"`
}

// Status reports the current configuration state.
type Status struct {
	Version      *Version
	Scrapers     []ScraperConfig
	LastCheck    time.Time
	NextCheck    time.Time
	Healthy      bool
	ErrorMessage string
	FileErrors   map[string]string
}
