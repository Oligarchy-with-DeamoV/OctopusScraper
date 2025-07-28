# TaskManager 模型文档

## 📢 重要架构更新

从最新版本开始，OctopusScraper 采用统一的任务管理架构，**TaskManager 已成为默认且唯一的任务执行方式**。

### 🔄 主要变化

#### 1. 统一任务执行

- ✅ **TaskManager 默认启用**: 所有抓取操作都通过 TaskManager 执行
- ❌ **移除传统方式**: 不再支持传统的直接抓取方式
- � **无需配置**: 无需手动设置 `use_task_manager=true`

#### 2. 简化配置

**之前的配置:**

```yaml
use_task_manager: true # 需要手动启用
task_manager_config:
  max_concurrent_tasks: 8
```

**现在的配置:**

```yaml
# TaskManager 默认启用，直接配置参数即可
task_manager_config:
  max_concurrent_tasks: 8
  max_queue_size: 1000
  result_retention_hours: 48
```

#### 3. 环境变量更新

**之前:**

```env
USE_TASK_MANAGER=true           # 不再需要
TASK_MANAGER_MAX_CONCURRENT=8   # 已更名
TASK_MANAGER_MAX_QUEUE_SIZE=1000 # 已更名
```

**现在:**

```env
MAX_CONCURRENT_TASKS=8          # 新变量名
MAX_QUEUE_SIZE=1000            # 新变量名
RESULT_RETENTION_HOURS=48      # 新增配置
```

### ⚠️ 迁移指南

#### 如果你使用的是配置文件

1. **移除** `use_task_manager: true` 配置项
2. **保留** `task_manager_config` 配置块
3. **可选** 添加 `result_retention_hours` 配置

#### 如果你使用的是环境变量

1. **移除** `USE_TASK_MANAGER=true`
2. **重命名** 环境变量：
   - `TASK_MANAGER_MAX_CONCURRENT` → `MAX_CONCURRENT_TASKS`
   - `TASK_MANAGER_MAX_QUEUE_SIZE` → `MAX_QUEUE_SIZE`
3. **可选** 添加 `RESULT_RETENTION_HOURS=48`

#### 如果你有自定义代码

- 移除任何 `use_task_manager` 相关的条件判断
- TaskManager 现在总是可用，无需检查
- 所有任务相关的 API 保持不变

### 🎯 优势

1. **统一架构**: 所有任务都通过同一套系统管理
2. **更好的性能**: 优化的并发控制和资源管理
3. **实时监控**: 完整的任务状态跟踪和统计
4. **简化配置**: 减少配置复杂度，提高易用性
5. **更好的错误处理**: 统一的重试和错误恢复机制

## 概述

TaskManager 是 OctopusScraper 的统一任务执行引擎，现已成为默认且唯一的任务管理方式。它为所有抓取操作提供异步任务队列、优先级调度、并发控制和监控功能。

## 核心架构

### 统一任务执行

TaskManager 现已集成到 OctopusScraper 的核心架构中：

```
用户请求 → OctopusService → Octopus → TaskManager → 具体抓取器
                                      ↓
                              任务调度、监控、重试
```

### TaskManager

位置: `src/octopus_scraper/task_manager/task_manager.py`

#### 主要功能

- **统一执行引擎**: 所有抓取任务的唯一执行方式
- **优先级队列**: 基于优先级的任务调度系统
- **并发控制**: 可配置的最大并发任务数和队列容量
- **实时监控**: 任务状态跟踪和性能指标统计
- **结果管理**: 任务结果存储、检索和保留策略
- **智能重试**: 指数退避的错误恢复机制

#### 配置方式

TaskManager 现已默认启用，可通过以下方式配置：

**环境变量配置:**

```bash
MAX_CONCURRENT_TASKS=8        # 最大并发任务数
MAX_QUEUE_SIZE=1000          # 队列最大容量
RESULT_RETENTION_HOURS=48    # 结果保留时间
```

**配置文件配置:**

```yaml
task_manager_config:
  max_concurrent_tasks: 8
  max_queue_size: 1000
  result_retention_hours: 48
```

#### 核心方法

