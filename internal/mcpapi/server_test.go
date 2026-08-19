package mcpapi

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"slices"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/config"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/storage"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

type fakeContentReader struct {
	list func(context.Context, storage.ContentListOptions) (storage.ContentListPage, error)
	get  func(context.Context, string) (storage.ContentRecord, bool, error)
}

func (f fakeContentReader) ListContents(ctx context.Context, opts storage.ContentListOptions) (storage.ContentListPage, error) {
	if f.list != nil {
		return f.list(ctx, opts)
	}
	return storage.ContentListPage{}, nil
}

func (f fakeContentReader) GetContent(ctx context.Context, contentID string) (storage.ContentRecord, bool, error) {
	if f.get != nil {
		return f.get(ctx, contentID)
	}
	return storage.ContentRecord{}, false, nil
}

type authTransport struct {
	token string
	base  http.RoundTripper
}

func (t authTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	req.Header.Set("Authorization", "Bearer "+t.token)
	return t.base.RoundTrip(req)
}

func TestAuthorizationAndOrigin(t *testing.T) {
	handler := NewHandler(
		context.Background(),
		discardLogger(),
		fakeContentReader{},
		testConfig(),
		"test",
	)
	for _, test := range []struct {
		name   string
		token  string
		origin string
		want   int
	}{
		{name: "missing", want: http.StatusUnauthorized},
		{name: "incorrect", token: "wrong", want: http.StatusUnauthorized},
		{name: "origin", token: "secret", origin: "https://example.com", want: http.StatusForbidden},
	} {
		t.Run(test.name, func(t *testing.T) {
			request := mcpRequest(t, test.token, `{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}`)
			if test.origin != "" {
				request.Header.Set("Origin", test.origin)
			}
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, request)
			if response.Code != test.want {
				t.Fatalf("status = %d, want %d: %s", response.Code, test.want, response.Body.String())
			}
		})
	}
}

func TestCorrectTokenConnectsAndToolsListIsReadOnly(t *testing.T) {
	httpServer := httptest.NewServer(NewHandler(
		context.Background(),
		discardLogger(),
		fakeContentReader{},
		testConfig(),
		"test",
	))
	defer httpServer.Close()
	session := connectClient(t, httpServer.URL, "secret")
	result, err := session.ListTools(context.Background(), nil)
	if err != nil {
		t.Fatal(err)
	}
	names := make([]string, 0, len(result.Tools))
	for _, tool := range result.Tools {
		names = append(names, tool.Name)
		if tool.OutputSchema == nil {
			t.Fatalf("%s output schema is nil", tool.Name)
		}
		if tool.Annotations == nil || !tool.Annotations.ReadOnlyHint {
			t.Fatalf("%s readOnlyHint not set: %#v", tool.Name, tool.Annotations)
		}
	}
	slices.Sort(names)
	if !slices.Equal(names, []string{getContentTool, listContentsTool}) {
		t.Fatalf("tool names = %#v", names)
	}
}

