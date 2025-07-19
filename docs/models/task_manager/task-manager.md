# TaskManager 模型文档

## 概述

TaskManager 是 OctopusScraper 的现代化任务管理系统，提供异步任务队列、优先级调度、并发控制和任务监控功能。

## 核心类

### TaskManager

位置: `src/octopus_scraper/task_manager/task_manager.py`

#### 主要功能
- **任务队列**: 基于优先级的异步任务队列
- **并发控制**: 可配置的最大并发任务数
- **任务监控**: 实时任务状态跟踪和统计
- **结果管理**: 任务结果存储和检索
- **错误处理**: 任务失败处理和重试机制

#### 核心方法

```python
class TaskManager:
    def __init__(self, max_concurrent_tasks: int = 5, max_queue_size: int = 1000)

    async def start(self) -> None
    async def stop(self) -> None

    async def submit_task(self, task: Task, priority: TaskPriority = TaskPriority.NORMAL) -> str
    async def cancel_task(self, task_id: str) -> bool

    def get_task_status(self, task_id: str) -> Optional[TaskStatus]
    def get_statistics(self) -> TaskStatistics
    def list_tasks(self, status: Optional[TaskStatus] = None, limit: int = 50) -> List[TaskInfo]
```

#### 任务统计

```python
@dataclass
class TaskStatistics:
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    pending_tasks: int
    active_tasks: int
    queue_size: int
    workers_count: int
    uptime_seconds: float
    tasks_per_minute: float
    average_task_duration: float
    success_rate: float
```

### Task 数据模型

位置: `src/octopus_scraper/task_manager/models.py`

#### Task 基类

```python
@dataclass
class Task:
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_type: str = "generic"
    created_at: datetime = field(default_factory=datetime.now)
    timeout_seconds: int = 300
    max_retries: int = 3
    metadata: Dict[str, Any] = field(default_factory=dict)

    async def execute(self) -> TaskResult:
        """子类需要实现的执行方法"""
        raise NotImplementedError
```

#### TaskResult

```python
@dataclass
class TaskResult:
    task_id: str
    status: TaskStatus
    result_data: Any = None
    error_message: str = ""
    execution_time: float = 0.0
    retry_count: int = 0
    completed_at: datetime = field(default_factory=datetime.now)
```

#### TaskStatus 枚举

```python
class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
```

#### TaskPriority 枚举

```python
class TaskPriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4
```

### TaskScheduler

位置: `src/octopus_scraper/task_manager/scheduler.py`

#### 功能
基于 Cron 表达式的定时任务调度器。

```python
class TaskScheduler:
    def __init__(self, task_manager: TaskManager)

    async def start(self) -> None
    async def stop(self) -> None

    def add_schedule(self, schedule: ScheduleConfig) -> None
    def remove_schedule(self, schedule_id: str) -> bool
    def get_schedules(self) -> List[ScheduleConfig]
```

#### ScheduleConfig

```python
@dataclass
class ScheduleConfig:
    schedule_id: str
    scraper_name: str
    cron_expression: str
    enabled: bool = True
    priority: TaskPriority = TaskPriority.NORMAL
    timeout_seconds: int = 300
    max_concurrent_runs: int = 1
    max_retries: int = 2
    fetch_params: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
```

## 任务类型

### ScraperTask

抓取任务实现，用于执行网页内容抓取。

```python
class ScraperTask(Task):
    def __init__(self, scraper_config: ScraperConfig, fetch_params: Dict[str, Any]):
        super().__init__(task_type="scraper")
        self.scraper_config = scraper_config
        self.fetch_params = fetch_params

    async def execute(self) -> TaskResult:
        # 执行抓取逻辑
        pass
```

### UploadTask

上传任务实现，用于将内容上传到 Notion。

```python
class UploadTask(Task):
    def __init__(self, contents: List[Content], notion_config: NotionConfig):
        super().__init__(task_type="upload")
        self.contents = contents
        self.notion_config = notion_config

    async def execute(self) -> TaskResult:
        # 执行上传逻辑
        pass
```

## 使用示例

### 基本用法

```python
from octopus_scraper.task_manager import TaskManager, TaskPriority
from octopus_scraper.task_manager.models import Task

# 创建任务管理器
task_manager = TaskManager(max_concurrent_tasks=8, max_queue_size=1000)
await task_manager.start()

# 提交任务
class MyTask(Task):
    async def execute(self):
        # 执行任务逻辑
        return TaskResult(task_id=self.task_id, status=TaskStatus.COMPLETED)

task = MyTask()
task_id = await task_manager.submit_task(task, priority=TaskPriority.HIGH)

# 查询任务状态
status = task_manager.get_task_status(task_id)
print(f"任务状态: {status}")

# 获取统计信息
stats = task_manager.get_statistics()
print(f"总任务数: {stats.total_tasks}")
print(f"成功率: {stats.success_rate:.2%}")
```

