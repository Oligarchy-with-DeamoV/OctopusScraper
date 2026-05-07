"""Tests for LLMClient."""

import json
from unittest.mock import MagicMock, patch

import pytest

from octopus_scraper.llm.client import (
    LLMClient,
    LLMConfig,
    LLMError,
    LLMProvider,
    LLMResponse,
)


class TestLLMConfig:
    def test_default_values(self):
        config = LLMConfig()
        assert config.provider == LLMProvider.OPENAI
        assert config.model_name == "gpt-3.5-turbo"
        assert config.max_tokens == 1000
        assert config.temperature == 0.7
        assert config.timeout == 30

    def test_custom_values(self):
        config = LLMConfig(
            provider=LLMProvider.ANTHROPIC,
            model_name="claude-3",
            api_key="key",
            max_tokens=2000,
        )
        assert config.provider == LLMProvider.ANTHROPIC
        assert config.max_tokens == 2000


class TestLLMResponse:
    def test_success_response(self):
        resp = LLMResponse(success=True, content="hello")
        assert resp.success is True
        assert resp.content == "hello"
        assert resp.error is None

    def test_failure_response(self):
        resp = LLMResponse(success=False, error="failed")
        assert resp.success is False
        assert resp.error == "failed"


class TestLLMClientValidation:
    def test_missing_api_key_raises(self):
        config = LLMConfig(provider=LLMProvider.OPENAI, api_key=None)
        with pytest.raises(LLMError, match="API key required"):
            LLMClient(config)

    def test_local_provider_no_api_key_ok(self):
        config = LLMConfig(provider=LLMProvider.LOCAL, api_key=None)
        # LOCAL provider doesn't require API key; should not raise on validation
        # but may warn about not being fully implemented
        client = LLMClient(config)
        assert client.config.provider == LLMProvider.LOCAL

    def test_negative_max_tokens_raises(self):
        config = LLMConfig(api_key="key", max_tokens=-1)
        with pytest.raises(LLMError, match="max_tokens must be positive"):
            LLMClient(config)

    def test_zero_max_tokens_raises(self):
        config = LLMConfig(api_key="key", max_tokens=0)
        with pytest.raises(LLMError, match="max_tokens must be positive"):
            LLMClient(config)

    def test_temperature_too_high_raises(self):
        config = LLMConfig(api_key="key", temperature=3.0)
        with pytest.raises(LLMError, match="temperature must be between"):
            LLMClient(config)

    def test_temperature_negative_raises(self):
        config = LLMConfig(api_key="key", temperature=-0.1)
        with pytest.raises(LLMError, match="temperature must be between"):
            LLMClient(config)


class TestLLMClientSetup:
    @patch("octopus_scraper.llm.client.LLMClient._setup_openai_client")
    def test_openai_setup_called(self, mock_setup):
        config = LLMConfig(provider=LLMProvider.OPENAI, api_key="key")
        client = LLMClient(config)
        mock_setup.assert_called_once()

    @patch("octopus_scraper.llm.client.LLMClient._setup_anthropic_client")
    def test_anthropic_setup_called(self, mock_setup):
        config = LLMConfig(provider=LLMProvider.ANTHROPIC, api_key="key")
        client = LLMClient(config)
        mock_setup.assert_called_once()


class TestLLMClientGenerate:
    @pytest.fixture
    def openai_client(self):
        with patch("octopus_scraper.llm.client.LLMClient._setup_openai_client"):
            config = LLMConfig(provider=LLMProvider.OPENAI, api_key="key")
            client = LLMClient(config)
            client._openai_request = MagicMock(return_value=(True, "generated text"))
            return client

    def test_generate_success(self, openai_client):
        messages = [{"role": "user", "content": "Hello"}]
        response = openai_client.generate(messages)
        assert response.success is True
        assert response.content == "generated text"

    def test_generate_api_failure(self, openai_client):
        openai_client._openai_request = MagicMock(return_value=(False, "API error"))
        messages = [{"role": "user", "content": "Hello"}]
        response = openai_client.generate(messages)
        assert response.success is False
        assert response.error == "API error"

    def test_generate_exception(self, openai_client):
        openai_client._openai_request = MagicMock(side_effect=Exception("network err"))
        messages = [{"role": "user", "content": "Hello"}]
        response = openai_client.generate(messages)
        assert response.success is False
        assert "network err" in response.error

    def test_generate_with_kwargs(self, openai_client):
        messages = [{"role": "user", "content": "Hello"}]
        response = openai_client.generate(messages, max_tokens=500, temperature=0.5)
        assert response.success is True

    def test_generate_anthropic_not_implemented(self):
        with patch("octopus_scraper.llm.client.LLMClient._setup_anthropic_client"):
            config = LLMConfig(provider=LLMProvider.ANTHROPIC, api_key="key")
            client = LLMClient(config)
            messages = [{"role": "user", "content": "Hello"}]
            response = client.generate(messages)
            assert response.success is False
            assert "not implemented" in response.error.lower()


