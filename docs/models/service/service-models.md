# Service Models 文档

## 概述

Service Models 是 OctopusScraper 的数据模型层，定义了系统中各种数据结构、API 响应格式、以及服务间通信的标准接口。这些模型确保了数据的一致性和类型安全。

## 模块结构

```
src/octopus_scraper/service_models.py
├── BaseModel           # 基础数据模型
├── ScrapingItem        # 抓取项目模型
├── ScrapingResult      # 抓取结果模型
├── TaskModel           # 任务模型
├── TaskResult          # 任务结果模型
├── ScheduleModel       # 调度任务模型
├── SchedulerStatus     # 调度器状态模型
├── AdminResponse       # 管理接口响应模型
├── ErrorResponse       # 错误响应模型
└── SystemInfo          # 系统信息模型
```

## 核心数据模型

### 1. BaseModel (基础模型)

```python
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from datetime import datetime
import json

@dataclass
class BaseModel:
    """所有数据模型的基类"""

    created_at: datetime = field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = {}
        for key, value in self.__dict__.items():
            if isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, BaseModel):
                result[key] = value.to_dict()
            elif isinstance(value, list):
                result[key] = [
                    item.to_dict() if isinstance(item, BaseModel) else item
                    for item in value
                ]
            else:
                result[key] = value
        return result

    def to_json(self) -> str:
        """转换为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        """从字典创建实例"""
        # 实现从字典反序列化的逻辑
        pass

    def update_timestamp(self):
        """更新时间戳"""
        self.updated_at = datetime.now()
```

### 2. ScrapingItem (抓取项目模型)

```python
from typing import List, Optional
from datetime import datetime

@dataclass
class ScrapingItem(BaseModel):
    """单个抓取项目的数据模型"""

    # 基本信息
    title: str
    url: str
    content: Optional[str] = None
    summary: Optional[str] = None

    # 作者和发布信息
    author: Optional[str] = None
    published_date: Optional[datetime] = None

    # 分类和标签
    category: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    # 内容相关
    content_type: str = "article"  # article, video, podcast, etc.
    language: Optional[str] = None
    word_count: Optional[int] = None

    # 社交指标
    likes_count: Optional[int] = None
    shares_count: Optional[int] = None
    comments_count: Optional[int] = None

    # 技术信息
    source_scraper: Optional[str] = None
    source_feed: Optional[str] = None
    content_hash: Optional[str] = None

    # 处理状态
    processed: bool = False
    processing_errors: List[str] = field(default_factory=list)

    def __post_init__(self):
        """初始化后处理"""
        super().__post_init__()

        # 计算内容哈希
        if self.content and not self.content_hash:
            import hashlib
            self.content_hash = hashlib.md5(
                f"{self.title}|{self.url}".encode()
            ).hexdigest()

        # 估算字数
        if self.content and not self.word_count:
            self.word_count = len(self.content.split())

    def get_display_title(self, max_length: int = 100) -> str:
        """获取显示用的标题（可截断）"""
        if len(self.title) <= max_length:
            return self.title
        return self.title[:max_length - 3] + "..."

    def get_domain(self) -> Optional[str]:
        """从 URL 提取域名"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(self.url)
            return parsed.netloc
        except Exception:
            return None

    def is_recent(self, days: int = 7) -> bool:
        """检查是否为最近的内容"""
        if not self.published_date:
            return False

        from datetime import timedelta
        cutoff_date = datetime.now() - timedelta(days=days)
        return self.published_date > cutoff_date

    def add_processing_error(self, error: str):
        """添加处理错误"""
        self.processing_errors.append(error)
        self.update_timestamp()

    def mark_processed(self):
        """标记为已处理"""
        self.processed = True
        self.update_timestamp()
```

### 3. ScrapingResult (抓取结果模型)

