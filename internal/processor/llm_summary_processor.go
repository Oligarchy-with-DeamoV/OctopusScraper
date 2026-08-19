package processor

import (
	"context"
	"fmt"
	"log/slog"
	"strings"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
)

type LLMSummaryProcessor struct {
	baseProcessor
	config SummaryProcessorConfig
	client LLMClient
	cache  summaryCache
}

func newLLMSummaryProcessor(
	raw map[string]any,
	factory llmClientFactory,
	loggers ...*slog.Logger,
) (*LLMSummaryProcessor, error) {
	cfg, err := parseSummaryConfig(raw)
	if err != nil {
		return nil, err
	}
	if factory == nil {
		return nil, fmt.Errorf("nil llm client factory")
	}
	return &LLMSummaryProcessor{
		baseProcessor: baseProcessor{
			name:     ProcessorLLMSummary,
			priority: cfg.Priority,
			logger:   processorLogger(loggers),
		},
		config: cfg,
		client: factory(cfg.BaseLLMProcessorConfig),
		cache:  newSummaryCache(),
	}, nil
}

func (p *LLMSummaryProcessor) Process(ctx context.Context, items []content.Content) ([]content.Content, error) {
	out := make([]content.Content, 0, len(items))
	for _, item := range items {
		processed, err := p.processOne(ctx, item)
		if err != nil {
			p.logFailure(item, err)
			if p.config.FailFast {
				return nil, err
			}
			out = append(out, item)
			continue
		}
		out = append(out, processed)
	}
	return out, nil
}

func (p *LLMSummaryProcessor) processOne(ctx context.Context, item content.Content) (content.Content, error) {
	cacheKey := buildCacheKey(p.Name(), item, p.config.SummaryStyle, p.config.MaxSummaryLength, p.config.ModelName)
	if cached, ok := p.cache.get(cacheKey); ok {
		item.Summary = cached
		return item, nil
	}

	title := trimPromptInput(item.Title, 500)
	article := trimPromptInput(item.Content, 12000)
	wordCount := mixedWordCount(article)
	if wordCount < 50 || wordCount > 5000 {
		summary := p.fallbackSummary(title, article)
		if summary == "" {
			return item, fmt.Errorf("content is unsuitable for summarization")
		}
		item.Summary = summary
		p.cache.set(cacheKey, summary)
		return item, nil
	}

	response, err := invokeLLM(ctx, p.config.BaseLLMProcessorConfig, p.client, ChatRequest{
		Messages: []ChatMessage{
			{Role: "system", Content: p.summarySystemPrompt()},
			{Role: "user", Content: fmt.Sprintf("Title: %s\n\nContent:\n%s", title, article)},
		},
	})
	if err != nil {
		if p.config.EnableFallback {
			p.logFallback(item, err)
			summary := p.fallbackSummary(title, article)
			item.Summary = summary
			p.cache.set(cacheKey, summary)
			return item, nil
		}
		return item, err
	}

	summary := normalizeSpace(response)
	if summary == "" {
		if p.config.EnableFallback {
			p.logFallback(item, fmt.Errorf("empty summary response"))
			summary = p.fallbackSummary(title, article)
		} else {
			return item, fmt.Errorf("empty summary response")
		}
	}
	summary = truncateWords(summary, p.config.MaxSummaryLength)
	if summary == "" {
		return item, fmt.Errorf("summary became empty after truncation")
	}
	item.Summary = summary
	p.cache.set(cacheKey, summary)
	return item, nil
}

func (p *LLMSummaryProcessor) summarySystemPrompt() string {
	style := map[string]string{
		"concise":       "Write a concise summary in plain prose.",
		"detailed":      "Write a detailed but compact summary covering the main points.",
		"bullet_points": "Write a summary as short bullet points.",
		"executive":     "Write an executive summary focused on decisions, impact, and takeaways.",
	}[p.config.SummaryStyle]
	return strings.TrimSpace(fmt.Sprintf("You summarize web articles. %s Keep the output under %d words and do not add facts.", style, p.config.MaxSummaryLength))
}

func (p *LLMSummaryProcessor) fallbackSummary(title string, article string) string {
	sentences := splitSentences(article, 3)
	if len(sentences) == 0 {
		sentences = splitSentences(title, 1)
	}
	if len(sentences) == 0 {
		return ""
	}
	switch p.config.SummaryStyle {
	case "bullet_points":
		bullets := make([]string, 0, len(sentences))
		for _, sentence := range sentences {
			bullets = append(bullets, "- "+truncateWords(sentence, max(8, p.config.MaxSummaryLength/3)))
		}
		return strings.Join(bullets, "\n")
	case "detailed":
		return truncateWords(strings.Join(sentences, ". "), p.config.MaxSummaryLength)
	case "executive":
		return truncateWords(strings.Join(sentences[:min(2, len(sentences))], ". "), p.config.MaxSummaryLength)
	default:
		return truncateWords(sentences[0], p.config.MaxSummaryLength)
	}
}
