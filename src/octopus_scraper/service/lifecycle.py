"""Server lifecycle hooks for OctopusService."""

import structlog
from sanic.exceptions import SanicException

from octopus_scraper.config import ConfigManager
from octopus_scraper.octopus import Octopus
from octopus_scraper.service.app import app
from octopus_scraper.service.config_helpers import (
    build_fetcher_config,
    create_config_from_env,
)

logger = structlog.get_logger()


@app.listener("before_server_start")
async def setup_octopus(app, _):
    """Initialize ConfigManager and Octopus instance with dynamic configuration loading."""
    try:
        # Create configuration from environment variables
        notion_config, service_config, task_manager_config = create_config_from_env()

        # Validate required configuration
        if not notion_config.api_key or not notion_config.scrapers_database_id:
            logger.error(
                "Missing NOTION_API_KEY or NOTION_SCRAPERS_DATABASE_ID environment variables."
            )
            raise ValueError(
                "NOTION_API_KEY and NOTION_SCRAPERS_DATABASE_ID must be set."
            )

        # Initialize ConfigManager
        config_manager = ConfigManager(notion_config, service_config)
        app.ctx.config_manager = config_manager

        logger.info("ConfigManager created successfully")

        # Load initial configuration from Notion
        scrapers_config = await config_manager.load_initial_config()

        # Create base config for Octopus with TaskManager
        octopus_config = {
            "scrapers_config_with_fetch_params": [
                {
                    "scraper_config": {
                        "fetcher_name": scraper.fetcher,
                        "fetcher_config": build_fetcher_config(scraper),
                        "content_processor_configs": scraper.content_processor_configs,
                        "scraper_name": scraper.name,
                        "default_keywords": scraper.default_keywords,
                    },
                    "fetch_params": scraper.fetch_params or {},
                }
                for scraper in scrapers_config
            ],
            "notion_api_config": {
                "api_key": notion_config.api_key,
                "database_id": notion_config.content_database_id
                or notion_config.scrapers_database_id,
            },
            "use_task_manager": True,  # Always enable TaskManager
            "task_manager_config": task_manager_config,
            "max_concurrent_scrapers": task_manager_config["max_concurrent_tasks"],
        }

        # Initialize Octopus with loaded configuration
        octopus = Octopus(octopus_config)
        app.ctx.octopus = octopus

        logger.info(
            "Octopus instance initialized successfully with TaskManager",
            scraper_count=len(scrapers_config),
            config_version=(
                config_manager.get_current_version().version_id
                if config_manager.get_current_version()
                else "initial"
            ),
            task_manager_enabled=True,
            max_concurrent_tasks=task_manager_config["max_concurrent_tasks"],
        )

        # Start configuration monitoring
        config_manager.start_config_watcher()

        # Register callback so the background watcher also reloads
        # Octopus when configuration changes are detected.
        async def _on_config_changed():
            await reload_octopus_config(app)

        config_manager.set_on_config_changed(_on_config_changed)
        logger.info("Configuration monitoring started")

    except Exception as e:
        logger.error(
            "Failed to initialize Octopus with ConfigManager",
            error=str(e),
            exc_info=True,
        )
        raise SanicException(
            "Service unavailable: Octopus initialization failed.", status_code=503
        )


@app.listener("after_server_start")
async def log_registered_routes(app, _):
    """Log all registered routes after the Sanic server starts."""
    route_list = []
    for route in app.router.routes:
        # Collect HTTP methods and URI pattern for each route
        methods = (
            ",".join(sorted(route.methods - {"OPTIONS"})) if route.methods else "N/A"
        )
        route_list.append({"methods": methods, "uri": route.uri, "name": route.name})

    # Sort routes by URI for readability
    route_list.sort(key=lambda r: r["uri"])

    logger.info("Registered routes", total=len(route_list))
    for route_info in route_list:
        logger.info(
            "Route registered",
            methods=route_info["methods"],
            uri=route_info["uri"],
            name=route_info["name"],
        )


@app.listener("before_server_stop")
async def cleanup_octopus(app, _):
    """Clean up resources before server stops."""
    try:
        # Stop ConfigManager
        if hasattr(app.ctx, "config_manager"):
            app.ctx.config_manager.stop_config_watcher()
            logger.info("ConfigManager stopped successfully")

        # Clean up TaskManager in Octopus
        if hasattr(app.ctx, "octopus"):
            app.ctx.octopus.cleanup_task_manager()
            logger.info("Octopus TaskManager cleaned up successfully")

    except Exception as e:
        logger.error("Error during cleanup", error=str(e))


async def reload_octopus_config(app):
    """Reload Octopus configuration when ConfigManager detects changes.

    This is a *soft* reload: only the scraper list is hot-swapped on the
    existing Octopus instance. The underlying TaskManager (and any running
    long-lived scraping tasks) is intentionally left untouched.
    Restarting TaskManager on every Notion edit would cancel pending tasks
    and interrupt in-flight ones, which is unacceptable for the long-running
    scraper workloads it manages.
    """
    try:
        config_manager: ConfigManager = app.ctx.config_manager
        current_scrapers = config_manager.get_current_scrapers()

        scrapers_config_with_fetch_params = [
            {
                "scraper_config": {
                    "fetcher_name": scraper.fetcher,
                    "fetcher_config": build_fetcher_config(scraper),
                    "content_processor_configs": scraper.content_processor_configs,
                    "scraper_name": scraper.name,
                    "default_keywords": scraper.default_keywords,
                },
                "fetch_params": scraper.fetch_params or {},
            }
            for scraper in current_scrapers
        ]

        octopus = app.ctx.octopus
        updated_count = octopus.update_scrapers(scrapers_config_with_fetch_params)

        logger.info(
            "Octopus scrapers reloaded (soft reload, TaskManager preserved)",
            scraper_count=updated_count,
            config_version=config_manager.get_current_version().version_id,
        )

        return True

    except Exception as e:
        logger.error(
            "Failed to reload Octopus configuration", error=str(e), exc_info=True
        )
        return False
