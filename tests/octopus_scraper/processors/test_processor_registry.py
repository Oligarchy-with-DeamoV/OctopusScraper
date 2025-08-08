"""
Tests for processor registry and factory system.
"""

from unittest.mock import Mock, patch

import pytest

from octopus_scraper.processors import (
    ProcessorFactory,
    ProcessorRegistry,
    create_processor,
    get_available_processors,
    register_processor,
)
from octopus_scraper.processors.llm_summary_processor import LLMSummaryProcessor
from octopus_scraper.processors.processor_base import ProcessorBase


class MockProcessor(ProcessorBase):
    """Mock processor for testing."""

    def __init__(self, config: dict):
        super().__init__(config)

    def _parse_config(self, config: dict) -> dict:
        """Parse and validate configuration."""
        return config

    def process(self, data: dict) -> dict:
        """Process data."""
        return {"mock_result": f"processed_{data.get('content', '')}"}

    def __call__(self, contents: list) -> list:
        """Legacy callable interface."""
        return [{"mock_result": f"processed_{content}"} for content in contents]


class TestProcessorRegistry:
    """Test cases for ProcessorRegistry."""

    def test_registry_initialization(self):
        """Test registry creates with built-in processors."""
        registry = ProcessorRegistry()

        processors = registry.list_processors()
        assert "html_content" in processors
        assert "llm_summary" in processors
        assert "llm_tags" in processors
        assert "llm_keywords" in processors
        assert len(processors) >= 4

    def test_register_processor(self):
        """Test registering custom processor."""
        registry = ProcessorRegistry()
        initial_count = len(registry.list_processors())

        registry.register("mock", MockProcessor)

        assert "mock" in registry.list_processors()
        assert len(registry.list_processors()) == initial_count + 1
        assert registry.get_processor_class("mock") == MockProcessor

    def test_register_invalid_processor(self):
        """Test registering invalid processor class."""
        registry = ProcessorRegistry()

        with pytest.raises(ValueError, match="must inherit from ProcessorBase"):
            registry.register("invalid", str)

    def test_unregister_processor(self):
        """Test unregistering processor."""
        registry = ProcessorRegistry()
        registry.register("temp", MockProcessor)

        assert "temp" in registry.list_processors()
        registry.unregister("temp")
        assert "temp" not in registry.list_processors()

    def test_get_unknown_processor(self):
        """Test getting unknown processor raises error."""
        registry = ProcessorRegistry()

        with pytest.raises(KeyError, match="Unknown processor: nonexistent"):
            registry.get_processor_class("nonexistent")

    def test_create_processor(self):
        """Test creating processor instance."""
        registry = ProcessorRegistry()
        registry.register("mock", MockProcessor)

        config = {"test": "value"}
        processor = registry.create_processor("mock", config)

        assert isinstance(processor, MockProcessor)
        assert processor.config == config

    def test_create_processor_with_invalid_config(self):
        """Test creating processor with invalid config."""
        registry = ProcessorRegistry()
        registry.register("mock", MockProcessor)

        # Mock constructor that raises exception
        with patch.object(
            MockProcessor, "__init__", side_effect=ValueError("Invalid config")
        ):
            with pytest.raises(ValueError, match="Failed to create processor 'mock'"):
                registry.create_processor("mock", {})

    def test_get_processor_info(self):
        """Test getting processor information."""
        registry = ProcessorRegistry()

        info = registry.get_processor_info("llm_summary")

        assert info["name"] == "llm_summary"
        assert info["class_name"] == "LLMSummaryProcessor"
        assert "module" in info
        assert "doc" in info

    def test_get_processor_info_unknown(self):
        """Test getting info for unknown processor."""
        registry = ProcessorRegistry()

        with pytest.raises(KeyError, match="Unknown processor: nonexistent"):
            registry.get_processor_info("nonexistent")


