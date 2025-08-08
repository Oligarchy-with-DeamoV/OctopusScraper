"""
Simple additional tests for LLM client module.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from octopus_scraper.llm.client import LLMClient


class TestLLMClientSimple:
    """Simple tests to improve LLM client coverage."""

    def test_init(self):
        """Test client initialization."""
        client = LLMClient(
            api_key="test_key", base_url="http://test.com", model="test-model"
        )
        assert client.model == "test-model"
        assert client.base_url == "http://test.com"

    @pytest.mark.asyncio
    async def test_generate_completion_basic(self):
        """Test basic completion generation."""
        client = LLMClient(api_key="test", base_url="http://test.com", model="test")

        with patch.object(client.client.chat.completions, "create") as mock_create:
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = "Test response"
            mock_create.return_value = mock_response

            result = await client.generate_completion("Test prompt")
            assert result == "Test response"

    @pytest.mark.asyncio
    async def test_generate_structured_completion_basic(self):
        """Test structured completion generation."""
        client = LLMClient(api_key="test", base_url="http://test.com", model="test")

        with patch.object(client.client.chat.completions, "create") as mock_create:
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = '{"key": "value"}'
            mock_create.return_value = mock_response

            schema = {"type": "object", "properties": {"key": {"type": "string"}}}
            result = await client.generate_structured_completion("Test prompt", schema)
            assert isinstance(result, dict)

    def test_validate_response_basic(self):
        """Test response validation."""
        client = LLMClient(api_key="test", base_url="http://test.com", model="test")

        # Test valid response
        assert client.validate_response("Valid response") is True

        # Test empty response
        assert client.validate_response("") is False

        # Test None response
        assert client.validate_response(None) is False
