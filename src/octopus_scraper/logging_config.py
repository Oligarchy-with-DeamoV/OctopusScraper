"""Logging configuration helpers for OctopusScraper."""

import logging
from typing import ClassVar, Tuple


class LoggingConfigurator:
    """Configure application and third-party logger levels."""

    _NOISY_LOGGERS: ClassVar[Tuple[str, ...]] = ("httpx", "httpcore")

    @classmethod
    def configure_service_logging(cls, log_level: str) -> None:
        """Apply the requested root log level and quiet noisy HTTP clients."""
        logging.getLogger().setLevel(getattr(logging, log_level))

        for logger_name in cls._NOISY_LOGGERS:
            logging.getLogger(logger_name).setLevel(logging.WARNING)
