package notion

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/config"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
)

func TestUtilityValidationBranches(t *testing.T) {
	t.Parallel()

	t.Run("option names", func(t *testing.T) {
		long := strings.Repeat("界", maxOptionNameLength+1)
		tests := []struct {
			raw, want string
		}{
			{"", ""},
			{" \t\n ", ""},
			{"  alpha\t beta\n gamma  ", "alpha beta gamma"},
			{long, strings.Repeat("界", maxOptionNameLength)},
		}
		for _, test := range tests {
			if got := sanitizeOptionName(test.raw); got != test.want {
				t.Errorf("sanitizeOptionName(%q) = %q, want %q", test.raw, got, test.want)
			}
		}
	})

	t.Run("URLs", func(t *testing.T) {
		valid := "https://example.com/a?x=1"
		if got := sanitizeURL(valid); got == nil || *got != valid {
			t.Fatalf("sanitizeURL(%q) = %v, want valid URL", valid, got)
		}
		invalid := []string{
			"", "ftp://example.com", "https:///missing-host", "https://example.com/a b",
			"https://example.com/a\nb", "://bad", strings.Repeat("x", maxURLLength+1),
		}
		for _, raw := range invalid {
			if got := sanitizeURL(raw); got != nil {
				t.Errorf("sanitizeURL(%q) = %q, want nil", raw, *got)
			}
		}
	})

	t.Run("options and errors", func(t *testing.T) {
		values := sanitizeOptions([]string{" a ", "a", "", "b"})
		if got, want := strings.Join(values, ","), "a,b"; got != want {
			t.Fatalf("sanitizeOptions = %q, want %q", got, want)
		}
		many := make([]string, maxMultiSelectOptions+1)
		for i := range many {
			many[i] = fmt.Sprintf("option-%d", i)
		}
		if got := len(sanitizeOptions(many)); got != maxMultiSelectOptions {
			t.Fatalf("sanitizeOptions count = %d, want %d", got, maxMultiSelectOptions)
		}
		if got := limitRichTextSegments([]map[string]any{{"n": 1}}); len(got) != 1 {
			t.Fatalf("short rich text was changed: %#v", got)
		}
		if got := limitRichTextSegments(make([]map[string]any, maxRichTextItems+1)); len(got) != maxRichTextItems {
			t.Fatalf("long rich text count = %d, want %d", len(got), maxRichTextItems)
		}
		if got := joinErrors([]error{nil, errors.New("one"), nil, errors.New("two")}); got == nil ||
			!strings.Contains(got.Error(), "one") || !strings.Contains(got.Error(), "two") {
			t.Fatalf("joinErrors = %v", got)
		}
		if got := joinErrors(nil); got != nil {
			t.Fatalf("joinErrors(nil) = %v, want nil", got)
		}
	})

	t.Run("date and context", func(t *testing.T) {
		if got := parsePublishedDate("not a date"); got != nil {
			t.Fatalf("parsePublishedDate invalid = %q, want nil", *got)
		}
		ctx, cancel := context.WithCancel(context.Background())
		cancel()
		if err := sleepContext(ctx, time.Hour); !errors.Is(err, context.Canceled) {
			t.Fatalf("sleepContext canceled error = %v", err)
		}
		if err := sleepContext(context.Background(), 0); err != nil {
			t.Fatalf("sleepContext zero error = %v", err)
		}
	})
}

func TestHTTPErrorAndClientValidation(t *testing.T) {
	t.Parallel()

	if got := (&HTTPError{StatusCode: 400, Code: "bad", Message: "no"}).Error(); got != "notion API 400 bad: no" {
		t.Fatalf("structured HTTPError = %q", got)
	}
	if got := (&HTTPError{StatusCode: 500, Message: "no"}).Error(); got != "notion API 500: no" {
		t.Fatalf("plain HTTPError = %q", got)
	}
	for _, cfg := range []config.NotionConfig{
		{DatabaseID: "db"},
		{APIKey: "key"},
	} {
		if client, err := NewClient(cfg, nil); client != nil || err == nil {
			t.Fatalf("NewClient(%+v) = client %v, err %v", cfg, client, err)
		}
	}
	client, err := NewClient(config.NotionConfig{APIKey: "key", DatabaseID: "db"}, nil)
	if err != nil {
		t.Fatal(err)
	}
	if client.httpClient == nil || client.httpClient.Timeout != 30*time.Second {
		t.Fatalf("default HTTP client = %#v", client.httpClient)
	}
}

func TestDeliverSuccessAndFailure(t *testing.T) {
	t.Parallel()
	t.Run("success", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			switch r.Method + " " + r.URL.Path {
			case "POST /v1/data_sources/ds/query":
				writeJSON(t, w, map[string]any{"results": []any{}, "has_more": false})
			case "POST /v1/pages":
				writeJSON(t, w, map[string]any{"id": "page"})
			case "PATCH /v1/pages/page":
				writeJSON(t, w, map[string]any{})
			default:
				t.Fatalf("unexpected request %s %s", r.Method, r.URL.Path)
			}
		}))
		defer server.Close()
		client, _ := newFastCoverageClient(t, config.NotionConfig{APIKey: "key", DatabaseID: "db"}, server.URL)
		client.initialized, client.dataSourceID = true, "ds"
		if err := client.Deliver(context.Background(), content.Content{ContentID: "deliver", Title: "title"}); err != nil {
			t.Fatalf("Deliver error = %v", err)
		}
	})
	t.Run("store error", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(http.StatusBadGateway)
			writeJSON(t, w, map[string]any{"message": "query failed"})
		}))
		defer server.Close()
		client, _ := newFastCoverageClient(t, config.NotionConfig{APIKey: "key", DatabaseID: "db"}, server.URL)
		client.initialized, client.dataSourceID = true, "ds"
		if err := client.Deliver(context.Background(), content.Content{ContentID: "deliver"}); err == nil {
			t.Fatal("Deliver returned nil after StoreContents failure")
		}
	})
}

