"""
Notion configuration database interaction module.

This module handles communication with Notion databases for
loading and managing scraper configurations.
"""

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

            return scrapers

        except Exception as e:
            logger.error(
                "Failed to load scrapers configuration",
                error=str(e),
                error_type=type(e).__name__,
                status_code=getattr(e, "status", None),
                api_code=getattr(e, "code", None),
                exc_info=True,
            )
            raise

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

    async def _ensure_scrapers_database_schema(self) -> None:
        """Ensure required columns exist in the scrapers Notion database.

        Retrieves current database schema first, then only creates
        columns that are missing. This avoids overwriting existing
        select options (e.g. Status, Fetcher) which would be cleared
        if we passed ``{"select": {}}`` for an existing select column.
        """
        # Define the expected schema — column name → property type definition
        # For select columns, pre-populate options so new databases are ready to use
        expected_properties: Dict[str, Dict[str, Any]] = {
            "Name": {"title": {}},
            "Status": {
                "select": {
                    "options": [
                        {"name": "Active", "color": "green"},
                        {"name": "Inactive", "color": "red"},
                    ]
                }
            },
            "Fetcher": {
                "select": {
                    "options": [
                        {"name": "rsshub", "color": "blue"},
                        {"name": "direct_rss", "color": "purple"},
                    ]
                }
            },
            "Hub Root": {"url": {}},
            "Route": {"rich_text": {}},
            "Priority": {"number": {}},
            "Fetch Params": {"rich_text": {}},
            "Content Processors": {"rich_text": {}},
            "Keywords": {"multi_select": {}},
        }

        try:
            # Retrieve current database schema to find existing columns
            db_info = await self.client.databases.retrieve(
                database_id=self.config.scrapers_database_id
            )
            existing_properties = set(db_info.get("properties", {}).keys())

            # Only add columns that are missing
            missing_properties = {
                name: prop_def
                for name, prop_def in expected_properties.items()
                if name not in existing_properties
            }

            if not missing_properties:
                logger.debug("All required scrapers database columns already exist")
                return

            logger.info(
                "Creating missing scrapers database columns",
                missing_columns=list(missing_properties.keys()),
            )

            await self.client.databases.update(
                database_id=self.config.scrapers_database_id,
                properties=missing_properties,
            )
            logger.info("Scrapers database schema ensured successfully")
        except Exception as e:
            logger.warning(
                "Failed to ensure scrapers database schema, columns may need manual creation",
                error=str(e),
            )

    async def validate_connection(self) -> bool:
        """Validate connection to Notion databases."""
        try:
            # Test access to scrapers database
            logger.info(
                "Start Testing databases connections.",
                scrapers_db=self.config.scrapers_database_id,
                content_db=self.config.content_database_id,
            )
            await self.client.databases.retrieve(
                database_id=self.config.scrapers_database_id
            )
            logger.info("Notion connection validation scraper database successful")

            # Ensure required columns exist (idempotent)
            await self._ensure_scrapers_database_schema()

            # Test access to content database
            await self.client.databases.retrieve(
                database_id=self.config.content_database_id
            )

            logger.info("Notion connection validation successful")
            return True

        except Exception as e:
            logger.error("Notion connection validation failed", error=str(e))
            return False
