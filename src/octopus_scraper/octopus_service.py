import asyncio
import os
from dataclasses import asdict

import structlog
from dotenv import load_dotenv
from sanic import Sanic
from sanic.exceptions import SanicException
from sanic.response import json

from octopus_scraper.config import (
    ConfigManager,
    ConfigStatus,
    NotionDatabaseConfig,
    ServiceConfig,
)
from octopus_scraper.octopus import Octopus
from octopus_scraper.service_models import (
    HealthCheckResponse,
    TriggerScraperResponse,
    TriggerUploadResponse,
)

load_dotenv()  # take environment variables
# 初始化日志配置
log_format = os.getenv("LOG_FORMAT", "plain")
if log_format == "json":
    structlog.configure(processors=[structlog.processors.JSONRenderer()])
else:
    structlog.configure(processors=[structlog.dev.ConsoleRenderer()])

logger = structlog.get_logger()

app = Sanic("OctopusService")

# Default service configuration (can be overridden by CLI)
DEFAULT_SERVICE_CONFIG = {
    "host": os.getenv("OCTOPUS_HOST", "0.0.0.0"),
    "port": int(os.getenv("OCTOPUS_PORT", "8000")),
    "debug": os.getenv("OCTOPUS_DEBUG", "False").lower() == "true",
}


def create_config_from_env() -> tuple[NotionDatabaseConfig, ServiceConfig]:
    """Create configuration objects from environment variables."""
    # Notion database configuration
    notion_config = NotionDatabaseConfig(
        api_key=os.getenv("NOTION_API_KEY", ""),
        scrapers_database_id=os.getenv("NOTION_SCRAPERS_DATABASE_ID")
        or os.getenv("NOTION_DATABASE_ID", ""),
        content_database_id=os.getenv("NOTION_CONTENT_DATABASE_ID", ""),
    )

    # Service configuration
    service_config = ServiceConfig(
        host=os.getenv("SERVICE_HOST", "0.0.0.0"),
        port=int(os.getenv("SERVICE_PORT", "8000")),
        debug=os.getenv("DEBUG", "False").lower() == "true",
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_format=os.getenv("LOG_FORMAT", "plain"),
        config_refresh_interval=int(
            os.getenv("CONFIG_REFRESH_INTERVAL", "300")
        ),  # 5 minutes
        scraper_timeout=int(os.getenv("SCRAPER_TIMEOUT", "10")),
        upload_timeout=int(os.getenv("UPLOAD_TIMEOUT", "15")),
        upload_max_retries=int(os.getenv("UPLOAD_MAX_RETRIES", "3")),
    )

    return notion_config, service_config