```python
class TaskManager:
    def __init__(self, max_concurrent_tasks: int = 8, max_queue_size: int = 1000)

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

## 系统集成

### 与 Octopus 核心集成

TaskManager 已完全集成到 Octopus 核心类中，所有抓取操作都将自动通过 TaskManager 执行：

```python
# Octopus 类自动使用 TaskManager
from octopus_scraper import Octopus

octopus = Octopus(config_path="config.yml")
# TaskManager 已自动初始化和启动

# 所有抓取操作都通过 TaskManager 执行
contents = await octopus.trigger_scraper()
```

### 与 OctopusService Web 服务集成

TaskManager 配置通过环境变量自动读取和应用：

```python
# OctopusService 自动配置 TaskManager
from octopus_scraper.octopus_service import create_config_from_env

config, task_manager_config, _ = create_config_from_env()

# TaskManager 配置从环境变量获取
# MAX_CONCURRENT_TASKS → max_concurrent_tasks
# MAX_QUEUE_SIZE → max_queue_size
# RESULT_RETENTION_HOURS → result_retention_hours
```

### 配置自动应用

无需手动配置，TaskManager 会自动从以下源获取配置：

1. **环境变量** (优先级最高)
2. **配置文件** (`config.yml` 中的 `task_manager_config`)
3. **默认值** (如果以上都未设置)

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

## 🚀 使用指南

### 1. CLI 使用

所有 CLI 命令保持不变，TaskManager 在后台自动工作：

```bash
# 标准抓取 - 现在通过 TaskManager 执行
poetry run octopus_go --config config.yml

# Web 服务 - TaskManager 自动启用
poetry run octopus_service
```

### 2. 代码使用

```python
from octopus_scraper import Octopus

# TaskManager 自动启用，无需额外配置
octopus = Octopus(config_path="config.yml")

# 所有操作都通过 TaskManager 执行
contents = await octopus.trigger_scraper()

# 获取任务统计
stats = octopus.get_task_manager_stats()
print(f"活跃任务: {stats.active_tasks}")
```

### 3. 监控和统计

通过新的 API 端点获取任务状态：

```bash
# 获取任务统计
curl http://localhost:8000/tasks/stats

# 获取活跃任务
curl http://localhost:8000/tasks/active

# 提交新任务
curl -X POST http://localhost:8000/tasks/submit \
  -H "Content-Type: application/json" \
  -d '{"name": "test_task", "scraper_name": "example"}'
```

## 使用示例

### 推荐用法 (通过 Octopus)

**最推荐的使用方式是通过 Octopus 类，TaskManager 已自动集成：**

```python
from octopus_scraper import Octopus

# TaskManager 自动启用，无需手动配置
octopus = Octopus(config_path="config.yml")

# 所有抓取操作都通过 TaskManager 执行
contents = await octopus.trigger_scraper()

# 获取任务统计信息
stats = octopus.get_task_manager_stats()
print(f"已完成任务: {stats.completed_tasks}")
print(f"活跃任务: {stats.active_tasks}")
print(f"成功率: {stats.success_rate:.2%}")
```

### 直接使用 TaskManager (高级用法)

如需直接操作 TaskManager，可以这样使用：

```python
from octopus_scraper.task_manager import TaskManager, TaskPriority
from octopus_scraper.task_manager.models import Task

# 创建任务管理器 (通常由 Octopus 自动管理)
task_manager = TaskManager(max_concurrent_tasks=8, max_queue_size=1000)
await task_manager.start()

# 提交自定义任务
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

## 💬 需要帮助？

如果在使用或迁移过程中遇到问题，请：

1. 查看 [GitHub Issues](https://github.com/your-repo/OctopusScraper/issues)
2. 参考 [测试用例](../../../tests/octopus_scraper/) 了解最新用法
3. 查看 [配置示例](../../../config.example.yml) 了解推荐配置

## 📚 相关文档

- [TaskManager Testing](./task-manager-testing.md)
- [Admin Interface](../../interface/web_service/admin-interface.md)
- [ConfigManager Models](../config/config-manager.md)
- [Service Models](../service/service-models.md)
- [主要 README](../../../README.md#任务管理系统)
