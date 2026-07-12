"""Tests for Prometheus metrics registration and exposition."""

from prometheus_client import CollectorRegistry

from octopus_scraper.metrics import OctopusMetrics
from octopus_scraper.service.metrics import prometheus_metrics


def test_metrics_register_and_update_values():
    registry = CollectorRegistry()
    test_metrics = OctopusMetrics(registry)

    test_metrics.configure_task_manager(queue_capacity=100, workers=3)
    test_metrics.set_task_state(queued=4, running=2)
    test_metrics.tasks_submitted.inc()
    test_metrics.record_task_completed(duration=2.5, items_fetched=7)
    test_metrics.record_config_refresh(success=True)
    test_metrics.record_external_request("rss", duration=0.4, success=False)
    test_metrics.record_upload(requested=3, processed=2, failed=1)

    output = test_metrics.render().decode()

    assert "octopus_tasks_submitted_total 1.0" in output
    assert "octopus_tasks_completed_total 1.0" in output
    assert "octopus_tasks_queued 4.0" in output
    assert "octopus_tasks_running 2.0" in output
    assert "octopus_task_queue_capacity 100.0" in output
    assert "octopus_config_healthy 1.0" in output
    assert 'octopus_external_requests_total{dependency="rss"} 1.0' in output
    assert 'octopus_external_request_failures_total{dependency="rss"} 1.0' in output
    assert 'octopus_upload_items_total{outcome="processed"} 2.0' in output
    assert 'octopus_upload_items_total{outcome="failed"} 1.0' in output


def test_metrics_reject_unbounded_dependency_labels():
    test_metrics = OctopusMetrics(CollectorRegistry())

    try:
        test_metrics.record_external_request(
            "https://example.com/feed", duration=1, success=True
        )
    except ValueError as error:
        assert "Unsupported metrics dependency" in str(error)
    else:
        raise AssertionError("Dynamic dependency labels must be rejected")


async def test_metrics_endpoint_uses_prometheus_exposition_format():
    response = await prometheus_metrics(None)

    assert response.status == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert b"# HELP octopus_build_info" in response.body
    assert b"octopus_service_uptime_seconds" in response.body
    assert b"task_id" not in response.body