func TestMarkdownConverterEdgeCases(t *testing.T) {
	t.Parallel()

	converter := NewMarkdownConverter()
	if got := converter.Convert(" \r\n\t "); got != nil {
		t.Fatalf("empty conversion = %#v, want nil", got)
	}
	markdown := strings.Join([]string{
		"#### capped", "~~~python", "", "~~~", "after",
		"***", "___", "![bad](ftp://example.com/x) and ![alt](not url)",
		"> one", "> two", "1) first", "2. second", "- bullet", "+ plus",
		"| a | b |", "| --- | --- |", "| only |", "| too | many | cells |",
	}, "\n")
	blocks := converter.Convert(markdown)
	if len(blocks) == 0 {
		t.Fatal("edge-case markdown produced no blocks")
	}
	if blocks[0]["type"] != "heading_3" {
		t.Fatalf("heading type = %v, want heading_3", blocks[0]["type"])
	}
	if got := converter.Convert("```"); len(got) != 1 || got[0]["type"] != "code" {
		t.Fatalf("unclosed empty fence = %#v", got)
	}
	if got := converter.Convert("~~~\nline"); len(got) != 1 || got[0]["type"] != "code" {
		t.Fatalf("unclosed tilde fence = %#v", got)
	}
	if got := converter.makeCodeBlocks("", ""); len(got) != 1 {
		t.Fatalf("empty code blocks = %#v", got)
	}
	if got := converter.makeTableBlock([]string{"|"}); got != nil {
		t.Fatalf("empty table header = %#v, want nil", got)
	}
	if got := converter.makeTableBlock([]string{"| a |"}); got != nil {
		t.Fatalf("one-line table = %#v, want nil", got)
	}
	longCell := "|" + strings.Repeat("x", maxTextLength*(maxRichTextItems+1)) + "|"
	if got := makeTableRow([]string{longCell}, converter)["table_row"]; got == nil {
		t.Fatal("long table row is nil")
	}
	if got := converter.makeRichTextBlocks("paragraph", nil); got != nil {
		t.Fatalf("empty rich text blocks = %#v, want nil", got)
	}
	if got := converter.renderInline("[label](ftp://example.com)", defaultAnnotations()); len(got) != 1 {
		t.Fatalf("invalid inline link = %#v", got)
	}
	if got := applyLink([]map[string]any{{"type": "equation"}}, stringPtr("https://example.com")); len(got) != 1 {
		t.Fatalf("applyLink non-text = %#v", got)
	}
}

func TestMarkdownConverterTableAndCodeSplitting(t *testing.T) {
	t.Parallel()

	converter := NewMarkdownConverter()
	code := converter.makeCodeBlocks(strings.Repeat("x", maxTextLength*maxRichTextItems+1), "go")
	if len(code) != 2 {
		t.Fatalf("code block count = %d, want 2", len(code))
	}
	rows := converter.makeTableBlock([]string{
		"| h1 | h2 |", "| --- | --- |", "| one |", "| one | two | three |",
	})
	if rows == nil {
		t.Fatal("table is nil")
	}
	table := rows["table"].(map[string]any)
	if got := table["table_width"]; got != 2 {
		t.Fatalf("table width = %v, want 2", got)
	}
	lines := []string{"", "```go", "# h", "---", ">", "- x", "1. y", "| h | x |", "| --- | --- |"}
	for i, want := range []bool{true, true, true, true, true, true, true, true, false} {
		if got := converter.isBlockBoundary(lines, i); got != want {
			t.Errorf("isBlockBoundary(%d) = %v, want %v", i, got, want)
		}
	}
	if got := converter.makeParagraphBlocks("before ![alt](https://example.com) after"); len(got) != 3 {
		t.Fatalf("image paragraph blocks = %d, want 3", len(got))
	}
	if got := splitTextToRichText("linked", defaultAnnotations(), stringPtr("https://example.com")); len(got) != 1 {
		t.Fatalf("linked rich text = %#v", got)
	}
	if got := converter.renderInline("*", defaultAnnotations()); len(got) != 1 {
		t.Fatalf("literal special character = %#v", got)
	}
}

func newFastCoverageClient(t *testing.T, cfg config.NotionConfig, baseURL string) (*Client, *fakeClock) {
	t.Helper()
	client := newTestClient(t, cfg, baseURL)
	clock := &fakeClock{nowValue: time.Unix(0, 0)}
	client.now = clock.Now
	client.sleep = clock.Sleep
	return client, clock
}

func TestInitializePropertyFailuresAndIdempotence(t *testing.T) {
	t.Parallel()

	var dataSourceCalls atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.Method + " " + r.URL.Path {
		case "GET /v1/databases/db":
			writeJSON(t, w, map[string]any{"data_sources": []any{map[string]any{"id": "ds"}}})
		case "GET /v1/data_sources/ds":
			dataSourceCalls.Add(1)
			writeJSON(t, w, map[string]any{"properties": map[string]any{
				propertyNameTitle: map[string]any{"type": "number"},
			}})
		default:
			t.Fatalf("unexpected request %s %s", r.Method, r.URL.Path)
		}
	}))
	defer server.Close()

	client, _ := newFastCoverageClient(t, config.NotionConfig{APIKey: "key", DatabaseID: "db"}, server.URL)
	err := client.Initialize(context.Background())
	if err == nil || !strings.Contains(err.Error(), "expected") {
		t.Fatalf("Initialize error = %v", err)
	}
	if client.initialized {
		t.Fatal("failed initialization marked client initialized")
	}
	if got := dataSourceCalls.Load(); got != 1 {
		t.Fatalf("data source calls = %d, want 1", got)
	}
}

func TestInitializeFailsWhenDataSourceRetrievalFails(t *testing.T) {
	t.Parallel()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/v1/databases/db" {
			writeJSON(t, w, map[string]any{"data_sources": []any{map[string]any{"id": "ds"}}})
			return
		}
		w.WriteHeader(http.StatusBadGateway)
		writeJSON(t, w, map[string]any{"message": "unavailable"})
	}))
	defer server.Close()
	client, _ := newFastCoverageClient(t, config.NotionConfig{APIKey: "key", DatabaseID: "db"}, server.URL)
	if err := client.Initialize(context.Background()); err == nil || !strings.Contains(err.Error(), "unavailable") {
		t.Fatalf("Initialize error = %v", err)
	}
}

