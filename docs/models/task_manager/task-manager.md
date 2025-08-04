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

## 环境变量配置

### TaskManager 环境变量（默认启用）

| 变量名 | 默认值 | 描述 |
|--------|--------|------|
| `MAX_CONCURRENT_TASKS` | `8` | 最大并发任务数 |
| `MAX_QUEUE_SIZE` | `1000` | 任务队列最大容量 |
| `RESULT_RETENTION_HOURS` | `48` | 任务结果保留时间（小时） |

### 调度器环境变量（可选）

| 变量名 | 默认值 | 描述 |
|--------|--------|------|
| `ENABLE_SCHEDULER` | `false` | 启用/禁用 TaskScheduler 功能 |
| `AUTO_START_SCHEDULER` | `false` | 服务启动时自动启动调度器 |
| `MAX_CONCURRENT_SCHEDULES` | `10` | 最大并发调度任务数 |
| `SCHEDULE_CHECK_INTERVAL` | `60` | 调度检查间隔（秒） |

### 配置示例

#### 基本配置（仅 TaskManager）
```bash
# TaskManager 配置
export MAX_CONCURRENT_TASKS=8
export MAX_QUEUE_SIZE=1000
export RESULT_RETENTION_HOURS=48
```

#### 启用调度器（自动启动）
```bash
# TaskManager 配置
export MAX_CONCURRENT_TASKS=8
export MAX_QUEUE_SIZE=1000
export RESULT_RETENTION_HOURS=48

# 调度器配置
export ENABLE_SCHEDULER=true
export AUTO_START_SCHEDULER=true
export MAX_CONCURRENT_SCHEDULES=10
export SCHEDULE_CHECK_INTERVAL=60
```

#### 启用调度器（手动控制）
```bash
# 启用但不自动启动，通过 API 手动控制
export ENABLE_SCHEDULER=true
export AUTO_START_SCHEDULER=false
export MAX_CONCURRENT_SCHEDULES=5
export SCHEDULE_CHECK_INTERVAL=30
```

#### Docker Compose 配置
```yaml
version: '3.8'
services:
  octopus-service:
    build: .
    environment:
      # Notion 配置
      - NOTION_API_KEY=your_notion_api_key
      - NOTION_SCRAPERS_DATABASE_ID=your_database_id
      - NOTION_CONTENT_DATABASE_ID=your_content_db_id
      
      # TaskManager 配置
      - MAX_CONCURRENT_TASKS=8
      - MAX_QUEUE_SIZE=1000
      - RESULT_RETENTION_HOURS=48
      
      # 调度器配置
      - ENABLE_SCHEDULER=true
      - AUTO_START_SCHEDULER=true
      - MAX_CONCURRENT_SCHEDULES=10
      - SCHEDULE_CHECK_INTERVAL=60
    ports:
      - "8000:8000"
```

#### .env 文件配置
```bash
# .env
# TaskManager 配置（默认启用）
MAX_CONCURRENT_TASKS=8
MAX_QUEUE_SIZE=1000
RESULT_RETENTION_HOURS=48

# 调度器配置（可选）
ENABLE_SCHEDULER=true
AUTO_START_SCHEDULER=false
MAX_CONCURRENT_SCHEDULES=3
SCHEDULE_CHECK_INTERVAL=120

# 其他服务配置
DEBUG=true
LOG_LEVEL=DEBUG
```

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

### TaskScheduler

位置: `src/octopus_scraper/task_manager/scheduler.py`

TaskScheduler 为 TaskManager 提供定时调度功能，支持基于 Cron 表达式的自动任务执行。

#### 主要功能

- **Cron 调度**: 基于标准 Cron 表达式的时间调度
- **环境变量配置**: 支持动态启用/禁用调度器
- **自动启动**: 可配置服务启动时自动启动调度器
- **并发控制**: 独立的调度任务并发控制
- **状态管理**: 完整的调度任务状态跟踪

#### 环境变量配置

```bash
# 调度器基本配置
ENABLE_SCHEDULER=true              # 启用调度器功能
AUTO_START_SCHEDULER=true          # 服务启动时自动启动
MAX_CONCURRENT_SCHEDULES=10        # 最大并发调度任务数
SCHEDULE_CHECK_INTERVAL=60         # 调度检查间隔（秒）
```