func TestListContentsFiltersPaginationAndEmptyResult(t *testing.T) {
	firstTime := time.Date(2026, 8, 19, 10, 0, 0, 0, time.UTC)
	secondTime := firstTime.Add(-time.Minute)
	var calls atomic.Int32
	reader := fakeContentReader{list: func(_ context.Context, opts storage.ContentListOptions) (storage.ContentListPage, error) {
		switch calls.Add(1) {
		case 1:
			if opts.Limit != 2 ||
				opts.ScraperName != "Feed" ||
				!slices.Equal(opts.Tags, []string{"alpha", "beta"}) ||
				opts.CollectedAfter == nil ||
				opts.CollectedBefore == nil ||
				opts.Cursor != nil {
				t.Fatalf("unexpected first opts: %#v", opts)
			}
			return storage.ContentListPage{
				Items: []storage.ContentMetadata{
					metadata("one", firstTime),
					metadata("two", secondTime),
				},
				NextCursor: &storage.ContentListCursor{
					CreatedAt: secondTime,
					ContentID: "two",
				},
			}, nil
		case 2:
			if opts.Cursor == nil ||
				!opts.Cursor.CreatedAt.Equal(secondTime) ||
				opts.Cursor.ContentID != "two" {
				t.Fatalf("unexpected cursor opts: %#v", opts.Cursor)
			}
			return storage.ContentListPage{}, nil
		default:
			t.Fatalf("unexpected call")
			return storage.ContentListPage{}, nil
		}
	}}
	httpServer := httptest.NewServer(NewHandler(
		context.Background(),
		discardLogger(),
		reader,
		testConfig(),
		"test",
	))
	defer httpServer.Close()
	session := connectClient(t, httpServer.URL, "secret")

	first := callTool[listContentsOutput](t, session, listContentsTool, map[string]any{
		"limit":            2,
		"scraper_name":     "Feed",
		"tags":             []string{"alpha", "", "beta", "alpha"},
		"collected_after":  "2026-08-19T09:00:00Z",
		"collected_before": "2026-08-19T11:00:00Z",
	})
	if len(first.Contents) != 2 || first.NextCursor == "" {
		t.Fatalf("unexpected first output: %#v", first)
	}
	if first.Contents[0].ContentID != "one" {
		t.Fatalf("wrong item: %#v", first.Contents[0])
	}
	second := callTool[listContentsOutput](t, session, listContentsTool, map[string]any{
		"cursor": first.NextCursor,
	})
	if len(second.Contents) != 0 || second.NextCursor != "" {
		t.Fatalf("unexpected empty page: %#v", second)
	}
}

func TestListContentsArgumentValidation(t *testing.T) {
	session := connectClientForReader(t, fakeContentReader{})
	for _, test := range []struct {
		name      string
		arguments map[string]any
		want      string
	}{
		{name: "limit low", arguments: map[string]any{"limit": -1}, want: "limit"},
		{name: "limit high", arguments: map[string]any{"limit": 51}, want: "limit"},
		{name: "cursor", arguments: map[string]any{"cursor": "not-base64"}, want: "cursor"},
		{name: "after", arguments: map[string]any{"collected_after": "yesterday"}, want: "collected_after"},
		{name: "before", arguments: map[string]any{"collected_before": "tomorrow"}, want: "collected_before"},
		{name: "range", arguments: map[string]any{
			"collected_after":  "2026-08-19T12:00:00Z",
			"collected_before": "2026-08-19T11:00:00Z",
		}, want: "collected_after"},
	} {
		t.Run(test.name, func(t *testing.T) {
			result, err := session.CallTool(context.Background(), &mcp.CallToolParams{
				Name:      listContentsTool,
				Arguments: test.arguments,
			})
			if err != nil {
				t.Fatal(err)
			}
			if !result.IsError || !strings.Contains(textContent(t, result), test.want) {
				t.Fatalf("result = %#v, text = %q", result, textContent(t, result))
			}
		})
	}
}

