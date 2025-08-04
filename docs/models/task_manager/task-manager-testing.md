# TaskManager 测试文档

## 📢 重要更新

**TaskManager 现已成为默认且唯一的任务执行方式**。所有测试都基于这一架构更新：

- ✅ **默认启用**: TaskManager 在所有测试中自动启用
- ❌ **移除传统测试**: 不再测试 `use_task_manager=false` 的情况
- 🔄 **测试更新**: 所有测试用例都假设 TaskManager 已启用
- 🚀 **简化配置**: 测试配置中无需设置 `use_task_manager: true`

## 概述

TaskManager 的测试覆盖了任务提交、执行、监控、调度等核心功能，确保任务管理系统的可靠性和性能。由于 TaskManager 现已成为唯一的任务执行方式，所有测试都围绕这一统一架构进行。

## 测试文件位置

- **核心测试**: `tests/octopus_scraper/task_manager/task_manager_test.py`
- **调度器测试**: `tests/octopus_scraper/task_manager/scheduler_test.py`
- **模型测试**: `tests/octopus_scraper/task_manager/models_test.py`
- **Octopus 集成测试**: `tests/octopus_scraper/task_manager/test_octopus_integration.py`
- **Octopus 核心测试**: `tests/octopus_scraper/octopus_test.py`
- **Web 服务集成测试**: `tests/octopus_scraper/octopus_service_test.py` (任务管理部分)

## 测试结构

### TaskManager 核心测试

#### 测试类: `TestTaskManager`

```python
class TestTaskManager:
    """TaskManager 核心功能测试"""

    async def test_init_and_start(self):
        """测试初始化和启动"""

    async def test_submit_task(self):
        """测试任务提交"""

    async def test_task_execution(self):
        """测试任务执行"""

    async def test_task_priority(self):
        """测试任务优先级"""

    async def test_concurrent_tasks(self):
        """测试并发任务执行"""

    async def test_task_cancellation(self):
        """测试任务取消"""

    async def test_task_timeout(self):
        """测试任务超时"""

    async def test_task_retry(self):
        """测试任务重试"""

    def test_get_statistics(self):
        """测试获取统计信息"""

    def test_list_tasks(self):
        """测试任务列表"""
```

#### 测试类: `TestTaskExecution`

```python
class TestTaskExecution:
    """任务执行流程测试"""

    async def test_successful_task(self):
        """测试成功任务执行"""

    async def test_failing_task(self):
        """测试失败任务处理"""

    async def test_task_with_result(self):
        """测试带结果的任务"""

    async def test_task_error_handling(self):
        """测试任务错误处理"""
```

### TaskScheduler 测试

#### 测试类: `TestTaskScheduler`

```python
class TestTaskScheduler:
    """任务调度器测试"""

    async def test_scheduler_init(self):
        """测试调度器初始化"""

    async def test_add_schedule(self):
        """测试添加调度任务"""

    async def test_remove_schedule(self):
        """测试移除调度任务"""

    async def test_cron_execution(self):
        """测试 Cron 表达式执行"""

    async def test_schedule_conflict(self):
        """测试调度冲突处理"""

    async def test_scheduler_persistence(self):
        """测试调度器持久化"""
```

### 模型测试

#### 测试类: `TestTaskModels`

```python
class TestTaskModels:
    """任务模型测试"""

    def test_task_creation(self):
        """测试任务创建"""

    def test_task_serialization(self):
        """测试任务序列化"""

    def test_task_status_transitions(self):
        """测试任务状态转换"""

    def test_task_result_model(self):
        """测试任务结果模型"""

    def test_schedule_config(self):
        """测试调度配置"""
```

## 测试用例详解

### 任务提交和执行测试

```python
async def test_task_submission_and_execution(self):
    """测试任务提交和执行流程"""

    class TestTask(Task):
        def __init__(self, result_value: str):
            super().__init__(task_type="test")
            self.result_value = result_value

        async def execute(self) -> TaskResult:
            await asyncio.sleep(0.1)  # 模拟执行时间
            return TaskResult(
                task_id=self.task_id,
                status=TaskStatus.COMPLETED,
                result_data=self.result_value,
                execution_time=0.1
            )

    task_manager = TaskManager(max_concurrent_tasks=2)
    await task_manager.start()

    try:
        # 提交任务
        task = TestTask("test_result")
        task_id = await task_manager.submit_task(task, TaskPriority.HIGH)

        # 验证任务ID
        assert task_id is not None
        assert task_id == task.task_id

        # 等待任务完成
        await asyncio.sleep(0.2)

        # 检查任务状态
        status = task_manager.get_task_status(task_id)
        assert status == TaskStatus.COMPLETED

        # 检查任务结果
        result = task_manager.get_task_result(task_id)
        assert result.result_data == "test_result"
        assert result.execution_time > 0

    finally:
        await task_manager.stop()
```