#### 配置文件配置

```yaml
# 调度器配置
scheduler_config:
  enable_scheduler: true
  auto_start_scheduler: true
  max_concurrent_schedules: 10
  schedule_check_interval: 60

# 在 octopus_service.py 中的配置集成
octopus_config:
  use_task_manager: true
  task_manager_config:
    max_concurrent_tasks: 8
    max_queue_size: 1000
    result_retention_hours: 48
  # 调度器配置会自动从环境变量读取
  enable_scheduler: ${ENABLE_SCHEDULER}
  auto_start_scheduler: ${AUTO_START_SCHEDULER}
  scheduler_config:
    max_concurrent_schedules: ${MAX_CONCURRENT_SCHEDULES}
    schedule_check_interval: ${SCHEDULE_CHECK_INTERVAL}
```

#### 核心方法

```python
class TaskScheduler:
    def __init__(self, task_manager: TaskManager, config: dict = None)
    
    def start(self) -> None
    def stop(self) -> None
    def is_running(self) -> bool
    
    def add_schedule(self, schedule: TaskScheduleConfig) -> str
    def remove_schedule(self, schedule_id: str) -> bool
    def enable_schedule(self, schedule_id: str) -> bool
    def disable_schedule(self, schedule_id: str) -> bool
    
    def get_schedule_status(self, schedule_id: str) -> Optional[ScheduleStatus]
    def list_schedules(self) -> List[TaskScheduleConfig]
    def get_scheduler_status(self) -> Dict[str, Any]
```

#### 调度配置模型

```python
@dataclass
class TaskScheduleConfig:
    name: str
    scraper_name: str
    cron_expression: str
    priority: TaskPriority = TaskPriority.NORMAL
    timeout: int = 300
    max_retries: int = 3
    enabled: bool = True
    fetch_params: Dict[str, Any] = field(default_factory=dict)
    
    schedule_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.now)
    next_run: Optional[datetime] = None
    last_run: Optional[datetime] = None
    run_count: int = 0
```

#### 便捷方法

```python
# 添加每日任务
scheduler.add_daily_task(
    name="daily_news",
    scraper_name="news_scraper",
    hour=9,
    minute=0
)

# 添加每周任务  
scheduler.add_weekly_task(
    name="weekly_report",
    scraper_name="report_scraper",
    day_of_week=1,  # Monday
    hour=8,
    minute=0
)

# 添加每小时任务
scheduler.add_hourly_task(
    name="hourly_check",
    scraper_name="status_scraper",
    minute=30
)
```

#### 调度器状态

```python
{
    "enabled": true,
    "running": true,
    "total_schedules": 5,
    "enabled_schedules": 3,
    "disabled_schedules": 2,
    "running_scheduled_tasks": 1,
    "next_run": "2025-08-04T09:00:00.000Z",
    "configuration": {
        "max_concurrent_schedules": 10,
        "schedule_check_interval": 60,
        "auto_start_scheduler": true
    },
    "schedules_by_status": {
        "enabled": 3,
        "disabled": 2
    }
}
```

#### 调度器 API 端点

一旦启用调度器，以下 API 端点将可用：

**调度器管理:**
- `GET /admin/scheduler/status` - 获取调度器状态
- `POST /admin/scheduler/start` - 启动调度器
- `POST /admin/scheduler/stop` - 停止调度器
- `POST /admin/scheduler/restart` - 重启调度器

**调度任务管理:**
- `GET /admin/scheduler/schedules` - 列出所有调度任务
- `POST /admin/scheduler/schedules` - 添加新调度任务
- `GET /admin/scheduler/schedules/{schedule_id}` - 获取特定调度任务
- `PUT /admin/scheduler/schedules/{schedule_id}` - 更新调度任务
- `DELETE /admin/scheduler/schedules/{schedule_id}` - 删除调度任务
- `POST /admin/scheduler/schedules/{schedule_id}/enable` - 启用调度任务
- `POST /admin/scheduler/schedules/{schedule_id}/disable` - 禁用调度任务
- `POST /admin/scheduler/schedules/{schedule_id}/trigger` - 手动触发调度任务

