package processor

import (
	"fmt"
	htmlpkg "html"
	"regexp"
	"strings"
)

var (
	whitespaceRE = regexp.MustCompile(`[ \t]+`)
	blankLinesRE = regexp.MustCompile(`\n{3,}`)
	hrefPattern  = regexp.MustCompile(`(?i)href="([^"]+)"`)
	srcPattern   = regexp.MustCompile(`(?i)src="([^"]+)"`)
)

type simpleMarkdownConverter struct{}

func (simpleMarkdownConverter) Convert(html string) (string, error) {
	if strings.TrimSpace(html) == "" {
		return "", fmt.Errorf("empty html")
	}

	text := html
	replacements := []struct {
		pattern *regexp.Regexp
		replace string
	}{
		{regexp.MustCompile(`(?is)<pre\b[^>]*><code\b[^>]*>(.*?)</code></pre>`), "\n```\n$1\n```\n"},
		{regexp.MustCompile(`(?is)<code\b[^>]*>(.*?)</code>`), "`$1`"},
		{regexp.MustCompile(`(?is)<h1\b[^>]*>(.*?)</h1>`), "\n# $1\n\n"},
		{regexp.MustCompile(`(?is)<h2\b[^>]*>(.*?)</h2>`), "\n## $1\n\n"},
		{regexp.MustCompile(`(?is)<h3\b[^>]*>(.*?)</h3>`), "\n### $1\n\n"},
		{regexp.MustCompile(`(?is)<h[4-6]\b[^>]*>(.*?)</h[4-6]>`), "\n#### $1\n\n"},
		{regexp.MustCompile(`(?is)<strong\b[^>]*>(.*?)</strong>`), "**$1**"},
		{regexp.MustCompile(`(?is)<b\b[^>]*>(.*?)</b>`), "**$1**"},
		{regexp.MustCompile(`(?is)<em\b[^>]*>(.*?)</em>`), "*$1*"},
		{regexp.MustCompile(`(?is)<i\b[^>]*>(.*?)</i>`), "*$1*"},
		{regexp.MustCompile(`(?is)<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>`), "[$2]($1)"},
		{regexp.MustCompile(`(?is)<li\b[^>]*>(.*?)</li>`), "\n- $1"},
		{regexp.MustCompile(`(?is)</(p|div|section|article|blockquote)>`), "\n\n"},
		{regexp.MustCompile(`(?is)<br\s*/?>`), "\n"},
	}
	for _, replacement := range replacements {
		text = replacement.pattern.ReplaceAllString(text, replacement.replace)
	}

	text = regexp.MustCompile(`(?is)<[^>]+>`).ReplaceAllString(text, "")
	text = htmlpkg.UnescapeString(text)
	text = whitespaceRE.ReplaceAllString(text, " ")
	lines := strings.Split(text, "\n")
	for i, line := range lines {
		lines[i] = strings.TrimSpace(line)
	}
	text = strings.Join(lines, "\n")
	text = blankLinesRE.ReplaceAllString(text, "\n\n")
	text = strings.TrimSpace(text)
	if text == "" {
		return "", fmt.Errorf("empty markdown after conversion")
	}
	return text, nil
}

func stripTagPairs(html string, tags ...string) string {
	out := html
	for _, tag := range tags {
		out = regexp.MustCompile(fmt.Sprintf(`(?is)<%s\b[^>]*>.*?</%s>`, regexp.QuoteMeta(tag), regexp.QuoteMeta(tag))).ReplaceAllString(out, "")
	}
	return out
}

func extractTagContent(html string, tag string) string {
	pattern := regexp.MustCompile(
		fmt.Sprintf(
			`(?is)<%s\b[^>]*>(.*?)</%s>`,
			regexp.QuoteMeta(tag),
			regexp.QuoteMeta(tag),
		),
	)
	match := pattern.FindStringSubmatch(html)
	if len(match) < 2 {
		return ""
	}
	return match[1]
}
