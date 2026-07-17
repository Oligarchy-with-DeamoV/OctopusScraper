"""Prometheus exposition endpoint."""

from prometheus_client import CONTENT_TYPE_LATEST
from sanic.response import raw

from octopus_scraper.metrics import metrics
from octopus_scraper.service.app import app


@app.route("/metrics", methods=["GET"])
async def prometheus_metrics(request):
    """Expose service metrics in Prometheus text format."""
    metrics.refresh_app_state(app)
    return raw(metrics.render(), headers={"Content-Type": CONTENT_TYPE_LATEST})
