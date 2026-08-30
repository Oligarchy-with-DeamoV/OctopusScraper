package processor

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"math"
	"net/http"
	"reflect"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
)

func TestConfigValidationAndHelperMatrices(t *testing.T) {
	if _, err := parseHTMLConfig(map[string]any{"priority": -1}); err == nil {
		t.Fatal("negative HTML priority accepted")
	}
	if _, err := parseHTMLConfig(map[string]any{"timeout": 0}); err == nil {
		t.Fatal("zero HTML timeout accepted")
	}
	if _, err := parseHTMLConfig(map[string]any{"browser_timeout": 0}); err == nil {
		t.Fatal("zero browser timeout accepted")
	}
	if _, err := parseHTMLConfig(map[string]any{"browserless_url": "file:///browser"}); err == nil {
		t.Fatal("invalid browser endpoint accepted")
	}
	baseCases := []map[string]any{
		{"priority": -1},
		{"llm_provider": "other"},
		{"model_name": ""},
		{"max_tokens": 0},
		{"temperature": -0.1},
		{"temperature": 2.1},
		{"timeout": 0},
		{"retry_times": 0},
		{"base_url": "file:///model"},
	}
	for _, raw := range baseCases {
		if _, err := parseBaseLLMConfig(raw); err == nil {
			t.Fatalf("accepted invalid base config %#v", raw)
		}
	}
	if _, err := parseSummaryConfig(map[string]any{"max_summary_length": 0}); err == nil {
		t.Fatal("zero summary length accepted")
	}
	if _, err := parseSummaryConfig(map[string]any{"summary_style": "unknown"}); err == nil {
		t.Fatal("unknown summary style accepted")
	}
	if _, err := parseSummaryConfig(map[string]any{"max_summary_length": "bad"}); err == nil {
		t.Fatal("invalid summary field type accepted")
	}
	if _, err := parseSummaryConfig(map[string]any{"model_name": ""}); err == nil {
		t.Fatal("invalid summary base config accepted")
	}
	for _, raw := range []map[string]any{
		{"keywords_count": 0}, {"max_keywords": 0},
		{"min_keyword_length": 0}, {"max_keyword_length": 1},
		{"language_preference": "fr"}, {"min_importance_score": -0.1},
		{"min_importance_score": 1.1}, {"exclude_patterns": []any{"["}},
	} {
		if _, err := parseKeywordsConfig(raw); err == nil {
			t.Fatalf("accepted invalid keyword config %#v", raw)
		}
	}
	if _, err := parseKeywordsConfig(map[string]any{"model_name": ""}); err == nil {
		t.Fatal("invalid keyword base config accepted")
	}
	for _, raw := range []map[string]any{
		{"max_tags": 0}, {"max_tags_count": 0}, {"confidence_threshold": -0.1},
		{"confidence_threshold": 1.1},
	} {
		if _, err := parseTagsConfig(raw); err == nil {
			t.Fatalf("accepted invalid tag config %#v", raw)
		}
	}
	if _, err := parseTagsConfig(map[string]any{"model_name": ""}); err == nil {
		t.Fatal("invalid tag base config accepted")
	}

	allValues := []any{int(1), int8(1), int16(1), int32(1), int64(1), uint(1), uint8(1), uint16(1), uint32(1), uint64(1), float32(1), float64(1)}
	for _, value := range allValues {
		if number, ok := numericValue(value); !ok || number != 1 {
			t.Fatalf("numericValue(%T) = %v, %v", value, number, ok)
		}
	}
	if _, ok := numericValue("1"); ok {
		t.Fatal("string accepted by numericValue")
	}
	for _, value := range []any{int(1), int8(1), int16(1), int32(1), int64(1), uint(1), uint8(1), uint16(1), uint32(1), uint64(1)} {
		if !isInteger(value) {
			t.Fatalf("isInteger(%T) = false", value)
		}
	}
	for _, value := range []any{float64(1), "1", true} {
		if isInteger(value) {
			t.Fatalf("isInteger(%#v) = true", value)
		}
	}
	for _, kind := range []configValueKind{configString, configBoolean, configInteger, configNumber, configStringList, configStringListMap, configValueKind(99)} {
		if configKindName(kind) == "" {
			t.Fatalf("empty kind name for %d", kind)
		}
	}
	if !validConfigValue("x", configString) || !validConfigValue(true, configBoolean) ||
		!validConfigValue(1, configInteger) || !validConfigValue(1.2, configNumber) ||
		!validConfigValue([]any{"x"}, configStringList) ||
		!validConfigValue(map[string]any{"x": []any{"y"}}, configStringListMap) {
		t.Fatal("valid config values rejected")
	}
	if validConfigValue(math.NaN(), configNumber) ||
		validConfigValue(map[string]any{"x": []any{1}}, configStringListMap) ||
		validConfigValue("x", configValueKind(99)) {
		t.Fatal("invalid config value accepted")
	}
	if err := validateConfigFields(map[string]any{"optional": nil}, configFieldSpec{key: "optional", kind: configString, nullable: true}); err != nil {
		t.Fatal(err)
	}
	if err := validateConfigFields(map[string]any{"x": 1}, configFieldSpec{key: "x", kind: configString}); err == nil {
		t.Fatal("invalid field type accepted")
	}
}

