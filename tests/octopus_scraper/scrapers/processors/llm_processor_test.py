from typing import Dict

from dacite import from_dict
import pytest
from unittest import mock
from unittest.mock import MagicMock

from octopus_scraper.scrapers.processors.llm_processor import (
    Content,
    LLMProcessor,
)
from octopus_scraper.scrapers.processors.llm_processor import (
    extract_markdown_json_code,
)

mock_json_schema = {"type": "object", "properties": {"summary": {"type": "string"}}}
mock_llm_response = """
```json
{
    "summary": "This is a processed summary."
}
```
"""


def test_extract_markdown_json_code():
    markdown_json_code = """```json
{
    'test': 1
}
```
"""
    input_message = f"""
upper nonce
{markdown_json_code}
lower nonce
"""
    result = extract_markdown_json_code(input_message)
    assert result == ["{\n    'test': 1\n}"]


@pytest.fixture
def sample_content():
    return Content(
        title="Test Article",
        content_id="content-id",
        link="http://example.com",
        summary="This is the article summary.",
        content="This is the article content.",
    )


@pytest.fixture
def llm_processor_config() -> Dict:
    config = {
        "prompt": "prompt_here",
        "if_structure_output": True,
        "json_schema": mock_json_schema,
    }
    return config


@pytest.fixture
def llm_processor(llm_processor_config):
    return LLMProcessor(llm_processor_config)


class TestLLMProcessor:
    def test_create_single_content_input(self, llm_processor):
        content_data = {
            "title": "name",
            "link": "url",
            "summary": "summary",
            "content": "content",
            "content_id": "content_id",
        }
        content = from_dict(Content, content_data)
        input_content = llm_processor._create_single_content_input(content)
        assert len(input_content) == 3
        assert input_content[-1] == {"content": "prompt_here", "role": "user"}

    def test_parse_json_output(self, llm_processor):
        markdown_json_code_01 = """```json
{
    'test': 1
}
```
"""
        markdown_json_code_02 = """```json
{
    'test': 2
}
```
"""
        input_message = f"""
upper nonce
{markdown_json_code_01}
lower nonce
"""
        codes = llm_processor._parse_json_output(input_message)
        assert codes == "{\n    'test': 1\n}"

        input_message = f"""
upper nonce
{markdown_json_code_01}
middle nonce
{markdown_json_code_02}
lower nonce
"""
        codes = llm_processor._parse_json_output(input_message)
        assert codes == "{\n    'test': 1\n}"

    @mock.patch("octopus_scraper.scrapers.processors.llm_processor.request_openai")
    def test_main_func(self, mock_request_openai, llm_processor, sample_content):
        mock_request_openai.return_value = (True, mock_llm_response)
        processed_contents = llm_processor([sample_content])
        mock_request_openai.assert_called_once()

        assert len(processed_contents) == 1
        assert processed_contents[0].title == "Test Article"
        assert processed_contents[0].link == "http://example.com"
        assert (
            processed_contents[0].summary
            == '{"summary": "This is a processed summary."}'
        )
