# TaskManager 测试文档

## 概述

TaskManager 的测试覆盖了任务提交、执行、监控、调度等核心功能，确保任务管理系统的可靠性和性能。

## 测试文件位置

- **核心测试**: `tests/octopus_scraper/task_manager/task_manager_test.py`
- **调度器测试**: `tests/octopus_scraper/task_manager/scheduler_test.py`
- **模型测试**: `tests/octopus_scraper/task_manager/models_test.py`
- **集成测试**: `tests/octopus_scraper/octopus_service_test.py` (任务管理部分)

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

### 运行所有 TaskManager 测试

```bash
# 运行核心任务管理测试
poetry run pytest tests/octopus_scraper/task_manager/ -v

# 运行特定测试文件
poetry run pytest tests/octopus_scraper/task_manager/task_manager_test.py -v

# 运行调度器测试
poetry run pytest tests/octopus_scraper/task_manager/scheduler_test.py -v
```

### 运行 Web 服务集成测试

```bash
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
