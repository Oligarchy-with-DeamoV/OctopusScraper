from octopus_scraper.processors.html_content_processor import HTMLContentProcessor
from octopus_scraper.processors.llm_processor import LLMProcessor

AVALIABLE_PROCESSOR = {"llm": LLMProcessor, "html_content": HTMLContentProcessor}
