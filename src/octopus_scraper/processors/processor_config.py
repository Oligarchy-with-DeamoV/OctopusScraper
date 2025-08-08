"""
Processor Configuration Management.

This module provides configuration validation and management for processors,
ensuring proper configuration structure and validation rules.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

import structlog

logger = structlog.getLogger(__name__)


@dataclass
class ProcessorConfig:
    """
    Configuration container for processor instances.

    Provides validation and type checking for processor configurations.
    """

    processor_type: str
    config: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    priority: int = 100
    dependencies: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Validate configuration after initialization."""
        if not self.processor_type:
            raise ValueError("processor_type cannot be empty")

        if not isinstance(self.config, dict):
            raise ValueError("config must be a dictionary")

    def get_config_value(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value with default fallback.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value
        """
        return self.config.get(key, default)

    def set_config_value(self, key: str, value: Any) -> None:
        """
        Set configuration value.

        Args:
            key: Configuration key
            value: Configuration value
        """
        self.config[key] = value

    def merge_config(self, other_config: Dict[str, Any]) -> None:
        """
        Merge additional configuration.

        Args:
            other_config: Additional configuration to merge
        """
        self.config.update(other_config)


class ProcessorConfigManager:
    """
    Manager for processor configurations.

    Handles loading, validation, and management of processor configurations
    with support for profiles and inheritance.
    """

    def __init__(self):
        self._configurations: Dict[str, ProcessorConfig] = {}
        self._profiles: Dict[str, List[ProcessorConfig]] = {}

    def add_config(self, name: str, config: ProcessorConfig) -> None:
        """
        Add a processor configuration.

        Args:
            name: Configuration name
            config: Processor configuration
        """
        self._configurations[name] = config
        logger.debug(
            "Added processor configuration", name=name, type=config.processor_type
        )

    def get_config(self, name: str) -> ProcessorConfig:
        """
        Get processor configuration by name.

        Args:
            name: Configuration name

        Returns:
            Processor configuration

        Raises:
            KeyError: If configuration not found
        """
        if name not in self._configurations:
            raise KeyError(f"Configuration not found: {name}")

        return self._configurations[name]

    def remove_config(self, name: str) -> None:
        """
        Remove processor configuration.

        Args:
            name: Configuration name
        """
        if name in self._configurations:
            del self._configurations[name]
            logger.debug("Removed processor configuration", name=name)

    def list_configurations(self) -> List[str]:
        """
        List all configuration names.

        Returns:
            List of configuration names
        """
        return list(self._configurations.keys())

    def create_profile(self, profile_name: str, config_names: List[str]) -> None:
        """
        Create a processor profile.

        Args:
            profile_name: Profile name
            config_names: List of configuration names to include

        Raises:
            KeyError: If any configuration name not found
        """
        configs = []
        for name in config_names:
            if name not in self._configurations:
                raise KeyError(f"Configuration not found: {name}")
            configs.append(self._configurations[name])

        self._profiles[profile_name] = configs
        logger.info(
            "Created processor profile", profile=profile_name, configs=len(configs)
        )

    def get_profile(self, profile_name: str) -> List[ProcessorConfig]:
        """
        Get processor configurations for a profile.

        Args:
            profile_name: Profile name

        Returns:
            List of processor configurations

        Raises:
            KeyError: If profile not found
        """
        if profile_name not in self._profiles:
            raise KeyError(f"Profile not found: {profile_name}")

        return self._profiles[profile_name]

    def validate_configuration(self, config: ProcessorConfig) -> List[str]:
        """
        Validate processor configuration.

        Args:
            config: Configuration to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Basic validation
        if not config.processor_type:
            errors.append("processor_type is required")

        if not isinstance(config.config, dict):
            errors.append("config must be a dictionary")

        if config.priority < 0:
            errors.append("priority must be non-negative")

        # Type-specific validation
        if config.processor_type.startswith("llm"):
            if "model" not in config.config:
                errors.append("LLM processors require 'model' configuration")

        return errors

    def load_from_dict(self, config_dict: Dict[str, Any]) -> None:
        """
        Load configurations from dictionary.

        Args:
            config_dict: Configuration dictionary
        """
        for name, config_data in config_dict.items():
            if isinstance(config_data, dict):
                processor_config = ProcessorConfig(
                    processor_type=config_data.get("type", ""),
                    config=config_data.get("config", {}),
                    enabled=config_data.get("enabled", True),
                    priority=config_data.get("priority", 100),
                    dependencies=config_data.get("dependencies", []),
                )

                errors = self.validate_configuration(processor_config)
                if errors:
                    logger.warning(
                        "Configuration validation errors", name=name, errors=errors
                    )
                else:
                    self.add_config(name, processor_config)

    def to_dict(self) -> Dict[str, Any]:
        """
        Export configurations to dictionary.

        Returns:
            Configuration dictionary
        """
        result = {}
        for name, config in self._configurations.items():
            result[name] = {
                "type": config.processor_type,
                "config": config.config,
                "enabled": config.enabled,
                "priority": config.priority,
                "dependencies": config.dependencies,
            }
        return result


def create_llm_config(
    model: str = "gpt-3.5-turbo",
    api_key: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Create LLM processor configuration.

    Args:
        model: Model name
        api_key: API key (if None, will use environment variable)
        temperature: Sampling temperature
        max_tokens: Maximum tokens
        **kwargs: Additional configuration

    Returns:
        LLM configuration dictionary
    """
    config = {"model": model, "temperature": temperature, **kwargs}

    if api_key:
        config["api_key"] = api_key

    if max_tokens:
        config["max_tokens"] = max_tokens

    return config


def create_html_config(
    clean_content: bool = True,
    extract_links: bool = False,
    extract_images: bool = False,
    **kwargs,
) -> Dict[str, Any]:
    """
    Create HTML processor configuration.

    Args:
        clean_content: Whether to clean HTML content
        extract_links: Whether to extract links
        extract_images: Whether to extract images
        **kwargs: Additional configuration

    Returns:
        HTML processor configuration dictionary
    """
    return {
        "clean_content": clean_content,
        "extract_links": extract_links,
        "extract_images": extract_images,
        **kwargs,
    }


# Predefined configuration templates
DEFAULT_CONFIGS = {
    "llm_summary_default": ProcessorConfig(
        processor_type="llm_summary",
        config=create_llm_config(model="gpt-3.5-turbo", temperature=0.3),
        priority=100,
    ),
    "llm_tags_default": ProcessorConfig(
        processor_type="llm_tags",
        config=create_llm_config(model="gpt-3.5-turbo", temperature=0.5),
        priority=90,
    ),
    "llm_keywords_default": ProcessorConfig(
        processor_type="llm_keywords",
        config=create_llm_config(model="gpt-3.5-turbo", temperature=0.3),
        priority=80,
    ),
    "html_content_default": ProcessorConfig(
        processor_type="html_content", config=create_html_config(), priority=200
    ),
}