func TestResolveDataSourceIDPropagatesHTTPError(t *testing.T) {
	t.Parallel()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusBadGateway)
		writeJSON(t, w, map[string]any{"message": "database unavailable"})
	}))
	defer server.Close()
	client, _ := newFastCoverageClient(t, config.NotionConfig{APIKey: "key", DatabaseID: "db"}, server.URL)
	if _, err := client.resolveDataSourceID(context.Background()); err == nil {
		t.Fatal("resolveDataSourceID returned nil")
	}
}

func TestExistingContentIDsPaginatesAndReadsTextValues(t *testing.T) {
	t.Parallel()
	var calls atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/data_sources/ds/query" {
			t.Fatalf("unexpected request %s %s", r.Method, r.URL.Path)
		}
		if calls.Add(1) == 1 {
			writeJSON(t, w, map[string]any{
				"results": []any{map[string]any{"properties": map[string]any{
					propertyNameContentID: map[string]any{"rich_text": []any{
						map[string]any{"text": map[string]any{"content": "text-id"}, "plain_text": "ignored"},
						map[string]any{"plain_text": "plain-id"},
					}},
				}}},
				"has_more": true, "next_cursor": "cursor",
			})
			return
		}
		writeJSON(t, w, map[string]any{"results": []any{}, "has_more": false, "next_cursor": ""})
	}))
	defer server.Close()
	client, _ := newFastCoverageClient(t, config.NotionConfig{APIKey: "key", DatabaseID: "db"}, server.URL)
	client.dataSourceID = "ds"
	ids, full, err := client.existingContentIDs(context.Background(), true)
	if err != nil || !full || calls.Load() != 2 {
		t.Fatalf("ids=%v full=%v calls=%d err=%v", ids, full, calls.Load(), err)
	}
	if _, ok := ids["text-idplain-id"]; !ok {
		t.Fatalf("text rich text value missing: %v", ids)
	}
}

func TestPaginatedLookupAndArchivePendingPages(t *testing.T) {
	t.Parallel()

	var queryCalls, archiveCalls atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.Method + " " + r.URL.Path {
		case "POST /v1/data_sources/ds/query":
			queryCalls.Add(1)
			var payload map[string]any
			_ = json.NewDecoder(r.Body).Decode(&payload)
			cursor, _ := payload["start_cursor"].(string)
			if cursor == "" {
				writeJSON(t, w, map[string]any{
					"results": []any{map[string]any{"id": "p1", "properties": map[string]any{
						propertyNameContentID: map[string]any{"rich_text": []any{map[string]any{"plain_text": "id"}}},
					}}},
					"has_more": true, "next_cursor": "next",
				})
			} else {
				writeJSON(t, w, map[string]any{
					"results": []any{map[string]any{"id": "p2", "properties": map[string]any{
						propertyNameContentID: map[string]any{"rich_text": []any{map[string]any{"plain_text": pendingContentID("id")}}},
					}}},
					"has_more": false,
				})
			}
		case "PATCH /v1/pages/p1", "PATCH /v1/pages/p2":
			archiveCalls.Add(1)
			writeJSON(t, w, map[string]any{})
		default:
			t.Fatalf("unexpected request %s %s", r.Method, r.URL.Path)
		}
	}))
	defer server.Close()
	client, _ := newFastCoverageClient(t, config.NotionConfig{APIKey: "key", DatabaseID: "db"}, server.URL)
	client.dataSourceID = "ds"
	ids, err := client.lookupContentPages(context.Background(), "id", pendingContentID("id"))
	if err != nil || len(ids["id"]) != 1 || len(ids[pendingContentID("id")]) != 1 {
		t.Fatalf("lookup ids=%v err=%v", ids, err)
	}
	client.contentIDs = map[string]struct{}{pendingContentID("id"): {}}
	if err := client.archivePendingPages(context.Background(), pendingContentID("id")); err != nil {
		t.Fatal(err)
	}
	if queryCalls.Load() != 4 || archiveCalls.Load() != 2 {
		t.Fatalf("query calls=%d archive calls=%d", queryCalls.Load(), archiveCalls.Load())
	}
	if _, ok := client.contentIDs[pendingContentID("id")]; ok {
		t.Fatal("pending ID remained in cache")
	}
}

func TestIncompleteQueryErrors(t *testing.T) {
	t.Parallel()
	if err := incompleteQueryError(queryRequestStatus{Type: "ok"}); err != nil {
		t.Fatalf("complete query error = %v", err)
	}
	if got := incompleteQueryError(queryRequestStatus{Type: "incomplete"}); got == nil ||
		!strings.Contains(got.Error(), "unknown reason") {
		t.Fatalf("blank incomplete reason = %v", got)
	}
}

func TestReconcileExactPendingPageAndErrors(t *testing.T) {
	t.Parallel()
	t.Run("archives pending", func(t *testing.T) {
		var archived atomic.Int32
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.Method == http.MethodPost {
				writeJSON(t, w, map[string]any{"results": []any{map[string]any{
					"id": "pending-page", "properties": map[string]any{
						propertyNameContentID: map[string]any{"rich_text": []any{map[string]any{"plain_text": pendingContentID("id")}}},
					},
				}}, "has_more": false})
				return
			}

			archived.Add(1)
			writeJSON(t, w, map[string]any{})
		}))
		defer server.Close()
		client, _ := newFastCoverageClient(t, config.NotionConfig{APIKey: "key", DatabaseID: "db"}, server.URL)
		client.dataSourceID = "ds"
		existing := map[string]struct{}{pendingContentID("id"): {}}
		exists, err := client.reconcileExactContentPages(context.Background(), "id", existing)
		if err != nil || exists || archived.Load() != 1 {
			t.Fatalf("exists=%v err=%v archived=%d", exists, err, archived.Load())
		}
		if _, ok := existing[pendingContentID("id")]; ok {
			t.Fatal("pending ID remained after reconciliation")
		}
	})
	t.Run("archive failure", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.Method == http.MethodPost {
				writeJSON(t, w, map[string]any{"results": []any{map[string]any{
					"id": "pending-page", "properties": map[string]any{
						propertyNameContentID: map[string]any{"rich_text": []any{map[string]any{"plain_text": pendingContentID("id")}}},
					},
				}}, "has_more": false})
				return
			}
			w.WriteHeader(http.StatusBadRequest)
			writeJSON(t, w, map[string]any{"message": "archive failed"})
		}))
		defer server.Close()
		client, _ := newFastCoverageClient(t, config.NotionConfig{APIKey: "key", DatabaseID: "db"}, server.URL)
		client.dataSourceID = "ds"
		if _, err := client.reconcileExactContentPages(context.Background(), "id", map[string]struct{}{}); err == nil {
			t.Fatal("archive failure returned nil")
		}
	})
}