func TestConfigGettersSlicesAndURLHelpers(t *testing.T) {
	raw := map[string]any{
		"s": " text ", "b": " true ", "i": " 42 ", "f": " 1.5 ",
		"list": []any{" a ", 2, " ", "b"}, "strings": []string{" c ", ""},
		"categories": map[string]any{"topic": []any{" ai ", 1}},
	}
	if getString(raw, "", "s") != "text" || !getBool(raw, false, "b") ||
		getInt(raw, 0, "i") != 42 || getFloat(raw, 0, "f") != 1.5 {
		t.Fatal("getter conversions failed")
	}
	if got := getStringSlice(raw, "list"); !reflect.DeepEqual(got, []string{"a", "b"}) {
		t.Fatalf("list = %#v", got)
	}
	if got := getStringSlice(raw, "strings"); !reflect.DeepEqual(got, []string{"c"}) {
		t.Fatalf("strings = %#v", got)
	}
	if got := getStringSlice(raw, "missing"); got != nil {
		t.Fatalf("missing list = %#v", got)
	}
	if got := getStringSlice(map[string]any{"x": "bad"}, "x"); got != nil {
		t.Fatalf("bad list = %#v", got)
	}
	if got := getStringSliceMap(raw, "categories"); !reflect.DeepEqual(got, map[string][]string{"topic": {"ai"}}) {
		t.Fatalf("categories = %#v", got)
	}
	if getStringSliceMap(map[string]any{"x": "bad"}, "x") != nil {
		t.Fatal("bad category map accepted")
	}
	if getStringSliceMap(map[string]any{}, "x") != nil {
		t.Fatal("missing category map should be nil")
	}
	for _, value := range []any{true, "bad", nil} {
		if getBool(map[string]any{"x": value}, true, "x") != true {
			t.Fatalf("getBool(%#v) changed fallback", value)
		}
	}
	if getInt(map[string]any{"x": "bad"}, 9, "x") != 9 || getFloat(map[string]any{"x": "bad"}, 9, "x") != 9 {
		t.Fatal("numeric getter fallback failed")
	}
	for _, value := range []any{int8(1), int16(2), int32(3), int64(4), uint(5), uint8(6), uint16(7), uint32(8), uint64(9), float32(10), float64(11)} {
		if getInt(map[string]any{"x": value}, 0, "x") == 0 {
			t.Fatalf("getInt(%T) did not convert", value)
		}
	}
	for _, value := range []any{float32(1), float64(2), int(3), int64(4), "5"} {
		if getFloat(map[string]any{"x": value}, 0, "x") == 0 {
			t.Fatalf("getFloat(%T) did not convert", value)
		}
	}
	if !isStringList([]string{"x"}) || !isStringList([]any{"x"}) ||
		isStringList([]any{"x", 1}) || isStringList("x") {
		t.Fatal("isStringList matrix failed")
	}
	if validConfigValue(map[string]any{"x": "bad"}, configStringListMap) {
		t.Fatal("invalid string-list map accepted")
	}
	if validConfigValue("bad", configStringListMap) {
		t.Fatal("non-map accepted as string-list map")
	}
	if sameHTTPBaseURL("https://example.com/a/", "https://example.com/a") != true ||
		sameHTTPBaseURL("https://example.com/a?x=1", "https://example.com/a?x=2") {
		t.Fatal("sameHTTPBaseURL comparison failed")
	}
	if sameHTTPBaseURL("%", "https://example.com") {
		t.Fatal("invalid URL considered equal")
	}
	if _, err := parseBaseLLMConfig(map[string]any{"api_key": nil}); err != nil {
		t.Fatal(err)
	}
	if validateHTTPBaseURL("://bad") == nil || validateHTTPBaseURL("ftp://example.com") == nil ||
		validateHTTPBaseURL("https:///missing-host") == nil {
		t.Fatal("invalid HTTP URLs accepted")
	}
}

