package processor

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
)

type fakeLLMClient struct {
	response string
	err      error
	calls    atomic.Int32
}

func (c *fakeLLMClient) CreateChatCompletion(_ context.Context, _ ChatRequest) (string, error) {
	c.calls.Add(1)
	if c.err != nil {
		return "", c.err
	}
	return c.response, nil
}

func TestLLMSummaryProcessorUsesFallbackAndCache(t *testing.T) {
	client := &fakeLLMClient{err: errors.New("boom")}
	processor, err := newLLMSummaryProcessor(map[string]any{
		"enable_fallback":    true,
		"summary_style":      "bullet_points",
		"max_summary_length": 20,
		"retry_times":        1,
	}, func(BaseLLMProcessorConfig) LLMClient { return client })
	if err != nil {
		t.Fatalf("newLLMSummaryProcessor() error = %v", err)
	}

	item := content.Content{
		Title:   "Title",
		Content: strings.Repeat("First sentence. ", 25),
	}
	items, err := processor.Process(context.Background(), []content.Content{item})
	if err != nil {
		t.Fatalf("Process() error = %v", err)
	}
	if items[0].Summary == "" || items[0].Summary[0] != '-' {
		t.Fatalf("fallback summary = %q, want bullet fallback", items[0].Summary)
	}
	if client.calls.Load() != 1 {
		t.Fatalf("client calls = %d, want 1", client.calls.Load())
	}

	cachedClient := &fakeLLMClient{response: "should not be called"}
	processor.client = cachedClient
	items, err = processor.Process(context.Background(), []content.Content{item})
	if err != nil {
		t.Fatalf("Process() second call error = %v", err)
	}
	if cachedClient.calls.Load() != 0 {
		t.Fatalf("cached client calls = %d, want 0", cachedClient.calls.Load())
	}
}

func TestLLMKeywordsProcessorFiltersDedupesAndCaps(t *testing.T) {
	client := &fakeLLMClient{response: `{"keywords":["AI","the","AI","multi agent systems","Go"],"importance_scores":{"AI":0.95,"the":0.9,"multi agent systems":0.7,"Go":0.4}}`}
	processor, err := newLLMKeywordsProcessor(map[string]any{
		"max_keywords":         2,
		"min_keyword_length":   2,
		"max_keyword_length":   10,
		"min_importance_score": 0.5,
		"include_phrases":      false,
	}, func(BaseLLMProcessorConfig) LLMClient { return client })
	if err != nil {
		t.Fatalf("newLLMKeywordsProcessor() error = %v", err)
	}

	items, err := processor.Process(context.Background(), []content.Content{{Title: "AI", Content: "AI and Go power multi agent systems"}})
	if err != nil {
		t.Fatalf("Process() error = %v", err)
	}
	want := []string{"AI"}
	if fmt.Sprint(items[0].Keywords) != fmt.Sprint(want) {
		t.Fatalf("keywords = %v, want %v", items[0].Keywords, want)
	}
}

func TestLLMKeywordsProcessorIncludesPhrasesAndUsesKeywordsCount(t *testing.T) {
	client := &fakeLLMClient{response: `{"keywords":["Go","AI"],"phrases":["multi agent systems"]}`}
	processor, err := newLLMKeywordsProcessor(map[string]any{
		"keywords_count":     2,
		"max_keywords":       10,
		"max_keyword_length": 30,
		"include_phrases":    true,
	}, func(BaseLLMProcessorConfig) LLMClient { return client })
	if err != nil {
		t.Fatalf("newLLMKeywordsProcessor() error = %v", err)
	}

	items, err := processor.Process(
		context.Background(),
		[]content.Content{{
			Title:   "Agents",
			Content: "Go and AI power reliable multi agent systems",
		}},
	)
	if err != nil {
		t.Fatalf("Process() error = %v", err)
	}
	want := []string{"Go", "AI"}
	if fmt.Sprint(items[0].Keywords) != fmt.Sprint(want) {
		t.Fatalf("keywords = %v, want %v", items[0].Keywords, want)
	}

	processor.config.KeywordsCount = 3
	processor.cache = newKeywordsCache()
	items, err = processor.Process(
		context.Background(),
		[]content.Content{{
			Title:   "Agents",
			Content: "Go and AI power reliable multi agent systems",
		}},
	)
	if err != nil {
		t.Fatalf("Process() error = %v", err)
	}
	want = []string{"Go", "AI", "multi agent systems"}
	if fmt.Sprint(items[0].Keywords) != fmt.Sprint(want) {
		t.Fatalf("keywords = %v, want %v", items[0].Keywords, want)
	}
}

func TestLLMKeywordsProcessorTreatsEmptyScoresAsAbsent(t *testing.T) {
	client := &fakeLLMClient{
		response: `{"keywords":["Go"],"importance_scores":{}}`,
	}
	processor, err := newLLMKeywordsProcessor(map[string]any{
		"min_importance_score": 0.9,
	}, func(BaseLLMProcessorConfig) LLMClient { return client })
	if err != nil {
		t.Fatalf("newLLMKeywordsProcessor() error = %v", err)
	}

	items, err := processor.Process(
		context.Background(),
		[]content.Content{{
			Title:   "Go",
			Content: "The Go release improves runtime performance and tooling",
		}},
	)
	if err != nil {
		t.Fatalf("Process() error = %v", err)
	}
	if fmt.Sprint(items[0].Keywords) != fmt.Sprint([]string{"Go"}) {
		t.Fatalf("keywords = %v", items[0].Keywords)
	}
}

