from doraemon.logger.slogger import configure_structlog
import structlog

configure_structlog()
logger = structlog.getLogger(__name__)


def run_octopus_go():
    logger.info("hello occcctopus")
