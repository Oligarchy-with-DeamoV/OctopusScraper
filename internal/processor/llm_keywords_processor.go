package processor

import (
	"context"
	"fmt"
	"log/slog"
	"regexp"
	"sort"
	"strings"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
)

type LLMKeywordsProcessor struct {
	baseProcessor
	config    KeywordsProcessorConfig
	client    LLMClient
	cache     keywordsCache
	stopWords map[string]struct{}
}

func newLLMKeywordsProcessor(
	raw map[string]any,
	factory llmClientFactory,
	loggers ...*slog.Logger,
) (*LLMKeywordsProcessor, error) {
	cfg, err := parseKeywordsConfig(raw)
	if err != nil {
		return nil, err
	}
	if factory == nil {
		return nil, fmt.Errorf("nil llm client factory")
	}
	return &LLMKeywordsProcessor{
		baseProcessor: baseProcessor{
			name:     ProcessorLLMKeywords,
			priority: cfg.Priority,
			logger:   processorLogger(loggers),
		},
		config:    cfg,
		client:    factory(cfg.BaseLLMProcessorConfig),
		cache:     newKeywordsCache(),
		stopWords: buildStopWords(cfg.CustomStopWords),
	}, nil
}

func (p *LLMKeywordsProcessor) Process(ctx context.Context, items []content.Content) ([]content.Content, error) {
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

func (p *LLMKeywordsProcessor) processOne(ctx context.Context, item content.Content) (content.Content, error) {
	cacheKey := buildCacheKey(p.Name(), item, p.config.MaxKeywords, p.config.MinKeywordLength, p.config.MaxKeywordLength, p.config.MinImportanceScore)
	if cached, ok := p.cache.get(cacheKey); ok {
		item.Keywords = append([]string(nil), cached.Keywords...)
		return item, nil
	}

	article := trimPromptInput(item.Content, 12000)
	if len([]rune(strings.TrimSpace(article))) < 20 {
		return item, nil
	}

	response, err := invokeLLM(ctx, p.config.BaseLLMProcessorConfig, p.client, ChatRequest{
		ResponseFormat: "json_object",
		Messages: []ChatMessage{
			{Role: "system", Content: p.keywordSystemPrompt()},
			{Role: "user", Content: fmt.Sprintf("Title: %s\n\nContent:\n%s", trimPromptInput(item.Title, 500), article)},
		},
	})
	if err != nil {
		return p.handleKeywordFailure(item, cacheKey, err)
	}

	var parsed keywordResult
	if err := parseJSONObject(response, &parsed); err != nil {
		return p.handleKeywordFailure(item, cacheKey, err)
	}
	filtered := p.normalizeKeywords(parsed)
	if len(filtered.Keywords) == 0 {
		return p.handleKeywordFailure(item, cacheKey, fmt.Errorf("no valid keywords"))
	}
	item.Keywords = filtered.Keywords
	p.cache.set(cacheKey, filtered)
	return item, nil
}

func (p *LLMKeywordsProcessor) handleKeywordFailure(item content.Content, cacheKey string, originalErr error) (content.Content, error) {
	if !p.config.EnableFallback {
		return item, originalErr
	}
	fallback := p.fallbackKeywords(item)
	if len(fallback) == 0 {
		return item, originalErr
	}
	p.logFallback(item, originalErr)
	item.Keywords = fallback
	p.cache.set(cacheKey, keywordResult{Keywords: fallback})
	return item, nil
}

func (p *LLMKeywordsProcessor) keywordSystemPrompt() string {
	return fmt.Sprintf("Extract up to %d keywords from the article. Return strict JSON with fields keywords, optional phrases, and importance_scores. Keep keywords relevant, deduplicated, and concise.", p.config.MaxKeywords)
}

func (p *LLMKeywordsProcessor) normalizeKeywords(parsed keywordResult) keywordResult {
	candidates := append([]string(nil), parsed.Keywords...)
	if p.config.IncludePhrases {
		candidates = append(candidates, parsed.Phrases...)
	}
	cleaned := make([]string, 0, len(candidates))
	scores := map[string]float64{}
	hasImportanceScores := len(parsed.Importance) > 0
	for _, keyword := range candidates {
		trimmed := normalizeSpace(keyword)
		if trimmed == "" {
			continue
		}
		length := len([]rune(trimmed))
		if length < p.config.MinKeywordLength || length > p.config.MaxKeywordLength {
			continue
		}
		if p.config.ExcludeCommonWords {
			if _, blocked := p.stopWords[strings.ToLower(trimmed)]; blocked {
				continue
			}
		}
		if matchesAnyPattern(trimmed, p.config.ExcludePatterns) {
			continue
		}
		score := parsed.Importance[trimmed]
		if hasImportanceScores && score < p.config.MinImportanceScore {
			continue
		}
		cleaned = append(cleaned, trimmed)
		if hasImportanceScores {
			scores[trimmed] = score
		}
	}

	cleaned = dedupeCaseInsensitive(cleaned, 0)
	if len(scores) > 0 {
		sort.SliceStable(cleaned, func(i, j int) bool {
			return scores[cleaned[i]] > scores[cleaned[j]]
		})
	}
	limit := min(p.config.KeywordsCount, p.config.MaxKeywords)
	if len(cleaned) > limit {
		cleaned = cleaned[:limit]
	}
	filteredScores := map[string]float64{}
	for _, keyword := range cleaned {
		if score, ok := scores[keyword]; ok {
			filteredScores[keyword] = score
		}
	}
	return keywordResult{Keywords: cleaned, Importance: filteredScores}
}

func (p *LLMKeywordsProcessor) fallbackKeywords(item content.Content) []string {
	words := regexp.MustCompile(`[A-Za-z0-9\p{Han}][A-Za-z0-9\p{Han}\-]+`).FindAllString(item.Title+" "+item.Content, -1)
	frequency := map[string]int{}
	for _, word := range words {
		trimmed := normalizeSpace(word)
		lowered := strings.ToLower(trimmed)
		length := len([]rune(trimmed))
		if length < p.config.MinKeywordLength || length > p.config.MaxKeywordLength {
			continue
		}
		if p.config.ExcludeCommonWords {
			if _, blocked := p.stopWords[lowered]; blocked {
				continue
			}
		}
		if matchesAnyPattern(trimmed, p.config.ExcludePatterns) {
			continue
		}
		frequency[trimmed]++
	}
	type pair struct {
		keyword string
		count   int
	}
	pairs := make([]pair, 0, len(frequency))
	for keyword, count := range frequency {
		pairs = append(pairs, pair{keyword: keyword, count: count})
	}
	sort.SliceStable(pairs, func(i, j int) bool {
		if pairs[i].count == pairs[j].count {
			return pairs[i].keyword < pairs[j].keyword
		}
		return pairs[i].count > pairs[j].count
	})
	limit := min(p.config.KeywordsCount, p.config.MaxKeywords)
	out := make([]string, 0, limit)
	for _, candidate := range pairs {
		out = append(out, candidate.keyword)
		if len(out) == limit {
			break
		}
	}
	return dedupeCaseInsensitive(out, limit)
}

func buildStopWords(custom []string) map[string]struct{} {
	words := []string{"the", "a", "an", "and", "or", "but", "with", "for", "from", "this", "that", "these", "those", "into", "about", "article", "content", "there", "their", "have", "has", "will", "would", "could", "should", "的", "了", "和", "是", "在", "与", "及", "对", "将"}
	out := make(map[string]struct{}, len(words)+len(custom))
	for _, word := range words {
		out[strings.ToLower(word)] = struct{}{}
	}
	for _, word := range custom {
		trimmed := strings.ToLower(strings.TrimSpace(word))
		if trimmed != "" {
			out[trimmed] = struct{}{}
		}
	}
	return out
}

func matchesAnyPattern(value string, patterns []string) bool {
	for _, pattern := range patterns {
		matched, err := regexp.MatchString(pattern, value)
		if err == nil && matched {
			return true
		}
	}
	return false
}
