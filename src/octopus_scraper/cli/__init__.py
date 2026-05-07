import argparse
import os

import structlog
import yaml
from doraemon.logger.slogger import configure_structlog

configure_structlog()
logger = structlog.getLogger(__name__)


def create_service_args():
    """Create argument parser for service command."""
    parser = argparse.ArgumentParser(
        description="Start OctopusScraper Web Service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                  # Start with default settings
  %(prog)s --host 127.0.0.1 --port 8080   # Custom host and port
  %(prog)s --debug                         # Enable debug mode
  %(prog)s --log-level DEBUG               # Set log level
        """,
    )

    parser.add_argument(
        "--host",
        type=str,
        default=os.getenv("OCTOPUS_HOST", "0.0.0.0"),
        help="Host to bind the service (default: 0.0.0.0, env: OCTOPUS_HOST)",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("OCTOPUS_PORT", "8000")),
        help="Port to bind the service (default: 8000, env: OCTOPUS_PORT)",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        default=os.getenv("OCTOPUS_DEBUG", "false").lower() == "true",
        help="Enable debug mode (default: false, env: OCTOPUS_DEBUG)",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=os.getenv("OCTOPUS_LOG_LEVEL", "INFO"),
        help="Set log level (default: INFO, env: OCTOPUS_LOG_LEVEL)",
    )

    parser.add_argument(
        "--log-format",
        type=str,
        choices=["plain", "json"],
        default=os.getenv("OCTOPUS_LOG_FORMAT", "plain"),
        help="Set log format (default: plain, env: OCTOPUS_LOG_FORMAT)",
    )

    return parser.parse_args()


def load_yml_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_octopus_service():
    """Start the OctopusScraper web service."""
    args = create_service_args()

    # Configure logging based on arguments
    if args.log_format == "json":
        structlog.configure(processors=[structlog.processors.JSONRenderer()])
    else:
        structlog.configure(processors=[structlog.dev.ConsoleRenderer()])

    # Set log level
    import logging

    logging.getLogger().setLevel(getattr(logging, args.log_level))

    logger.info(
        "Starting OctopusScraper service",
        host=args.host,
        port=args.port,
        debug=args.debug,
        log_level=args.log_level,
    )

    # Import and configure the service
    from octopus_scraper.octopus_service import app

    # Update service configuration
    service_config = {
        "host": args.host,
        "port": args.port,
        "debug": args.debug,
        "single_process": True,
    }

    try:
        logger.info("Starting service", config=service_config)
        app.run(**service_config)
    except KeyboardInterrupt:
        logger.info("Service shutdown requested by user")
    except Exception as e:
        logger.error("Service failed to start", error=str(e))
        raise
