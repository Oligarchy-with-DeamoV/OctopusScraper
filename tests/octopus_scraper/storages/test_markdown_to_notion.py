import pytest

from octopus_scraper.storages.markdown_to_notion import MarkdownToNotionConverter


@pytest.fixture
def converter():
    return MarkdownToNotionConverter()


class TestRichTextRendering:
    """Tests for inline formatting within paragraph blocks."""

    def test_plain_text(self, converter):
        blocks = converter.convert("Hello world")
        assert len(blocks) == 1
        block = blocks[0]
        assert block["type"] == "paragraph"
        rich_text = block["paragraph"]["rich_text"]
        assert len(rich_text) == 1
        assert rich_text[0]["type"] == "text"
        assert rich_text[0]["text"]["content"] == "Hello world"
        # Plain text should have no special annotations
        assert rich_text[0]["annotations"]["bold"] is False
        assert rich_text[0]["annotations"]["italic"] is False
        assert rich_text[0]["annotations"]["code"] is False

    def test_bold_text(self, converter):
        blocks = converter.convert("Hello **bold** world")
        assert len(blocks) == 1
        rich_text = blocks[0]["paragraph"]["rich_text"]
        # Should have 3 segments: "Hello ", "bold", " world"
        assert len(rich_text) == 3
        assert rich_text[0]["text"]["content"] == "Hello "
        assert rich_text[0]["annotations"]["bold"] is False
        assert rich_text[1]["text"]["content"] == "bold"
        assert rich_text[1]["annotations"]["bold"] is True
        assert rich_text[2]["text"]["content"] == " world"
        assert rich_text[2]["annotations"]["bold"] is False

    def test_italic_text(self, converter):
        blocks = converter.convert("Hello *italic* world")
        assert len(blocks) == 1
        rich_text = blocks[0]["paragraph"]["rich_text"]
        assert len(rich_text) == 3
        assert rich_text[1]["text"]["content"] == "italic"
        assert rich_text[1]["annotations"]["italic"] is True

    def test_inline_code(self, converter):
        blocks = converter.convert("Use `print()` here")
        assert len(blocks) == 1
        block = blocks[0]
        assert block["type"] == "paragraph"
        rich_text = block["paragraph"]["rich_text"]
        assert len(rich_text) == 3
        assert rich_text[1]["text"]["content"] == "print()"
        assert rich_text[1]["annotations"]["code"] is True

    def test_inline_link(self, converter):
        blocks = converter.convert("Visit [Example](https://example.com) now")
        assert len(blocks) == 1
        block = blocks[0]
        # Must be a paragraph, NOT a bookmark block
        assert block["type"] == "paragraph"
        rich_text = block["paragraph"]["rich_text"]
        # Find the link segment
        link_segments = [seg for seg in rich_text if seg["text"].get("link")]
        assert len(link_segments) == 1
        assert link_segments[0]["text"]["content"] == "Example"
        assert link_segments[0]["text"]["link"]["url"] == "https://example.com"

    def test_bold_italic_combined(self, converter):
        blocks = converter.convert("This is ***bold italic*** text")
        assert len(blocks) == 1
        rich_text = blocks[0]["paragraph"]["rich_text"]
        # Find the bold+italic segment
        bold_italic = [
            seg
            for seg in rich_text
            if seg["annotations"]["bold"] and seg["annotations"]["italic"]
        ]
        assert len(bold_italic) == 1
        assert bold_italic[0]["text"]["content"] == "bold italic"

    def test_strikethrough(self, converter):
        blocks = converter.convert("This is ~~deleted~~ text")
        assert len(blocks) == 1
        rich_text = blocks[0]["paragraph"]["rich_text"]
        strikethrough_segments = [
            seg for seg in rich_text if seg["annotations"]["strikethrough"]
        ]
        assert len(strikethrough_segments) == 1
        assert strikethrough_segments[0]["text"]["content"] == "deleted"


