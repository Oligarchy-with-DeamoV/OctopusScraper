package notion

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/config"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
)

const (
	maxNotionResponseBytes  = 10 << 20
	maxNotionErrorBodyBytes = 2048
)

type Uploader interface {
	StoreContents(context.Context, []content.Content, bool) ([]bool, error)
}

func (c *Client) ID() string { return "notion" }

func (c *Client) Deliver(ctx context.Context, item content.Content) error {
	results, err := c.StoreContents(ctx, []content.Content{item}, true)
	if err != nil {
		return err
	}
	if len(results) != 1 || !results[0] {
		return errors.New("Notion upload failed")
	}
	return nil
}

type Client struct {
	config     config.NotionConfig
	httpClient *http.Client
	baseURL    string
	converter  *MarkdownConverter
	now        func() time.Time
	sleep      func(context.Context, time.Duration) error

	initMu       sync.Mutex
	initialized  bool
	dataSourceID string

	cacheMu    sync.Mutex
	contentIDs map[string]struct{}
	cacheAt    time.Time
	cacheFull  bool

	rateMu      sync.Mutex
	nextRequest time.Time
	pauseUntil  time.Time
}

type databaseResponse struct {
	DataSources []dataSourceRef `json:"data_sources"`
}

type dataSourceRef struct {
	ID   string `json:"id"`
	Name string `json:"name"`
}

type dataSourceResponse struct {
	ID         string                        `json:"id"`
	Properties map[string]dataSourceProperty `json:"properties"`
}

type dataSourceProperty struct {
	ID   string `json:"id"`
	Name string `json:"name"`
	Type string `json:"type"`
}

type pageResponse struct {
	ID         string                          `json:"id"`
	Properties map[string]pagePropertyResponse `json:"properties"`
}

type pagePropertyResponse struct {
	Type     string             `json:"type"`
	RichText []richTextResponse `json:"rich_text"`
}

type richTextResponse struct {
	PlainText string           `json:"plain_text"`
	Text      *richTextContent `json:"text"`
}

type richTextContent struct {
	Content string `json:"content"`
}

type queryResponse struct {
	Results       []pageResponse     `json:"results"`
	HasMore       bool               `json:"has_more"`
	NextCursor    *string            `json:"next_cursor"`
	RequestStatus queryRequestStatus `json:"request_status"`
}

type queryRequestStatus struct {
	Type             string `json:"type"`
	IncompleteReason string `json:"incomplete_reason"`
}

type apiErrorResponse struct {
	Object  string `json:"object"`
	Status  int    `json:"status"`
	Code    string `json:"code"`
	Message string `json:"message"`
}

type HTTPError struct {
	StatusCode int
	Code       string
	Message    string
	Body       string
}

func (e *HTTPError) Error() string {
	if e.Code != "" {
		return fmt.Sprintf("notion API %d %s: %s", e.StatusCode, e.Code, e.Message)
	}
	return fmt.Sprintf("notion API %d: %s", e.StatusCode, e.Message)
}

func NewClient(cfg config.NotionConfig, httpClient *http.Client) (*Client, error) {
	if strings.TrimSpace(cfg.APIKey) == "" {
		return nil, errors.New("notion API key is required")
	}
	if strings.TrimSpace(cfg.DatabaseID) == "" {
		return nil, errors.New("notion database ID is required")
	}
	if httpClient == nil {
		httpClient = &http.Client{Timeout: 30 * time.Second}
	}
	return &Client{
		config:     cfg,
		httpClient: httpClient,
		baseURL:    "https://api.notion.com",
		converter:  NewMarkdownConverter(),
		now:        time.Now,
		sleep:      sleepContext,
	}, nil
}

func (c *Client) Initialize(ctx context.Context) error {
	c.initMu.Lock()
	defer c.initMu.Unlock()
	if c.initialized {
		return nil
	}

	dataSourceID := strings.TrimSpace(c.config.DataSourceID)
	if dataSourceID == "" {
		resolvedID, err := c.resolveDataSourceID(ctx)
		if err != nil {
			return err
		}
		dataSourceID = resolvedID
	}
	properties, err := c.retrieveDataSource(ctx, dataSourceID)
	if err != nil {
		return err
	}
	if err := c.ensureProperties(ctx, dataSourceID, properties); err != nil {
		return err
	}

	c.dataSourceID = dataSourceID
	c.initialized = true
	return nil
}

