"""Strict YAML scraper configuration loading."""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import yaml
from yaml.tokens import AliasToken

from octopus_scraper.config.models import ScraperConfig
from octopus_scraper.processors import AVAILABLE_PROCESSOR
from octopus_scraper.scraper import AVAILABLE_FETCHERS

SCRAPER_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
ALLOWED_FIELDS = {
    "id",
    "name",
    "enabled",
    "fetcher",
    "hub_root",
    "route",
    "fetch_params",
    "priority",
    "content_processor_configs",
    "default_keywords",
}
MAX_CONFIG_FILE_BYTES = 1024 * 1024
MAX_CONFIG_DEPTH = 20
MAX_CONFIG_NODES = 5000
MAX_STRING_LENGTH = 100000


class ScraperConfigError(ValueError):
    """Raised when one scraper configuration file is invalid."""


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> Dict[str, Any]:
    mapping: Dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise ScraperConfigError("YAML mapping keys must be strings")
        if key in mapping:
            raise ScraperConfigError(f"Duplicate YAML key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


class YamlScraperConfigLoader:
    """Load and validate one scraper from one YAML file."""

    def load(self, path: Path) -> ScraperConfig:
        """Load a scraper configuration from ``path``."""
        try:
            if path.stat().st_size > MAX_CONFIG_FILE_BYTES:
                raise ScraperConfigError(
                    f"Configuration file exceeds {MAX_CONFIG_FILE_BYTES} bytes"
                )
            raw_content = path.read_bytes()
            text = raw_content.decode("utf-8")
            if any(isinstance(token, AliasToken) for token in yaml.scan(text)):
                raise ScraperConfigError("YAML aliases are not supported")
            documents = list(yaml.load_all(text, Loader=UniqueKeyLoader))
        except (OSError, yaml.YAMLError, UnicodeError, RecursionError) as error:
            raise ScraperConfigError(str(error)) from error

        if len(documents) != 1:
            raise ScraperConfigError("Each file must contain exactly one YAML document")

        data = documents[0]
        if not isinstance(data, dict):
            raise ScraperConfigError("The YAML document must be a mapping")
        self._validate_structure(data)

        unknown_fields = sorted(set(data) - ALLOWED_FIELDS)
        if unknown_fields:
            raise ScraperConfigError(f"Unknown fields: {', '.join(unknown_fields)}")

        scraper_id = self._required_string(data, "id")
        if not SCRAPER_ID_PATTERN.fullmatch(scraper_id):
            raise ScraperConfigError("id must match ^[a-z0-9][a-z0-9._-]*$")

        name = self._required_string(data, "name")
        fetcher = self._required_string(data, "fetcher")
        if fetcher not in AVAILABLE_FETCHERS:
            raise ScraperConfigError(
                f"Unknown fetcher '{fetcher}'. Available: {sorted(AVAILABLE_FETCHERS)}"
            )

        hub_root = self._required_string(data, "hub_root")
        parsed_url = urlparse(hub_root)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ScraperConfigError("hub_root must be an absolute HTTP(S) URL")

        route = self._required_string(data, "route")
        enabled = data.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ScraperConfigError("enabled must be a boolean")

        priority = data.get("priority", 5)
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise ScraperConfigError("priority must be an integer")
        if not 1 <= priority <= 10:
            raise ScraperConfigError("priority must be between 1 and 10")

        fetch_params = data.get("fetch_params", {})
        if not isinstance(fetch_params, dict):
            raise ScraperConfigError("fetch_params must be a mapping")

        processor_configs = data.get("content_processor_configs", {})
        if not isinstance(processor_configs, dict):
            raise ScraperConfigError("content_processor_configs must be a mapping")
        for processor_name, processor_config in processor_configs.items():
            if processor_name not in AVAILABLE_PROCESSOR:
                raise ScraperConfigError(
                    f"Unknown processor '{processor_name}'. "
                    f"Available: {sorted(AVAILABLE_PROCESSOR)}"
                )
            if not isinstance(processor_config, dict):
                raise ScraperConfigError(
                    f"Processor '{processor_name}' configuration must be a mapping"
                )

        keywords = data.get("default_keywords", [])
        if not isinstance(keywords, list) or any(
            not isinstance(keyword, str) for keyword in keywords
        ):
            raise ScraperConfigError("default_keywords must be a list of strings")
        keywords = self._normalize_keywords(keywords)

        return ScraperConfig(
            id=scraper_id,
            name=name,
            enabled=enabled,
            fetcher=fetcher,
            hub_root=hub_root,
            route=route,
            fetch_params=fetch_params,
            priority=priority,
            content_processor_configs=processor_configs,
            default_keywords=keywords,
            source_path=str(path),
        )

    def _required_string(self, data: Dict[str, Any], field: str) -> str:
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ScraperConfigError(f"{field} must be a non-empty string")
        return value.strip()

    def _normalize_keywords(self, keywords: List[str]) -> List[str]:
        normalized: List[str] = []
        seen = set()
        for keyword in keywords:
            stripped = keyword.strip()
            if stripped and stripped not in seen:
                seen.add(stripped)
                normalized.append(stripped)
        return normalized

    def _validate_structure(
        self,
        value: Any,
        depth: int = 0,
        node_count: Optional[List[int]] = None,
    ) -> None:
        if node_count is None:
            node_count = [0]
        node_count[0] += 1
        if node_count[0] > MAX_CONFIG_NODES:
            raise ScraperConfigError("Configuration contains too many values")
        if depth > MAX_CONFIG_DEPTH:
            raise ScraperConfigError("Configuration nesting is too deep")

        if isinstance(value, str):
            if len(value) > MAX_STRING_LENGTH:
                raise ScraperConfigError("Configuration string is too long")
            return
        if value is None or isinstance(value, (bool, int, float)):
            return
        if isinstance(value, list):
            for item in value:
                self._validate_structure(item, depth + 1, node_count)
            return
        if isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str):
                    raise ScraperConfigError("All configuration keys must be strings")
                self._validate_structure(key, depth + 1, node_count)
                self._validate_structure(item, depth + 1, node_count)
            return
        raise ScraperConfigError(
            f"Unsupported configuration value type: {type(value).__name__}"
        )
