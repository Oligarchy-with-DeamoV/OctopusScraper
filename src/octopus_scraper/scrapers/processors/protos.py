from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class ProcessorConfig:
    pass


@dataclass
class LLMProcessorConfig:
    prompt: str
    if_structure_output: bool = False
    json_schema: Optional[Dict] = None