### 并发控制测试

```python
async def test_concurrent_task_limit(self):
    """测试并发任务数量限制"""

    class SlowTask(Task):
        async def execute(self) -> TaskResult:
            await asyncio.sleep(1.0)  # 模拟长时间任务
            return TaskResult(
                task_id=self.task_id,
                status=TaskStatus.COMPLETED
            )

    max_concurrent = 3
    task_manager = TaskManager(max_concurrent_tasks=max_concurrent)
    await task_manager.start()

    try:
        # 提交多个任务
        task_ids = []
        for i in range(6):  # 提交超过并发限制的任务数
            task = SlowTask()
            task_id = await task_manager.submit_task(task)
            task_ids.append(task_id)

        # 检查活跃任务数量不超过限制
        await asyncio.sleep(0.1)  # 让任务开始执行
        stats = task_manager.get_statistics()
        assert stats.active_tasks <= max_concurrent
        assert stats.pending_tasks > 0

        # 等待所有任务完成
        await asyncio.sleep(3.0)

        # 验证所有任务都完成了
        final_stats = task_manager.get_statistics()
        assert final_stats.active_tasks == 0
        assert final_stats.completed_tasks == 6

    finally:
        await task_manager.stop()
```

### 优先级测试

```python
async def test_task_priority_ordering(self):
    """测试任务优先级排序"""

    executed_order = []

    class PriorityTestTask(Task):
        def __init__(self, name: str):
            super().__init__(task_type="priority_test")
            self.name = name

        async def execute(self) -> TaskResult:
            executed_order.append(self.name)
            return TaskResult(
                task_id=self.task_id,
                status=TaskStatus.COMPLETED
            )

    task_manager = TaskManager(max_concurrent_tasks=1)  # 串行执行
    await task_manager.start()

    try:
        # 按不同优先级提交任务
        await task_manager.submit_task(PriorityTestTask("low"), TaskPriority.LOW)
        await task_manager.submit_task(PriorityTestTask("urgent"), TaskPriority.URGENT)
        await task_manager.submit_task(PriorityTestTask("normal"), TaskPriority.NORMAL)
        await task_manager.submit_task(PriorityTestTask("high"), TaskPriority.HIGH)

        # 等待所有任务完成
        await asyncio.sleep(1.0)

        # 验证执行顺序 (优先级: URGENT > HIGH > NORMAL > LOW)
        expected_order = ["urgent", "high", "normal", "low"]
        assert executed_order == expected_order

    finally:
        await task_manager.stop()
```

### 错误处理和重试测试

```python
async def test_task_retry_mechanism(self):
    """测试任务重试机制"""

    attempt_count = 0

    class FailingTask(Task):
        def __init__(self, max_retries: int = 3):
            super().__init__(task_type="failing", max_retries=max_retries)

        async def execute(self) -> TaskResult:
            nonlocal attempt_count
            attempt_count += 1

            if attempt_count < 3:
                raise Exception(f"Attempt {attempt_count} failed")

            return TaskResult(
                task_id=self.task_id,
                status=TaskStatus.COMPLETED,
                retry_count=attempt_count - 1
            )

    task_manager = TaskManager()
    await task_manager.start()

    try:
        task = FailingTask(max_retries=3)
        task_id = await task_manager.submit_task(task)

        # 等待任务完成（包括重试）
        await asyncio.sleep(2.0)

        # 验证任务最终成功
        status = task_manager.get_task_status(task_id)
        assert status == TaskStatus.COMPLETED

        # 验证重试次数
        result = task_manager.get_task_result(task_id)
        assert result.retry_count == 2
        assert attempt_count == 3

    finally:
        await task_manager.stop()
```

### 调度器测试

