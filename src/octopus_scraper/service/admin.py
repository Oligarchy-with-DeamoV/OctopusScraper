"""Admin management API endpoints for OctopusService."""

import os
from datetime import datetime

import structlog
from sanic.response import json

from octopus_scraper.config import ConfigManager
from octopus_scraper.octopus import Octopus
from octopus_scraper.service.app import app
from octopus_scraper.service.config_helpers import _get_memory_usage

logger = structlog.get_logger()


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
                            "id": scraper.id,
                            "name": scraper.name,
                            "status": scraper.status,
                            "enabled": scraper.enabled,
                            "fetcher": scraper.fetcher,
                            "source_path": scraper.source_path,
                        }
                        for scraper in config_status.scrapers
                    ],
                    "error_message": config_status.error_message,
                    "file_errors": config_manager.get_file_errors(),
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
    """Rescan the scraper configuration directory."""
    try:
        config_manager: ConfigManager = app.ctx.config_manager

        # Get current state before reload
        old_version = config_manager.get_current_version()
        old_scrapers_count = len(config_manager.get_current_scrapers())

        config_changed = await config_manager.reload_config_if_changed()
        new_version = config_manager.get_current_version()
        new_scrapers_count = len(config_manager.get_current_scrapers())
        return json(
            {
                "status": "success",
                "message": (
                    "Configuration directory changes applied"
                    if config_changed
                    else "Configuration directory is unchanged"
                ),
                "config_changed": config_changed,
                "reload_performed": config_changed,
                "changes": {
                    "old_version": old_version.version_id if old_version else None,
                    "new_version": new_version.version_id if new_version else None,
                    "old_scrapers_count": old_scrapers_count,
                    "new_scrapers_count": new_scrapers_count,
                    "change_summary": (
                        new_version.change_summary if new_version else None
                    ),
                },
                "file_errors": config_manager.get_file_errors(),
                "timestamp": datetime.now().isoformat(),
            }
        )

    except Exception as e:
        logger.error("Failed to refresh config", error=str(e), exc_info=True)
        return json(
            {"status": "error", "message": f"Configuration refresh failed: {e}"},
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
                "scraper_config_dir": str(config_manager.file_settings.directory),
                "config_poll_interval_seconds": (
                    config_manager.file_settings.poll_interval_seconds
                ),
                "config_debounce_seconds": (
                    config_manager.file_settings.debounce_seconds
                ),
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
            "storage": {
                "database_url_configured": bool(octopus._storage.config.url),
                "notion_sync": octopus.get_sync_status(),
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

        current_scrapers = config_manager.get_all_scrapers()

        # Build detailed scraper information
        scrapers_info = []
        for i, scraper_config in enumerate(current_scrapers):
            scraper_info = {
                "index": i,
                "id": scraper_config.id,
                "name": scraper_config.name,
                "status": scraper_config.status,
                "enabled": scraper_config.enabled,
                "fetcher": scraper_config.fetcher,
                "hub_root": scraper_config.hub_root,
                "route": scraper_config.route,
                "priority": scraper_config.priority,
                "fetch_params": scraper_config.fetch_params,
                "is_active": scraper_config.enabled,
                "source_path": scraper_config.source_path,
            }

            # Add runtime information if available
            runtime_entry = next(
                (entry for entry in octopus._scrapers if entry[2] == scraper_config.id),
                None,
            )
            if runtime_entry is not None:
                runtime_scraper, runtime_params, _, _ = runtime_entry
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
