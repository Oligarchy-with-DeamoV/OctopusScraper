from unittest.mock import Mock, patch

import pytest

from octopus_scraper.cli import create_service_args, run_octopus_service


class TestCLI:
    @patch(
        "sys.argv",
        [
            "service",
            "--host",
            "127.0.0.1",
            "--port",
            "9000",
            "--debug",
            "--scraper-config-dir",
            "/tmp/scrapers",
        ],
    )
    def test_create_service_args_custom_values(self):
        args = create_service_args()
        assert args.host == "127.0.0.1"
        assert args.port == 9000
        assert args.debug is True
        assert args.scraper_config_dir == "/tmp/scrapers"

    @patch("sys.argv", ["service", "--log-level", "WARNING"])
    def test_create_service_args_log_level_choices(self):
        assert create_service_args().log_level == "WARNING"

    @patch("sys.argv", ["service", "--log-format", "json"])
    def test_create_service_args_log_format_choices(self):
        assert create_service_args().log_format == "json"

    @patch("octopus_scraper.cli.create_service_args")
    @patch("octopus_scraper.octopus_service.app")
    @patch("octopus_scraper.cli.LoggingConfigurator.configure_service_logging")
    @patch("structlog.configure")
    def test_run_octopus_service_single_process(
        self,
        mock_structlog,
        mock_configure_logging,
        mock_app,
        mock_create_args,
    ):
        mock_create_args.return_value = Mock(
            host="127.0.0.1",
            port=8000,
            debug=False,
            log_level="INFO",
            log_format="plain",
            scraper_config_dir="/tmp/scrapers",
        )

        run_octopus_service()

        mock_app.run.assert_called_once_with(
            host="127.0.0.1",
            port=8000,
            debug=False,
            single_process=True,
        )
        mock_configure_logging.assert_called_once_with("INFO")

    @patch("octopus_scraper.cli.create_service_args")
    @patch("octopus_scraper.octopus_service.app")
    @patch("octopus_scraper.cli.LoggingConfigurator.configure_service_logging")
    def test_run_octopus_service_exception(
        self,
        mock_configure_logging,
        mock_app,
        mock_create_args,
    ):
        mock_create_args.return_value = Mock(
            host="127.0.0.1",
            port=8000,
            debug=False,
            log_level="INFO",
            log_format="plain",
            scraper_config_dir="/tmp/scrapers",
        )
        mock_app.run.side_effect = RuntimeError("Service failed")

        with pytest.raises(RuntimeError, match="Service failed"):
            run_octopus_service()
