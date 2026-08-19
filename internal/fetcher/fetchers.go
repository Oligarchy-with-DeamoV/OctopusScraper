package fetcher

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"html"
	"io"
	"math"
	"net"
	"net/http"
	"net/url"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
	"github.com/mmcdole/gofeed"
)

const (
	NameRSSHub    = "rsshub"
	NameDirectRSS = "direct_rss"

	defaultSummaryMaxLength = 500
	defaultRSSHubConnect    = 10 * time.Second
	defaultRSSHubRead       = 1200 * time.Second
	defaultDirectRSSConnect = 10 * time.Second
	defaultDirectRSSRead    = 60 * time.Second
	maxFeedResponseBytes    = 20 << 20
)

var (
	tagPattern           = regexp.MustCompile(`(?is)<[^>]+>`)
	scriptPattern        = regexp.MustCompile(`(?is)<(script|style)[^>]*>.*?</(script|style)>`)
	codeBlockPattern     = regexp.MustCompile(`(?is)<pre\b[^>]*><code\b[^>]*>(.*?)</code></pre>`)
	inlineCodePattern    = regexp.MustCompile(`(?is)<code\b[^>]*>(.*?)</code>`)
	headingOnePattern    = regexp.MustCompile(`(?is)<h1\b[^>]*>(.*?)</h1>`)
	headingTwoPattern    = regexp.MustCompile(`(?is)<h2\b[^>]*>(.*?)</h2>`)
	headingThreePattern  = regexp.MustCompile(`(?is)<h3\b[^>]*>(.*?)</h3>`)
	headingOtherPattern  = regexp.MustCompile(`(?is)<h[4-6]\b[^>]*>(.*?)</h[4-6]>`)
	strongPattern        = regexp.MustCompile(`(?is)<(strong|b)\b[^>]*>(.*?)</(strong|b)>`)
	emphasisPattern      = regexp.MustCompile(`(?is)<(em|i)\b[^>]*>(.*?)</(em|i)>`)
	linkPattern          = regexp.MustCompile(`(?is)<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>`)
	paragraphPattern     = regexp.MustCompile(`(?is)</?(p|div|section|article|blockquote)[^>]*>`)
	lineBreakPattern     = regexp.MustCompile(`(?is)<br\s*/?>`)
	listItemOpenPattern  = regexp.MustCompile(`(?is)<li[^>]*>`)
	listItemClosePattern = regexp.MustCompile(`(?is)</li>`)
	whitespacePattern    = regexp.MustCompile(`[ \t\x0b\f\r]+`)
	newlinePattern       = regexp.MustCompile(`\n{3,}`)
)

type endpointConfig struct {
	HubRoot        string
	Route          string
	FetchParams    map[string]any
	ConnectTimeout time.Duration
	ReadTimeout    time.Duration
}

type baseFetcher struct {
	name             string
	config           endpointConfig
	client           *http.Client
	parser           *gofeed.Parser
	summaryMaxLength int
}

type FactoryOptions struct {
	RSSHubConnectTimeout    time.Duration
	RSSHubReadTimeout       time.Duration
	DirectRSSConnectTimeout time.Duration
	DirectRSSReadTimeout    time.Duration
	SummaryMaxLength        int
}

type fetcherFactory struct {
	options FactoryOptions
}

func NewFactory(options ...FactoryOptions) Factory {
	resolved := FactoryOptions{
		RSSHubConnectTimeout:    defaultRSSHubConnect,
		RSSHubReadTimeout:       defaultRSSHubRead,
		DirectRSSConnectTimeout: defaultDirectRSSConnect,
		DirectRSSReadTimeout:    defaultDirectRSSRead,
		SummaryMaxLength:        defaultSummaryMaxLength,
	}
	if len(options) > 0 {
		option := options[0]
		if option.RSSHubConnectTimeout > 0 {
			resolved.RSSHubConnectTimeout = option.RSSHubConnectTimeout
		}
		if option.RSSHubReadTimeout > 0 {
			resolved.RSSHubReadTimeout = option.RSSHubReadTimeout
		}
		if option.DirectRSSConnectTimeout > 0 {
			resolved.DirectRSSConnectTimeout = option.DirectRSSConnectTimeout
		}
		if option.DirectRSSReadTimeout > 0 {
			resolved.DirectRSSReadTimeout = option.DirectRSSReadTimeout
		}
		if option.SummaryMaxLength > 0 {
			resolved.SummaryMaxLength = option.SummaryMaxLength
		}
	}
	return &fetcherFactory{options: resolved}
}

