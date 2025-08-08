"""
Extended tests for text processor utilities.
"""

import os
import sys

import pytest

# Add src to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from octopus_scraper.utils.text_processor import TextProcessor


class TestTextProcessor:
    """Test cases for TextProcessor utility methods."""

    def test_clean_html_basic(self):
        """Test basic HTML cleaning."""
        html_text = "<p>This is a <strong>test</strong> paragraph.</p>"
        result = TextProcessor.clean_html(html_text)
        assert result == "This is a test paragraph."

    def test_clean_html_with_entities(self):
        """Test HTML cleaning with entities."""
        html_text = "<p>Test &amp; example with &quot;quotes&quot; &lt;tags&gt;</p>"
        result = TextProcessor.clean_html(html_text)
        assert result == 'Test & example with "quotes"'

    def test_clean_html_empty(self):
        """Test HTML cleaning with empty input."""
        assert TextProcessor.clean_html("") == ""
        assert TextProcessor.clean_html(None) == ""

    def test_clean_html_complex(self):
        """Test HTML cleaning with complex markup."""
        html_text = """
        <div class="content">
            <h1>Title</h1>
            <p>Paragraph with <a href="#">link</a></p>
            <ul>
                <li>Item 1</li>
                <li>Item 2</li>
            </ul>
        </div>
        """
        result = TextProcessor.clean_html(html_text)
        assert "Title" in result
        assert "Paragraph with link" in result
        assert "Item 1" in result
        assert "Item 2" in result
        assert "<" not in result
        assert ">" not in result

    def test_normalize_whitespace_basic(self):
        """Test whitespace normalization."""
        text = "Text   with    multiple   spaces"
        result = TextProcessor.normalize_whitespace(text)
        assert result == "Text with multiple spaces"

    def test_normalize_whitespace_empty(self):
        """Test whitespace normalization with empty input."""
        assert TextProcessor.normalize_whitespace("") == ""
        assert TextProcessor.normalize_whitespace(None) == ""

    def test_normalize_unicode_basic(self):
        """Test unicode normalization."""
        # Text with composed and decomposed characters
        text = "café naïve résumé"  # These might have different unicode forms
        result = TextProcessor.normalize_unicode(text)

        # Should normalize to consistent form
        assert len(result) > 0
        assert "café" in result or "cafe" in result

    def test_normalize_unicode_empty(self):
        """Test unicode normalization with empty input."""
        assert TextProcessor.normalize_unicode("") == ""
        assert TextProcessor.normalize_unicode(None) == ""

    def test_clean_text_basic(self):
        """Test comprehensive text cleaning."""
        text = "<p>Test &amp; example</p>"
        result = TextProcessor.clean_text(text)

        assert "Test & example" in result
        assert "<" not in result
        assert "&amp;" not in result

    def test_clean_text_empty(self):
        """Test comprehensive text cleaning with empty input."""
        assert TextProcessor.clean_text("") == ""
        assert TextProcessor.clean_text(None) == ""

    def test_clean_text_complex(self):
        """Test comprehensive text cleaning with complex input."""
        text = """
        <div>
            <h1>Title &amp; Subtitle</h1>
            <p>Content with   multiple    spaces</p>
        </div>
        """
        result = TextProcessor.clean_text(text)

        assert "Title & Subtitle" in result
        assert "Content with" in result
        assert "<" not in result
        assert "&amp;" not in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
