package notion

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/config"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
)

func TestClientStoreContentsPayloads(t *testing.T) {
	t.Parallel()

	var mu sync.Mutex
	captured := map[string][]byte{}
	requestCounts := map[string]int{}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		key := r.Method + " " + r.URL.Path
		requestCounts[key]++
		if got := r.Header.Get("Notion-Version"); got != notionVersion {
			t.Fatalf("Notion-Version header = %q, want %q", got, notionVersion)
		}
		body, _ := io.ReadAll(r.Body)
		switch key {
		case "GET /v1/databases/db-1":
			writeJSON(t, w, map[string]any{"data_sources": []map[string]any{{"id": "ds-1", "name": "Primary"}}})
		case "GET /v1/data_sources/ds-1":
			writeJSON(t, w, map[string]any{"id": "ds-1", "properties": map[string]any{
				propertyNameTitle:  map[string]any{"id": "title", "name": propertyNameTitle, "type": "title"},
				propertyNameSource: map[string]any{"id": "src", "name": propertyNameSource, "type": "select"},
			}})
		case "PATCH /v1/data_sources/ds-1":
			captured["update_data_source_request.golden.json"] = body
			writeJSON(t, w, map[string]any{"id": "ds-1"})
		case "POST /v1/data_sources/ds-1/query":
			if got := r.URL.Query()["filter_properties"]; len(got) != 1 || got[0] != propertyNameContentID {
				t.Fatalf("filter_properties = %v, want [%s]", got, propertyNameContentID)
			}
			writeJSON(t, w, map[string]any{"results": []any{}, "has_more": false, "next_cursor": nil})
		case "POST /v1/pages":
			captured["create_page_request.golden.json"] = body
			writeJSON(t, w, map[string]any{"id": "page-1"})
		case "PATCH /v1/blocks/page-1/children":
			captured["append_block_children_request.golden.json"] = body
			writeJSON(t, w, map[string]any{"results": []any{}, "has_more": false, "next_cursor": nil})
		case "PATCH /v1/pages/page-1":
			captured["finalize_page_request.golden.json"] = body
			writeJSON(t, w, map[string]any{"id": "page-1"})
		default:
			t.Fatalf("unexpected request %s", key)
		}
	}))
	defer server.Close()

	client := newTestClient(t, config.NotionConfig{
		APIKey:     "secret",
		DatabaseID: "db-1",
		RetryDelay: time.Second,
	}, server.URL)
	item := content.Content{
		ContentID:   "article-123",
		Title:       strings.Repeat("A", 2105),
		Link:        "https://example.com/posts/1",
		Summary:     "<p>Hello &amp; <strong>world</strong></p>",
		Content:     makeParagraphMarkdown(101),
		Published:   "Tue, 06 Apr 2025 13:50:59 +0800",
		Author:      stringPtr(" Ada Lovelace "),
		Keywords:    []string{" ai ", "ai", "line\nbreak"},
		Tags:        []string{"tag-1", strings.Repeat("x", 120)},
		ScraperName: stringPtr("  Feed Source  "),
	}

	results, err := client.StoreContents(context.Background(), []content.Content{item}, true)
	if err != nil {
		t.Fatalf("StoreContents returned error: %v", err)
	}
	if len(results) != 1 || !results[0] {
		t.Fatalf("StoreContents results = %v, want [true]", results)
	}
	for name, body := range captured {
		assertJSONGolden(t, name, body)
	}
	if got := requestCounts["PATCH /v1/blocks/page-1/children"]; got != 1 {
		t.Fatalf("append request count = %d, want 1", got)
	}
}

func TestBuildPagePropertiesUsesArrayForEmptyAuthor(t *testing.T) {
	t.Parallel()

	client := &Client{}
	properties, err := client.buildPageProperties(content.Content{
		ContentID: "empty-rich-text",
		Title:     "Empty rich text",
	}, pendingContentID("empty-rich-text"))
	if err != nil {
		t.Fatal(err)
	}
	payload, err := json.Marshal(properties)
	if err != nil {
		t.Fatal(err)
	}
	var decoded map[string]map[string]any
	if err := json.Unmarshal(payload, &decoded); err != nil {
		t.Fatal(err)
	}
	summary, ok := decoded[propertyNameSummary]["rich_text"].([]any)
	if !ok || len(summary) == 0 {
		t.Fatalf("Summary.rich_text = %#v, want non-empty JSON array", decoded[propertyNameSummary]["rich_text"])
	}
	author, ok := decoded[propertyNameAuthor]["rich_text"].([]any)
	if !ok {
		t.Fatalf("Author.rich_text = %#v, want JSON array", decoded[propertyNameAuthor]["rich_text"])
	}
	if len(author) != 0 {
		t.Fatalf("Author.rich_text = %#v, want empty array", author)
	}
}