func TestArchivePendingPagesFailureModes(t *testing.T) {
	t.Parallel()
	for _, test := range []struct {
		name string
		mode string
	}{
		{"query", "query"},
		{"incomplete", "incomplete"},
		{"archive", "archive"},
	} {
		t.Run(test.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.Method == http.MethodPost {
					if test.mode == "query" {
						w.WriteHeader(http.StatusBadGateway)
						writeJSON(t, w, map[string]any{"message": "query failed"})
					} else if test.mode == "incomplete" {
						writeJSON(t, w, map[string]any{
							"request_status": map[string]any{"type": "incomplete"},
						})
					} else {
						writeJSON(t, w, map[string]any{"results": []any{map[string]any{
							"id": "p", "properties": map[string]any{},
						}}, "has_more": false})
					}
					return
				}
				w.WriteHeader(http.StatusBadRequest)
				writeJSON(t, w, map[string]any{"message": "archive failed"})
			}))
			defer server.Close()
			client, _ := newFastCoverageClient(t, config.NotionConfig{APIKey: "key", DatabaseID: "db"}, server.URL)
			client.dataSourceID = "ds"
			if err := client.archivePendingPages(context.Background(), "pending"); err == nil {
				t.Fatal("archivePendingPages returned nil")
			}
		})
	}
}

func TestStoreContentsValidationAndRetryRecovery(t *testing.T) {
	t.Parallel()

	var queries, creates atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.Method + " " + r.URL.Path {
		case "GET /v1/databases/db":
			writeJSON(t, w, map[string]any{"data_sources": []any{map[string]any{"id": "ds"}}})
		case "GET /v1/data_sources/ds":
			writeJSON(t, w, map[string]any{"properties": completeProperties()})
		case "POST /v1/data_sources/ds/query":
			n := queries.Add(1)
			if n == 1 {
				writeJSON(t, w, map[string]any{"results": []any{}, "has_more": false})
			} else {
				writeJSON(t, w, map[string]any{"results": []any{map[string]any{
					"id": "created-elsewhere", "properties": map[string]any{
						propertyNameContentID: map[string]any{"rich_text": []any{map[string]any{"plain_text": "retry"}}},
					},
				}}, "has_more": false})
			}
		case "POST /v1/pages":
			creates.Add(1)
			w.WriteHeader(http.StatusBadGateway)
			writeJSON(t, w, map[string]any{"message": "temporary"})
		default:
			t.Fatalf("unexpected request %s %s", r.Method, r.URL.Path)
		}
	}))
	defer server.Close()
	client, clock := newFastCoverageClient(t, config.NotionConfig{
		APIKey: "key", DatabaseID: "db", RetryDelay: time.Second,
	}, server.URL)
	results, err := client.StoreContents(context.Background(), []content.Content{
		{ContentID: "", Title: "invalid"},
		{ContentID: "retry", Title: "retryable"},
		{ContentID: "retry", Title: "duplicate"},
	}, true)
	if err == nil || len(results) != 3 || results[0] || !results[1] || !results[2] {
		t.Fatalf("results=%v err=%v", results, err)
	}
	if creates.Load() != 1 || queries.Load() != 2 || len(clock.sleeps) == 0 {
		t.Fatalf("creates=%d queries=%d sleeps=%v", creates.Load(), queries.Load(), clock.sleeps)
	}
}

func TestStoreContentsEmptyAndPendingRecovery(t *testing.T) {
	t.Parallel()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.Method + " " + r.URL.Path {
		case "GET /v1/databases/db":
			writeJSON(t, w, map[string]any{"data_sources": []any{map[string]any{"id": "ds"}}})
		case "GET /v1/data_sources/ds":
			writeJSON(t, w, map[string]any{"properties": completeProperties()})
		case "POST /v1/data_sources/ds/query":
			writeJSON(t, w, map[string]any{"results": []any{map[string]any{
				"id": "pending-page", "properties": map[string]any{
					propertyNameContentID: map[string]any{"rich_text": []any{map[string]any{
						"plain_text": pendingContentID("fresh"),
					}}},
				},
			}}, "has_more": false})
		case "PATCH /v1/pages/pending-page":
			writeJSON(t, w, map[string]any{})
		case "POST /v1/pages":
			writeJSON(t, w, map[string]any{"id": "new-page"})
		case "PATCH /v1/pages/new-page":
			writeJSON(t, w, map[string]any{})
		default:
			t.Fatalf("unexpected request %s %s", r.Method, r.URL.Path)
		}
	}))
	defer server.Close()
	client, _ := newFastCoverageClient(t, config.NotionConfig{APIKey: "key", DatabaseID: "db"}, server.URL)
	if got, err := client.StoreContents(context.Background(), nil, true); err != nil || len(got) != 0 {
		t.Fatalf("empty StoreContents = %v, %v", got, err)
	}
	results, err := client.StoreContents(context.Background(), []content.Content{{ContentID: "fresh", Title: "fresh"}}, true)
	if err != nil || len(results) != 1 || !results[0] {
		t.Fatalf("pending StoreContents = %v, %v", results, err)
	}
}

