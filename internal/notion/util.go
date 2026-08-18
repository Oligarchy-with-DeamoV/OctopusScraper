package notion

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"html"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"time"
)

const (
	notionVersion         = "2026-03-11"
	maxTextLength         = 2000
	maxRichTextItems      = 100
	maxBlocksPerRequest   = 100
	maxMultiSelectOptions = 100
	maxOptionNameLength   = 100
	maxURLLength          = 2000
	minRequestInterval    = 500 * time.Millisecond
	contentIDCacheTTL     = 5 * time.Minute
	defaultSummary        = "[No summary available]"
	propertyNameTitle     = "Name"
	propertyNameSummary   = "Summary"
	propertyNameContentID = "ContentId"
	propertyNameURL       = "URL"
	propertyNameAuthor    = "Author"
	propertyNameKeywords  = "Keywords"
	propertyNameTags      = "Tags"
	propertyNameSource    = "Source"
	propertyNamePublished = "Published Date"
)

var (
	htmlTagPattern          = regexp.MustCompile(`(?s)<[^>]+>`)
	whitespacePattern       = regexp.MustCompile(`\s+`)
	summarySpacePattern     = regexp.MustCompile(`[ \t]+`)
	summaryBreakPattern     = regexp.MustCompile(`\n{3,}`)
	dividerPattern          = regexp.MustCompile(`^\s{0,3}((\*\s*){3,}|(-\s*){3,}|(_\s*){3,})\s*$`)
	headingPattern          = regexp.MustCompile(`^\s{0,3}(#{1,6})\s+(.*)$`)
	unorderedListPattern    = regexp.MustCompile(`^\s*[-+*]\s+(.*)$`)
	orderedListPattern      = regexp.MustCompile(`^\s*\d+[.)]\s+(.*)$`)
	blockquotePattern       = regexp.MustCompile(`^\s*>\s?(.*)$`)
	imagePattern            = regexp.MustCompile(`!\[([^\]]*)\]\(([^)]+)\)`)
	tableSeparatorPattern   = regexp.MustCompile(`^\s*\|?(\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$`)
	inlineSpecialCharacters = "`[*_~!"
)

func sanitizeOptionName(raw string) string {
	if raw == "" {
		return ""
	}
	value := whitespacePattern.ReplaceAllString(strings.TrimSpace(raw), " ")
	if value == "" {
		return ""
	}
	runes := []rune(value)
	if len(runes) > maxOptionNameLength {
		value = string(runes[:maxOptionNameLength])
	}
	return value
}

func sanitizeURL(raw string) *string {
	value := strings.TrimSpace(raw)
	if value == "" {
		return nil
	}
	if len(value) > maxURLLength {
		return nil
	}
	if strings.ContainsAny(value, "\r\n\t ") {
		return nil
	}
	parsed, err := url.Parse(value)
	if err != nil || parsed == nil {
		return nil
	}
	if parsed.Scheme != "http" && parsed.Scheme != "https" {
		return nil
	}
	if parsed.Host == "" {
		return nil
	}
	return &value
}

func sanitizeSummary(raw string) string {
	value := strings.TrimSpace(html.UnescapeString(raw))
	value = htmlTagPattern.ReplaceAllString(value, "")
	value = strings.ReplaceAll(value, "\r\n", "\n")
	value = strings.ReplaceAll(value, "\r", "\n")
	value = summarySpacePattern.ReplaceAllString(value, " ")
	value = summaryBreakPattern.ReplaceAllString(value, "\n\n")
	value = strings.TrimSpace(value)
	if value == "" {
		return defaultSummary
	}
	return value
}

func limitRichTextSegments(richText []map[string]any) []map[string]any {
	if len(richText) <= maxRichTextItems {
		return richText
	}
	return richText[:maxRichTextItems]
}

func parsePublishedDate(raw string) *string {
	value := strings.TrimSpace(raw)
	if value == "" {
		return nil
	}
	layouts := []string{
		time.RFC3339Nano,
		time.RFC3339,
		time.RFC1123Z,
		time.RFC1123,
		time.RFC822Z,
		time.RFC822,
		time.RFC850,
		"2006-01-02 15:04:05 -0700 MST",
		"2006-01-02 15:04:05 -0700",
		"2006-01-02 15:04:05",
		"2006-01-02",
	}
	for _, layout := range layouts {
		if parsed, err := time.Parse(layout, value); err == nil {
			formatted := parsed.Format(time.RFC3339)
			return &formatted
		}
	}
	if parsed, err := http.ParseTime(value); err == nil {
		formatted := parsed.Format(time.RFC3339)
		return &formatted
	}
	return nil
}

func pendingContentID(contentID string) string {
	digest := sha256.Sum256([]byte(contentID))
	return "pending:" + hex.EncodeToString(digest[:])
}

func newToken(prefix string) string {
	buffer := make([]byte, 8)
	if _, err := rand.Read(buffer); err != nil {
		return fmt.Sprintf("%s-%d", prefix, time.Now().UnixNano())
	}
	return fmt.Sprintf("%s-%s", prefix, hex.EncodeToString(buffer))
}

func sleepContext(ctx context.Context, delay time.Duration) error {
	if delay <= 0 {
		return nil
	}
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}

func joinErrors(errs []error) error {
	filtered := make([]error, 0, len(errs))
	for _, err := range errs {
		if err != nil {
			filtered = append(filtered, err)
		}
	}
	if len(filtered) == 0 {
		return nil
	}
	return errors.Join(filtered...)
}