@app.listener("before_server_start")
async def setup_octopus(app, _):
    """Initialize ConfigManager and Octopus instance with dynamic configuration loading."""
    try:
        # Create configuration from environment variables
        notion_config, service_config = create_config_from_env()

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

        # Create base config for Octopus
        octopus_config = {
            "scrapers_config_with_fetch_params": [
                {
                    "scraper_config": {
                        "fetcher_name": scraper.fetcher,
                        "fetcher_config": {
                            "hub_root": scraper.hub_root,
                            "route": scraper.route,
                            "fetch_params": scraper.fetch_params or {},
                        },
                        "content_processor_configs": {},
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
        }

        # Initialize Octopus with loaded configuration
        octopus = Octopus(octopus_config)
        app.ctx.octopus = octopus

        logger.info(
            "Octopus instance initialized successfully with dynamic configuration",
            scraper_count=len(scrapers_config),
            config_version=config_manager.get_current_version().version_id
            if config_manager.get_current_version()
            else "initial",
        )

        # Start configuration monitoring
        config_manager.start_config_watcher()
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


@app.listener("before_server_stop")
async def cleanup_octopus(app, _):
    """Clean up resources before server stops."""
    try:
        if hasattr(app.ctx, "config_manager"):
            app.ctx.config_manager.stop_config_watcher()
            logger.info("ConfigManager stopped successfully")
    except Exception as e:
        logger.error("Error during cleanup", error=str(e))


async def reload_octopus_config(app):
    """Reload Octopus configuration when ConfigManager detects changes."""
    try:
        config_manager: ConfigManager = app.ctx.config_manager
        current_scrapers = config_manager.get_current_scrapers()

        # Create new Octopus configuration
        octopus_config = {
            "scrapers_config_with_fetch_params": [
                {
                    "scraper_config": {
                        "fetcher_name": scraper.fetcher,
                        "fetcher_config": {
                            "hub_root": scraper.hub_root,
                            "route": scraper.route,
                            "fetch_params": scraper.fetch_params or {},
                        },
                        "content_processor_configs": {},
                    },
                    "fetch_params": scraper.fetch_params or {},
                }
                for scraper in current_scrapers
            ],
            "notion_api_config": app.ctx.octopus._notion_api_config,  # Keep existing notion config
        }

        # Replace the Octopus instance with new configuration
        new_octopus = Octopus(octopus_config)
        app.ctx.octopus = new_octopus

        logger.info(
            "Octopus configuration reloaded successfully",
            scraper_count=len(current_scrapers),
            config_version=config_manager.get_current_version().version_id,
        )

        return True

    except Exception as e:
        logger.error(
            "Failed to reload Octopus configuration", error=str(e), exc_info=True
        )
        return False


@app.route("/health", methods=["GET"])
async def health_check(request):
    """Enhanced health check with configuration status."""
    try:
        # Check if ConfigManager is available
        if hasattr(app.ctx, "config_manager"):
            config_manager: ConfigManager = app.ctx.config_manager
            config_status = config_manager.get_status()

            health_data = {
                "status": "ok" if config_status.is_healthy else "degraded",
                "timestamp": config_status.last_check.isoformat()
                if config_status.last_check
                else None,
                "config_version": config_status.version.version_id
                if config_status.version
                else None,
                "scrapers_count": len(config_status.scrapers),
            }

            if not config_status.is_healthy and config_status.error_message:
                health_data["error"] = config_status.error_message
        else:
            # Fallback for basic health check without ConfigManager
            health_data = {
                "status": "ok",
                "timestamp": None,
                "config_version": None,
                "scrapers_count": 0,
                "note": "Running without ConfigManager (legacy mode)",
            }

        return json(health_data)

    except Exception as e:
        logger.error("Health check failed", error=str(e))
        return json({"status": "error", "error": str(e)}, status=500)


@app.route("/trigger_scraper", methods=["POST"])
async def trigger_scraper(request):
    """触发抓取任务"""
    try:
        octopus: Octopus = app.ctx.octopus
        # 使用to_thread在异步环境中运行同步的抓取方法
        await asyncio.to_thread(octopus.trigger_scraper)

        response = TriggerScraperResponse(
            status="success",
            message="Scraping completed successfully.",
            data={
                "source_count": len(octopus._scrapers),
                "item_count": len(octopus._fetched_contents),
            },
        )
        return json(asdict(response))
    except Exception as e:
        logger.error("Scraping task failed", error=str(e), exc_info=True)
        response = TriggerScraperResponse(
            status="error", message=f"An unexpected error occurred: {e}"
        )
        return json(asdict(response), status=500)


@app.route("/trigger_upload", methods=["POST"])
async def trigger_upload(request):
    """触发上传任务"""
    try:
        octopus: Octopus = app.ctx.octopus
        # 使用to_thread在异步环境中运行同步的上传方法
        upload_result = await asyncio.to_thread(octopus.trigger_upload)

        response = TriggerUploadResponse(
            status="success",
            message="Upload completed successfully.",
            # trigger_upload返回一个整数，表示上传成功的数量
            data={"uploaded_count": upload_result},
        )
        return json(asdict(response))
    except Exception as e:
        logger.error("Upload task failed", error=str(e), exc_info=True)
        response = TriggerUploadResponse(
            status="error", message=f"An unexpected error occurred: {e}"
        )
        return json(asdict(response), status=500)


# Configuration Management Endpoints


@app.route("/admin/config/status", methods=["GET"])
async def get_config_status(request):
    """Get detailed configuration status."""
    try:
        config_manager: ConfigManager = app.ctx.config_manager
        config_status = config_manager.get_status()

        status_data = {
            "is_healthy": config_status.is_healthy,
            "last_check": config_status.last_check.isoformat()
            if config_status.last_check
            else None,
            "error_message": config_status.error_message,
            "current_version": {
                "version_id": config_status.version.version_id,
                "timestamp": config_status.version.timestamp.isoformat(),
                "config_hash": config_status.version.config_hash,
                "scrapers_count": config_status.version.scrapers_count,
            }
            if config_status.version
            else None,
            "scrapers": [
                {
                    "name": scraper.name,
                    "status": scraper.status,
                    "fetcher": scraper.fetcher,
                    "priority": scraper.priority,
                }
                for scraper in config_status.scrapers
            ],
        }

        return json(status_data)

    except Exception as e:
        logger.error("Failed to get config status", error=str(e))
        return json({"error": str(e)}, status=500)


@app.route("/admin/config/refresh", methods=["POST"])
async def refresh_config(request):
    """Manually trigger configuration refresh."""
    try:
        config_manager: ConfigManager = app.ctx.config_manager

        # Check for changes and reload if necessary
        config_changed = await config_manager.reload_config_if_changed()

        if config_changed:
            # Reload Octopus with new configuration
            await reload_octopus_config(app)
            message = "Configuration refreshed successfully"
        else:
            message = "No configuration changes detected"

        config_status = config_manager.get_status()

        return json(
            {
                "status": "success",
                "message": message,
                "config_changed": config_changed,
                "current_version": config_status.version.version_id
                if config_status.version
                else None,
                "scrapers_count": len(config_status.scrapers),
            }
        )

    except Exception as e:
        logger.error("Failed to refresh config", error=str(e))
        return json(
            {"status": "error", "message": f"Configuration refresh failed: {e}"},
            status=500,
        )


@app.route("/admin/config/validate", methods=["POST"])
async def validate_config(request):
    """Validate current configuration without applying changes."""
    try:
        config_manager: ConfigManager = app.ctx.config_manager

        # Load configuration from Notion without applying
        scrapers = await config_manager.notion_client.load_scrapers_config()

        # Validate configuration
        validation_errors = config_manager.validate_scrapers_config(scrapers)

        return json(
            {
                "status": "success",
                "is_valid": len(validation_errors) == 0,
                "validation_errors": validation_errors,
                "scrapers_count": len(scrapers),
                "scrapers": [
                    {
                        "name": scraper.name,
                        "status": scraper.status,
                        "fetcher": scraper.fetcher,
                    }
                    for scraper in scrapers
                ],
            }
        )

    except Exception as e:
        logger.error("Failed to validate config", error=str(e))
        return json(
            {"status": "error", "message": f"Configuration validation failed: {e}"},
            status=500,
        )


if __name__ == "__main__":
    app.run(**DEFAULT_SERVICE_CONFIG)
