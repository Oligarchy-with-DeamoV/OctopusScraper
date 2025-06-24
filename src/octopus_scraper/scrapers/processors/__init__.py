from octopus_scraper.scrapers.processors.html_content_processor import (
    HTMLContentProcessor,
)
from octopus_scraper.scrapers.processors.llm_processor import LLMProcessor

AVALIABLE_PROCESSOR = {"llm": LLMProcessor, "html_content": HTMLContentProcessor}
