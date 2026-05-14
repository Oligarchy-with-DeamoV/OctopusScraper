import logging
from unittest.mock import Mock, patch

from octopus_scraper.logging_config import LoggingConfigurator


class TestLoggingConfigurator:
    @patch("logging.getLogger")
    def test_configure_service_logging_keeps_http_clients_at_warning(
        self, mock_get_logger
    ):
        """Keep noisy HTTP client loggers quieter than the application root logger."""
        mock_root_logger = Mock()
        mock_httpx_logger = Mock()
        mock_httpcore_logger = Mock()

        logger_map = {
            None: mock_root_logger,
            "httpx": mock_httpx_logger,
            "httpcore": mock_httpcore_logger,
        }
        mock_get_logger.side_effect = lambda name=None: logger_map[name]

        LoggingConfigurator.configure_service_logging("INFO")

        mock_root_logger.setLevel.assert_called_once_with(logging.INFO)
        mock_httpx_logger.setLevel.assert_called_once_with(logging.WARNING)
        mock_httpcore_logger.setLevel.assert_called_once_with(logging.WARNING)