type sequenceLLM struct {
	results []struct {
		response string
		err      error
	}
	calls atomic.Int32
}

func (c *sequenceLLM) CreateChatCompletion(ctx context.Context, _ ChatRequest) (string, error) {
	index := int(c.calls.Add(1)) - 1
	if index >= len(c.results) {
		return "", errors.New("unexpected call")
	}
	if err := c.results[index].err; err != nil {
		return "", err
	}
	return c.results[index].response, nil
}

func TestLLMCommonRetryParsingAndHelpers(t *testing.T) {
	client := &sequenceLLM{results: []struct {
		response string
		err      error
	}{{err: errors.New("temporary")}, {response: " okay "}}}
	var observed bool
	result, err := invokeLLM(context.Background(), BaseLLMProcessorConfig{
		BaseURL: "https://example.com", ModelName: "model", RetryTimes: 2, Timeout: time.Second,
		observer: func(_ time.Duration, success bool) { observed = success },
	}, client, ChatRequest{})
	if err != nil || result != "okay" || !observed {
		t.Fatalf("retry result = %q, %v, observed=%v", result, err, observed)
	}
	if _, err := invokeLLM(context.Background(), BaseLLMProcessorConfig{RetryTimes: 1}, nil, ChatRequest{}); err == nil {
		t.Fatal("nil LLM client accepted")
	}
	if _, err := invokeLLM(context.Background(), BaseLLMProcessorConfig{}, &sequenceLLM{}, ChatRequest{}); err == nil {
		t.Fatal("zero retry count unexpectedly succeeded")
	}
	cancelled, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := invokeLLM(cancelled, BaseLLMProcessorConfig{RetryTimes: 2, Timeout: time.Second}, &sequenceLLM{results: []struct {
		response string
		err      error
	}{{err: errors.New("x")}}}, ChatRequest{}); !errors.Is(err, context.Canceled) {
		t.Fatalf("cancelled retry error = %v", err)
	}
	for _, raw := range []string{
		"```json\n{\"x\":1}\n```",
		"prefix {\"x\":1} suffix",
	} {
		var target map[string]int
		if err := parseJSONObject(raw, &target); err != nil || target["x"] != 1 {
			t.Fatalf("parseJSONObject(%q) = %#v, %v", raw, target, err)
		}
	}
	var target map[string]any
	if err := parseJSONObject("not json", &target); err == nil {
		t.Fatal("invalid JSON accepted")
	}
	if got := trimPromptInput("  abc  ", 2); got != "ab" {
		t.Fatalf("trimPromptInput = %q", got)
	}
	if got := splitSentences("One. Two! Three?", 2); !reflect.DeepEqual(got, []string{"One", "Two"}) {
		t.Fatalf("splitSentences = %#v", got)
	}
	if got := truncateWords("one two", 0); got != "" || truncateWords("one two", 1) != "one" {
		t.Fatalf("truncateWords edge = %q", got)
	}
	if got := dedupeCaseInsensitive([]string{" A ", "", "a", "B"}, 0); !reflect.DeepEqual(got, []string{"A", "B"}) {
		t.Fatalf("dedupe = %#v", got)
	}
	if got := sortedMapKeys(map[string]float64{"b": 1, "a": 2}); !reflect.DeepEqual(got, []string{"a", "b"}) {
		t.Fatalf("sorted keys = %#v", got)
	}
	if max(2, 1) != 2 || max(1, 2) != 2 {
		t.Fatal("max helper failed")
	}
}

