package processor

import (
	"context"
	"strings"
	"testing"
)

func TestCDPBrowserRendererValidatesURLs(t *testing.T) {
	renderer := cdpBrowserRenderer{}
	tests := []struct {
		endpoint string
		pageURL  string
	}{
		{"", "https://example.com"},
		{"file:///tmp/browser", "https://example.com"},
		{"http://browserless:3000", ""},
		{"http://browserless:3000", "file:///etc/passwd"},
	}
	for _, test := range tests {
		_, err := renderer.RenderHTML(
			context.Background(),
			test.endpoint,
			BrowserRenderOptions{URL: test.pageURL},
		)
		if err == nil {
			t.Fatalf("RenderHTML(%q, %q) succeeded", test.endpoint, test.pageURL)
		}
	}
	if err := validateBrowserEndpoint("wss://browserless.example"); err != nil {
		t.Fatal(err)
	}
	if err := validatePageURL("https://example.com"); err != nil {
		t.Fatal(err)
	}
}

func TestReadBoundedBody(t *testing.T) {
	body, err := readBoundedBody(strings.NewReader("okay"), 4)
	if err != nil || string(body) != "okay" {
		t.Fatalf("unexpected body: %q, %v", body, err)
	}
	if _, err := readBoundedBody(strings.NewReader("large"), 4); err == nil {
		t.Fatal("expected oversized body error")
	}
}
