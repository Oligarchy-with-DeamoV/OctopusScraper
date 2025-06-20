"""
Tests for config/models.py module.
"""
from datetime import datetime

import pytest

from octopus_scraper.config.models import (
    ConfigStatus,
    ConfigVersion,
    NotionDatabaseConfig,
    ScraperConfig,
    ServiceConfig,
)


class TestScraperConfig:
    def test_to_octopus_config(self):
        """Test converting ScraperConfig to Octopus format."""
        scraper = ScraperConfig(
            name="Test Scraper",
            status="Active",
            fetcher="rsshub",
            hub_root="https://example.com",
            route="/test",
            fetch_params={"key": "value"},
            priority=3
        )
        
        octopus_config = scraper.to_octopus_config()
        
        expected = {
            "name": "Test Scraper",
            "fetcher": "rsshub",
            "hub_root": "https://example.com",
            "route": "/test",
            "fetch_params": {"key": "value"},
            "priority": 3
        }
        
        assert octopus_config == expected

    def test_to_octopus_config_with_none_fetch_params(self):
        """Test converting ScraperConfig with None fetch_params."""
        scraper = ScraperConfig(
            name="Test Scraper",
            status="Active",
            fetcher="rsshub",
            hub_root="https://example.com",
            route="/test",
            fetch_params=None,
            priority=1
        )
        
        octopus_config = scraper.to_octopus_config()
        
        assert octopus_config["fetch_params"] == {}

    def test_default_values(self):
        """Test ScraperConfig default values."""
        scraper = ScraperConfig(
            name="Test",
            status="Active",
            fetcher="rsshub",
            hub_root="https://example.com",
            route="/test"
        )
        
        assert scraper.fetch_params is None
        assert scraper.priority == 5


class TestNotionDatabaseConfig:
    def test_notion_database_config_creation(self):
        """Test NotionDatabaseConfig creation."""
        config = NotionDatabaseConfig(
            api_key="test_key",
            scrapers_database_id="scrapers_db",
            content_database_id="content_db"
        )
        
        assert config.api_key == "test_key"
        assert config.scrapers_database_id == "scrapers_db"
        assert config.content_database_id == "content_db"


class TestServiceConfig:
    def test_service_config_defaults(self):
        """Test ServiceConfig default values."""
        config = ServiceConfig()
        
        assert config.host == "0.0.0.0"
        assert config.port == 8000
        assert config.debug == False
        assert config.log_level == "INFO"
        assert config.log_format == "plain"
        assert config.config_refresh_interval == 300
        assert config.scraper_timeout == 10
        assert config.upload_timeout == 15
        assert config.upload_max_retries == 3

    def test_service_config_custom_values(self):
        """Test ServiceConfig with custom values."""
        config = ServiceConfig(
            host="127.0.0.1",
            port=9000,
            debug=True,
            log_level="DEBUG",
            log_format="json",
            config_refresh_interval=600,
            scraper_timeout=20,
            upload_timeout=30,
            upload_max_retries=5
        )
        
        assert config.host == "127.0.0.1"
        assert config.port == 9000
        assert config.debug == True
        assert config.log_level == "DEBUG"
        assert config.log_format == "json"
        assert config.config_refresh_interval == 600
        assert config.scraper_timeout == 20
        assert config.upload_timeout == 30
        assert config.upload_max_retries == 5


class TestConfigVersion:
    def test_config_version_creation(self):
        """Test ConfigVersion creation."""
        timestamp = datetime.now()
        version = ConfigVersion(
            version_id="v1.0.0",
            timestamp=timestamp,
            config_hash="abc123",
            scrapers_count=5,
            change_summary="Initial version"
        )
        
        assert version.version_id == "v1.0.0"
        assert version.timestamp == timestamp
        assert version.config_hash == "abc123"
        assert version.scrapers_count == 5
        assert version.change_summary == "Initial version"

    def test_config_version_default_change_summary(self):
        """Test ConfigVersion with default change_summary."""
        version = ConfigVersion(
            version_id="v1.0.0",
            timestamp=datetime.now(),
            config_hash="abc123",
            scrapers_count=5
        )
        
        assert version.change_summary == ""


class TestConfigStatus:
    def test_config_status_creation(self):
        """Test ConfigStatus creation."""
        timestamp = datetime.now()
        version = ConfigVersion(
            version_id="v1.0.0",
            timestamp=timestamp,
            config_hash="abc123",
            scrapers_count=2
        )
        
        scrapers = [
            ScraperConfig("Scraper1", "Active", "rsshub", "http://test1.com", "/route1"),
            ScraperConfig("Scraper2", "Active", "direct_rss", "http://test2.com", "/route2")
        ]
        
        status = ConfigStatus(
            version=version,
            scrapers=scrapers,
            last_check=timestamp,
            next_check=timestamp,
            is_healthy=True,
            error_message=None
        )
        
        assert status.version == version
        assert len(status.scrapers) == 2
        assert status.last_check == timestamp
        assert status.next_check == timestamp
        assert status.is_healthy == True
        assert status.error_message is None

    def test_config_status_defaults(self):
        """Test ConfigStatus default values."""
        timestamp = datetime.now()
        version = ConfigVersion("v1.0.0", timestamp, "abc123", 0)
        
        status = ConfigStatus(
            version=version,
            scrapers=[],
            last_check=timestamp,
            next_check=timestamp
        )
        
        assert status.is_healthy == True
        assert status.error_message is None

    def test_config_status_unhealthy(self):
        """Test ConfigStatus when unhealthy."""
        timestamp = datetime.now()
        version = ConfigVersion("v1.0.0", timestamp, "abc123", 0)
        
        status = ConfigStatus(
            version=version,
            scrapers=[],
            last_check=timestamp,
            next_check=timestamp,
            is_healthy=False,
            error_message="Configuration error"
        )
        
        assert status.is_healthy == False
        assert status.error_message == "Configuration error"