**监控集成:**
- `GET /admin/monitoring/metrics` - 包含调度器指标（如果启用）
- `GET /health` - 健康检查包含调度器状态

#### 调度器行为说明

**自动启动行为:**
- 当 `ENABLE_SCHEDULER=true` 且 `AUTO_START_SCHEDULER=true` 时：
  - 调度器在服务初始化期间自动创建并启动
  - 服务日志将显示 "TaskScheduler started automatically"

**手动控制:**
- 当 `ENABLE_SCHEDULER=true` 且 `AUTO_START_SCHEDULER=false` 时：
  - 调度器被创建但不启动
  - 使用 `POST /admin/scheduler/start` 手动启动
  - 使用 `POST /admin/scheduler/stop` 停止

**禁用状态:**
- 当 `ENABLE_SCHEDULER=false`（默认）时：
  - 不提供调度器功能
  - 调度器 API 端点将返回相应的错误消息
  - TaskManager 仍正常运行即时任务

**监控和健康检查:**
- 调度器状态包含在健康检查中
- `/health` - 在依赖项中包含调度器状态
- `/admin/monitoring/metrics` - 详细的调度器指标

**关键日志消息:**
```
TaskScheduler started automatically
TaskScheduler stopped and cleaned up
Octopus instance initialized successfully with TaskManager and optional Scheduler
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

### 调度器使用示例

#### 1. 通过环境变量配置调度器

```bash
# 启用调度器
export ENABLE_SCHEDULER=true
export AUTO_START_SCHEDULER=true
export MAX_CONCURRENT_SCHEDULES=10
export SCHEDULE_CHECK_INTERVAL=60

# 启动服务 (调度器会自动启动)
python src/octopus_scraper/octopus_service.py
```

#### 2. 程序中使用调度器

```python
from octopus_scraper import Octopus
from octopus_scraper.task_manager import TaskScheduler, TaskScheduleConfig, TaskPriority

# 创建 Octopus 实例 (调度器根据环境变量自动配置)
octopus = Octopus(config_path="config.yml")

# 获取调度器实例 (如果启用)
scheduler = octopus.get_scheduler()

if scheduler:
    # 添加每日新闻抓取调度
    daily_news_schedule = TaskScheduleConfig(
        name="daily_news",
        scraper_name="news_scraper",
        cron_expression="0 9 * * *",  # 每天上午9点
        priority=TaskPriority.HIGH,
        timeout=300,
        max_retries=2,
        fetch_params={"limit": 50}
    )
    
    schedule_id = scheduler.add_schedule(daily_news_schedule)
    print(f"添加调度任务: {schedule_id}")
    
    # 添加每周报告调度
    scheduler.add_weekly_task(
        name="weekly_summary",
        scraper_name="summary_scraper",
        day_of_week=1,  # 每周一
        hour=8,
        minute=0,
        fetch_params={"report_type": "weekly"}
    )
    
    # 获取调度器状态
    status = scheduler.get_scheduler_status()
    print(f"调度器状态: {status}")
    
    # 列出所有调度任务
    schedules = scheduler.list_schedules()
    for schedule in schedules:
        print(f"调度: {schedule.name} - 下次运行: {schedule.next_run}")
```

#### 3. 通过 API 管理调度

```bash
# 获取调度器状态
curl http://localhost:8000/admin/scheduler/status

# 获取调度任务列表
curl http://localhost:8000/admin/scheduler/schedules

# 添加新调度任务
curl -X POST http://localhost:8000/admin/scheduler/schedules \
  -H "Content-Type: application/json" \
  -d '{
    "name": "hourly_check",
    "scraper_name": "status_scraper", 
    "cron_expression": "0 * * * *",
    "enabled": true,
    "priority": "normal",
    "timeout": 120
  }'

# 手动触发调度任务
curl -X POST http://localhost:8000/admin/scheduler/schedules/schedule_123/trigger

