package processor

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"time"
)

type BrowserRenderer interface {
	RenderHTML(
		context.Context,
		string,
		BrowserRenderOptions,
	) (string, error)
}

type BrowserRenderOptions struct {
	URL       string
	UserAgent string
	TimeoutMs int64
}

type ArticleExtractor interface {
	ExtractHTML(baseURL string, rawHTML string) (string, error)
}

type MarkdownConverter interface {
	Convert(html string) (string, error)
}

type LLMClient interface {
	CreateChatCompletion(ctx context.Context, req ChatRequest) (string, error)
}

type llmClientFactory func(BaseLLMProcessorConfig) LLMClient
type LLMOperationObserver func(time.Duration, bool)

// Registry owns processor construction and dependency injection for tests.
type Registry struct {
	browserRenderer  BrowserRenderer
	articleExtractor ArticleExtractor
	markdown         MarkdownConverter
	httpClient       *http.Client
	llmFactory       llmClientFactory
	llmObserver      LLMOperationObserver
	logger           *slog.Logger
}

var _ Factory = (*Registry)(nil)

type Option func(*Registry)

func WithBrowserRenderer(renderer BrowserRenderer) Option {
	return func(r *Registry) {
		r.browserRenderer = renderer
	}
}

func WithArticleExtractor(extractor ArticleExtractor) Option {
	return func(r *Registry) {
		r.articleExtractor = extractor
	}
}

func WithMarkdownConverter(converter MarkdownConverter) Option {
	return func(r *Registry) {
		r.markdown = converter
	}
}

func WithHTTPClient(client *http.Client) Option {
	return func(r *Registry) {
		if client != nil {
			r.httpClient = client
		}
	}
}

func WithLLMClientFactory(factory func(BaseLLMProcessorConfig) LLMClient) Option {
	return func(r *Registry) {
		if factory != nil {
			r.llmFactory = factory
		}
	}
}

func WithLLMOperationObserver(observer LLMOperationObserver) Option {
	return func(r *Registry) {
		r.llmObserver = observer
	}
}

func WithLogger(logger *slog.Logger) Option {
	return func(r *Registry) {
		r.logger = logger
	}
}

func NewRegistry(opts ...Option) *Registry {
	registry := &Registry{
		browserRenderer:  cdpBrowserRenderer{},
		articleExtractor: simpleArticleExtractor{},
		markdown:         simpleMarkdownConverter{},
		httpClient:       &http.Client{},
		logger:           slog.Default(),
	}
	registry.llmFactory = func(cfg BaseLLMProcessorConfig) LLMClient {
		return NewOpenAICompatibleClient(registry.httpClient, cfg)
	}
	for _, opt := range opts {
		opt(registry)
	}
	return registry
}

func (r *Registry) Supported(name string) bool {
	switch name {
	case ProcessorHTMLContent, ProcessorLLMSummary, ProcessorLLMKeywords, ProcessorLLMTags:
		return true
	default:
		return false
	}
}

func (r *Registry) Create(name string, rawConfig map[string]any) (Processor, error) {
	if !r.Supported(name) {
		return nil, fmt.Errorf("%w: %s", ErrUnsupportedProcessor, name)
	}
	if rawConfig == nil {
		rawConfig = map[string]any{}
	}
	switch name {
	case ProcessorHTMLContent:
		return newHTMLContentProcessor(rawConfig, htmlProcessorDeps{
			browserRenderer:  r.browserRenderer,
			articleExtractor: r.articleExtractor,
			markdown:         r.markdown,
			httpClient:       r.httpClient,
			logger:           r.logger,
		})
	case ProcessorLLMSummary:
		active, err := newLLMSummaryProcessor(rawConfig, r.llmFactory, r.logger)
		if err == nil {
			active.config.observer = r.llmObserver
		}
		return active, err
	case ProcessorLLMKeywords:
		active, err := newLLMKeywordsProcessor(rawConfig, r.llmFactory, r.logger)
		if err == nil {
			active.config.observer = r.llmObserver
		}
		return active, err
	case ProcessorLLMTags:
		active, err := newLLMTagsProcessor(rawConfig, r.llmFactory, r.logger)
		if err == nil {
			active.config.observer = r.llmObserver
		}
		return active, err
	default:
		return nil, fmt.Errorf("%w: %s", ErrUnsupportedProcessor, name)
	}
}