```python
async def test_cron_schedule_execution(self):
    """测试 Cron 调度执行"""

    executed_tasks = []

    class ScheduledTask(Task):
        def __init__(self, schedule_id: str):
            super().__init__(task_type="scheduled")
            self.schedule_id = schedule_id

        async def execute(self) -> TaskResult:
            executed_tasks.append(self.schedule_id)
            return TaskResult(
                task_id=self.task_id,
                status=TaskStatus.COMPLETED
            )

    task_manager = TaskManager()
    await task_manager.start()

    scheduler = TaskScheduler(task_manager)
    await scheduler.start()

    try:
        # 添加每秒执行的调度
        schedule = ScheduleConfig(
            schedule_id="test_schedule",
            scraper_name="test_scraper",
            cron_expression="* * * * * *",  # 每秒执行
            enabled=True,
            max_concurrent_runs=1
        )

        scheduler.add_schedule(schedule)

        # 等待几次执行
        await asyncio.sleep(3.5)

        # 验证任务被执行了
        assert len(executed_tasks) >= 3
        assert all(task_id == "test_schedule" for task_id in executed_tasks)

    finally:
        await scheduler.stop()
        await task_manager.stop()
```

### 调度器环境变量配置测试

#### 测试类: `TestSchedulerEnvironmentConfig`

```python
class TestSchedulerEnvironmentConfig:
    """调度器环境变量配置测试"""

    def test_scheduler_disabled_by_default(self):
        """测试调度器默认禁用"""
        with patch.dict(os.environ, {}, clear=True):
            _, _, _, scheduler_config = create_config_from_env()
            assert scheduler_config["enable_scheduler"] == False
            assert scheduler_config["auto_start_scheduler"] == False

    def test_scheduler_enabled_via_env(self):
        """测试通过环境变量启用调度器"""
        env_vars = {
            "ENABLE_SCHEDULER": "true",
            "AUTO_START_SCHEDULER": "true",
            "MAX_CONCURRENT_SCHEDULES": "15",
            "SCHEDULE_CHECK_INTERVAL": "30"
        }
        
        with patch.dict(os.environ, env_vars):
            _, _, _, scheduler_config = create_config_from_env()
            assert scheduler_config["enable_scheduler"] == True
            assert scheduler_config["auto_start_scheduler"] == True
            assert scheduler_config["scheduler_config"]["max_concurrent_schedules"] == 15
            assert scheduler_config["scheduler_config"]["schedule_check_interval"] == 30

    def test_scheduler_boolean_parsing(self):
        """测试调度器布尔值解析"""
        test_cases = [
            ("true", True), ("TRUE", True), ("True", True),
            ("false", False), ("FALSE", False), ("False", False),
            ("1", False), ("0", False), ("", False), ("random", False)
        ]
        
        for env_value, expected in test_cases:
            with patch.dict(os.environ, {"ENABLE_SCHEDULER": env_value}, clear=True):
                _, _, _, scheduler_config = create_config_from_env()
                assert scheduler_config["enable_scheduler"] == expected

    def test_scheduler_integer_parsing(self):
        """测试调度器整数值解析"""
        env_vars = {
            "MAX_CONCURRENT_SCHEDULES": "25",
            "SCHEDULE_CHECK_INTERVAL": "120"
        }
        
        with patch.dict(os.environ, env_vars):
            _, _, _, scheduler_config = create_config_from_env()
            assert scheduler_config["scheduler_config"]["max_concurrent_schedules"] == 25
            assert scheduler_config["scheduler_config"]["schedule_check_interval"] == 120

    def test_scheduler_invalid_integer(self):
        """测试调度器无效整数值处理"""
        env_vars = {"MAX_CONCURRENT_SCHEDULES": "not_a_number"}
        
        with patch.dict(os.environ, env_vars):
            with pytest.raises(ValueError):
                create_config_from_env()

    async def test_octopus_setup_with_scheduler_enabled(self):
        """测试启用调度器的 Octopus 设置"""
        mock_app = Mock()
        mock_config_manager = Mock()
        mock_config_manager.load_initial_config = AsyncMock(return_value=[])
        mock_config_manager.get_current_version = Mock(return_value=Mock(version_id="test_v1"))
        mock_config_manager.start_config_watcher = Mock()

        with patch("octopus_scraper.octopus_service.create_config_from_env") as mock_create_config, \
             patch("octopus_scraper.octopus_service.ConfigManager") as mock_config_class, \
             patch("octopus_scraper.octopus_service.Octopus") as mock_octopus_class:

            # 模拟启用调度器的配置
            mock_create_config.return_value = (
                Mock(),  # notion_config
                Mock(),  # service_config
                {"max_concurrent_tasks": 8, "max_queue_size": 1000, "result_retention_hours": 48},
                {
                    "enable_scheduler": True,
                    "auto_start_scheduler": True,
                    "scheduler_config": {
                        "max_concurrent_schedules": 10,
                        "schedule_check_interval": 60
                    }
                }
            )
            
            mock_config_class.return_value = mock_config_manager
            mock_octopus_instance = Mock()
            mock_octopus_class.return_value = mock_octopus_instance

            await setup_octopus(mock_app, None)

            # 验证 Octopus 使用了调度器配置
            mock_octopus_class.assert_called_once()
            call_args = mock_octopus_class.call_args[0][0]
            assert call_args["enable_scheduler"] == True
            assert call_args["auto_start_scheduler"] == True

    async def test_octopus_setup_with_scheduler_disabled(self):
        """测试禁用调度器的 Octopus 设置"""
        mock_app = Mock()
        mock_config_manager = Mock()
        mock_config_manager.load_initial_config = AsyncMock(return_value=[])
        mock_config_manager.get_current_version = Mock(return_value=Mock(version_id="test_v1"))
        mock_config_manager.start_config_watcher = Mock()

        with patch("octopus_scraper.octopus_service.create_config_from_env") as mock_create_config, \
             patch("octopus_scraper.octopus_service.ConfigManager") as mock_config_class, \
             patch("octopus_scraper.octopus_service.Octopus") as mock_octopus_class:

            # 模拟禁用调度器的配置
            mock_create_config.return_value = (
                Mock(),  # notion_config
                Mock(),  # service_config
                {"max_concurrent_tasks": 8, "max_queue_size": 1000, "result_retention_hours": 48},
                {
                    "enable_scheduler": False,
                    "auto_start_scheduler": False,
                    "scheduler_config": {
                        "max_concurrent_schedules": 10,
                        "schedule_check_interval": 60
                    }
                }
            )
            
            mock_config_class.return_value = mock_config_manager
            mock_octopus_instance = Mock()
            mock_octopus_class.return_value = mock_octopus_instance

            await setup_octopus(mock_app, None)

            # 验证 Octopus 使用了禁用的调度器配置
            mock_octopus_class.assert_called_once()
            call_args = mock_octopus_class.call_args[0][0]
            assert call_args["enable_scheduler"] == False
            assert call_args["auto_start_scheduler"] == False
```

