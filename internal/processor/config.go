package processor

import (
	"fmt"
	"math"
	"net/url"
	"os"
	"regexp"
	"strconv"
	"strings"
	"time"
)

const (
	defaultPriority            = 100
	defaultHTTPTimeout         = 30 * time.Second
	defaultBrowserTimeout      = 60 * time.Second
	defaultUserAgent           = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
	defaultOpenAIBaseURL       = "https://api.openai.com/v1"
	defaultSummaryModel        = "gpt-3.5-turbo"
	defaultLLMTimeout          = 30 * time.Second
	defaultRetryTimes          = 3
	defaultSummaryMaxLength    = 200
	defaultMaxTokens           = 1000
	defaultTemperature         = 0.7
	defaultMaxKeywords         = 10
	defaultKeywordsCount       = 3
	defaultMinKeywordLength    = 2
	defaultMaxKeywordLength    = 20
	defaultMaxTags             = 5
	defaultConfidenceThreshold = 0.5
	defaultMaxTagLength        = 50
)

var summaryStyles = map[string]struct{}{
	"concise":       {},
	"detailed":      {},
	"bullet_points": {},
	"executive":     {},
}

type HTMLContentProcessorConfig struct {
	Priority       int
	Timeout        time.Duration
	UserAgent      string
	BrowserlessURL string
	UseBrowser     bool
	BrowserTimeout time.Duration
}

type BaseLLMProcessorConfig struct {
	Priority       int
	Provider       string
	ModelName      string
	MaxTokens      int
	Temperature    float64
	Timeout        time.Duration
	RetryTimes     int
	APIKey         string
	APIBase        string
	BaseURL        string
	FailFast       bool
	EnableFallback bool
	observer       LLMOperationObserver
}

type SummaryProcessorConfig struct {
	BaseLLMProcessorConfig
	MaxSummaryLength int
	SummaryStyle     string
}

type KeywordsProcessorConfig struct {
	BaseLLMProcessorConfig
	KeywordsCount      int
	MaxKeywords        int
	MinKeywordLength   int
	MaxKeywordLength   int
	ExcludeCommonWords bool
	IncludePhrases     bool
	LanguagePreference string
	ExcludePatterns    []string
	CustomStopWords    []string
	MinImportanceScore float64
}

type TagsProcessorConfig struct {
	BaseLLMProcessorConfig
	AvailableTags       []string
	CustomCategories    map[string][]string
	CustomCategoryOrder []string
	MaxTagsCount        int
	MaxTags             int
	AllowNewTags        bool
	ConfidenceThreshold float64
}

func parseHTMLConfig(raw map[string]any) (HTMLContentProcessorConfig, error) {
	if err := validateConfigFields(
		raw,
		configFieldSpec{key: "priority", kind: configInteger},
		configFieldSpec{key: "timeout_seconds", kind: configInteger},
		configFieldSpec{key: "timeout", kind: configInteger},
		configFieldSpec{key: "user_agent", kind: configString},
		configFieldSpec{key: "browserless_url", kind: configString},
		configFieldSpec{key: "browser_url", kind: configString},
		configFieldSpec{key: "cdp_url", kind: configString},
		configFieldSpec{key: "use_browser", kind: configBoolean},
		configFieldSpec{key: "browser_timeout_ms", kind: configInteger},
		configFieldSpec{key: "browser_timeout", kind: configInteger},
	); err != nil {
		return HTMLContentProcessorConfig{}, err
	}
	timeout, err := getConfigDuration(
		raw,
		defaultHTTPTimeout,
		time.Second,
		"timeout_seconds",
		"timeout",
	)
	if err != nil {
		return HTMLContentProcessorConfig{}, err
	}
	browserTimeout, err := getConfigDuration(
		raw,
		defaultBrowserTimeout,
		time.Millisecond,
		"browser_timeout_ms",
		"browser_timeout",
	)
	if err != nil {
		return HTMLContentProcessorConfig{}, err
	}
	cfg := HTMLContentProcessorConfig{
		Priority:       getInt(raw, defaultPriority, "priority"),
		Timeout:        timeout,
		UserAgent:      getString(raw, defaultUserAgent, "user_agent"),
		BrowserlessURL: getString(raw, "", "browserless_url", "browser_url", "cdp_url"),
		UseBrowser:     getBool(raw, true, "use_browser"),
		BrowserTimeout: browserTimeout,
	}
	if cfg.Priority < 0 {
		return cfg, fmt.Errorf("priority must be non-negative")
	}
	if cfg.Timeout <= 0 {
		return cfg, fmt.Errorf("timeout must be positive")
	}
	if cfg.BrowserTimeout <= 0 {
		return cfg, fmt.Errorf("browser_timeout must be positive")
	}
	if cfg.UseBrowser && cfg.BrowserlessURL != "" {
		if err := validateBrowserEndpoint(cfg.BrowserlessURL); err != nil {
			return cfg, err
		}
	}
	return cfg, nil
}

