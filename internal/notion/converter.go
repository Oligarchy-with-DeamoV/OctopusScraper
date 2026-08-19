package notion

import (
	"fmt"
	"strings"
)

type Block map[string]any

type annotations struct {
	Bold          bool   `json:"bold"`
	Italic        bool   `json:"italic"`
	Strikethrough bool   `json:"strikethrough"`
	Underline     bool   `json:"underline"`
	Code          bool   `json:"code"`
	Color         string `json:"color"`
}

type MarkdownConverter struct{}

func NewMarkdownConverter() *MarkdownConverter {
	return &MarkdownConverter{}
}

func (c *MarkdownConverter) Convert(markdown string) []Block {
	if strings.TrimSpace(markdown) == "" {
		return nil
	}
	lines := strings.Split(strings.ReplaceAll(strings.ReplaceAll(markdown, "\r\n", "\n"), "\r", "\n"), "\n")
	blocks := make([]Block, 0, len(lines))
	for index := 0; index < len(lines); {
		line := lines[index]
		trimmed := strings.TrimSpace(line)
		if trimmed == "" {
			index++
			continue
		}
		if fence, language, ok := parseFenceStart(trimmed); ok {
			index++
			body := make([]string, 0)
			for index < len(lines) {
				candidate := strings.TrimSpace(lines[index])
				if strings.HasPrefix(candidate, fence) {
					index++
					break
				}
				body = append(body, lines[index])
				index++
			}
			blocks = append(blocks, c.makeCodeBlocks(strings.Join(body, "\n"), language)...)
			continue
		}
		if matches := headingPattern.FindStringSubmatch(line); len(matches) == 3 {
			level := len(matches[1])
			if level > 3 {
				level = 3
			}
			blocks = append(blocks, c.makeRichTextBlocks(fmt.Sprintf("heading_%d", level), c.renderInline(strings.TrimSpace(matches[2]), defaultAnnotations()))...)
			index++
			continue
		}
		if dividerPattern.MatchString(line) {
			blocks = append(blocks, Block{"object": "block", "type": "divider", "divider": map[string]any{}})
			index++
			continue
		}
		if c.isTableStart(lines, index) {
			tableLines := make([]string, 0)
			for index < len(lines) && strings.Contains(lines[index], "|") && strings.TrimSpace(lines[index]) != "" {
				tableLines = append(tableLines, lines[index])
				index++
			}
			if block := c.makeTableBlock(tableLines); block != nil {
				blocks = append(blocks, block)
			}
			continue
		}
		if unorderedListPattern.MatchString(line) || orderedListPattern.MatchString(line) {
			ordered := orderedListPattern.MatchString(line)
			blockType := "bulleted_list_item"
			if ordered {
				blockType = "numbered_list_item"
			}
			for index < len(lines) {
				current := lines[index]
				var itemText string
				if ordered {
					matches := orderedListPattern.FindStringSubmatch(current)
					if len(matches) != 2 {
						break
					}
					itemText = matches[1]
				} else {
					matches := unorderedListPattern.FindStringSubmatch(current)
					if len(matches) != 2 {
						break
					}
					itemText = matches[1]
				}
				blocks = append(blocks, c.makeRichTextBlocks(blockType, c.renderInline(strings.TrimSpace(itemText), defaultAnnotations()))...)
				index++
			}
			continue
		}
		if blockquotePattern.MatchString(line) {
			parts := make([]string, 0)
			for index < len(lines) {
				matches := blockquotePattern.FindStringSubmatch(lines[index])
				if len(matches) != 2 {
					break
				}
				parts = append(parts, matches[1])
				index++
			}
			blocks = append(blocks, c.makeRichTextBlocks("quote", c.renderInline(strings.Join(parts, "\n"), defaultAnnotations()))...)
			continue
		}

		paragraphLines := make([]string, 0)
		for index < len(lines) {
			candidate := lines[index]
			if strings.TrimSpace(candidate) == "" || c.isBlockBoundary(lines, index) {
				break
			}
			paragraphLines = append(paragraphLines, strings.TrimRight(candidate, " "))
			index++
		}
		blocks = append(blocks, c.makeParagraphBlocks(strings.Join(paragraphLines, "\n"))...)
	}
	return blocks
}

func (c *MarkdownConverter) isTableStart(lines []string, index int) bool {
	if index+1 >= len(lines) {
		return false
	}
	return strings.Contains(lines[index], "|") && tableSeparatorPattern.MatchString(lines[index+1])
}

