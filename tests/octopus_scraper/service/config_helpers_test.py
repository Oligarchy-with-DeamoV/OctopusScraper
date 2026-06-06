"""Tests for service/config_helpers.py — the env-driven config builders.

The two behaviours covered here matter operationally:

* ``get_rsshub_request_timeout`` is what allows operators to tune RSSHub
  read/connect timeouts from the environment without touching code or
  Notion. We verify defaults and overrides.
* ``build_fetcher_config`` is now the single source of truth for how a
  ``ScraperConfig`` becomes a fetcher_config dict, so a regression here
  would silently break either the scraper lifecycle or the admin
  endpoints. We verify rsshub gets the timeout, direct_rss does not, and
  ``include_fetch_params`` toggles correctly.
"""

import os
from unittest.mock import patch

import pytest

from octopus_scraper.config.models import ScraperConfig
from octopus_scraper.service.config_helpers import (
    DEFAULT_RSSHUB_CONNECT_TIMEOUT,
    DEFAULT_RSSHUB_READ_TIMEOUT,
    build_fetcher_config,
    get_rsshub_request_timeout,
)


class TestGetRsshubRequestTimeout:
    def test_defaults_match_historical_hardcoded_values(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RSSHUB_CONNECT_TIMEOUT", None)
            os.environ.pop("RSSHUB_READ_TIMEOUT", None)

            connect, read = get_rsshub_request_timeout()

            assert connect == DEFAULT_RSSHUB_CONNECT_TIMEOUT == 10.0
            assert read == DEFAULT_RSSHUB_READ_TIMEOUT == 1200.0

    def test_env_overrides_are_applied(self):
        with patch.dict(
            os.environ,
            {"RSSHUB_CONNECT_TIMEOUT": "5", "RSSHUB_READ_TIMEOUT": "300"},
            clear=False,
        ):
            assert get_rsshub_request_timeout() == (5.0, 300.0)

    def test_partial_override_keeps_other_default(self):
        with patch.dict(os.environ, {"RSSHUB_READ_TIMEOUT": "600"}, clear=False):
            os.environ.pop("RSSHUB_CONNECT_TIMEOUT", None)
            connect, read = get_rsshub_request_timeout()
            assert connect == DEFAULT_RSSHUB_CONNECT_TIMEOUT
            assert read == 600.0

    def test_invalid_env_value_raises(self):
        with patch.dict(
            os.environ, {"RSSHUB_READ_TIMEOUT": "not-a-number"}, clear=False
        ):
            with pytest.raises(ValueError):
                get_rsshub_request_timeout()


class TestBuildFetcherConfig:
    def _scraper(self, fetcher: str) -> ScraperConfig:
        return ScraperConfig(
            name="demo",
            status="Active",
            fetcher=fetcher,
            hub_root="http://example.com",
            route="/feed",
            fetch_params={"limit": 5},
        )

    def test_rsshub_includes_request_timeout_and_fetch_params(self):
        scraper = self._scraper("rsshub")
        with patch.dict(
            os.environ,
            {"RSSHUB_CONNECT_TIMEOUT": "7", "RSSHUB_READ_TIMEOUT": "900"},
            clear=False,
        ):
            cfg = build_fetcher_config(scraper)

        assert cfg == {
            "hub_root": "http://example.com",
            "route": "/feed",
            "fetch_params": {"limit": 5},
            "request_timeout": (7.0, 900.0),
        }

    def test_direct_rss_does_not_get_rsshub_timeout(self):
        """direct_rss has its own default (10, 60); the RSSHUB_* env vars must
        not bleed into it, otherwise unrelated feeds inherit a 20-minute read
        timeout silently."""
        scraper = self._scraper("direct_rss")
        with patch.dict(
            os.environ,
            {"RSSHUB_CONNECT_TIMEOUT": "7", "RSSHUB_READ_TIMEOUT": "900"},
            clear=False,
        ):
            cfg = build_fetcher_config(scraper)

        assert "request_timeout" not in cfg
        assert cfg["hub_root"] == "http://example.com"
        assert cfg["route"] == "/feed"
        assert cfg["fetch_params"] == {"limit": 5}

    def test_include_fetch_params_false_omits_key(self):
        scraper = self._scraper("rsshub")
        cfg = build_fetcher_config(scraper, include_fetch_params=False)
        assert "fetch_params" not in cfg
        # rsshub timeout still injected
        assert "request_timeout" in cfg

    def test_none_fetch_params_normalised_to_empty_dict(self):
        scraper = ScraperConfig(
            name="demo",
            status="Active",
            fetcher="rsshub",
            hub_root="http://example.com",
            route="/feed",
            fetch_params=None,
        )
        cfg = build_fetcher_config(scraper)
        assert cfg["fetch_params"] == {}
