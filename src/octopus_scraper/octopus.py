import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

import structlog
from dacite import from_dict

from octopus_scraper.scrapers.scraper import BaseScraperConfig, Content, Scraper
from octopus_scraper.scrapers.utils.notion_api import NotionAPIConfig, NotionStorage
from octopus_scraper.task_manager import (
    ScraperTask,
    TaskBatch,
    TaskManager,
    TaskScheduler,
)

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
    enable_scheduler: bool = False  # 是否启用定时任务调度器
    scheduler_config: Optional[Dict[str, Any]] = None  # 调度器配置
    auto_start_scheduler: bool = False  # 是否自动启动调度器


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

        # Initialize task scheduler if enabled
        if self._config.enable_scheduler:
            self._task_scheduler = TaskScheduler(self._task_manager)
            if self._config.auto_start_scheduler:
                self._task_scheduler.start()
                logger.info("TaskScheduler started automatically")
        else:
            self._task_scheduler = None

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
        """清理任务管理器和调度器"""
        if self._task_scheduler:
            self._task_scheduler.stop()
            logger.info("TaskScheduler stopped and cleaned up")

        if self._task_manager:
            self._task_manager.stop()
            logger.info("TaskManager stopped and cleaned up")

    # Scheduler Management Methods

    def get_task_scheduler(self) -> Optional[TaskScheduler]:
        """获取任务调度器实例"""
        return self._task_scheduler

    def start_scheduler(self) -> bool:
        """启动任务调度器"""
        if not self._task_scheduler:
            logger.warning("TaskScheduler not enabled in configuration")
            return False

        self._task_scheduler.start()
        logger.info("TaskScheduler started")
        return True

    def stop_scheduler(self) -> bool:
        """停止任务调度器"""
        if not self._task_scheduler:
            return False

        self._task_scheduler.stop()
        logger.info("TaskScheduler stopped")
        return True

    def add_schedule(self, schedule_config) -> Optional[str]:
        """添加定时任务调度

        Args:
            schedule_config: TaskScheduleConfig 实例

        Returns:
            调度ID，如果调度器未启用则返回 None
        """
        if not self._task_scheduler:
            logger.error(
                "TaskScheduler not enabled. Set enable_scheduler=True in config"
            )
            return None

        try:
            schedule_id = self._task_scheduler.add_schedule(schedule_config)
            logger.info(
                "Schedule added successfully",
                schedule_id=schedule_id,
                scraper_name=schedule_config.scraper_name,
                cron_expression=schedule_config.cron_expression,
            )
            return schedule_id
        except Exception as e:
            logger.error("Failed to add schedule", error=str(e), exc_info=True)
            return None

    def remove_schedule(self, schedule_id: str) -> bool:
        """移除定时任务调度"""
        if not self._task_scheduler:
            return False

        return self._task_scheduler.remove_schedule(schedule_id)

    def enable_schedule(self, schedule_id: str) -> bool:
        """启用特定的调度任务"""
        if not self._task_scheduler:
            return False

        return self._task_scheduler.enable_schedule(schedule_id)

    def disable_schedule(self, schedule_id: str) -> bool:
        """禁用特定的调度任务"""
        if not self._task_scheduler:
            return False

        return self._task_scheduler.disable_schedule(schedule_id)

    def list_schedules(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        """列出所有调度任务"""
        if not self._task_scheduler:
            return []

        schedules = self._task_scheduler.list_schedules(enabled_only=enabled_only)
        return [
            {
                "schedule_id": schedule.schedule_id,
                "scraper_name": schedule.scraper_name,
                "cron_expression": schedule.cron_expression,
                "enabled": schedule.enabled,
                "next_run": (
                    schedule.next_run.isoformat() if schedule.next_run else None
                ),
                "last_run": (
                    schedule.last_run.isoformat() if schedule.last_run else None
                ),
                "max_concurrent_runs": schedule.max_concurrent_runs,
                "timeout_seconds": schedule.timeout_seconds,
                "metadata": schedule.metadata,
            }
            for schedule in schedules
        ]

    def get_schedule(self, schedule_id: str) -> Optional[Dict[str, Any]]:
        """获取特定的调度任务信息"""
        if not self._task_scheduler:
            return None

        schedule = self._task_scheduler.get_schedule(schedule_id)
        if not schedule:
            return None

        return {
            "schedule_id": schedule.schedule_id,
            "scraper_name": schedule.scraper_name,
            "cron_expression": schedule.cron_expression,
            "enabled": schedule.enabled,
            "next_run": schedule.next_run.isoformat() if schedule.next_run else None,
            "last_run": schedule.last_run.isoformat() if schedule.last_run else None,
            "max_concurrent_runs": schedule.max_concurrent_runs,
            "timeout_seconds": schedule.timeout_seconds,
            "metadata": schedule.metadata,
            "fetch_params": schedule.fetch_params,
        }

    def trigger_schedule_now(self, schedule_id: str) -> Optional[str]:
        """立即触发特定的调度任务"""
        if not self._task_scheduler:
            return None

        return self._task_scheduler.trigger_schedule_now(schedule_id)

    def get_scheduler_status(self) -> Dict[str, Any]:
        """获取调度器状态和统计信息"""
        if not self._task_scheduler:
            return {
                "enabled": False,
                "status": "disabled",
                "message": "TaskScheduler not enabled in configuration",
            }

        status = self._task_scheduler.get_scheduler_status()
        return {"enabled": True, **status}

    def add_scraper_schedule(
        self,
        schedule_id: str,
        scraper_name: str,
        cron_expression: str,
        fetch_params: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Optional[str]:
        """为现有的 scraper 配置添加调度任务

        这是一个便利方法，自动根据现有的 scraper 配置创建调度任务
        """
        if not self._task_scheduler:
            logger.error("TaskScheduler not enabled")
            return None

        # 查找对应的 scraper 配置
        scraper_config = None
        scraper_fetch_params = None

        for scraper, params in self._scrapers:
            # 通过 fetcher_name 或其他标识符匹配
            if (
                getattr(scraper.config, "fetcher_name", None) == scraper_name
                or getattr(scraper.config, "name", None) == scraper_name
            ):
                scraper_config = {
                    "name": scraper_name,
                    "fetcher_name": scraper.config.fetcher_name,
                    "fetcher_config": scraper.config.fetcher_config,
                    "content_processor_configs": scraper.config.content_processor_configs,
                }
                scraper_fetch_params = fetch_params or params
                break

        if not scraper_config:
            logger.error(f"Scraper '{scraper_name}' not found in configured scrapers")
            return None

        # 创建调度配置
        from octopus_scraper.task_manager.models import TaskScheduleConfig

        schedule_config = TaskScheduleConfig(
            schedule_id=schedule_id,
            scraper_name=scraper_name,
            cron_expression=cron_expression,
            fetch_params=scraper_fetch_params,
            metadata={"scraper_config": scraper_config},
            **kwargs,
        )

        return self.add_schedule(schedule_config)
