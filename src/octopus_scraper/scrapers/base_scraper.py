from dataclasses import asdict, dataclass
from typing import Dict, List, Literal, Text
import structlog

from dacite import from_dict

from octopus_scraper.scrapers.utils.rsshub import Content, RssHub, RssHubConifg

AVALIABLE_FETCHERS = {"rsshub": RssHub}
AVALIABLE_PROCESSOR = {}

logger = structlog.getLogger(__name__)


@dataclass
class ProccessorConfig:
    pass


@dataclass
class BaseScraperConfig:
    fetcher_name: Literal["rsshub"]
    fecher_config: RssHubConifg
    content_processor_configs: Dict[Text, ProccessorConfig]


class Scraper:
    def __init__(self, config: Dict):
        self.config = from_dict(BaseScraperConfig, config)
        self.activate_fetcher = AVALIABLE_FETCHERS[self.config.fetcher_name](
            asdict(self.config.fecher_config)
        )
        self.active_content_processor = {
            key: AVALIABLE_PROCESSOR[key](asdict(config))
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