func TestLLMTagsProcessorAppliesConfidenceAndAvailableTags(t *testing.T) {
	client := &fakeLLMClient{response: `{"tags":["AI","News","AI","Other"],"confidence":{"AI":0.9,"News":0.6,"Other":0.95}}`}
	processor, err := newLLMTagsProcessor(map[string]any{
		"max_tags":             2,
		"available_tags":       []any{"AI", "News"},
		"allow_new_tags":       false,
		"confidence_threshold": 0.7,
	}, func(BaseLLMProcessorConfig) LLMClient { return client })
	if err != nil {
		t.Fatalf("newLLMTagsProcessor() error = %v", err)
	}

	items, err := processor.Process(
		context.Background(),
		[]content.Content{{
			Title:   "AI update",
			Content: "AI platform news",
		}},
	)
	if err != nil {
		t.Fatalf("Process() error = %v", err)
	}
	want := []string{"AI"}
	if fmt.Sprint(items[0].Tags) != fmt.Sprint(want) {
		t.Fatalf("tags = %v, want %v", items[0].Tags, want)
	}
}

func TestLLMTagsProcessorTreatsEmptyScoresAsAbsent(t *testing.T) {
	client := &fakeLLMClient{
		response: `{"tags":["Go"],"confidence":{}}`,
	}
	processor, err := newLLMTagsProcessor(map[string]any{
		"confidence_threshold": 0.9,
	}, func(BaseLLMProcessorConfig) LLMClient { return client })
	if err != nil {
		t.Fatalf("newLLMTagsProcessor() error = %v", err)
	}

	items, err := processor.Process(
		context.Background(),
		[]content.Content{{Title: "Go", Content: "Go release"}},
	)
	if err != nil {
		t.Fatalf("Process() error = %v", err)
	}
	if fmt.Sprint(items[0].Tags) != fmt.Sprint([]string{"Go"}) {
		t.Fatalf("tags = %v", items[0].Tags)
	}
}

func TestLLMTagsProcessorAppliesCustomCategories(t *testing.T) {
	client := &fakeLLMClient{
		response: `{"tags":["AI platform","News update"],"confidence":{"AI platform":0.9,"News update":0.8}}`,
	}
	processor, err := newLLMTagsProcessor(map[string]any{
		"custom_categories": map[string]any{
			"topic": []any{"AI"},
		},
	}, func(BaseLLMProcessorConfig) LLMClient { return client })
	if err != nil {
		t.Fatalf("newLLMTagsProcessor() error = %v", err)
	}

	items, err := processor.Process(
		context.Background(),
		[]content.Content{{Title: "AI update", Content: "AI platform news"}},
	)
	if err != nil {
		t.Fatalf("Process() error = %v", err)
	}
	want := []string{"topic:AI platform", "News update"}
	if fmt.Sprint(items[0].Tags) != fmt.Sprint(want) {
		t.Fatalf("tags = %v, want %v", items[0].Tags, want)
	}
}

func TestLLMTagsProcessorPreservesCustomCategoryOrder(t *testing.T) {
	client := &fakeLLMClient{
		response: `{"tags":["AI platform","News update"],"confidence":{}}`,
	}
	active, err := newLLMTagsProcessor(map[string]any{
		"custom_categories": map[string]any{
			"topic": []any{"AI"},
			"news":  []any{"News"},
		},
	}, func(BaseLLMProcessorConfig) LLMClient { return client })
	if err != nil {
		t.Fatal(err)
	}
	SetCustomCategoryOrder(active, []string{"news", "topic"})
	items, err := active.Process(
		context.Background(),
		[]content.Content{{
			Title:   "AI update",
			Content: "AI platform news update",
		}},
	)
	if err != nil {
		t.Fatal(err)
	}
	want := []string{"news:News update", "topic:AI platform"}
	if fmt.Sprint(items[0].Tags) != fmt.Sprint(want) {
		t.Fatalf("tags = %v, want %v", items[0].Tags, want)
	}
}

func TestLLMTagsProcessorFallbackUsesGeneralTag(t *testing.T) {
	client := &fakeLLMClient{err: errors.New("unavailable")}
	processor, err := newLLMTagsProcessor(map[string]any{
		"retry_times": 1,
	}, func(BaseLLMProcessorConfig) LLMClient { return client })
	if err != nil {
		t.Fatalf("newLLMTagsProcessor() error = %v", err)
	}

	items, err := processor.Process(
		context.Background(),
		[]content.Content{{Title: "Untitled", Content: "unclassified material"}},
	)
	if err != nil {
		t.Fatalf("Process() error = %v", err)
	}
	if fmt.Sprint(items[0].Tags) != fmt.Sprint([]string{"general"}) {
		t.Fatalf("tags = %v", items[0].Tags)
	}
}

