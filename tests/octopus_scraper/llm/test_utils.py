"""Tests for LLMUtils utility class."""

import pytest

from octopus_scraper.llm.utils import LLMUtils


class TestCleanText:
    def test_empty_string(self):
        assert LLMUtils.clean_text("") == ""

    def test_none_like_falsy(self):
        assert LLMUtils.clean_text("") == ""

    def test_removes_excessive_whitespace(self):
        assert LLMUtils.clean_text("hello   world") == "hello world"

    def test_removes_control_characters(self):
        assert LLMUtils.clean_text("hello\x00world\x07test") == "helloworldtest"

    def test_preserves_newline_as_space(self):
        result = LLMUtils.clean_text("line1\n\nline2")
        assert result == "line1 line2"

    def test_strips_whitespace(self):
        assert LLMUtils.clean_text("  hello  ") == "hello"

    def test_normal_text_unchanged(self):
        assert LLMUtils.clean_text("hello world") == "hello world"


class TestTruncateText:
    def test_short_text_unchanged(self):
        text = "short"
        assert LLMUtils.truncate_text(text) == text

    def test_truncates_at_sentence_boundary(self):
        text = "First sentence. Second sentence. Third sentence."
        result = LLMUtils.truncate_text(text, max_tokens=5, chars_per_token=4)
        # max_chars = 20, should keep sentences that fit
        assert len(result) <= 20
        assert "First sentence" in result

    def test_truncates_long_single_sentence(self):
        text = "A" * 200
        result = LLMUtils.truncate_text(text, max_tokens=10, chars_per_token=4)
        assert len(result) == 40

    def test_exact_boundary(self):
        text = "A" * 12000
        result = LLMUtils.truncate_text(text, max_tokens=3000, chars_per_token=4)
        assert len(result) == 12000  # exactly at limit

    def test_custom_chars_per_token(self):
        text = "A" * 100
        result = LLMUtils.truncate_text(text, max_tokens=10, chars_per_token=2)
        assert len(result) == 20


class TestExtractJsonBlocks:
    def test_json_in_code_block(self):
        text = '```json\n{"key": "value"}\n```'
        result = LLMUtils.extract_json_blocks(text)
        assert result == [{"key": "value"}]

    def test_json_in_generic_code_block(self):
        text = '```\n{"key": "value"}\n```'
        result = LLMUtils.extract_json_blocks(text)
        assert len(result) >= 1
        assert {"key": "value"} in result

    def test_standalone_json_object(self):
        text = 'Some text {"key": "value"} more text'
        result = LLMUtils.extract_json_blocks(text)
        assert {"key": "value"} in result

    def test_invalid_json_skipped(self):
        text = '```json\n{invalid json}\n```'
        result = LLMUtils.extract_json_blocks(text)
        assert result == []

    def test_multiple_json_blocks(self):
        text = '```json\n{"a": 1}\n```\n```json\n{"b": 2}\n```'
        result = LLMUtils.extract_json_blocks(text)
        assert {"a": 1} in result
        assert {"b": 2} in result

    def test_no_json(self):
        text = "No JSON here at all"
        result = LLMUtils.extract_json_blocks(text)
        assert result == []

    def test_no_duplicates(self):
        text = '```json\n{"key": "value"}\n```\nAlso {"key": "value"} inline'
        result = LLMUtils.extract_json_blocks(text)
        assert result.count({"key": "value"}) == 1


class TestFormatContentForLlm:
    def test_all_fields(self):
        result = LLMUtils.format_content_for_llm("Title", "Body", "Summary")
        assert "标题: Title" in result
        assert "摘要: Summary" in result
        assert "内容:\nBody" in result

    def test_no_summary(self):
        result = LLMUtils.format_content_for_llm("Title", "Body")
        assert "摘要" not in result

    def test_empty_title(self):
        result = LLMUtils.format_content_for_llm("", "Body")
        assert "标题" not in result
        assert "内容:\nBody" in result

    def test_empty_content(self):
        result = LLMUtils.format_content_for_llm("Title", "")
        assert "标题: Title" in result
        assert "内容" not in result

    def test_all_empty(self):
        result = LLMUtils.format_content_for_llm("", "", None)
        assert result == ""


