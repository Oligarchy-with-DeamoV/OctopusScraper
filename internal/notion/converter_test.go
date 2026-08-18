package notion

import (
	"strings"
	"testing"
)

func TestMarkdownConverterConvertsSupportedBlocks(t *testing.T) {
	t.Parallel()

	converter := NewMarkdownConverter()
	markdown := strings.Join([]string{
		"# Heading",
		"",
		"Paragraph with **bold**, *italic*, `code`, ~~strike~~, and [link](https://example.com).",
		"",
		"![Alt text](https://example.com/image.png)",
		"",
		"- bullet one",
		"1. number one",
		"",
		"> quoted line",
		"",
		"---",
		"",
		"```go",
		"fmt.Println(\"hello\")",
		"```",
		"",
		"| Name | Value |",
		"| --- | --- |",
		"| one | two |",
	}, "\n")
	blocks := converter.Convert(markdown)
	wantTypes := []string{"heading_1", "paragraph", "image", "bulleted_list_item", "numbered_list_item", "quote", "divider", "code", "table"}
	if len(blocks) != len(wantTypes) {
		t.Fatalf("block count = %d, want %d", len(blocks), len(wantTypes))
	}
	for index, want := range wantTypes {
		if got := blocks[index]["type"]; got != want {
			t.Fatalf("block %d type = %v, want %s", index, got, want)
		}
	}
	paragraph := blocks[1]["paragraph"].(map[string]any)
	richText := paragraph["rich_text"].([]map[string]any)
	assertHasAnnotation(t, richText, "bold", true)
	assertHasAnnotation(t, richText, "italic", true)
	assertHasAnnotation(t, richText, "code", true)
	assertHasAnnotation(t, richText, "strikethrough", true)
	assertHasLink(t, richText, "https://example.com")
	table := blocks[len(blocks)-1]["table"].(map[string]any)
	children := table["children"].([]any)
	if len(children) != 2 {
		t.Fatalf("table rows = %d, want 2", len(children))
	}
}

func TestMarkdownConverterSplitsLongContent(t *testing.T) {
	t.Parallel()

	converter := NewMarkdownConverter()
	longText := strings.Repeat("a", 2100)
	blocks := converter.Convert(longText)
	if len(blocks) != 1 {
		t.Fatalf("long text block count = %d, want 1", len(blocks))
	}
	richText := blocks[0]["paragraph"].(map[string]any)["rich_text"].([]map[string]any)
	if len(richText) != 2 {
		t.Fatalf("long text segments = %d, want 2", len(richText))
	}

	manySegments := strings.TrimSpace(strings.Repeat("**x** ", 101))
	blocks = converter.Convert(manySegments)
	if len(blocks) < 2 {
		t.Fatalf("segment-split block count = %d, want at least 2", len(blocks))
	}
	for _, block := range blocks {
		items := block["paragraph"].(map[string]any)["rich_text"].([]map[string]any)
		if len(items) > maxRichTextItems {
			t.Fatalf("rich_text items = %d, want <= %d", len(items), maxRichTextItems)
		}
	}
}

func assertHasAnnotation(t *testing.T, richText []map[string]any, key string, want bool) {
	t.Helper()
	for _, item := range richText {
		annotations := item["annotations"].(map[string]any)
		if got, ok := annotations[key].(bool); ok && got == want {
			return
		}
	}
	t.Fatalf("annotation %s=%v not found", key, want)
}

func assertHasLink(t *testing.T, richText []map[string]any, want string) {
	t.Helper()
	for _, item := range richText {
		textValue := item["text"].(map[string]any)
		link, ok := textValue["link"].(map[string]any)
		if ok && link["url"] == want {
			return
		}
	}
	t.Fatalf("link %q not found", want)
}
