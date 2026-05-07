"""Sanic application instance and shared state for OctopusService."""

from sanic import Sanic

app_name = "OctopusService"
app = Sanic(app_name)

# Health check cache to avoid expensive operations on every request
_health_cache = {
    "last_check": None,
    "cache_duration": 30,  # seconds
    "cached_result": None,
}