```python
from typing import List
from enum import Enum

class ScrapingStatus(Enum):
    """抓取状态枚举"""
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"

@dataclass
class ScrapingResult(BaseModel):
    """抓取结果数据模型"""

    # 基本信息
    scraper_name: str
    status: ScrapingStatus

    # 结果数据
    items: List[ScrapingItem] = field(default_factory=list)

    # 统计信息
    total_items: int = 0
    new_items: int = 0
    duplicate_items: int = 0
    error_items: int = 0

    # 执行信息
    execution_time: float = 0.0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    # 错误信息
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)

    # 配置信息
    scraper_config: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """初始化后处理"""
        super().__post_init__()

        # 自动计算统计信息
        if self.total_items == 0:
            self.total_items = len(self.items)

        # 计算执行时间
        if self.start_time and self.end_time and self.execution_time == 0.0:
            self.execution_time = (self.end_time - self.start_time).total_seconds()

    @property
    def success(self) -> bool:
        """是否成功"""
        return self.status in [ScrapingStatus.SUCCESS, ScrapingStatus.PARTIAL_SUCCESS]

    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_items == 0:
            return 0.0
        return (self.total_items - self.error_items) / self.total_items

    def add_warning(self, message: str):
        """添加警告"""
        self.warnings.append(message)
        self.update_timestamp()

    def set_error(self, message: str):
        """设置错误"""
        self.status = ScrapingStatus.FAILURE
        self.error_message = message
        self.update_timestamp()

    def get_summary(self) -> Dict[str, Any]:
        """获取结果摘要"""
        return {
            'scraper_name': self.scraper_name,
            'status': self.status.value,
            'success': self.success,
            'total_items': self.total_items,
            'new_items': self.new_items,
            'duplicate_items': self.duplicate_items,
            'error_items': self.error_items,
            'success_rate': self.success_rate,
            'execution_time': self.execution_time,
            'has_errors': bool(self.error_message),
            'warnings_count': len(self.warnings)
        }
```

### 4. TaskModel (任务模型)

```python
from enum import Enum
from typing import Any, Dict, Optional

class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"

class TaskPriority(Enum):
    """任务优先级枚举"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4

@dataclass
class TaskModel(BaseModel):
    """任务数据模型"""

    # 基本信息
    task_id: str
    task_type: str
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL

    # 任务配置
    task_config: Dict[str, Any] = field(default_factory=dict)

    # 执行信息
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    execution_time: float = 0.0

    # 重试信息
    retry_count: int = 0
    max_retries: int = 3
    retry_delay: float = 1.0

    # 关联信息
    scraper_name: Optional[str] = None
    schedule_id: Optional[str] = None
    parent_task_id: Optional[str] = None

    # 结果和错误
    result_data: Any = None
    error_message: Optional[str] = None
    error_traceback: Optional[str] = None

    def __post_init__(self):
        """初始化后处理"""
        super().__post_init__()

        # 生成任务ID（如果未提供）
        if not hasattr(self, 'task_id') or not self.task_id:
            import uuid
            self.task_id = str(uuid.uuid4())

    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self.status == TaskStatus.RUNNING

    @property
    def is_completed(self) -> bool:
        """是否已完成"""
        return self.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]

    @property
    def can_retry(self) -> bool:
        """是否可以重试"""
        return (self.status == TaskStatus.FAILED and
                self.retry_count < self.max_retries)

    def start_execution(self):
        """开始执行"""
        self.status = TaskStatus.RUNNING
        self.start_time = datetime.now()
        self.update_timestamp()

    def complete_execution(self, result_data: Any = None):
        """完成执行"""
        self.status = TaskStatus.COMPLETED
        self.end_time = datetime.now()
        self.result_data = result_data

        if self.start_time:
            self.execution_time = (self.end_time - self.start_time).total_seconds()

        self.update_timestamp()

    def fail_execution(self, error_message: str, error_traceback: str = None):
        """执行失败"""
        self.status = TaskStatus.FAILED
        self.end_time = datetime.now()
        self.error_message = error_message
        self.error_traceback = error_traceback

        if self.start_time:
            self.execution_time = (self.end_time - self.start_time).total_seconds()

        self.update_timestamp()

    def cancel_execution(self, reason: str = None):
        """取消执行"""
        self.status = TaskStatus.CANCELLED
        self.end_time = datetime.now()
        if reason:
            self.error_message = f"Cancelled: {reason}"

        self.update_timestamp()

    def increment_retry(self):
        """增加重试次数"""
        self.retry_count += 1
        self.status = TaskStatus.PENDING
        self.error_message = None
        self.error_traceback = None
        self.update_timestamp()
```

