"""
Tests for processor configuration system.
"""

from unittest.mock import Mock

import pytest

from octopus_scraper.processors.processor_config import (
    DEFAULT_CONFIGS,
    ProcessorConfig,
    ProcessorConfigManager,
    create_html_config,
    create_llm_config,
)


class TestProcessorConfig:
    """Test cases for ProcessorConfig."""

    def test_config_creation(self):
        """Test basic config creation."""
        config = ProcessorConfig(
            processor_type="llm_summary",
            config={"model": "gpt-3.5-turbo"},
            enabled=True,
            priority=100,
        )

        assert config.processor_type == "llm_summary"
        assert config.config == {"model": "gpt-3.5-turbo"}
        assert config.enabled is True
        assert config.priority == 100
        assert config.dependencies == []

    def test_config_with_dependencies(self):
        """Test config with dependencies."""
        config = ProcessorConfig(
            processor_type="llm_tags",
            dependencies=["html_processor", "summary_processor"],
        )

        assert config.dependencies == ["html_processor", "summary_processor"]

    def test_config_validation_empty_type(self):
        """Test config validation with empty processor type."""
        with pytest.raises(ValueError, match="processor_type cannot be empty"):
            ProcessorConfig(processor_type="")

    def test_config_validation_invalid_config(self):
        """Test config validation with invalid config type."""
        with pytest.raises(ValueError, match="config must be a dictionary"):
            ProcessorConfig(processor_type="test", config="invalid")

    def test_get_config_value(self):
        """Test getting configuration values."""
        config = ProcessorConfig(
            processor_type="test", config={"key1": "value1", "key2": "value2"}
        )

        assert config.get_config_value("key1") == "value1"
        assert config.get_config_value("key2") == "value2"
        assert config.get_config_value("nonexistent") is None
        assert config.get_config_value("nonexistent", "default") == "default"

    def test_set_config_value(self):
        """Test setting configuration values."""
        config = ProcessorConfig(processor_type="test")

        config.set_config_value("new_key", "new_value")
        assert config.config["new_key"] == "new_value"

    def test_merge_config(self):
        """Test merging configuration."""
        config = ProcessorConfig(processor_type="test", config={"key1": "value1"})

        config.merge_config({"key2": "value2", "key3": "value3"})

        assert config.config == {"key1": "value1", "key2": "value2", "key3": "value3"}


class TestProcessorConfigManager:
    """Test cases for ProcessorConfigManager."""

    def test_manager_initialization(self):
        """Test manager initialization."""
        manager = ProcessorConfigManager()

        assert len(manager.list_configurations()) == 0

    def test_add_and_get_config(self):
        """Test adding and getting configuration."""
        manager = ProcessorConfigManager()
        config = ProcessorConfig(processor_type="test")

        manager.add_config("test_config", config)

        assert "test_config" in manager.list_configurations()
        retrieved_config = manager.get_config("test_config")
        assert retrieved_config == config

    def test_get_nonexistent_config(self):
        """Test getting nonexistent configuration."""
        manager = ProcessorConfigManager()

        with pytest.raises(KeyError, match="Configuration not found: nonexistent"):
            manager.get_config("nonexistent")

    def test_remove_config(self):
        """Test removing configuration."""
        manager = ProcessorConfigManager()
        config = ProcessorConfig(processor_type="test")

        manager.add_config("test_config", config)
        assert "test_config" in manager.list_configurations()

        manager.remove_config("test_config")
        assert "test_config" not in manager.list_configurations()

    def test_create_profile(self):
        """Test creating processor profile."""
        manager = ProcessorConfigManager()

        config1 = ProcessorConfig(processor_type="type1")
        config2 = ProcessorConfig(processor_type="type2")

        manager.add_config("config1", config1)
        manager.add_config("config2", config2)

        manager.create_profile("test_profile", ["config1", "config2"])

        profile = manager.get_profile("test_profile")
        assert len(profile) == 2
        assert profile[0] == config1
        assert profile[1] == config2

    def test_create_profile_with_nonexistent_config(self):
        """Test creating profile with nonexistent configuration."""
        manager = ProcessorConfigManager()

        with pytest.raises(KeyError, match="Configuration not found: nonexistent"):
            manager.create_profile("test_profile", ["nonexistent"])

    def test_get_nonexistent_profile(self):
        """Test getting nonexistent profile."""
        manager = ProcessorConfigManager()

        with pytest.raises(KeyError, match="Profile not found: nonexistent"):
            manager.get_profile("nonexistent")

    def test_validate_configuration_valid(self):
        """Test validating valid configuration."""
        manager = ProcessorConfigManager()
        config = ProcessorConfig(
            processor_type="llm_summary",
            config={"model": "gpt-3.5-turbo"},
            priority=100,
        )

        errors = manager.validate_configuration(config)
        assert len(errors) == 0

    def test_validate_configuration_invalid(self):
        """Test validating invalid configuration."""
        manager = ProcessorConfigManager()

        # Valid processor type but negative priority
        config2 = ProcessorConfig(processor_type="test", priority=-1)
        errors2 = manager.validate_configuration(config2)
        assert "priority must be non-negative" in errors2

        # LLM processor without model
        config3 = ProcessorConfig(processor_type="llm_summary", config={})
        errors3 = manager.validate_configuration(config3)
        assert "LLM processors require 'model' configuration" in errors3

    def test_load_from_dict(self):
        """Test loading configurations from dictionary."""
        manager = ProcessorConfigManager()

        config_dict = {
            "config1": {
                "type": "llm_summary",
                "config": {"model": "gpt-3.5-turbo"},
                "enabled": True,
                "priority": 100,
                "dependencies": ["html"],
            },
            "config2": {"type": "html_content", "config": {"clean": True}},
        }

        manager.load_from_dict(config_dict)

        assert len(manager.list_configurations()) == 2

        config1 = manager.get_config("config1")
        assert config1.processor_type == "llm_summary"
        assert config1.config == {"model": "gpt-3.5-turbo"}
        assert config1.dependencies == ["html"]

        config2 = manager.get_config("config2")
        assert config2.processor_type == "html_content"
        assert config2.enabled is True  # Default value

    def test_to_dict(self):
        """Test exporting configurations to dictionary."""
        manager = ProcessorConfigManager()

        config = ProcessorConfig(
            processor_type="llm_summary",
            config={"model": "gpt-3.5-turbo"},
            enabled=True,
            priority=100,
            dependencies=["html"],
        )

        manager.add_config("test_config", config)

        result = manager.to_dict()

        expected = {
            "test_config": {
                "type": "llm_summary",
                "config": {"model": "gpt-3.5-turbo"},
                "enabled": True,
                "priority": 100,
                "dependencies": ["html"],
            }
        }

        assert result == expected


