"""Shared helpers for structured LLM processors."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Dict, List

from octopus_scraper.llm.client import LLMClient
from octopus_scraper.processors.processor_base import ProcessingError
from octopus_scraper.protos import Content
from octopus_scraper.utils.validators import DataValidator


class StructuredLLMProcessorHelper:
    """Reusable behavior for LLM processors that expect JSON output."""

    @staticmethod
    def generate_cache_key(
        processor_type: str,
        content: Content,
        config_values: Dict[str, Any],
    ) -> str:
        """Generate a stable content/config digest for processor cache entries."""
        key_data = {
            "processor_type": processor_type,
            "title": content.title,
            "content": content.content,
            "config": config_values,
        }
        serialized = json.dumps(
            key_data,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def generate_structured_data(
        llm_client: LLMClient,
        validator: DataValidator,
        messages: List[Dict[str, str]],
        schema: Dict[str, Any],
        fix_response: Callable[[Dict[str, Any]], Dict[str, Any]],
        invalid_schema_event: str,
    ) -> Dict[str, Any]:
        """Generate, parse, validate, and repair structured JSON output."""
        response = llm_client.generate(messages)
        if not response.success:
            raise ProcessingError(
                f"LLM generation failed: {response.content or response.error}"
            )

        json_content = llm_client.extract_json_from_response(response.content or "")
        structured_data = json.loads(json_content)

        if not validator.validate_json(structured_data, schema):
            import structlog

            structlog.getLogger(__name__).warning(
                invalid_schema_event,
                data=structured_data,
            )
            structured_data = fix_response(structured_data)

        return structured_data
