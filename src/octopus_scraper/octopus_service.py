from dataclasses import asdict
import os

from sanic import Sanic
from sanic.exceptions import SanicException
from sanic.response import json
from dotenv import load_dotenv

import structlog

from octopus_scraper.octopus import Octopus
from octopus_scraper.service_models import (
    HealthCheckResponse,
    TriggerScraperResponse,
    TriggerUploadResponse,
)

load_dotenv()  # take environment variables
# 初始化日志配置
log_format = os.getenv("LOG_FORMAT", "plain")
if log_format == "json":
    structlog.configure(processors=[structlog.processors.JSONRenderer()])
else:
    structlog.configure(processors=[structlog.dev.ConsoleRenderer()])

logger = structlog.get_logger()

app = Sanic("OctopusService")

SERVICE_CONFIG = {
    "host": os.getenv("SERVICE_HOST", "0.0.0.0"),
    "port": int(os.getenv("SERVICE_PORT", "8000")),
    "debug": os.getenv("DEBUG", "False").lower() == "true",
    "log_level": os.getenv("LOG_LEVEL", "INFO"),
}


@app.listener("before_server_start")
async def setup_octopus(app, _):
    """初始化Octopus实例"""
    try:
        # 这里需要根据实际配置加载Octopus
        # 示例配置，实际应从Notion或环境变量获取
        config = {
            "scrapers_config_with_fetch_params": [],
            "notion_api_config": {
                "api_key": os.getenv("NOTION_API_KEY"),
                "database_id": os.getenv("DATABASE_ID"),
            },
        }
        app.ctx.octopus = Octopus(config)
        logger.info("Octopus instance initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Octopus: {e}")
        raise SanicException("Service unavailable", status_code=503)


@app.route("/health", methods=["GET"])
async def health_check(request):
    """健康检查接口"""
    return json(asdict(HealthCheckResponse(status="ok")))


@app.route("/trigger_scraper", methods=["POST"])
async def trigger_scraper(request):
    """触发抓取任务"""
    try:
        octopus: Octopus = app.ctx.octopus
        octopus.trigger_scraper()

        response = TriggerScraperResponse(
            status="success",
            message="Scraping completed",
            data={
                "source_count": len(octopus._scrapers),
                "item_count": len(octopus._fetched_contents),
            },
        )
        return json(asdict(response))
    except Exception as e:
        logger.error(f"Scraper error: {e}", exc_info=True)
        return json(
            {
                "status": "error",
                "message": str(e),
                "error_code": "SCRAPER_ERROR",
                "details": {"exception": str(type(e).__name__)},
            },
            status=500,
        )


@app.route("/trigger_upload", methods=["POST"])
async def trigger_upload(request):
    """触发上传任务"""
    try:
        octopus: Octopus = app.ctx.octopus
        octopus.trigger_upload()

        response = TriggerUploadResponse(
            status="success",
            message="Upload completed",
            data={"uploaded_count": len(octopus._fetched_contents)},
        )
        return json(asdict(response))
    except Exception as e:
        logger.error(f"Upload error: {e}", exc_info=True)
        return json(
            {
                "status": "error",
                "message": str(e),
                "error_code": "UPLOAD_ERROR",
                "details": {"exception": str(type(e).__name__)},
            },
            status=500,
        )


if __name__ == "__main__":
    app.run(
        host=SERVICE_CONFIG["host"],
        port=SERVICE_CONFIG["port"],
        debug=SERVICE_CONFIG["debug"],
    )