### 调度器使用

```python
from octopus_scraper.task_manager import TaskScheduler, ScheduleConfig

# 创建调度器
scheduler = TaskScheduler(task_manager)
await scheduler.start()

# 添加定时任务
schedule = ScheduleConfig(
    schedule_id="daily_news",
    scraper_name="news_scraper",
    cron_expression="0 8 * * *",  # 每天上午8点
    enabled=True,
    priority=TaskPriority.HIGH,
    timeout_seconds=600,
    fetch_params={"limit": 50}
)

scheduler.add_schedule(schedule)
```

### 任务监控

```python
# 获取任务列表
pending_tasks = task_manager.list_tasks(status=TaskStatus.PENDING, limit=10)
for task_info in pending_tasks:
    print(f"任务 {task_info.task_id}: {task_info.task_type}")

# 获取详细统计
stats = task_manager.get_statistics()
print(f"""
任务统计:
- 总任务数: {stats.total_tasks}
- 已完成: {stats.completed_tasks}
- 失败任务: {stats.failed_tasks}
- 等待中: {stats.pending_tasks}
- 执行中: {stats.active_tasks}
- 队列大小: {stats.queue_size}
- 成功率: {stats.success_rate:.2%}
- 平均执行时间: {stats.average_task_duration:.2f}秒
""")
```

## 配置示例

### 任务管理器配置

```yaml
# config.yml
use_task_manager: true

task_manager_config:
  max_concurrent_tasks: 8
  max_queue_size: 1000
  result_retention_hours: 48
  enable_monitoring: true
  log_level: "INFO"
```

### 调度器配置

```yaml
scheduler_config:
  enabled: true
  schedules:
    - schedule_id: "daily_vscode_issues"
      scraper_name: "vscode_issues"
      cron_expression: "0 8 * * *"
      enabled: true
      priority: "high"
      timeout_seconds: 600
      max_concurrent_runs: 1
      max_retries: 2
      fetch_params:
        limit: 50
      metadata:
        source: "github"
        category: "issues"
```

## 性能特性

### 并发控制

- **异步执行**: 基于 asyncio 的异步任务执行
- **工作线程池**: 可配置的并发任务数量
- **队列管理**: 基于优先级的任务队列
- **背压控制**: 队列满时的背压处理

### 内存管理

- **结果清理**: 自动清理过期的任务结果
- **内存监控**: 监控任务执行的内存使用
- **垃圾回收**: 定期清理无用对象

### 错误处理

- **重试机制**: 可配置的任务重试
- **超时处理**: 任务执行超时控制
- **错误隔离**: 单个任务失败不影响其他任务
- **故障转移**: 任务失败时的备用策略

## 扩展性

### 自定义任务类型

```python
class CustomTask(Task):
    def __init__(self, custom_param: str):
        super().__init__(task_type="custom")
        self.custom_param = custom_param

    async def execute(self) -> TaskResult:
        # 自定义任务逻辑
        result = await self.custom_logic()
        return TaskResult(
            task_id=self.task_id,
            status=TaskStatus.COMPLETED,
            result_data=result
        )

    async def custom_logic(self):
        # 实现自定义逻辑
        pass
```

### 任务插件

```python
class TaskPlugin:
    async def before_execute(self, task: Task) -> None:
        """任务执行前的钩子"""
        pass

    async def after_execute(self, task: Task, result: TaskResult) -> None:
        """任务执行后的钩子"""
        pass

# 注册插件
task_manager.register_plugin(TaskPlugin())
```

## 监控和日志

### 日志配置

```python
import logging

# 启用任务管理器日志
logging.getLogger('octopus_scraper.task_manager').setLevel(logging.INFO)

# 启用详细调试日志
logging.getLogger('octopus_scraper.task_manager').setLevel(logging.DEBUG)
```

### 指标收集

```python
# 自定义指标收集
class MetricsCollector:
    def __init__(self, task_manager: TaskManager):
        self.task_manager = task_manager

    def collect_metrics(self) -> Dict[str, Any]:
        stats = self.task_manager.get_statistics()
        return {
            "task_queue_size": stats.queue_size,
            "active_tasks": stats.active_tasks,
            "success_rate": stats.success_rate,
            "average_duration": stats.average_task_duration
        }
```

## 最佳实践

1. **资源管理**: 合理设置并发任务数量
2. **任务分解**: 将大任务分解为小任务
3. **错误处理**: 实现适当的重试和错误恢复
4. **监控**: 监控任务执行状态和性能指标
5. **清理**: 定期清理过期的任务结果
6. **测试**: 充分测试任务执行逻辑

## 相关文档

- [TaskManager Testing](./task-manager-testing.md)
- [Admin Interface](../../interface/web_service/admin-interface.md)
- [ConfigManager Models](../config/config-manager.md)
- [Service Models](../service/service-models.md)