class TestEstimateProcessingCost:
    def test_known_model(self):
        result = LLMUtils.estimate_processing_cost("hello world", "gpt-4")
        assert result["model"] == "gpt-4"
        assert result["cost_per_1k_tokens"] == 0.03
        assert result["estimated_tokens"] > 0
        assert result["estimated_cost_usd"] >= 0

    def test_unknown_model_uses_default_rate(self):
        result = LLMUtils.estimate_processing_cost("test", "unknown-model")
        assert result["cost_per_1k_tokens"] == 0.002

    def test_empty_text(self):
        result = LLMUtils.estimate_processing_cost("")
        assert result["estimated_tokens"] == 1  # len("") // 4 + 1

    def test_token_estimation(self):
        text = "A" * 400
        result = LLMUtils.estimate_processing_cost(text)
        assert result["estimated_tokens"] == 101  # 400 // 4 + 1


class TestCreatePromptWithContext:
    def test_substitutes_variables(self):
        result = LLMUtils.create_prompt_with_context(
            "Hello {name}, you are {age}", {"name": "Alice", "age": 30}
        )
        assert result == "Hello Alice, you are 30"

    def test_missing_variable_returns_base(self):
        result = LLMUtils.create_prompt_with_context("Hello {name}", {})
        assert result == "Hello {name}"

    def test_extra_context_ignored(self):
        result = LLMUtils.create_prompt_with_context(
            "Hello {name}", {"name": "Bob", "extra": "ignored"}
        )
        assert result == "Hello Bob"


class TestValidateLlmResponse:
    def test_valid_text(self):
        is_valid, error = LLMUtils.validate_llm_response("Some text")
        assert is_valid is True
        assert error == ""

    def test_empty_response(self):
        is_valid, error = LLMUtils.validate_llm_response("")
        assert is_valid is False
        assert "Empty" in error

    def test_whitespace_only(self):
        is_valid, error = LLMUtils.validate_llm_response("   ")
        assert is_valid is False

    def test_none_response(self):
        is_valid, error = LLMUtils.validate_llm_response(None)
        assert is_valid is False

    def test_valid_json(self):
        is_valid, error = LLMUtils.validate_llm_response('{"key": "val"}', "json")
        assert is_valid is True

    def test_invalid_json(self):
        is_valid, error = LLMUtils.validate_llm_response("not json", "json")
        assert is_valid is False
        assert "Invalid JSON" in error

    def test_valid_list_with_dash(self):
        is_valid, _ = LLMUtils.validate_llm_response("- item1\n- item2", "list")
        assert is_valid is True

    def test_valid_list_with_numbers(self):
        is_valid, _ = LLMUtils.validate_llm_response("1. First\n2. Second", "list")
        assert is_valid is True

    def test_invalid_list(self):
        is_valid, error = LLMUtils.validate_llm_response("no list here", "list")
        assert is_valid is False
        assert "list format" in error


class TestExtractKeyPhrases:
    def test_empty_text(self):
        assert LLMUtils.extract_key_phrases("") == []

    def test_extracts_capitalized_words(self):
        result = LLMUtils.extract_key_phrases("Hello world Python language")
        # The regex captures "Capitalized word + following lowercase words"
        assert any("Hello" in phrase for phrase in result)
        assert any("Python" in phrase for phrase in result)

    def test_extracts_quoted_phrases(self):
        result = LLMUtils.extract_key_phrases('She said "important phrase" today')
        assert "important phrase" in result

    def test_extracts_caps_words(self):
        result = LLMUtils.extract_key_phrases("This is API and HTTP protocol")
        assert "API" in result or "HTTP" in result

    def test_respects_max_phrases(self):
        text = " ".join(f"Word{i}" for i in range(100))
        result = LLMUtils.extract_key_phrases(text, max_phrases=5)
        assert len(result) <= 5

    def test_no_duplicates(self):
        result = LLMUtils.extract_key_phrases('"Hello" and Hello world')
        assert len(result) == len(set(result))


class TestSplitLongContent:
    def test_short_content_not_split(self):
        result = LLMUtils.split_long_content("short", max_chunk_size=100)
        assert result == ["short"]

    def test_splits_long_content(self):
        text = "A" * 5000
        result = LLMUtils.split_long_content(text, max_chunk_size=2000, overlap=200)
        assert len(result) > 1
        assert all(len(chunk) <= 2000 for chunk in result)

    def test_overlap_between_chunks(self):
        text = "A" * 5000
        chunks = LLMUtils.split_long_content(text, max_chunk_size=2000, overlap=200)
        # Verify total coverage
        assert len(chunks) >= 3

    def test_sentence_boundary_splitting(self):
        sentences = ". ".join(["Sentence " + str(i) for i in range(50)])
        chunks = LLMUtils.split_long_content(sentences, max_chunk_size=200, overlap=50)
        assert len(chunks) > 1

    def test_exact_boundary(self):
        text = "A" * 2000
        result = LLMUtils.split_long_content(text, max_chunk_size=2000)
        assert result == [text]
