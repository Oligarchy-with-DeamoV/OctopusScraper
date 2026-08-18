package processor

import (
	"context"
	"fmt"
	"log/slog"
	"sort"
	"strings"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
)

type LLMTagsProcessor struct {
	baseProcessor
	config TagsProcessorConfig
	client LLMClient
	cache  tagsCache
}

// SetCustomCategoryOrder preserves the YAML category order for legacy output.
func SetCustomCategoryOrder(active Processor, order []string) {
	tagsProcessor, ok := active.(*LLMTagsProcessor)
	if !ok {
		return
	}
	tagsProcessor.config.CustomCategoryOrder = append([]string(nil), order...)
}

func newLLMTagsProcessor(
	raw map[string]any,
	factory llmClientFactory,
	loggers ...*slog.Logger,
) (*LLMTagsProcessor, error) {
	cfg, err := parseTagsConfig(raw)
	if err != nil {
		return nil, err
	}
	if factory == nil {
		return nil, fmt.Errorf("nil llm client factory")
	}
	return &LLMTagsProcessor{
		baseProcessor: baseProcessor{
			name:     ProcessorLLMTags,
			priority: cfg.Priority,
			logger:   processorLogger(loggers),
		},
		config: cfg,
		client: factory(cfg.BaseLLMProcessorConfig),
		cache:  newTagsCache(),
	}, nil
}