func TestStoreContentsRetryRecoveryBranches(t *testing.T) {
	t.Parallel()
	for _, mode := range []string{"pending-error", "reconcile-success", "reconcile-error", "store-error"} {
		t.Run(mode, func(t *testing.T) {
			clock := &fakeClock{nowValue: time.Unix(0, 0)}
			var createCalls, queryCalls int
			client, err := NewClient(config.NotionConfig{
				APIKey: "key", DatabaseID: "db", RetryDelay: time.Second,
			}, &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
				switch r.Method + " " + r.URL.Path {
				case "POST /v1/pages":
					createCalls++
					return coverageHTTPResponse(http.StatusBadRequest, `{"message":"create failed"}`), nil
				case "PATCH /v1/pages/pending":
					return coverageHTTPResponse(http.StatusBadRequest, `{"message":"archive failed"}`), nil
				case "POST /v1/data_sources/ds/query":
					queryCalls++
					switch mode {
					case "pending-error":
						return coverageHTTPResponse(http.StatusOK, fmt.Sprintf(`{"results":[{"id":"pending","properties":{"ContentId":{"rich_text":[{"plain_text":%q}]}}}],"has_more":false}`, pendingContentID("id"))), nil
					case "reconcile-success":
						if queryCalls == 1 {
							return coverageHTTPResponse(http.StatusOK, `{"results":[],"has_more":false}`), nil
						}
						if queryCalls == 2 {
							return coverageHTTPResponse(http.StatusOK, `{"results":[],"has_more":false,"request_status":{"type":"incomplete"}}`), nil
						}
						return coverageHTTPResponse(http.StatusOK, `{"results":[{"id":"final","properties":{"ContentId":{"rich_text":[{"plain_text":"id"}]}}}],"has_more":false}`), nil
					case "reconcile-error":
						if queryCalls == 1 {
							return coverageHTTPResponse(http.StatusOK, `{"results":[],"has_more":false}`), nil
						}
						if queryCalls == 2 {
							return coverageHTTPResponse(http.StatusOK, `{"results":[],"has_more":false,"request_status":{"type":"incomplete"}}`), nil
						}
						return coverageHTTPResponse(http.StatusBadRequest, `{"message":"lookup failed"}`), nil
					default:
						return coverageHTTPResponse(http.StatusOK, `{"results":[],"has_more":false}`), nil
					}
				default:
					return nil, fmt.Errorf("unexpected request %s %s", r.Method, r.URL.Path)
				}
			})})
			if err != nil {
				t.Fatal(err)
			}
			client.initialized, client.dataSourceID = true, "ds"
			client.now, client.sleep = clock.Now, clock.Sleep
			client.contentIDs, client.cacheFull = map[string]struct{}{}, true
			if mode != "pending-error" {
				client.cacheAt = clock.Now()
			}
			results, storeErr := client.StoreContents(context.Background(), []content.Content{{ContentID: "id", Title: "title"}}, true)
			switch mode {
			case "pending-error", "reconcile-error", "store-error":
				if storeErr == nil || len(results) != 1 || results[0] {
					t.Fatalf("results=%v err=%v", results, storeErr)
				}
			case "reconcile-success":
				if storeErr != nil || !results[0] {
					t.Fatalf("results=%v err=%v", results, storeErr)
				}
			}
			if mode == "store-error" && createCalls != 2 {
				t.Fatalf("create calls = %d, want 2", createCalls)
			}
		})
	}
}

func TestStoreOneCompensatesPartialPages(t *testing.T) {
	t.Parallel()

	for _, test := range []struct {
		name       string
		failPath   string
		archiveErr bool
		want       string
	}{
		{"append", "/v1/blocks/page/children", false, "append blocks"},
		{"append archive failure", "/v1/blocks/page/children", true, "archive partial page"},
		{"finalize", "/v1/pages/page", false, "finalize page"},
		{"finalize archive failure", "/v1/pages/page", true, "archive partial page"},
	} {
		t.Run(test.name, func(t *testing.T) {
			var archive atomic.Int32
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				path := r.URL.Path
				switch {
				case r.Method == http.MethodPost && path == "/v1/pages":
					writeJSON(t, w, map[string]any{"id": "page"})
				case r.Method == http.MethodPatch && path == "/v1/blocks/page/children":
					w.WriteHeader(http.StatusBadRequest)
					writeJSON(t, w, map[string]any{"message": "failed"})
				case r.Method == http.MethodPatch && path == "/v1/pages/page":
					var payload map[string]any
					_ = json.NewDecoder(r.Body).Decode(&payload)
					if payload["in_trash"] == true {
						archive.Add(1)
						if test.archiveErr {
							w.WriteHeader(http.StatusBadRequest)
						}

						writeJSON(t, w, map[string]any{})
						return
					}
					if test.failPath == "/v1/pages/page" {
						w.WriteHeader(http.StatusBadRequest)
						writeJSON(t, w, map[string]any{"message": "failed"})
						return
					}
					if test.archiveErr {
						w.WriteHeader(http.StatusBadRequest)
					}
					writeJSON(t, w, map[string]any{})
				default:
					t.Fatalf("unexpected request %s %s", r.Method, path)
				}
			}))
			defer server.Close()
			client, _ := newFastCoverageClient(t, config.NotionConfig{APIKey: "key", DatabaseID: "db"}, server.URL)
			client.dataSourceID = "ds"
			body := "one block"
			if strings.Contains(test.name, "append") {
				body = strings.Repeat("x\n\n", 101)
			}
			item := content.Content{ContentID: test.name, Title: "title", Content: body}
			err := client.storeOne(context.Background(), item)
			if err == nil || !strings.Contains(err.Error(), test.want) {
				t.Fatalf("storeOne error = %v, want %q", err, test.want)
			}
			if archive.Load() != 1 {
				t.Fatalf("archive calls = %d, want 1", archive.Load())
			}
		})
	}
}

