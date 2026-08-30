package fetcher

import (
	"context"
	"errors"
	"io"
	"math"
	"net/http"
	"net/url"
	"strings"
	"testing"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
	"github.com/mmcdole/gofeed"
)

type fetcherRoundTripper struct {
	response *http.Response
	err      error
}

func (r fetcherRoundTripper) RoundTrip(*http.Request) (*http.Response, error) {
	return r.response, r.err
}

type fetcherReadCloser struct {
	reader io.Reader
	err    error
}

func (r fetcherReadCloser) Read(p []byte) (int, error) {
	if r.err != nil {
		return 0, r.err
	}
	return r.reader.Read(p)
}

func (fetcherReadCloser) Close() error { return nil }

func validFetcherConfig() map[string]any {
	return map[string]any{"hub_root": "https://example.com", "route": "/feed.xml"}
}

func TestFetcherConfigValidationAndTimeoutMatrices(t *testing.T) {
	for _, raw := range []map[string]any{
		nil,
		{"route": "/feed.xml"},
		{"hub_root": "https://example.com"},
		{"hub_root": 1, "route": "/feed.xml"},
		{"hub_root": "https://example.com", "route": ""},
		{"hub_root": "https://example.com", "route": "/feed.xml", "fetch_params": "bad"},
	} {
		if _, err := NewDirectRSSFetcher(raw); err == nil {
			t.Fatalf("accepted invalid config %#v", raw)
		}
	}
	for _, value := range []any{
		[]any{1},
		[]any{"bad", 1},
		[]any{0, 1},
		[]any{1, math.NaN()},
		[]any{1, math.Inf(1)},
	} {
		raw := validFetcherConfig()
		raw["request_timeout"] = value
		if _, err := NewDirectRSSFetcher(raw); err == nil {
			t.Fatalf("accepted invalid request_timeout %#v", value)
		}
	}
	for _, raw := range []map[string]any{
		{"request_timeout": 0},
		{"request_timeout": "bad"},
		{"connect_timeout_seconds": 0},
		{"read_timeout_seconds": "bad"},
	} {
		config := validFetcherConfig()
		for key, value := range raw {
			config[key] = value
		}
		if _, err := NewDirectRSSFetcher(config); err == nil {
			t.Fatalf("accepted invalid timeout %#v", raw)
		}
	}
	config := validFetcherConfig()
	config["request_timeout"] = []any{1.5, "2"}
	config["connect_timeout_seconds"] = float32(3)
	config["read_timeout_seconds"] = int64(4)
	instance, err := NewDirectRSSFetcherWithOptions(config, FactoryOptions{
		DirectRSSConnectTimeout: 5 * time.Second,
		DirectRSSReadTimeout:    6 * time.Second,
	})
	if err != nil {
		t.Fatal(err)
	}
	if instance.(*baseFetcher).config.ConnectTimeout != 3*time.Second ||
		instance.(*baseFetcher).config.ReadTimeout != 4*time.Second {
		t.Fatalf("timeouts = %#v", instance.(*baseFetcher).config)
	}
}

func TestFetcherNumericQueryAndCloneMatrices(t *testing.T) {
	for _, value := range []any{
		int(1), int64(2), float32(3), float64(4), "5",
	} {
		if duration, err := numericSeconds(value); err != nil || duration <= 0 {
			t.Fatalf("numericSeconds(%#v) = %v, %v", value, duration, err)
		}
	}
	for _, value := range []any{nil, true, 0, -1, "", "bad", math.NaN(), math.Inf(1), float64(1e20), 1e-20} {
		if _, err := numericSeconds(value); err == nil {
			t.Fatalf("numericSeconds(%#v) unexpectedly succeeded", value)
		}
	}

	values := make(url.Values)
	for key, value := range map[string]any{
		"string": "value", "bool": true, "int": int8(1), "uint": uint64(2),
		"float": float32(1.5), "strings": []string{"a", "b"},
		"any": []any{"c", 3},
	} {
		if err := addQueryValue(values, key, value); err != nil {
			t.Fatalf("addQueryValue(%s): %v", key, err)
		}
	}
	if err := addQueryValue(values, "bad", map[string]any{}); err == nil {
		t.Fatal("accepted unsupported query value")
	}
	nested := map[string]any{"nested": map[string]any{"value": "one"}, "list": []any{map[string]any{"value": "two"}}, "strings": []string{"x"}}
	cloned := cloneParams(nested)
	cloned["nested"].(map[string]any)["value"] = "changed"
	cloned["list"].([]any)[0].(map[string]any)["value"] = "changed"
	cloned["strings"].([]string)[0] = "changed"
	if nested["nested"].(map[string]any)["value"] != "one" ||
		nested["list"].([]any)[0].(map[string]any)["value"] != "two" ||
		nested["strings"].([]string)[0] != "x" {
		t.Fatal("cloneParams did not deep-copy values")
	}
}

func TestFetcherURLResolutionAndCanonicalErrors(t *testing.T) {
	for _, values := range [][2]string{
		{"%", "/feed"}, {"https://example.com", "%"},
	} {
		if _, err := resolveURL(values[0], values[1]); err == nil {
			t.Fatalf("resolveURL(%q, %q) unexpectedly succeeded", values[0], values[1])
		}
	}
	if _, err := CanonicalSourceIdentity("unknown", "https://example.com", "/", nil); err == nil {
		t.Fatal("accepted unsupported canonical fetcher")
	}
	if _, err := CanonicalSourceIdentity(NameRSSHub, "%", "/", nil); err == nil {
		t.Fatal("accepted invalid canonical URL")
	}
	if _, err := CanonicalSourceIdentity(NameRSSHub, "https://example.com", "%", nil); err == nil {
		t.Fatal("accepted invalid canonical route")
	}
}