## Web 服务集成测试

### 任务管理 API 测试

位置: `tests/octopus_scraper/octopus_service_test.py`

```python
class TestTaskManagementEndpoints:
    """任务管理 API 端点测试"""

    async def test_task_stats_endpoint(self):
        """测试任务统计端点"""

    async def test_submit_task_endpoint(self):
        """测试任务提交端点"""

    async def test_list_tasks_endpoint(self):
        """测试任务列表端点"""

    async def test_cancel_task_endpoint(self):
        """测试任务取消端点"""

    async def test_task_details_endpoint(self):
        """测试任务详情端点"""
```

### 调度器 API 测试

位置: `tests/octopus_scraper/octopus_service_test.py`

```python
class TestSchedulerAPIEndpoints:
    """调度器 API 端点测试"""

    async def test_scheduler_status_endpoint(self):
        """测试调度器状态端点"""
        mock_request = Mock()
        
        with patch("octopus_scraper.octopus_service.app") as mock_app:
            mock_octopus = Mock()
            mock_octopus.get_scheduler_status.return_value = {
                "enabled": True,
                "running": True,
                "total_schedules": 5,
                "enabled_schedules": 3
            }
            mock_app.ctx.octopus = mock_octopus
            
            response = await scheduler_status(mock_request)
            assert response.status == 200

    async def test_scheduler_start_stop_endpoints(self):
        """测试调度器启动/停止端点"""
        mock_request = Mock()
        
        with patch("octopus_scraper.octopus_service.app") as mock_app:
            mock_scheduler = Mock()
            mock_app.ctx.octopus.get_scheduler.return_value = mock_scheduler
            
            # 测试启动
            response = await start_scheduler(mock_request)
            assert response.status == 200
            mock_scheduler.start.assert_called_once()
            
            # 测试停止
            response = await stop_scheduler(mock_request)
            assert response.status == 200
            mock_scheduler.stop.assert_called_once()

    async def test_schedule_management_endpoints(self):
        """测试调度任务管理端点"""
        mock_request = Mock()
        mock_request.json = {
            "name": "test_schedule",
            "scraper_name": "test_scraper",
            "cron_expression": "0 9 * * *",
            "enabled": True
        }
        
        with patch("octopus_scraper.octopus_service.app") as mock_app:
            mock_scheduler = Mock()
            mock_scheduler.add_schedule.return_value = "schedule_123"
            mock_app.ctx.octopus.get_scheduler.return_value = mock_scheduler
            
            # 测试添加调度
            response = await add_schedule(mock_request)
            assert response.status == 200
            mock_scheduler.add_schedule.assert_called_once()

    async def test_schedule_trigger_endpoint(self):
        """测试手动触发调度端点"""
        mock_request = Mock()
        
        with patch("octopus_scraper.octopus_service.app") as mock_app:
            mock_scheduler = Mock()
            mock_scheduler.trigger_schedule.return_value = "task_456"
            mock_app.ctx.octopus.get_scheduler.return_value = mock_scheduler
            
            response = await trigger_schedule(mock_request, "schedule_123")
            assert response.status == 200

    async def test_scheduler_disabled_error_responses(self):
        """测试调度器禁用时的错误响应"""
        mock_request = Mock()
        
        with patch("octopus_scraper.octopus_service.app") as mock_app:
            # 模拟调度器未启用
            mock_app.ctx.octopus.get_scheduler.return_value = None
            
            response = await scheduler_status(mock_request)
            assert response.status == 503  # Service Unavailable

    async def test_monitoring_metrics_with_scheduler(self):
        """测试监控指标包含调度器信息"""
        mock_request = Mock()
        
        with patch("octopus_scraper.octopus_service.app") as mock_app:
            mock_octopus = Mock()
            mock_octopus.get_scheduler_status.return_value = {
                "enabled": True,
                "status": "running",
                "total_schedules": 5,
                "enabled_schedules": 3,
                "running_scheduled_tasks": 1
            }
            mock_app.ctx.octopus = mock_octopus
            mock_app.ctx.config_manager = Mock()
            
            response = await get_monitoring_metrics(mock_request)
            assert response.status == 200
            
            # 验证响应包含调度器指标
            import json
            data = json.loads(response.body.decode('utf-8'))
            assert "scheduler" in data["metrics"]
            assert data["metrics"]["scheduler"]["enabled"] == True
```