### 5. TaskResult (任务结果模型)

```python
@dataclass
class TaskResult(BaseModel):
    """任务结果数据模型"""

    # 关联信息
    task_id: str
    task_type: str
    status: TaskStatus

    # 结果数据
    result_data: Any = None

    # 执行统计
    execution_time: float = 0.0
    retry_count: int = 0

    # 错误信息
    error_message: Optional[str] = None
    error_code: Optional[str] = None

    # 输出信息
    output_logs: List[str] = field(default_factory=list)
    warning_logs: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """是否成功"""
        return self.status == TaskStatus.COMPLETED

    def add_log(self, message: str, level: str = "info"):
        """添加日志"""
        timestamp = datetime.now().isoformat()
        log_entry = f"[{timestamp}] [{level.upper()}] {message}"

        if level.lower() == "warning":
            self.warning_logs.append(log_entry)
        else:
            self.output_logs.append(log_entry)

        self.update_timestamp()

    def get_summary(self) -> Dict[str, Any]:
        """获取结果摘要"""
        return {
            'task_id': self.task_id,
            'task_type': self.task_type,
            'status': self.status.value,
            'success': self.success,
            'execution_time': self.execution_time,
            'retry_count': self.retry_count,
            'has_error': bool(self.error_message),
            'log_count': len(self.output_logs),
            'warning_count': len(self.warning_logs)
        }
```

## API 响应模型

### 1. AdminResponse (管理接口响应)

```python
from typing import Union, List

@dataclass
class AdminResponse(BaseModel):
    """管理接口统一响应模型"""

    # 响应状态
    success: bool
    message: str = ""

    # 响应数据
    data: Any = None

    # 分页信息
    pagination: Optional[Dict[str, Any]] = None

    # 统计信息
    stats: Optional[Dict[str, Any]] = None

    # 错误信息
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # 请求信息
    request_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)

    @classmethod
    def success_response(cls, data: Any = None, message: str = "Success",
                        stats: Dict[str, Any] = None) -> 'AdminResponse':
        """创建成功响应"""
        return cls(
            success=True,
            message=message,
            data=data,
            stats=stats
        )

    @classmethod
    def error_response(cls, message: str, errors: List[str] = None) -> 'AdminResponse':
        """创建错误响应"""
        return cls(
            success=False,
            message=message,
            errors=errors or []
        )

    def add_error(self, error: str):
        """添加错误"""
        self.errors.append(error)
        if self.success:
            self.success = False
            if not self.message:
                self.message = "Request failed with errors"

    def add_warning(self, warning: str):
        """添加警告"""
        self.warnings.append(warning)
```

### 2. ErrorResponse (错误响应模型)

```python
@dataclass
class ErrorResponse(BaseModel):
    """错误响应数据模型"""

    # 错误基本信息
    error_code: str
    error_message: str
    error_type: str = "general"

    # 错误详情
    details: Dict[str, Any] = field(default_factory=dict)
    suggestions: List[str] = field(default_factory=list)

    # 调试信息
    traceback: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)

    # 请求信息
    request_path: Optional[str] = None
    request_method: Optional[str] = None
    user_agent: Optional[str] = None

    @classmethod
    def from_exception(cls, exc: Exception, context: Dict[str, Any] = None) -> 'ErrorResponse':
        """从异常创建错误响应"""
        import traceback as tb

        return cls(
            error_code=exc.__class__.__name__,
            error_message=str(exc),
            error_type="exception",
            traceback=tb.format_exc(),
            context=context or {}
        )

    def add_suggestion(self, suggestion: str):
        """添加建议"""
        self.suggestions.append(suggestion)
```