func (c *MarkdownConverter) isBlockBoundary(lines []string, index int) bool {
	line := strings.TrimSpace(lines[index])
	if line == "" {
		return true
	}
	if _, _, ok := parseFenceStart(line); ok {
		return true
	}
	if headingPattern.MatchString(line) || dividerPattern.MatchString(line) || blockquotePattern.MatchString(line) {
		return true
	}
	if unorderedListPattern.MatchString(line) || orderedListPattern.MatchString(line) {
		return true
	}
	if c.isTableStart(lines, index) {
		return true
	}
	return false
}

func parseFenceStart(line string) (string, string, bool) {
	if strings.HasPrefix(line, "```") {
		return "```", strings.TrimSpace(strings.TrimPrefix(line, "```")), true
	}
	if strings.HasPrefix(line, "~~~") {
		return "~~~", strings.TrimSpace(strings.TrimPrefix(line, "~~~")), true
	}
	return "", "", false
}

func (c *MarkdownConverter) makeParagraphBlocks(text string) []Block {
	matches := imagePattern.FindAllStringSubmatchIndex(text, -1)
	if len(matches) == 0 {
		return c.makeRichTextBlocks("paragraph", c.renderInline(strings.TrimSpace(text), defaultAnnotations()))
	}
	blocks := make([]Block, 0, len(matches)*2+1)
	last := 0
	for _, match := range matches {
		before := strings.TrimSpace(text[last:match[0]])
		if before != "" {
			blocks = append(blocks, c.makeRichTextBlocks("paragraph", c.renderInline(before, defaultAnnotations()))...)
		}
		alt := text[match[2]:match[3]]
		rawURL := text[match[4]:match[5]]
		if url := sanitizeURL(rawURL); url != nil {
			blocks = append(blocks, Block{
				"object": "block",
				"type":   "image",
				"image": map[string]any{
					"type": "external",
					"external": map[string]any{
						"url": *url,
					},
					"caption": c.renderInline(strings.TrimSpace(alt), defaultAnnotations()),
				},
			})
		} else if strings.TrimSpace(alt) != "" {
			blocks = append(blocks, c.makeRichTextBlocks("paragraph", c.renderInline(strings.TrimSpace(alt), defaultAnnotations()))...)
		}
		last = match[1]
	}
	after := strings.TrimSpace(text[last:])
	if after != "" {
		blocks = append(blocks, c.makeRichTextBlocks("paragraph", c.renderInline(after, defaultAnnotations()))...)
	}
	return blocks
}

func (c *MarkdownConverter) makeCodeBlocks(text string, language string) []Block {
	if language == "" {
		language = "plain text"
	}
	richText := splitTextToRichText(text, defaultAnnotations(), nil)
	blocks := make([]Block, 0, (len(richText)/maxRichTextItems)+1)
	if len(richText) == 0 {
		return []Block{{"object": "block", "type": "code", "code": map[string]any{"language": language, "rich_text": []any{}}}}
	}
	for start := 0; start < len(richText); start += maxRichTextItems {
		end := start + maxRichTextItems
		if end > len(richText) {
			end = len(richText)
		}
		blocks = append(blocks, Block{
			"object": "block",
			"type":   "code",
			"code": map[string]any{
				"language":  language,
				"rich_text": richText[start:end],
			},
		})
	}
	return blocks
}

func (c *MarkdownConverter) makeTableBlock(lines []string) Block {
	if len(lines) < 2 {
		return nil
	}
	rows := make([]any, 0, len(lines)-1)
	header := splitTableRow(lines[0])
	if len(header) == 0 {
		return nil
	}
	rows = append(rows, makeTableRow(header, c))
	for _, line := range lines[2:] {
		cells := splitTableRow(line)
		if len(cells) == 0 {
			continue
		}
		for len(cells) < len(header) {
			cells = append(cells, "")
		}
		if len(cells) > len(header) {
			cells = cells[:len(header)]
		}
		rows = append(rows, makeTableRow(cells, c))
	}
	return Block{
		"object": "block",
		"type":   "table",
		"table": map[string]any{
			"table_width":       len(header),
			"has_column_header": true,
			"has_row_header":    false,
			"children":          rows,
		},
	}
}

func makeTableRow(cells []string, c *MarkdownConverter) Block {
	cellValues := make([]any, 0, len(cells))
	for _, cell := range cells {
		richText := c.renderInline(strings.TrimSpace(cell), defaultAnnotations())
		if len(richText) > maxRichTextItems {
			richText = richText[:maxRichTextItems]
		}
		cellValues = append(cellValues, richText)
	}
	return Block{
		"object": "block",
		"type":   "table_row",
		"table_row": map[string]any{
			"cells": cellValues,
		},
	}
}