func TestClientUsesContentIDCache(t *testing.T) {
	t.Parallel()

	var mu sync.Mutex
	queryCount := 0
	createCount := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		switch r.Method + " " + r.URL.Path {
		case "GET /v1/data_sources/ds-1":
			writeJSON(t, w, map[string]any{"id": "ds-1", "properties": completeProperties()})
		case "POST /v1/data_sources/ds-1/query":
			queryCount++
			writeJSON(t, w, map[string]any{"results": []any{}, "has_more": false, "next_cursor": nil})
		case "POST /v1/pages":
			createCount++
			writeJSON(t, w, map[string]any{"id": "page-1"})
		case "PATCH /v1/pages/page-1":
			writeJSON(t, w, map[string]any{"id": "page-1"})
		default:
			t.Fatalf("unexpected request %s %s", r.Method, r.URL.Path)
		}
	}))
	defer server.Close()

	client := newTestClient(t, config.NotionConfig{
		APIKey:       "secret",
		DatabaseID:   "db-1",
		DataSourceID: "ds-1",
	}, server.URL)
	item := content.Content{ContentID: "cache-me", Title: "Cached", Summary: "Summary"}

	if _, err := client.StoreContents(context.Background(), []content.Content{item}, true); err != nil {
		t.Fatalf("first StoreContents error: %v", err)
	}
	if _, err := client.StoreContents(context.Background(), []content.Content{item}, true); err != nil {
		t.Fatalf("second StoreContents error: %v", err)
	}
	if queryCount != 1 {
		t.Fatalf("queryCount = %d, want 1", queryCount)
	}
	if createCount != 1 {
		t.Fatalf("createCount = %d, want 1", createCount)
	}
}

func TestClientChecksNotionWhenFreshCacheMissesCrossInstanceWrite(t *testing.T) {
	t.Parallel()

	queryCount := 0
	createCount := 0
	server := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		switch request.Method + " " + request.URL.Path {
		case "GET /v1/data_sources/ds-1":
			writeJSON(
				t,
				writer,
				map[string]any{
					"id":         "ds-1",
					"properties": completeProperties(),
				},
			)
		case "POST /v1/data_sources/ds-1/query":
			queryCount++
			if queryCount == 1 {
				writeJSON(t, writer, map[string]any{
					"results":  []any{},
					"has_more": false,
				})
				return
			}
			var payload struct {
				Filter struct {
					Or []struct {
						Property string `json:"property"`
						RichText struct {
							Equals string `json:"equals"`
						} `json:"rich_text"`
					} `json:"or"`
				} `json:"filter"`
			}
			if err := json.NewDecoder(request.Body).Decode(&payload); err != nil {
				t.Fatal(err)
			}
			if len(payload.Filter.Or) != 2 ||
				payload.Filter.Or[0].Property != propertyNameContentID ||
				payload.Filter.Or[0].RichText.Equals != "cache-miss" ||
				payload.Filter.Or[1].RichText.Equals != pendingContentID("cache-miss") {
				t.Fatalf("exact lookup filter = %#v", payload.Filter.Or)
			}
			writeJSON(t, writer, map[string]any{
				"results": []any{
					map[string]any{
						"id": "page-from-other-instance",
						"properties": map[string]any{
							propertyNameContentID: map[string]any{
								"type": "rich_text",
								"rich_text": []any{
									map[string]any{
										"plain_text": "cache-miss",
									},
								},
							},
						},
					},
				},
				"has_more": false,
			})
		case "POST /v1/pages":
			createCount++
			writeJSON(t, writer, map[string]any{"id": "duplicate"})
		default:
			t.Fatalf(
				"unexpected request %s %s",
				request.Method,
				request.URL.Path,
			)
		}
	}))
	defer server.Close()

	client := newTestClient(t, config.NotionConfig{
		APIKey:       "secret",
		DatabaseID:   "db-1",
		DataSourceID: "ds-1",
	}, server.URL)
	if err := client.Initialize(context.Background()); err != nil {
		t.Fatal(err)
	}
	if _, _, err := client.existingContentIDs(
		context.Background(),
		false,
	); err != nil {
		t.Fatal(err)
	}
	results, err := client.StoreContents(
		context.Background(),
		[]content.Content{{
			ContentID: "cache-miss",
			Title:     "Existing elsewhere",
		}},
		true,
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(results) != 1 || !results[0] {
		t.Fatalf("results = %v", results)
	}
	if queryCount != 2 || createCount != 0 {
		t.Fatalf(
			"queryCount = %d, createCount = %d",
			queryCount,
			createCount,
		)
	}
}