func parseBaseLLMConfig(raw map[string]any) (BaseLLMProcessorConfig, error) {
	if err := validateConfigFields(
		raw,
		configFieldSpec{key: "priority", kind: configInteger},
		configFieldSpec{key: "llm_provider", kind: configString},
		configFieldSpec{key: "model_name", kind: configString},
		configFieldSpec{key: "model", kind: configString},
		configFieldSpec{key: "max_tokens", kind: configInteger},
		configFieldSpec{key: "temperature", kind: configNumber},
		configFieldSpec{key: "timeout_seconds", kind: configInteger},
		configFieldSpec{key: "timeout", kind: configInteger},
		configFieldSpec{key: "retry_times", kind: configInteger},
		configFieldSpec{key: "api_key", kind: configString, nullable: true},
		configFieldSpec{key: "api_base", kind: configString, nullable: true},
		configFieldSpec{key: "base_url", kind: configString, nullable: true},
		configFieldSpec{key: "fail_fast", kind: configBoolean},
		configFieldSpec{key: "enable_fallback", kind: configBoolean},
	); err != nil {
		return BaseLLMProcessorConfig{}, err
	}
	defaultModelName := envOrDefault("OPENAI_MODEL_NAME", defaultSummaryModel)
	defaultBaseURL := envOrDefault("OPENAI_BASE_URL", defaultOpenAIBaseURL)
	defaultAPIKey := strings.TrimSpace(os.Getenv("OPENAI_API_KEY"))
	_, apiKeyProvided := raw["api_key"]
	_, apiBaseProvided := raw["api_base"]
	_, baseURLProvided := raw["base_url"]
	timeout, err := getConfigDuration(
		raw,
		defaultLLMTimeout,
		time.Second,
		"timeout_seconds",
		"timeout",
	)
	if err != nil {
		return BaseLLMProcessorConfig{}, err
	}
	cfg := BaseLLMProcessorConfig{
		Priority:       getInt(raw, defaultPriority, "priority"),
		Provider:       getString(raw, "openai", "llm_provider"),
		ModelName:      getString(raw, defaultModelName, "model_name", "model"),
		MaxTokens:      getInt(raw, defaultMaxTokens, "max_tokens"),
		Temperature:    getFloat(raw, defaultTemperature, "temperature"),
		Timeout:        timeout,
		RetryTimes:     getInt(raw, defaultRetryTimes, "retry_times"),
		APIKey:         getString(raw, defaultAPIKey, "api_key"),
		APIBase:        getString(raw, defaultBaseURL, "api_base"),
		BaseURL:        getString(raw, "", "base_url"),
		FailFast:       getBool(raw, false, "fail_fast"),
		EnableFallback: getBool(raw, true, "enable_fallback"),
	}
	if cfg.Priority < 0 {
		return cfg, fmt.Errorf("priority must be non-negative")
	}
	if cfg.Provider != "openai" {
		return cfg, fmt.Errorf("llm_provider %q is unsupported; use openai with an OpenAI-compatible base_url", cfg.Provider)
	}
	if cfg.ModelName == "" {
		return cfg, fmt.Errorf("model_name must be a non-empty string")
	}
	if cfg.MaxTokens <= 0 {
		return cfg, fmt.Errorf("max_tokens must be positive")
	}
	if cfg.Temperature < 0 || cfg.Temperature > 2 {
		return cfg, fmt.Errorf("temperature must be between 0 and 2")
	}
	if cfg.Timeout <= 0 {
		return cfg, fmt.Errorf("timeout must be positive")
	}
	if cfg.RetryTimes <= 0 {
		return cfg, fmt.Errorf("retry_times must be positive")
	}
	if cfg.BaseURL == "" {
		cfg.BaseURL = cfg.APIBase
	}
	if cfg.BaseURL == "" {
		cfg.BaseURL = defaultOpenAIBaseURL
	}
	if err := validateHTTPBaseURL(cfg.BaseURL); err != nil {
		return cfg, err
	}
	if value, exists := raw["api_key"]; exists && value == nil {
		cfg.APIKey = ""
	} else if (apiBaseProvided || baseURLProvided) &&
		!apiKeyProvided &&
		!sameHTTPBaseURL(cfg.BaseURL, defaultBaseURL) {
		cfg.APIKey = ""
	}
	return cfg, nil
}

