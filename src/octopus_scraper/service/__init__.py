"""
OctopusService package — Sanic web service for OctopusScraper.

This package organizes the service into submodules:
- app: Sanic application instance and shared state
- config_helpers: Configuration creation and utility functions
- lifecycle: Server lifecycle hooks (setup, cleanup, reload)
- health: Health check endpoints (/health, /health/liveness, /health/readiness)
- routes: Core route handlers (/trigger_scraper, /trigger_upload)
- admin: Admin management API endpoints (/admin/*)
"""

# Import app and shared state
from octopus_scraper.service.app import _health_cache, app  # noqa: F401

# Import config helpers
from octopus_scraper.service.config_helpers import (  # noqa: F401
    DEFAULT_SERVICE_CONFIG,
    _get_memory_usage,
    create_config_from_env,
    logger,
)

# Import lifecycle hooks — these register @app.listener decorators on import
from octopus_scraper.service.lifecycle import (  # noqa: F401
    cleanup_octopus,
    log_registered_routes,
    reload_octopus_config,
    setup_octopus,
)

# Import health endpoints — these register @app.route decorators on import
from octopus_scraper.service.health import (  # noqa: F401
    health_check,
    liveness_check,
    readiness_check,
)

# Import core routes — these register @app.route decorators on import
from octopus_scraper.service.routes import (  # noqa: F401
    trigger_scraper,
    trigger_upload,
)

# Import Prometheus endpoint — registers /metrics
from octopus_scraper.service.metrics import prometheus_metrics  # noqa: F401

# Import admin routes — these register @app.route decorators on import
from octopus_scraper.service.admin import (  # noqa: F401
    get_config_status,
    get_monitoring_metrics,
    get_system_info,
    get_task_details,
    get_task_stats,
    list_scrapers,
    list_tasks,
    refresh_config,
)

__all__ = [
    "app",
    "_health_cache",
    "DEFAULT_SERVICE_CONFIG",
    "_get_memory_usage",
    "create_config_from_env",
    "logger",
    "setup_octopus",
    "cleanup_octopus",
    "log_registered_routes",
    "reload_octopus_config",
    "health_check",
    "liveness_check",
    "readiness_check",
    "trigger_scraper",
    "trigger_upload",
    "prometheus_metrics",
    "get_config_status",
    "get_monitoring_metrics",
    "get_system_info",
    "get_task_details",
    "get_task_stats",
    "list_scrapers",
    "list_tasks",
    "refresh_config",
]