func (p *LLMTagsProcessor) Process(ctx context.Context, items []content.Content) ([]content.Content, error) {
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

func (p *LLMTagsProcessor) processOne(ctx context.Context, item content.Content) (content.Content, error) {
	cacheKey := buildCacheKey(
		p.Name(),
		item,
		p.config.MaxTags,
		p.config.AllowNewTags,
		p.config.AvailableTags,
		p.config.CustomCategories,
		p.config.ConfidenceThreshold,
	)
	if cached, ok := p.cache.get(cacheKey); ok {
		item.Tags = append([]string(nil), cached.Tags...)
		return item, nil
	}

	article := trimPromptInput(item.Content, 12000)
	if len([]rune(strings.TrimSpace(article))) < 10 {
		return item, nil
	}

	response, err := invokeLLM(ctx, p.config.BaseLLMProcessorConfig, p.client, ChatRequest{
		ResponseFormat: "json_object",
		Messages: []ChatMessage{
			{Role: "system", Content: p.tagSystemPrompt()},
			{Role: "user", Content: fmt.Sprintf("Title: %s\n\nContent:\n%s", trimPromptInput(item.Title, 500), article)},
		},
	})
	if err != nil {
		return p.handleTagFailure(item, cacheKey, err)
	}

	var parsed tagResult
	if err := parseJSONObject(response, &parsed); err != nil {
		return p.handleTagFailure(item, cacheKey, err)
	}
	filtered := p.normalizeTags(parsed)
	if len(filtered.Tags) == 0 {
		return p.handleTagFailure(item, cacheKey, fmt.Errorf("no valid tags"))
	}
	filtered.Tags = p.categorizeTags(filtered.Tags)
	item.Tags = filtered.Tags
	p.cache.set(cacheKey, filtered)
	return item, nil
}

func (p *LLMTagsProcessor) handleTagFailure(item content.Content, cacheKey string, originalErr error) (content.Content, error) {
	if !p.config.EnableFallback {
		return item, originalErr
	}
	fallback := p.fallbackTags(item)
	if len(fallback) == 0 {
		return item, originalErr
	}
	p.logFallback(item, originalErr)
	item.Tags = fallback
	p.cache.set(cacheKey, tagResult{Tags: fallback})
	return item, nil
}

func (p *LLMTagsProcessor) tagSystemPrompt() string {
	if len(p.config.AvailableTags) > 0 {
		return fmt.Sprintf("Return strict JSON with fields tags and confidence. Choose up to %d tags. Prefer this allowed list: %s.", p.config.MaxTags, strings.Join(p.config.AvailableTags, ", "))
	}
	return fmt.Sprintf("Return strict JSON with fields tags and confidence. Choose up to %d concise tags.", p.config.MaxTags)
}

func (p *LLMTagsProcessor) normalizeTags(parsed tagResult) tagResult {
	available := make(map[string]string, len(p.config.AvailableTags))
	for _, tag := range p.config.AvailableTags {
		available[strings.ToLower(strings.TrimSpace(tag))] = strings.TrimSpace(tag)
	}

	cleaned := make([]string, 0, len(parsed.Tags))
	confidence := map[string]float64{}
	hasConfidenceScores := len(parsed.Confidence) > 0
	for _, rawTag := range parsed.Tags {
		trimmed := normalizeSpace(rawTag)
		if trimmed == "" || len([]rune(trimmed)) > defaultMaxTagLength {
			continue
		}
		lowered := strings.ToLower(trimmed)
		canonical := trimmed
		if canonicalAllowed, ok := available[lowered]; ok {
			canonical = canonicalAllowed
		} else if len(available) > 0 && !p.config.AllowNewTags {
			continue
		}
		score := parsed.Confidence[trimmed]
		if score == 0 {
			score = parsed.Confidence[canonical]
		}
		if hasConfidenceScores && score < p.config.ConfidenceThreshold {
			continue
		}
		cleaned = append(cleaned, canonical)
		if hasConfidenceScores {
			confidence[canonical] = score
		}
	}
	cleaned = dedupeCaseInsensitive(cleaned, 0)
	if len(confidence) > 0 {
		sort.SliceStable(cleaned, func(i, j int) bool {
			return confidence[cleaned[i]] > confidence[cleaned[j]]
		})
	}
	if len(cleaned) > p.config.MaxTags {
		cleaned = cleaned[:p.config.MaxTags]
	}
	filteredConfidence := map[string]float64{}
	for _, tag := range cleaned {
		if score, ok := confidence[tag]; ok {
			filteredConfidence[tag] = score
		}
	}
	return tagResult{Tags: cleaned, Confidence: filteredConfidence}
}

func (p *LLMTagsProcessor) categorizeTags(tags []string) []string {
	if len(p.config.CustomCategories) == 0 {
		return tags
	}
	categoryNames := orderedCategoryNames(
		p.config.CustomCategories,
		p.config.CustomCategoryOrder,
	)

	categorized := make(map[string]struct{}, len(tags))
	out := make([]string, 0, len(tags))
	for _, category := range categoryNames {
		keywords := p.config.CustomCategories[category]
		for _, tag := range tags {
			loweredTag := strings.ToLower(tag)
			matched := false
			for _, keyword := range keywords {
				if strings.Contains(
					loweredTag,
					strings.ToLower(strings.TrimSpace(keyword)),
				) {
					matched = true
					break
				}
			}
			if !matched {
				continue
			}
			categorized[tag] = struct{}{}
			if category == "general" {
				out = append(out, tag)
			} else {
				out = append(out, category+":"+tag)
			}
		}
	}
	for _, tag := range tags {
		if _, ok := categorized[tag]; !ok {
			out = append(out, tag)
		}
	}
	return out
}

func orderedCategoryNames(
	categories map[string][]string,
	preferred []string,
) []string {
	names := make([]string, 0, len(categories))
	seen := make(map[string]struct{}, len(categories))
	for _, name := range preferred {
		if _, exists := categories[name]; !exists {
			continue
		}
		if _, exists := seen[name]; exists {
			continue
		}
		seen[name] = struct{}{}
		names = append(names, name)
	}
	remaining := make([]string, 0, len(categories)-len(names))
	for name := range categories {
		if _, exists := seen[name]; !exists {
			remaining = append(remaining, name)
		}
	}
	sort.Strings(remaining)
	return append(names, remaining...)
}

func (p *LLMTagsProcessor) fallbackTags(item content.Content) []string {
	text := strings.ToLower(item.Title + " " + item.Content)
	if len(p.config.AvailableTags) > 0 {
		matched := make([]string, 0, p.config.MaxTags)
		for _, tag := range p.config.AvailableTags {
			lowered := strings.ToLower(tag)
			if strings.Contains(text, lowered) {
				matched = append(matched, tag)
			}
		}
		return dedupeCaseInsensitive(matched, p.config.MaxTags)
	}
	heuristics := []struct {
		tag      string
		keywords []string
	}{
		{tag: "technology", keywords: []string{"tech", "software", "computer", "digital", "ai", "ml"}},
		{tag: "business", keywords: []string{"business", "company", "market", "finance", "economy"}},
		{tag: "science", keywords: []string{"research", "study", "analysis", "experiment", "data"}},
		{tag: "health", keywords: []string{"health", "medical", "disease", "treatment"}},
		{tag: "education", keywords: []string{"education", "learning", "school", "university", "course"}},
	}
	matched := make([]string, 0, p.config.MaxTags)
	for _, heuristic := range heuristics {
		for _, keyword := range heuristic.keywords {
			if strings.Contains(text, keyword) {
				matched = append(matched, heuristic.tag)
				break
			}
		}
	}
	matched = dedupeCaseInsensitive(matched, p.config.MaxTags)
	if len(matched) == 0 {
		return []string{"general"}
	}
	return matched
}