func TestFetcherTransportStatusReadAndParseErrors(t *testing.T) {
	cases := []struct {
		name string
		resp *http.Response
		err  error
	}{
		{"transport", nil, errors.New("network")},
		{"status", &http.Response{StatusCode: http.StatusBadGateway, Body: io.NopCloser(strings.NewReader("upstream"))}, nil},
		{"read", &http.Response{StatusCode: http.StatusOK, Body: fetcherReadCloser{err: errors.New("read")}}, nil},
		{"parse", &http.Response{StatusCode: http.StatusOK, Body: io.NopCloser(strings.NewReader("<not xml"))}, nil},
	}
	for _, test := range cases {
		t.Run(test.name, func(t *testing.T) {
			instance := &baseFetcher{
				name:   NameDirectRSS,
				client: &http.Client{Transport: fetcherRoundTripper{response: test.resp, err: test.err}},
				parser: gofeed.NewParser(),
			}
			if _, err := instance.fetchFeed(context.Background(), "https://example.com/feed"); err == nil {
				t.Fatal("fetchFeed unexpectedly succeeded")
			}
		})
	}
	instance := &baseFetcher{
		name:   NameDirectRSS,
		client: &http.Client{Transport: fetcherRoundTripper{response: &http.Response{StatusCode: http.StatusOK, Body: io.NopCloser(strings.NewReader(strings.Repeat("x", maxFeedResponseBytes+1)))}}},
		parser: gofeed.NewParser(),
	}
	if _, err := instance.fetchFeed(context.Background(), "https://example.com/feed"); err == nil {
		t.Fatal("accepted oversized feed")
	}
	if _, err := instance.fetchFeed(context.Background(), "://bad"); err == nil {
		t.Fatal("accepted invalid request URL")
	}
}

func TestFetcherContentQualityAndFormattingEdges(t *testing.T) {
	if got := buildContents(nil, 10); got != nil {
		t.Fatalf("buildContents(nil) = %#v", got)
	}
	items := buildContents(&gofeed.Feed{FeedType: "atom", Items: []*gofeed.Item{
		nil,
		{Title: "  Title ", Link: "https://example.com", Updated: "same", Published: "same", Description: "<p>desc</p>", Custom: map[string]string{}},
	}}, 10)
	if len(items) != 1 || items[0].Published != "" {
		t.Fatalf("atom items = %#v", items)
	}
	item := &gofeed.Item{Content: "", Description: "", Custom: map[string]string{"description": "<p>custom</p>"}}
	if got := bestEffortContent(item); got != "custom" {
		t.Fatalf("custom fallback = %q", got)
	}
	if got := bestEffortContent(&gofeed.Item{Custom: map[string]string{}}); got != "" {
		t.Fatalf("empty fallback = %q", got)
	}
	for _, max := range []int{0, 2, 3, 10} {
		_ = truncateSummary("long summary", max)
	}
	if got := publishedText("", nil); got != "" {
		t.Fatalf("publishedText(nil) = %q", got)
	}
	filtered := FilterQualityContents([]content.Content{
		{ContentID: "", Title: "title", Link: "link", Content: "body"},
		{ContentID: "1", Title: "", Link: "link", Content: "body"},
		{ContentID: "2", Title: "title", Link: "link"},
		{ContentID: "3", Title: "title", Link: "link", Summary: "summary"},
		{ContentID: "3", Title: "duplicate", Link: "link", Content: "body"},
	})
	if len(filtered) != 1 || filtered[0].ContentID != "3" {
		t.Fatalf("quality filter = %#v", filtered)
	}
}

func TestFetcherFetchParameterAndTimeErrors(t *testing.T) {
	instance := &baseFetcher{name: NameRSSHub, config: endpointConfig{HubRoot: "%", Route: "/feed"}}
	if _, _, err := instance.requestURL(nil); err == nil {
		t.Fatal("requestURL accepted invalid base")
	}
	instance = &baseFetcher{name: NameRSSHub, config: endpointConfig{
		HubRoot: "https://example.com", Route: "/feed", FetchParams: map[string]any{"bad": map[string]any{}},
	}}
	if _, _, err := instance.requestURL(nil); err == nil {
		t.Fatal("requestURL accepted unsupported parameter")
	}
	if _, err := filterByTimeRange(nil, map[string]any{"filter_time": "bad"}); err == nil {
		t.Fatal("filterByTimeRange accepted invalid filter")
	}
	if _, err := filterByTimeRange([]content.Content{{Published: "not-a-time"}}, map[string]any{"filter_time": 1}); err != nil {
		t.Fatal(err)
	}
	for _, value := range []any{false, int8(0), int16(0), int32(0), uint(0), uint8(0), uint16(0), uint32(0), uint64(0), float32(0), float64(0), ""} {
		if !isFalseyFilterTime(value) {
			t.Fatalf("isFalseyFilterTime(%#v) = false", value)
		}
	}
	if isFalseyFilterTime(struct{}{}) {
		t.Fatal("unknown filter value treated as falsey")
	}
}
