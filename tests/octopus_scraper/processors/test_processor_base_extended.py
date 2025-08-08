"""
Additional tests for processor base functionality.
"""

import os
import sys
from unittest.mock import Mock, patch

import pytest

# Add src to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from octopus_scraper.processors.processor_base import (
    ProcessingError,
    ProcessingResult,
    ProcessorBase,
)
from octopus_scraper.processors.processor_config import ProcessorConfig
from octopus_scraper.protos import Content


class TestProcessorBase(ProcessorBase):
    """Test implementation of ProcessorBase."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.process_calls = []

    def _parse_config(self, config: dict) -> ProcessorConfig:
        """Parse configuration."""
        return ProcessorConfig(
            processor_type=config.get("type", "test"),
            config=config,
            priority=config.get("priority", 100),
        )

    def __call__(self, contents: list) -> list:
        """Process contents."""
        self.process_calls.append(("__call__", contents))
        return [f"processed_{item}" for item in contents]


class FailingTestProcessor(ProcessorBase):
    """Test processor that fails."""

    def _parse_config(self, config: dict) -> ProcessorConfig:
        return ProcessorConfig(processor_type="failing", config=config)

    def __call__(self, contents: list) -> list:
        raise RuntimeError("Processing failed")


class InvalidConfigProcessor(ProcessorBase):
    """Test processor with invalid config validation."""

    def _parse_config(self, config: dict) -> ProcessorConfig:
        return ProcessorConfig(processor_type="invalid", config=config)

    def _validate_config(self) -> None:
        """Override validation to always fail."""
        raise ValueError("Invalid configuration")

    def __call__(self, contents: list) -> list:
        """Process contents - not used in test."""
        return contents


class TestProcessorBaseUnit:
    """Unit tests for ProcessorBase functionality."""

    def test_processor_initialization_valid(self):
        """Test processor initialization with valid config."""
        config = {"type": "test", "priority": 150}
        processor = TestProcessorBase(config)

        assert processor.name == "TestProcessorBase"
        assert processor.priority == 150
        assert processor.config.processor_type == "test"

    def test_processor_initialization_invalid_config(self):
        """Test processor initialization with invalid config."""
        config = {"type": "invalid"}

        with pytest.raises(ValueError, match="Invalid configuration"):
            InvalidConfigProcessor(config)

    def test_process_single_success(self):
        """Test processing single content successfully."""
        processor = TestProcessorBase({"type": "test"})
        content = Content(
            content_id="test_1",
            title="Test Title",
            link="http://example.com",
            summary="",
            content="Test content",
            published="2025-01-01",
        )

        result = processor.process_single(content)

        assert result.success is True
        assert result.content is not None
        assert result.error is None
        assert result.metadata["processor"] == "TestProcessorBase"

    def test_process_single_failure(self):
        """Test processing single content with failure."""
        processor = FailingTestProcessor({"type": "failing"})
        content = Content(
            content_id="test_1",
            title="Test Title",
            link="http://example.com",
            summary="",
            content="Test content",
            published="2025-01-01",
        )

        result = processor.process_single(content)

        assert result.success is False
        assert result.content is None
        assert "Processing failed" in result.error
        assert result.metadata["processor"] == "FailingTestProcessor"

    def test_process_single_no_result(self):
        """Test processing single content with no result returned."""

        class NoResultProcessor(ProcessorBase):
            def _parse_config(self, config: dict):
                return ProcessorConfig(processor_type="no_result", config=config)

            def __call__(self, contents: list) -> list:
                return []  # Return empty list

        processor = NoResultProcessor({"type": "no_result"})
        content = Content(
            content_id="test_1",
            title="Test Title",
            link="http://example.com",
            summary="",
            content="Test content",
            published="2025-01-01",
        )

        result = processor.process_single(content)

        assert result.success is False
        assert "No content returned" in result.error

    def test_batch_process_success(self):
        """Test batch processing successfully."""
        processor = TestProcessorBase({"type": "test"})
        contents = [
            Content(
                content_id="1",
                title="Title 1",
                link="http://example.com/1",
                summary="",
                content="Content 1",
                published="2025-01-01",
            ),
            Content(
                content_id="2",
                title="Title 2",
                link="http://example.com/2",
                summary="",
                content="Content 2",
                published="2025-01-01",
            ),
        ]

        results = processor.batch_process(contents, batch_size=1)

        assert len(results) == 2
        assert all(result.success for result in results)
        assert results[0].metadata["batch_index"] == 0
        assert results[1].metadata["batch_index"] == 1

    def test_batch_process_failure(self):
        """Test batch processing with failure."""
        processor = FailingTestProcessor({"type": "failing"})
        contents = [
            Content(
                content_id="1",
                title="Title 1",
                link="http://example.com/1",
                summary="",
                content="Content 1",
                published="2025-01-01",
            ),
            Content(
                content_id="2",
                title="Title 2",
                link="http://example.com/2",
                summary="",
                content="Content 2",
                published="2025-01-01",
            ),
        ]

        results = processor.batch_process(contents, batch_size=2)

        assert len(results) == 2
        assert all(not result.success for result in results)
        assert all("Batch processing failed" in result.error for result in results)
        assert all(
            result.metadata["processor"] == "FailingTestProcessor" for result in results
        )

    def test_batch_process_mixed_results(self):
        """Test batch processing with mixed success/failure."""

        class MixedProcessor(ProcessorBase):
            def _parse_config(self, config: dict):
                return ProcessorConfig(processor_type="mixed", config=config)

            def __call__(self, contents: list) -> list:
                # First content succeeds, subsequent ones fail
                processed = []
                for content in contents:
                    if content.content_id == "1":
                        processed.append(f"processed_{content.content_id}")
                    else:
                        raise RuntimeError(
                            f"Processing failed for {content.content_id}"
                        )
                return processed

        processor = MixedProcessor({"type": "mixed"})
        contents = [
            Content(
                content_id="1",
                title="Title 1",
                link="http://example.com/1",
                summary="",
                content="Content 1",
                published="2025-01-01",
            ),
            Content(
                content_id="2",
                title="Title 2",
                link="http://example.com/2",
                summary="",
                content="Content 2",
                published="2025-01-01",
            ),
            Content(
                content_id="3",
                title="Title 3",
                link="http://example.com/3",
                summary="",
                content="Content 3",
                published="2025-01-01",
            ),
        ]

        results = processor.batch_process(contents, batch_size=1)

        assert len(results) == 3
        assert results[0].success is True  # First should succeed
        assert results[1].success is False  # Second should fail
        assert results[2].success is False  # Third should fail

    def test_processor_properties(self):
        """Test processor properties."""
        config = {"type": "test", "priority": 75}
        processor = TestProcessorBase(config)

        assert processor.name == "TestProcessorBase"
        assert processor.priority == 75

    def test_processor_priority_default(self):
        """Test processor default priority."""
        processor = TestProcessorBase({"type": "test"})
        assert processor.priority == 100  # Default priority

    def test_processor_string_representations(self):
        """Test string representations of processor."""
        config = {"type": "test", "priority": 50}
        processor = TestProcessorBase(config)

        str_repr = str(processor)
        assert "TestProcessorBase" in str_repr
        assert "priority=50" in str_repr

        repr_str = repr(processor)
        assert "TestProcessorBase" in repr_str
        assert "config=" in repr_str

    def test_processing_result_initialization(self):
        """Test ProcessingResult initialization."""
        result = ProcessingResult(
            success=True, content="test_content", error=None, metadata={"key": "value"}
        )

        assert result.success is True
        assert result.content == "test_content"
        assert result.error is None
        assert result.metadata == {"key": "value"}

    def test_processing_result_defaults(self):
        """Test ProcessingResult default values."""
        result = ProcessingResult(success=False)

        assert result.success is False
        assert result.content is None
        assert result.error is None
        assert result.metadata is None


class TestProcessingError:
    """Test cases for ProcessingError."""

    def test_processing_error_basic(self):
        """Test basic ProcessingError creation."""
        error = ProcessingError("Test error message")

        assert str(error) == "Test error message"
        assert error.processor_name is None
        assert error.content_id is None
        assert error.original_error is None

    def test_processing_error_with_details(self):
        """Test ProcessingError with additional details."""
        original = ValueError("Original error")
        error = ProcessingError(
            "Processing failed",
            processor_name="TestProcessor",
            content_id="content_123",
            original_error=original,
        )

        assert error.processor_name == "TestProcessor"
        assert error.content_id == "content_123"
        assert error.original_error == original

        error_str = str(error)
        assert "Processing failed" in error_str
        assert "TestProcessor" in error_str
        assert "content_123" in error_str

    def test_processing_error_inheritance(self):
        """Test ProcessingError inherits from Exception."""
        error = ProcessingError("Test error")
        assert isinstance(error, Exception)

    def test_processing_error_partial_details(self):
        """Test ProcessingError with partial details."""
        error = ProcessingError("Test error", processor_name="TestProcessor")

        error_str = str(error)
        assert "Test error" in error_str
        assert "TestProcessor" in error_str
        assert "Content ID" not in error_str  # Should not appear since not provided


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