func TestClientChecksExactIDsAfterIncompleteColdScan(t *testing.T) {
	t.Parallel()

	queryCount := 0
	createCount := 0
	server := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		switch request.Method + " " + request.URL.Path {
		case "GET /v1/data_sources/ds-1":
			writeJSON(t, writer, map[string]any{
				"id":         "ds-1",
				"properties": completeProperties(),
			})
		case "POST /v1/data_sources/ds-1/query":
			queryCount++
			if queryCount == 1 {
				writeJSON(t, writer, map[string]any{
					"results":  []any{},
					"has_more": false,
					"request_status": map[string]any{
						"type":              "incomplete",
						"incomplete_reason": "query_result_limit_reached",
					},
				})
				return
			}
			var payload struct {
				Filter struct {
					Or []struct {
						RichText struct {
							Equals string `json:"equals"`
						} `json:"rich_text"`
					} `json:"or"`
				} `json:"filter"`
			}
			if err := json.NewDecoder(request.Body).Decode(&payload); err != nil {
				t.Fatal(err)
			}
			if len(payload.Filter.Or) != 2 ||
				payload.Filter.Or[0].RichText.Equals != "over-10k" ||
				payload.Filter.Or[1].RichText.Equals !=
					pendingContentID("over-10k") {
				t.Fatalf("exact lookup filter = %#v", payload.Filter.Or)
			}
			writeJSON(t, writer, map[string]any{
				"results": []any{
					map[string]any{
						"id": "existing-page",
						"properties": map[string]any{
							propertyNameContentID: map[string]any{
								"type": "rich_text",
								"rich_text": []any{
									map[string]any{"plain_text": "over-10k"},
								},
							},
						},
					},
				},
				"has_more": false,
			})
		case "POST /v1/pages":
			createCount++
			writeJSON(t, writer, map[string]any{"id": "duplicate"})
		default:
			t.Fatalf(
				"unexpected request %s %s",
				request.Method,
				request.URL.Path,
			)
		}
	}))
	defer server.Close()

	client := newTestClient(t, config.NotionConfig{
		APIKey:       "secret",
		DatabaseID:   "db-1",
		DataSourceID: "ds-1",
	}, server.URL)
	results, err := client.StoreContents(
		context.Background(),
		[]content.Content{{
			ContentID: "over-10k",
			Title:     "Existing after query cap",
		}},
		true,
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(results) != 1 || !results[0] {
		t.Fatalf("results = %v", results)
	}
	if queryCount != 2 || createCount != 0 {
		t.Fatalf(
			"queryCount = %d, createCount = %d",
			queryCount,
			createCount,
		)
	}
}

func TestClientCachesEmptyContentIDQuery(t *testing.T) {
	t.Parallel()

	var mu sync.Mutex
	queryCount := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		switch r.Method + " " + r.URL.Path {
		case "GET /v1/data_sources/ds-1":
			writeJSON(t, w, map[string]any{"id": "ds-1", "properties": completeProperties()})
		case "POST /v1/data_sources/ds-1/query":
			queryCount++
			writeJSON(t, w, map[string]any{"results": []any{}, "has_more": false})
		default:
			t.Fatalf("unexpected request %s %s", r.Method, r.URL.Path)
		}
	}))
	defer server.Close()

	client := newTestClient(t, config.NotionConfig{
		APIKey:       "secret",
		DatabaseID:   "db-1",
		DataSourceID: "ds-1",
	}, server.URL)
	if err := client.Initialize(context.Background()); err != nil {
		t.Fatal(err)
	}
	if _, _, err := client.existingContentIDs(context.Background(), false); err != nil {
		t.Fatal(err)
	}
	if _, _, err := client.existingContentIDs(context.Background(), false); err != nil {
		t.Fatal(err)
	}
	if queryCount != 1 {
		t.Fatalf("queryCount = %d, want 1", queryCount)
	}
}

func TestClientInitializeFailsForMultipleDataSources(t *testing.T) {
	t.Parallel()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		writeJSON(t, w, map[string]any{"data_sources": []map[string]any{{"id": "ds-1"}, {"id": "ds-2"}}})
	}))
	defer server.Close()

	client := newTestClient(t, config.NotionConfig{APIKey: "secret", DatabaseID: "db-1"}, server.URL)
	err := client.Initialize(context.Background())
	if err == nil || !strings.Contains(err.Error(), "set DataSourceID explicitly") {
		t.Fatalf("Initialize error = %v, want multiple data source guidance", err)
	}
}

