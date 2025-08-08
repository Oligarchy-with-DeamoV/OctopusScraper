"""
Processor Pipeline System.

This module provides a flexible pipeline system for chaining processors
together with dependency management and error handling.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar

import structlog

from octopus_scraper.processors import ProcessorFactory
from octopus_scraper.processors.processor_base import ProcessorBase
from octopus_scraper.processors.processor_config import (
    ProcessorConfig,
    ProcessorConfigManager,
)

logger = structlog.getLogger(__name__)

T = TypeVar("T")


@dataclass
class PipelineResult:
    """
    Result from pipeline execution.

    Contains both successful results and any errors that occurred.
    """

    success: bool
    results: Dict[str, Any]
    errors: List[Exception]
    execution_time: float
    processor_results: Dict[str, Any]

    def get_result(self, processor_name: str, default: Any = None) -> Any:
        """
        Get result from specific processor.

        Args:
            processor_name: Name of processor
            default: Default value if not found

        Returns:
            Processor result
        """
        return self.processor_results.get(processor_name, default)

    def has_errors(self) -> bool:
        """Check if pipeline has any errors."""
        return len(self.errors) > 0

    def get_error_summary(self) -> str:
        """Get summary of all errors."""
        if not self.errors:
            return "No errors"

        return "; ".join(str(error) for error in self.errors)


class ProcessorPipeline:
    """
    Pipeline for executing processors in sequence or parallel.

    Supports dependency management, error handling, and flexible execution modes.
    """

    def __init__(
        self,
        name: str = "default",
        factory: Optional[ProcessorFactory] = None,
        config_manager: Optional[ProcessorConfigManager] = None,
    ):
        self.name = name
        self.factory = factory or ProcessorFactory()
        self.config_manager = config_manager or ProcessorConfigManager()

        self._processors: List[ProcessorBase] = []
        self._processor_names: List[str] = []
        self._dependencies: Dict[str, List[str]] = {}
        self._error_handlers: Dict[str, Callable] = {}

        logger.info("Created processor pipeline", name=name)

    def add_processor(
        self,
        name: str,
        config: ProcessorConfig,
        dependencies: Optional[List[str]] = None,
        error_handler: Optional[Callable] = None,
    ) -> None:
        """
        Add processor to pipeline.

        Args:
            name: Processor name
            config: Processor configuration
            dependencies: List of processor names this depends on
            error_handler: Optional error handler function
        """
        if name in self._processor_names:
            raise ValueError(f"Processor '{name}' already exists in pipeline")

        # Create processor instance
        processor = self.factory.create_processor(config.processor_type, config.config)

        self._processors.append(processor)
        self._processor_names.append(name)

        if dependencies:
            self._dependencies[name] = dependencies

        if error_handler:
            self._error_handlers[name] = error_handler

        logger.debug(
            "Added processor to pipeline", name=name, type=config.processor_type
        )

    def add_processor_by_name(
        self, name: str, config_name: str, dependencies: Optional[List[str]] = None
    ) -> None:
        """
        Add processor using configuration manager.

        Args:
            name: Processor name
            config_name: Configuration name from config manager
            dependencies: List of processor names this depends on
        """
        config = self.config_manager.get_config(config_name)
        self.add_processor(name, config, dependencies)

    def remove_processor(self, name: str) -> None:
        """
        Remove processor from pipeline.

        Args:
            name: Processor name
        """
        if name not in self._processor_names:
            logger.warning("Processor not found in pipeline", name=name)
            return

        index = self._processor_names.index(name)
        del self._processors[index]
        del self._processor_names[index]

        # Remove dependencies
        if name in self._dependencies:
            del self._dependencies[name]

        # Remove error handler
        if name in self._error_handlers:
            del self._error_handlers[name]

        logger.debug("Removed processor from pipeline", name=name)

    def _resolve_execution_order(self) -> List[str]:
        """
        Resolve processor execution order based on dependencies.

        Returns:
            List of processor names in execution order

        Raises:
            ValueError: If circular dependencies detected
        """
        # Topological sort for dependency resolution
        visited = set()
        temp_visited = set()
        result = []

        def visit(node: str):
            if node in temp_visited:
                raise ValueError(f"Circular dependency detected involving '{node}'")

            if node not in visited:
                temp_visited.add(node)

                # Visit dependencies first
                for dep in self._dependencies.get(node, []):
                    if dep not in self._processor_names:
                        raise ValueError(
                            f"Dependency '{dep}' not found for processor '{node}'"
                        )
                    visit(dep)

                temp_visited.remove(node)
                visited.add(node)
                result.append(node)

        # Visit all processors
        for name in self._processor_names:
            if name not in visited:
                visit(name)

        return result

    def execute(
        self,
        input_data: Dict[str, Any],
        parallel: bool = False,
        stop_on_error: bool = False,
    ) -> PipelineResult:
        """
        Execute pipeline.

        Args:
            input_data: Input data for processors
            parallel: Whether to execute processors in parallel (ignores dependencies)
            stop_on_error: Whether to stop execution on first error

        Returns:
            Pipeline execution result
        """
        import time

        start_time = time.time()

        results = {}
        errors = []
        processor_results = {}

        try:
            if parallel:
                execution_order = self._processor_names
            else:
                execution_order = self._resolve_execution_order()

            logger.info(
                "Executing pipeline",
                name=self.name,
                order=execution_order,
                parallel=parallel,
            )

            if parallel:
                # Parallel execution
                with ThreadPoolExecutor(max_workers=len(self._processors)) as executor:
                    futures = {}

                    for name in execution_order:
                        index = self._processor_names.index(name)
                        processor = self._processors[index]

                        future = executor.submit(
                            self._execute_processor, processor, name, input_data
                        )
                        futures[name] = future

                    # Collect results
                    for name, future in futures.items():
                        try:
                            result = future.result()
                            processor_results[name] = result
                            results.update(
                                result if isinstance(result, dict) else {name: result}
                            )
                        except Exception as e:
                            errors.append(e)
                            self._handle_processor_error(name, e)

                            if stop_on_error:
                                break
            else:
                # Sequential execution
                current_data = input_data.copy()

                for name in execution_order:
                    index = self._processor_names.index(name)
                    processor = self._processors[index]

                    try:
                        result = self._execute_processor(processor, name, current_data)
                        processor_results[name] = result

                        # Update current data with results
                        if isinstance(result, dict):
                            current_data.update(result)
                            results.update(result)
                        else:
                            current_data[name] = result
                            results[name] = result

                    except Exception as e:
                        errors.append(e)
                        self._handle_processor_error(name, e)

                        if stop_on_error:
                            break

        except Exception as e:
            logger.error("Pipeline execution failed", name=self.name, error=str(e))
            errors.append(e)

        execution_time = time.time() - start_time
        success = len(errors) == 0

        logger.info(
            "Pipeline execution completed",
            name=self.name,
            success=success,
            errors=len(errors),
            execution_time=execution_time,
        )

        return PipelineResult(
            success=success,
            results=results,
            errors=errors,
            execution_time=execution_time,
            processor_results=processor_results,
        )

    def _execute_processor(
        self, processor: ProcessorBase, name: str, data: Dict[str, Any]
    ) -> Any:
        """
        Execute single processor.

        Args:
            processor: Processor instance
            name: Processor name
            data: Input data

        Returns:
            Processor result
        """
        logger.debug("Executing processor", name=name)

        try:
            result = processor.process(data)
            logger.debug("Processor completed", name=name)
            return result
        except Exception as e:
            logger.error("Processor failed", name=name, error=str(e))
            raise

    def _handle_processor_error(self, name: str, error: Exception) -> None:
        """
        Handle processor error.

        Args:
            name: Processor name
            error: Exception that occurred
        """
        if name in self._error_handlers:
            try:
                self._error_handlers[name](error)
            except Exception as handler_error:
                logger.error(
                    "Error handler failed",
                    processor=name,
                    original_error=str(error),
                    handler_error=str(handler_error),
                )

    def get_processor_info(self) -> Dict[str, Any]:
        """
        Get information about pipeline processors.

        Returns:
            Dictionary with processor information
        """
        return {
            "name": self.name,
            "processors": [
                {
                    "name": name,
                    "type": type(processor).__name__,
                    "dependencies": self._dependencies.get(name, []),
                    "has_error_handler": name in self._error_handlers,
                }
                for name, processor in zip(self._processor_names, self._processors)
            ],
            "execution_order": self._resolve_execution_order(),
        }


class PipelineBuilder:
    """
    Builder for creating processor pipelines.

    Provides a fluent interface for constructing complex pipelines.
    """

    def __init__(self, name: str = "pipeline"):
        self.name = name
        self._configs: List[tuple] = []
        self._factory: Optional[ProcessorFactory] = None
        self._config_manager: Optional[ProcessorConfigManager] = None

    def with_factory(self, factory: ProcessorFactory) -> "PipelineBuilder":
        """Set processor factory."""
        self._factory = factory
        return self

    def with_config_manager(
        self, config_manager: ProcessorConfigManager
    ) -> "PipelineBuilder":
        """Set configuration manager."""
        self._config_manager = config_manager
        return self

    def add_processor(
        self,
        name: str,
        processor_type: str,
        config: Dict[str, Any],
        dependencies: Optional[List[str]] = None,
    ) -> "PipelineBuilder":
        """Add processor to pipeline."""
        processor_config = ProcessorConfig(
            processor_type=processor_type,
            config=config,
            dependencies=dependencies or [],
        )

        self._configs.append((name, processor_config, dependencies))
        return self

    def add_llm_summary(
        self,
        name: str = "summary",
        model: str = "gpt-3.5-turbo",
        dependencies: Optional[List[str]] = None,
        **kwargs,
    ) -> "PipelineBuilder":
        """Add LLM summary processor."""
        config = {"model": model, **kwargs}
        return self.add_processor(name, "llm_summary", config, dependencies)

    def add_llm_tags(
        self,
        name: str = "tags",
        model: str = "gpt-3.5-turbo",
        dependencies: Optional[List[str]] = None,
        **kwargs,
    ) -> "PipelineBuilder":
        """Add LLM tags processor."""
        config = {"model": model, **kwargs}
        return self.add_processor(name, "llm_tags", config, dependencies)

    def add_llm_keywords(
        self,
        name: str = "keywords",
        model: str = "gpt-3.5-turbo",
        dependencies: Optional[List[str]] = None,
        **kwargs,
    ) -> "PipelineBuilder":
        """Add LLM keywords processor."""
        config = {"model": model, **kwargs}
        return self.add_processor(name, "llm_keywords", config, dependencies)

    def add_html_content(
        self, name: str = "html", dependencies: Optional[List[str]] = None, **kwargs
    ) -> "PipelineBuilder":
        """Add HTML content processor."""
        return self.add_processor(name, "html_content", kwargs, dependencies)

    def build(self) -> ProcessorPipeline:
        """Build the pipeline."""
        pipeline = ProcessorPipeline(
            name=self.name, factory=self._factory, config_manager=self._config_manager
        )

        for name, config, dependencies in self._configs:
            pipeline.add_processor(name, config, dependencies)

        return pipeline


def create_default_pipeline(name: str = "default") -> ProcessorPipeline:
    """
    Create a default pipeline with common processors.

    Args:
        name: Pipeline name

    Returns:
        Configured pipeline
    """
    builder = PipelineBuilder(name)

    return (
        builder.add_html_content("html")
        .add_llm_summary("summary", dependencies=["html"])
        .add_llm_tags("tags", dependencies=["html"])
        .add_llm_keywords("keywords", dependencies=["html"])
        .build()
    )


def create_analysis_pipeline(name: str = "analysis") -> ProcessorPipeline:
    """
    Create a content analysis pipeline.

    Args:
        name: Pipeline name

    Returns:
        Configured pipeline
    """
    builder = PipelineBuilder(name)

    return (
        builder.add_html_content("html", clean_content=True)
        .add_llm_summary("summary", dependencies=["html"], temperature=0.3)
        .add_llm_tags("tags", dependencies=["summary"], temperature=0.5)
        .add_llm_keywords("keywords", dependencies=["summary"], temperature=0.3)
        .build()
    )