### 3. SystemInfo (系统信息模型)

```python
import platform
import psutil
from typing import Dict

@dataclass
class SystemInfo(BaseModel):
    """系统信息数据模型"""

    # 系统基本信息
    platform: str = field(default_factory=lambda: platform.system())
    platform_version: str = field(default_factory=lambda: platform.version())
    python_version: str = field(default_factory=lambda: platform.python_version())

    # 应用信息
    app_version: str = "1.0.0"
    app_name: str = "OctopusScraper"

    # 运行时信息
    uptime: float = 0.0
    startup_time: datetime = field(default_factory=datetime.now)

    # 系统资源
    cpu_count: int = field(default_factory=lambda: psutil.cpu_count())
    memory_total: int = field(default_factory=lambda: psutil.virtual_memory().total)
    memory_available: int = field(default_factory=lambda: psutil.virtual_memory().available)
    disk_usage: Dict[str, int] = field(default_factory=dict)

    # 网络信息
    network_interfaces: List[str] = field(default_factory=list)

    def update_runtime_info(self):
        """更新运行时信息"""
        current_time = datetime.now()
        self.uptime = (current_time - self.startup_time).total_seconds()

        # 更新内存信息
        memory = psutil.virtual_memory()
        self.memory_available = memory.available

        # 更新磁盘使用情况
        disk = psutil.disk_usage('/')
        self.disk_usage = {
            'total': disk.total,
            'used': disk.used,
            'free': disk.free
        }

        self.update_timestamp()

    def get_memory_usage_percentage(self) -> float:
        """获取内存使用百分比"""
        used = self.memory_total - self.memory_available
        return (used / self.memory_total) * 100

    def get_disk_usage_percentage(self) -> float:
        """获取磁盘使用百分比"""
        if not self.disk_usage:
            return 0.0
        return (self.disk_usage['used'] / self.disk_usage['total']) * 100
```

## 统计和聚合模型

### 1. TaskStatistics (任务统计模型)

```python
@dataclass
class TaskStatistics(BaseModel):
    """任务统计数据模型"""

    # 任务数量统计
    total_tasks: int = 0
    pending_tasks: int = 0
    running_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    cancelled_tasks: int = 0

    # 性能统计
    average_execution_time: float = 0.0
    total_execution_time: float = 0.0

    # 成功率统计
    success_rate: float = 0.0

    # 时间范围
    stats_period: str = "all_time"
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    @property
    def active_tasks(self) -> int:
        """活跃任务数"""
        return self.pending_tasks + self.running_tasks

    def calculate_success_rate(self):
        """计算成功率"""
        total_finished = self.completed_tasks + self.failed_tasks + self.cancelled_tasks
        if total_finished == 0:
            self.success_rate = 0.0
        else:
            self.success_rate = (self.completed_tasks / total_finished) * 100

    def update_from_tasks(self, tasks: List[TaskModel]):
        """从任务列表更新统计"""
        self.total_tasks = len(tasks)

        # 重置计数器
        self.pending_tasks = 0
        self.running_tasks = 0
        self.completed_tasks = 0
        self.failed_tasks = 0
        self.cancelled_tasks = 0

        execution_times = []

        for task in tasks:
            # 状态统计
            if task.status == TaskStatus.PENDING:
                self.pending_tasks += 1
            elif task.status == TaskStatus.RUNNING:
                self.running_tasks += 1
            elif task.status == TaskStatus.COMPLETED:
                self.completed_tasks += 1
                if task.execution_time > 0:
                    execution_times.append(task.execution_time)
            elif task.status == TaskStatus.FAILED:
                self.failed_tasks += 1
            elif task.status == TaskStatus.CANCELLED:
                self.cancelled_tasks += 1

        # 性能统计
        if execution_times:
            self.average_execution_time = sum(execution_times) / len(execution_times)
            self.total_execution_time = sum(execution_times)

        # 成功率
        self.calculate_success_rate()

        self.update_timestamp()
```

