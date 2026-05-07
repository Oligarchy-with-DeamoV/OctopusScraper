"""
OctopusScraper Processors Module.

This module provides a comprehensive processing system with multiple specialized processors
for content analysis, summarization, tagging, and keyword extraction.
"""

from typing import Any, Dict, List, Optional, Type

import structlog

from octopus_scraper.processors.html_content_processor import HTMLContentProcessor
from octopus_scraper.processors.llm_keywords_processor import LLMKeywordsProcessor
from octopus_scraper.processors.llm_processor import LLMProcessor
from octopus_scraper.processors.llm_summary_processor import LLMSummaryProcessor
from octopus_scraper.processors.llm_tags_processor import LLMTagsProcessor
from octopus_scraper.processors.processor_base import ProcessorBase

logger = structlog.getLogger(__name__)


class ProcessorRegistry:
    """
    Registry for managing processor types and creation.

    Provides a centralized system for registering, discovering, and creating
    processor instances with dependency management and validation.
    """

    def __init__(self):
        self._processors: Dict[str, Type[ProcessorBase]] = {}
        self._register_builtin_processors()

    def _register_builtin_processors(self):
        """Register all built-in processors."""
        self.register("html_content", HTMLContentProcessor)
        self.register("llm", LLMProcessor)  # Legacy LLM processor
        self.register("llm_summary", LLMSummaryProcessor)
        self.register("llm_tags", LLMTagsProcessor)
        self.register("llm_keywords", LLMKeywordsProcessor)

        logger.info("Registered built-in processors", count=len(self._processors))

    def register(self, name: str, processor_class: Type[ProcessorBase]) -> None:
        """
        Register a processor class.

        Args:
            name: Unique name for the processor
            processor_class: Processor class that inherits from ProcessorBase

        Raises:
            ValueError: If name is already registered or processor_class is invalid
        """
        if name in self._processors:
            logger.warning("Processor name already registered, overwriting", name=name)

        if not issubclass(processor_class, ProcessorBase):
            raise ValueError(
                f"Processor class must inherit from ProcessorBase: {processor_class}"
            )

        self._processors[name] = processor_class
        logger.debug(
            "Processor registered", name=name, class_name=processor_class.__name__
        )

    def unregister(self, name: str) -> None:
        """
        Unregister a processor.

        Args:
            name: Name of processor to unregister
        """
        if name in self._processors:
            del self._processors[name]
            logger.debug("Processor unregistered", name=name)

    def get_processor_class(self, name: str) -> Type[ProcessorBase]:
        """
        Get processor class by name.

        Args:
            name: Processor name

        Returns:
            Processor class

        Raises:
            KeyError: If processor not found
        """
        if name not in self._processors:
            raise KeyError(
                f"Unknown processor: {name}. Available: {list(self._processors.keys())}"
            )

        return self._processors[name]

    def create_processor(self, name: str, config: Dict[str, Any]) -> ProcessorBase:
        """
        Create processor instance with configuration.

        Args:
            name: Processor name
            config: Processor configuration

        Returns:
            Configured processor instance

        Raises:
            KeyError: If processor not found
            ValueError: If configuration is invalid
        """
        processor_class = self.get_processor_class(name)

        try:
            processor = processor_class(config)
            logger.info(
                "Processor created", name=name, class_name=processor_class.__name__
            )
            return processor
        except Exception as e:
            logger.error("Failed to create processor", name=name, error=str(e))
            raise ValueError(f"Failed to create processor '{name}': {e}")

    def list_processors(self) -> List[str]:
        """
        List all registered processor names.

        Returns:
            List of processor names
        """
        return list(self._processors.keys())

    def get_processor_info(self, name: str) -> Dict[str, Any]:
        """
        Get information about a processor.

        Args:
            name: Processor name

        Returns:
            Dictionary with processor information
        """
        if name not in self._processors:
            raise KeyError(f"Unknown processor: {name}")

        processor_class = self._processors[name]
        return {
            "name": name,
            "class_name": processor_class.__name__,
            "module": processor_class.__module__,
            "doc": processor_class.__doc__ or "No documentation available",
        }


class ProcessorFactory:
    """
    Factory for creating and managing processor instances.

    Provides high-level interface for processor creation with configuration
    validation and dependency management.
    """

    def __init__(self, registry: Optional[ProcessorRegistry] = None):
        self.registry = registry or ProcessorRegistry()

    def create_processor(
        self, processor_type: str, config: Dict[str, Any]
    ) -> ProcessorBase:
        """
        Create a processor instance.

        Args:
            processor_type: Type of processor to create
            config: Processor configuration

        Returns:
            Configured processor instance
        """
        return self.registry.create_processor(processor_type, config)

    def create_processor_chain(
        self, processor_configs: List[Dict[str, Any]]
    ) -> List[ProcessorBase]:
        """
        Create a chain of processors.

        Args:
            processor_configs: List of processor configurations with 'type' and other config

        Returns:
            List of configured processors
        """
        processors = []

        for config in processor_configs:
            if "type" not in config:
                raise ValueError("Processor config must include 'type' field")

            processor_type = config.pop("type")
            processor = self.create_processor(processor_type, config)
            processors.append(processor)

        logger.info("Created processor chain", count=len(processors))
        return processors

    def get_available_processors(self) -> List[str]:
        """Get list of available processor types."""
        return self.registry.list_processors()


# Global registry and factory instances
_registry = ProcessorRegistry()
_factory = ProcessorFactory(_registry)


def register_processor(name: str, processor_class: Type[ProcessorBase]) -> None:
    """
    Register a custom processor globally.

    Args:
        name: Unique name for the processor
        processor_class: Processor class that inherits from ProcessorBase
    """
    _registry.register(name, processor_class)


def create_processor(processor_type: str, config: Dict[str, Any]) -> ProcessorBase:
    """
    Create a processor instance using the global factory.

    Args:
        processor_type: Type of processor to create
        config: Processor configuration

    Returns:
        Configured processor instance
    """
    return _factory.create_processor(processor_type, config)


def get_available_processors() -> List[str]:
    """Get list of available processor types."""
    return _factory.get_available_processors()


def get_processor_info(name: str) -> Dict[str, Any]:
    """Get information about a processor."""
    return _registry.get_processor_info(name)


# Legacy compatibility - maintain existing API
# NOTE: "AVALIABLE" is a known typo preserved for backward compatibility.
# Prefer using the ProcessorRegistry/ProcessorFactory API instead.
AVAILABLE_PROCESSOR = {
    "llm": LLMProcessor,
    "html_content": HTMLContentProcessor,
    "llm_summary": LLMSummaryProcessor,
    "llm_tags": LLMTagsProcessor,
    "llm_keywords": LLMKeywordsProcessor,
}

# Deprecated alias — will be removed in a future release
AVALIABLE_PROCESSOR = AVAILABLE_PROCESSOR


# Export public API
__all__ = [
    "ProcessorRegistry",
    "ProcessorFactory",
    "register_processor",
    "create_processor",
    "get_available_processors",
    "get_processor_info",
    "AVAILABLE_PROCESSOR",
    "AVALIABLE_PROCESSOR",  # Deprecated alias
    # Processor classes
    "ProcessorBase",
    "HTMLContentProcessor",
    "LLMProcessor",
    "LLMSummaryProcessor",
    "LLMTagsProcessor",
    "LLMKeywordsProcessor",
]
