"""
Backward-compatible re-export module for OctopusService.

The service implementation has been decomposed into the ``octopus_scraper.service``
package. This module re-exports all public names so that existing imports such as
``from octopus_scraper.octopus_service import app`` continue to work.
"""

from octopus_scraper.service import (  # noqa: F401
    DEFAULT_SERVICE_CONFIG,
    _get_memory_usage,
    _health_cache,
    app,
    cleanup_octopus,
    create_config_from_env,
    get_config_status,
    get_system_info,
    get_task_details,
    get_task_stats,
    health_check,
    list_scrapers,
    list_tasks,
    liveness_check,
    log_registered_routes,
    prometheus_metrics,
    logger,
    readiness_check,
    refresh_config,
    reload_octopus_config,
    setup_octopus,
    trigger_scraper,
    trigger_upload,
)
