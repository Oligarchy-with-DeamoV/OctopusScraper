package processor

import (
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestOpenAICompatibleClientResponses(t *testing.T) {
	responses := map[string]struct {
		status int
		body   string
		want   string
		err    bool
	}{
		"/string/chat/completions": {
			status: http.StatusOK,
			body:   `{"choices":[{"message":{"content":"summary"}}]}`,
			want:   "summary",
		},
		"/parts/chat/completions": {
			status: http.StatusOK,
			body:   `{"choices":[{"message":{"content":[{"text":"part one"},{"text":" part two"}]}}]}`,
			want:   "part one part two",
		},
		"/empty/chat/completions": {
			status: http.StatusOK,
			body:   `{"choices":[]}`,
			err:    true,
		},
		"/invalid/chat/completions": {
			status: http.StatusOK,
			body:   `{`,
			err:    true,
		},
		"/failure/chat/completions": {
			status: http.StatusBadGateway,
			body:   `upstream failed`,
			err:    true,
		},
	}
	server := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		response := responses[request.URL.Path]
		if request.Header.Get("Authorization") != "Bearer secret" {
			http.Error(writer, "missing authorization", http.StatusUnauthorized)
			return
		}
		if request.Header.Get("Content-Type") != "application/json" {
			http.Error(writer, "missing content type", http.StatusBadRequest)
			return
		}
		writer.WriteHeader(response.status)
		_, _ = io.WriteString(writer, response.body)
	}))
	defer server.Close()

	client := NewOpenAICompatibleClient(server.Client(), BaseLLMProcessorConfig{})
	for path, expected := range responses {
		result, err := client.CreateChatCompletion(context.Background(), ChatRequest{
			BaseURL:        server.URL + strings.TrimSuffix(path, "/chat/completions"),
			APIKey:         "secret",
			Model:          "test-model",
			Messages:       []ChatMessage{{Role: "user", Content: "hello"}},
			Temperature:    0.2,
			MaxTokens:      100,
			ResponseFormat: "json_object",
		})
		if expected.err {
			if err == nil {
				t.Fatalf("%s: expected error, got %q", path, result)
			}
			continue
		}
		if err != nil || result != expected.want {
			t.Fatalf("%s: got %q, %v", path, result, err)
		}
	}
}

type failingRoundTripper struct {
	err  error
	body io.ReadCloser
}

func (r failingRoundTripper) RoundTrip(*http.Request) (*http.Response, error) {
	if r.err != nil {
		return nil, r.err
	}
	return &http.Response{
		StatusCode: http.StatusOK,
		Body:       r.body,
		Header:     make(http.Header),
	}, nil
}

type failingBody struct{}

func (failingBody) Read([]byte) (int, error) { return 0, errors.New("read failed") }
func (failingBody) Close() error             { return nil }

func TestOpenAICompatibleClientErrors(t *testing.T) {
	client := NewOpenAICompatibleClient(nil, BaseLLMProcessorConfig{})
	if client.httpClient == nil {
		t.Fatal("expected default HTTP client")
	}
	if _, err := client.CreateChatCompletion(context.Background(), ChatRequest{
		BaseURL: "://invalid",
	}); err == nil {
		t.Fatal("expected invalid request URL error")
	}

	client = NewOpenAICompatibleClient(&http.Client{
		Transport: failingRoundTripper{err: errors.New("network failed")},
	}, BaseLLMProcessorConfig{})
	if _, err := client.CreateChatCompletion(context.Background(), ChatRequest{
		BaseURL: "https://example.com",
	}); err == nil {
		t.Fatal("expected transport error")
	}

	client = NewOpenAICompatibleClient(&http.Client{
		Transport: failingRoundTripper{body: failingBody{}},
	}, BaseLLMProcessorConfig{})
	if _, err := client.CreateChatCompletion(context.Background(), ChatRequest{
		BaseURL: "https://example.com",
	}); err == nil {
		t.Fatal("expected response read error")
	}
}

func TestContentFromMessageValidation(t *testing.T) {
	if _, err := contentFromMessage([]any{"invalid", map[string]any{}}); err == nil {
		t.Fatal("expected empty content array error")
	}
	if _, err := contentFromMessage(42); err == nil {
		t.Fatal("expected unsupported content type error")
	}
	if snippet := errorBodySnippet(
		[]byte(strings.Repeat("x", maxLLMErrorBodyBytes+10)),
		maxLLMErrorBodyBytes,
	); len(snippet) != maxLLMErrorBodyBytes+3 {
		t.Fatalf("error snippet length = %d", len(snippet))
	}
}
