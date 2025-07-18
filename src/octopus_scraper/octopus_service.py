import asyncio
import os
from dataclasses import asdict
from datetime import datetime

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

# Create app with unique name to avoid conflicts in parallel tests
import uuid

app_name = f"OctopusService_{uuid.uuid4().hex[:8]}"
app = Sanic(app_name)

# Health check cache to avoid expensive operations on every request
_health_cache = {
    "last_check": None,
    "cache_duration": 30,  # seconds
    "cached_result": None,
}

# Default service configuration (can be overridden by CLI)
DEFAULT_SERVICE_CONFIG = {
    "host": os.getenv("OCTOPUS_HOST", "0.0.0.0"),
    "port": int(os.getenv("OCTOPUS_PORT", "8000")),
    "debug": os.getenv("OCTOPUS_DEBUG", "False").lower() == "true",
}


def _get_memory_usage():
    """Get basic memory usage information."""
    try:
        import resource

        # Get memory usage in MB
        memory_usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Convert from different units based on platform
        if os.name == "posix":
            # Linux/Unix returns in kilobytes
            return {"rss_mb": round(memory_usage / 1024, 2)}
        else:
            # Other platforms might return in bytes
            return {"rss_mb": round(memory_usage / (1024 * 1024), 2)}
    except Exception:
        return {"rss_mb": "unavailable"}


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
    """Enhanced health check with comprehensive system status."""
    start_time = datetime.now()

    # Check cache first for non-critical health checks
    use_cache = request.args.get("cache", "true").lower() == "true"
    if use_cache and _health_cache["cached_result"] and _health_cache["last_check"]:
        cache_age = (start_time - _health_cache["last_check"]).total_seconds()
        if cache_age < _health_cache["cache_duration"]:
            cached_result = _health_cache["cached_result"].copy()
            cached_result["cached"] = True
            cached_result["cache_age_seconds"] = round(cache_age, 2)
            return json(cached_result, status=cached_result.get("_status_code", 200))

    try:
        health_data = {
            "status": "ok",
            "timestamp": start_time.isoformat(),
            "service": {
                "name": "OctopusService",
                "version": "0.1.2",
                "uptime_seconds": None,  # Will be calculated if app start time is available
            },
            "dependencies": {},
            "configuration": {},
            "performance": {},
            "cached": False,
        }

        overall_healthy = True

        # Check if ConfigManager is available
        if hasattr(app.ctx, "config_manager"):
            config_manager: ConfigManager = app.ctx.config_manager
            config_status = config_manager.get_status()

            # Configuration health
            config_healthy = config_status.is_healthy
            health_data["configuration"] = {
                "status": "healthy" if config_healthy else "unhealthy",
                "last_check": config_status.last_check.isoformat()
                if config_status.last_check
                else None,
                "next_check": config_status.next_check.isoformat()
                if hasattr(config_status, "next_check") and config_status.next_check
                else None,
                "version": config_status.version.version_id
                if config_status.version
                else None,
                "scrapers_count": len(config_status.scrapers),
                "active_scrapers": len(
                    [s for s in config_status.scrapers if s.status == "Active"]
                ),
                "error": config_status.error_message if not config_healthy else None,
            }

            if not config_healthy:
                overall_healthy = False

            # Check Notion API connectivity (cached to avoid too frequent calls)
            try:
                notion_healthy = (
                    await config_manager.notion_client.validate_connection()
                )
                health_data["dependencies"]["notion_api"] = {
                    "status": "healthy" if notion_healthy else "unhealthy",
                    "scrapers_database": {
                        "id": config_manager.notion_config.scrapers_database_id,
                        "accessible": notion_healthy,
                    },
                    "content_database": {
                        "id": config_manager.notion_config.content_database_id,
                        "accessible": notion_healthy,
                    },
                }
                if not notion_healthy:
                    overall_healthy = False
            except Exception as e:
                health_data["dependencies"]["notion_api"] = {
                    "status": "unhealthy",
                    "error": str(e),
                }
                overall_healthy = False

        else:
            # Fallback for basic health check without ConfigManager
            health_data["configuration"] = {
                "status": "unknown",
                "note": "Running without ConfigManager (legacy mode)",
                "scrapers_count": 0,
            }
            health_data["dependencies"]["notion_api"] = {
                "status": "unknown",
                "note": "ConfigManager not available",
            }
            # In legacy mode, we don't consider this as unhealthy
            # overall_healthy remains True

        # Check Octopus instance
        if hasattr(app.ctx, "octopus"):
            octopus = app.ctx.octopus
            health_data["dependencies"]["octopus_instance"] = {
                "status": "healthy",
                "scrapers_configured": len(octopus._scrapers)
                if hasattr(octopus, "_scrapers")
                else 0,
                "fetched_contents_cached": len(octopus._fetched_contents)
                if hasattr(octopus, "_fetched_contents")
                else 0,
            }
        else:
            health_data["dependencies"]["octopus_instance"] = {
                "status": "unhealthy",
                "error": "Octopus instance not initialized",
            }
            # Only mark as unhealthy if we're not in legacy mode and octopus is missing
            if hasattr(app.ctx, "config_manager"):
                overall_healthy = False

        # Performance metrics
        response_time = (datetime.now() - start_time).total_seconds() * 1000
        health_data["performance"] = {
            "response_time_ms": round(response_time, 2),
            "memory_usage": _get_memory_usage(),
        }

        # Set overall status
        if overall_healthy:
            health_data["status"] = "healthy"
            status_code = 200
        else:
            health_data["status"] = "unhealthy"
            status_code = 503

        # Update cache
        health_data["_status_code"] = status_code
        _health_cache["last_check"] = start_time
        _health_cache["cached_result"] = health_data.copy()

        return json(health_data, status=status_code)

    except Exception as e:
        logger.error("Health check failed", error=str(e), exc_info=True)
        response_time = (datetime.now() - start_time).total_seconds() * 1000
        return json(
            {
                "status": "error",
                "timestamp": start_time.isoformat(),
                "error": str(e),
                "performance": {
                    "response_time_ms": round(response_time, 2),
                },
            },
            status=500,
        )