type failingExtractor struct{ err error }

func (failingExtractor) ExtractHTML(string, string) (string, error) { return "", errors.New("extract") }

type failingConverter struct {
	output string
	err    error
}

func (f failingConverter) Convert(string) (string, error) { return f.output, f.err }

type processorRoundTripper struct {
	body io.ReadCloser
	code int
	err  error
}

func (r processorRoundTripper) RoundTrip(*http.Request) (*http.Response, error) {
	if r.err != nil {
		return nil, r.err
	}
	return &http.Response{StatusCode: r.code, Body: r.body, Header: make(http.Header)}, nil
}

func TestHTMLProcessorBrowserAndHTTPErrorBranches(t *testing.T) {
	if _, err := newHTMLContentProcessor(map[string]any{"timeout": 0}, htmlProcessorDeps{}); err == nil {
		t.Fatal("invalid HTML config accepted")
	}
	browser := &fakeBrowser{html: "<article>browser</article>"}
	active, err := newHTMLContentProcessor(map[string]any{
		"browserless_url": "http://browserless", "use_browser": true,
	}, htmlProcessorDeps{browserRenderer: browser, articleExtractor: simpleArticleExtractor{}, markdown: simpleMarkdownConverter{}, logger: slog.Default()})
	if err != nil {
		t.Fatal(err)
	}
	items, err := active.Process(context.Background(), []content.Content{{Link: "https://example.com"}})
	if err != nil || items[0].Content != "browser" {
		t.Fatalf("browser success = %#v, %v", items, err)
	}
	emptyBrowser := &fakeBrowser{}
	active.deps.browserRenderer = emptyBrowser
	active.deps.httpClient = &http.Client{Transport: processorRoundTripper{
		code: http.StatusOK, body: io.NopCloser(strings.NewReader("<body>http</body>")),
	}}
	if _, err := active.Process(context.Background(), []content.Content{{Link: "https://example.com"}}); err != nil {
		t.Fatal(err)
	}
	for _, transport := range []http.RoundTripper{
		processorRoundTripper{code: http.StatusBadGateway, body: io.NopCloser(strings.NewReader("bad"))},
		processorRoundTripper{code: http.StatusOK, body: processorErrorBody{}},
		processorRoundTripper{err: errors.New("network")},
	} {
		active.deps.browserRenderer = nil
		active.deps.httpClient = &http.Client{Transport: transport}
		active.deps.retryDelay = time.Nanosecond
		if _, err := active.fetchHTMLOnce(context.Background(), "https://example.com"); err == nil {
			t.Fatal("fetchHTMLOnce unexpectedly succeeded")
		}
	}
	for _, item := range []content.Content{{}, {Link: "://bad"}} {
		if _, err := active.processOne(context.Background(), item); err == nil {
			t.Fatalf("processOne accepted %#v", item)
		}
	}
}

type processorErrorBody struct{}

func (processorErrorBody) Read([]byte) (int, error) { return 0, errors.New("body read") }
func (processorErrorBody) Close() error             { return nil }

