"""
LLM client interface for OctopusScraper.

This module provides a unified interface for interacting with different LLM providers,
including OpenAI, Anthropic, and other language models. It handles API calls, retries,
error handling, and response parsing.
"""

import json
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = structlog.getLogger(__name__)


class LLMProvider(Enum):
    """Supported LLM providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE_OPENAI = "azure_openai"
    LOCAL = "local"


@dataclass
class LLMConfig:
    """
    Configuration for LLM client.

    Attributes:
        provider: LLM provider to use
        model_name: Name of the model
        api_key: API key for authentication
        api_base: Base URL for API (optional)
        max_tokens: Maximum tokens in response
        temperature: Sampling temperature
        timeout: Request timeout in seconds
        retry_times: Number of retry attempts
    """

    provider: LLMProvider = LLMProvider.OPENAI
    model_name: str = "gpt-3.5-turbo"
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    max_tokens: int = 1000
    temperature: float = 0.7
    timeout: int = 30
    retry_times: int = 3


@dataclass
class LLMResponse:
    """
    Response from LLM API.

    Attributes:
        success: Whether the request was successful
        content: Generated content
        error: Error message if failed
        usage: Token usage information
        metadata: Additional response metadata
    """

    success: bool
    content: Optional[str] = None
    error: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    metadata: Optional[Dict[str, Any]] = None


class LLMError(Exception):
    """Base exception for LLM-related errors."""

    pass


class LLMRateLimitError(LLMError):
    """Exception raised when rate limit is exceeded."""

    pass


class LLMAuthenticationError(LLMError):
    """Exception raised when authentication fails."""

    pass


class LLMClient:
    """
    Unified client for interacting with different LLM providers.

    This class provides a consistent interface for making requests to various
    LLM providers, handling authentication, retries, and error scenarios.
    """

    def __init__(self, config: LLMConfig) -> None:
        """
        Initialize the LLM client.

        Args:
            config: LLM configuration

        Raises:
            LLMError: If configuration is invalid
        """
        self.config = config
        self.logger = structlog.getLogger(self.__class__.__name__)
        self._validate_config()
        self._setup_client()

        self.logger.info(
            "LLM client initialized",
            provider=config.provider.value,
            model=config.model_name,
        )

    def _validate_config(self) -> None:
        """
        Validate the LLM configuration.

        Raises:
            LLMError: If configuration is invalid
        """
        if not self.config.api_key and self.config.provider != LLMProvider.LOCAL:
            raise LLMError(
                f"API key required for provider: {self.config.provider.value}"
            )

        if self.config.max_tokens <= 0:
            raise LLMError("max_tokens must be positive")

        if not 0 <= self.config.temperature <= 2:
            raise LLMError("temperature must be between 0 and 2")

    def _setup_client(self) -> None:
        """Setup provider-specific client."""
        if self.config.provider == LLMProvider.OPENAI:
            self._setup_openai_client()
        elif self.config.provider == LLMProvider.ANTHROPIC:
            self._setup_anthropic_client()
        else:
            self.logger.warning(
                "Provider not fully implemented", provider=self.config.provider.value
            )

    def _setup_openai_client(self) -> None:
        """Setup OpenAI client."""
        try:
            from doraemon.gpt_utils.chatgpt_api import request_openai

            self._openai_request = request_openai
            self.logger.debug("OpenAI client setup complete")
        except ImportError as e:
            raise LLMError(f"Failed to import OpenAI dependencies: {e}")

    def _setup_anthropic_client(self) -> None:
        """Setup Anthropic client."""
        # Placeholder for Anthropic client setup
        self.logger.warning("Anthropic client not implemented yet")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((LLMRateLimitError, ConnectionError)),
    )
    def generate(self, messages: List[Dict[str, str]], **kwargs) -> LLMResponse:
        """
        Generate content using the configured LLM.

        Args:
            messages: List of message dictionaries with 'role' and 'content'
            **kwargs: Additional parameters to override config

        Returns:
            LLMResponse object with generation results

        Raises:
            LLMError: If generation fails
        """
        start_time = time.time()

        try:
            # Merge kwargs with config
            params = self._prepare_request_params(**kwargs)

            # Log request
            self.logger.debug(
                "Generating content",
                provider=self.config.provider.value,
                model=self.config.model_name,
                message_count=len(messages),
                max_tokens=params.get("max_tokens", self.config.max_tokens),
            )

            # Make request based on provider
            if self.config.provider == LLMProvider.OPENAI:
                response = self._generate_openai(messages, **params)
            elif self.config.provider == LLMProvider.ANTHROPIC:
                response = self._generate_anthropic(messages, **params)
            else:
                raise LLMError(f"Provider not supported: {self.config.provider.value}")
            from octopus_scraper.metrics import metrics

            metrics.record_external_request(
                "llm", time.time() - start_time, success=response.success
            )
            return response

        except Exception as e:
            duration = time.time() - start_time
            self.logger.error(
                "Content generation failed",
                error=str(e),
                provider=self.config.provider.value,
                duration=duration,
            )
            from octopus_scraper.metrics import metrics

            metrics.record_external_request("llm", duration, success=False)
            return LLMResponse(
                success=False, error=str(e), metadata={"duration": duration}
            )

    def _prepare_request_params(self, **kwargs) -> Dict[str, Any]:
        """Prepare request parameters by merging kwargs with config."""
        params = {
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
            "timeout": kwargs.get("timeout", self.config.timeout),
        }
        return params

    def _generate_openai(self, messages: List[Dict[str, str]], **params) -> LLMResponse:
        """
        Generate content using OpenAI API.

        Args:
            messages: List of message dictionaries
            **params: Request parameters

        Returns:
            LLMResponse object
        """
        try:
            success, result = self._openai_request(messages)

            if success:
                return LLMResponse(
                    success=True,
                    content=result,
                    metadata={
                        "provider": self.config.provider.value,
                        "model": self.config.model_name,
                    },
                )
            else:
                return LLMResponse(
                    success=False,
                    error=result,
                    metadata={
                        "provider": self.config.provider.value,
                        "model": self.config.model_name,
                    },
                )

        except Exception as e:
            self.logger.error("OpenAI request failed", error=str(e))
            return LLMResponse(success=False, error=f"OpenAI request failed: {str(e)}")

    def _generate_anthropic(
        self, messages: List[Dict[str, str]], **params
    ) -> LLMResponse:
        """
        Generate content using Anthropic API.

        Args:
            messages: List of message dictionaries
            **params: Request parameters

        Returns:
            LLMResponse object
        """
        # Placeholder for Anthropic implementation
        return LLMResponse(
            success=False, error="Anthropic provider not implemented yet"
        )

    def generate_structured(
        self, messages: List[Dict[str, str]], schema: Dict[str, Any], **kwargs
    ) -> LLMResponse:
        """
        Generate structured content that conforms to a JSON schema.

        Args:
            messages: List of message dictionaries
            schema: JSON schema for validation
            **kwargs: Additional parameters

        Returns:
            LLMResponse with structured content
        """
        # Add schema instructions to the last message
        schema_instruction = (
            f"\n\nPlease respond with valid JSON that conforms to this schema:\n"
            f"```json\n{json.dumps(schema, indent=2)}\n```\n"
            f"Wrap your JSON response in ```json``` code blocks."
        )

        if messages and messages[-1].get("role") == "user":
            messages[-1]["content"] += schema_instruction
        else:
            messages.append({"role": "user", "content": schema_instruction})

        response = self.generate(messages, **kwargs)

        if response.success and response.content:
            try:
                # Extract JSON from response
                json_content = self._extract_json_from_response(response.content)
                if json_content:
                    # Validate against schema
                    from octopus_scraper.utils.validators import validate_json_schema

                    is_valid, error = validate_json_schema(json_content, schema)

                    if is_valid:
                        response.content = json.dumps(json_content)
                        response.metadata = response.metadata or {}
                        response.metadata["structured"] = True
                    else:
                        response.success = False
                        response.error = f"Schema validation failed: {error}"
                else:
                    response.success = False
                    response.error = "No valid JSON found in response"

            except Exception as e:
                response.success = False
                response.error = f"Structured response processing failed: {str(e)}"

        return response

    def _extract_json_from_response(self, content: str) -> Optional[Dict[str, Any]]:
        """
        Extract JSON content from LLM response.

        Args:
            content: Raw response content

        Returns:
            Parsed JSON object or None
        """
        # Try to find JSON in code blocks first
        json_pattern = r"```json\s*(.*?)\s*```"
        matches = re.findall(json_pattern, content, re.DOTALL)

        if matches:
            for match in matches:
                try:
                    return json.loads(match.strip())
                except json.JSONDecodeError:
                    continue

        # Try to parse the entire content as JSON
        try:
            return json.loads(content.strip())
        except json.JSONDecodeError:
            pass

        # Try to find JSON-like content
        json_like_pattern = r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}"
        matches = re.findall(json_like_pattern, content)

        for match in matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue

        return None

    def health_check(self) -> bool:
        """
        Check if the LLM service is healthy.

        Returns:
            True if service is healthy, False otherwise
        """
        try:
            test_messages = [
                {"role": "user", "content": "Hello, please respond with 'OK'"}
            ]
            response = self.generate(test_messages, max_tokens=10)
            return response.success
        except Exception as e:
            self.logger.error("Health check failed", error=str(e))
            return False

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate the number of tokens in a text.

        Args:
            text: Text to estimate tokens for

        Returns:
            Estimated token count
        """
        # Simple estimation: ~4 characters per token for English
        return len(text) // 4 + 1

    def __str__(self) -> str:
        """String representation of the client."""
        return f"LLMClient(provider={self.config.provider.value}, model={self.config.model_name})"