func (c *Client) StoreContents(ctx context.Context, contents []content.Content, deduplicate bool) ([]bool, error) {
	if err := c.Initialize(ctx); err != nil {
		return nil, err
	}
	results := make([]bool, len(contents))
	if len(contents) == 0 {
		return results, nil
	}
	entries := make([]storeEntry, 0, len(contents))
	failures := make([]storeEntry, 0)
	seen := make(map[string]struct{})
	for index, item := range contents {
		id := strings.TrimSpace(item.ContentID)
		if id == "" {
			results[index] = false
			failures = append(failures, storeEntry{
				Index:   index,
				Content: item,
				Err:     errors.New("content ID is required"),
			})
			continue
		}
		if deduplicate {
			if _, exists := seen[id]; exists {
				results[index] = true
				continue
			}
			seen[id] = struct{}{}
		}
		entries = append(entries, storeEntry{Index: index, Content: item})
	}

	cacheWasFresh := c.contentIDCacheFresh()
	existingIDs, cacheFull, err := c.existingContentIDs(ctx, false)
	if err != nil {
		return nil, err
	}
	exactLookupOnMiss := cacheWasFresh || !cacheFull
	pending := make([]storeEntry, 0, len(entries))
	for _, entry := range entries {
		if entry.Err != nil {
			failures = append(failures, entry)
			continue
		}
		if deduplicate {
			if _, exists := existingIDs[entry.Content.ContentID]; exists {
				results[entry.Index] = true
				continue
			}
			if _, exists := existingIDs[pendingContentID(entry.Content.ContentID)]; exists {
				if err := c.archivePendingPages(ctx, pendingContentID(entry.Content.ContentID)); err != nil {
					entry.Err = fmt.Errorf("archive pending pages for %s: %w", entry.Content.ContentID, err)
					results[entry.Index] = false
					pending = append(pending, entry)
					continue
				}
				delete(existingIDs, pendingContentID(entry.Content.ContentID))
			} else if exactLookupOnMiss {
				exists, err := c.reconcileExactContentPages(
					ctx,
					entry.Content.ContentID,
					existingIDs,
				)
				if err != nil {
					return nil, err
				}
				if exists {
					results[entry.Index] = true
					continue
				}
			}
		}
		pending = append(pending, entry)
	}

	for _, entry := range pending {
		if entry.Err != nil {
			failures = append(failures, entry)
			continue
		}
		if err := c.storeOne(ctx, entry.Content); err != nil {
			entry.Err = err
			results[entry.Index] = false
			failures = append(failures, entry)
			continue
		}
		results[entry.Index] = true
	}

	if len(failures) > 0 && c.config.RetryDelay > 0 {
		if err := c.sleep(ctx, c.config.RetryDelay); err != nil {
			return results, err
		}
		refreshedIDs, cacheFull, err := c.existingContentIDs(ctx, true)
		if err != nil {
			return results, err
		}
		retryFailures := make([]storeEntry, 0)
		for _, failure := range failures {
			if _, exists := refreshedIDs[failure.Content.ContentID]; exists {
				results[failure.Index] = true
				failure.Err = nil
				continue
			}
			pendingID := pendingContentID(failure.Content.ContentID)
			if _, exists := refreshedIDs[pendingID]; exists {
				if err := c.archivePendingPages(ctx, pendingID); err != nil {
					failure.Err = fmt.Errorf("archive ambiguous pending page for %s: %w", failure.Content.ContentID, err)
					retryFailures = append(retryFailures, failure)
					continue
				}
			} else if !cacheFull {
				exists, err := c.reconcileExactContentPages(
					ctx,
					failure.Content.ContentID,
					refreshedIDs,
				)
				if err != nil {
					return results, err
				}
				if exists {
					results[failure.Index] = true
					failure.Err = nil
					continue
				}
			}
			if failure.Err != nil && strings.Contains(failure.Err.Error(), "content ID is required") {
				retryFailures = append(retryFailures, failure)
				continue
			}
			if err := c.storeOne(ctx, failure.Content); err != nil {
				failure.Err = err
				retryFailures = append(retryFailures, failure)
				continue
			}
			results[failure.Index] = true
			failure.Err = nil
		}
		failures = retryFailures
	}

	errs := make([]error, 0, len(failures))
	for _, failure := range failures {
		if failure.Err != nil {
			errs = append(errs, failure.Err)
		}
	}
	return results, joinErrors(errs)
}