func TestHTMLProcessorExtractorConverterAndUtilityBranches(t *testing.T) {
	active, err := newHTMLContentProcessor(map[string]any{"use_browser": false}, htmlProcessorDeps{
		httpClient: &http.Client{Transport: processorRoundTripper{
			code: http.StatusOK, body: io.NopCloser(strings.NewReader("<html>ok</html>")),
		}},
		articleExtractor: failingExtractor{},
		retryDelay:       time.Nanosecond,
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := active.processOne(context.Background(), content.Content{Link: "https://example.com"}); err == nil {
		t.Fatal("extractor error was ignored")
	}
	active.deps.articleExtractor = simpleArticleExtractor{}
	active.deps.markdown = failingConverter{err: errors.New("convert")}
	active.deps.httpClient = &http.Client{Transport: processorRoundTripper{
		code: http.StatusOK, body: io.NopCloser(strings.NewReader("<html>ok</html>")),
	}}
	if _, err := active.processOne(context.Background(), content.Content{Link: "https://example.com"}); err == nil {
		t.Fatal("converter error was ignored")
	}
	active.deps.markdown = failingConverter{output: "  "}
	active.deps.httpClient = &http.Client{Transport: processorRoundTripper{
		code: http.StatusOK, body: io.NopCloser(strings.NewReader("<html>ok</html>")),
	}}
	if _, err := active.processOne(context.Background(), content.Content{Link: "https://example.com"}); err == nil {
		t.Fatal("empty markdown accepted")
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	active.deps.httpClient = &http.Client{Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
		return nil, req.Context().Err()
	})}
	if _, err := active.fetchHTML(ctx, "https://example.com"); !errors.Is(err, context.Canceled) {
		t.Fatalf("cancelled HTML fetch = %v", err)
	}
	for _, html := range []string{
		`<article>A <a href="/x">x</a><img src="/i"></article>`,
		`<main>Main</main>`, `<body>Body</body>`, `<div>Fallback</div>`,
	} {
		got, err := (simpleArticleExtractor{}).ExtractHTML("https://example.com/base/page", html)
		if err != nil || got == "" {
			t.Fatalf("extract %q = %q, %v", html, got, err)
		}
	}
	if _, err := (simpleArticleExtractor{}).ExtractHTML("https://example.com", "   "); err == nil {
		t.Fatal("empty extraction accepted")
	}
	if got := absolutizeLinks("://bad", `<a href="/relative">x</a>`); got == "" {
		t.Fatal("invalid base removed HTML")
	}
	if got := absolutizeLinks("https://example.com", `<a href="https://other/x">x</a><a href="%bad">bad</a>`); got == "" {
		t.Fatal("absolute/malformed links removed")
	}
	for _, input := range []string{"", "<div></div>", "<p>text</p><br><strong>x</strong>"} {
		_, _ = (simpleMarkdownConverter{}).Convert(input)
	}
	if _, err := (simpleMarkdownConverter{}).Convert("<div></div>"); err == nil {
		t.Fatal("empty markdown conversion accepted")
	}
	baseProcessor{logger: slog.Default()}.logFailure(content.Content{}, errors.New("failure"))
}

func TestLLMProcessorFallbackAndNormalizationBranches(t *testing.T) {
	if _, err := newLLMKeywordsProcessor(nil, nil); err == nil {
		t.Fatal("nil keyword factory accepted")
	}
	if _, err := newLLMSummaryProcessor(nil, nil); err == nil {
		t.Fatal("nil summary factory accepted")
	}
	if _, err := newLLMTagsProcessor(nil, nil); err == nil {
		t.Fatal("nil tag factory accepted")
	}
	long := strings.Repeat("technology software research. ", 30)
	keywordClient := &fakeLLMClient{err: errors.New("down")}
	keywords, err := newLLMKeywordsProcessor(map[string]any{
		"retry_times": 1, "enable_fallback": true, "keywords_count": 3,
		"exclude_patterns": []any{"software"}, "custom_stop_words": []any{"technology"},
	}, func(BaseLLMProcessorConfig) LLMClient { return keywordClient })
	if err != nil {
		t.Fatal(err)
	}
	items, err := keywords.Process(context.Background(), []content.Content{{Title: "Technology", Content: long}})
	if err != nil || len(items[0].Keywords) == 0 {
		t.Fatalf("keyword fallback = %#v, %v", items, err)
	}
	keywords.config.EnableFallback = false
	keywords.config.FailFast = false
	keywordClient.err = nil
	keywordClient.response = "{"
	if _, err := keywords.Process(context.Background(), []content.Content{{Content: long}}); err != nil {
		t.Fatal(err)
	}
	keywords.config.FailFast = true
	if _, err := keywords.Process(context.Background(), []content.Content{{Content: long}}); err == nil {
		t.Fatal("keyword fail-fast did not return error")
	}
	keywords.config.FailFast = false
	keywords.config.EnableFallback = true
	if _, err := keywords.handleKeywordFailure(content.Content{}, "empty", errors.New("bad")); err == nil {
		t.Fatal("empty keyword fallback unexpectedly succeeded")
	}
	_, _ = keywords.processOne(context.Background(), content.Content{Title: "cache", Content: long})
	_, _ = keywords.processOne(context.Background(), content.Content{Title: "cache", Content: long})
	keywords.client = &fakeLLMClient{response: `{"keywords":["the"]}`}
	keywords.config.EnableFallback = false
	if _, err := keywords.processOne(context.Background(), content.Content{Content: long + " unique"}); err == nil {
		t.Fatal("empty normalized keyword result unexpectedly succeeded")
	}
	keywords.config.EnableFallback = true
	_ = keywords.normalizeKeywords(keywordResult{Keywords: []string{"", strings.Repeat("x", 30), "software"}})
	keywords.config.KeywordsCount = 1
	_ = keywords.fallbackKeywords(content.Content{Title: "aa bb", Content: "aa bb"})
	if got := keywords.normalizeKeywords(keywordResult{
		Keywords:   []string{"  Alpha  ", "the", "Beta", "alpha"},
		Importance: map[string]float64{"Alpha": 0.9, "Beta": 0.8},
	}); len(got.Keywords) == 0 {
		t.Fatal("keyword normalization removed all values")
	}

	tagClient := &fakeLLMClient{err: errors.New("down")}
	tags, err := newLLMTagsProcessor(map[string]any{
		"retry_times": 1, "available_tags": []any{"Go", "AI"},
	}, func(BaseLLMProcessorConfig) LLMClient { return tagClient })
	if err != nil {
		t.Fatal(err)
	}
	tagItems, err := tags.Process(context.Background(), []content.Content{{Title: "Go AI", Content: long}})
	if err != nil || len(tagItems[0].Tags) != 2 {
		t.Fatalf("available tag fallback = %#v, %v", tagItems, err)
	}
	tags.config.AvailableTags = nil
	tagItems, err = tags.Process(context.Background(), []content.Content{{Title: "software research", Content: long}})
	if err != nil || len(tagItems[0].Tags) == 0 {
		t.Fatalf("heuristic fallback = %#v, %v", tagItems, err)
	}
	if tags.fallbackTags(content.Content{Title: "none", Content: "none"})[0] != "general" {
		t.Fatal("general fallback missing")
	}
	tags.config.EnableFallback = false
	tags.config.FailFast = true
	if _, err := tags.Process(context.Background(), []content.Content{{Content: long}}); err == nil {
		t.Fatal("tag fail-fast did not return error")
	}
	tags.config.FailFast = false
	tags.config.EnableFallback = true
	tags.config.AvailableTags = []string{"NoMatch"}
	if _, err := tags.handleTagFailure(content.Content{}, "empty", errors.New("bad")); err == nil {
		t.Fatal("empty tag fallback unexpectedly succeeded")
	}
	tags.config.AvailableTags = nil
	_, _ = tags.processOne(context.Background(), content.Content{Title: "cache", Content: long})
	_, _ = tags.processOne(context.Background(), content.Content{Title: "cache", Content: long})
	_ = tags.normalizeTags(tagResult{Tags: []string{"", strings.Repeat("x", defaultMaxTagLength+1)}})
	tags.client = &fakeLLMClient{response: "{"}
	tags.config.EnableFallback = false
	if _, err := tags.processOne(context.Background(), content.Content{Content: long + " invalid"}); err == nil {
		t.Fatal("invalid tag JSON unexpectedly succeeded")
	}
	tags.client = &fakeLLMClient{response: `{"tags":[]}`}
	if _, err := tags.processOne(context.Background(), content.Content{Content: long + " empty"}); err == nil {
		t.Fatal("empty tag result unexpectedly succeeded")
	}
	tags.client = &fakeLLMClient{err: errors.New("unavailable")}
	tags.config.FailFast = false
	tags.config.EnableFallback = false
	if items, err := tags.Process(context.Background(), []content.Content{{Content: long + " process error"}}); err != nil || len(items) != 1 {
		t.Fatalf("non-fail-fast tag error = %#v, %v", items, err)
	}
	tags.config.MaxTags = 1
	_ = tags.normalizeTags(tagResult{Tags: []string{"one", "two"}})
	tags.config.CustomCategories = map[string][]string{"general": {"one"}}
	_ = tags.categorizeTags([]string{"one", "other"})
	if got := orderedCategoryNames(map[string][]string{"b": nil, "a": nil}, []string{"missing", "a", "a"}); !reflect.DeepEqual(got, []string{"a", "b"}) {
		t.Fatalf("category ordering = %#v", got)
	}
	SetCustomCategoryOrder(tags, []string{"a"})
	SetCustomCategoryOrder(struct{ Processor }{}, []string{"a"})
}

func TestSummaryFallbackStylesAndFailures(t *testing.T) {
	article := "One sentence. Two sentence! Three sentence?"
	for _, style := range []string{"concise", "detailed", "bullet_points", "executive"} {
		active, err := newLLMSummaryProcessor(map[string]any{
			"summary_style": style, "retry_times": 1,
		}, func(BaseLLMProcessorConfig) LLMClient { return &fakeLLMClient{err: errors.New("down")} })
		if err != nil {
			t.Fatal(err)
		}
		items, err := active.Process(context.Background(), []content.Content{{Title: "Title", Content: strings.Repeat(article+" ", 20)}})
		if err != nil || items[0].Summary == "" {
			t.Fatalf("%s fallback = %#v, %v", style, items, err)
		}
	}
	active, err := newLLMSummaryProcessor(map[string]any{
		"retry_times": 1, "enable_fallback": false, "fail_fast": false,
	}, func(BaseLLMProcessorConfig) LLMClient { return &fakeLLMClient{response: "   "} })
	if err != nil {
		t.Fatal(err)
	}
	if _, err := active.Process(context.Background(), []content.Content{{Title: "Title", Content: strings.Repeat("word ", 60)}}); err != nil {
		t.Fatal(err)
	}
	active.config.FailFast = true
	if _, err := active.Process(context.Background(), []content.Content{{Title: "Title", Content: strings.Repeat("word ", 60)}}); err == nil {
		t.Fatal("summary fail-fast did not return error")
	}
	if active.fallbackSummary("", "") != "" {
		t.Fatal("empty fallback summary should be empty")
	}
	unsuitable, err := newLLMSummaryProcessor(map[string]any{"enable_fallback": false}, func(BaseLLMProcessorConfig) LLMClient {
		return &fakeLLMClient{}
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := unsuitable.processOne(context.Background(), content.Content{}); err == nil {
		t.Fatal("unsuitable content accepted")
	}
	withoutFallback, err := newLLMSummaryProcessor(map[string]any{
		"enable_fallback": false, "max_summary_length": 10,
	}, func(BaseLLMProcessorConfig) LLMClient { return &fakeLLMClient{response: "   "} })
	if err != nil {
		t.Fatal(err)
	}
	if _, err := withoutFallback.processOne(context.Background(), content.Content{Content: strings.Repeat("word ", 60)}); err == nil {
		t.Fatal("empty summary response accepted")
	}
	withoutFallback.client = &fakeLLMClient{err: errors.New("unavailable")}
	withoutFallback.config.MaxSummaryLength = 10
	if _, err := withoutFallback.processOne(context.Background(), content.Content{Title: "Title", Content: strings.Repeat("word ", 60)}); err == nil {
		t.Fatal("summary request error accepted")
	}
	withoutFallback.config.MaxSummaryLength = 0
	withoutFallback.client = &fakeLLMClient{response: "word"}
	if _, err := withoutFallback.processOne(context.Background(), content.Content{Content: strings.Repeat("word ", 60)}); err == nil {
		t.Fatal("empty truncated summary accepted")
	}
	withFallback, err := newLLMSummaryProcessor(map[string]any{
		"enable_fallback": true, "max_summary_length": 10,
	}, func(BaseLLMProcessorConfig) LLMClient { return &fakeLLMClient{response: "   "} })
	if err != nil {
		t.Fatal(err)
	}
	if _, err := withFallback.processOne(context.Background(), content.Content{Content: strings.Repeat("word ", 60)}); err != nil {
		t.Fatalf("empty response fallback failed: %v", err)
	}
}

func TestBrowserlessCDPAndRegistryBranches(t *testing.T) {
	renderer := cdpBrowserRenderer{}
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()
	if _, err := renderer.RenderHTML(ctx, "http://127.0.0.1:1", BrowserRenderOptions{
		URL: "https://example.com", UserAgent: "test", TimeoutMs: 20,
	}); err == nil {
		t.Fatal("unavailable Browserless endpoint succeeded")
	}
	if _, err := renderer.RenderHTML(ctx, "http://127.0.0.1:1", BrowserRenderOptions{
		URL: "https://example.com",
	}); err == nil {
		t.Fatal("unavailable Browserless endpoint with default timeout succeeded")
	}
	if err := validatePageURL("%"); err == nil {
		t.Fatal("invalid page URL accepted")
	}
	if err := validatePageURL("http:///missing-host"); err == nil {
		t.Fatal("page URL without host accepted")
	}
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	registry := NewRegistry(WithLogger(logger))
	if registry.logger != logger {
		t.Fatal("logger option was ignored")
	}
	defaultRegistry := NewRegistry()
	if defaultRegistry.llmFactory(BaseLLMProcessorConfig{}) == nil {
		t.Fatal("default LLM factory returned nil")
	}
	if _, err := registry.Create("unknown", nil); err == nil {
		t.Fatal("unknown processor accepted")
	}
}

func TestOpenAIClientOptionalResponseFormat(t *testing.T) {
	client := NewOpenAICompatibleClient(&http.Client{Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
		if req.Header.Get("Authorization") != "" {
			t.Fatal("unexpected auth header")
		}
		return &http.Response{
			StatusCode: http.StatusOK,
			Body:       io.NopCloser(strings.NewReader(`{"choices":[{"message":{"content":"ok"}}]}`)),
			Header:     make(http.Header),
		}, nil
	})}, BaseLLMProcessorConfig{})
	got, err := client.CreateChatCompletion(context.Background(), ChatRequest{
		BaseURL: "https://example.com", Model: "m", Messages: []ChatMessage{{Role: "user", Content: "x"}},
	})
	if err != nil || got != "ok" {
		t.Fatalf("optional response format = %q, %v", got, err)
	}
}

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(req *http.Request) (*http.Response, error) { return f(req) }

func TestProcessorFormattingAndStringHelpers(t *testing.T) {
	if normalizeSpace("  a \n b  ") != "a b" || mixedWordCount("Go 中国") != 3 {
		t.Fatal("text helpers failed")
	}
}
