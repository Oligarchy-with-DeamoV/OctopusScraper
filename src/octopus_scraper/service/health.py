"""Health check endpoints for OctopusService."""

import os
from datetime import datetime

import structlog
from sanic.response import json

from octopus_scraper.config import ConfigManager
from octopus_scraper.service.app import _health_cache, app
from octopus_scraper.service.config_helpers import _get_memory_usage

logger = structlog.get_logger()


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