func (c *Client) contentIDCacheFresh() bool {
	c.cacheMu.Lock()
	defer c.cacheMu.Unlock()
	return !c.cacheAt.IsZero() &&
		c.now().Sub(c.cacheAt) < contentIDCacheTTL
}

func (c *Client) cacheFinalContentID(contentID string) {
	c.cacheMu.Lock()
	defer c.cacheMu.Unlock()
	if c.contentIDs == nil {
		c.contentIDs = make(map[string]struct{})
		c.cacheAt = c.now()
		c.cacheFull = false
	}
	c.contentIDs[contentID] = struct{}{}
	delete(c.contentIDs, pendingContentID(contentID))
}

func (c *Client) reconcileExactContentPages(
	ctx context.Context,
	contentID string,
	existingIDs map[string]struct{},
) (bool, error) {
	pendingID := pendingContentID(contentID)
	pages, err := c.lookupContentPages(ctx, contentID, pendingID)
	if err != nil {
		return false, err
	}
	if len(pages[contentID]) > 0 {
		existingIDs[contentID] = struct{}{}
		c.cacheFinalContentID(contentID)
		return true, nil
	}
	for _, pageID := range pages[pendingID] {
		if err := c.archivePage(ctx, pageID); err != nil {
			return false, fmt.Errorf(
				"archive pending page for %s: %w",
				contentID,
				err,
			)
		}
	}
	delete(existingIDs, pendingID)
	return false, nil
}

type storeEntry struct {
	Index   int
	Content content.Content
	Err     error
}

func (c *Client) resolveDataSourceID(ctx context.Context) (string, error) {
	var response databaseResponse
	if err := c.doJSON(ctx, http.MethodGet, "/v1/databases/"+url.PathEscape(c.config.DatabaseID), nil, nil, &response); err != nil {
		return "", err
	}
	switch len(response.DataSources) {
	case 0:
		return "", fmt.Errorf("database %s has no data sources", c.config.DatabaseID)
	case 1:
		return response.DataSources[0].ID, nil
	default:
		return "", fmt.Errorf("database %s has %d data sources; set DataSourceID explicitly", c.config.DatabaseID, len(response.DataSources))
	}
}

func (c *Client) retrieveDataSource(ctx context.Context, dataSourceID string) (map[string]dataSourceProperty, error) {
	var response dataSourceResponse
	if err := c.doJSON(ctx, http.MethodGet, "/v1/data_sources/"+url.PathEscape(dataSourceID), nil, nil, &response); err != nil {
		return nil, err
	}
	return response.Properties, nil
}

func (c *Client) ensureProperties(ctx context.Context, dataSourceID string, properties map[string]dataSourceProperty) error {
	expected := map[string]string{
		propertyNameTitle:     "title",
		propertyNameSummary:   "rich_text",
		propertyNameContentID: "rich_text",
		propertyNameURL:       "url",
		propertyNameAuthor:    "rich_text",
		propertyNameKeywords:  "multi_select",
		propertyNameTags:      "multi_select",
		propertyNameSource:    "select",
		propertyNamePublished: "date",
	}
	missing := make(map[string]any)
	for name, expectedType := range expected {
		property, exists := properties[name]
		if exists {
			if property.Type != expectedType {
				return fmt.Errorf("required Notion property %q has type %q; expected %q", name, property.Type, expectedType)
			}
			continue
		}
		missing[name] = map[string]any{
			"type":       expectedType,
			expectedType: map[string]any{},
		}
	}
	if len(missing) == 0 {
		return nil
	}
	payload := map[string]any{"properties": missing}
	return c.doJSON(ctx, http.MethodPatch, "/v1/data_sources/"+url.PathEscape(dataSourceID), nil, payload, nil)
}