# 启动/停止调度器
curl -X POST http://localhost:8000/admin/scheduler/start
curl -X POST http://localhost:8000/admin/scheduler/stop
```

#### 4. 调度器生命周期管理

```python
from octopus_scraper.task_manager import TaskScheduler

# 如果需要手动管理调度器
scheduler = TaskScheduler(task_manager, config={
    "max_concurrent_schedules": 15,
    "schedule_check_interval": 30
})

# 启动调度器
scheduler.start()

# 检查运行状态
if scheduler.is_running():
    print("调度器正在运行")

# 添加调度后，调度器会自动执行
# ...

# 优雅关闭
scheduler.stop()
```

#### 5. 监控调度执行

```python
# 获取调度器详细状态
status = scheduler.get_scheduler_status()
print(f"""
调度器状态:
- 启用: {status['enabled']}
- 运行中: {status['running']}
- 总调度数: {status['total_schedules']}
- 启用的调度: {status['enabled_schedules']}
- 运行中的调度任务: {status['running_scheduled_tasks']}
- 下次运行: {status['next_run']}
""")

# 获取特定调度的状态
schedule_status = scheduler.get_schedule_status("daily_news")
if schedule_status:
    print(f"调度状态: {schedule_status}")
```

## 配置示例

### 完整配置示例

#### 环境变量配置

```bash
# TaskManager 配置 (默认启用)
MAX_CONCURRENT_TASKS=8
MAX_QUEUE_SIZE=1000
RESULT_RETENTION_HOURS=48

# 调度器配置 (可选)
ENABLE_SCHEDULER=true
AUTO_START_SCHEDULER=true
MAX_CONCURRENT_SCHEDULES=10
SCHEDULE_CHECK_INTERVAL=60

# 服务配置
SERVICE_HOST=0.0.0.0
SERVICE_PORT=8000
LOG_LEVEL=INFO
```

#### 配置文件配置

```yaml
# config.yml
# TaskManager 默认启用，无需 use_task_manager 配置

task_manager_config:
  max_concurrent_tasks: 8
  max_queue_size: 1000
  result_retention_hours: 48
  enable_monitoring: true
  log_level: "INFO"

# 调度器配置 (可选，也可通过环境变量配置)
scheduler_config:
  enable_scheduler: true
  auto_start_scheduler: true
  max_concurrent_schedules: 10
  schedule_check_interval: 60

# 传统调度配置 (用于 Notion 数据库中的调度配置)
scheduler:
  enabled: true
  schedules:
    - name: "daily_vscode_issues"
      scraper_name: "vscode_issues"
      cron_expression: "0 8 * * *"
      enabled: true
      priority: "high"
      timeout: 600
      max_retries: 2
      fetch_params:
        limit: 50
      metadata:
        source: "github"
        category: "issues"
    
    - name: "hourly_status_check"
      scraper_name: "status_scraper"
      cron_expression: "0 * * * *"
      enabled: true
      priority: "normal"
      timeout: 120
      max_retries: 1
      fetch_params:
        check_type: "health"
```

#### Docker Compose 配置

```yaml
# docker-compose.yml
version: '3.8'
services:
  octopus-service:
    build: .
    environment:
      # Notion 配置
      NOTION_API_KEY: ${NOTION_API_KEY}
      NOTION_SCRAPERS_DATABASE_ID: ${NOTION_SCRAPERS_DATABASE_ID}
      NOTION_CONTENT_DATABASE_ID: ${NOTION_CONTENT_DATABASE_ID}
      
      # TaskManager 配置
      MAX_CONCURRENT_TASKS: 8
      MAX_QUEUE_SIZE: 1000
      RESULT_RETENTION_HOURS: 48
      
      # 调度器配置
      ENABLE_SCHEDULER: true
      AUTO_START_SCHEDULER: true
      MAX_CONCURRENT_SCHEDULES: 10
      SCHEDULE_CHECK_INTERVAL: 60
      
      # 服务配置
      SERVICE_HOST: 0.0.0.0
      SERVICE_PORT: 8000
      LOG_LEVEL: INFO
      LOG_FORMAT: json
      ENVIRONMENT: production
    ports:
      - "8000:8000"
    volumes:
      - ./logs:/app/logs
    restart: unless-stopped
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
