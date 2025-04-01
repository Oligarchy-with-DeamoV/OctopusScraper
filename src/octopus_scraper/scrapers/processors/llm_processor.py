from copy import deepcopy
import json
import re
from typing import Dict, List

from jsonschema import validate

from dacite import from_dict
from doraemon.gpt_utils.chatgpt_api import request_openai
from octopus_scraper.scrapers.processors.protos import LLMProcessorConfig
from octopus_scraper.scrapers.utils.rsshub import Content
import structlog

logger = structlog.getLogger(__name__)

SYSTEM_PROMPT = """
你是一个出色的文案工作者，请根据指令完成以下文章的总结工作。
"""

CONTENT_PROMPT = """
文章标题: {title}
文章链接: {link}
文章内容:
{summary}
"""


def extract_markdown_json_code(markdown_text: str):
    pattern = r"```json\s*(.*?)\s*```"
    matches = re.findall(pattern, markdown_text, re.DOTALL)
    code_blocks = [block.strip() for block in matches]
    return code_blocks


class LLMProcessor:
    def __init__(self, configs: Dict):
        self.configs = from_dict(LLMProcessorConfig, configs)
        self.output_schema = False
        if self.configs.if_structure_output:
            self.output_schema = self.configs.json_schema

    def _create_single_content_input(self, content: Content) -> List[Dict]:
        mmessages = []
        content_prompt = CONTENT_PROMPT.format(
            title=content.title, link=content.link, summary=content.summary
        )
        mmessages.append({"role": "system", "content": SYSTEM_PROMPT})
        mmessages.append({"role": "user", "content": content_prompt})
        mmessages.append({"role": "user", "content": self.configs.prompt})
        return mmessages

    def _parse_json_output(self, llm_raw_output: str) -> str:
        json_blocks: List[str] = extract_markdown_json_code(llm_raw_output)
        if len(json_blocks) > 1:
            logger.warning("Multi json blocks found, choice first one.")
        return json_blocks[0]

    def __call__(self, contents: List[Content]) -> List[Content]:
        _output_contents = []
        for c in contents:
            _llm_req = self._create_single_content_input(c)
            success, result = request_openai(_llm_req)
            if self.output_schema and success:
                try:
                    result = self._parse_json_output(result)
                    result = json.loads(result)
                    validate(result, self.output_schema)
                    _o_c = deepcopy(c)
                    _o_c.summary = json.dumps(result)
                    _output_contents.append(_o_c)
                except Exception as e:
                    logger.error(
                        f"Json output schema check failed with Exception:\n{e}"
                    )
                    continue
        return _output_contents