func TestGetContentNotFoundUnicodeChunkingAndValidation(t *testing.T) {
	record := storage.ContentRecord{
		ContentMetadata: metadata("content-1", time.Date(2026, 8, 19, 10, 0, 0, 0, time.UTC)),
		Content:         "a界🙂b",
	}
	reader := fakeContentReader{get: func(_ context.Context, contentID string) (storage.ContentRecord, bool, error) {
		if contentID == "missing" {
			return storage.ContentRecord{}, false, nil
		}
		return record, true, nil
	}}
	session := connectClientForReader(t, reader)
	chunk := callTool[getContentOutput](t, session, getContentTool, map[string]any{
		"content_id": "content-1",
		"offset":     1,
		"max_chars":  2,
	})
	if chunk.Content != "界🙂" || chunk.NextOffset != 3 || !chunk.Truncated {
		t.Fatalf("chunk = %#v", chunk)
	}
	empty := callTool[getContentOutput](t, session, getContentTool, map[string]any{
		"content_id": "content-1",
		"offset":     20,
		"max_chars":  2,
	})
	if empty.Content != "" || empty.NextOffset != 4 || empty.Truncated {
		t.Fatalf("empty chunk = %#v", empty)
	}
	full := callTool[getContentOutput](t, session, getContentTool, map[string]any{
		"content_id": "content-1",
	})
	if full.Content != "a界🙂b" || full.NextOffset != 4 || full.Truncated {
		t.Fatalf("full content = %#v", full)
	}
	result, err := session.CallTool(context.Background(), &mcp.CallToolParams{
		Name:      getContentTool,
		Arguments: map[string]any{"content_id": "missing"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if !result.IsError || !strings.Contains(textContent(t, result), "content_id not found") {
		t.Fatalf("missing result = %#v, text = %q", result, textContent(t, result))
	}
	for _, test := range []struct {
		name      string
		arguments map[string]any
		want      string
	}{
		{name: "id", arguments: map[string]any{}, want: "content_id"},
		{name: "offset", arguments: map[string]any{"content_id": "content-1", "offset": -1}, want: "offset"},
		{name: "max low", arguments: map[string]any{"content_id": "content-1", "max_chars": -1}, want: "max_chars"},
		{name: "max high", arguments: map[string]any{"content_id": "content-1", "max_chars": 50001}, want: "max_chars"},
	} {
		t.Run(test.name, func(t *testing.T) {
			result, err := session.CallTool(context.Background(), &mcp.CallToolParams{
				Name:      getContentTool,
				Arguments: test.arguments,
			})
			if err != nil {
				t.Fatal(err)
			}
			if !result.IsError || !strings.Contains(textContent(t, result), test.want) {
				t.Fatalf("result = %#v, text = %q", result, textContent(t, result))
			}
		})
	}
}

func TestTimeoutDBErrorOverloadAndShutdownCancellation(t *testing.T) {
	t.Run("timeout", func(t *testing.T) {
		svc := &service{
			reader: fakeContentReader{list: func(ctx context.Context, _ storage.ContentListOptions) (storage.ContentListPage, error) {
				<-ctx.Done()
				return storage.ContentListPage{}, ctx.Err()
			}},
			cfg:      config.MCPConfig{QueryTimeout: 10 * time.Millisecond},
			shutdown: context.Background(),
		}
		_, _, err := svc.listContents(context.Background(), nil, listContentsInput{})
		if !errors.Is(err, context.DeadlineExceeded) {
			t.Fatalf("timeout err = %v", err)
		}
	})
	t.Run("db error", func(t *testing.T) {
		session := connectClientForReader(t, fakeContentReader{list: func(context.Context, storage.ContentListOptions) (storage.ContentListPage, error) {
			return storage.ContentListPage{}, errors.New("database unavailable")
		}})
		result, err := session.CallTool(context.Background(), &mcp.CallToolParams{Name: listContentsTool, Arguments: map[string]any{}})
		if err != nil {
			t.Fatal(err)
		}
		if !result.IsError || !strings.Contains(textContent(t, result), "database unavailable") {
			t.Fatalf("db error result = %#v, text = %q", result, textContent(t, result))
		}
	})
	t.Run("get db error", func(t *testing.T) {
		session := connectClientForReader(t, fakeContentReader{get: func(context.Context, string) (storage.ContentRecord, bool, error) {
			return storage.ContentRecord{}, false, errors.New("database unavailable")
		}})
		result, err := session.CallTool(context.Background(), &mcp.CallToolParams{
			Name:      getContentTool,
			Arguments: map[string]any{"content_id": "content-1"},
		})
		if err != nil {
			t.Fatal(err)
		}
		if !result.IsError || !strings.Contains(textContent(t, result), "database unavailable") {
			t.Fatalf("get db error result = %#v, text = %q", result, textContent(t, result))
		}
	})
	t.Run("overload", func(t *testing.T) {
		entered := make(chan struct{})
		release := make(chan struct{})
		reader := fakeContentReader{list: func(context.Context, storage.ContentListOptions) (storage.ContentListPage, error) {
			close(entered)
			<-release
			return storage.ContentListPage{}, nil
		}}
		handler := NewHandler(
			context.Background(),
			discardLogger(),
			reader,
			config.MCPConfig{
				APIToken:             "secret",
				QueryTimeout:         time.Second,
				MaxConcurrentQueries: 1,
			},
			"test",
		)
		done := make(chan int, 1)
		go func() {
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, mcpRequest(t, "secret", toolCallBody(listContentsTool, map[string]any{})))
			done <- response.Code
		}()
		<-entered
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, mcpRequest(t, "secret", toolCallBody(listContentsTool, map[string]any{})))
		close(release)
		if response.Code != http.StatusTooManyRequests {
			t.Fatalf("status = %d, want 429: %s", response.Code, response.Body.String())
		}
		if code := <-done; code != http.StatusOK {
			t.Fatalf("first status = %d", code)
		}
	})
	t.Run("shutdown", func(t *testing.T) {
		root, cancelRoot := context.WithCancel(context.Background())
		cancelRoot()
		svc := &service{
			reader: fakeContentReader{list: func(ctx context.Context, _ storage.ContentListOptions) (storage.ContentListPage, error) {
				<-ctx.Done()
				return storage.ContentListPage{}, ctx.Err()
			}},
			cfg:      config.MCPConfig{QueryTimeout: time.Second},
			shutdown: root,
		}
		_, _, err := svc.listContents(context.Background(), nil, listContentsInput{})
		if !errors.Is(err, context.Canceled) {
			t.Fatalf("shutdown err = %v", err)
		}
	})
}

func TestToolLoggingDoesNotIncludeArguments(t *testing.T) {
	var buffer bytes.Buffer
	logger := slog.New(slog.NewTextHandler(&buffer, nil))
	svc := &service{
		reader: fakeContentReader{get: func(context.Context, string) (storage.ContentRecord, bool, error) {
			return storage.ContentRecord{}, false, nil
		}},
		logger:   logger,
		cfg:      testConfig(),
		shutdown: context.Background(),
	}
	_, _, err := svc.getContent(context.Background(), nil, getContentInput{ContentID: "secret-content-id"})
	if err == nil {
		t.Fatal("expected not found error")
	}
	logLine := buffer.String()
	for _, allowed := range []string{"tool", "duration_ms", "result"} {
		if !strings.Contains(logLine, allowed) {
			t.Fatalf("log missing %q: %s", allowed, logLine)
		}
	}
	if strings.Contains(logLine, "secret-content-id") {
		t.Fatalf("log contains tool argument: %s", logLine)
	}
}

func TestHelperEdgeCases(t *testing.T) {
	if got := nonNilStrings(nil); len(got) != 0 {
		t.Fatalf("nonNilStrings(nil) = %#v", got)
	}
	text, next, truncated := sliceRunes("abc", 1, 10)
	if text != "bc" || next != 3 || truncated {
		t.Fatalf("sliceRunes = %q, %d, %t", text, next, truncated)
	}
	for _, cursor := range []string{
		base64.RawURLEncoding.EncodeToString([]byte("{")),
		base64.RawURLEncoding.EncodeToString([]byte(`{"created_at":"bad","content_id":"id"}`)),
		base64.RawURLEncoding.EncodeToString([]byte(`{"created_at":"2026-08-19T10:00:00Z"}`)),
	} {
		if _, err := decodeCursor(cursor); err == nil {
			t.Fatalf("decodeCursor(%q) unexpectedly succeeded", cursor)
		}
	}
	ctx, cancel := context.WithCancel(context.Background())
	svc := &service{cfg: config.MCPConfig{}, shutdown: ctx}
	queryCtx, stop := svc.queryContext(context.Background())
	cancel()
	<-queryCtx.Done()
	stop()
	if !errors.Is(queryCtx.Err(), context.Canceled) {
		t.Fatalf("query context err = %v", queryCtx.Err())
	}
	response := httptest.NewRecorder()
	limitConcurrency(0, http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNoContent)
	})).ServeHTTP(response, httptest.NewRequest(http.MethodPost, "/mcp", nil))
	if response.Code != http.StatusNoContent {
		t.Fatalf("limit <= 0 status = %d", response.Code)
	}
}

