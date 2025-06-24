from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class ProcessorConfig:
    priority: int = field(default=100)  # 默认优先级为100，数值越小优先级越高


@dataclass
class LLMProcessorConfig(ProcessorConfig):
    prompt: str = field(default="")  # 设置默认值避免dataclass错误
    if_structure_output: bool = field(default=False)
    json_schema: Optional[Dict] = field(default=None)