func sameHTTPBaseURL(left string, right string) bool {
	leftURL, leftErr := url.Parse(strings.TrimSpace(left))
	rightURL, rightErr := url.Parse(strings.TrimSpace(right))
	if leftErr != nil || rightErr != nil {
		return false
	}
	return strings.EqualFold(leftURL.Scheme, rightURL.Scheme) &&
		strings.EqualFold(leftURL.Host, rightURL.Host) &&
		strings.TrimRight(leftURL.EscapedPath(), "/") ==
			strings.TrimRight(rightURL.EscapedPath(), "/") &&
		leftURL.RawQuery == rightURL.RawQuery
}

func envOrDefault(key string, fallback string) string {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback
	}
	return value
}

func parseSummaryConfig(raw map[string]any) (SummaryProcessorConfig, error) {
	if err := validateConfigFields(
		raw,
		configFieldSpec{key: "max_summary_length", kind: configInteger},
		configFieldSpec{key: "summary_style", kind: configString},
		configFieldSpec{key: "preserve_structure", kind: configBoolean},
		configFieldSpec{key: "include_key_points", kind: configBoolean},
	); err != nil {
		return SummaryProcessorConfig{}, err
	}
	base, err := parseBaseLLMConfig(raw)
	if err != nil {
		return SummaryProcessorConfig{}, err
	}
	cfg := SummaryProcessorConfig{
		BaseLLMProcessorConfig: base,
		MaxSummaryLength:       getInt(raw, defaultSummaryMaxLength, "max_summary_length"),
		SummaryStyle:           getString(raw, "concise", "summary_style"),
	}
	if cfg.MaxSummaryLength <= 0 {
		return cfg, fmt.Errorf("max_summary_length must be positive")
	}
	if _, ok := summaryStyles[cfg.SummaryStyle]; !ok {
		return cfg, fmt.Errorf("summary_style must be one of concise, detailed, bullet_points, executive")
	}
	return cfg, nil
}

func parseKeywordsConfig(raw map[string]any) (KeywordsProcessorConfig, error) {
	if err := validateConfigFields(
		raw,
		configFieldSpec{key: "keywords_count", kind: configInteger},
		configFieldSpec{key: "max_keywords", kind: configInteger},
		configFieldSpec{key: "min_keyword_length", kind: configInteger},
		configFieldSpec{key: "max_keyword_length", kind: configInteger},
		configFieldSpec{key: "exclude_common_words", kind: configBoolean},
		configFieldSpec{key: "include_phrases", kind: configBoolean},
		configFieldSpec{key: "language_preference", kind: configString},
		configFieldSpec{key: "exclude_patterns", kind: configStringList, nullable: true},
		configFieldSpec{key: "custom_stop_words", kind: configStringList, nullable: true},
		configFieldSpec{key: "min_importance_score", kind: configNumber},
	); err != nil {
		return KeywordsProcessorConfig{}, err
	}
	base, err := parseBaseLLMConfig(raw)
	if err != nil {
		return KeywordsProcessorConfig{}, err
	}
	cfg := KeywordsProcessorConfig{
		BaseLLMProcessorConfig: base,
		KeywordsCount:          getInt(raw, defaultKeywordsCount, "keywords_count"),
		MaxKeywords:            getInt(raw, defaultMaxKeywords, "max_keywords"),
		MinKeywordLength:       getInt(raw, defaultMinKeywordLength, "min_keyword_length"),
		MaxKeywordLength:       getInt(raw, defaultMaxKeywordLength, "max_keyword_length"),
		ExcludeCommonWords:     getBool(raw, true, "exclude_common_words"),
		IncludePhrases:         getBool(raw, true, "include_phrases"),
		LanguagePreference:     getString(raw, "mixed", "language_preference"),
		ExcludePatterns:        getStringSlice(raw, "exclude_patterns"),
		CustomStopWords:        getStringSlice(raw, "custom_stop_words"),
		MinImportanceScore:     getFloat(raw, 0, "min_importance_score"),
	}
	if cfg.MaxKeywords <= 0 || cfg.KeywordsCount <= 0 {
		return cfg, fmt.Errorf("keywords_count and max_keywords must be positive")
	}
	if cfg.MinKeywordLength <= 0 || cfg.MaxKeywordLength < cfg.MinKeywordLength {
		return cfg, fmt.Errorf("keyword length bounds are invalid")
	}
	switch cfg.LanguagePreference {
	case "en", "zh", "mixed":
	default:
		return cfg, fmt.Errorf("language_preference must be one of en, zh, mixed")
	}
	if cfg.MinImportanceScore < 0 || cfg.MinImportanceScore > 1 {
		return cfg, fmt.Errorf("min_importance_score must be between 0 and 1")
	}
	for _, pattern := range cfg.ExcludePatterns {
		if _, err := regexp.Compile(pattern); err != nil {
			return cfg, fmt.Errorf("invalid exclude_patterns entry %q: %w", pattern, err)
		}
	}
	return cfg, nil
}