func connectClientForReader(t *testing.T, reader storage.ContentReader) *mcp.ClientSession {
	t.Helper()
	httpServer := httptest.NewServer(NewHandler(
		context.Background(),
		discardLogger(),
		reader,
		testConfig(),
		"test",
	))
	t.Cleanup(httpServer.Close)
	return connectClient(t, httpServer.URL, "secret")
}

func connectClient(t *testing.T, endpoint, token string) *mcp.ClientSession {
	t.Helper()
	client := mcp.NewClient(&mcp.Implementation{Name: "test-client", Version: "v0.0.1"}, nil)
	session, err := client.Connect(
		context.Background(),
		&mcp.StreamableClientTransport{
			Endpoint:             endpoint,
			DisableStandaloneSSE: true,
			HTTPClient: &http.Client{Transport: authTransport{
				token: token,
				base:  http.DefaultTransport,
			}},
		},
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = session.Close() })
	return session
}

func callTool[T any](t *testing.T, session *mcp.ClientSession, name string, arguments map[string]any) T {
	t.Helper()
	result, err := session.CallTool(context.Background(), &mcp.CallToolParams{
		Name:      name,
		Arguments: arguments,
	})
	if err != nil {
		t.Fatal(err)
	}
	if result.IsError {
		t.Fatalf("tool returned error: %s", textContent(t, result))
	}
	var output T
	encoded, err := json.Marshal(result.StructuredContent)
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(encoded, &output); err != nil {
		t.Fatalf("decode structured content: %v: %s", err, encoded)
	}
	if textContent(t, result) == "" {
		t.Fatal("missing JSON text compatibility content")
	}
	return output
}