## Octopus 集成测试

### TaskManager 与 Octopus 集成

位置: `tests/octopus_scraper/task_manager/test_octopus_integration.py`

#### 测试 Octopus 初始化

```python
@patch("octopus_scraper.octopus.NotionStorage")
def test_octopus_initialization_with_task_manager(
    mock_notion_class, octopus_config_with_task_manager
):
    """测试 Octopus 初始化时 TaskManager 自动启用"""
    mock_notion_class.return_value = Mock()

    octopus = Octopus(octopus_config_with_task_manager)

    # 验证 TaskManager 已初始化且配置正确
    assert octopus._task_manager is not None
    assert octopus._task_manager.max_concurrent_tasks == 4
    assert octopus._task_manager.max_queue_size == 100
    assert octopus._task_manager.result_retention_hours == 2

    # 验证存储已设置
    assert octopus._task_manager._storage is not None

    # 清理
    octopus.cleanup_task_manager()
```

#### 测试抓取器触发

```python
@patch("octopus_scraper.octopus.NotionStorage")
@patch("octopus_scraper.scrapers.scraper.Scraper")
def test_trigger_scraper_with_task_manager(
    mock_scraper_class,
    mock_notion_class,
    octopus_config_with_task_manager,
    sample_contents,
):
    """测试通过 TaskManager 触发抓取器"""
    mock_notion_class.return_value = Mock()
    mock_scraper = Mock()
    mock_scraper.scrap_contents.return_value = sample_contents
    mock_scraper_class.return_value = mock_scraper

    octopus = Octopus(octopus_config_with_task_manager)

    # 触发抓取器
    batch_id = octopus.trigger_scraper()

    # 验证返回批次ID
    assert batch_id is not None
    assert batch_id.startswith("scraper_batch_")

    # 验证任务已提交到 TaskManager
    stats = octopus.get_task_manager_statistics()
    assert stats["total_tasks"] == 2  # 配置了两个抓取器

    # 清理
    octopus.cleanup_task_manager()
```