func (f *fetcherFactory) Create(name string, rawConfig map[string]any) (Fetcher, error) {
	switch name {
	case NameRSSHub:
		return NewRSSHubFetcherWithOptions(rawConfig, f.options)
	case NameDirectRSS:
		return NewDirectRSSFetcherWithOptions(rawConfig, f.options)
	default:
		return nil, fmt.Errorf("unsupported fetcher %q", name)
	}
}

func NewRSSHubFetcher(rawConfig map[string]any) (Fetcher, error) {
	return NewRSSHubFetcherWithOptions(rawConfig, FactoryOptions{})
}

func NewRSSHubFetcherWithOptions(
	rawConfig map[string]any,
	options FactoryOptions,
) (Fetcher, error) {
	options = normalizeFactoryOptions(options)
	config, err := endpointConfigFromMap(
		rawConfig,
		options.RSSHubConnectTimeout,
		options.RSSHubReadTimeout,
	)
	if err != nil {
		return nil, err
	}
	if err := validateRSSHubQueryParams(config.FetchParams); err != nil {
		return nil, err
	}
	return &baseFetcher{
		name:             NameRSSHub,
		config:           config,
		client:           newHTTPClient(config.ConnectTimeout, config.ReadTimeout),
		parser:           gofeed.NewParser(),
		summaryMaxLength: options.SummaryMaxLength,
	}, nil
}

func validateRSSHubQueryParams(params map[string]any) error {
	values := make(url.Values)
	for key, value := range params {
		if err := addQueryValue(values, key, value); err != nil {
			return fmt.Errorf("fetch_params.%s: %w", key, err)
		}
	}
	return nil
}

func NewDirectRSSFetcher(rawConfig map[string]any) (Fetcher, error) {
	return NewDirectRSSFetcherWithOptions(rawConfig, FactoryOptions{})
}

func NewDirectRSSFetcherWithOptions(
	rawConfig map[string]any,
	options FactoryOptions,
) (Fetcher, error) {
	options = normalizeFactoryOptions(options)
	config, err := endpointConfigFromMap(
		rawConfig,
		options.DirectRSSConnectTimeout,
		options.DirectRSSReadTimeout,
	)
	if err != nil {
		return nil, err
	}
	return &baseFetcher{
		name:             NameDirectRSS,
		config:           config,
		client:           newHTTPClient(config.ConnectTimeout, config.ReadTimeout),
		parser:           gofeed.NewParser(),
		summaryMaxLength: options.SummaryMaxLength,
	}, nil
}

func (f *baseFetcher) Fetch(ctx context.Context, params map[string]any) ([]content.Content, error) {
	requestURL, mergedParams, err := f.requestURL(params)
	if err != nil {
		return nil, err
	}
	feed, err := f.fetchFeed(ctx, requestURL)
	if err != nil {
		return nil, err
	}
	contents := buildContents(feed, f.summaryMaxLength)
	if f.name == NameDirectRSS {
		contents, err = filterByTimeRange(contents, mergedParams)
		if err != nil {
			return nil, err
		}
	}
	return FilterQualityContents(contents), nil
}