func TestStoreOneArchivesAfterCreationContextCancellation(t *testing.T) {
	t.Parallel()

	var appendCalls, archiveCalls atomic.Int32
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.Method + " " + r.URL.Path {
		case "POST /v1/pages":
			writeJSON(t, w, map[string]any{"id": "page"})
		case "PATCH /v1/blocks/page/children":
			appendCalls.Add(1)
			writeJSON(t, w, map[string]any{})
		case "PATCH /v1/pages/page":
			var payload map[string]any
			if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
				t.Fatalf("decode archive payload: %v", err)
			}
			if payload["in_trash"] != true {
				t.Fatalf("page update payload = %#v, want archive payload", payload)
			}
			archiveCalls.Add(1)
			writeJSON(t, w, map[string]any{})
		default:
			t.Fatalf("unexpected request %s %s", r.Method, r.URL.Path)
		}
	}))
	defer server.Close()

	client, _ := newFastCoverageClient(
		t,
		config.NotionConfig{APIKey: "key", DatabaseID: "db"},
		server.URL,
	)
	client.dataSourceID = "ds"
	client.httpClient = &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		response, err := http.DefaultTransport.RoundTrip(r)
		if err == nil && r.Method == http.MethodPost && r.URL.Path == "/v1/pages" {
			response.Body = cancelOnEOFBody{ReadCloser: response.Body, cancel: cancel}
		}
		return response, err
	})}
	err := client.storeOne(ctx, content.Content{
		ContentID: "canceled",
		Title:     "title",
		Content:   makeParagraphMarkdown(maxBlocksPerRequest + 1),
	})
	if err == nil || !strings.Contains(err.Error(), "append blocks") {
		t.Fatalf("storeOne error = %v, want append failure", err)
	}
	if got := appendCalls.Load(); got != 0 {
		t.Fatalf("append calls = %d, want 0 after cancellation", got)
	}
	if got := archiveCalls.Load(); got != 1 {
		t.Fatalf("archive calls = %d, want 1", got)
	}
}

func TestArchivePageAfterFailureUsesBoundedContext(t *testing.T) {
	t.Parallel()

	type contextKey string
	const key contextKey = "cleanup-value"
	var sawDeadline atomic.Bool
	var sawValue atomic.Bool
	client, _ := newFastCoverageClient(
		t,
		config.NotionConfig{APIKey: "key", DatabaseID: "db"},
		"https://notion.test",
	)
	client.httpClient = &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		if _, ok := r.Context().Deadline(); !ok {
			t.Error("cleanup request has no deadline")
		} else {
			sawDeadline.Store(true)
		}
		if r.Context().Value(key) == "retained" {
			sawValue.Store(true)
		}
		return nil, context.DeadlineExceeded
	})}

	ctx, cancel := context.WithCancel(context.WithValue(context.Background(), key, "retained"))
	cancel()
	err := client.archivePageAfterFailure(ctx, "page")
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("archivePageAfterFailure error = %v, want deadline exceeded", err)
	}
	if !sawDeadline.Load() {
		t.Fatal("cleanup request did not carry a deadline")
	}
	if !sawValue.Load() {
		t.Fatal("cleanup request did not retain context values")
	}
}

func TestDoJSONFailureModes(t *testing.T) {
	t.Parallel()

	t.Run("marshal and URL errors", func(t *testing.T) {
		client, _ := newFastCoverageClient(t, config.NotionConfig{APIKey: "key", DatabaseID: "db"}, "://bad")
		if err := client.doJSON(context.Background(), http.MethodPost, "/x", nil, map[string]any{"bad": make(chan int)}, nil); err == nil {
			t.Fatal("marshal failure returned nil")
		}
		if err := client.doJSON(context.Background(), http.MethodGet, "/x", nil, nil, nil); err == nil {
			t.Fatal("invalid URL returned nil")
		}
	})

	t.Run("response decoding and body failures", func(t *testing.T) {
		client, _ := NewClient(config.NotionConfig{APIKey: "key", DatabaseID: "db"}, &http.Client{
			Transport: roundTripFunc(func(*http.Request) (*http.Response, error) {
				return &http.Response{StatusCode: http.StatusOK, Body: io.NopCloser(strings.NewReader("{"))}, nil
			}),
		})
		client.baseURL = "https://notion.test"
		if err := client.doJSON(context.Background(), http.MethodGet, "/x", nil, nil, &map[string]any{}); err == nil {
			t.Fatal("malformed JSON returned nil")
		}
		client.httpClient = &http.Client{Transport: roundTripFunc(func(*http.Request) (*http.Response, error) {
			return &http.Response{StatusCode: http.StatusOK, Body: errReader{}}, nil
		})}
		if err := client.doJSON(context.Background(), http.MethodGet, "/x", nil, nil, nil); err == nil {
			t.Fatal("read failure returned nil")
		}
	})

	t.Run("HTTP error shapes and safe methods", func(t *testing.T) {
		responses := []string{"plain text", `{"message":"message only"}`}
		for _, body := range responses {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				w.WriteHeader(http.StatusBadRequest)
				_, _ = io.WriteString(w, body)
			}))
			client, _ := newFastCoverageClient(t, config.NotionConfig{APIKey: "key", DatabaseID: "db"}, server.URL)
			err := client.doJSON(context.Background(), http.MethodPatch, "/x", nil, nil, nil)
			server.Close()
			var httpErr *HTTPError
			if !errors.As(err, &httpErr) || httpErr.StatusCode != http.StatusBadRequest {
				t.Fatalf("HTTP error = %v", err)
			}
		}
		client, clock := newFastCoverageClient(t, config.NotionConfig{APIKey: "key", DatabaseID: "db"}, "https://unused")
		attempts := 0
		client.httpClient.Transport = roundTripFunc(func(*http.Request) (*http.Response, error) {
			attempts++
			return &http.Response{StatusCode: http.StatusServiceUnavailable, Body: io.NopCloser(strings.NewReader("bad"))}, nil
		})
		if err := client.doJSON(context.Background(), http.MethodPatch, "/x", nil, nil, nil); err == nil {
			t.Fatal("unsafe method unexpectedly retried")
		}
		if attempts != 1 {
			t.Fatalf("unsafe attempts = %d, want 1", attempts)
		}
		if len(clock.sleeps) != 0 {
			t.Fatalf("unsafe sleeps = %v", clock.sleeps)
		}
	})

	t.Run("oversized response", func(t *testing.T) {
		if _, err := readNotionResponse(strings.NewReader(strings.Repeat("x", maxNotionResponseBytes+1))); err == nil {
			t.Fatal("oversized response returned nil")
		}
	})
}