class TestProcessorFactory:
    """Test cases for ProcessorFactory."""

    def test_factory_initialization(self):
        """Test factory creates with default registry."""
        factory = ProcessorFactory()

        processors = factory.get_available_processors()
        assert len(processors) >= 4

    def test_factory_with_custom_registry(self):
        """Test factory with custom registry."""
        registry = ProcessorRegistry()
        registry.register("custom", MockProcessor)

        factory = ProcessorFactory(registry)

        assert "custom" in factory.get_available_processors()

    def test_create_processor(self):
        """Test creating processor through factory."""
        factory = ProcessorFactory()

        # Use MockProcessor instead of trying to mock real processor
        factory.registry.register("test_llm", MockProcessor)

        config = {"model": "gpt-3.5-turbo", "api_key": "test-key"}
        processor = factory.create_processor("test_llm", config)

        assert isinstance(processor, MockProcessor)
        assert processor.config == config

    def test_create_processor_chain(self):
        """Test creating processor chain."""
        factory = ProcessorFactory()
        factory.registry.register("mock", MockProcessor)

        configs = [
            {"type": "mock", "config_value": "test1"},
            {"type": "mock", "config_value": "test2"},
        ]

        processors = factory.create_processor_chain(configs)

        assert len(processors) == 2
        assert all(isinstance(p, MockProcessor) for p in processors)

    def test_create_processor_chain_missing_type(self):
        """Test creating processor chain with missing type."""
        factory = ProcessorFactory()

        configs = [{"config_value": "test"}]  # Missing 'type'

        with pytest.raises(ValueError, match="must include 'type' field"):
            factory.create_processor_chain(configs)


class TestGlobalAPI:
    """Test cases for global API functions."""

    def test_register_processor_global(self):
        """Test global processor registration."""
        register_processor("global_mock", MockProcessor)

        assert "global_mock" in get_available_processors()

    @patch("octopus_scraper.processors._factory.create_processor")
    def test_create_processor_global(self, mock_create):
        """Test global processor creation."""
        mock_create.return_value = Mock()

        config = {"test": "value"}
        create_processor("test_type", config)

        mock_create.assert_called_once_with("test_type", config)

    def test_get_available_processors_global(self):
        """Test getting available processors globally."""
        processors = get_available_processors()

        assert isinstance(processors, list)
        assert len(processors) > 0
        assert "llm_summary" in processors


class TestLegacyCompatibility:
    """Test cases for legacy compatibility."""

    def test_available_processor_dict(self):
        """Test legacy AVALIABLE_PROCESSOR dict."""
        from octopus_scraper.processors import AVALIABLE_PROCESSOR

        assert isinstance(AVALIABLE_PROCESSOR, dict)
        assert "llm" in AVALIABLE_PROCESSOR
        assert "html_content" in AVALIABLE_PROCESSOR
        assert "llm_summary" in AVALIABLE_PROCESSOR
        assert "llm_tags" in AVALIABLE_PROCESSOR
        assert "llm_keywords" in AVALIABLE_PROCESSOR


@pytest.fixture
def sample_registry():
    """Create sample registry for testing."""
    registry = ProcessorRegistry()
    registry.register("test_processor", MockProcessor)
    return registry


@pytest.fixture
def sample_factory(sample_registry):
    """Create sample factory for testing."""
    return ProcessorFactory(sample_registry)


class TestProcessorIntegration:
    """Integration tests for processor system."""

    def test_end_to_end_processor_creation(self, sample_factory):
        """Test complete processor creation workflow."""
        config = {"model": "test-model", "temperature": 0.5}

        processor = sample_factory.create_processor("test_processor", config)

        assert isinstance(processor, MockProcessor)
        assert processor.config == config

        # Test processing
        result = processor.process({"content": "test content"})
        assert result == {"mock_result": "processed_test content"}

    def test_multiple_processor_types(self, sample_factory):
        """Test creating multiple processor types."""
        configs = [
            {"type": "test_processor", "value": "config1"},
            {"type": "test_processor", "value": "config2"},
        ]

        processors = sample_factory.create_processor_chain(configs)

        assert len(processors) == 2
        assert processors[0].config == {"value": "config1"}
        assert processors[1].config == {"value": "config2"}
