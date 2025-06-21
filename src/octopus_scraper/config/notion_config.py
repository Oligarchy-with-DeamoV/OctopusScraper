"""
Notion configuration database interaction module.

This module handles communication with Notion databases for
loading and managing scraper configurations.
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from notion_client import AsyncClient

from octopus_scraper.config.models import NotionDatabaseConfig, ScraperConfig

logger = structlog.get_logger(__name__)


class NotionConfigClient:
    """Client for interacting with Notion configuration databases."""

    def __init__(self, config: NotionDatabaseConfig):
        self.config = config
        self.client = AsyncClient(auth=config.api_key)
        self._last_scrapers_check: Optional[datetime] = None

    async def load_scrapers_config(self) -> List[ScraperConfig]:
        """Load all active scraper configurations from Notion database."""
        try:
            logger.info(
                "Loading scrapers configuration from Notion",
                database_id=self.config.scrapers_database_id,
            )

            # Query the scrapers database
            response = await self.client.databases.query(
                database_id=self.config.scrapers_database_id,
                filter={"property": "Status", "select": {"equals": "Active"}},
                sorts=[{"property": "Priority", "direction": "ascending"}],
            )

            scrapers = []
            for record in response["results"]:
                try:
                    scraper = ScraperConfig.from_notion_record(record)
                    scrapers.append(scraper)
                    logger.debug(
                        "Loaded scraper config",
                        scraper_name=scraper.name,
                        fetcher=scraper.fetcher,
                    )
                except Exception as e:
                    logger.error(
                        "Failed to parse scraper record",
                        record_id=record["id"],
                        error=str(e),
                    )
                    # Continue with other scrapers
                    continue

            logger.info(
                "Successfully loaded scrapers configuration",
                scrapers_count=len(scrapers),
            )

            self._last_scrapers_check = datetime.now()
            return scrapers

        except Exception as e:
            logger.error(
                "Failed to load scrapers configuration", error=str(e), exc_info=True
            )
            raise

    async def check_config_changes(self) -> bool:
        """Check if scraper configuration has changed since last check."""
        try:
            if not self._last_scrapers_check:
                return True  # First time, consider as changed

            # Query for any records modified after last check
            response = await self.client.databases.query(
                database_id=self.config.scrapers_database_id,
                filter={
                    "property": "Last edited time",
                    "last_edited_time": {
                        "after": self._last_scrapers_check.isoformat()
                    },
                },
                page_size=1,  # We only need to know if any changes exist
            )

            has_changes = len(response["results"]) > 0
            logger.debug(
                "Configuration change check completed",
                has_changes=has_changes,
                last_check=self._last_scrapers_check,
            )

            return has_changes

        except Exception as e:
            logger.error("Failed to check configuration changes", error=str(e))
            # In case of error, assume there are changes to be safe
            return True

    async def get_database_info(self) -> Dict[str, Any]:
        """Get information about the scrapers database."""
        try:
            response = await self.client.databases.retrieve(
                database_id=self.config.scrapers_database_id
            )
            return {
                "title": response.get("title", [{}])[0].get("plain_text", "Unknown"),
                "created_time": response.get("created_time"),
                "last_edited_time": response.get("last_edited_time"),
                "properties": list(response.get("properties", {}).keys()),
            }
        except Exception as e:
            logger.error("Failed to get database info", error=str(e))
            return {}

    async def validate_connection(self) -> bool:
        """Validate connection to Notion databases."""
        try:
            # Test access to scrapers database
            await self.client.databases.retrieve(
                database_id=self.config.scrapers_database_id
            )

            # Test access to content database
            await self.client.databases.retrieve(
                database_id=self.config.content_database_id
            )

            logger.info("Notion connection validation successful")
            return True

        except Exception as e:
            logger.error("Notion connection validation failed", error=str(e))
            return False
