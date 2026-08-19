package processor

import (
	"context"
	"errors"
	"net/http"
	"reflect"
	"testing"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
)

type stubProcessor struct {
	baseProcessor
	mark string
}

type pipelineFactory struct {
	processors map[string]Processor
	err        error
}

func (f pipelineFactory) Create(name string, _ map[string]any) (Processor, error) {
	if f.err != nil {
		return nil, f.err
	}
	return f.processors[name], nil
}

func (f pipelineFactory) Supported(name string) bool {
	_, found := f.processors[name]
	return found
}

type failingProcessor struct {
	baseProcessor
}

func (p failingProcessor) Process(
	context.Context,
	[]content.Content,
) ([]content.Content, error) {
	return nil, errors.New("process failed")
}

func TestBuildPipelineAndProcessorCopies(t *testing.T) {
	factory := pipelineFactory{processors: map[string]Processor{
		"one": stubProcessor{
			baseProcessor: baseProcessor{name: "one", priority: 1},
			mark:          "1",
		},
		"two": stubProcessor{
			baseProcessor: baseProcessor{name: "two", priority: 2},
			mark:          "2",
		},
	}}
	pipeline, err := BuildPipeline(factory, map[string]map[string]any{
		"two": nil,
		"one": nil,
	})
	if err != nil {
		t.Fatal(err)
	}
	processors := pipeline.Processors()
	if len(processors) != 2 {
		t.Fatalf("unexpected processors: %#v", processors)
	}
	processors[0] = nil
	if pipeline.Processors()[0] == nil {
		t.Fatal("Processors returned internal slice")
	}
	if _, err := BuildPipeline(
		pipelineFactory{err: errors.New("create failed")},
		map[string]map[string]any{"bad": nil},
	); err == nil {
		t.Fatal("expected pipeline construction error")
	}
	failing := NewPipeline(failingProcessor{
		baseProcessor: baseProcessor{name: "bad", priority: 1},
	})
	if _, err := failing.Process(context.Background(), nil); err == nil {
		t.Fatal("expected processor error")
	}
}

func TestRegistryOptionsAndConstructors(t *testing.T) {
	httpClient := &http.Client{}
	llmClient := &fakeLLMClient{response: `{"keywords":[]}`}
	registry := NewRegistry(
		WithBrowserRenderer(nil),
		WithArticleExtractor(nil),
		WithMarkdownConverter(nil),
		WithHTTPClient(nil),
		WithHTTPClient(httpClient),
		WithLLMClientFactory(nil),
		WithLLMClientFactory(func(BaseLLMProcessorConfig) LLMClient {
			return llmClient
		}),
	)
	if registry.httpClient != httpClient || registry.llmFactory == nil {
		t.Fatal("registry options were not applied")
	}
	for _, name := range SupportedProcessors() {
		active, err := registry.Create(name, nil)
		if err != nil {
			t.Fatalf("Create(%s): %v", name, err)
		}
		if active.Name() != name {
			t.Fatalf("Create(%s) returned %s", name, active.Name())
		}
	}
	if _, err := BuildPipeline(nil, nil); err != nil {
		t.Fatal(err)
	}
}

func (p stubProcessor) Process(_ context.Context, items []content.Content) ([]content.Content, error) {
	out := make([]content.Content, 0, len(items))
	for _, item := range items {
		item.Content += p.mark
		out = append(out, item)
	}
	return out, nil
}

func TestRegistrySupportsOnlyCurrentProcessors(t *testing.T) {
	registry := NewRegistry()
	supported := SupportedProcessors()
	expected := []string{ProcessorHTMLContent, ProcessorLLMSummary, ProcessorLLMKeywords, ProcessorLLMTags}
	if !reflect.DeepEqual(supported, expected) {
		t.Fatalf("supported processors = %v, want %v", supported, expected)
	}
	if registry.Supported("llm") {
		t.Fatalf("legacy llm processor should not be supported")
	}
	if _, err := registry.Create("llm", map[string]any{}); err == nil {
		t.Fatalf("expected unsupported processor error")
	}
}

func TestPipelineSortsByPriorityAscending(t *testing.T) {
	pipeline := NewPipeline(
		stubProcessor{baseProcessor: baseProcessor{name: "later", priority: 20}, mark: "B"},
		stubProcessor{baseProcessor: baseProcessor{name: "first", priority: 10}, mark: "A"},
		stubProcessor{baseProcessor: baseProcessor{name: "middle", priority: 15}, mark: "C"},
	)
	got, err := pipeline.Process(context.Background(), []content.Content{{Content: "start"}})
	if err != nil {
		t.Fatalf("pipeline.Process() error = %v", err)
	}
	if got[0].Content != "startACB" {
		t.Fatalf("pipeline order = %q, want %q", got[0].Content, "startACB")
	}
}

func TestPipelinePreservesInputOrderForEqualPriorities(t *testing.T) {
	pipeline := NewPipeline(
		stubProcessor{
			baseProcessor: baseProcessor{name: "zeta", priority: 10},
			mark:          "Z",
		},
		stubProcessor{
			baseProcessor: baseProcessor{name: "alpha", priority: 10},
			mark:          "A",
		},
	)
	got, err := pipeline.Process(
		context.Background(),
		[]content.Content{{Content: "start"}},
	)
	if err != nil {
		t.Fatal(err)
	}
	if got[0].Content != "startZA" {
		t.Fatalf("pipeline order = %q, want %q", got[0].Content, "startZA")
	}
}
