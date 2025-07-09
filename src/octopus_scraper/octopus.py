from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Tuple

import structlog
from dacite import from_dict

from octopus_scraper.scrapers.scraper import BaseScraperConfig, Content, Scraper
from octopus_scraper.scrapers.utils.notion_api import NotionAPIConfig, NotionStorage

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


class Octopus:
    def __init__(self, config: Dict):
        self._config = from_dict(OctopusConfig, config)
        self._scrapers: List[Tuple[Scraper, Dict]] = []
        self._fetched_contents: List[Content] = []
        self._notion_api: NotionStorage = NotionStorage(
            asdict(self._config.notion_api_config)
        )

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
        """触发一次 Scraper - 并发执行"""
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