func (c *Client) existingContentIDs(
	ctx context.Context,
	forceRefresh bool,
) (map[string]struct{}, bool, error) {
	c.cacheMu.Lock()
	if !forceRefresh && !c.cacheAt.IsZero() && c.now().Sub(c.cacheAt) < contentIDCacheTTL {
		copy := copyIDSet(c.contentIDs)
		cacheFull := c.cacheFull
		c.cacheMu.Unlock()
		return copy, cacheFull, nil
	}
	c.cacheMu.Unlock()

	filterProps := url.Values{}
	filterProps.Add("filter_properties", propertyNameContentID)
	result := make(map[string]struct{})
	cacheFull := true
	var cursor *string
	for {
		payload := map[string]any{"page_size": 100}
		if cursor != nil && *cursor != "" {
			payload["start_cursor"] = *cursor
		}
		var response queryResponse
		if err := c.doJSON(ctx, http.MethodPost, "/v1/data_sources/"+url.PathEscape(c.dataSourceID)+"/query", filterProps, payload, &response); err != nil {
			return nil, false, err
		}
		if response.RequestStatus.Type == "incomplete" {
			cacheFull = false
		}
		for _, page := range response.Results {
			property := page.Properties[propertyNameContentID]
			if id := readRichTextValue(property.RichText); id != "" {
				result[id] = struct{}{}
			}
		}
		if !response.HasMore || response.NextCursor == nil || *response.NextCursor == "" {
			break
		}
		cursor = response.NextCursor
	}

	c.cacheMu.Lock()
	c.contentIDs = copyIDSet(result)
	c.cacheAt = c.now()
	c.cacheFull = cacheFull
	c.cacheMu.Unlock()
	return copyIDSet(result), cacheFull, nil
}

func (c *Client) lookupContentPages(
	ctx context.Context,
	contentIDs ...string,
) (map[string][]string, error) {
	result := make(map[string][]string, len(contentIDs))
	filters := make([]any, 0, len(contentIDs))
	for _, contentID := range contentIDs {
		result[contentID] = []string{}
		filters = append(filters, map[string]any{
			"property": propertyNameContentID,
			"rich_text": map[string]any{
				"equals": contentID,
			},
		})
	}
	var cursor *string
	for {
		payload := map[string]any{
			"page_size": 100,
			"filter":    map[string]any{"or": filters},
		}
		if cursor != nil && *cursor != "" {
			payload["start_cursor"] = *cursor
		}
		var response queryResponse
		if err := c.doJSON(
			ctx,
			http.MethodPost,
			"/v1/data_sources/"+url.PathEscape(c.dataSourceID)+"/query",
			nil,
			payload,
			&response,
		); err != nil {
			return nil, err
		}
		if err := incompleteQueryError(response.RequestStatus); err != nil {
			return nil, err
		}
		for _, page := range response.Results {
			contentID := readRichTextValue(
				page.Properties[propertyNameContentID].RichText,
			)
			if _, expected := result[contentID]; expected {
				result[contentID] = append(result[contentID], page.ID)
			}
		}
		if !response.HasMore ||
			response.NextCursor == nil ||
			*response.NextCursor == "" {
			break
		}
		cursor = response.NextCursor
	}
	return result, nil
}

func (c *Client) archivePendingPages(ctx context.Context, pendingID string) error {
	var cursor *string
	for {
		payload := map[string]any{
			"page_size": 100,
			"filter": map[string]any{
				"property": propertyNameContentID,
				"rich_text": map[string]any{
					"equals": pendingID,
				},
			},
		}
		if cursor != nil && *cursor != "" {
			payload["start_cursor"] = *cursor
		}
		var response queryResponse
		if err := c.doJSON(ctx, http.MethodPost, "/v1/data_sources/"+url.PathEscape(c.dataSourceID)+"/query", nil, payload, &response); err != nil {
			return err
		}
		if err := incompleteQueryError(response.RequestStatus); err != nil {
			return err
		}
		for _, page := range response.Results {
			if err := c.archivePage(ctx, page.ID); err != nil {
				return err
			}
		}
		if !response.HasMore || response.NextCursor == nil || *response.NextCursor == "" {
			break
		}
		cursor = response.NextCursor
	}
	c.cacheMu.Lock()
	if c.contentIDs != nil {
		delete(c.contentIDs, pendingID)
	}
	c.cacheMu.Unlock()
	return nil
}

