package processor

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	neturl "net/url"
	"strings"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
)

const maxHTMLResponseBytes = 20 << 20

const (
	htmlFetchAttempts = 3
	htmlRetryDelay    = 2 * time.Second
)

type htmlProcessorDeps struct {
	browserRenderer  BrowserRenderer
	articleExtractor ArticleExtractor
	markdown         MarkdownConverter
	httpClient       *http.Client
	logger           *slog.Logger
	retryDelay       time.Duration
}

type HTMLContentProcessor struct {
	baseProcessor
	config HTMLContentProcessorConfig
	deps   htmlProcessorDeps
}

func newHTMLContentProcessor(raw map[string]any, deps htmlProcessorDeps) (*HTMLContentProcessor, error) {
	cfg, err := parseHTMLConfig(raw)
	if err != nil {
		return nil, err
	}
	if deps.articleExtractor == nil {
		deps.articleExtractor = simpleArticleExtractor{}
	}
	if deps.markdown == nil {
		deps.markdown = simpleMarkdownConverter{}
	}
	if deps.httpClient == nil {
		deps.httpClient = &http.Client{}
	}
	if deps.retryDelay <= 0 {
		deps.retryDelay = htmlRetryDelay
	}
	return &HTMLContentProcessor{
		baseProcessor: baseProcessor{
			name:     ProcessorHTMLContent,
			priority: cfg.Priority,
			logger:   deps.logger,
		},
		config: cfg,
		deps:   deps,
	}, nil
}

func (p *HTMLContentProcessor) Process(ctx context.Context, items []content.Content) ([]content.Content, error) {
	out := make([]content.Content, 0, len(items))
	for _, item := range items {
		processed, err := p.processOne(ctx, item)
		if err != nil {
			p.logFailure(item, err)
			out = append(out, item)
			continue
		}
		out = append(out, processed)
	}
	return out, nil
}

func (p *HTMLContentProcessor) processOne(ctx context.Context, item content.Content) (content.Content, error) {
	if strings.TrimSpace(item.Link) == "" {
		return item, fmt.Errorf("missing link")
	}
	html, err := p.fetchHTML(ctx, item.Link)
	if err != nil {
		return item, err
	}
	extracted, err := p.deps.articleExtractor.ExtractHTML(item.Link, html)
	if err != nil {
		return item, err
	}
	markdown, err := p.deps.markdown.Convert(extracted)
	if err != nil {
		return item, err
	}
	markdown = strings.TrimSpace(markdown)
	if markdown == "" {
		return item, fmt.Errorf("empty markdown")
	}
	item.Content = markdown
	return item, nil
}

func (p *HTMLContentProcessor) fetchHTML(ctx context.Context, rawURL string) (string, error) {
	var lastErr error
	for attempt := 0; attempt < htmlFetchAttempts; attempt++ {
		html, err := p.fetchHTMLOnce(ctx, rawURL)
		if err == nil {
			return html, nil
		}
		lastErr = err
		if attempt == htmlFetchAttempts-1 {
			break
		}
		timer := time.NewTimer(p.deps.retryDelay)
		select {
		case <-ctx.Done():
			timer.Stop()
			return "", ctx.Err()
		case <-timer.C:
		}
	}
	return "", lastErr
}

func (p *HTMLContentProcessor) fetchHTMLOnce(
	ctx context.Context,
	rawURL string,
) (string, error) {
	if p.config.UseBrowser && strings.TrimSpace(p.config.BrowserlessURL) != "" && p.deps.browserRenderer != nil {
		browserHTML, err := p.deps.browserRenderer.RenderHTML(
			ctx,
			p.config.BrowserlessURL,
			BrowserRenderOptions{
				URL:       rawURL,
				UserAgent: p.config.UserAgent,
				TimeoutMs: p.config.BrowserTimeout.Milliseconds(),
			},
		)
		if err == nil && strings.TrimSpace(browserHTML) != "" {
			return browserHTML, nil
		}
		if p.logger != nil {
			if err == nil {
				err = fmt.Errorf("browser renderer returned empty HTML")
			}
			p.logger.Warn(
				"Browser fetch failed; falling back to HTTP",
				"url", rawURL,
				"error", err,
			)
		}
	}
	requestCtx, cancel := context.WithTimeout(ctx, p.config.Timeout)
	defer cancel()

	req, err := http.NewRequestWithContext(requestCtx, http.MethodGet, rawURL, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("User-Agent", p.config.UserAgent)

	resp, err := p.deps.httpClient.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode < http.StatusOK || resp.StatusCode >= http.StatusMultipleChoices {
		return "", fmt.Errorf("unexpected status: %d", resp.StatusCode)
	}
	body, err := readBoundedBody(resp.Body, maxHTMLResponseBytes)
	if err != nil {
		return "", err
	}
	return string(body), nil
}

type simpleArticleExtractor struct{}

func (simpleArticleExtractor) ExtractHTML(baseURL string, rawHTML string) (string, error) {
	cleaned := stripTagPairs(rawHTML, "script", "style", "noscript")
	candidate := extractTagContent(cleaned, "article")
	if candidate == "" {
		candidate = extractTagContent(cleaned, "main")
	}
	if candidate == "" {
		candidate = extractTagContent(cleaned, "body")
	}
	if candidate == "" {
		candidate = cleaned
	}
	candidate = absolutizeLinks(baseURL, candidate)
	candidate = strings.TrimSpace(candidate)
	if candidate == "" {
		return "", fmt.Errorf("unable to extract readable content")
	}
	return candidate, nil
}

func absolutizeLinks(baseURL string, html string) string {
	base, err := neturl.Parse(baseURL)
	if err != nil {
		return html
	}
	replacer := func(match string) string {
		parts := strings.SplitN(match, `"`, 3)
		if len(parts) < 3 {
			return match
		}
		parsed, err := neturl.Parse(parts[1])
		if err != nil || parsed.IsAbs() {
			return match
		}
		parts[1] = base.ResolveReference(parsed).String()
		return strings.Join(parts, `"`)
	}
	html = hrefPattern.ReplaceAllStringFunc(html, replacer)
	html = srcPattern.ReplaceAllStringFunc(html, replacer)
	return html
}
