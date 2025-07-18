from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Tuple, Optional
import time

import structlog
from dacite import from_dict

from octopus_scraper.scrapers.scraper import BaseScraperConfig, Content, Scraper
from octopus_scraper.scrapers.utils.notion_api import NotionAPIConfig, NotionStorage
from octopus_scraper.task_manager import TaskManager, ScraperTask, TaskBatch

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
    use_task_manager: bool = False  # 是否使用新的任务管理器
    task_manager_config: Optional[Dict[str, Any]] = None  # 任务管理器配置


class Octopus:
    def __init__(self, config: Dict):
        self._config = from_dict(OctopusConfig, config)
        self._scrapers: List[Tuple[Scraper, Dict]] = []
        self._fetched_contents: List[Content] = []
        self._notion_api: NotionStorage = NotionStorage(
            asdict(self._config.notion_api_config)
        )

        # Initialize task manager if enabled
        self._task_manager: Optional[TaskManager] = None
        if self._config.use_task_manager:
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
        """触发一次 Scraper - 支持新旧两种执行方式"""
        if self._config.use_task_manager and self._task_manager:
            return self._trigger_scraper_with_task_manager()
        else:
            return self._trigger_scraper_legacy()

    def _trigger_scraper_with_task_manager(self) -> str:
        """使用任务管理器触发抓取"""
        logger.info("Using TaskManager for scraper execution")

        # 创建任务批次
        tasks = []
        for scraper, params in self._scrapers:
            # 从 scraper 配置中提取信息
            scraper_config = {
                "name": getattr(scraper.config, "fetcher_name", "unknown"),
                "fetcher_name": scraper.config.fetcher_name,
                "fetcher_config": scraper.config.fetcher_config,
                "content_processor_configs": scraper.config.content_processor_configs,
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

    def _trigger_scraper_legacy(self):
        """传统的并发执行方式"""
        max_workers = getattr(self._config, "max_concurrent_scrapers", 5)

        def scrape_single(scraper_params_tuple):
            """单个scraper的抓取任务"""
            scraper, params = scraper_params_tuple
            try:
                contents = scraper.scrap_contents(params)
                logger.info(f"Scraper completed, fetched {len(contents)} contents")
                return contents
            except Exception as e:
                logger.error(f"Scraper failed: {e}", scraper=scraper, params=params)
                return []  # 返回空列表，避免中断其他scraper

        # 使用线程池并发执行所有scraper
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有scraper任务
            future_to_scraper = {
                executor.submit(scrape_single, scraper_params): scraper_params[0]
                for scraper_params in self._scrapers
            }

            # 收集所有结果
            for future in as_completed(future_to_scraper):
                try:
                    contents = future.result()
                    self._fetched_contents.extend(contents)
                except Exception as e:
                    scraper = future_to_scraper[future]
                    logger.error(f"Scraper execution failed: {e}", scraper=scraper)

    def trigger_upload(self) -> int:
        """将获取的 Content 批量上传, 返回成功数量"""
        try:
            success_cnt = sum(
                self._notion_api.store_contents_with_dedup(self._fetched_contents)
            )
            self._fetched_contents.clear()  # 清空已上传的内容
            return success_cnt

        except Exception as e:
            logger.error(
                "Failed to upload contents to Notion.",
                error=str(e),
                fetched_contents=self._fetched_contents,
            )
            raise RuntimeError(f"Failed to upload contents to Notion: {e}")

    # Task Management Methods (when using TaskManager)

    def get_task_manager(self) -> Optional[TaskManager]:
        """获取任务管理器实例"""
        return self._task_manager

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        if not self._task_manager:
            return None

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
        if not self._task_manager:
            return []

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
        if not self._task_manager:
            return False
        return self._task_manager.cancel_task(task_id)

    def get_task_manager_statistics(self) -> Dict[str, Any]:
        """获取任务管理器统计信息"""
        if not self._task_manager:
            return {"error": "TaskManager not enabled"}
        return self._task_manager.get_statistics()

    def submit_individual_scraper_task(
        self,
        scraper_name: str,
        scraper_config: Dict[str, Any],
        fetch_params: Dict[str, Any],
    ) -> Optional[str]:
        """提交单个抓取任务"""
        if not self._task_manager:
            logger.warning("TaskManager not enabled, cannot submit individual task")
            return None

        task = ScraperTask.from_scraper_config(scraper_config, fetch_params)
        task.scraper_name = scraper_name

        return self._task_manager.submit_task(task)

    def wait_for_batch_completion(
        self, batch_id: str, timeout_seconds: int = 300
    ) -> Dict[str, Any]:
        """等待批次任务完成"""
        if not self._task_manager:
            return {"error": "TaskManager not enabled"}

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