func incompleteQueryError(status queryRequestStatus) error {
	if status.Type != "incomplete" {
		return nil
	}
	reason := strings.TrimSpace(status.IncompleteReason)
	if reason == "" {
		reason = "unknown reason"
	}
	return fmt.Errorf("Notion query returned incomplete results: %s", reason)
}

func (c *Client) storeOne(ctx context.Context, item content.Content) error {
	properties, err := c.buildPageProperties(item, pendingContentID(item.ContentID))
	if err != nil {
		return err
	}
	children := c.converter.Convert(item.Content)
	initial := toAnyBlocks(children[:min(len(children), maxBlocksPerRequest)])
	remaining := children[min(len(children), maxBlocksPerRequest):]

	payload := map[string]any{
		"parent": map[string]any{
			"type":           "data_source_id",
			"data_source_id": c.dataSourceID,
		},
		"properties": properties,
	}
	if len(initial) > 0 {
		payload["children"] = initial
	}
	var created pageResponse
	if err := c.doJSON(ctx, http.MethodPost, "/v1/pages", nil, payload, &created); err != nil {
		return fmt.Errorf("create Notion page for %s: %w", item.ContentID, err)
	}
	pageID := created.ID
	for start := 0; start < len(remaining); start += maxBlocksPerRequest {
		end := start + maxBlocksPerRequest
		if end > len(remaining) {
			end = len(remaining)
		}
		appendPayload := map[string]any{
			"children": toAnyBlocks(remaining[start:end]),
		}
		if err := c.doJSON(ctx, http.MethodPatch, "/v1/blocks/"+url.PathEscape(pageID)+"/children", nil, appendPayload, nil); err != nil {
			archiveErr := c.archivePage(ctx, pageID)
			if archiveErr != nil {
				return fmt.Errorf("append blocks for %s: %w (archive partial page: %v)", item.ContentID, err, archiveErr)
			}
			return fmt.Errorf("append blocks for %s: %w", item.ContentID, err)
		}
	}
	finalizePayload := map[string]any{
		"properties": map[string]any{
			propertyNameContentID: map[string]any{
				"type":      "rich_text",
				"rich_text": splitTextToRichText(item.ContentID, defaultAnnotations(), nil),
			},
		},
	}
	if err := c.doJSON(ctx, http.MethodPatch, "/v1/pages/"+url.PathEscape(pageID), nil, finalizePayload, nil); err != nil {
		archiveErr := c.archivePage(ctx, pageID)
		if archiveErr != nil {
			return fmt.Errorf("finalize page for %s: %w (archive partial page: %v)", item.ContentID, err, archiveErr)
		}
		return fmt.Errorf("finalize page for %s: %w", item.ContentID, err)
	}
	c.cacheFinalContentID(item.ContentID)
	return nil
}

func (c *Client) archivePage(ctx context.Context, pageID string) error {
	payload := map[string]any{"in_trash": true}
	return c.doJSON(ctx, http.MethodPatch, "/v1/pages/"+url.PathEscape(pageID), nil, payload, nil)
}