func TestDoJSONTransportAndContextFailures(t *testing.T) {
	t.Parallel()
	t.Run("unsafe transport failure", func(t *testing.T) {
		client, _ := NewClient(config.NotionConfig{APIKey: "key", DatabaseID: "db"}, &http.Client{
			Transport: roundTripFunc(func(*http.Request) (*http.Response, error) {
				return nil, errors.New("transport failed")
			}),
		})
		client.baseURL = "https://notion.test"
		if err := client.doJSON(context.Background(), http.MethodPatch, "/x", nil, nil, nil); err == nil {
			t.Fatal("unsafe transport failure returned nil")
		}
	})
	t.Run("safe retries exhausted", func(t *testing.T) {
		clock := &fakeClock{nowValue: time.Unix(0, 0)}
		client, err := NewClient(config.NotionConfig{APIKey: "key", DatabaseID: "db"}, &http.Client{
			Transport: roundTripFunc(func(*http.Request) (*http.Response, error) {
				return nil, errors.New("temporary")
			}),
		})
		if err != nil {
			t.Fatal(err)
		}
		client.baseURL, client.now, client.sleep = "https://notion.test", clock.Now, clock.Sleep
		if err := client.doJSON(context.Background(), http.MethodGet, "/x", nil, nil, nil); err == nil ||
			!strings.Contains(err.Error(), "temporary") {
			t.Fatalf("safe transport error = %v", err)
		}
	})
	t.Run("retry sleep cancellation", func(t *testing.T) {
		client, err := NewClient(config.NotionConfig{APIKey: "key", DatabaseID: "db"}, &http.Client{
			Transport: roundTripFunc(func(*http.Request) (*http.Response, error) {
				return &http.Response{StatusCode: http.StatusServiceUnavailable, Body: io.NopCloser(strings.NewReader("retry"))}, nil
			}),
		})
		if err != nil {
			t.Fatal(err)
		}
		client.baseURL = "https://notion.test"
		client.sleep = func(context.Context, time.Duration) error { return context.Canceled }
		if err := client.doJSON(context.Background(), http.MethodGet, "/x", nil, nil, nil); !errors.Is(err, context.Canceled) {
			t.Fatalf("retry cancellation error = %v", err)
		}
	})
	t.Run("request turn cancellation", func(t *testing.T) {
		client, _ := newFastCoverageClient(t, config.NotionConfig{APIKey: "key", DatabaseID: "db"}, "https://notion.test")
		client.sleep = func(context.Context, time.Duration) error { return context.DeadlineExceeded }
		client.nextRequest = time.Now().Add(time.Hour)
		if err := client.doJSON(context.Background(), http.MethodGet, "/x", nil, nil, nil); !errors.Is(err, context.DeadlineExceeded) {
			t.Fatalf("request turn error = %v", err)
		}
	})
}

func TestStoreContentsInitializationAndReconcileErrors(t *testing.T) {
	t.Parallel()
	t.Run("initialization", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(http.StatusBadGateway)
			writeJSON(t, w, map[string]any{"message": "initialization failed"})
		}))
		defer server.Close()
		client, _ := newFastCoverageClient(t, config.NotionConfig{APIKey: "key", DatabaseID: "db"}, server.URL)
		if _, err := client.StoreContents(context.Background(), []content.Content{{ContentID: "id"}}, true); err == nil {
			t.Fatal("StoreContents returned nil after initialization failure")
		}
	})
	t.Run("exact lookup", func(t *testing.T) {
		client, clock := newFastCoverageClient(t, config.NotionConfig{APIKey: "key", DatabaseID: "db"}, "https://notion.test")
		client.initialized, client.dataSourceID = true, "ds"
		client.cacheAt, client.contentIDs, client.cacheFull = clock.Now(), map[string]struct{}{}, true
		client.httpClient.Transport = roundTripFunc(func(*http.Request) (*http.Response, error) {
			return coverageHTTPResponse(http.StatusOK, `{"request_status":{"type":"incomplete"}}`), nil
		})
		if _, err := client.StoreContents(context.Background(), []content.Content{{ContentID: "id"}}, true); err == nil {
			t.Fatal("StoreContents returned nil after incomplete exact lookup")
		}
	})
}

func TestStoreContentsRetryCanStoreAfterInitialFailure(t *testing.T) {
	t.Parallel()
	clock := &fakeClock{nowValue: time.Unix(0, 0)}
	var creates, queries int
	client, err := NewClient(config.NotionConfig{APIKey: "key", DatabaseID: "db", RetryDelay: time.Second}, &http.Client{
		Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
			switch r.Method + " " + r.URL.Path {
			case "POST /v1/data_sources/ds/query":
				queries++
				return coverageHTTPResponse(http.StatusOK, `{"results":[],"has_more":false}`), nil
			case "POST /v1/pages":
				creates++
				if creates == 1 {
					return coverageHTTPResponse(http.StatusBadRequest, `{"message":"first create failed"}`), nil
				}
				return coverageHTTPResponse(http.StatusOK, `{"id":"page"}`), nil
			case "PATCH /v1/pages/page":
				return coverageHTTPResponse(http.StatusOK, `{}`), nil
			default:
				return nil, fmt.Errorf("unexpected request %s %s", r.Method, r.URL.Path)
			}
		}),
	})
	if err != nil {
		t.Fatal(err)
	}
	client.initialized, client.dataSourceID = true, "ds"
	client.now, client.sleep = clock.Now, clock.Sleep
	client.cacheAt, client.contentIDs, client.cacheFull = clock.Now(), map[string]struct{}{}, true
	results, storeErr := client.StoreContents(context.Background(), []content.Content{{ContentID: "id", Title: "title"}}, true)
	if storeErr != nil || len(results) != 1 || !results[0] || creates != 2 || queries != 2 {
		t.Fatalf("results=%v err=%v creates=%d queries=%d", results, storeErr, creates, queries)
	}
}