func splitTableRow(line string) []string {
	trimmed := strings.TrimSpace(line)
	trimmed = strings.TrimPrefix(trimmed, "|")
	trimmed = strings.TrimSuffix(trimmed, "|")
	parts := strings.Split(trimmed, "|")
	for index := range parts {
		parts[index] = strings.TrimSpace(parts[index])
	}
	return parts
}

func (c *MarkdownConverter) makeRichTextBlocks(blockType string, richText []map[string]any) []Block {
	if len(richText) == 0 {
		return nil
	}
	blocks := make([]Block, 0, (len(richText)/maxRichTextItems)+1)
	for start := 0; start < len(richText); start += maxRichTextItems {
		end := start + maxRichTextItems
		if end > len(richText) {
			end = len(richText)
		}
		blocks = append(blocks, Block{
			"object": "block",
			"type":   blockType,
			blockType: map[string]any{
				"rich_text": richText[start:end],
			},
		})
	}
	return blocks
}

func (c *MarkdownConverter) renderInline(text string, ann annotations) []map[string]any {
	segments := make([]map[string]any, 0)
	for len(text) > 0 {
		switch {
		case strings.HasPrefix(text, "**") || strings.HasPrefix(text, "__"):
			delimiter := text[:2]
			if end := strings.Index(text[2:], delimiter); end >= 0 {
				inner := text[2 : 2+end]
				next := ann
				next.Bold = true
				segments = append(segments, c.renderInline(inner, next)...)
				text = text[2+end+2:]
				continue
			}
		case strings.HasPrefix(text, "~~"):
			if end := strings.Index(text[2:], "~~"); end >= 0 {
				inner := text[2 : 2+end]
				next := ann
				next.Strikethrough = true
				segments = append(segments, c.renderInline(inner, next)...)
				text = text[2+end+2:]
				continue
			}
		case strings.HasPrefix(text, "`"):
			if end := strings.Index(text[1:], "`"); end >= 0 {
				inner := text[1 : 1+end]
				next := ann
				next.Code = true
				segments = append(segments, splitTextToRichText(inner, next, nil)...)
				text = text[1+end+1:]
				continue
			}
		case strings.HasPrefix(text, "["):
			if closeBracket := strings.Index(text, "]("); closeBracket > 0 {
				if closeParen := strings.Index(text[closeBracket+2:], ")"); closeParen >= 0 {
					label := text[1:closeBracket]
					rawURL := text[closeBracket+2 : closeBracket+2+closeParen]
					segments = append(segments, applyLink(c.renderInline(label, ann), sanitizeURL(rawURL))...)
					text = text[closeBracket+2+closeParen+1:]
					continue
				}
			}
		case strings.HasPrefix(text, "*") || strings.HasPrefix(text, "_"):
			delimiter := text[:1]
			if end := strings.Index(text[1:], delimiter); end >= 0 {
				inner := text[1 : 1+end]
				next := ann
				next.Italic = true
				segments = append(segments, c.renderInline(inner, next)...)
				text = text[1+end+1:]
				continue
			}
		}
		nextSpecial := strings.IndexAny(text, inlineSpecialCharacters)
		if nextSpecial == -1 {
			nextSpecial = len(text)
		}
		if nextSpecial == 0 {
			nextSpecial = 1
		}
		segments = append(segments, splitTextToRichText(text[:nextSpecial], ann, nil)...)
		text = text[nextSpecial:]
	}
	return segments
}

func applyLink(richText []map[string]any, link *string) []map[string]any {
	if link == nil {
		return richText
	}
	for _, item := range richText {
		textValue, ok := item["text"].(map[string]any)
		if !ok {
			continue
		}
		textValue["link"] = map[string]any{"url": *link}
	}
	return richText
}

func splitTextToRichText(text string, ann annotations, link *string) []map[string]any {
	if text == "" {
		return []map[string]any{}
	}
	richText := make([]map[string]any, 0, len(text)/maxTextLength+1)
	for len(text) > 0 {
		runes := []rune(text)
		chunkLen := len(runes)
		if chunkLen > maxTextLength {
			chunkLen = maxTextLength
		}
		chunk := string(runes[:chunkLen])
		text = string(runes[chunkLen:])
		entry := map[string]any{
			"type": "text",
			"text": map[string]any{
				"content": chunk,
			},
			"annotations": ann.toMap(),
		}
		if link != nil {
			entry["text"].(map[string]any)["link"] = map[string]any{"url": *link}
		}
		richText = append(richText, entry)
	}
	return richText
}

func defaultAnnotations() annotations {
	return annotations{Color: "default"}
}

func (a annotations) toMap() map[string]any {
	return map[string]any{
		"bold":          a.Bold,
		"italic":        a.Italic,
		"strikethrough": a.Strikethrough,
		"underline":     a.Underline,
		"code":          a.Code,
		"color":         "default",
	}
}