func (c *Client) buildPageProperties(item content.Content, contentID string) (map[string]any, error) {
	title := strings.TrimSpace(item.Title)
	if title == "" {
		title = "Untitled"
	}
	summary := sanitizeSummary(item.Summary)
	author := ""
	if item.Author != nil {
		author = strings.TrimSpace(*item.Author)
	}
	source := ""
	if item.ScraperName != nil {
		source = sanitizeOptionName(*item.ScraperName)
	}
	keywords := sanitizeOptions(item.Keywords)
	tags := sanitizeOptions(item.Tags)
	properties := map[string]any{
		propertyNameTitle: map[string]any{
			"type":  "title",
			"title": limitRichTextSegments(splitTextToRichText(title, defaultAnnotations(), nil)),
		},
		propertyNameSummary: map[string]any{
			"type":      "rich_text",
			"rich_text": limitRichTextSegments(splitTextToRichText(summary, defaultAnnotations(), nil)),
		},
		propertyNameContentID: map[string]any{
			"type":      "rich_text",
			"rich_text": limitRichTextSegments(splitTextToRichText(contentID, defaultAnnotations(), nil)),
		},
		propertyNameAuthor: map[string]any{
			"type":      "rich_text",
			"rich_text": limitRichTextSegments(splitTextToRichText(author, defaultAnnotations(), nil)),
		},
		propertyNameKeywords: map[string]any{
			"type":         "multi_select",
			"multi_select": optionsToPropertyValues(keywords),
		},
		propertyNameTags: map[string]any{
			"type":         "multi_select",
			"multi_select": optionsToPropertyValues(tags),
		},
	}
	if urlValue := sanitizeURL(item.Link); urlValue != nil {
		properties[propertyNameURL] = map[string]any{"type": "url", "url": *urlValue}
	} else {
		properties[propertyNameURL] = map[string]any{"type": "url", "url": nil}
	}
	if source != "" {
		properties[propertyNameSource] = map[string]any{"type": "select", "select": map[string]any{"name": source}}
	} else {
		properties[propertyNameSource] = map[string]any{"type": "select", "select": nil}
	}
	if published := parsePublishedDate(item.Published); published != nil {
		properties[propertyNamePublished] = map[string]any{"type": "date", "date": map[string]any{"start": *published}}
	} else {
		properties[propertyNamePublished] = map[string]any{"type": "date", "date": nil}
	}
	return properties, nil
}

func sanitizeOptions(values []string) []string {
	result := make([]string, 0, len(values))
	seen := make(map[string]struct{})
	for _, value := range values {
		sanitized := sanitizeOptionName(value)
		if sanitized == "" {
			continue
		}
		if _, exists := seen[sanitized]; exists {
			continue
		}
		seen[sanitized] = struct{}{}
		result = append(result, sanitized)
		if len(result) == maxMultiSelectOptions {
			break
		}
	}
	return result
}

func optionsToPropertyValues(values []string) []map[string]any {
	result := make([]map[string]any, 0, len(values))
	for _, value := range values {
		result = append(result, map[string]any{"name": value})
	}
	return result
}

func readRichTextValue(items []richTextResponse) string {
	var builder strings.Builder
	for _, item := range items {
		if item.Text != nil && item.Text.Content != "" {
			builder.WriteString(item.Text.Content)
			continue
		}
		builder.WriteString(item.PlainText)
	}
	return builder.String()
}

func copyIDSet(source map[string]struct{}) map[string]struct{} {
	copy := make(map[string]struct{}, len(source))
	for key := range source {
		copy[key] = struct{}{}
	}
	return copy
}