func parseTagsConfig(raw map[string]any) (TagsProcessorConfig, error) {
	if err := validateConfigFields(
		raw,
		configFieldSpec{key: "available_tags", kind: configStringList},
		configFieldSpec{key: "max_tags", kind: configInteger},
		configFieldSpec{key: "max_tags_count", kind: configInteger},
		configFieldSpec{key: "allow_new_tags", kind: configBoolean},
		configFieldSpec{key: "confidence_threshold", kind: configNumber},
		configFieldSpec{key: "custom_categories", kind: configStringListMap},
	); err != nil {
		return TagsProcessorConfig{}, err
	}
	base, err := parseBaseLLMConfig(raw)
	if err != nil {
		return TagsProcessorConfig{}, err
	}
	maxTags := getInt(raw, defaultMaxTags, "max_tags")
	maxTagsCount := getInt(raw, defaultMaxTags, "max_tags_count")
	cfg := TagsProcessorConfig{
		BaseLLMProcessorConfig: base,
		AvailableTags:          getStringSlice(raw, "available_tags"),
		CustomCategories:       getStringSliceMap(raw, "custom_categories"),
		MaxTagsCount:           maxTagsCount,
		MaxTags:                maxTags,
		AllowNewTags:           getBool(raw, true, "allow_new_tags"),
		ConfidenceThreshold:    getFloat(raw, defaultConfidenceThreshold, "confidence_threshold"),
	}
	if cfg.MaxTags <= 0 || cfg.MaxTagsCount <= 0 {
		return cfg, fmt.Errorf("max_tags and max_tags_count must be positive")
	}
	if cfg.ConfidenceThreshold < 0 || cfg.ConfidenceThreshold > 1 {
		return cfg, fmt.Errorf("confidence_threshold must be between 0 and 1")
	}
	return cfg, nil
}

func getString(raw map[string]any, fallback string, keys ...string) string {
	for _, key := range keys {
		if value, ok := raw[key]; ok {
			switch typed := value.(type) {
			case string:
				return strings.TrimSpace(typed)
			}
		}
	}
	return fallback
}

func getBool(raw map[string]any, fallback bool, keys ...string) bool {
	for _, key := range keys {
		if value, ok := raw[key]; ok {
			switch typed := value.(type) {
			case bool:
				return typed
			case string:
				parsed, err := strconv.ParseBool(strings.TrimSpace(typed))
				if err == nil {
					return parsed
				}
			}
		}
	}
	return fallback
}

func getInt(raw map[string]any, fallback int, keys ...string) int {
	for _, key := range keys {
		if value, ok := raw[key]; ok {
			switch typed := value.(type) {
			case int:
				return typed
			case int8:
				return int(typed)
			case int16:
				return int(typed)
			case int32:
				return int(typed)
			case int64:
				return int(typed)
			case uint:
				return int(typed)
			case uint8:
				return int(typed)
			case uint16:
				return int(typed)
			case uint32:
				return int(typed)
			case uint64:
				return int(typed)
			case float32:
				return int(typed)
			case float64:
				return int(typed)
			case string:
				parsed, err := strconv.Atoi(strings.TrimSpace(typed))
				if err == nil {
					return parsed
				}
			}
		}
	}
	return fallback
}

func getFloat(raw map[string]any, fallback float64, keys ...string) float64 {
	for _, key := range keys {
		if value, ok := raw[key]; ok {
			switch typed := value.(type) {
			case float32:
				return float64(typed)
			case float64:
				return typed
			case int:
				return float64(typed)
			case int64:
				return float64(typed)
			case string:
				parsed, err := strconv.ParseFloat(strings.TrimSpace(typed), 64)
				if err == nil {
					return parsed
				}
			}
		}
	}
	return fallback
}

func getConfigDuration(
	raw map[string]any,
	fallback time.Duration,
	unit time.Duration,
	keys ...string,
) (time.Duration, error) {
	value := getInt(raw, int(fallback/unit), keys...)
	if value <= 0 {
		return 0, fmt.Errorf("%s must be positive", keys[0])
	}
	maxValue := time.Duration(1<<63-1) / unit
	if int64(value) > int64(maxValue) {
		return 0, fmt.Errorf("%s is too large", keys[0])
	}
	return time.Duration(value) * unit, nil
}

