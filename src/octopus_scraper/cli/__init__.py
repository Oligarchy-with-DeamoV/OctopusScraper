import argparse
import os

import structlog
from doraemon.logger.slogger import configure_structlog
from octopus_scraper.logging_config import LoggingConfigurator

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
        default=os.getenv(
            "SERVICE_HOST", os.getenv("OCTOPUS_HOST", "0.0.0.0")
        ),  # nosec B104
        help="Host to bind the service (default: 0.0.0.0, env: SERVICE_HOST)",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("SERVICE_PORT", os.getenv("OCTOPUS_PORT", "8000"))),
        help="Port to bind the service (default: 8000, env: SERVICE_PORT)",
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

    parser.add_argument(
        "--scraper-config-dir",
        type=str,
        default=os.getenv("SCRAPER_CONFIG_DIR", "resources/scrapers.d"),
        help=(
            "Directory containing one scraper per .yml/.yaml file "
            "(env: SCRAPER_CONFIG_DIR)"
        ),
    )

    return parser.parse_args()


def run_octopus_service():
    """Start the OctopusScraper web service."""
    args = create_service_args()

    # Configure logging based on arguments
    # `add_log_level` 将 level 名称注入事件字典，是下游日志消费方
    # （Vector → 飞书告警、ELK 等）按级别过滤的前提；没有它两种渲染器
    # 都不会把 level 写进输出。务必保持在渲染器之前。
    if args.log_format == "json":
        structlog.configure(
            processors=[
                structlog.processors.add_log_level,
                structlog.processors.JSONRenderer(),
            ]
        )
    else:
        structlog.configure(
            processors=[
                structlog.processors.add_log_level,
                structlog.dev.ConsoleRenderer(),
            ]
        )

    LoggingConfigurator.configure_service_logging(args.log_level)
    os.environ["SCRAPER_CONFIG_DIR"] = args.scraper_config_dir

    logger.info(
        "Starting OctopusScraper service",
        host=args.host,
        port=args.port,
        debug=args.debug,
        log_level=args.log_level,
        scraper_config_dir=args.scraper_config_dir,
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
