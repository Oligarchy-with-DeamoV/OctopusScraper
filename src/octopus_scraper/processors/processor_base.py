"""
Abstract base class for all processors in the OctopusScraper system.

This module defines the core interface that all processors must implement,
providing a consistent API for content processing operations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import structlog

from octopus_scraper.processors.processor_config import ProcessorConfig
from octopus_scraper.protos import Content

logger = structlog.getLogger(__name__)


@dataclass
class ProcessingResult:
    """
    Result of a processing operation.

    Attributes:
        success: Whether the processing was successful
        content: The processed content (if successful)
        error: Error message (if failed)
        metadata: Additional metadata about the processing
    """

    success: bool
    content: Optional[Content] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ProcessorBase(ABC):
    """
    Abstract base class for all content processors.

    This class defines the core interface that all processors must implement,
    including initialization, content processing, and error handling.

    Attributes:
        config: Processor-specific configuration
        logger: Structured logger instance
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize the processor with configuration.

        Args:
            config: Dictionary containing processor configuration

        Raises:
            ValidationError: If configuration is invalid
        """
        self.config = self._parse_config(config)
        self.logger = structlog.getLogger(self.__class__.__name__)
        self._validate_config()
        self.logger.info("Processor initialized", processor=self.__class__.__name__)

    @abstractmethod
    def _parse_config(self, config: Dict[str, Any]) -> ProcessorConfig:
        """
        Parse and validate the configuration for this processor.

        Args:
            config: Raw configuration dictionary

        Returns:
            Parsed configuration object

        Raises:
            ValidationError: If configuration is invalid
        """
        pass

    def _validate_config(self) -> None:
        """
        Validate the processor configuration.

        This method can be overridden by subclasses to add specific validation logic.

        Raises:
            ValidationError: If configuration is invalid
        """
        # Basic validation can be added here
        pass

    @abstractmethod
    def __call__(self, contents: List[Content]) -> List[Content]:
        """
        Process a list of content items.

        This is the main entry point for content processing. Subclasses must
        implement this method to define their specific processing logic.

        Args:
            contents: List of content items to process

        Returns:
            List of processed content items

        Raises:
            ProcessingError: If processing fails
        """
        pass

    def process_single(self, content: Content) -> ProcessingResult:
        """
        Process a single content item with detailed result information.

        Args:
            content: Content item to process

        Returns:
            ProcessingResult with success status and details
        """
        try:
            processed_contents = self([content])
            if processed_contents and len(processed_contents) > 0:
                return ProcessingResult(
                    success=True,
                    content=processed_contents[0],
                    metadata={"processor": self.__class__.__name__},
                )
            else:
                return ProcessingResult(
                    success=False, error="No content returned from processor"
                )
        except Exception as e:
            self.logger.error(
                "Single content processing failed",
                error=str(e),
                content_id=content.content_id,
            )
            return ProcessingResult(
                success=False,
                error=str(e),
                metadata={"processor": self.__class__.__name__},
            )

    def batch_process(
        self, contents: List[Content], batch_size: int = 10
    ) -> List[ProcessingResult]:
        """
        Process contents in batches for better performance and error isolation.

        Args:
            contents: List of content items to process
            batch_size: Number of items to process in each batch

        Returns:
            List of ProcessingResult objects
        """
        results = []

        for i in range(0, len(contents), batch_size):
            batch = contents[i : i + batch_size]
            try:
                processed_batch = self(batch)
                for j, processed_content in enumerate(processed_batch):
                    results.append(
                        ProcessingResult(
                            success=True,
                            content=processed_content,
                            metadata={
                                "processor": self.__class__.__name__,
                                "batch_index": i // batch_size,
                                "item_index": j,
                            },
                        )
                    )
            except Exception as e:
                self.logger.error(
                    "Batch processing failed",
                    error=str(e),
                    batch_start=i,
                    batch_size=len(batch),
                )
                # Add failed results for each item in the batch
                for j, content in enumerate(batch):
                    results.append(
                        ProcessingResult(
                            success=False,
                            error=f"Batch processing failed: {str(e)}",
                            metadata={
                                "processor": self.__class__.__name__,
                                "batch_index": i // batch_size,
                                "item_index": j,
                                "original_content_id": content.content_id,
                            },
                        )
                    )

        return results

    @property
    def name(self) -> str:
        """Get the processor name."""
        return self.__class__.__name__

    @property
    def priority(self) -> int:
        """Get the processor priority (lower number = higher priority)."""
        return getattr(self.config, "priority", 100)

    def __str__(self) -> str:
        """String representation of the processor."""
        return f"{self.__class__.__name__}(priority={self.priority})"

    def __repr__(self) -> str:
        """Detailed string representation of the processor."""
        return f"{self.__class__.__name__}(config={self.config})"


class ProcessingError(Exception):
    """Exception raised when content processing fails."""

    def __init__(
        self,
        message: str,
        processor_name: str = None,
        content_id: str = None,
        original_error: Exception = None,
    ):
        """
        Initialize the processing error.

        Args:
            message: Error message
            processor_name: Name of the processor that failed
            content_id: ID of the content being processed
            original_error: Original exception that caused this error
        """
        super().__init__(message)
        self.processor_name = processor_name
        self.content_id = content_id
        self.original_error = original_error

    def __str__(self) -> str:
        """String representation of the error."""
        parts = [super().__str__()]
        if self.processor_name:
            parts.append(f"Processor: {self.processor_name}")
        if self.content_id:
            parts.append(f"Content ID: {self.content_id}")
        return " | ".join(parts)