func TestBuildPagePropertiesDefaultsAndNewToken(t *testing.T) {
	t.Parallel()
	client := &Client{}
	properties, err := client.buildPageProperties(content.Content{ContentID: "id"}, "pending")
	if err != nil {
		t.Fatal(err)
	}
	title := properties[propertyNameTitle].(map[string]any)["title"].([]map[string]any)
	if title[0]["text"].(map[string]any)["content"] != "Untitled" {
		t.Fatalf("default title = %#v", title)
	}
	token := newToken("test")
	if !strings.HasPrefix(token, "test-") {
		t.Fatalf("newToken = %q", token)
	}
}

func TestTransportRetrySleepFailure(t *testing.T) {
	t.Parallel()
	client, err := NewClient(config.NotionConfig{APIKey: "key", DatabaseID: "db"}, &http.Client{
		Transport: roundTripFunc(func(*http.Request) (*http.Response, error) {
			return nil, errors.New("temporary transport")
		}),
	})
	if err != nil {
		t.Fatal(err)
	}
	client.baseURL = "https://notion.test"
	client.sleep = func(context.Context, time.Duration) error { return context.Canceled }
	if err := client.doJSON(context.Background(), http.MethodGet, "/x", nil, nil, nil); !errors.Is(err, context.Canceled) {
		t.Fatalf("transport retry error = %v", err)
	}
}

func TestRetryAndRateLimitHelpers(t *testing.T) {
	t.Parallel()

	for _, test := range []struct {
		status int
		safe   bool
		want   bool
	}{
		{http.StatusTooManyRequests, false, true}, {529, false, true},
		{http.StatusInternalServerError, true, true}, {http.StatusBadGateway, true, true},
		{http.StatusServiceUnavailable, true, true}, {http.StatusGatewayTimeout, true, true},
		{http.StatusInternalServerError, false, false}, {http.StatusBadRequest, true, false},
	} {
		if got := shouldRetry(test.status, test.safe); got != test.want {
			t.Errorf("shouldRetry(%d, %v) = %v, want %v", test.status, test.safe, got, test.want)
		}
	}
	if got := computeRetryDelay(&http.Response{Header: http.Header{"Retry-After": []string{"bad"}}}, 5); got != 30*time.Second {
		t.Fatalf("invalid Retry-After delay = %v", got)
	}
	if got := computeRetryDelay(&http.Response{Header: http.Header{"Retry-After": []string{"2"}}}, 0); got != 2*time.Second {
		t.Fatalf("valid Retry-After delay = %v", got)
	}
	if got := defaultRetryDelay(10); got != 30*time.Second {
		t.Fatalf("retry delay cap = %v", got)
	}
	if maxTime(time.Unix(2, 0), time.Unix(1, 0)) != time.Unix(2, 0) {
		t.Fatal("maxTime did not select later first value")
	}
}

func TestLookupContentPagesFailureModes(t *testing.T) {
	t.Parallel()
	for _, incomplete := range []bool{false, true} {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			if incomplete {
				writeJSON(t, w, map[string]any{"request_status": map[string]any{"type": "incomplete", "incomplete_reason": "capped"}})
				return
			}
			w.WriteHeader(http.StatusBadGateway)
			writeJSON(t, w, map[string]any{"message": "lookup failed"})
		}))
		client, _ := newFastCoverageClient(t, config.NotionConfig{APIKey: "key", DatabaseID: "db"}, server.URL)
		client.dataSourceID = "ds"
		if _, err := client.lookupContentPages(context.Background(), "id"); err == nil {
			t.Fatalf("lookupContentPages(%v) returned nil", incomplete)
		}
		server.Close()
	}
}

func TestCacheFinalContentIDInitializesCache(t *testing.T) {
	t.Parallel()
	client := &Client{now: time.Now}
	client.cacheFinalContentID("id")
	if _, ok := client.contentIDs["id"]; !ok || client.cacheAt.IsZero() || client.cacheFull {
		t.Fatalf("initialized cache = %#v at=%v full=%v", client.contentIDs, client.cacheAt, client.cacheFull)
	}
}

func TestStoreContentsRetryDelayAndRefreshErrors(t *testing.T) {
	t.Parallel()
	t.Run("delay", func(t *testing.T) {
		client, clock := newFastCoverageClient(t, config.NotionConfig{APIKey: "key", DatabaseID: "db", RetryDelay: time.Second}, "https://notion.test")
		client.initialized, client.dataSourceID = true, "ds"
		client.cacheAt, client.contentIDs, client.cacheFull = clock.Now(), map[string]struct{}{}, true
		client.sleep = func(context.Context, time.Duration) error { return context.Canceled }
		results, err := client.StoreContents(context.Background(), []content.Content{{ContentID: ""}}, true)
		if err == nil || results[0] || !errors.Is(err, context.Canceled) {
			t.Fatalf("results=%v err=%v", results, err)
		}
	})
	t.Run("refresh", func(t *testing.T) {
		client, clock := newFastCoverageClient(t, config.NotionConfig{APIKey: "key", DatabaseID: "db", RetryDelay: time.Second}, "https://notion.test")
		client.initialized, client.dataSourceID = true, "ds"
		client.cacheAt, client.contentIDs, client.cacheFull = clock.Now(), map[string]struct{}{}, true
		client.httpClient.Transport = roundTripFunc(func(*http.Request) (*http.Response, error) {
			return coverageHTTPResponse(http.StatusBadGateway, `{"message":"refresh failed"}`), nil
		})
		results, err := client.StoreContents(context.Background(), []content.Content{{ContentID: ""}}, true)
		if err == nil || results[0] {
			t.Fatalf("results=%v err=%v", results, err)
		}
	})
}

type errReader struct{}

func (errReader) Read([]byte) (int, error) { return 0, errors.New("read failed") }
func (errReader) Close() error             { return nil }

var _ io.ReadCloser = errReader{}

type cancelOnEOFBody struct {
	io.ReadCloser
	cancel context.CancelFunc
}

func (body cancelOnEOFBody) Read(p []byte) (int, error) {
	n, err := body.ReadCloser.Read(p)
	if err == io.EOF {
		body.cancel()
	}
	return n, err
}

func coverageHTTPResponse(status int, body string) *http.Response {
	return &http.Response{
		StatusCode: status,
		Status:     fmt.Sprintf("%d", status),
		Header:     make(http.Header),
		Body:       io.NopCloser(strings.NewReader(body)),
	}
}