@app.route("/health/liveness", methods=["GET"])
async def liveness_check(request):
    """Lightweight liveness probe for Kubernetes/Docker health checks."""
    return json({"status": "alive", "timestamp": datetime.now().isoformat()})


@app.route("/health/readiness", methods=["GET"])
async def readiness_check(request):
    """Readiness probe to check if service is ready to accept traffic."""
    try:
        ready = True
        checks = {
            "config_manager": False,
            "octopus_instance": False,
            "notion_connectivity": False,
        }

        # Check ConfigManager
        if hasattr(app.ctx, "config_manager"):
            config_manager = app.ctx.config_manager
            config_status = config_manager.get_status()
            checks["config_manager"] = config_status.is_healthy
        else:
            ready = False

        # Check Octopus instance
        if hasattr(app.ctx, "octopus"):
            checks["octopus_instance"] = True
        else:
            ready = False

        # Quick Notion connectivity check (optional, can be disabled via env var)
        if os.getenv("HEALTHCHECK_SKIP_NOTION", "false").lower() != "true":
            if hasattr(app.ctx, "config_manager"):
                try:
                    # Quick database info check (lightweight)
                    db_info = (
                        await app.ctx.config_manager.notion_client.get_database_info()
                    )
                    checks["notion_connectivity"] = bool(db_info)
                    if not checks["notion_connectivity"]:
                        ready = False
                except Exception:
                    checks["notion_connectivity"] = False
                    ready = False
        else:
            checks["notion_connectivity"] = "skipped"

        status_code = 200 if ready else 503
        return json(
            {
                "status": "ready" if ready else "not_ready",
                "timestamp": datetime.now().isoformat(),
                "checks": checks,
            },
            status=status_code,
        )

    except Exception as e:
        logger.error("Readiness check failed", error=str(e))
        return json(
            {
                "status": "not_ready",
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
            },
            status=503,
        )


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
            data={"uploaded_count": upload_result},
        )
        return json(asdict(response))
    except Exception as e:
        logger.error("Upload task failed", error=str(e), exc_info=True)
        response = TriggerUploadResponse(
            status="error", message=f"An unexpected error occurred: {e}"
        )
        return json(asdict(response), status=500)


@app.route("/admin/config/status", methods=["GET"])
async def get_config_status(request):
    """Get current configuration status."""
    try:
        config_manager: ConfigManager = app.ctx.config_manager
        config_status = config_manager.get_status()

        return json(
            {
                "status": "success",
                "config_status": {
                    "is_healthy": config_status.is_healthy,
                    "last_check": config_status.last_check.isoformat()
                    if config_status.last_check
                    else None,
                    "version": {
                        "version_id": config_status.version.version_id,
                        "timestamp": config_status.version.timestamp.isoformat(),
                        "change_summary": config_status.version.change_summary,
                    }
                    if config_status.version
                    else None,
                    "scrapers": [
                        {
                            "name": scraper.name,
                            "status": scraper.status,
                            "fetcher": scraper.fetcher,
                        }
                        for scraper in config_status.scrapers
                    ],
                    "error_message": config_status.error_message,
                },
            }
        )

    except Exception as e:
        logger.error("Failed to get config status", error=str(e))
        return json(
            {"status": "error", "message": f"Failed to get config status: {e}"},
            status=500,
        )


@app.route("/admin/config/refresh", methods=["POST"])
async def refresh_config(request):
    """Refresh configuration from Notion."""
    try:
        config_manager: ConfigManager = app.ctx.config_manager

        # Check if configuration has changed and reload if necessary
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