### 2. ScraperStatistics (抓取器统计模型)

```python
@dataclass
class ScraperStatistics(BaseModel):
    """抓取器统计数据模型"""

    # 抓取器信息
    scraper_name: str
    scraper_type: str

    # 运行统计
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0

    # 数据统计
    total_items_scraped: int = 0
    total_new_items: int = 0
    total_duplicate_items: int = 0

    # 性能统计
    average_execution_time: float = 0.0
    last_execution_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None

    # 错误统计
    error_count: int = 0
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None

    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_runs == 0:
            return 0.0
        return (self.successful_runs / self.total_runs) * 100

    @property
    def average_items_per_run(self) -> float:
        """每次运行平均项目数"""
        if self.successful_runs == 0:
            return 0.0
        return self.total_items_scraped / self.successful_runs

    def update_from_result(self, result: ScrapingResult):
        """从抓取结果更新统计"""
        self.total_runs += 1
        self.last_execution_time = datetime.now()

        if result.success:
            self.successful_runs += 1
            self.last_success_time = self.last_execution_time

            # 更新数据统计
            self.total_items_scraped += result.total_items
            self.total_new_items += result.new_items
            self.total_duplicate_items += result.duplicate_items

        else:
            self.failed_runs += 1
            self.error_count += 1
            self.last_error = result.error_message
            self.last_error_time = self.last_execution_time

        # 更新平均执行时间
        if self.average_execution_time == 0:
            self.average_execution_time = result.execution_time
        else:
            self.average_execution_time = (
                (self.average_execution_time * (self.total_runs - 1) + result.execution_time)
                / self.total_runs
            )

        self.update_timestamp()
```

## 调度器相关模型

### 1. ScheduleModel (调度任务模型)

```python
from enum import Enum
from croniter import croniter
from typing import Optional, Any, Dict

class ScheduleStatus(Enum):
    """调度任务状态枚举"""
    ENABLED = "enabled"
    DISABLED = "disabled"
    PAUSED = "paused"
    ERROR = "error"

@dataclass
class ScheduleModel(BaseModel):
    """调度任务数据模型"""

    # 基本信息
    schedule_id: str
    name: str
    description: Optional[str] = None
    status: ScheduleStatus = ScheduleStatus.ENABLED

    # 调度配置
    cron_expression: str
    timezone: str = "UTC"

    # 关联任务
    scraper_name: str
    task_priority: TaskPriority = TaskPriority.NORMAL
    task_timeout: int = 300  # 秒
    max_retries: int = 3

    # 执行参数
    fetch_params: Dict[str, Any] = field(default_factory=dict)
    task_config: Dict[str, Any] = field(default_factory=dict)

    # 执行统计
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    last_run_time: Optional[datetime] = None
    last_run_status: Optional[str] = None
    next_run_time: Optional[datetime] = None
    average_execution_time: float = 0.0

    # 错误信息
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None

    def __post_init__(self):
        """初始化后处理"""
        super().__post_init__()
        
        # 验证 cron 表达式
        if not self.is_valid_cron():
            raise ValueError(f"Invalid cron expression: {self.cron_expression}")
        
        # 计算下次运行时间
        self.update_next_run_time()

    def is_valid_cron(self) -> bool:
        """验证 cron 表达式是否有效"""
        try:
            croniter(self.cron_expression)
            return True
        except (ValueError, TypeError):
            return False

    def update_next_run_time(self):
        """更新下次运行时间"""
        try:
            cron = croniter(self.cron_expression, datetime.now())
            self.next_run_time = cron.get_next(datetime)
        except Exception as e:
            self.last_error = f"Failed to calculate next run time: {str(e)}"
            self.status = ScheduleStatus.ERROR

    def is_due(self, current_time: datetime = None) -> bool:
        """检查是否到了执行时间"""
        if self.status != ScheduleStatus.ENABLED:
            return False
        
        if not self.next_run_time:
            return False
            
        if current_time is None:
            current_time = datetime.now()
            
        return current_time >= self.next_run_time

    def record_execution(self, success: bool, execution_time: float = 0.0, error: str = None):
        """记录执行结果"""
        self.total_runs += 1
        self.last_run_time = datetime.now()
        
        if success:
            self.successful_runs += 1
            self.last_run_status = "success"
            self.last_error = None
        else:
            self.failed_runs += 1
            self.last_run_status = "failed"
            self.last_error = error
            self.last_error_time = self.last_run_time
        
        # 更新平均执行时间
        if execution_time > 0:
            if self.average_execution_time == 0:
                self.average_execution_time = execution_time
            else:
                self.average_execution_time = (
                    (self.average_execution_time * (self.total_runs - 1) + execution_time)
                    / self.total_runs
                )
        
        # 更新下次运行时间
        self.update_next_run_time()
        self.update_timestamp()

    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_runs == 0:
            return 0.0
        return self.successful_runs / self.total_runs

    def enable(self):
        """启用调度"""
        self.status = ScheduleStatus.ENABLED
        self.update_next_run_time()
        self.update_timestamp()

    def disable(self):
        """禁用调度"""
        self.status = ScheduleStatus.DISABLED
        self.next_run_time = None
        self.update_timestamp()

    def pause(self):
        """暂停调度"""
        self.status = ScheduleStatus.PAUSED
        self.update_timestamp()
```