func (f *baseFetcher) requestURL(params map[string]any) (string, map[string]any, error) {
	mergedParams := cloneParams(f.config.FetchParams)
	for key, value := range params {
		mergedParams[key] = value
	}
	baseURL, err := resolveURL(f.config.HubRoot, f.config.Route)
	if err != nil {
		return "", nil, err
	}
	if f.name != NameRSSHub {
		return baseURL, mergedParams, nil
	}
	parsed, err := url.Parse(baseURL)
	if err != nil {
		return "", nil, fmt.Errorf("parse RSSHub URL %q: %w", baseURL, err)
	}
	query := parsed.Query()
	keys := make([]string, 0, len(mergedParams))
	for key := range mergedParams {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	for _, key := range keys {
		if err := addQueryValue(query, key, mergedParams[key]); err != nil {
			return "", nil, fmt.Errorf("build RSSHub query for %q: %w", key, err)
		}
	}
	parsed.RawQuery = query.Encode()
	return parsed.String(), mergedParams, nil
}

func (f *baseFetcher) fetchFeed(ctx context.Context, requestURL string) (*gofeed.Feed, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, requestURL, nil)
	if err != nil {
		return nil, fmt.Errorf("create request for %q: %w", requestURL, err)
	}
	resp, err := f.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("fetch %s feed %q: %w", f.name, requestURL, err)
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return nil, fmt.Errorf("fetch %s feed %q: unexpected status %d: %s", f.name, requestURL, resp.StatusCode, strings.TrimSpace(string(body)))
	}
	body, err := readBoundedFeed(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read %s feed %q: %w", f.name, requestURL, err)
	}
	feed, err := f.parser.Parse(bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("parse %s feed %q: %w", f.name, requestURL, err)
	}
	return feed, nil
}

func readBoundedFeed(reader io.Reader) ([]byte, error) {
	limited := &io.LimitedReader{R: reader, N: maxFeedResponseBytes + 1}
	body, err := io.ReadAll(limited)
	if err != nil {
		return nil, err
	}
	if len(body) > maxFeedResponseBytes {
		return nil, fmt.Errorf(
			"response body exceeds %d bytes",
			maxFeedResponseBytes,
		)
	}
	return body, nil
}

func endpointConfigFromMap(raw map[string]any, defaultConnect, defaultRead time.Duration) (endpointConfig, error) {
	if raw == nil {
		raw = map[string]any{}
	}
	hubRoot, err := requiredStringValue(raw, "hub_root")
	if err != nil {
		return endpointConfig{}, err
	}
	route, err := requiredStringValue(raw, "route")
	if err != nil {
		return endpointConfig{}, err
	}
	fetchParams, err := optionalMapValue(raw, "fetch_params")
	if err != nil {
		return endpointConfig{}, err
	}
	connectTimeout, readTimeout, err := parseRequestTimeouts(raw, defaultConnect, defaultRead)
	if err != nil {
		return endpointConfig{}, err
	}
	return endpointConfig{
		HubRoot:        hubRoot,
		Route:          route,
		FetchParams:    fetchParams,
		ConnectTimeout: connectTimeout,
		ReadTimeout:    readTimeout,
	}, nil
}

func parseRequestTimeouts(raw map[string]any, defaultConnect, defaultRead time.Duration) (time.Duration, time.Duration, error) {
	connectTimeout := defaultConnect
	readTimeout := defaultRead
	if requestTimeout, ok := raw["request_timeout"]; ok && requestTimeout != nil {
		switch typed := requestTimeout.(type) {
		case []any:
			if len(typed) != 2 {
				return 0, 0, fmt.Errorf("request_timeout must contain [connect, read] seconds")
			}
			connectSeconds, err := numericSeconds(typed[0])
			if err != nil {
				return 0, 0, fmt.Errorf("request_timeout[0]: %w", err)
			}
			readSeconds, err := numericSeconds(typed[1])
			if err != nil {
				return 0, 0, fmt.Errorf("request_timeout[1]: %w", err)
			}
			connectTimeout = connectSeconds
			readTimeout = readSeconds
		default:
			readSeconds, err := numericSeconds(typed)
			if err != nil {
				return 0, 0, fmt.Errorf("request_timeout: %w", err)
			}
			readTimeout = readSeconds
		}
	}
	if value, ok := raw["connect_timeout_seconds"]; ok {
		seconds, err := numericSeconds(value)
		if err != nil {
			return 0, 0, fmt.Errorf("connect_timeout_seconds: %w", err)
		}
		connectTimeout = seconds
	}
	if value, ok := raw["read_timeout_seconds"]; ok {
		seconds, err := numericSeconds(value)
		if err != nil {
			return 0, 0, fmt.Errorf("read_timeout_seconds: %w", err)
		}
		readTimeout = seconds
	}
	return connectTimeout, readTimeout, nil
}