func TestClientHonorsRetryAfterAndRequestSpacing(t *testing.T) {
	t.Parallel()

	clock := &fakeClock{nowValue: time.Unix(0, 0)}
	var mu sync.Mutex
	requestTimes := make([]time.Time, 0, 3)
	attempt := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		requestTimes = append(requestTimes, clock.nowValue)
		attempt++
		currentAttempt := attempt
		mu.Unlock()
		if currentAttempt == 1 {
			w.Header().Set("Retry-After", "2")
			w.WriteHeader(http.StatusTooManyRequests)
			writeJSON(t, w, map[string]any{"code": "rate_limited", "message": "slow down"})
			return
		}
		writeJSON(t, w, map[string]any{"data_sources": []map[string]any{{"id": "ds-1"}}})
	}))
	defer server.Close()

	client := newTestClient(t, config.NotionConfig{APIKey: "secret", DatabaseID: "db-1"}, server.URL)
	client.now = clock.Now
	client.sleep = clock.Sleep

	if _, err := client.resolveDataSourceID(context.Background()); err != nil {
		t.Fatalf("resolveDataSourceID error: %v", err)
	}
	var response databaseResponse
	if err := client.doJSON(context.Background(), http.MethodGet, "/v1/databases/db-1", nil, nil, &response); err != nil {
		t.Fatalf("second doJSON error: %v", err)
	}
	if len(clock.sleeps) < 2 || clock.sleeps[0] != 2*time.Second || clock.sleeps[1] != 500*time.Millisecond {
		t.Fatalf("sleep sequence = %v, want [2s 500ms ...]", clock.sleeps)
	}
	if len(requestTimes) != 3 {
		t.Fatalf("request count = %d, want 3", len(requestTimes))
	}
	if got := requestTimes[1].Sub(requestTimes[0]); got != 2*time.Second {
		t.Fatalf("retry spacing = %v, want 2s", got)
	}
	if got := requestTimes[2].Sub(requestTimes[1]); got != 500*time.Millisecond {
		t.Fatalf("request spacing = %v, want 500ms", got)
	}
}

func TestClientRetriesReadOnlyQueryTransportAndServerFailures(t *testing.T) {
	t.Parallel()

	clock := &fakeClock{nowValue: time.Unix(0, 0)}
	attempts := 0
	client, err := NewClient(
		config.NotionConfig{
			APIKey:     "secret",
			DatabaseID: "db-1",
		},
		&http.Client{Transport: roundTripFunc(func(
			request *http.Request,
		) (*http.Response, error) {
			if request.Method != http.MethodPost ||
				!strings.HasSuffix(request.URL.Path, "/query") {
				return nil, fmt.Errorf(
					"unexpected request %s %s",
					request.Method,
					request.URL.Path,
				)
			}
			attempts++
			switch attempts {
			case 1:
				return nil, errors.New("temporary transport failure")
			case 2:
				return &http.Response{
					StatusCode: http.StatusServiceUnavailable,
					Status:     "503 Service Unavailable",
					Header: http.Header{
						"Retry-After": []string{"0"},
					},
					Body: io.NopCloser(strings.NewReader(
						`{"code":"service_unavailable"}`,
					)),
				}, nil
			default:
				return &http.Response{
					StatusCode: http.StatusOK,
					Status:     "200 OK",
					Header:     http.Header{},
					Body: io.NopCloser(strings.NewReader(
						`{"results":[],"has_more":false}`,
					)),
				}, nil
			}
		})},
	)
	if err != nil {
		t.Fatal(err)
	}
	client.baseURL = "https://notion.test"
	client.dataSourceID = "ds-1"
	client.now = clock.Now
	client.sleep = clock.Sleep

	ids, complete, err := client.existingContentIDs(
		context.Background(),
		true,
	)
	if err != nil {
		t.Fatal(err)
	}
	if attempts != 3 || len(ids) != 0 || !complete {
		t.Fatalf(
			"attempts=%d ids=%v complete=%v",
			attempts,
			ids,
			complete,
		)
	}
}

