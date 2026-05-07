"""Core route handlers for OctopusService (trigger_scraper, trigger_upload)."""

import asyncio
from dataclasses import asdict

import structlog
from sanic.response import json

from octopus_scraper.octopus import Octopus
from octopus_scraper.service.app import app
from octopus_scraper.service_models import TriggerScraperResponse, TriggerUploadResponse

logger = structlog.get_logger()


@app.route("/trigger_scraper", methods=["POST"])
async def trigger_scraper(request):
    """触发抓取任务，将任务提交到 TaskManager 异步执行。"""
    try:
        octopus: Octopus = app.ctx.octopus
        # trigger_scraper 提交任务到 TaskManager 并返回 batch_id
        batch_id = octopus.trigger_scraper()

        response = TriggerScraperResponse(
            status="success",
            message="Scraper tasks submitted successfully.",
            data={
                "batch_id": batch_id,
                "source_count": len(octopus._scrapers),
            },
        )
        return json(asdict(response))
    except Exception as e:
        logger.error("Scraping task submission failed", error=str(e), exc_info=True)
        response = TriggerScraperResponse(
            status="error", message=f"An unexpected error occurred: {e}"
        )
        return json(asdict(response), status=500)


@app.route("/trigger_upload", methods=["POST"])
async def trigger_upload(request):
    """从 TaskManager 已完成任务中收集未上传内容并上传到 Notion。"""
    try:
        octopus: Octopus = app.ctx.octopus
        # trigger_upload 涉及同步 Notion API 调用，使用 to_thread 避免阻塞事件循环
        upload_result = await asyncio.to_thread(octopus.trigger_upload)

        response = TriggerUploadResponse(
            status="success",
            message="Upload completed successfully.",
            data=upload_result,
        )
        return json(asdict(response))
    except Exception as e:
        logger.error("Upload task failed", error=str(e), exc_info=True)
        response = TriggerUploadResponse(
            status="error", message=f"An unexpected error occurred: {e}"
        )
        return json(asdict(response), status=500)