func requiredStringValue(raw map[string]any, field string) (string, error) {
	value, ok := raw[field]
	if !ok {
		return "", fmt.Errorf("%s is required", field)
	}
	stringValue, ok := value.(string)
	if !ok || strings.TrimSpace(stringValue) == "" {
		return "", fmt.Errorf("%s must be a non-empty string", field)
	}
	return strings.TrimSpace(stringValue), nil
}

func optionalMapValue(raw map[string]any, field string) (map[string]any, error) {
	value, ok := raw[field]
	if !ok || value == nil {
		return map[string]any{}, nil
	}
	mapped, ok := value.(map[string]any)
	if !ok {
		return nil, fmt.Errorf("%s must be a mapping", field)
	}
	return cloneParams(mapped), nil
}

func numericSeconds(value any) (time.Duration, error) {
	var seconds float64
	switch typed := value.(type) {
	case int:
		seconds = float64(typed)
	case int64:
		seconds = float64(typed)
	case float64:
		seconds = typed
	case float32:
		seconds = float64(typed)
	case string:
		parsed, err := strconv.ParseFloat(strings.TrimSpace(typed), 64)
		if err != nil {
			return 0, err
		}
		seconds = parsed
	default:
		return 0, fmt.Errorf("must be numeric seconds")
	}
	if seconds <= 0 {
		return 0, fmt.Errorf("must be greater than zero")
	}
	if math.IsNaN(seconds) || math.IsInf(seconds, 0) {
		return 0, fmt.Errorf("must be finite")
	}
	if seconds > float64(time.Duration(1<<63-1))/float64(time.Second) {
		return 0, fmt.Errorf("is too large")
	}
	duration := time.Duration(seconds * float64(time.Second))
	if duration <= 0 {
		return 0, fmt.Errorf("must be at least one nanosecond")
	}
	return duration, nil
}

func newHTTPClient(connectTimeout, readTimeout time.Duration) *http.Client {
	transport := &http.Transport{
		Proxy: http.ProxyFromEnvironment,
		DialContext: (&net.Dialer{
			Timeout:   connectTimeout,
			KeepAlive: 30 * time.Second,
		}).DialContext,
		TLSHandshakeTimeout:   connectTimeout,
		ResponseHeaderTimeout: readTimeout,
		ExpectContinueTimeout: time.Second,
		IdleConnTimeout:       30 * time.Second,
	}
	return &http.Client{
		Transport: transport,
		Timeout:   connectTimeout + readTimeout,
	}
}

func resolveURL(hubRoot, route string) (string, error) {
	baseURL, err := url.Parse(hubRoot)
	if err != nil {
		return "", fmt.Errorf("parse hub_root %q: %w", hubRoot, err)
	}
	routeURL, err := url.Parse(route)
	if err != nil {
		return "", fmt.Errorf("parse route %q: %w", route, err)
	}
	return baseURL.ResolveReference(routeURL).String(), nil
}

func addQueryValue(values url.Values, key string, value any) error {
	switch typed := value.(type) {
	case string:
		values.Set(key, typed)
	case fmt.Stringer:
		values.Set(key, typed.String())
	case bool:
		values.Set(key, strconv.FormatBool(typed))
	case int, int8, int16, int32, int64:
		values.Set(key, fmt.Sprintf("%d", typed))
	case uint, uint8, uint16, uint32, uint64:
		values.Set(key, fmt.Sprintf("%d", typed))
	case float32, float64:
		values.Set(key, fmt.Sprintf("%v", typed))
	case []string:
		for _, item := range typed {
			values.Add(key, item)
		}
	case []any:
		for _, item := range typed {
			values.Add(key, fmt.Sprint(item))
		}
	default:
		return fmt.Errorf("unsupported query value type %T", value)
	}
	return nil
}

