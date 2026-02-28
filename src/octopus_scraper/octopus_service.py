import asyncio
import os
from dataclasses import asdict
from datetime import datetime

import structlog
from dotenv import load_dotenv
from sanic import Sanic
from sanic.exceptions import SanicException
from sanic.response import json

from octopus_scraper.config import ConfigManager, NotionDatabaseConfig, ServiceConfig
from octopus_scraper.octopus import Octopus
from octopus_scraper.service_models import TriggerScraperResponse, TriggerUploadResponse

load_dotenv()

# Initialize logging configuration
log_format = os.getenv("LOG_FORMAT", "plain")
if log_format == "json":
    structlog.configure(processors=[structlog.processors.JSONRenderer()])
else:
    structlog.configure(processors=[structlog.dev.ConsoleRenderer()])

logger = structlog.get_logger()


app_name = "OctopusService"
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


def create_config_from_env() -> tuple[NotionDatabaseConfig, ServiceConfig, dict, dict]:
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

    # TaskManager configuration - always enabled
    task_manager_config = {
        "max_concurrent_tasks": int(os.getenv("MAX_CONCURRENT_TASKS", "8")),
        "max_queue_size": int(os.getenv("MAX_QUEUE_SIZE", "1000")),
        "result_retention_hours": int(os.getenv("RESULT_RETENTION_HOURS", "48")),
    }

    return notion_config, service_config, task_manager_config


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
                        "fetcher_config": {
                            "hub_root": scraper.hub_root,
                            "route": scraper.route,
                            "fetch_params": scraper.fetch_params or {},
                        },
                        "content_processor_configs": scraper.content_processor_configs,
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
    """Reload Octopus configuration when ConfigManager detects changes."""
    try:
        config_manager: ConfigManager = app.ctx.config_manager
        current_scrapers = config_manager.get_current_scrapers()

        # Get TaskManager configuration from environment
        _, _, task_manager_config = create_config_from_env()

        # Create new Octopus configuration with TaskManager
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
                        "content_processor_configs": scraper.content_processor_configs,
                    },
                    "fetch_params": scraper.fetch_params or {},
                }
                for scraper in current_scrapers
            ],
            "notion_api_config": app.ctx.octopus._config.notion_api_config,  # Keep existing notion config
            "use_task_manager": True,  # Always enable TaskManager
            "task_manager_config": task_manager_config,
            "max_concurrent_scrapers": task_manager_config["max_concurrent_tasks"],
        }

        # Clean up old Octopus instance
        old_octopus = app.ctx.octopus
        if hasattr(old_octopus, "_task_manager") and old_octopus._task_manager:
            old_octopus.cleanup_task_manager()

        # Replace the Octopus instance with new configuration
        new_octopus = Octopus(octopus_config)
        app.ctx.octopus = new_octopus

        logger.info(
            "Octopus configuration reloaded successfully with TaskManager",
            scraper_count=len(current_scrapers),
            config_version=config_manager.get_current_version().version_id,
            task_manager_enabled=True,
            max_concurrent_tasks=task_manager_config["max_concurrent_tasks"],
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
                "last_check": (
                    config_status.last_check.isoformat()
                    if config_status.last_check
                    else None
                ),
                "next_check": (
                    config_status.next_check.isoformat()
                    if hasattr(config_status, "next_check") and config_status.next_check
                    else None
                ),
                "version": (
                    config_status.version.version_id if config_status.version else None
                ),
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
            # Get pending upload count from TaskManager completed tasks
            pending_upload_count = 0
            if hasattr(octopus, "_task_manager") and octopus._task_manager:
                from octopus_scraper.task_manager.models import TaskStatus

                completed = octopus._task_manager.list_tasks(
                    status=TaskStatus.COMPLETED, limit=1000
                )
                pending_upload_count = sum(
                    1 for t in completed if t.items_uploaded == 0
                )

            health_data["dependencies"]["octopus_instance"] = {
                "status": "healthy",
                "scrapers_configured": (
                    len(octopus._scrapers) if hasattr(octopus, "_scrapers") else 0
                ),
                "pending_upload_tasks": pending_upload_count,
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
    """触发抓取任务，将任务提交到 TaskManager 异步执行。"""
    try:
        octopus: Octopus = app.ctx.octopus
        # trigger_scraper 提交任务到 TaskManager 并返回 batch_id
        batch_id = octopus.trigger_scraper()

        response = TriggerScraperResponse(
            status="success",
            message="Scraper tasks submitted successfully.",
            data={
                "batch_id": batch_id,
                "source_count": len(octopus._scrapers),
            },
        )
        return json(asdict(response))
    except Exception as e:
        logger.error("Scraping task submission failed", error=str(e), exc_info=True)
        response = TriggerScraperResponse(
            status="error", message=f"An unexpected error occurred: {e}"
        )
        return json(asdict(response), status=500)


@app.route("/trigger_upload", methods=["POST"])
async def trigger_upload(request):
    """从 TaskManager 已完成任务中收集未上传内容并上传到 Notion。"""
    try:
        octopus: Octopus = app.ctx.octopus
        # trigger_upload 涉及同步 Notion API 调用，使用 to_thread 避免阻塞事件循环
        upload_result = await asyncio.to_thread(octopus.trigger_upload)

        response = TriggerUploadResponse(
            status="success",
            message="Upload completed successfully.",
            data=upload_result,
        )
        return json(asdict(response))
    except Exception as e:
        logger.error("Upload task failed", error=str(e), exc_info=True)
        response = TriggerUploadResponse(
            status="error", message=f"An unexpected error occurred: {e}"
        )
        return json(asdict(response), status=500)


# ===== Admin Management APIs =====
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
                    "last_check": (
                        config_status.last_check.isoformat()
                        if config_status.last_check
                        else None
                    ),
                    "version": (
                        {
                            "version_id": config_status.version.version_id,
                            "timestamp": config_status.version.timestamp.isoformat(),
                            "change_summary": config_status.version.change_summary,
                        }
                        if config_status.version
                        else None
                    ),
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
    """Refresh configuration from Notion and reload Octopus if changed.

    Returns detailed change information including old/new version comparison.
    """
    try:
        config_manager: ConfigManager = app.ctx.config_manager

        # Get current state before reload
        old_version = config_manager.get_current_version()
        old_scrapers_count = len(config_manager.get_current_scrapers())

        # Check if configuration has changed and reload if necessary
        config_changed = await config_manager.reload_config_if_changed()

        if config_changed:
            # Reload Octopus with new configuration
            reload_success = await reload_octopus_config(app)

            if reload_success:
                new_version = config_manager.get_current_version()
                new_scrapers_count = len(config_manager.get_current_scrapers())

                return json(
                    {
                        "status": "success",
                        "message": "Configuration refreshed and reloaded successfully",
                        "config_changed": True,
                        "reload_performed": True,
                        "changes": {
                            "old_version": (
                                old_version.version_id if old_version else None
                            ),
                            "new_version": (
                                new_version.version_id if new_version else None
                            ),
                            "old_scrapers_count": old_scrapers_count,
                            "new_scrapers_count": new_scrapers_count,
                            "change_summary": (
                                new_version.change_summary if new_version else None
                            ),
                        },
                        "timestamp": datetime.now().isoformat(),
                    }
                )
            else:
                return json(
                    {
                        "status": "error",
                        "message": "Configuration changed but reload failed",
                        "config_changed": True,
                        "reload_performed": False,
                    },
                    status=500,
                )
        else:
            return json(
                {
                    "status": "success",
                    "message": "No configuration changes detected",
                    "config_changed": False,
                    "reload_performed": False,
                    "current_version": (
                        old_version.version_id if old_version else None
                    ),
                    "scrapers_count": old_scrapers_count,
                }
            )

    except Exception as e:
        logger.error("Failed to refresh config", error=str(e), exc_info=True)
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


@app.route("/admin/system/info", methods=["GET"])
async def get_system_info(request):
    """Get comprehensive system information."""
    try:
        config_manager: ConfigManager = app.ctx.config_manager
        octopus: Octopus = app.ctx.octopus

        # Basic system info
        system_info = {
            "service": {
                "name": "OctopusService",
                "version": "0.1.6",
                "uptime_seconds": None,  # Could be calculated from startup time
                "environment": os.getenv("ENVIRONMENT", "development"),
                "debug_mode": os.getenv("OCTOPUS_DEBUG", "False").lower() == "true",
            },
            "configuration": {
                "config_refresh_interval": config_manager.service_config.config_refresh_interval,
                "scraper_timeout": config_manager.service_config.scraper_timeout,
                "upload_timeout": config_manager.service_config.upload_timeout,
                "upload_max_retries": config_manager.service_config.upload_max_retries,
                "log_level": config_manager.service_config.log_level,
                "log_format": config_manager.service_config.log_format,
            },
            "octopus_instance": {
                "scrapers_configured": (
                    len(octopus._scrapers) if hasattr(octopus, "_scrapers") else 0
                ),
                "max_concurrent_scrapers": getattr(
                    octopus._config, "max_concurrent_scrapers", 5
                ),
                "use_task_manager": True,  # Always enabled now
            },
            "notion_config": {
                "api_key_configured": bool(config_manager.notion_config.api_key),
                "scrapers_database_id": config_manager.notion_config.scrapers_database_id,
                "content_database_id": config_manager.notion_config.content_database_id,
            },
            "memory_usage": _get_memory_usage(),
            "timestamp": datetime.now().isoformat(),
        }

        # Add task manager info - always available now
        task_manager = octopus.get_task_manager()
        task_stats = task_manager.get_statistics()
        system_info["task_manager"] = {
            "enabled": True,
            "statistics": task_stats,
        }

        return json(
            {
                "status": "success",
                "system_info": system_info,
            }
        )

    except Exception as e:
        logger.error("Failed to get system info", error=str(e))
        return json(
            {"status": "error", "message": f"Failed to get system info: {e}"},
            status=500,
        )


@app.route("/admin/scrapers", methods=["GET"])
async def list_scrapers(request):
    """Get detailed list of all configured scrapers."""
    try:
        config_manager: ConfigManager = app.ctx.config_manager
        octopus: Octopus = app.ctx.octopus

        current_scrapers = config_manager.get_current_scrapers()

        # Build detailed scraper information
        scrapers_info = []
        for i, scraper_config in enumerate(current_scrapers):
            scraper_info = {
                "index": i,
                "name": scraper_config.name,
                "status": scraper_config.status,
                "fetcher": scraper_config.fetcher,
                "hub_root": scraper_config.hub_root,
                "route": scraper_config.route,
                "priority": scraper_config.priority,
                "fetch_params": scraper_config.fetch_params,
                "is_active": scraper_config.status == "Active",
                "created_at": getattr(scraper_config, "created_at", None),
                "updated_at": getattr(scraper_config, "updated_at", None),
            }

            # Add runtime information if available
            if hasattr(octopus, "_scrapers") and i < len(octopus._scrapers):
                runtime_scraper, runtime_params = octopus._scrapers[i]
                scraper_info["runtime"] = {
                    "initialized": True,
                    "fetcher_type": (
                        type(runtime_scraper.activate_fetcher).__name__
                        if hasattr(runtime_scraper, "activate_fetcher")
                        else None
                    ),
                    "has_storage": (
                        runtime_scraper.storage is not None
                        if hasattr(runtime_scraper, "storage")
                        else False
                    ),
                    "processors_count": (
                        len(runtime_scraper.active_content_processor)
                        if hasattr(runtime_scraper, "active_content_processor")
                        else 0
                    ),
                }
            else:
                scraper_info["runtime"] = {"initialized": False}

            scrapers_info.append(scraper_info)

        return json(
            {
                "status": "success",
                "scrapers": scrapers_info,
                "summary": {
                    "total_count": len(scrapers_info),
                    "active_count": len([s for s in scrapers_info if s["is_active"]]),
                    "inactive_count": len(
                        [s for s in scrapers_info if not s["is_active"]]
                    ),
                    "fetcher_distribution": {
                        fetcher: len(
                            [s for s in scrapers_info if s["fetcher"] == fetcher]
                        )
                        for fetcher in set(s["fetcher"] for s in scrapers_info)
                    },
                },
            }
        )

    except Exception as e:
        logger.error("Failed to list scrapers", error=str(e))
        return json(
            {"status": "error", "message": f"Failed to list scrapers: {e}"},
            status=500,
        )


@app.route("/admin/scrapers/<scraper_name>/test", methods=["POST"])
async def run_scraper_test(request, scraper_name):
    """Test a specific scraper without storing results."""
    try:
        config_manager: ConfigManager = app.ctx.config_manager

        # Find the scraper configuration
        current_scrapers = config_manager.get_current_scrapers()
        target_scraper_config = None

        for scraper_config in current_scrapers:
            if scraper_config.name == scraper_name:
                target_scraper_config = scraper_config
                break

        if not target_scraper_config:
            return json(
                {
                    "status": "error",
                    "message": f"Scraper '{scraper_name}' not found",
                },
                status=404,
            )

        if target_scraper_config.status != "Active":
            return json(
                {
                    "status": "error",
                    "message": f"Scraper '{scraper_name}' is not active (status: {target_scraper_config.status})",
                },
                status=400,
            )

        # Parse request parameters
        request_data = request.json or {}
        test_params = request_data.get(
            "params", target_scraper_config.fetch_params or {}
        )
        timeout = request_data.get("timeout", 30)

        # Create test scraper instance
        from octopus_scraper.scraper import Scraper

        test_scraper_config = {
            "fetcher_name": target_scraper_config.fetcher,
            "fetcher_config": {
                "hub_root": target_scraper_config.hub_root,
                "route": target_scraper_config.route,
            },
            "content_processor_configs": target_scraper_config.content_processor_configs,
        }

        test_scraper = Scraper(test_scraper_config)

        # Execute test with timeout
        start_time = datetime.now()

        try:
            # Use asyncio.wait_for to implement timeout
            contents = await asyncio.wait_for(
                asyncio.to_thread(test_scraper.scrap_contents, test_params),
                timeout=timeout,
            )

            execution_time = (datetime.now() - start_time).total_seconds()

            return json(
                {
                    "status": "success",
                    "message": f"Scraper '{scraper_name}' test completed successfully",
                    "test_results": {
                        "scraper_name": scraper_name,
                        "fetcher": target_scraper_config.fetcher,
                        "execution_time_seconds": round(execution_time, 2),
                        "items_fetched": len(contents),
                        "test_params": test_params,
                        "sample_items": [
                            {
                                "title": (
                                    content.title[:100] + "..."
                                    if len(content.title) > 100
                                    else content.title
                                ),
                                "link": content.link,
                                "published": content.published,
                                "content_id": content.content_id,
                            }
                            for content in contents[:3]  # Show first 3 items
                        ],
                    },
                    "timestamp": datetime.now().isoformat(),
                }
            )

        except asyncio.TimeoutError:
            return json(
                {
                    "status": "error",
                    "message": f"Scraper '{scraper_name}' test timed out after {timeout} seconds",
                    "test_results": {
                        "scraper_name": scraper_name,
                        "execution_time_seconds": timeout,
                        "timeout_reached": True,
                    },
                },
                status=408,
            )

    except Exception as e:
        logger.error(
            "Scraper test failed",
            scraper_name=scraper_name,
            error=str(e),
            exc_info=True,
        )
        return json(
            {
                "status": "error",
                "message": f"Scraper test failed: {e}",
                "scraper_name": scraper_name,
            },
            status=500,
        )


@app.route("/admin/tasks/stats", methods=["GET"])
async def get_task_stats(request):
    """Get task manager statistics and performance metrics."""
    try:
        octopus: Octopus = app.ctx.octopus
        task_manager = octopus.get_task_manager()
        stats = task_manager.get_statistics()

        # Add additional runtime information
        enhanced_stats = {
            **stats,
            "task_manager_enabled": True,
            "legacy_mode": False,
            "uptime_info": {
                "queue_capacity_usage": f"{stats['current_queue_size']}/{stats['queue_capacity']}",
                "worker_utilization": f"{stats['running_tasks_count']}/{stats['max_concurrent_tasks']}",
            },
            "timestamp": datetime.now().isoformat(),
        }

        return json(
            {
                "status": "success",
                "statistics": enhanced_stats,
            }
        )

    except Exception as e:
        logger.error("Failed to get task statistics", error=str(e))
        return json(
            {"status": "error", "message": f"Failed to get task statistics: {e}"},
            status=500,
        )


@app.route("/admin/tasks", methods=["GET"])
async def list_tasks(request):
    """List tasks with optional filtering."""
    try:
        octopus: Octopus = app.ctx.octopus

        # Parse query parameters
        status_filter = request.args.get("status")
        limit = int(request.args.get("limit", "50"))
        limit = min(limit, 200)  # Cap at 200 for performance

        # Get tasks from Octopus (which wraps TaskManager)
        tasks = octopus.list_tasks(status=status_filter, limit=limit)

        return json(
            {
                "status": "success",
                "tasks": tasks,
                "filters": {
                    "status": status_filter,
                    "limit": limit,
                },
                "total_returned": len(tasks),
                "task_manager_enabled": True,
            }
        )

    except Exception as e:
        logger.error("Failed to list tasks", error=str(e))
        return json(
            {"status": "error", "message": f"Failed to list tasks: {e}"},
            status=500,
        )


@app.route("/admin/tasks/<task_id>", methods=["GET"])
async def get_task_details(request, task_id):
    """Get detailed information about a specific task."""
    try:
        octopus: Octopus = app.ctx.octopus

        # Get task details from Octopus
        task_details = octopus.get_task_status(task_id)

        if not task_details:
            return json(
                {
                    "status": "error",
                    "message": f"Task '{task_id}' not found",
                },
                status=404,
            )

        return json(
            {
                "status": "success",
                "task": task_details,
            }
        )

    except Exception as e:
        logger.error("Failed to get task details", task_id=task_id, error=str(e))
        return json(
            {"status": "error", "message": f"Failed to get task details: {e}"},
            status=500,
        )


@app.route("/admin/tasks/<task_id>/cancel", methods=["POST"])
async def cancel_task(request, task_id):
    """Cancel a specific task."""
    try:
        octopus: Octopus = app.ctx.octopus

        # Cancel task through Octopus
        cancelled = octopus.cancel_task(task_id)

        if cancelled:
            return json(
                {
                    "status": "success",
                    "message": f"Task '{task_id}' cancelled successfully",
                    "task_id": task_id,
                    "cancelled": True,
                }
            )
        else:
            return json(
                {
                    "status": "error",
                    "message": f"Failed to cancel task '{task_id}' (may already be completed or not found)",
                    "task_id": task_id,
                    "cancelled": False,
                },
                status=400,
            )

    except Exception as e:
        logger.error("Failed to cancel task", task_id=task_id, error=str(e))
        return json(
            {"status": "error", "message": f"Failed to cancel task: {e}"},
            status=500,
        )


@app.route("/admin/tasks", methods=["POST"])
async def submit_individual_task(request):
    """Submit an individual scraper task."""
    try:
        octopus: Octopus = app.ctx.octopus
        request_data = request.json or {}

        # Validate required fields
        scraper_name = request_data.get("scraper_name")
        if not scraper_name:
            return json(
                {
                    "status": "error",
                    "message": "Missing required field: scraper_name",
                },
                status=400,
            )

        # Find scraper configuration
        config_manager: ConfigManager = app.ctx.config_manager
        current_scrapers = config_manager.get_current_scrapers()

        target_scraper = None
        for scraper_config in current_scrapers:
            if scraper_config.name == scraper_name:
                target_scraper = scraper_config
                break

        if not target_scraper:
            return json(
                {
                    "status": "error",
                    "message": f"Scraper '{scraper_name}' not found in configuration",
                },
                status=404,
            )

        if target_scraper.status != "Active":
            return json(
                {
                    "status": "error",
                    "message": f"Scraper '{scraper_name}' is not active",
                },
                status=400,
            )

        # Prepare task configuration
        scraper_config = {
            "fetcher_name": target_scraper.fetcher,
            "fetcher_config": {
                "hub_root": target_scraper.hub_root,
                "route": target_scraper.route,
            },
            "content_processor_configs": target_scraper.content_processor_configs,
        }

        fetch_params = request_data.get(
            "fetch_params", target_scraper.fetch_params or {}
        )

        # Submit task through Octopus
        task_id = octopus.submit_individual_scraper_task(
            scraper_name=scraper_name,
            scraper_config=scraper_config,
            fetch_params=fetch_params,
        )

        if task_id:
            return json(
                {
                    "status": "success",
                    "message": "Task submitted successfully",
                    "task_id": task_id,
                    "scraper_name": scraper_name,
                    "fetch_params": fetch_params,
                }
            )
        else:
            return json(
                {
                    "status": "error",
                    "message": "Failed to submit task",
                },
                status=500,
            )

    except Exception as e:
        logger.error("Failed to submit task", error=str(e), exc_info=True)
        return json(
            {"status": "error", "message": f"Failed to submit task: {e}"},
            status=500,
        )


@app.route("/admin/monitoring/metrics", methods=["GET"])
async def get_monitoring_metrics(request):
    """Get comprehensive monitoring metrics for the service."""
    try:
        config_manager: ConfigManager = app.ctx.config_manager
        octopus: Octopus = app.ctx.octopus

        metrics = {
            "timestamp": datetime.now().isoformat(),
            "service": {
                "name": "OctopusService",
                "version": "0.1.2",
                "environment": os.getenv("ENVIRONMENT", "development"),
            },
            "performance": {
                "memory_usage": _get_memory_usage(),
                "response_times": {
                    "health_check_cache_duration": _health_cache["cache_duration"],
                    "last_health_check": (
                        _health_cache["last_check"].isoformat()
                        if _health_cache["last_check"]
                        else None
                    ),
                },
            },
            "configuration": {
                "status": (
                    "healthy" if config_manager.get_status().is_healthy else "unhealthy"
                ),
                "version": (
                    config_manager.get_current_version().version_id
                    if config_manager.get_current_version()
                    else None
                ),
                "scrapers_count": len(config_manager.get_current_scrapers()),
                "active_scrapers_count": len(
                    [
                        s
                        for s in config_manager.get_current_scrapers()
                        if s.status == "Active"
                    ]
                ),
                "last_refresh": (
                    config_manager.get_status().last_check.isoformat()
                    if config_manager.get_status().last_check
                    else None
                ),
                "refresh_interval_seconds": config_manager.service_config.config_refresh_interval,
            },
            "octopus": {
                "scrapers_initialized": (
                    len(octopus._scrapers) if hasattr(octopus, "_scrapers") else 0
                ),
                "max_concurrent_scrapers": getattr(
                    octopus._config, "max_concurrent_scrapers", 5
                ),
            },
        }

        # Add task manager metrics if available
        if hasattr(octopus, "_task_manager") and octopus._task_manager:
            task_stats = octopus._task_manager.get_statistics()
            metrics["task_manager"] = {
                "enabled": True,
                "statistics": task_stats,
                "performance": {
                    "success_rate": task_stats["success_rate_percent"],
                    "average_duration": task_stats["average_task_duration_seconds"],
                    "queue_utilization": f"{task_stats['current_queue_size']}/{task_stats['queue_capacity']}",
                    "worker_utilization": f"{task_stats['running_tasks_count']}/{task_stats['max_concurrent_tasks']}",
                },
            }
        else:
            metrics["task_manager"] = {"enabled": False}

        # Add Notion connectivity metrics
        try:
            notion_healthy = await config_manager.notion_client.validate_connection()
            metrics["notion"] = {
                "connectivity": "healthy" if notion_healthy else "unhealthy",
                "api_key_configured": bool(config_manager.notion_config.api_key),
                "databases": {
                    "scrapers_db": config_manager.notion_config.scrapers_database_id,
                    "content_db": config_manager.notion_config.content_database_id,
                },
            }
        except Exception as e:
            metrics["notion"] = {
                "connectivity": "error",
                "error": str(e),
            }

        return json(
            {
                "status": "success",
                "metrics": metrics,
            }
        )

    except Exception as e:
        logger.error("Failed to get monitoring metrics", error=str(e))
        return json(
            {"status": "error", "message": f"Failed to get monitoring metrics: {e}"},
            status=500,
        )


@app.route("/admin/cache/clear", methods=["POST"])
async def clear_cache(request):
    """Clear various caches in the service."""
    try:
        request_data = request.json or {}
        cache_types = request_data.get("cache_types", ["health", "contents"])
        cleared_caches = []

        # Clear health check cache
        if "health" in cache_types:
            global _health_cache
            _health_cache["last_check"] = None
            _health_cache["cached_result"] = None
            cleared_caches.append("health_check_cache")

        # Clear pending upload contents from completed tasks in TaskManager
        if "contents" in cache_types:
            octopus: Octopus = app.ctx.octopus
            if hasattr(octopus, "_task_manager") and octopus._task_manager:
                from octopus_scraper.task_manager.models import TaskStatus

                completed = octopus._task_manager.list_tasks(
                    status=TaskStatus.COMPLETED, limit=1000
                )
                cleared_count = 0
                for task_result in completed:
                    if "contents" in task_result.metadata:
                        cleared_count += len(task_result.metadata["contents"])
                        task_result.metadata.pop("contents", None)
                cleared_caches.append(f"task_contents_cache ({cleared_count} items)")

        # Clear task manager old results
        if "task_results" in cache_types:
            octopus: Octopus = app.ctx.octopus
            if hasattr(octopus, "_task_manager") and octopus._task_manager:
                octopus._task_manager.cleanup_old_results()
                cleared_caches.append("task_manager_old_results")

        return json(
            {
                "status": "success",
                "message": "Cache cleared successfully",
                "cleared_caches": cleared_caches,
                "timestamp": datetime.now().isoformat(),
            }
        )

    except Exception as e:
        logger.error("Failed to clear cache", error=str(e))
        return json(
            {"status": "error", "message": f"Failed to clear cache: {e}"},
            status=500,
        )


@app.route("/admin/runtime/gc", methods=["POST"])
async def force_garbage_collection(request):
    """Force garbage collection to free memory."""
    try:
        import gc

        # Get memory usage before GC
        memory_before = _get_memory_usage()

        # Force garbage collection
        collected = gc.collect()

        # Get memory usage after GC
        memory_after = _get_memory_usage()

        return json(
            {
                "status": "success",
                "message": "Garbage collection completed",
                "results": {
                    "objects_collected": collected,
                    "memory_before_mb": memory_before.get("rss_mb", "unavailable"),
                    "memory_after_mb": memory_after.get("rss_mb", "unavailable"),
                    "memory_freed_mb": (
                        round(
                            memory_before.get("rss_mb", 0)
                            - memory_after.get("rss_mb", 0),
                            2,
                        )
                        if isinstance(memory_before.get("rss_mb"), (int, float))
                        and isinstance(memory_after.get("rss_mb"), (int, float))
                        else "unavailable"
                    ),
                },
                "timestamp": datetime.now().isoformat(),
            }
        )

    except Exception as e:
        logger.error("Failed to force garbage collection", error=str(e))
        return json(
            {"status": "error", "message": f"Failed to force garbage collection: {e}"},
            status=500,
        )


@app.route("/admin/runtime/config-watcher", methods=["GET", "POST"])
async def manage_config_watcher(request):
    """Get status or control the configuration watcher."""
    try:
        config_manager: ConfigManager = app.ctx.config_manager

        if request.method == "GET":
            # Get watcher status
            watcher_status = {
                "running": hasattr(config_manager, "_watcher_task")
                and config_manager._watcher_task
                and not config_manager._watcher_task.done(),
                "stop_requested": getattr(config_manager, "_stop_watcher", False),
                "refresh_interval": config_manager.service_config.config_refresh_interval,
                "last_check": (
                    config_manager.get_status().last_check.isoformat()
                    if config_manager.get_status().last_check
                    else None
                ),
                "next_check": (
                    config_manager.get_status().next_check.isoformat()
                    if hasattr(config_manager.get_status(), "next_check")
                    and config_manager.get_status().next_check
                    else None
                ),
            }

            return json(
                {
                    "status": "success",
                    "watcher_status": watcher_status,
                }
            )

        elif request.method == "POST":
            # Control watcher (start/stop/restart)
            request_data = request.json or {}
            action = request_data.get("action", "restart")

            if action == "stop":
                config_manager.stop_config_watcher()
                message = "Configuration watcher stopped"

            elif action == "start":
                config_manager.start_config_watcher()
                message = "Configuration watcher started"

            elif action == "restart":
                config_manager.stop_config_watcher()
                await asyncio.sleep(0.5)  # Give it time to stop
                config_manager.start_config_watcher()
                message = "Configuration watcher restarted"

            else:
                return json(
                    {
                        "status": "error",
                        "message": f"Invalid action: {action}. Use 'start', 'stop', or 'restart'",
                    },
                    status=400,
                )

            return json(
                {
                    "status": "success",
                    "message": message,
                    "action": action,
                    "timestamp": datetime.now().isoformat(),
                }
            )

    except Exception as e:
        logger.error("Failed to manage config watcher", error=str(e))
        return json(
            {"status": "error", "message": f"Failed to manage config watcher: {e}"},
            status=500,
        )


@app.route("/admin/debug/dump-state", methods=["POST"])
async def dump_service_state(request):
    """Dump comprehensive service state for debugging (sensitive data masked)."""
    try:
        config_manager: ConfigManager = app.ctx.config_manager
        octopus: Octopus = app.ctx.octopus

        # Parse request options
        request_data = request.json or {}
        include_sensitive = request_data.get("include_sensitive", False)
        include_task_details = request_data.get("include_task_details", False)

        state_dump = {
            "timestamp": datetime.now().isoformat(),
            "service_info": {
                "name": "OctopusService",
                "version": "0.1.2",
                "app_name": app.name,
                "debug_mode": os.getenv("OCTOPUS_DEBUG", "False").lower() == "true",
                "environment": os.getenv("ENVIRONMENT", "development"),
            },
            "configuration_manager": {
                "is_healthy": config_manager.get_status().is_healthy,
                "current_version": (
                    config_manager.get_current_version().version_id
                    if config_manager.get_current_version()
                    else None
                ),
                "scrapers_count": len(config_manager.get_current_scrapers()),
                "watcher_running": hasattr(config_manager, "_watcher_task")
                and config_manager._watcher_task
                and not config_manager._watcher_task.done(),
                "service_config": {
                    "host": config_manager.service_config.host,
                    "port": config_manager.service_config.port,
                    "debug": config_manager.service_config.debug,
                    "log_level": config_manager.service_config.log_level,
                    "log_format": config_manager.service_config.log_format,
                    "config_refresh_interval": config_manager.service_config.config_refresh_interval,
                    "scraper_timeout": config_manager.service_config.scraper_timeout,
                    "upload_timeout": config_manager.service_config.upload_timeout,
                    "upload_max_retries": config_manager.service_config.upload_max_retries,
                },
                "notion_config": {
                    "api_key_configured": bool(config_manager.notion_config.api_key),
                    "api_key": (
                        config_manager.notion_config.api_key[:10] + "..."
                        if config_manager.notion_config.api_key
                        and not include_sensitive
                        else config_manager.notion_config.api_key
                    ),
                    "scrapers_database_id": config_manager.notion_config.scrapers_database_id,
                    "content_database_id": config_manager.notion_config.content_database_id,
                },
            },
            "octopus_instance": {
                "scrapers_count": (
                    len(octopus._scrapers) if hasattr(octopus, "_scrapers") else 0
                ),
                "config": {
                    "max_concurrent_scrapers": getattr(
                        octopus._config, "max_concurrent_scrapers", 5
                    ),
                    "use_task_manager": getattr(
                        octopus._config, "use_task_manager", False
                    ),
                },
                "task_manager": {
                    "enabled": hasattr(octopus, "_task_manager")
                    and octopus._task_manager is not None,
                },
            },
            "memory_usage": _get_memory_usage(),
            "cache_status": {
                "health_cache": {
                    "last_check": (
                        _health_cache["last_check"].isoformat()
                        if _health_cache["last_check"]
                        else None
                    ),
                    "cache_duration": _health_cache["cache_duration"],
                    "has_cached_result": _health_cache["cached_result"] is not None,
                },
            },
        }

        # Add detailed task manager information if requested
        if (
            include_task_details
            and hasattr(octopus, "_task_manager")
            and octopus._task_manager
        ):
            task_manager = octopus._task_manager
            task_stats = task_manager.get_statistics()

            state_dump["octopus_instance"]["task_manager"].update(
                {
                    "statistics": task_stats,
                    "running_tasks_count": len(task_manager._running_tasks),
                    "task_results_count": len(task_manager._task_results),
                    "queue_size": task_manager._task_queue.qsize(),
                    "worker_thread_alive": (
                        task_manager._worker_thread.is_alive()
                        if task_manager._worker_thread
                        else False
                    ),
                    "stop_event_set": task_manager._stop_event.is_set(),
                }
            )

        # Add scraper details
        if hasattr(octopus, "_scrapers"):
            state_dump["scrapers"] = [
                {
                    "index": i,
                    "fetcher_type": (
                        type(scraper.activate_fetcher).__name__
                        if hasattr(scraper, "activate_fetcher")
                        else "unknown"
                    ),
                    "has_storage": (
                        scraper.storage is not None
                        if hasattr(scraper, "storage")
                        else False
                    ),
                    "processors_count": (
                        len(scraper.active_content_processor)
                        if hasattr(scraper, "active_content_processor")
                        else 0
                    ),
                    "fetch_params": params,
                }
                for i, (scraper, params) in enumerate(octopus._scrapers)
            ]

        return json(
            {
                "status": "success",
                "state_dump": state_dump,
                "dump_options": {
                    "include_sensitive": include_sensitive,
                    "include_task_details": include_task_details,
                },
            }
        )

    except Exception as e:
        logger.error("Failed to dump service state", error=str(e), exc_info=True)
        return json(
            {"status": "error", "message": f"Failed to dump service state: {e}"},
            status=500,
        )


@app.route("/admin", methods=["GET"])
async def admin_overview(request):
    """Get overview of all available admin endpoints and current system status."""
    try:
        config_manager: ConfigManager = app.ctx.config_manager
        octopus: Octopus = app.ctx.octopus

        # Quick system health check
        system_healthy = True
        health_summary = {}

        try:
            config_status = config_manager.get_status()
            health_summary["configuration"] = {
                "healthy": config_status.is_healthy,
                "scrapers_count": len(config_status.scrapers),
                "active_scrapers": len(
                    [s for s in config_status.scrapers if s.status == "Active"]
                ),
            }
            if not config_status.is_healthy:
                system_healthy = False
        except Exception as e:
            health_summary["configuration"] = {"healthy": False, "error": str(e)}
            system_healthy = False

        try:
            notion_healthy = await config_manager.notion_client.validate_connection()
            health_summary["notion"] = {"healthy": notion_healthy}
            if not notion_healthy:
                system_healthy = False
        except Exception as e:
            health_summary["notion"] = {"healthy": False, "error": str(e)}
            system_healthy = False

        health_summary["octopus"] = {
            "scrapers_configured": (
                len(octopus._scrapers) if hasattr(octopus, "_scrapers") else 0
            ),
            "task_manager_enabled": hasattr(octopus, "_task_manager")
            and octopus._task_manager is not None,
        }

        # Available admin endpoints
        admin_endpoints = {
            "configuration_management": {
                "description": "Manage system configuration",
                "endpoints": [
                    {
                        "method": "GET",
                        "path": "/admin/config/status",
                        "description": "Get current configuration status",
                    },
                    {
                        "method": "POST",
                        "path": "/admin/config/refresh",
                        "description": "Refresh and reload configuration from Notion",
                    },
                    {
                        "method": "POST",
                        "path": "/admin/config/validate",
                        "description": "Validate configuration without applying",
                    },
                ],
            },
            "system_information": {
                "description": "Get comprehensive system information and monitoring",
                "endpoints": [
                    {
                        "method": "GET",
                        "path": "/admin/system/info",
                        "description": "Get detailed system information",
                    },
                    {
                        "method": "GET",
                        "path": "/admin/monitoring/metrics",
                        "description": "Get comprehensive monitoring metrics",
                    },
                    {
                        "method": "POST",
                        "path": "/admin/debug/dump-state",
                        "description": "Dump comprehensive service state for debugging",
                    },
                ],
            },
            "scraper_management": {
                "description": "Manage and test individual scrapers",
                "endpoints": [
                    {
                        "method": "GET",
                        "path": "/admin/scrapers",
                        "description": "List all configured scrapers with details",
                    },
                    {
                        "method": "POST",
                        "path": "/admin/scrapers/<scraper_name>/test",
                        "description": "Test a specific scraper",
                    },
                ],
            },
            "task_management": {
                "description": "Manage scraper tasks",
                "endpoints": [
                    {
                        "method": "GET",
                        "path": "/admin/tasks",
                        "description": "List tasks with optional filtering (?status=&limit=)",
                    },
                    {
                        "method": "POST",
                        "path": "/admin/tasks",
                        "description": "Submit an individual scraper task",
                    },
                    {
                        "method": "GET",
                        "path": "/admin/tasks/stats",
                        "description": "Get task manager statistics",
                    },
                    {
                        "method": "GET",
                        "path": "/admin/tasks/<task_id>",
                        "description": "Get detailed task information",
                    },
                    {
                        "method": "POST",
                        "path": "/admin/tasks/<task_id>/cancel",
                        "description": "Cancel a specific task",
                    },
                ],
            },
            "runtime_control": {
                "description": "Control runtime behavior and caching",
                "endpoints": [
                    {
                        "method": "POST",
                        "path": "/admin/cache/clear",
                        "description": "Clear various caches",
                    },
                    {
                        "method": "POST",
                        "path": "/admin/runtime/gc",
                        "description": "Force garbage collection",
                    },
                    {
                        "method": "GET",
                        "path": "/admin/runtime/config-watcher",
                        "description": "Get config watcher status",
                    },
                    {
                        "method": "POST",
                        "path": "/admin/runtime/config-watcher",
                        "description": "Control config watcher (start/stop/restart)",
                    },
                ],
            },
            "health_and_status": {
                "description": "Health checks and service status",
                "endpoints": [
                    {
                        "method": "GET",
                        "path": "/health",
                        "description": "Comprehensive health check",
                    },
                    {
                        "method": "GET",
                        "path": "/health/liveness",
                        "description": "Lightweight liveness probe",
                    },
                    {
                        "method": "GET",
                        "path": "/health/readiness",
                        "description": "Readiness probe for traffic",
                    },
                ],
            },
        }

        return json(
            {
                "status": "success",
                "message": "OctopusService Admin Interface",
                "system_health": {
                    "overall_healthy": system_healthy,
                    "summary": health_summary,
                },
                "admin_endpoints": admin_endpoints,
                "service_info": {
                    "name": "OctopusService",
                    "version": "0.1.2",
                    "environment": os.getenv("ENVIRONMENT", "development"),
                    "timestamp": datetime.now().isoformat(),
                },
                "usage_notes": [
                    "All admin endpoints require appropriate access controls in production",
                    "Use /admin/monitoring/metrics for comprehensive system metrics",
                    "Config refresh may cause brief service interruption during reload",
                    "Debug endpoints may expose sensitive information - use with caution",
                ],
            }
        )

    except Exception as e:
        logger.error("Failed to get admin overview", error=str(e))
        return json(
            {"status": "error", "message": f"Failed to get admin overview: {e}"},
            status=500,
        )
