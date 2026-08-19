package processor

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
)

type fakeBrowser struct {
	html  string
	err   error
	calls atomic.Int32
}

func (b *fakeBrowser) RenderHTML(
	_ context.Context,
	_ string,
	_ BrowserRenderOptions,
) (string, error) {
	b.calls.Add(1)
	if b.err != nil {
		return "", b.err
	}
	return b.html, nil
}

func TestHTMLProcessorFallsBackToHTTPAndConvertsMarkdown(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if got := r.Header.Get("User-Agent"); got != "OctopusTest/1.0" {
			t.Fatalf("user-agent = %q", got)
		}
		_, _ = w.Write([]byte(`<html><body><article><h1>Hello</h1><p>World</p><pre><code>fmt.Println(&#34;hi&#34;)</code></pre></article></body></html>`))
	}))
	defer server.Close()

	browser := &fakeBrowser{err: errors.New("browser down")}
	processor, err := newHTMLContentProcessor(map[string]any{
		"user_agent":      "OctopusTest/1.0",
		"browserless_url": "ws://browserless",
		"use_browser":     true,
		"priority":        1,
	}, htmlProcessorDeps{browserRenderer: browser, httpClient: server.Client()})
	if err != nil {
		t.Fatalf("newHTMLContentProcessor() error = %v", err)
	}

	items, err := processor.Process(context.Background(), []content.Content{{Link: server.URL, Content: "original"}})
	if err != nil {
		t.Fatalf("Process() error = %v", err)
	}
	if browser.calls.Load() != 1 {
		t.Fatalf("browser calls = %d, want 1", browser.calls.Load())
	}
	want := "# Hello\n\nWorld\n\n```\nfmt.Println(\"hi\")\n```"
	if items[0].Content != want {
		t.Fatalf("markdown = %q, want %q", items[0].Content, want)
	}
}

func TestHTMLProcessorPreservesOriginalOnPerItemFailure(t *testing.T) {
	processor, err := newHTMLContentProcessor(
		map[string]any{"priority": 1},
		htmlProcessorDeps{
			httpClient: &http.Client{},
			retryDelay: time.Millisecond,
		},
	)
	if err != nil {
		t.Fatalf("newHTMLContentProcessor() error = %v", err)
	}
	original := "keep me"
	items, err := processor.Process(context.Background(), []content.Content{{Link: "http://127.0.0.1:1", Content: original}})
	if err != nil {
		t.Fatalf("Process() error = %v", err)
	}
	if items[0].Content != original {
		t.Fatalf("content = %q, want original %q", items[0].Content, original)
	}
}

func TestHTMLProcessorRetriesTransientHTTPFailures(t *testing.T) {
	var requests atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		_ *http.Request,
	) {
		if requests.Add(1) < htmlFetchAttempts {
			http.Error(writer, "temporary", http.StatusBadGateway)
			return
		}
		_, _ = writer.Write([]byte("<article><p>recovered</p></article>"))
	}))
	defer server.Close()
	processor, err := newHTMLContentProcessor(
		map[string]any{"priority": 1, "use_browser": false},
		htmlProcessorDeps{
			httpClient: server.Client(),
			retryDelay: time.Millisecond,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	items, err := processor.Process(
		context.Background(),
		[]content.Content{{Link: server.URL, Content: "original"}},
	)
	if err != nil {
		t.Fatal(err)
	}
	if requests.Load() != htmlFetchAttempts || items[0].Content != "recovered" {
		t.Fatalf("requests=%d content=%q", requests.Load(), items[0].Content)
	}
}