func buildContents(feed *gofeed.Feed, summaryMaxLength int) []content.Content {
	if feed == nil {
		return nil
	}
	contents := make([]content.Content, 0, len(feed.Items))
	for _, item := range feed.Items {
		if item == nil {
			continue
		}
		published := publishedText(feed.FeedType, item)
		contents = append(contents, content.Content{
			ContentID: stableContentID(item.Link, published, strings.TrimSpace(item.GUID)),
			Title:     strings.TrimSpace(item.Title),
			Link:      strings.TrimSpace(item.Link),
			Summary: truncateSummary(
				strings.Join(strings.Fields(htmlToMarkdown(item.Description)), " "),
				summaryMaxLength,
			),
			Content:   bestEffortContent(item),
			Published: published,
		})
	}
	return contents
}

func publishedText(feedType string, item *gofeed.Item) string {
	if item == nil {
		return ""
	}
	published := strings.TrimSpace(item.Published)
	if feedType == "atom" &&
		published != "" &&
		published == strings.TrimSpace(item.Updated) {
		return ""
	}
	return published
}

func stableContentID(link, published, guid string) string {
	parsed, err := url.Parse(strings.TrimSpace(link))
	cleanURL := strings.TrimSpace(link)
	if err == nil {
		parsed.RawQuery = ""
		parsed.Fragment = ""
		cleanURL = parsed.String()
	}
	parts := []string{cleanURL, strings.TrimSpace(published)}
	if strings.TrimSpace(guid) != "" {
		parts = append(parts, strings.TrimSpace(guid))
	}
	hash := sha256.Sum256([]byte(strings.Join(parts, "|")))
	return hex.EncodeToString(hash[:])[:16]
}

func bestEffortContent(item *gofeed.Item) string {
	for _, candidate := range []string{item.Content, item.Description, item.Custom["description"]} {
		converted := htmlToMarkdown(candidate)
		if strings.TrimSpace(converted) != "" {
			return converted
		}
	}
	return ""
}

func htmlToMarkdown(input string) string {
	text := strings.TrimSpace(input)
	if text == "" {
		return ""
	}
	text = scriptPattern.ReplaceAllString(text, "")
	text = codeBlockPattern.ReplaceAllString(text, "\n```\n$1\n```\n")
	text = inlineCodePattern.ReplaceAllString(text, "`$1`")
	text = headingOnePattern.ReplaceAllString(text, "\n# $1\n\n")
	text = headingTwoPattern.ReplaceAllString(text, "\n## $1\n\n")
	text = headingThreePattern.ReplaceAllString(text, "\n### $1\n\n")
	text = headingOtherPattern.ReplaceAllString(text, "\n#### $1\n\n")
	text = strongPattern.ReplaceAllString(text, "**$2**")
	text = emphasisPattern.ReplaceAllString(text, "*$2*")
	text = linkPattern.ReplaceAllString(text, "[$2]($1)")
	text = lineBreakPattern.ReplaceAllString(text, "\n")
	text = listItemOpenPattern.ReplaceAllString(text, "- ")
	text = listItemClosePattern.ReplaceAllString(text, "\n")
	text = paragraphPattern.ReplaceAllString(text, "\n")
	text = tagPattern.ReplaceAllString(text, "")
	text = html.UnescapeString(text)
	lines := strings.Split(text, "\n")
	cleaned := make([]string, 0, len(lines))
	for _, line := range lines {
		line = whitespacePattern.ReplaceAllString(strings.TrimSpace(line), " ")
		if line == "" {
			cleaned = append(cleaned, "")
			continue
		}
		cleaned = append(cleaned, line)
	}
	result := strings.Join(cleaned, "\n")
	result = newlinePattern.ReplaceAllString(result, "\n\n")
	return strings.TrimSpace(result)
}

func truncateSummary(summary string, maxLength int) string {
	summary = strings.TrimSpace(summary)
	if maxLength <= 0 {
		maxLength = defaultSummaryMaxLength
	}
	runes := []rune(summary)
	if len(runes) <= maxLength {
		return summary
	}
	if maxLength <= 3 {
		return string(runes[:maxLength])
	}
	return string(runes[:maxLength-3]) + "..."
}