func TestClientBoundsStructuredAPIErrors(t *testing.T) {
	t.Parallel()

	message := strings.Repeat("x", maxNotionErrorBodyBytes*2)
	server := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		_ *http.Request,
	) {
		writer.Header().Set("Content-Type", "application/json")
		writer.WriteHeader(http.StatusBadRequest)
		if err := json.NewEncoder(writer).Encode(map[string]any{
			"object":  "error",
			"status":  http.StatusBadRequest,
			"code":    "validation_error",
			"message": message,
		}); err != nil {
			t.Fatalf("encode error response: %v", err)
		}
	}))
	defer server.Close()

	client := newTestClient(
		t,
		config.NotionConfig{APIKey: "secret", DatabaseID: "db-1"},
		server.URL,
	)
	var response databaseResponse
	err := client.doJSON(
		context.Background(),
		http.MethodGet,
		"/v1/databases/db-1",
		nil,
		nil,
		&response,
	)
	var httpErr *HTTPError
	if !errors.As(err, &httpErr) {
		t.Fatalf("doJSON error = %v, want HTTPError", err)
	}
	if len(httpErr.Message) > maxNotionErrorBodyBytes+3 ||
		len(httpErr.Body) > maxNotionErrorBodyBytes+3 {
		t.Fatalf(
			"error was not bounded: message=%d body=%d",
			len(httpErr.Message),
			len(httpErr.Body),
		)
	}
}

func newTestClient(t *testing.T, cfg config.NotionConfig, baseURL string) *Client {
	t.Helper()
	client, err := NewClient(cfg, &http.Client{Timeout: 5 * time.Second})
	if err != nil {
		t.Fatalf("NewClient error: %v", err)
	}
	client.baseURL = baseURL
	client.now = time.Now
	client.sleep = func(context.Context, time.Duration) error { return nil }
	return client
}

func completeProperties() map[string]any {
	return map[string]any{
		propertyNameTitle:     map[string]any{"id": "title", "name": propertyNameTitle, "type": "title"},
		propertyNameSummary:   map[string]any{"id": "summary", "name": propertyNameSummary, "type": "rich_text"},
		propertyNameContentID: map[string]any{"id": "content", "name": propertyNameContentID, "type": "rich_text"},
		propertyNameURL:       map[string]any{"id": "url", "name": propertyNameURL, "type": "url"},
		propertyNameAuthor:    map[string]any{"id": "author", "name": propertyNameAuthor, "type": "rich_text"},
		propertyNameKeywords:  map[string]any{"id": "keywords", "name": propertyNameKeywords, "type": "multi_select"},
		propertyNameTags:      map[string]any{"id": "tags", "name": propertyNameTags, "type": "multi_select"},
		propertyNameSource:    map[string]any{"id": "source", "name": propertyNameSource, "type": "select"},
		propertyNamePublished: map[string]any{"id": "published", "name": propertyNamePublished, "type": "date"},
	}
}

func makeParagraphMarkdown(count int) string {
	parts := make([]string, 0, count)
	for index := 1; index <= count; index++ {
		parts = append(parts, "Paragraph "+strconv.Itoa(index))
	}
	return strings.Join(parts, "\n\n")
}

func assertJSONGolden(t *testing.T, name string, actual []byte) {
	t.Helper()
	normalized := normalizeJSON(t, actual)
	path := filepath.Join("testdata", name)
	if os.Getenv("UPDATE_GOLDEN") == "1" {
		if err := os.WriteFile(path, normalized, 0o644); err != nil {
			t.Fatalf("write golden %s: %v", name, err)
		}
	}
	expected, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read golden %s: %v", name, err)
	}
	if string(expected) != string(normalized) {
		t.Fatalf("golden mismatch for %s\nexpected:\n%s\nactual:\n%s", name, expected, normalized)
	}
}

func normalizeJSON(t *testing.T, payload []byte) []byte {
	t.Helper()
	var value any
	if err := json.Unmarshal(payload, &value); err != nil {
		t.Fatalf("invalid JSON payload: %v\n%s", err, payload)
	}
	normalized, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		t.Fatalf("marshal normalized JSON: %v", err)
	}
	return append(normalized, '\n')
}

func writeJSON(t *testing.T, w http.ResponseWriter, payload any) {
	t.Helper()
	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(payload); err != nil {
		t.Fatalf("writeJSON: %v", err)
	}
}

func stringPtr(value string) *string { return &value }

type fakeClock struct {
	mu       sync.Mutex
	nowValue time.Time
	sleeps   []time.Duration
}

type roundTripFunc func(*http.Request) (*http.Response, error)

func (function roundTripFunc) RoundTrip(
	request *http.Request,
) (*http.Response, error) {
	return function(request)
}

func (c *fakeClock) Now() time.Time {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.nowValue
}

func (c *fakeClock) Sleep(_ context.Context, delay time.Duration) error {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.sleeps = append(c.sleeps, delay)
	c.nowValue = c.nowValue.Add(delay)
	return nil
}