class TestBlockRendering:
    """Tests for block-level rendering."""

    def test_heading_levels(self, converter):
        blocks = converter.convert("# Heading 1\n\n## Heading 2\n\n### Heading 3")
        heading_blocks = [b for b in blocks if b["type"].startswith("heading_")]
        assert len(heading_blocks) == 3
        assert heading_blocks[0]["type"] == "heading_1"
        assert (
            heading_blocks[0]["heading_1"]["rich_text"][0]["text"]["content"]
            == "Heading 1"
        )
        assert heading_blocks[1]["type"] == "heading_2"
        assert (
            heading_blocks[1]["heading_2"]["rich_text"][0]["text"]["content"]
            == "Heading 2"
        )
        assert heading_blocks[2]["type"] == "heading_3"
        assert (
            heading_blocks[2]["heading_3"]["rich_text"][0]["text"]["content"]
            == "Heading 3"
        )

    def test_heading_4_5_6_downgrade_to_3(self, converter):
        blocks = converter.convert("#### H4\n\n##### H5\n\n###### H6")
        heading_blocks = [b for b in blocks if b["type"].startswith("heading_")]
        assert len(heading_blocks) == 3
        for block in heading_blocks:
            assert block["type"] == "heading_3"

    def test_code_block_with_language(self, converter):
        blocks = converter.convert("```python\nprint('hello')\n```")
        code_blocks = [b for b in blocks if b["type"] == "code"]
        assert len(code_blocks) == 1
        code_block = code_blocks[0]
        assert code_block["code"]["language"] == "python"
        assert "print('hello')" in code_block["code"]["rich_text"][0]["text"]["content"]

    def test_code_block_without_language(self, converter):
        blocks = converter.convert("```\nsome code\n```")
        code_blocks = [b for b in blocks if b["type"] == "code"]
        assert len(code_blocks) == 1
        assert code_blocks[0]["code"]["language"] == "plain text"

    def test_code_block_hyphenated_language(self, converter):
        blocks = converter.convert(
            "```objective-c\n#import <Foundation/Foundation.h>\n```"
        )
        code_blocks = [b for b in blocks if b["type"] == "code"]
        assert len(code_blocks) == 1
        assert code_blocks[0]["code"]["language"] == "objective-c"

    def test_bulleted_list(self, converter):
        blocks = converter.convert("- Item 1\n- Item 2\n- Item 3")
        list_blocks = [b for b in blocks if b["type"] == "bulleted_list_item"]
        assert len(list_blocks) == 3
        assert (
            list_blocks[0]["bulleted_list_item"]["rich_text"][0]["text"]["content"]
            == "Item 1"
        )
        assert (
            list_blocks[1]["bulleted_list_item"]["rich_text"][0]["text"]["content"]
            == "Item 2"
        )
        assert (
            list_blocks[2]["bulleted_list_item"]["rich_text"][0]["text"]["content"]
            == "Item 3"
        )

    def test_ordered_list(self, converter):
        blocks = converter.convert("1. First\n2. Second\n3. Third")
        list_blocks = [b for b in blocks if b["type"] == "numbered_list_item"]
        assert len(list_blocks) == 3
        assert (
            list_blocks[0]["numbered_list_item"]["rich_text"][0]["text"]["content"]
            == "First"
        )
        assert (
            list_blocks[1]["numbered_list_item"]["rich_text"][0]["text"]["content"]
            == "Second"
        )
        assert (
            list_blocks[2]["numbered_list_item"]["rich_text"][0]["text"]["content"]
            == "Third"
        )

    def test_blockquote(self, converter):
        blocks = converter.convert("> This is a quote")
        quote_blocks = [b for b in blocks if b["type"] == "quote"]
        assert len(quote_blocks) == 1
        assert (
            quote_blocks[0]["quote"]["rich_text"][0]["text"]["content"]
            == "This is a quote"
        )

    def test_thematic_break(self, converter):
        blocks = converter.convert("Above\n\n---\n\nBelow")
        divider_blocks = [b for b in blocks if b["type"] == "divider"]
        assert len(divider_blocks) == 1
        assert divider_blocks[0] == {"type": "divider", "divider": {}}

    def test_table(self, converter):
        blocks = converter.convert("| H1 | H2 |\n|---|---|\n| A | B |")
        table_blocks = [b for b in blocks if b["type"] == "table"]
        assert len(table_blocks) == 1
        table = table_blocks[0]
        assert table["table"]["table_width"] == 2
        assert table["table"]["has_column_header"] is True
        rows = table["table"]["children"]
        assert len(rows) == 2  # header row + 1 data row
        # Check header row
        header_row = rows[0]
        assert header_row["type"] == "table_row"
        header_cells = header_row["table_row"]["cells"]
        assert header_cells[0][0]["text"]["content"] == "H1"
        assert header_cells[1][0]["text"]["content"] == "H2"
        # Check data row
        data_row = rows[1]
        data_cells = data_row["table_row"]["cells"]
        assert data_cells[0][0]["text"]["content"] == "A"
        assert data_cells[1][0]["text"]["content"] == "B"

    def test_image(self, converter):
        blocks = converter.convert("![Alt text](https://example.com/image.png)")
        image_blocks = [b for b in blocks if b["type"] == "image"]
        assert len(image_blocks) == 1
        image = image_blocks[0]
        assert image["image"]["type"] == "external"
        assert image["image"]["external"]["url"] == "https://example.com/image.png"

    def test_inline_code_not_code_block(self, converter):
        blocks = converter.convert("Use `print()` here")
        # Must produce a paragraph, NOT a code block
        assert len(blocks) == 1
        assert blocks[0]["type"] == "paragraph"
        code_blocks = [b for b in blocks if b["type"] == "code"]
        assert len(code_blocks) == 0
        # Verify it has code annotation
        rich_text = blocks[0]["paragraph"]["rich_text"]
        code_segments = [seg for seg in rich_text if seg["annotations"]["code"]]
        assert len(code_segments) == 1

    def test_empty_input(self, converter):
        assert converter.convert("") == []
        assert converter.convert("   ") == []
        assert converter.convert(None) == []

    def test_mixed_content(self, converter):
        md = """# Project Title

This is a paragraph with **bold** text.

- Item 1
- Item 2

```python
def hello():
    pass
```

> A quote here
"""
        blocks = converter.convert(md)
        block_types = [b["type"] for b in blocks]
        assert "heading_1" in block_types
        assert "paragraph" in block_types
        assert "bulleted_list_item" in block_types
        assert "code" in block_types
        assert "quote" in block_types