func getStringSlice(raw map[string]any, key string) []string {
	value, ok := raw[key]
	if !ok {
		return nil
	}
	switch typed := value.(type) {
	case []string:
		out := make([]string, 0, len(typed))
		for _, item := range typed {
			trimmed := strings.TrimSpace(item)
			if trimmed != "" {
				out = append(out, trimmed)
			}
		}
		return out
	case []any:
		out := make([]string, 0, len(typed))
		for _, item := range typed {
			stringItem, ok := item.(string)
			if !ok {
				continue
			}
			trimmed := strings.TrimSpace(stringItem)
			if trimmed != "" {
				out = append(out, trimmed)
			}
		}
		return out
	default:
		return nil
	}
}

func getStringSliceMap(raw map[string]any, key string) map[string][]string {
	value, ok := raw[key]
	if !ok {
		return nil
	}
	typed, ok := value.(map[string]any)
	if !ok {
		return nil
	}
	out := make(map[string][]string, len(typed))
	for category, entries := range typed {
		values := getStringSlice(map[string]any{"values": entries}, "values")
		out[category] = values
	}
	return out
}

type configValueKind int

const (
	configString configValueKind = iota
	configBoolean
	configInteger
	configNumber
	configStringList
	configStringListMap
)

type configFieldSpec struct {
	key      string
	kind     configValueKind
	nullable bool
}

func validateConfigFields(raw map[string]any, specs ...configFieldSpec) error {
	for _, spec := range specs {
		value, exists := raw[spec.key]
		if !exists {
			continue
		}
		if value == nil && spec.nullable {
			continue
		}
		if !validConfigValue(value, spec.kind) {
			return fmt.Errorf("%s must be %s", spec.key, configKindName(spec.kind))
		}
	}
	return nil
}

func validConfigValue(value any, kind configValueKind) bool {
	switch kind {
	case configString:
		_, ok := value.(string)
		return ok
	case configBoolean:
		_, ok := value.(bool)
		return ok
	case configInteger:
		return isInteger(value)
	case configNumber:
		number, ok := numericValue(value)
		return ok && !math.IsNaN(number) && !math.IsInf(number, 0)
	case configStringList:
		return isStringList(value)
	case configStringListMap:
		mapped, ok := value.(map[string]any)
		if !ok {
			return false
		}
		for _, entries := range mapped {
			if !isStringList(entries) {
				return false
			}
		}
		return true
	default:
		return false
	}
}

func configKindName(kind configValueKind) string {
	switch kind {
	case configString:
		return "a string"
	case configBoolean:
		return "a boolean"
	case configInteger:
		return "an integer"
	case configNumber:
		return "a finite number"
	case configStringList:
		return "a list of strings"
	case configStringListMap:
		return "a mapping of string lists"
	default:
		return "a valid value"
	}
}

func isInteger(value any) bool {
	maxInt := uint64(^uint(0) >> 1)
	minInt := -int64(maxInt) - 1
	switch typed := value.(type) {
	case int, int8, int16, int32, uint8, uint16, uint32:
		return true
	case int64:
		return typed >= minInt && (typed < 0 || uint64(typed) <= maxInt)
	case uint:
		return uint64(typed) <= maxInt
	case uint64:
		return typed <= maxInt
	default:
		return false
	}
}

func numericValue(value any) (float64, bool) {
	switch typed := value.(type) {
	case int:
		return float64(typed), true
	case int8:
		return float64(typed), true
	case int16:
		return float64(typed), true
	case int32:
		return float64(typed), true
	case int64:
		return float64(typed), true
	case uint:
		return float64(typed), true
	case uint8:
		return float64(typed), true
	case uint16:
		return float64(typed), true
	case uint32:
		return float64(typed), true
	case uint64:
		return float64(typed), true
	case float32:
		return float64(typed), true
	case float64:
		return typed, true
	default:
		return 0, false
	}
}

func isStringList(value any) bool {
	switch typed := value.(type) {
	case []string:
		return true
	case []any:
		for _, entry := range typed {
			if _, ok := entry.(string); !ok {
				return false
			}
		}
		return true
	default:
		return false
	}
}

func validateHTTPBaseURL(rawURL string) error {
	parsed, err := url.Parse(rawURL)
	if err != nil || parsed.Host == "" {
		return fmt.Errorf("base_url must be an absolute HTTP(S) URL")
	}
	if parsed.Scheme != "http" && parsed.Scheme != "https" {
		return fmt.Errorf("base_url must be an absolute HTTP(S) URL")
	}
	return nil
}