### 2. SchedulerStatus (调度器状态模型)

```python
@dataclass
class SchedulerStatus(BaseModel):
    """调度器状态数据模型"""

    # 调度器状态
    enabled: bool = False
    running: bool = False
    
    # 调度统计
    total_schedules: int = 0
    enabled_schedules: int = 0
    disabled_schedules: int = 0
    paused_schedules: int = 0
    error_schedules: int = 0
    
    # 运行状态
    running_scheduled_tasks: int = 0
    next_run: Optional[datetime] = None
    last_check_time: Optional[datetime] = None
    
    # 配置信息
    max_concurrent_schedules: int = 10
    schedule_check_interval: int = 60
    auto_start_enabled: bool = False
    
    # 统计信息
    schedules_by_status: Dict[str, int] = field(default_factory=dict)
    
    def update_from_schedules(self, schedules: List[ScheduleModel]):
        """从调度列表更新状态"""
        self.total_schedules = len(schedules)
        
        # 按状态统计
        status_counts = {}
        earliest_next_run = None
        
        for schedule in schedules:
            status = schedule.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
            
            # 查找最早的下次运行时间
            if (schedule.status == ScheduleStatus.ENABLED and 
                schedule.next_run_time and 
                (earliest_next_run is None or schedule.next_run_time < earliest_next_run)):
                earliest_next_run = schedule.next_run_time
        
        self.enabled_schedules = status_counts.get(ScheduleStatus.ENABLED.value, 0)
        self.disabled_schedules = status_counts.get(ScheduleStatus.DISABLED.value, 0)
        self.paused_schedules = status_counts.get(ScheduleStatus.PAUSED.value, 0)
        self.error_schedules = status_counts.get(ScheduleStatus.ERROR.value, 0)
        
        self.schedules_by_status = status_counts
        self.next_run = earliest_next_run
        self.last_check_time = datetime.now()
        
        self.update_timestamp()

    @property
    def health_status(self) -> str:
        """健康状态"""
        if not self.enabled:
            return "disabled"
        elif self.error_schedules > 0:
            return "warning"
        elif self.running:
            return "healthy"
        else:
            return "stopped"
```