class TestLLMClientPrepareParams:
    @pytest.fixture
    def client(self):
        with patch("octopus_scraper.llm.client.LLMClient._setup_openai_client"):
            config = LLMConfig(
                provider=LLMProvider.OPENAI,
                api_key="key",
                max_tokens=1000,
                temperature=0.7,
                timeout=30,
            )
            return LLMClient(config)

    def test_defaults_from_config(self, client):
        params = client._prepare_request_params()
        assert params["max_tokens"] == 1000
        assert params["temperature"] == 0.7
        assert params["timeout"] == 30

    def test_overrides(self, client):
        params = client._prepare_request_params(max_tokens=500, temperature=0.1)
        assert params["max_tokens"] == 500
        assert params["temperature"] == 0.1


class TestLLMClientExtractJson:
    @pytest.fixture
    def client(self):
        with patch("octopus_scraper.llm.client.LLMClient._setup_openai_client"):
            config = LLMConfig(provider=LLMProvider.OPENAI, api_key="key")
            return LLMClient(config)

    def test_json_in_code_block(self, client):
        content = '```json\n{"key": "value"}\n```'
        result = client._extract_json_from_response(content)
        assert result == {"key": "value"}

    def test_raw_json(self, client):
        content = '{"key": "value"}'
        result = client._extract_json_from_response(content)
        assert result == {"key": "value"}

    def test_json_in_text(self, client):
        content = 'Here is the result: {"key": "value"} done'
        result = client._extract_json_from_response(content)
        assert result == {"key": "value"}

    def test_no_json(self, client):
        result = client._extract_json_from_response("no json here")
        assert result is None

    def test_invalid_json_returns_none(self, client):
        result = client._extract_json_from_response("```json\n{bad}\n```")
        assert result is None


class TestLLMClientHealthCheck:
    def test_health_check_success(self):
        with patch("octopus_scraper.llm.client.LLMClient._setup_openai_client"):
            config = LLMConfig(provider=LLMProvider.OPENAI, api_key="key")
            client = LLMClient(config)
            client._openai_request = MagicMock(return_value=(True, "OK"))
            assert client.health_check() is True

    def test_health_check_failure(self):
        with patch("octopus_scraper.llm.client.LLMClient._setup_openai_client"):
            config = LLMConfig(provider=LLMProvider.OPENAI, api_key="key")
            client = LLMClient(config)
            client._openai_request = MagicMock(return_value=(False, "error"))
            assert client.health_check() is False

    def test_health_check_exception(self):
        with patch("octopus_scraper.llm.client.LLMClient._setup_openai_client"):
            config = LLMConfig(provider=LLMProvider.OPENAI, api_key="key")
            client = LLMClient(config)
            client._openai_request = MagicMock(side_effect=Exception("down"))
            assert client.health_check() is False


class TestLLMClientGenerateStructured:
    @pytest.fixture
    def client(self):
        with patch("octopus_scraper.llm.client.LLMClient._setup_openai_client"):
            config = LLMConfig(provider=LLMProvider.OPENAI, api_key="key")
            client = LLMClient(config)
            return client

    def test_structured_no_json_in_response(self, client):
        client._openai_request = MagicMock(return_value=(True, "plain text no json"))
        messages = [{"role": "user", "content": "Generate data"}]
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        response = client.generate_structured(messages, schema)
        assert response.success is False
        assert "No valid JSON" in response.error

    def test_structured_generation_failure(self, client):
        client._openai_request = MagicMock(return_value=(False, "API error"))
        messages = [{"role": "user", "content": "Generate data"}]
        schema = {"type": "object"}
        response = client.generate_structured(messages, schema)
        assert response.success is False


class TestLLMProviderEnum:
    def test_values(self):
        assert LLMProvider.OPENAI.value == "openai"
        assert LLMProvider.ANTHROPIC.value == "anthropic"
        assert LLMProvider.AZURE_OPENAI.value == "azure_openai"
        assert LLMProvider.LOCAL.value == "local"