func TestLLMKeywordsProcessorFailFastReturnsError(t *testing.T) {
	client := &fakeLLMClient{err: errors.New("bad gateway")}
	processor, err := newLLMKeywordsProcessor(map[string]any{
		"enable_fallback": false,
		"fail_fast":       true,
	}, func(BaseLLMProcessorConfig) LLMClient { return client })
	if err != nil {
		t.Fatalf("newLLMKeywordsProcessor() error = %v", err)
	}

	if _, err := processor.Process(
		context.Background(),
		[]content.Content{{
			Content: "long enough text to require a keyword model request",
		}},
	); err == nil {
		t.Fatalf("expected fail_fast error")
	}
}

func TestLLMSummaryProcessorSkipsUnsuitableContentLengths(t *testing.T) {
	for _, test := range []struct {
		name    string
		content string
	}{
		{name: "short", content: "too short"},
		{name: "oversized", content: strings.Repeat("a ", 5001)},
	} {
		t.Run(test.name, func(t *testing.T) {
			client := &fakeLLMClient{response: "should not be called"}
			active, err := newLLMSummaryProcessor(
				map[string]any{},
				func(BaseLLMProcessorConfig) LLMClient { return client },
			)
			if err != nil {
				t.Fatal(err)
			}
			items, err := active.Process(
				context.Background(),
				[]content.Content{{Title: "Title", Content: test.content}},
			)
			if err != nil {
				t.Fatal(err)
			}
			if client.calls.Load() != 0 || items[0].Summary == "" {
				t.Fatalf(
					"calls = %d, summary = %q",
					client.calls.Load(),
					items[0].Summary,
				)
			}
		})
	}
}

func TestLLMKeywordAndTagProcessorsSkipShortContent(t *testing.T) {
	client := &fakeLLMClient{response: `{"keywords":["unexpected"]}`}
	keywords, err := newLLMKeywordsProcessor(
		map[string]any{},
		func(BaseLLMProcessorConfig) LLMClient { return client },
	)
	if err != nil {
		t.Fatal(err)
	}
	items, err := keywords.Process(
		context.Background(),
		[]content.Content{{Content: "short"}},
	)
	if err != nil {
		t.Fatal(err)
	}
	if client.calls.Load() != 0 || len(items[0].Keywords) != 0 {
		t.Fatalf("keyword calls = %d, keywords = %v", client.calls.Load(), items[0].Keywords)
	}

	client.response = `{"tags":["unexpected"]}`
	tags, err := newLLMTagsProcessor(
		map[string]any{},
		func(BaseLLMProcessorConfig) LLMClient { return client },
	)
	if err != nil {
		t.Fatal(err)
	}
	items, err = tags.Process(
		context.Background(),
		[]content.Content{{Content: "short"}},
	)
	if err != nil {
		t.Fatal(err)
	}
	if client.calls.Load() != 0 || len(items[0].Tags) != 0 {
		t.Fatalf("tag calls = %d, tags = %v", client.calls.Load(), items[0].Tags)
	}
}

func TestInvokeLLMReturnsFinalAttemptErrorWithoutWaitingAgain(t *testing.T) {
	clientErr := errors.New("bad gateway")
	client := &fakeLLMClient{err: clientErr}
	ctx, cancel := context.WithTimeout(context.Background(), 45*time.Millisecond)
	defer cancel()
	_, err := invokeLLM(
		ctx,
		BaseLLMProcessorConfig{
			ModelName:  "model",
			Timeout:    time.Second,
			RetryTimes: 2,
		},
		client,
		ChatRequest{},
	)
	if !errors.Is(err, clientErr) {
		t.Fatalf("invokeLLM() error = %v, want %v", err, clientErr)
	}
	if client.calls.Load() != 2 {
		t.Fatalf("client calls = %d, want 2", client.calls.Load())
	}
}

func TestLLMOperationObserverRecordsFallbackAsFailure(t *testing.T) {
	client := &fakeLLMClient{response: "Generated summary"}
	observations := make([]bool, 0, 2)
	registry := NewRegistry(
		WithLLMClientFactory(func(BaseLLMProcessorConfig) LLMClient {
			return client
		}),
		WithLLMOperationObserver(func(_ time.Duration, success bool) {
			observations = append(observations, success)
		}),
	)
	active, err := registry.Create(ProcessorLLMSummary, map[string]any{
		"retry_times": 1,
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := active.Process(
		context.Background(),
		[]content.Content{{
			Title:   "Title",
			Content: strings.Repeat("article content ", 25),
		}},
	); err != nil {
		t.Fatal(err)
	}

	client.err = errors.New("gateway unavailable")
	active, err = registry.Create(ProcessorLLMSummary, map[string]any{
		"retry_times": 1,
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := active.Process(
		context.Background(),
		[]content.Content{{
			Title:   "Other",
			Content: strings.Repeat("fallback content ", 25),
		}},
	); err != nil {
		t.Fatal(err)
	}
	if fmt.Sprint(observations) != fmt.Sprint([]bool{true, false}) {
		t.Fatalf("observations = %v", observations)
	}
}