class TestConfigHelpers:
    """Test cases for configuration helper functions."""

    def test_create_llm_config_basic(self):
        """Test creating basic LLM configuration."""
        config = create_llm_config()

        assert config["model"] == "gpt-3.5-turbo"
        assert config["temperature"] == 0.7
        assert "api_key" not in config
        assert "max_tokens" not in config

    def test_create_llm_config_with_params(self):
        """Test creating LLM configuration with parameters."""
        config = create_llm_config(
            model="gpt-4",
            api_key="test_key",
            temperature=0.5,
            max_tokens=1000,
            custom_param="value",
        )

        assert config["model"] == "gpt-4"
        assert config["api_key"] == "test_key"
        assert config["temperature"] == 0.5
        assert config["max_tokens"] == 1000
        assert config["custom_param"] == "value"

    def test_create_html_config_basic(self):
        """Test creating basic HTML configuration."""
        config = create_html_config()

        assert config["clean_content"] is True
        assert config["extract_links"] is False
        assert config["extract_images"] is False

    def test_create_html_config_with_params(self):
        """Test creating HTML configuration with parameters."""
        config = create_html_config(
            clean_content=False,
            extract_links=True,
            extract_images=True,
            custom_param="value",
        )

        assert config["clean_content"] is False
        assert config["extract_links"] is True
        assert config["extract_images"] is True
        assert config["custom_param"] == "value"


class TestDefaultConfigs:
    """Test cases for default configurations."""

    def test_default_configs_exist(self):
        """Test that default configurations exist."""
        assert "llm_summary_default" in DEFAULT_CONFIGS
        assert "llm_tags_default" in DEFAULT_CONFIGS
        assert "llm_keywords_default" in DEFAULT_CONFIGS
        assert "html_content_default" in DEFAULT_CONFIGS

    def test_default_configs_structure(self):
        """Test default configurations structure."""
        for name, config in DEFAULT_CONFIGS.items():
            assert isinstance(config, ProcessorConfig)
            assert config.processor_type
            assert isinstance(config.config, dict)
            assert isinstance(config.priority, int)

    def test_llm_summary_default_config(self):
        """Test LLM summary default configuration."""
        config = DEFAULT_CONFIGS["llm_summary_default"]

        assert config.processor_type == "llm_summary"
        assert config.config["model"] == "gpt-3.5-turbo"
        assert config.config["temperature"] == 0.3
        assert config.priority == 100

    def test_html_content_default_config(self):
        """Test HTML content default configuration."""
        config = DEFAULT_CONFIGS["html_content_default"]

        assert config.processor_type == "html_content"
        assert config.config["clean_content"] is True
        assert config.priority == 200
