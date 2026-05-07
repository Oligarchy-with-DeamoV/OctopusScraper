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
    admin_overview,
    app,
    cancel_task,
    cleanup_octopus,
    clear_cache,
    create_config_from_env,
    dump_service_state,
    force_garbage_collection,
    get_config_status,
    get_monitoring_metrics,
    get_system_info,
    get_task_details,
    get_task_stats,
    health_check,
    list_scrapers,
    list_tasks,
    liveness_check,
    log_registered_routes,
    logger,
    manage_config_watcher,
    readiness_check,
    refresh_config,
    reload_octopus_config,
    run_scraper_test,
    setup_octopus,
    submit_individual_task,
    trigger_scraper,
    trigger_upload,
    validate_config,
)