## 数据验证和转换

### ValidationMixin

```python
from typing import Any, List, Callable

class ValidationMixin:
    """数据验证混入类"""

    def validate_field(self, field_name: str, value: Any,
                      validators: List[Callable]) -> bool:
        """验证单个字段"""
        for validator in validators:
            if not validator(value):
                return False
        return True

    def validate_required_fields(self, required_fields: List[str]) -> List[str]:
        """验证必需字段"""
        missing_fields = []
        for field in required_fields:
            if not hasattr(self, field) or getattr(self, field) is None:
                missing_fields.append(field)
        return missing_fields

    def validate_url(self, url: str) -> bool:
        """验证 URL 格式"""
        import re
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        return url_pattern.match(url) is not None
```

## 使用示例

### 创建和使用数据模型

```python
from octopus_scraper.service_models import *

# 创建抓取项目
item = ScrapingItem(
    title="VS Code 最新更新",
    url="https://code.visualstudio.com/updates/v1_75",
    content="这是一个关于 VS Code 更新的文章...",
    author="VS Code Team",
    tags=["vscode", "update", "development"],
    source_scraper="vscode_blog"
)

# 创建抓取结果
result = ScrapingResult(
    scraper_name="vscode_blog",
    status=ScrapingStatus.SUCCESS,
    items=[item],
    execution_time=2.5
)

# 转换为字典和 JSON
result_dict = result.to_dict()
result_json = result.to_json()

# 创建 API 响应
response = AdminResponse.success_response(
    data=result.get_summary(),
    message="Scraping completed successfully"
)

# 添加统计信息
stats = TaskStatistics()
stats.update_from_tasks([task1, task2, task3])
response.stats = stats.to_dict()
```

### 错误处理

```python
try:
    # 抓取操作
    result = await scraper.scrape()
except Exception as e:
    # 创建错误响应
    error_response = ErrorResponse.from_exception(
        e,
        context={'scraper_name': scraper.name}
    )
    error_response.add_suggestion("检查网络连接和配置")

    # 返回错误响应
    return AdminResponse.error_response(
        message="Scraping failed",
        errors=[error_response.error_message]
    )
```

### 数据验证

```python
class ValidatedScrapingItem(ScrapingItem, ValidationMixin):
    """带验证的抓取项目"""

    def __post_init__(self):
        super().__post_init__()
        self.validate()

    def validate(self) -> bool:
        """验证数据"""
        # 检查必需字段
        missing = self.validate_required_fields(['title', 'url'])
        if missing:
            raise ValueError(f"Missing required fields: {missing}")

        # 验证 URL
        if not self.validate_url(self.url):
            raise ValueError(f"Invalid URL: {self.url}")

        return True
```

## 序列化和持久化

### 数据库序列化

```python
def to_database_dict(self) -> Dict[str, Any]:
    """转换为数据库存储格式"""
    data = self.to_dict()

    # 处理特殊字段
    if 'tags' in data and isinstance(data['tags'], list):
        data['tags'] = ','.join(data['tags'])

    # 处理日期时间
    for key, value in data.items():
        if isinstance(value, datetime):
            data[key] = value.timestamp()

    return data

@classmethod
def from_database_dict(cls, data: Dict[str, Any]):
    """从数据库格式创建实例"""
    # 恢复标签列表
    if 'tags' in data and isinstance(data['tags'], str):
        data['tags'] = data['tags'].split(',') if data['tags'] else []

    # 恢复日期时间
    for key in ['created_at', 'updated_at', 'published_date']:
        if key in data and isinstance(data[key], (int, float)):
            data[key] = datetime.fromtimestamp(data[key])

    return cls(**data)
```

## 相关文档

- [ConfigManager Models](../config/config-manager.md)
- [TaskManager Models](../task_manager/task-manager.md)
- [Scrapers Models](../scrapers/scrapers.md)
- [Service Models Testing](./service-models-testing.md)