func textContent(t *testing.T, result *mcp.CallToolResult) string {
	t.Helper()
	if len(result.Content) == 0 {
		return ""
	}
	text, ok := result.Content[0].(*mcp.TextContent)
	if !ok {
		t.Fatalf("content type = %T", result.Content[0])
	}
	return text.Text
}

func metadata(id string, collectedAt time.Time) storage.ContentMetadata {
	author := "Author"
	scraper := "Feed"
	return storage.ContentMetadata{
		ContentID:   id,
		Title:       "Title " + id,
		Link:        "https://example.com/" + id,
		Summary:     "Summary",
		Published:   "source-time",
		Author:      &author,
		Keywords:    []string{"keyword"},
		Tags:        []string{"alpha"},
		ScraperName: &scraper,
		CollectedAt: collectedAt,
	}
}

func mcpRequest(t *testing.T, token, body string) *http.Request {
	t.Helper()
	request := httptest.NewRequest(http.MethodPost, "/mcp", strings.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Add("Accept", "application/json")
	request.Header.Add("Accept", "text/event-stream")
	if token != "" {
		request.Header.Set("Authorization", "Bearer "+token)
	}
	return request
}

func toolCallBody(name string, arguments map[string]any) string {
	body, _ := json.Marshal(map[string]any{
		"jsonrpc": "2.0",
		"id":      1,
		"method":  "tools/call",
		"params": map[string]any{
			"name":      name,
			"arguments": arguments,
		},
	})
	return string(body)
}

func testConfig() config.MCPConfig {
	return config.MCPConfig{
		APIToken:             "secret",
		QueryTimeout:         time.Second,
		MaxConcurrentQueries: 4,
	}
}

func discardLogger() *slog.Logger {
	return slog.New(slog.NewTextHandler(io.Discard, nil))
}
