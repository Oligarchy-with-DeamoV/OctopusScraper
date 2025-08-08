"""
Tests for processor pipeline system.
"""

import os
import sys
import time
from unittest.mock import Mock, patch

import pytest

# Add src to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from octopus_scraper.processors import ProcessorFactory
from octopus_scraper.processors.processor_base import ProcessorBase
from octopus_scraper.processors.processor_config import (
    ProcessorConfig,
    ProcessorConfigManager,
)
from octopus_scraper.processors.processor_pipeline import (
    PipelineBuilder,
    PipelineResult,
    ProcessorPipeline,
    create_analysis_pipeline,
    create_default_pipeline,
)


class MockProcessor(ProcessorBase):
    """Mock processor for testing."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.processed_data = []

    def _parse_config(self, config: dict) -> dict:
        """Parse and validate configuration."""
        return config

    def __call__(self, contents: list) -> list:
        """Process contents."""
        return [f"processed_{item}" for item in contents]

    def process(self, data: dict) -> dict:
        """Process single data item."""
        result = {"processed": data.get("input", ""), "processor": self.name}
        self.processed_data.append(result)
        return result


class FailingProcessor(ProcessorBase):
    """Processor that always fails for testing error handling."""

    def __init__(self, config: dict):
        super().__init__(config)

    def _parse_config(self, config: dict) -> dict:
        return config

    def __call__(self, contents: list) -> list:
        raise RuntimeError("Processor failed")

    def process(self, data: dict) -> dict:
        raise RuntimeError("Processor failed")


class TestPipelineResult:
    """Test cases for PipelineResult."""

    def test_pipeline_result_creation(self):
        """Test creating pipeline result."""
        result = PipelineResult(
            success=True,
            results={"key": "value"},
            errors=[],
            execution_time=1.5,
            processor_results={"proc1": "result1"},
        )

        assert result.success is True
        assert result.results == {"key": "value"}
        assert result.errors == []
        assert result.execution_time == 1.5
        assert result.processor_results == {"proc1": "result1"}

    def test_get_result(self):
        """Test getting processor result."""
        result = PipelineResult(
            success=True,
            results={},
            errors=[],
            execution_time=0.0,
            processor_results={"proc1": "result1", "proc2": "result2"},
        )

        assert result.get_result("proc1") == "result1"
        assert result.get_result("proc2") == "result2"
        assert result.get_result("nonexistent") is None
        assert result.get_result("nonexistent", "default") == "default"

    def test_has_errors(self):
        """Test checking for errors."""
        result_no_errors = PipelineResult(
            success=True,
            results={},
            errors=[],
            execution_time=0.0,
            processor_results={},
        )
        assert result_no_errors.has_errors() is False

        result_with_errors = PipelineResult(
            success=False,
            results={},
            errors=[RuntimeError("test")],
            execution_time=0.0,
            processor_results={},
        )
        assert result_with_errors.has_errors() is True

    def test_get_error_summary(self):
        """Test getting error summary."""
        result_no_errors = PipelineResult(
            success=True,
            results={},
            errors=[],
            execution_time=0.0,
            processor_results={},
        )
        assert result_no_errors.get_error_summary() == "No errors"

        errors = [RuntimeError("error1"), ValueError("error2")]
        result_with_errors = PipelineResult(
            success=False,
            results={},
            errors=errors,
            execution_time=0.0,
            processor_results={},
        )
        summary = result_with_errors.get_error_summary()
        assert "error1" in summary
        assert "error2" in summary


class TestProcessorPipeline:
    """Test cases for ProcessorPipeline."""

    @pytest.fixture
    def mock_factory(self):
        """Create mock processor factory."""
        factory = Mock(spec=ProcessorFactory)
        factory.create_processor.side_effect = lambda proc_type, config: MockProcessor(
            config
        )
        return factory

    @pytest.fixture
    def mock_config_manager(self):
        """Create mock config manager."""
        manager = Mock(spec=ProcessorConfigManager)
        manager.get_config.return_value = ProcessorConfig(
            processor_type="test", config={"key": "value"}
        )
        return manager

    def test_pipeline_initialization(self, mock_factory, mock_config_manager):
        """Test pipeline initialization."""
        pipeline = ProcessorPipeline("test_pipeline", mock_factory, mock_config_manager)

        assert pipeline.name == "test_pipeline"
        assert pipeline.factory == mock_factory
        assert pipeline.config_manager == mock_config_manager
        assert len(pipeline._processors) == 0
        assert len(pipeline._processor_names) == 0

    def test_add_processor(self, mock_factory, mock_config_manager):
        """Test adding processor to pipeline."""
        pipeline = ProcessorPipeline("test", mock_factory, mock_config_manager)
        config = ProcessorConfig(processor_type="test", config={"key": "value"})

        pipeline.add_processor("proc1", config)

        assert len(pipeline._processors) == 1
        assert len(pipeline._processor_names) == 1
        assert "proc1" in pipeline._processor_names
        mock_factory.create_processor.assert_called_once_with("test", {"key": "value"})

    def test_add_processor_with_dependencies(self, mock_factory, mock_config_manager):
        """Test adding processor with dependencies."""
        pipeline = ProcessorPipeline("test", mock_factory, mock_config_manager)
        config = ProcessorConfig(processor_type="test", config={})

        pipeline.add_processor("proc1", config, dependencies=["dep1", "dep2"])

        assert pipeline._dependencies["proc1"] == ["dep1", "dep2"]

    def test_add_processor_duplicate_name(self, mock_factory, mock_config_manager):
        """Test adding processor with duplicate name."""
        pipeline = ProcessorPipeline("test", mock_factory, mock_config_manager)
        config = ProcessorConfig(processor_type="test", config={})

        pipeline.add_processor("proc1", config)

        with pytest.raises(ValueError, match="already exists"):
            pipeline.add_processor("proc1", config)

    def test_add_processor_by_name(self, mock_factory, mock_config_manager):
        """Test adding processor by configuration name."""
        pipeline = ProcessorPipeline("test", mock_factory, mock_config_manager)

        pipeline.add_processor_by_name("proc1", "config_name")

        mock_config_manager.get_config.assert_called_once_with("config_name")
        assert len(pipeline._processors) == 1

    def test_remove_processor(self, mock_factory, mock_config_manager):
        """Test removing processor from pipeline."""
        pipeline = ProcessorPipeline("test", mock_factory, mock_config_manager)
        config = ProcessorConfig(processor_type="test", config={})

        pipeline.add_processor("proc1", config, dependencies=["dep1"])
        assert len(pipeline._processors) == 1

        pipeline.remove_processor("proc1")
        assert len(pipeline._processors) == 0
        assert "proc1" not in pipeline._dependencies

    def test_remove_nonexistent_processor(self, mock_factory, mock_config_manager):
        """Test removing nonexistent processor (should not raise error)."""
        pipeline = ProcessorPipeline("test", mock_factory, mock_config_manager)

        # Should not raise error
        pipeline.remove_processor("nonexistent")

    def test_resolve_execution_order_simple(self, mock_factory, mock_config_manager):
        """Test resolving execution order without dependencies."""
        pipeline = ProcessorPipeline("test", mock_factory, mock_config_manager)
        config = ProcessorConfig(processor_type="test", config={})

        pipeline.add_processor("proc1", config)
        pipeline.add_processor("proc2", config)

        order = pipeline._resolve_execution_order()
        assert set(order) == {"proc1", "proc2"}
        assert len(order) == 2

    def test_resolve_execution_order_with_dependencies(
        self, mock_factory, mock_config_manager
    ):
        """Test resolving execution order with dependencies."""
        pipeline = ProcessorPipeline("test", mock_factory, mock_config_manager)
        config = ProcessorConfig(processor_type="test", config={})

        pipeline.add_processor("proc1", config)
        pipeline.add_processor("proc2", config, dependencies=["proc1"])
        pipeline.add_processor("proc3", config, dependencies=["proc2"])

        order = pipeline._resolve_execution_order()

        # proc1 should come before proc2, proc2 before proc3
        assert order.index("proc1") < order.index("proc2")
        assert order.index("proc2") < order.index("proc3")

    def test_resolve_execution_order_circular_dependency(
        self, mock_factory, mock_config_manager
    ):
        """Test resolving execution order with circular dependencies."""
        pipeline = ProcessorPipeline("test", mock_factory, mock_config_manager)
        config = ProcessorConfig(processor_type="test", config={})

        pipeline.add_processor("proc1", config, dependencies=["proc2"])
        pipeline.add_processor("proc2", config, dependencies=["proc1"])

        with pytest.raises(ValueError, match="Circular dependency"):
            pipeline._resolve_execution_order()

    def test_resolve_execution_order_missing_dependency(
        self, mock_factory, mock_config_manager
    ):
        """Test resolving execution order with missing dependency."""
        pipeline = ProcessorPipeline("test", mock_factory, mock_config_manager)
        config = ProcessorConfig(processor_type="test", config={})

        pipeline.add_processor("proc1", config, dependencies=["missing"])

        with pytest.raises(ValueError, match="Dependency 'missing' not found"):
            pipeline._resolve_execution_order()

    def test_execute_sequential(self, mock_factory, mock_config_manager):
        """Test sequential pipeline execution."""
        pipeline = ProcessorPipeline("test", mock_factory, mock_config_manager)
        config = ProcessorConfig(processor_type="test", config={})

        pipeline.add_processor("proc1", config)
        pipeline.add_processor("proc2", config)

        input_data = {"input": "test_data"}
        result = pipeline.execute(input_data)

        assert result.success is True
        assert len(result.errors) == 0
        assert result.execution_time > 0
        assert len(result.processor_results) == 2

    def test_execute_parallel(self, mock_factory, mock_config_manager):
        """Test parallel pipeline execution."""
        pipeline = ProcessorPipeline("test", mock_factory, mock_config_manager)
        config = ProcessorConfig(processor_type="test", config={})

        pipeline.add_processor("proc1", config)
        pipeline.add_processor("proc2", config)

        input_data = {"input": "test_data"}
        result = pipeline.execute(input_data, parallel=True)

        assert result.success is True
        assert len(result.errors) == 0
        assert result.execution_time > 0
        assert len(result.processor_results) == 2

    def test_execute_with_error_continue(self, mock_config_manager):
        """Test pipeline execution with error (continue on error)."""
        # Create custom factory that returns failing processor for one name
        factory = Mock(spec=ProcessorFactory)

        def create_processor_side_effect(proc_type, config):
            if "fail" in str(config):
                return FailingProcessor(config)
            return MockProcessor(config)

        factory.create_processor.side_effect = create_processor_side_effect

        pipeline = ProcessorPipeline("test", factory, mock_config_manager)

        config1 = ProcessorConfig(processor_type="test", config={"name": "normal"})
        config2 = ProcessorConfig(processor_type="test", config={"name": "fail"})

        pipeline.add_processor("proc1", config1)
        pipeline.add_processor("proc2", config2)

        result = pipeline.execute({"input": "test"}, stop_on_error=False)

        assert result.success is False
        assert len(result.errors) == 1
        assert "proc1" in result.processor_results  # Should have some results

    def test_execute_with_error_stop(self, mock_config_manager):
        """Test pipeline execution with error (stop on error)."""
        factory = Mock(spec=ProcessorFactory)

        def create_processor_side_effect(proc_type, config):
            if "fail" in str(config):
                return FailingProcessor(config)
            return MockProcessor(config)

        factory.create_processor.side_effect = create_processor_side_effect

        pipeline = ProcessorPipeline("test", factory, mock_config_manager)

        config1 = ProcessorConfig(processor_type="test", config={"name": "fail"})
        config2 = ProcessorConfig(processor_type="test", config={"name": "normal"})

        pipeline.add_processor("proc1", config1)
        pipeline.add_processor("proc2", config2)

        result = pipeline.execute({"input": "test"}, stop_on_error=True)

        assert result.success is False
        assert len(result.errors) >= 1

    def test_execute_with_error_handler(self, mock_factory, mock_config_manager):
        """Test pipeline execution with custom error handler."""
        pipeline = ProcessorPipeline("test", mock_factory, mock_config_manager)
        config = ProcessorConfig(processor_type="test", config={})

        error_handled = []

        def error_handler(error):
            error_handled.append(str(error))

        pipeline.add_processor("proc1", config, error_handler=error_handler)

        # Mock processor to raise error
        pipeline._processors[0].process = Mock(side_effect=RuntimeError("test error"))

        result = pipeline.execute({"input": "test"})

        assert len(error_handled) == 1
        assert "test error" in error_handled[0]

    def test_get_processor_info(self, mock_factory, mock_config_manager):
        """Test getting processor information."""
        pipeline = ProcessorPipeline("test", mock_factory, mock_config_manager)
        config = ProcessorConfig(processor_type="test", config={})

        pipeline.add_processor("dep1", config)  # Add dependency first
        pipeline.add_processor("proc1", config, dependencies=["dep1"])
        pipeline.add_processor("proc2", config)

        info = pipeline.get_processor_info()

        assert info["name"] == "test"
        assert len(info["processors"]) == 3
        assert "execution_order" in info


class TestPipelineBuilder:
    """Test cases for PipelineBuilder."""

    def test_builder_initialization(self):
        """Test builder initialization."""
        builder = PipelineBuilder("test_pipeline")

        assert builder.name == "test_pipeline"
        assert len(builder._configs) == 0
        assert builder._factory is None
        assert builder._config_manager is None

    def test_with_factory(self):
        """Test setting factory."""
        builder = PipelineBuilder()
        factory = Mock(spec=ProcessorFactory)

        result = builder.with_factory(factory)

        assert result is builder  # Should return self for chaining
        assert builder._factory == factory

    def test_with_config_manager(self):
        """Test setting config manager."""
        builder = PipelineBuilder()
        manager = Mock(spec=ProcessorConfigManager)

        result = builder.with_config_manager(manager)

        assert result is builder
        assert builder._config_manager == manager

    def test_add_processor(self):
        """Test adding processor to builder."""
        builder = PipelineBuilder()

        result = builder.add_processor("proc1", "test_type", {"key": "value"}, ["dep1"])

        assert result is builder
        assert len(builder._configs) == 1

        name, config, deps = builder._configs[0]
        assert name == "proc1"
        assert config.processor_type == "test_type"
        assert config.config == {"key": "value"}
        assert deps == ["dep1"]

    def test_add_llm_summary(self):
        """Test adding LLM summary processor."""
        builder = PipelineBuilder()

        result = builder.add_llm_summary(
            "summary", "gpt-4", ["dep1"], custom_param="value"
        )

        assert result is builder
        assert len(builder._configs) == 1

        name, config, deps = builder._configs[0]
        assert name == "summary"
        assert config.processor_type == "llm_summary"
        assert config.config["model"] == "gpt-4"
        assert config.config["custom_param"] == "value"
        assert deps == ["dep1"]

    def test_add_llm_tags(self):
        """Test adding LLM tags processor."""
        builder = PipelineBuilder()

        result = builder.add_llm_tags("tags", "gpt-3.5-turbo", temperature=0.5)

        assert result is builder
        assert len(builder._configs) == 1

        name, config, deps = builder._configs[0]
        assert name == "tags"
        assert config.processor_type == "llm_tags"
        assert config.config["model"] == "gpt-3.5-turbo"
        assert config.config["temperature"] == 0.5

    def test_add_llm_keywords(self):
        """Test adding LLM keywords processor."""
        builder = PipelineBuilder()

        result = builder.add_llm_keywords("keywords", max_keywords=10)

        assert result is builder
        assert len(builder._configs) == 1

        name, config, deps = builder._configs[0]
        assert name == "keywords"
        assert config.processor_type == "llm_keywords"
        assert config.config["max_keywords"] == 10

    def test_add_html_content(self):
        """Test adding HTML content processor."""
        builder = PipelineBuilder()

        result = builder.add_html_content("html", clean=True)

        assert result is builder
        assert len(builder._configs) == 1

        name, config, deps = builder._configs[0]
        assert name == "html"
        assert config.processor_type == "html_content"
        assert config.config["clean"] == True

    @patch("octopus_scraper.processors.processor_pipeline.ProcessorPipeline")
    def test_build(self, mock_pipeline_class):
        """Test building pipeline."""
        mock_pipeline = Mock()
        mock_pipeline_class.return_value = mock_pipeline

        factory = Mock(spec=ProcessorFactory)
        manager = Mock(spec=ProcessorConfigManager)

        builder = PipelineBuilder("test")
        builder.with_factory(factory).with_config_manager(manager)
        builder.add_processor("proc1", "type1", {"key": "value"})

        result = builder.build()

        assert result == mock_pipeline
        mock_pipeline_class.assert_called_once_with(
            name="test", factory=factory, config_manager=manager
        )
        mock_pipeline.add_processor.assert_called_once()


class TestPipelineHelpers:
    """Test cases for pipeline helper functions."""

    @patch("octopus_scraper.processors.processor_pipeline.PipelineBuilder")
    def test_create_default_pipeline(self, mock_builder_class):
        """Test creating default pipeline."""
        mock_builder = Mock()
        mock_builder_class.return_value = mock_builder
        mock_builder.add_html_content.return_value = mock_builder
        mock_builder.add_llm_summary.return_value = mock_builder
        mock_builder.add_llm_tags.return_value = mock_builder
        mock_builder.add_llm_keywords.return_value = mock_builder
        mock_builder.build.return_value = Mock()

        result = create_default_pipeline("test_name")

        mock_builder_class.assert_called_once_with("test_name")
        mock_builder.add_html_content.assert_called_once_with("html")
        mock_builder.add_llm_summary.assert_called_once_with(
            "summary", dependencies=["html"]
        )
        mock_builder.add_llm_tags.assert_called_once_with("tags", dependencies=["html"])
        mock_builder.add_llm_keywords.assert_called_once_with(
            "keywords", dependencies=["html"]
        )
        mock_builder.build.assert_called_once()

    @patch("octopus_scraper.processors.processor_pipeline.PipelineBuilder")
    def test_create_analysis_pipeline(self, mock_builder_class):
        """Test creating analysis pipeline."""
        mock_builder = Mock()
        mock_builder_class.return_value = mock_builder
        mock_builder.add_html_content.return_value = mock_builder
        mock_builder.add_llm_summary.return_value = mock_builder
        mock_builder.add_llm_tags.return_value = mock_builder
        mock_builder.add_llm_keywords.return_value = mock_builder
        mock_builder.build.return_value = Mock()

        result = create_analysis_pipeline("analysis_name")

        mock_builder_class.assert_called_once_with("analysis_name")
        mock_builder.add_html_content.assert_called_once_with(
            "html", clean_content=True
        )
        mock_builder.add_llm_summary.assert_called_once_with(
            "summary", dependencies=["html"], temperature=0.3
        )
        mock_builder.add_llm_tags.assert_called_once_with(
            "tags", dependencies=["summary"], temperature=0.5
        )
        mock_builder.add_llm_keywords.assert_called_once_with(
            "keywords", dependencies=["summary"], temperature=0.3
        )
        mock_builder.build.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
