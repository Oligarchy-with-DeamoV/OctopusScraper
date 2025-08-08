import json
import re
from copy import deepcopy
from typing import Dict, List

import structlog
from dacite import from_dict
from doraemon.gpt_utils.chatgpt_api import request_openai
from jsonschema import validate

from octopus_scraper.processors.processor_base import ProcessorBase
from octopus_scraper.processors.protos import LLMProcessorConfig
from octopus_scraper.utils.rsshub import Content

logger = structlog.getLogger(__name__)

SYSTEM_PROMPT = """
你是一个出色的文案工作者，请根据指令完成以下文章的总结工作。
"""

CONTENT_PROMPT = """
文章标题: {title}
文章链接: {link}
文章内容:
{content}
"""


def extract_markdown_json_code(markdown_text: str):
    pattern = r"```json\s*(.*?)\s*```"
    matches = re.findall(pattern, markdown_text, re.DOTALL)
    code_blocks = [block.strip() for block in matches]
    return code_blocks


class LLMProcessor(ProcessorBase):
    def __init__(self, configs: Dict):
        super().__init__(configs)
        self.output_schema = False
        if self.config.if_structure_output:
            self.output_schema = self.config.json_schema

    def _parse_config(self, config: Dict) -> LLMProcessorConfig:
        """
        解析和验证配置

        Args:
            config: 原始配置字典

        Returns:
            验证过的配置对象
        """
        return from_dict(LLMProcessorConfig, config)

    def _create_single_content_input(self, content: Content) -> List[Dict]:
        mmessages = []
        content_prompt = CONTENT_PROMPT.format(
            title=content.title, link=content.link, content=content.content
        )
        mmessages.append({"role": "system", "content": SYSTEM_PROMPT})
        mmessages.append({"role": "user", "content": content_prompt})
        mmessages.append({"role": "user", "content": self.config.prompt})
        return mmessages

    def _parse_json_output(self, llm_raw_output: str) -> str:
        json_blocks: List[str] = extract_markdown_json_code(llm_raw_output)
        if len(json_blocks) > 1:
            logger.warning("Multi json blocks found, choice first one.")
        return json_blocks[0]

    def process(self, data: Dict) -> Dict:
        """
        处理数据字典，符合ProcessorBase接口

        Args:
            data: 包含contents字段的数据字典

        Returns:
            包含处理后内容的数据字典
        """
        contents = data.get("contents", [])
        if not contents:
            logger.warning("No contents found in data")
            return data

        processed_contents = self(contents)

        result = data.copy()
        result["contents"] = processed_contents

        return result

    def __call__(self, contents: List[Content]) -> List[Content]:
        _output_contents = []
        for c in contents:
            _llm_req = self._create_single_content_input(c)
            success, result = request_openai(_llm_req)
            if not success:
                logger.error(f"LLM request failed with error: {result}")
                _o_c = deepcopy(c)
                _output_contents.append(_o_c)
                continue
            elif self.output_schema:
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
            else:
                _o_c = deepcopy(c)
                _o_c.summary = result
                _output_contents.append(_o_c)
        return _output_contents
