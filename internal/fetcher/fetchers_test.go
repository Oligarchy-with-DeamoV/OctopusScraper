package fetcher

import (
	"context"
	"encoding/json"
	"math"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
	"time"

	"github.com/mmcdole/gofeed"
)

func TestRSSHubFetcherMergesQueryParamsAndDoesNotMutateConfig(t *testing.T) {
	var requestedQuery url.Values
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestedQuery = r.URL.Query()
		w.Header().Set("Content-Type", "application/rss+xml")
		_, _ = w.Write([]byte(rssFeed(`
			<item>
				<title>Test Entry</title>
				<link>https://example.com/items/1?from=feed</link>
				<guid>guid-1</guid>
				<pubDate>Tue, 18 Aug 2026 11:00:00 +0000</pubDate>
				<description><![CDATA[<p>Summary</p>]]></description>
			</item>`)))
	}))
	defer server.Close()

	rawConfig := map[string]any{
		"hub_root":     server.URL,
		"route":        "/feed.xml",
		"fetch_params": map[string]any{"limit": 5},
	}
	fetcher, err := NewRSSHubFetcher(rawConfig)
	if err != nil {
		t.Fatalf("NewRSSHubFetcher() error = %v", err)
	}
	contents, err := fetcher.Fetch(context.Background(), map[string]any{"filter_title": "test", "limit": 2})
	if err != nil {
		t.Fatalf("Fetch() error = %v", err)
	}
	if len(contents) != 1 {
		t.Fatalf("len(contents) = %d", len(contents))
	}
	if requestedQuery.Get("limit") != "2" || requestedQuery.Get("filter_title") != "test" {
		t.Fatalf("requested query = %#v", requestedQuery)
	}
	if rawConfig["fetch_params"].(map[string]any)["limit"] != 5 {
		t.Fatalf("fetch params were mutated: %#v", rawConfig)
	}
}

func TestDirectRSSFetcherAppliesFilterTimeAndQualityFilter(t *testing.T) {
	recent := time.Now().UTC().Add(-30 * time.Minute).Format(time.RFC3339)
	old := time.Now().UTC().Add(-2 * time.Hour).Format(time.RFC3339)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/rss+xml")
		_, _ = w.Write([]byte(rssFeed(`
			<item>
				<title>Recent</title>
				<link>https://example.com/items/recent</link>
				<guid>recent</guid>
				<pubDate>` + recent + `</pubDate>
				<description><![CDATA[<p>Recent summary</p>]]></description>
			</item>
			<item>
				<title>Old</title>
				<link>https://example.com/items/old</link>
				<guid>old</guid>
				<pubDate>` + old + `</pubDate>
				<description><![CDATA[<p>Old summary</p>]]></description>
			</item>
			<item>
				<title></title>
				<link>https://example.com/items/invalid</link>
				<guid>invalid</guid>
				<description><![CDATA[<p>Missing title</p>]]></description>
			</item>`)))
	}))
	defer server.Close()

	fetcher, err := NewDirectRSSFetcher(map[string]any{"hub_root": server.URL, "route": "/feed.xml"})
	if err != nil {
		t.Fatalf("NewDirectRSSFetcher() error = %v", err)
	}
	contents, err := fetcher.Fetch(context.Background(), map[string]any{"filter_time": 3600})
	if err != nil {
		t.Fatalf("Fetch() error = %v", err)
	}
	if len(contents) != 1 || contents[0].Title != "Recent" {
		t.Fatalf("contents = %#v", contents)
	}
}

func TestFilterByTimeRangeTreatsFalseyValuesAsDisabled(t *testing.T) {
	for _, value := range []any{nil, false, 0, int64(0), float64(0), ""} {
		if _, err := filterByTimeRange(nil, map[string]any{
			"filter_time": value,
		}); err != nil {
			t.Fatalf("filter_time=%#v returned %v", value, err)
		}
	}
}

func TestParsePublishedTimeAcceptsLegacyISOForms(t *testing.T) {
	for _, value := range []string{
		"2025-04-06 13:50:59",
		"2025-04-06 13:50:59+08:00",
		"2025-04-06",
	} {
		if _, ok := parsePublishedTime(value); !ok {
			t.Fatalf("parsePublishedTime(%q) failed", value)
		}
	}
}

func TestStableContentIDAndFallbackMarkdown(t *testing.T) {
	idOne := stableContentID("https://example.com/path?a=1", "2026-08-18T11:00:00Z", "guid")
	idTwo := stableContentID("https://example.com/path?b=2", "2026-08-18T11:00:00Z", "guid")
	if idOne != idTwo {
		t.Fatalf("stableContentID should ignore query strings: %s != %s", idOne, idTwo)
	}
	content := bestEffortContent(&gofeed.Item{Description: "<p>Hello <strong>world</strong></p>"})
	if content != "Hello **world**" {
		t.Fatalf("bestEffortContent() = %q", content)
	}
}

func TestFactoryOptionsOverrideSummaryLength(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/rss+xml")
		_, _ = w.Write([]byte(rssFeed(`
			<item>
				<title>Test Entry</title>
				<link>https://example.com/items/1</link>
				<guid>guid-1</guid>
				<pubDate>Tue, 18 Aug 2026 11:00:00 +0000</pubDate>
				<description><![CDATA[<p>1234567890</p>]]></description>
			</item>`)))
	}))
	defer server.Close()

	factory := NewFactory(FactoryOptions{SummaryMaxLength: 8})
	instance, err := factory.Create(NameDirectRSS, map[string]any{
		"hub_root": server.URL,
		"route":    "/feed.xml",
	})
	if err != nil {
		t.Fatalf("Create() error = %v", err)
	}
	contents, err := instance.Fetch(context.Background(), nil)
	if err != nil {
		t.Fatalf("Fetch() error = %v", err)
	}
	if len(contents) != 1 || contents[0].Summary != "12345..." {
		t.Fatalf("contents = %#v", contents)
	}
}

