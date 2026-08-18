package processor

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"regexp"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
)

var jsonFenceRE = regexp.MustCompile("(?is)```json\\s*(.*?)\\s*```")
var englishWordRE = regexp.MustCompile(`[A-Za-z]+`)

type summaryCache struct {
	mu    sync.RWMutex
	items map[string]string
}

type keywordsCache struct {
	mu    sync.RWMutex
	items map[string]keywordResult
}

type tagsCache struct {
	mu    sync.RWMutex
	items map[string]tagResult
}

type keywordResult struct {
	Keywords   []string           `json:"keywords"`
	Phrases    []string           `json:"phrases,omitempty"`
	Importance map[string]float64 `json:"importance_scores,omitempty"`
}

type tagResult struct {
	Tags       []string           `json:"tags"`
	Confidence map[string]float64 `json:"confidence,omitempty"`
}

func newSummaryCache() summaryCache {
	return summaryCache{items: map[string]string{}}
}

func newKeywordsCache() keywordsCache {
	return keywordsCache{items: map[string]keywordResult{}}
}

func newTagsCache() tagsCache {
	return tagsCache{items: map[string]tagResult{}}
}

func (c *summaryCache) get(key string) (string, bool) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	value, ok := c.items[key]
	return value, ok
}

func (c *summaryCache) set(key, value string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.items[key] = value
}

func (c *keywordsCache) get(key string) (keywordResult, bool) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	value, ok := c.items[key]
	return cloneKeywordResult(value), ok
}

func (c *keywordsCache) set(key string, value keywordResult) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.items[key] = cloneKeywordResult(value)
}

func (c *tagsCache) get(key string) (tagResult, bool) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	value, ok := c.items[key]
	return cloneTagResult(value), ok
}

func (c *tagsCache) set(key string, value tagResult) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.items[key] = cloneTagResult(value)
}

func cloneKeywordResult(value keywordResult) keywordResult {
	out := keywordResult{
		Keywords: append([]string(nil), value.Keywords...),
		Phrases:  append([]string(nil), value.Phrases...),
	}
	if len(value.Importance) > 0 {
		out.Importance = make(map[string]float64, len(value.Importance))
		for key, score := range value.Importance {
			out.Importance[key] = score
		}
	}
	return out
}

func cloneTagResult(value tagResult) tagResult {
	out := tagResult{Tags: append([]string(nil), value.Tags...)}
	if len(value.Confidence) > 0 {
		out.Confidence = make(map[string]float64, len(value.Confidence))
		for key, score := range value.Confidence {
			out.Confidence[key] = score
		}
	}
	return out
}

func invokeLLM(ctx context.Context, cfg BaseLLMProcessorConfig, client LLMClient, request ChatRequest) (string, error) {
	started := time.Now()
	succeeded := false
	if cfg.observer != nil {
		defer func() {
			cfg.observer(time.Since(started), succeeded)
		}()
	}
	if client == nil {
		return "", fmt.Errorf("nil llm client")
	}
	request.BaseURL = cfg.BaseURL
	request.APIKey = cfg.APIKey
	request.Model = cfg.ModelName
	request.Temperature = cfg.Temperature
	request.MaxTokens = cfg.MaxTokens

	var lastErr error
	for attempt := 0; attempt < cfg.RetryTimes; attempt++ {
		attemptCtx, cancel := context.WithTimeout(ctx, cfg.Timeout)
		response, err := client.CreateChatCompletion(attemptCtx, request)
		cancel()
		if err == nil {
			succeeded = true
			return strings.TrimSpace(response), nil
		}
		lastErr = err
		if attempt+1 >= cfg.RetryTimes {
			break
		}
		select {
		case <-ctx.Done():
			return "", ctx.Err()
		case <-time.After(time.Duration(attempt+1) * 25 * time.Millisecond):
		}
	}
	if lastErr == nil {
		lastErr = fmt.Errorf("llm request failed")
	}
	return "", lastErr
}

func buildCacheKey(prefix string, item content.Content, configParts ...any) string {
	payload := map[string]any{
		"prefix":     prefix,
		"content_id": item.ContentID,
		"title":      item.Title,
		"link":       item.Link,
		"summary":    item.Summary,
		"content":    item.Content,
		"keywords":   item.Keywords,
		"tags":       item.Tags,
		"config":     configParts,
	}
	bytes, _ := json.Marshal(payload)
	sum := sha256.Sum256(bytes)
	return hex.EncodeToString(sum[:])
}

func trimPromptInput(text string, maxRunes int) string {
	runes := []rune(strings.TrimSpace(text))
	if len(runes) <= maxRunes {
		return string(runes)
	}
	return string(runes[:maxRunes])
}

func normalizeSpace(text string) string {
	return strings.Join(strings.Fields(strings.TrimSpace(text)), " ")
}

func mixedWordCount(text string) int {
	count := len(englishWordRE.FindAllString(text, -1))
	for _, character := range text {
		if character >= '\u4e00' && character <= '\u9fff' {
			count++
		}
	}
	return count
}

func splitSentences(text string, maxCount int) []string {
	fields := regexp.MustCompile(`[.!?。！？]+`).Split(text, -1)
	out := make([]string, 0, maxCount)
	for _, field := range fields {
		sentence := strings.TrimSpace(field)
		if sentence == "" {
			continue
		}
		out = append(out, sentence)
		if len(out) == maxCount {
			break
		}
	}
	return out
}

func truncateWords(text string, limit int) string {
	if limit <= 0 {
		return ""
	}
	words := strings.Fields(text)
	if len(words) <= limit {
		return strings.Join(words, " ")
	}
	return strings.Join(words[:limit], " ")
}

func parseJSONObject(raw string, target any) error {
	cleaned := strings.TrimSpace(raw)
	if matches := jsonFenceRE.FindStringSubmatch(cleaned); len(matches) == 2 {
		cleaned = matches[1]
	}
	if err := json.Unmarshal([]byte(cleaned), target); err == nil {
		return nil
	}
	start := strings.Index(cleaned, "{")
	end := strings.LastIndex(cleaned, "}")
	if start >= 0 && end > start {
		return json.Unmarshal([]byte(cleaned[start:end+1]), target)
	}
	return fmt.Errorf("no json object found")
}

func dedupeCaseInsensitive(values []string, limit int) []string {
	seen := map[string]struct{}{}
	out := make([]string, 0, len(values))
	for _, value := range values {
		normalized := strings.ToLower(strings.TrimSpace(value))
		if normalized == "" {
			continue
		}
		if _, ok := seen[normalized]; ok {
			continue
		}
		seen[normalized] = struct{}{}
		out = append(out, strings.TrimSpace(value))
		if limit > 0 && len(out) == limit {
			break
		}
	}
	return out
}

func sortedMapKeys(values map[string]float64) []string {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}
