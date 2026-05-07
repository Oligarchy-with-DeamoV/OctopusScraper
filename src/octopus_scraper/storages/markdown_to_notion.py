"""Markdown to Notion block converter.

Parses Markdown text into Notion API block structures using mistune v3 AST mode.
"""

from typing import Dict, List, Optional

import mistune
import structlog

logger = structlog.get_logger(__name__)

# Default annotations for rich text segments
_DEFAULT_ANNOTATIONS = {
    "bold": False,
    "italic": False,
    "strikethrough": False,
    "underline": False,
    "code": False,
    "color": "default",
}

# Notion API max length for a single rich text content segment
_MAX_TEXT_LENGTH = 2000

# Notion API max number of rich_text elements per block (paragraph, heading, etc.)
_MAX_RICH_TEXT_PER_BLOCK = 100


class MarkdownToNotionConverter:
    """Converts Markdown text into a list of Notion API block dicts.

    Uses mistune v3 to parse Markdown into an AST, then walks the tree
    to produce Notion-compatible block and rich_text structures.
    """

    def __init__(self):
        self._md = mistune.create_markdown(
            renderer="ast", plugins=["strikethrough", "table"]
        )

    def convert(self, markdown_text: str) -> List[Dict]:
        """Convert Markdown text to a list of Notion API block dicts.

        Args:
            markdown_text: Raw Markdown string. None or whitespace-only returns [].

        Returns:
            List of Notion block dicts ready for the Notion API.
        """
        if not markdown_text or not markdown_text.strip():
            return []

        try:
            tokens = self._md(markdown_text)
        except Exception:
            logger.warning("markdown_parse_failed", text_preview=markdown_text[:100])
            return self._split_rich_text_to_blocks(
                self._make_text_segments(markdown_text), "paragraph"
            )

        blocks = []
        for token in tokens:
            rendered = self._render_block(token)
            if rendered is not None:
                if isinstance(rendered, list):
                    blocks.extend(rendered)
                else:
                    blocks.append(rendered)
        return blocks

    # ---------------------------------------------------------------
    # Block-level rendering
    # ---------------------------------------------------------------

    def _render_block(self, token: Dict) -> Optional[Dict | List[Dict]]:
        """Dispatch a top-level AST token to the appropriate block renderer."""
        token_type = token.get("type", "")
        handler = getattr(self, f"_block_{token_type}", None)
        if handler:
            return handler(token)
        logger.debug("unhandled_block_type", token_type=token_type)
        return None

    def _block_paragraph(self, token: Dict) -> Optional[Dict | List[Dict]]:
        """Render a paragraph block, detecting inline images.

        If the resulting rich_text exceeds the Notion API limit of
        _MAX_RICH_TEXT_PER_BLOCK elements, the paragraph is split into
        multiple consecutive paragraph blocks.

        Note: Dispatched via reflection in ``_render_block`` — when mistune emits
        a token with ``type="paragraph"``, ``getattr(self, "_block_paragraph")`` resolves here.
        """
        children = token.get("children", [])
        # Detect image tokens inside paragraph children
        image_result = self._try_extract_image(children)
        if image_result is not None:
            return image_result

        rich_text = self._render_rich_text(children)
        if not rich_text:
            return None
        blocks = self._split_rich_text_to_blocks(rich_text, "paragraph")
        return blocks if len(blocks) > 1 else blocks[0]

    def _block_heading(self, token: Dict) -> Dict | List[Dict]:
        """Render heading_1, heading_2, or heading_3. Levels 4-6 downgrade to 3.

        If the resulting rich_text exceeds _MAX_RICH_TEXT_PER_BLOCK elements,
        the heading is split into multiple consecutive heading blocks.

        Note: Dispatched via reflection in ``_render_block`` — when mistune emits
        a token with ``type="heading"``, ``getattr(self, "_block_heading")`` resolves here.
        """
        level = token.get("attrs", {}).get("level", 1)
        if level > 3:
            level = 3
        heading_type = f"heading_{level}"
        rich_text = self._render_rich_text(token.get("children", []))
        blocks = self._split_rich_text_to_blocks(rich_text, heading_type)
        return blocks if len(blocks) > 1 else blocks[0]

    def _block_block_code(self, token: Dict) -> Dict:
        """Render a fenced code block.

        Note: Dispatched via reflection in ``_render_block`` — when mistune emits
        a token with ``type="block_code"``, ``getattr(self, "_block_block_code")`` resolves here.
        """
        info = (token.get("attrs", {}).get("info") or "").strip()
        language = info if info else "plain text"
        raw = token.get("raw", "")
        # Strip trailing newline that mistune appends
        if raw.endswith("\n"):
            raw = raw[:-1]
        rich_text = self._make_text_segments(raw)
        return {"type": "code", "code": {"rich_text": rich_text, "language": language}}

    def _block_list(self, token: Dict) -> List[Dict]:
        """Render a list (ordered or unordered) as flat list item blocks.

        If a single list item's rich_text exceeds _MAX_RICH_TEXT_PER_BLOCK,
        it is split into multiple consecutive list item blocks.

        Note: Dispatched via reflection in ``_render_block`` — when mistune emits
        a token with ``type="list"``, ``getattr(self, "_block_list")`` resolves here.
        """
        ordered = token.get("attrs", {}).get("ordered", False)
        block_type = "numbered_list_item" if ordered else "bulleted_list_item"
        blocks = []
        for item in token.get("children", []):
            if item.get("type") == "list_item":
                rich_text = self._extract_list_item_text(item)
                blocks.extend(self._split_rich_text_to_blocks(rich_text, block_type))
        return blocks

    def _block_block_quote(self, token: Dict) -> Dict | List[Dict]:
        """Render a blockquote.

        If the resulting rich_text exceeds _MAX_RICH_TEXT_PER_BLOCK elements,
        the quote is split into multiple consecutive quote blocks.

        Note: Dispatched via reflection in ``_render_block`` — when mistune emits
        a token with ``type="block_quote"``, ``getattr(self, "_block_block_quote")`` resolves here.
        """
        # block_quote children are typically paragraphs
        all_rich_text = []
        for child in token.get("children", []):
            if child.get("type") == "paragraph":
                all_rich_text.extend(self._render_rich_text(child.get("children", [])))
        blocks = self._split_rich_text_to_blocks(all_rich_text, "quote")
        if len(blocks) > 1:
            return blocks
        if blocks:
            return blocks[0]
        return {"type": "quote", "quote": {"rich_text": []}}

    def _block_thematic_break(self, token: Dict) -> Dict:
        """Render a horizontal rule / divider.

        Note: Dispatched via reflection in ``_render_block`` — when mistune emits
        a token with ``type="thematic_break"``, ``getattr(self, "_block_thematic_break")`` resolves here.
        """
        return {"type": "divider", "divider": {}}

    def _block_table(self, token: Dict) -> Dict:
        """Render a table block with table_row children.

        Note: Dispatched via reflection in ``_render_block`` — when mistune emits
        a token with ``type="table"``, ``getattr(self, "_block_table")`` resolves here.
        """
        rows = []
        table_width = 0
        has_header = False

        for child in token.get("children", []):
            if child["type"] == "table_head":
                has_header = True
                cells = self._extract_table_row_cells(child.get("children", []))
                table_width = len(cells)
                rows.append({"type": "table_row", "table_row": {"cells": cells}})
            elif child["type"] == "table_body":
                for row in child.get("children", []):
                    cells = self._extract_table_row_cells(row.get("children", []))
                    if not table_width:
                        table_width = len(cells)
                    rows.append({"type": "table_row", "table_row": {"cells": cells}})

        return {
            "type": "table",
            "table": {
                "table_width": table_width,
                "has_column_header": has_header,
                "children": rows,
            },
        }

    def _block_blank_line(self, token: Dict) -> None:
        """Skip blank lines.

        Note: Dispatched via reflection in ``_render_block`` — when mistune emits
        a token with ``type="blank_line"``, ``getattr(self, "_block_blank_line")`` resolves here.
        """
        return None

    # ---------------------------------------------------------------
    # Inline / rich text rendering
    # ---------------------------------------------------------------

    def _render_rich_text(
        self, children: List[Dict], annotations: Optional[Dict] = None
    ) -> List[Dict]:
        """Recursively render inline AST nodes into Notion rich_text segments.

        Args:
            children: List of inline AST tokens (text, strong, emphasis, etc.).
            annotations: Annotation overrides inherited from parent nodes.

        Returns:
            List of Notion rich_text segment dicts.
        """
        if annotations is None:
            annotations = {}
        segments = []
        for child in children:
            child_type = child.get("type", "")
            if child_type == "text":
                segments.extend(
                    self._make_text_segments(child.get("raw", ""), annotations)
                )
            elif child_type == "strong":
                merged = {**annotations, "bold": True}
                segments.extend(
                    self._render_rich_text(child.get("children", []), merged)
                )
            elif child_type == "emphasis":
                merged = {**annotations, "italic": True}
                segments.extend(
                    self._render_rich_text(child.get("children", []), merged)
                )
            elif child_type == "codespan":
                merged = {**annotations, "code": True}
                segments.extend(self._make_text_segments(child.get("raw", ""), merged))
            elif child_type == "strikethrough":
                merged = {**annotations, "strikethrough": True}
                segments.extend(
                    self._render_rich_text(child.get("children", []), merged)
                )
            elif child_type == "link":
                url = child.get("attrs", {}).get("url", "")
                link_text_parts = self._render_rich_text(
                    child.get("children", []), annotations
                )
                for part in link_text_parts:
                    part["text"]["link"] = {"url": url}
                segments.extend(link_text_parts)
            elif child_type == "softbreak":
                segments.extend(self._make_text_segments("\n", annotations))
            elif child_type == "linebreak":
                segments.extend(self._make_text_segments("\n", annotations))
            elif child_type == "image":
                # Fallback: render alt text if image appears inline
                alt = child.get("alt", child.get("attrs", {}).get("alt", ""))
                if alt:
                    segments.extend(self._make_text_segments(alt, annotations))
            else:
                logger.debug("unhandled_inline_type", inline_type=child_type)
        return segments

    # ---------------------------------------------------------------
    # Image detection for mistune v3 AST
    # ---------------------------------------------------------------

    def _try_extract_image(self, children: List[Dict]) -> Optional[Dict | List[Dict]]:
        """Detect image tokens inside paragraph children.

        Mistune v3 AST renders ![alt](url) as an inline image token
        inside a paragraph. If the paragraph contains only an image,
        return an image block. If mixed with other content, return the
        image block alongside paragraph blocks for the remaining text.
        """
        has_image = any(c.get("type") == "image" for c in children)
        if not has_image:
            return None

        results = []
        remaining_children = []

        for child in children:
            if child.get("type") == "image":
                # Flush any accumulated non-image content as a paragraph
                if remaining_children:
                    rich_text = self._render_rich_text(remaining_children)
                    if rich_text:
                        results.extend(
                            self._split_rich_text_to_blocks(rich_text, "paragraph")
                        )
                    remaining_children = []

                url = child.get("attrs", {}).get("url", "")
                results.append(
                    {
                        "type": "image",
                        "image": {
                            "type": "external",
                            "external": {"url": url},
                        },
                    }
                )
            else:
                remaining_children.append(child)

        # Flush any trailing non-image children
        if remaining_children:
            rich_text = self._render_rich_text(remaining_children)
            if rich_text:
                results.extend(self._split_rich_text_to_blocks(rich_text, "paragraph"))

        return results if len(results) > 1 else results[0] if results else None

    # ---------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------

    def _split_rich_text_to_blocks(
        self, rich_text: List[Dict], block_type: str
    ) -> List[Dict]:
        """Create Notion blocks from rich_text, splitting into multiple if over limit.

        Notion API limits rich_text arrays to _MAX_RICH_TEXT_PER_BLOCK elements per
        block. This method splits the list into chunks and wraps each in a block of
        the given type.

        Args:
            rich_text: List of Notion rich_text segment dicts.
            block_type: The Notion block type string (e.g. ``"paragraph"``, ``"quote"``).

        Returns:
            List of one or more Notion block dicts, each with at most
            _MAX_RICH_TEXT_PER_BLOCK rich_text segments.
        """
        if not rich_text:
            return [{"type": block_type, block_type: {"rich_text": []}}]
        blocks = []
        for i in range(0, len(rich_text), _MAX_RICH_TEXT_PER_BLOCK):
            chunk = rich_text[i : i + _MAX_RICH_TEXT_PER_BLOCK]
            blocks.append({"type": block_type, block_type: {"rich_text": chunk}})
        return blocks

    def _extract_list_item_text(self, item: Dict) -> List[Dict]:
        """Extract rich text from a list_item token."""
        segments = []
        for child in item.get("children", []):
            child_type = child.get("type", "")
            if child_type in ("paragraph", "block_text"):
                segments.extend(self._render_rich_text(child.get("children", [])))
        return segments

    def _extract_table_row_cells(self, cell_nodes: List[Dict]) -> List[List[Dict]]:
        """Extract cells from table_head or table_row children.

        Returns a list of cells, each cell being a list of rich_text segments.
        """
        cells = []
        for cell_node in cell_nodes:
            if cell_node.get("type") == "table_cell":
                cell_rich_text = self._render_rich_text(cell_node.get("children", []))
                cells.append(cell_rich_text)
        return cells

    def _make_text_segments(
        self, text: str, annotations: Optional[Dict] = None
    ) -> List[Dict]:
        """Split text into Notion rich_text segments, respecting the 2000-char limit.

        Args:
            text: Raw text content.
            annotations: Optional annotation overrides.

        Returns:
            List of Notion rich_text segment dicts.
        """
        if not text:
            return []
        segments = []
        for i in range(0, len(text), _MAX_TEXT_LENGTH):
            chunk = text[i : i + _MAX_TEXT_LENGTH]
            segments.append(self._make_text_segment(chunk, annotations))
        return segments

    def _make_text_segment(self, text: str, annotations: Optional[Dict] = None) -> Dict:
        """Create a single Notion rich_text segment dict.

        Args:
            text: Text content (must be <= 2000 chars).
            annotations: Optional annotation overrides.

        Returns:
            A single Notion rich_text segment dict.
        """
        merged_annotations = {**_DEFAULT_ANNOTATIONS, **(annotations or {})}
        return {
            "type": "text",
            "text": {"content": text},
            "annotations": merged_annotations,
        }