class TestRichTextLengthLimit:
    """Tests for Notion API rich_text array length limit (max 100 per block)."""

    def test_paragraph_with_exactly_100_segments_stays_single_block(self, converter):
        # A paragraph whose inline tokens produce exactly 100 rich_text segments
        # should not be split.
        # Build 100 link segments: "[n](https://example.com/n)" separated by spaces.
        # Each link produces 1 segment; spaces are additional text segments,
        # so construct exactly 100 text-only segments instead.
        # Use 100 separate bold words wrapped in a single paragraph token by
        # injecting the result directly through the internal helper.
        from octopus_scraper.storages.markdown_to_notion import _MAX_RICH_TEXT_PER_BLOCK

        segments = [
            {"type": "text", "text": {"content": f"word{i} "}, "annotations": {}}
            for i in range(_MAX_RICH_TEXT_PER_BLOCK)
        ]
        blocks = converter._split_rich_text_to_blocks(segments, "paragraph")
        assert len(blocks) == 1
        assert blocks[0]["type"] == "paragraph"
        assert len(blocks[0]["paragraph"]["rich_text"]) == _MAX_RICH_TEXT_PER_BLOCK

    def test_paragraph_with_101_segments_splits_into_two_blocks(self, converter):
        from octopus_scraper.storages.markdown_to_notion import _MAX_RICH_TEXT_PER_BLOCK

        segments = [
            {"type": "text", "text": {"content": f"w{i}"}, "annotations": {}}
            for i in range(_MAX_RICH_TEXT_PER_BLOCK + 1)
        ]
        blocks = converter._split_rich_text_to_blocks(segments, "paragraph")
        assert len(blocks) == 2
        assert all(b["type"] == "paragraph" for b in blocks)
        assert len(blocks[0]["paragraph"]["rich_text"]) == _MAX_RICH_TEXT_PER_BLOCK
        assert len(blocks[1]["paragraph"]["rich_text"]) == 1

    def test_paragraph_with_many_links_does_not_exceed_limit(self, converter):
        # Build a markdown paragraph with 150 links – each link yields 1 rich_text
        # segment, so the total would be 150 without splitting.
        links = " ".join(f"[L{i}](https://example.com/{i})" for i in range(150))
        blocks = converter.convert(links)
        # All generated blocks must be paragraphs (no other types expected)
        paragraph_blocks = [b for b in blocks if b["type"] == "paragraph"]
        assert len(paragraph_blocks) >= 2, "Expected the content to be split into multiple paragraphs"
        # Every paragraph block must have ≤ 100 rich_text segments
        for block in paragraph_blocks:
            assert len(block["paragraph"]["rich_text"]) <= 100

    def test_quote_with_many_segments_splits(self, converter):
        from octopus_scraper.storages.markdown_to_notion import _MAX_RICH_TEXT_PER_BLOCK

        segments = [
            {"type": "text", "text": {"content": f"q{i}"}, "annotations": {}}
            for i in range(_MAX_RICH_TEXT_PER_BLOCK + 5)
        ]
        blocks = converter._split_rich_text_to_blocks(segments, "quote")
        assert len(blocks) == 2
        assert all(b["type"] == "quote" for b in blocks)
        assert len(blocks[0]["quote"]["rich_text"]) == _MAX_RICH_TEXT_PER_BLOCK
        assert len(blocks[1]["quote"]["rich_text"]) == 5

    def test_numbered_list_item_with_many_segments_splits(self, converter):
        """Regression test: numbered_list_item rich_text must not exceed 100 elements.

        Previously, _block_list did not call _split_rich_text_to_blocks, causing
        Notion API validation_error when a single list item had >100 rich_text segments.
        See: body.children[N].numbered_list_item.rich_text.length should be ≤ 100
        """
        # Build markdown with a single list item containing 130 links
        links = " ".join(f"[L{i}](https://example.com/{i})" for i in range(130))
        md = f"1. {links}\n"
        blocks = converter.convert(md)
        list_blocks = [b for b in blocks if b["type"] == "numbered_list_item"]
        assert len(list_blocks) >= 2, "Expected the list item to be split into multiple blocks"
        for block in list_blocks:
            assert len(block["numbered_list_item"]["rich_text"]) <= 100

    def test_bulleted_list_item_with_many_segments_splits(self, converter):
        """Bulleted list items should also split when rich_text exceeds limit."""
        links = " ".join(f"[L{i}](https://example.com/{i})" for i in range(130))
        md = f"- {links}\n"
        blocks = converter.convert(md)
        list_blocks = [b for b in blocks if b["type"] == "bulleted_list_item"]
        assert len(list_blocks) >= 2, "Expected the list item to be split into multiple blocks"
        for block in list_blocks:
            assert len(block["bulleted_list_item"]["rich_text"]) <= 100

    def test_empty_rich_text_produces_single_empty_block(self, converter):
        blocks = converter._split_rich_text_to_blocks([], "paragraph")
        assert len(blocks) == 1
        assert blocks[0]["paragraph"]["rich_text"] == []