#### 测试任务状态和统计

```python
def test_octopus_task_management_methods(octopus_with_task_manager):
    """测试 Octopus 任务管理方法"""

    # 测试获取任务管理器
    task_manager = octopus_with_task_manager.get_task_manager()
    assert task_manager is not None

    # 测试获取统计信息
    stats = octopus_with_task_manager.get_task_manager_statistics()
    assert isinstance(stats, dict)
    assert "total_tasks" in stats
    assert "completed_tasks" in stats

    # 测试列出任务
    tasks = octopus_with_task_manager.list_tasks(limit=10)
    assert isinstance(tasks, list)
```

### 配置更新对应的测试

TaskManager 现已默认启用，测试需要反映这一变化：

#### 配置测试示例

```python
def test_task_manager_always_enabled():
    """测试 TaskManager 始终启用"""
    config = {
        "scrapers_config_with_fetch_params": [...],
        "notion_api_config": {...},
        # 注意：不再需要 use_task_manager: true
        "task_manager_config": {
            "max_concurrent_tasks": 8,
            "max_queue_size": 1000,
            "result_retention_hours": 48,
        },
    }

    octopus = Octopus(config)

    # TaskManager 应该始终存在
    assert octopus._task_manager is not None
    assert octopus._config.use_task_manager == True  # 强制为 True
```

#### 环境变量配置测试

```python
@patch.dict("os.environ", {
    "MAX_CONCURRENT_TASKS": "12",
    "MAX_QUEUE_SIZE": "2000",
    "RESULT_RETENTION_HOURS": "72"
})
def test_task_manager_env_config():
    """测试通过环境变量配置 TaskManager"""
    from octopus_scraper.octopus_service import create_config_from_env

    notion_config, service_config, task_manager_config = create_config_from_env()

    # 验证环境变量配置正确应用
    assert task_manager_config["max_concurrent_tasks"] == 12
    assert task_manager_config["max_queue_size"] == 2000
    assert task_manager_config["result_retention_hours"] == 72
```

## Mock 和 Fixture

### 通用 Fixture

```python
@pytest.fixture
async def task_manager():
    """TaskManager fixture"""
    manager = TaskManager(max_concurrent_tasks=2, max_queue_size=100)
    await manager.start()
    yield manager
    await manager.stop()

@pytest.fixture
async def scheduler(task_manager):
    """TaskScheduler fixture"""
    sched = TaskScheduler(task_manager)
    await sched.start()
    yield sched
    await sched.stop()

@pytest.fixture
def sample_task():
    """示例任务 fixture"""
    class SampleTask(Task):
        async def execute(self) -> TaskResult:
            return TaskResult(
                task_id=self.task_id,
                status=TaskStatus.COMPLETED,
                result_data="sample_result"
            )
    return SampleTask()
```

### Mock 任务

```python
@pytest.fixture
def mock_scraper_task():
    """Mock 抓取任务"""
    task = Mock(spec=ScraperTask)
    task.task_id = "mock_task_id"
    task.task_type = "scraper"
    task.execute = AsyncMock(return_value=TaskResult(
        task_id="mock_task_id",
        status=TaskStatus.COMPLETED
    ))
    return task
```

## 测试运行

### 核心 TaskManager 测试

```bash
# 运行所有 TaskManager 测试
poetry run pytest tests/octopus_scraper/task_manager/ -v

# 运行核心 TaskManager 测试
poetry run pytest tests/octopus_scraper/task_manager/task_manager_test.py -v

# 运行调度器测试
poetry run pytest tests/octopus_scraper/task_manager/scheduler_test.py -v
```

### 集成测试

```bash
# 运行 Octopus 集成测试
poetry run pytest tests/octopus_scraper/task_manager/test_octopus_integration.py -v

# 运行 Octopus 核心测试 (包含 TaskManager 集成)
poetry run pytest tests/octopus_scraper/octopus_test.py -v

# 运行任务管理 API 测试
poetry run pytest tests/octopus_scraper/octopus_service_test.py::TestAdminEndpoints -k "task" -v

# 运行特定的任务统计测试
poetry run pytest tests/octopus_scraper/octopus_service_test.py::TestAdminEndpoints::test_task_stats_with_task_manager -v
```

### 性能测试

```bash
# 运行性能测试
poetry run pytest tests/octopus_scraper/task_manager/performance_test.py -v

# 运行负载测试
poetry run pytest tests/octopus_scraper/task_manager/load_test.py -v
```