// FilterQualityContents preserves the Python fetch-quality compatibility rules.
func FilterQualityContents(contents []content.Content) []content.Content {
	filtered := make([]content.Content, 0, len(contents))
	seen := make(map[string]struct{}, len(contents))
	for _, item := range contents {
		contentID := strings.TrimSpace(item.ContentID)
		title := strings.TrimSpace(item.Title)
		link := strings.TrimSpace(item.Link)
		summary := strings.TrimSpace(item.Summary)
		body := strings.TrimSpace(item.Content)
		if contentID == "" || title == "" || link == "" {
			continue
		}
		if summary == "" && body == "" {
			continue
		}
		if _, exists := seen[contentID]; exists {
			continue
		}
		seen[contentID] = struct{}{}
		filtered = append(filtered, item)
	}
	return filtered
}

func filterByTimeRange(contents []content.Content, params map[string]any) ([]content.Content, error) {
	value, ok := params["filter_time"]
	if !ok || isFalseyFilterTime(value) {
		return contents, nil
	}
	window, err := numericSeconds(value)
	if err != nil {
		return nil, fmt.Errorf("filter_time: %w", err)
	}
	cutoff := time.Now().UTC().Add(-window)
	filtered := make([]content.Content, 0, len(contents))
	for _, item := range contents {
		publishedTime, ok := parsePublishedTime(item.Published)
		if !ok {
			continue
		}
		if !publishedTime.Before(cutoff) {
			filtered = append(filtered, item)
		}
	}
	return filtered, nil
}

func isFalseyFilterTime(value any) bool {
	switch typed := value.(type) {
	case nil:
		return true
	case bool:
		return !typed
	case int:
		return typed == 0
	case int8:
		return typed == 0
	case int16:
		return typed == 0
	case int32:
		return typed == 0
	case int64:
		return typed == 0
	case uint:
		return typed == 0
	case uint8:
		return typed == 0
	case uint16:
		return typed == 0
	case uint32:
		return typed == 0
	case uint64:
		return typed == 0
	case float32:
		return typed == 0
	case float64:
		return typed == 0
	case string:
		return typed == ""
	default:
		return false
	}
}

func parsePublishedTime(value string) (time.Time, bool) {
	value = strings.TrimSpace(value)
	if value == "" {
		return time.Time{}, false
	}
	layouts := []string{
		time.RFC3339,
		time.RFC3339Nano,
		time.RFC1123Z,
		time.RFC1123,
		time.RFC822Z,
		time.RFC822,
		time.RFC850,
		time.RubyDate,
		"Mon, 02 Jan 2006 15:04:05 MST",
		"2006-01-02 15:04:05Z07:00",
		"2006-01-02 15:04:05 -0700 MST",
		"2006-01-02 15:04:05 -0700",
		"2006-01-02 15:04:05",
		"2006-01-02",
	}
	for _, layout := range layouts {
		if parsed, err := time.Parse(layout, value); err == nil {
			return parsed.UTC(), true
		}
	}
	return time.Time{}, false
}

func cloneParams(input map[string]any) map[string]any {
	if len(input) == 0 {
		return map[string]any{}
	}
	result := make(map[string]any, len(input))
	for key, value := range input {
		result[key] = cloneParamValue(value)
	}
	return result
}

func cloneParamValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		return cloneParams(typed)
	case []any:
		copied := make([]any, len(typed))
		for index := range typed {
			copied[index] = cloneParamValue(typed[index])
		}
		return copied
	case []string:
		return append([]string(nil), typed...)
	default:
		return typed
	}
}

func normalizeFactoryOptions(options FactoryOptions) FactoryOptions {
	if options.RSSHubConnectTimeout <= 0 {
		options.RSSHubConnectTimeout = defaultRSSHubConnect
	}
	if options.RSSHubReadTimeout <= 0 {
		options.RSSHubReadTimeout = defaultRSSHubRead
	}
	if options.DirectRSSConnectTimeout <= 0 {
		options.DirectRSSConnectTimeout = defaultDirectRSSConnect
	}
	if options.DirectRSSReadTimeout <= 0 {
		options.DirectRSSReadTimeout = defaultDirectRSSRead
	}
	if options.SummaryMaxLength <= 0 {
		options.SummaryMaxLength = defaultSummaryMaxLength
	}
	return options
}