func toAnyBlocks(blocks []Block) []any {
	result := make([]any, 0, len(blocks))
	for _, block := range blocks {
		result = append(result, block)
	}
	return result
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func (c *Client) doJSON(ctx context.Context, method string, path string, query url.Values, payload any, out any) error {
	var bodyBytes []byte
	var err error
	if payload != nil {
		bodyBytes, err = json.Marshal(payload)
		if err != nil {
			return err
		}
	}
	attempts := 6
	retrySafe := method == http.MethodGet ||
		method == http.MethodDelete ||
		(method == http.MethodPost && strings.HasSuffix(path, "/query"))
	for attempt := 0; attempt < attempts; attempt++ {
		if err := c.waitForRequestTurn(ctx); err != nil {
			return err
		}
		requestURL := c.baseURL + path
		if len(query) > 0 {
			requestURL += "?" + query.Encode()
		}
		var body io.Reader
		if bodyBytes != nil {
			body = bytes.NewReader(bodyBytes)
		}
		request, err := http.NewRequestWithContext(ctx, method, requestURL, body)
		if err != nil {
			return err
		}
		request.Header.Set("Authorization", "Bearer "+c.config.APIKey)
		request.Header.Set("Notion-Version", notionVersion)
		request.Header.Set("Accept", "application/json")
		if bodyBytes != nil {
			request.Header.Set("Content-Type", "application/json")
		}
		response, err := c.httpClient.Do(request)
		if err != nil {
			if retrySafe && attempt < attempts-1 {
				delay := defaultRetryDelay(attempt)
				c.notePause(delay)
				if err := c.sleep(ctx, delay); err != nil {
					return err
				}
				continue
			}
			return err
		}
		if shouldRetry(response.StatusCode, retrySafe) && attempt < attempts-1 {
			delay := computeRetryDelay(response, attempt)
			_, _ = io.CopyN(
				io.Discard,
				response.Body,
				maxNotionResponseBytes+1,
			)
			response.Body.Close()
			c.notePause(delay)
			if err := c.sleep(ctx, delay); err != nil {
				return err
			}
			continue
		}
		defer response.Body.Close()
		responseBody, err := readNotionResponse(response.Body)
		if err != nil {
			return err
		}
		if response.StatusCode < 200 || response.StatusCode >= 300 {
			apiErr := apiErrorResponse{}
			if json.Unmarshal(responseBody, &apiErr) == nil && (apiErr.Code != "" || apiErr.Message != "") {
				return &HTTPError{
					StatusCode: response.StatusCode,
					Code:       apiErr.Code,
					Message: errorBodySnippet(
						[]byte(apiErr.Message),
						maxNotionErrorBodyBytes,
					),
					Body: errorBodySnippet(
						responseBody,
						maxNotionErrorBodyBytes,
					),
				}
			}
			return &HTTPError{
				StatusCode: response.StatusCode,
				Message: errorBodySnippet(
					responseBody,
					maxNotionErrorBodyBytes,
				),
				Body: errorBodySnippet(
					responseBody,
					maxNotionErrorBodyBytes,
				),
			}
		}
		if out != nil && len(responseBody) > 0 {
			if err := json.Unmarshal(responseBody, out); err != nil {
				return err
			}
		}
		return nil
	}
	return errors.New("exhausted Notion API retries")
}

func errorBodySnippet(body []byte, limit int) string {
	if limit > 0 && len(body) > limit {
		return strings.TrimSpace(
			strings.ToValidUTF8(string(body[:limit]), ""),
		) + "..."
	}
	return strings.TrimSpace(strings.ToValidUTF8(string(body), ""))
}

func readNotionResponse(reader io.Reader) ([]byte, error) {
	limited := &io.LimitedReader{
		R: reader,
		N: maxNotionResponseBytes + 1,
	}
	body, err := io.ReadAll(limited)
	if err != nil {
		return nil, err
	}
	if len(body) > maxNotionResponseBytes {
		return nil, fmt.Errorf(
			"Notion response body exceeds %d bytes",
			maxNotionResponseBytes,
		)
	}
	return body, nil
}

func shouldRetry(statusCode int, retrySafe bool) bool {
	if statusCode == http.StatusTooManyRequests || statusCode == 529 {
		return true
	}
	if !retrySafe {
		return false
	}
	switch statusCode {
	case http.StatusInternalServerError, http.StatusBadGateway, http.StatusServiceUnavailable, http.StatusGatewayTimeout:
		return true
	default:
		return false
	}
}

func computeRetryDelay(response *http.Response, attempt int) time.Duration {
	if retryAfter := strings.TrimSpace(response.Header.Get("Retry-After")); retryAfter != "" {
		if seconds, err := time.ParseDuration(retryAfter + "s"); err == nil && seconds >= 0 {
			return seconds
		}
	}
	return defaultRetryDelay(attempt)
}

func defaultRetryDelay(attempt int) time.Duration {
	seconds := math.Pow(2, float64(attempt))
	if seconds > 30 {
		seconds = 30
	}
	return time.Duration(seconds) * time.Second
}

func (c *Client) waitForRequestTurn(ctx context.Context) error {
	for {
		c.rateMu.Lock()
		now := c.now()
		waitUntil := maxTime(c.nextRequest, c.pauseUntil)
		if !waitUntil.After(now) {
			c.nextRequest = now.Add(minRequestInterval)
			c.rateMu.Unlock()
			return nil
		}
		delay := waitUntil.Sub(now)
		c.rateMu.Unlock()
		if err := c.sleep(ctx, delay); err != nil {
			return err
		}
	}
}

func (c *Client) notePause(delay time.Duration) {
	c.rateMu.Lock()
	defer c.rateMu.Unlock()
	pauseUntil := c.now().Add(delay)
	if pauseUntil.After(c.pauseUntil) {
		c.pauseUntil = pauseUntil
	}
}

func maxTime(a, b time.Time) time.Time {
	if a.After(b) {
		return a
	}
	return b
}
