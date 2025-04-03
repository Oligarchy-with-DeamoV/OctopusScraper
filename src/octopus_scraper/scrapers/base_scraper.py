from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Literal, Text

from dacite import from_dict
import structlog

from octopus_scraper.scrapers.scraper_protos import Content
from octopus_scraper.scrapers.utils.rsshub import RssHub, RssHubConifg

AVALIABLE_FETCHERS = {"rsshub": RssHub}
AVALIABLE_PROCESSOR = {}

logger = structlog.getLogger(__name__)


@dataclass
class ProccessorConfig:
    pass


@dataclass
class BaseScraperConfig:
    fetcher_name: Literal["rsshub"]
    fecher_config: Any
    content_processor_configs: Dict[Text, Any]


class Scraper:
    def __init__(self, config: Dict):
        self.config = from_dict(BaseScraperConfig, config)
        try:
            self.activate_fetcher = AVALIABLE_FETCHERS[self.config.fetcher_name](
                self.config.fecher_config
            )
        except Exception as e:
            logger.error(
                f"Activate_fetcher init failed with exception: {e}.",
                config=self.config,
            )
        self.active_content_processor = {
            key: AVALIABLE_PROCESSOR[key](config)
            for key, config in self.config.content_processor_configs.items()
        }

    def _content_process(self, contents: List[Content]) -> List[Content]:
        for key, _processor in self.active_content_processor.items():
            logger.debug(f"Proccess content with proccessor: {key}")
            contents = _processor(contents)
        return contents

    def scrap_contents(self, params) -> List[Content]:
        """抓取配置的信息源中 update_time 之后的文章，并进行信息总结
        return:
            contents: List[Content]
        """
        contents = self.activate_fetcher.fetch_contents(params)
        return self._content_process(contents)
