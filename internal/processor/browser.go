package processor

import (
	"context"
	"fmt"
	"net/url"
	"strings"
	"time"

	"github.com/chromedp/cdproto/emulation"
	"github.com/chromedp/chromedp"
)

const maxBrowserHTMLBytes = 20 << 20

type cdpBrowserRenderer struct{}

func (cdpBrowserRenderer) RenderHTML(
	ctx context.Context,
	endpoint string,
	options BrowserRenderOptions,
) (string, error) {
	if err := validateBrowserEndpoint(endpoint); err != nil {
		return "", err
	}
	if err := validatePageURL(options.URL); err != nil {
		return "", err
	}
	timeout := time.Duration(options.TimeoutMs) * time.Millisecond
	if timeout <= 0 {
		timeout = time.Minute
	}
	timeoutCtx, cancelTimeout := context.WithTimeout(ctx, timeout)
	defer cancelTimeout()
	allocatorCtx, cancelAllocator := chromedp.NewRemoteAllocator(
		timeoutCtx,
		endpoint,
	)
	defer cancelAllocator()
	browserCtx, cancelBrowser := chromedp.NewContext(allocatorCtx)
	defer cancelBrowser()

	actions := make([]chromedp.Action, 0, 4)
	if strings.TrimSpace(options.UserAgent) != "" {
		actions = append(
			actions,
			emulation.SetUserAgentOverride(options.UserAgent),
		)
	}
	var html string
	actions = append(
		actions,
		chromedp.Navigate(options.URL),
		chromedp.WaitReady("body", chromedp.ByQuery),
		chromedp.OuterHTML("html", &html, chromedp.ByQuery),
	)
	if err := chromedp.Run(browserCtx, actions...); err != nil {
		return "", fmt.Errorf("render page through Browserless: %w", err)
	}
	if len(html) > maxBrowserHTMLBytes {
		return "", fmt.Errorf(
			"rendered HTML exceeds %d bytes",
			maxBrowserHTMLBytes,
		)
	}
	return html, nil
}

func validateBrowserEndpoint(rawURL string) error {
	return validateURLSchemes(
		rawURL,
		"browserless endpoint",
		map[string]struct{}{
			"http": {}, "https": {}, "ws": {}, "wss": {},
		},
	)
}

func validatePageURL(rawURL string) error {
	return validateURLSchemes(
		rawURL,
		"page URL",
		map[string]struct{}{"http": {}, "https": {}},
	)
}

func validateURLSchemes(
	rawURL string,
	field string,
	allowed map[string]struct{},
) error {
	parsed, err := url.Parse(strings.TrimSpace(rawURL))
	if err != nil {
		return fmt.Errorf("parse %s: %w", field, err)
	}
	if _, ok := allowed[parsed.Scheme]; !ok {
		return fmt.Errorf("%s has unsupported scheme %q", field, parsed.Scheme)
	}
	if parsed.Host == "" {
		return fmt.Errorf("%s host is required", field)
	}
	return nil
}