func TestTruncateSummaryCountsUnicodeCharacters(t *testing.T) {
	if got := truncateSummary("中文摘要内容", 5); got != "中文..." {
		t.Fatalf("truncateSummary() = %q", got)
	}
}

func TestNumericSecondsRejectsNonFiniteAndOverflowValues(t *testing.T) {
	for _, value := range []any{
		math.NaN(),
		math.Inf(1),
		float64(1 << 63),
	} {
		if _, err := numericSeconds(value); err == nil {
			t.Fatalf("numericSeconds(%v) unexpectedly succeeded", value)
		}
	}
}

func TestFactorySupportsRSSHubAndDirectRSS(t *testing.T) {
	factory := NewFactory()
	for _, name := range []string{NameRSSHub, NameDirectRSS} {
		if _, err := factory.Create(name, map[string]any{"hub_root": "https://example.com", "route": "/feed.xml"}); err != nil {
			t.Fatalf("Create(%q) error = %v", name, err)
		}
	}
	if _, err := factory.Create("missing", nil); err == nil {
		t.Fatalf("Create() unexpectedly accepted unsupported fetcher")
	}
	if _, err := factory.Create(NameRSSHub, map[string]any{
		"hub_root": "https://example.com",
		"route":    "/feed.xml",
		"fetch_params": map[string]any{
			"filter": map[string]any{"title": "Go"},
		},
	}); err == nil {
		t.Fatal("Create() accepted an unsupported nested query parameter")
	}
}

func TestFetchParsesAtomFeeds(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/atom+xml")
		_, _ = w.Write([]byte(`<?xml version="1.0" encoding="utf-8"?>
			<feed xmlns="http://www.w3.org/2005/Atom">
			  <title>Example Feed</title>
			  <entry>
			    <title>Atom Entry</title>
			    <link href="https://example.com/atom/1"/>
			    <id>atom-1</id>
			    <updated>2026-08-18T11:00:00Z</updated>
			    <summary type="html"><![CDATA[<p>Atom summary</p>]]></summary>
			  </entry>
			</feed>`))
	}))
	defer server.Close()

	fetcher, err := NewDirectRSSFetcher(map[string]any{"hub_root": server.URL, "route": "/atom.xml"})
	if err != nil {
		t.Fatalf("NewDirectRSSFetcher() error = %v", err)
	}
	contents, err := fetcher.Fetch(context.Background(), nil)
	if err != nil {
		t.Fatalf("Fetch() error = %v", err)
	}
	if len(contents) != 1 || strings.TrimSpace(contents[0].Summary) != "Atom summary" {
		t.Fatalf("contents = %#v", contents)
	}
	if contents[0].Published != "" ||
		contents[0].ContentID != stableContentID(
			"https://example.com/atom/1",
			"",
			"atom-1",
		) {
		t.Fatalf("Atom compatibility fields = %#v", contents[0])
	}
}

func TestBuildContentsPreservesLegacyAuthorAndSummaryContract(t *testing.T) {
	items := buildContents(&gofeed.Feed{Items: []*gofeed.Item{{
		Title:       "Entry",
		Link:        "https://example.com/entry",
		GUID:        "entry-1",
		Description: "<p>Line one</p><p>Line two</p>",
		Author:      &gofeed.Person{Name: "Author"},
	}}}, 500)
	if len(items) != 1 {
		t.Fatalf("items = %#v", items)
	}
	if items[0].Author != nil {
		t.Fatalf("author = %#v, want nil for Python compatibility", items[0].Author)
	}
	if items[0].Summary != "Line one Line two" {
		t.Fatalf("summary = %q", items[0].Summary)
	}
}

func TestRSSAndContentContractFixtures(t *testing.T) {
	feed, err := os.ReadFile(
		filepath.Join("..", "..", "contracts", "rss", "sample.xml"),
	)
	if err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		_ *http.Request,
	) {
		writer.Header().Set("Content-Type", "application/rss+xml")
		_, _ = writer.Write(feed)
	}))
	defer server.Close()

	active, err := NewDirectRSSFetcher(map[string]any{
		"hub_root": server.URL,
		"route":    "/sample.xml",
	})
	if err != nil {
		t.Fatal(err)
	}
	items, err := active.Fetch(context.Background(), nil)
	if err != nil {
		t.Fatal(err)
	}
	type contractContent struct {
		ContentID string `json:"content_id"`
		Title     string `json:"title"`
		Link      string `json:"link"`
		Published string `json:"published"`
		Summary   string `json:"summary"`
		Content   string `json:"content"`
	}
	actual := make([]contractContent, 0, len(items))
	for _, item := range items {
		actual = append(actual, contractContent{
			ContentID: item.ContentID,
			Title:     item.Title,
			Link:      item.Link,
			Published: item.Published,
			Summary:   item.Summary,
			Content:   item.Content,
		})
	}
	golden, err := os.ReadFile(
		filepath.Join("..", "..", "contracts", "golden", "content.json"),
	)
	if err != nil {
		t.Fatal(err)
	}
	var expected []contractContent
	if err := json.Unmarshal(golden, &expected); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(actual, expected) {
		t.Fatalf("contract content mismatch:\nactual: %#v\nexpected: %#v", actual, expected)
	}
}

func rssFeed(items string) string {
	return `<?xml version="1.0" encoding="UTF-8"?>
	<rss version="2.0">
	  <channel>
	    <title>Example</title>` + items + `
	  </channel>
	</rss>`
}