### 测试覆盖率

```bash
# 生成测试覆盖率报告
poetry run pytest tests/octopus_scraper/task_manager/ --cov=octopus_scraper.task_manager --cov-report=html

# 查看覆盖率报告
open htmlcov/index.html
```

## 性能测试

### 吞吐量测试

```python
async def test_task_throughput(benchmark):
    """测试任务吞吐量"""

    async def submit_and_execute_tasks():
        task_manager = TaskManager(max_concurrent_tasks=10)
        await task_manager.start()

        try:
            # 提交100个快速任务
            tasks = []
            for i in range(100):
                task = QuickTask(f"task_{i}")
                task_id = await task_manager.submit_task(task)
                tasks.append(task_id)

            # 等待所有任务完成
            while task_manager.get_statistics().active_tasks > 0:
                await asyncio.sleep(0.01)

            stats = task_manager.get_statistics()
            assert stats.completed_tasks == 100

        finally:
            await task_manager.stop()

    await benchmark(submit_and_execute_tasks)
```

### 内存使用测试

```python
def test_memory_usage_under_load():
    """测试高负载下的内存使用"""

    import psutil
    import os

    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss

    async def load_test():
        task_manager = TaskManager(max_concurrent_tasks=50)
        await task_manager.start()

        try:
            # 提交大量任务
            for i in range(1000):
                task = MemoryTestTask()
                await task_manager.submit_task(task)

            # 等待任务完成
            while task_manager.get_statistics().pending_tasks > 0:
                await asyncio.sleep(0.1)

        finally:
            await task_manager.stop()

    asyncio.run(load_test())

    final_memory = process.memory_info().rss
    memory_increase = final_memory - initial_memory

    # 内存增长应该在合理范围内 (100MB)
    assert memory_increase < 100 * 1024 * 1024
```

## 测试数据和工具

### 测试任务实现

```python
class QuickTask(Task):
    """快速执行的测试任务"""

    def __init__(self, name: str):
        super().__init__(task_type="quick")
        self.name = name

    async def execute(self) -> TaskResult:
        await asyncio.sleep(0.001)  # 1ms
        return TaskResult(
            task_id=self.task_id,
            status=TaskStatus.COMPLETED,
            result_data=f"Result for {self.name}"
        )

class SlowTask(Task):
    """慢速执行的测试任务"""

    async def execute(self) -> TaskResult:
        await asyncio.sleep(1.0)  # 1s
        return TaskResult(
            task_id=self.task_id,
            status=TaskStatus.COMPLETED
        )

class FailingTask(Task):
    """会失败的测试任务"""

    async def execute(self) -> TaskResult:
        raise Exception("Intentional failure for testing")
```

### 测试工具函数

```python
async def wait_for_completion(task_manager: TaskManager, timeout: float = 5.0):
    """等待所有任务完成"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        stats = task_manager.get_statistics()
        if stats.active_tasks == 0 and stats.pending_tasks == 0:
            return True
        await asyncio.sleep(0.1)
    return False

def assert_task_stats(stats: TaskStatistics, **expected):
    """验证任务统计"""
    for key, value in expected.items():
        actual = getattr(stats, key)
        assert actual == value, f"Expected {key}={value}, got {actual}"
```

## 故障排除

### 常见测试问题

1. **异步测试超时**

   ```python
   # 使用适当的超时时间
   await asyncio.wait_for(task_completion, timeout=10.0)
   ```

2. **资源清理**

   ```python
   # 确保在测试后清理 TaskManager
   try:
       # 测试代码
   finally:
       await task_manager.stop()
   ```

3. **并发测试不稳定**
   ```python
   # 使用适当的等待时间
   await asyncio.sleep(0.1)  # 让任务开始执行
   ```

## 测试最佳实践

1. **异步测试**: 正确使用 `@pytest.mark.asyncio`
2. **资源管理**: 确保 TaskManager 正确启动和停止
3. **时间控制**: 合理设置测试任务的执行时间
4. **并发控制**: 测试并发限制和队列管理
5. **错误覆盖**: 测试各种错误和异常情况
6. **性能验证**: 包含性能和负载测试

## 相关文档

- [TaskManager Models](./task-manager.md)
- [Admin Interface Testing](../../interface/web_service/admin-interface-testing.md)
- [ConfigManager Testing](../config/config-manager-testing.md)
