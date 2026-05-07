import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

import structlog
from dacite import from_dict

from octopus_scraper.scraper import BaseScraperConfig, Content, Scraper
from octopus_scraper.storages.notion_storage import NotionAPIConfig, NotionStorage
from octopus_scraper.task_manager import ScraperTask, TaskBatch, TaskManager

logger = structlog.getLogger(__name__)


@dataclass
class ScraperRuntimeConfig:
    scraper_config: BaseScraperConfig
    fetch_params: dict


@dataclass
class OctopusConfig:
    scrapers_config_with_fetch_params: List[ScraperRuntimeConfig]
    notion_api_config: NotionAPIConfig
    max_concurrent_scrapers: int = 5  # 默认最大并发数为5
    use_task_manager: bool = True  # 强制使用任务管理器
    task_manager_config: Optional[Dict[str, Any]] = None  # 任务管理器配置


class Octopus:
    def __init__(self, config: Dict):
        self._config = from_dict(OctopusConfig, config)
        self._scrapers: List[Tuple[Scraper, Dict]] = []
        self._fetched_contents: List[Content] = []
        self._notion_api: NotionStorage = NotionStorage(
            asdict(self._config.notion_api_config)
        )

        # Initialize task manager - always enabled
        task_manager_config = self._config.task_manager_config or {}
        self._task_manager = TaskManager(
            max_concurrent_tasks=task_manager_config.get(
                "max_concurrent_tasks", self._config.max_concurrent_scrapers
            ),
            max_queue_size=task_manager_config.get("max_queue_size", 1000),
            result_retention_hours=task_manager_config.get(
                "result_retention_hours", 24
            ),
        )
        self._task_manager.set_storage(self._notion_api)
        self._upload_lock = threading.Lock()

        try:
            self._setup()
        except Exception as e:
            logger.error(
                f"Activate scrapers init failed with exception: {e}.",
                config=self._config,
            )
            raise RuntimeError(f"Activate scrapers init failed with exception: {e}.")
        self._health_check()

    def _setup(self):
        for scraper_runtime_config in self._config.scrapers_config_with_fetch_params:
            self._setup_single_scrapper(
                scraper_runtime_config.scraper_config,
                scraper_runtime_config.fetch_params,
            )

    def _setup_single_scrapper(self, config: Any, fetch_params: Dict):
        """初始化 scraper，同时设置对应的 fetch_params"""
        self._scrapers.append((Scraper(asdict(config)), fetch_params))

        # set storage for the scraper for content id check
        for scraper, _ in self._scrapers:
            scraper.set_storage(self._notion_api)

    def set_max_concurrent_scrapers(self, max_workers: int):
        """动态设置最大并发scraper数量"""
        self._config.max_concurrent_scrapers = max_workers
        logger.info(f"Set max concurrent scrapers to {max_workers}")

    def _health_check(self):
        """针对设置的 Scraper 和 NotionAPI 进行健康检查"""
        pass

    def trigger_scraper(self):
        """触发一次 Scraper - 使用任务管理器"""
        logger.info("Using TaskManager for scraper execution")

        # 创建任务批次
        tasks = []
        for scraper, params in self._scrapers:
            # 从 scraper 配置中提取信息
            scraper_config = {
                "name": getattr(scraper.config, "scraper_name", None)
                or getattr(scraper.config, "fetcher_name", "unknown"),
                "fetcher_name": scraper.config.fetcher_name,
                "fetcher_config": scraper.config.fetcher_config,
                "content_processor_configs": scraper.config.content_processor_configs,
                "default_keywords": getattr(scraper.config, "default_keywords", None)
                or [],
            }

            task = ScraperTask.from_scraper_config(scraper_config, params)
            tasks.append(task)

        # 提交任务批次
        batch = TaskBatch(
            batch_id=f"scraper_batch_{int(time.time())}",
            tasks=tasks,
            name="Manual Scraper Trigger",
            description="Manually triggered scraper batch execution",
        )

        submitted_task_ids = self._task_manager.submit_batch(batch)

        logger.info(
            "Scraper tasks submitted to TaskManager",
            batch_id=batch.batch_id,
            task_count=len(tasks),
            submitted_count=len(submitted_task_ids),
        )

        return batch.batch_id

    def trigger_upload(self) -> Dict[str, Any]:
        """从 TaskManager 已完成任务中收集未上传的内容并批量上传到 Notion。

        Uses a non-blocking lock to prevent concurrent uploads. If an upload
        is already in progress, returns immediately with zero counts.

        Returns:
            Dict containing upload statistics:
                - uploaded_count: Number of successfully uploaded items.
                - tasks_processed: Number of completed tasks whose contents were uploaded.
                - errors: List of error messages if any tasks failed to upload.
        """
        if not self._upload_lock.acquire(blocking=False):
            logger.info("Upload already in progress, skipping")
            return {
                "uploaded_count": 0,
                "tasks_processed": 0,
                "errors": [],
            }
        try:
            return self._do_upload()
        finally:
            self._upload_lock.release()

    def _do_upload(self) -> Dict[str, Any]:
        """Internal upload logic. Must be called while holding _upload_lock."""
        from octopus_scraper.task_manager.models import TaskStatus

        upload_stats: Dict[str, Any] = {
            "uploaded_count": 0,
            "tasks_processed": 0,
            "errors": [],
        }

        try:
            # Collect contents from completed tasks that have not been uploaded yet
            completed_tasks = self._task_manager.list_tasks(
                status=TaskStatus.COMPLETED, limit=1000
            )

            all_contents: List[Content] = []
            processed_task_ids: List[str] = []
            # Track which content index belongs to which task
            content_task_mapping: List[str] = []  # index -> task_id

            for task_result in completed_tasks:
                # Skip tasks with no remaining contents to upload
                contents = task_result.metadata.get("contents", [])
                if not contents:
                    continue

                for content in contents:
                    content_task_mapping.append(task_result.task_id)
                all_contents.extend(contents)
                processed_task_ids.append(task_result.task_id)

            if not all_contents:
                logger.info("No pending contents to upload from completed tasks")
                return upload_stats

            # Upload collected contents to Notion
            upload_results = self._notion_api.store_contents(
                all_contents, deduplicate=True
            )

            # Map results back to tasks: determine which contents succeeded per task
            task_success_ids: Dict[str, set] = (
                {}
            )  # task_id -> set of succeeded content_ids
            for i, (content, success) in enumerate(zip(all_contents, upload_results)):
                task_id = content_task_mapping[i]
                if success:
                    if task_id not in task_success_ids:
                        task_success_ids[task_id] = set()
                    task_success_ids[task_id].add(content.content_id)

            # Update each task: remove succeeded contents, keep failed ones
            total_uploaded = 0
            for task_id in processed_task_ids:
                task_result = self._task_manager.get_task_result(task_id)
                if not task_result:
                    continue

                succeeded_ids = task_success_ids.get(task_id, set())
                task_contents = task_result.metadata.get("contents", [])

                # Separate succeeded and failed contents
                failed_contents = [
                    c for c in task_contents if c.content_id not in succeeded_ids
                ]

                # Update items_uploaded (cumulative)
                task_result.items_uploaded += len(succeeded_ids)
                total_uploaded += len(succeeded_ids)

                if failed_contents:
                    # Keep failed contents in metadata for next cycle
                    task_result.metadata["contents"] = failed_contents
                    logger.warning(
                        "Some contents failed to upload, kept for retry",
                        task_id=task_id,
                        succeeded=len(succeeded_ids),
                        failed=len(failed_contents),
                    )
                else:
                    # All contents uploaded, clear metadata
                    task_result.metadata.pop("contents", None)

            upload_stats["uploaded_count"] = total_uploaded
            upload_stats["tasks_processed"] = len(processed_task_ids)

            logger.info(
                "Upload completed",
                uploaded_count=total_uploaded,
                tasks_processed=len(processed_task_ids),
                total_contents_collected=len(all_contents),
            )

            return upload_stats

        except Exception as e:
            logger.error(
                "Failed to upload contents to Notion.",
                error=str(e),
                exc_info=True,
            )
            raise RuntimeError(f"Failed to upload contents to Notion: {e}")

    # Task Management Methods

    def get_task_manager(self) -> TaskManager:
        """获取任务管理器实例"""
        return self._task_manager

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        result = self._task_manager.get_task_result(task_id)
        if not result:
            return None

        return {
            "task_id": result.task_id,
            "status": result.status.value,
            "start_time": result.start_time.isoformat(),
            "end_time": result.end_time.isoformat() if result.end_time else None,
            "duration_seconds": result.duration_seconds,
            "items_fetched": result.items_fetched,
            "items_processed": result.items_processed,
            "items_uploaded": result.items_uploaded,
            "error_message": result.error_message,
            "metadata": result.metadata,
        }

    def list_tasks(
        self, status: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """列出任务"""
        from octopus_scraper.task_manager.models import TaskStatus

        task_status = None
        if status:
            try:
                task_status = TaskStatus(status)
            except ValueError:
                logger.warning(f"Invalid task status: {status}")

        results = self._task_manager.list_tasks(status=task_status, limit=limit)

        return [
            {
                "task_id": result.task_id,
                "status": result.status.value,
                "start_time": result.start_time.isoformat(),
                "end_time": result.end_time.isoformat() if result.end_time else None,
                "duration_seconds": result.duration_seconds,
                "items_fetched": result.items_fetched,
                "items_processed": result.items_processed,
                "items_uploaded": result.items_uploaded,
                "error_message": result.error_message,
                "metadata": result.metadata,
            }
            for result in results
        ]

    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        return self._task_manager.cancel_task(task_id)

    def get_task_manager_statistics(self) -> Dict[str, Any]:
        """获取任务管理器统计信息"""
        return self._task_manager.get_statistics()

    def submit_individual_scraper_task(
        self,
        scraper_name: str,
        scraper_config: Dict[str, Any],
        fetch_params: Dict[str, Any],
    ) -> str:
        """提交单个抓取任务"""
        task = ScraperTask.from_scraper_config(scraper_config, fetch_params)
        task.scraper_name = scraper_name

        return self._task_manager.submit_task(task)

    def wait_for_batch_completion(
        self, batch_id: str, timeout_seconds: int = 300
    ) -> Dict[str, Any]:
        """等待批次任务完成"""
        start_time = time.time()
        completed_tasks = []
        failed_tasks = []

        # Note: This is a simplified implementation
        # In a production system, you'd want proper batch tracking
        while time.time() - start_time < timeout_seconds:
            # Check task results with batch_id in metadata
            tasks = self._task_manager.list_tasks(limit=1000)
            batch_tasks = [
                task
                for task in tasks
                if task.get("metadata", {}).get("batch_id") == batch_id
            ]

            running_tasks = [
                t for t in batch_tasks if t["status"] in ["pending", "running"]
            ]
            completed_tasks = [t for t in batch_tasks if t["status"] == "completed"]
            failed_tasks = [t for t in batch_tasks if t["status"] == "failed"]

            if not running_tasks:
                break

            time.sleep(1)

        return {
            "batch_id": batch_id,
            "completed": len(completed_tasks),
            "failed": len(failed_tasks),
            "total_items_fetched": sum(t["items_fetched"] for t in completed_tasks),
            "timeout": time.time() - start_time >= timeout_seconds,
        }

    def cleanup_task_manager(self):
        """清理任务管理器"""
        if self._task_manager:
            self._task_manager.stop()
            logger.info("TaskManager stopped and cleaned up")
