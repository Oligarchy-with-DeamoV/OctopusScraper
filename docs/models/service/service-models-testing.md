# Service Models 测试文档

## 概述

Service Models 的测试确保数据模型的正确性、序列化/反序列化功能、数据验证、以及与各种存储后端的兼容性。测试覆盖了所有核心模型的创建、转换、验证和错误处理。

## 测试文件位置

- **核心模型测试**: `tests/octopus_scraper/service_models_test.py`
- **数据验证测试**: `tests/octopus_scraper/models/validation_test.py`
- **序列化测试**: `tests/octopus_scraper/models/serialization_test.py`
- **响应模型测试**: `tests/octopus_scraper/models/response_models_test.py`
- **统计模型测试**: `tests/octopus_scraper/models/statistics_test.py`
- **集成测试**: `tests/octopus_scraper/octopus_service_test.py` (模型部分)

## 测试结构

### BaseModel 测试

#### 测试类: `TestBaseModel`

```python
class TestBaseModel:
    """基础模型测试"""

    def test_base_model_creation(self):
        """测试基础模型创建"""

    def test_to_dict_conversion(self):
        """测试字典转换"""

    def test_to_json_conversion(self):
        """测试 JSON 转换"""

    def test_timestamp_management(self):
        """测试时间戳管理"""

    def test_metadata_handling(self):
        """测试元数据处理"""

    def test_from_dict_creation(self):
        """测试从字典创建"""
```

### ScrapingItem 测试

#### 测试类: `TestScrapingItem`

```python
class TestScrapingItem:
    """抓取项目模型测试"""

    def test_scraping_item_creation(self):
        """测试抓取项目创建"""

    def test_content_hash_calculation(self):
        """测试内容哈希计算"""

    def test_word_count_estimation(self):
        """测试字数统计"""

    def test_display_title_truncation(self):
        """测试标题截断"""

    def test_domain_extraction(self):
        """测试域名提取"""

    def test_recent_content_check(self):
        """测试最近内容检查"""

    def test_processing_error_handling(self):
        """测试处理错误管理"""

    def test_mark_processed(self):
        """测试标记已处理"""
```

### ScrapingResult 测试

#### 测试类: `TestScrapingResult`

```python
class TestScrapingResult:
    """抓取结果模型测试"""

    def test_scraping_result_creation(self):
        """测试抓取结果创建"""

    def test_status_enum_handling(self):
        """测试状态枚举处理"""

    def test_statistics_calculation(self):
        """测试统计信息计算"""

    def test_execution_time_calculation(self):
        """测试执行时间计算"""

    def test_success_property(self):
        """测试成功属性"""

    def test_success_rate_calculation(self):
        """测试成功率计算"""

    def test_warning_management(self):
        """测试警告管理"""

    def test_error_handling(self):
        """测试错误处理"""

    def test_result_summary(self):
        """测试结果摘要"""
```

### TaskModel 测试

#### 测试类: `TestTaskModel`

```python
class TestTaskModel:
    """任务模型测试"""

    def test_task_model_creation(self):
        """测试任务模型创建"""

    def test_task_id_generation(self):
        """测试任务ID生成"""

    def test_status_transitions(self):
        """测试状态转换"""

    def test_priority_handling(self):
        """测试优先级处理"""

    def test_execution_lifecycle(self):
        """测试执行生命周期"""

    def test_retry_mechanism(self):
        """测试重试机制"""

    def test_task_properties(self):
        """测试任务属性"""
```

## 测试用例详解

### ScrapingItem 综合测试

```python
def test_scraping_item_comprehensive(self):
    """测试抓取项目综合功能"""

    # 创建基本项目
    item = ScrapingItem(
        title="测试文章标题",
        url="https://example.com/article/123",
        content="这是一篇测试文章的内容。包含多个句子和段落。",
        author="测试作者",
        tags=["测试", "文章", "示例"],
        published_date=datetime(2023, 11, 15, 10, 30, 0)
    )

    # 验证基本属性
    assert item.title == "测试文章标题"
    assert item.url == "https://example.com/article/123"
    assert item.author == "测试作者"
    assert len(item.tags) == 3
    assert "测试" in item.tags

    # 验证自动计算的属性
    assert item.content_hash is not None
    assert len(item.content_hash) == 32  # MD5 哈希长度
    assert item.word_count > 0

    # 测试显示标题
    short_title = item.get_display_title(max_length=10)
    assert len(short_title) <= 10
    assert short_title.endswith("...") if len(item.title) > 10 else True

    # 测试域名提取
    domain = item.get_domain()
    assert domain == "example.com"

    # 测试最近内容检查
    is_recent = item.is_recent(days=30)
    # 根据发布日期判断

    # 测试处理错误
    item.add_processing_error("测试错误")
    assert len(item.processing_errors) == 1
    assert "测试错误" in item.processing_errors

    # 测试标记已处理
    initial_time = item.updated_at
    time.sleep(0.1)
    item.mark_processed()
    assert item.processed == True
    assert item.updated_at > initial_time

    # 测试序列化
    item_dict = item.to_dict()
    assert isinstance(item_dict, dict)
    assert item_dict['title'] == item.title
    assert item_dict['tags'] == item.tags

    item_json = item.to_json()
    assert isinstance(item_json, str)
    assert "测试文章标题" in item_json

def test_scraping_item_edge_cases(self):
    """测试抓取项目边界情况"""

    # 最小化项目
    minimal_item = ScrapingItem(
        title="",
        url="invalid-url"
    )

    # 验证默认值
    assert minimal_item.tags == []
    assert minimal_item.metadata == {}
    assert minimal_item.processed == False
    assert minimal_item.processing_errors == []

    # 测试无效 URL 的域名提取
    domain = minimal_item.get_domain()
    assert domain is None

    # 测试没有发布日期的最近检查
    is_recent = minimal_item.is_recent()
    assert is_recent == False

    # 测试空内容的字数统计
    assert minimal_item.word_count == 0

    # 测试长标题处理
    long_title_item = ScrapingItem(
        title="这是一个非常长的标题" * 10,
        url="https://example.com"
    )

    short_title = long_title_item.get_display_title(max_length=50)
    assert len(short_title) <= 50
    assert short_title.endswith("...")
```

### ScrapingResult 状态和统计测试

```python
def test_scraping_result_statistics(self):
    """测试抓取结果统计功能"""

    # 创建测试项目
    items = [
        ScrapingItem(title=f"Item {i}", url=f"https://example.com/{i}")
        for i in range(5)
    ]

    # 创建成功结果
    start_time = datetime.now()
    time.sleep(0.1)
    end_time = datetime.now()

    result = ScrapingResult(
        scraper_name="test_scraper",
        status=ScrapingStatus.SUCCESS,
        items=items,
        start_time=start_time,
        end_time=end_time,
        new_items=3,
        duplicate_items=2
    )

    # 验证自动计算的统计
    assert result.total_items == 5
    assert result.execution_time > 0
    assert result.success == True

    # 验证成功率
    result.error_items = 1
    success_rate = result.success_rate
    assert success_rate == 0.8  # (5-1)/5 = 0.8

    # 测试添加警告
    result.add_warning("测试警告")
    assert len(result.warnings) == 1
    assert "测试警告" in result.warnings

    # 测试设置错误
    result.set_error("测试错误")
    assert result.status == ScrapingStatus.FAILURE
    assert result.error_message == "测试错误"
    assert result.success == False

    # 测试结果摘要
    summary = result.get_summary()
    expected_keys = [
        'scraper_name', 'status', 'success', 'total_items',
        'new_items', 'duplicate_items', 'error_items',
        'success_rate', 'execution_time', 'has_errors', 'warnings_count'
    ]

    for key in expected_keys:
        assert key in summary

    assert summary['scraper_name'] == "test_scraper"
    assert summary['total_items'] == 5
    assert summary['warnings_count'] == 1

def test_scraping_result_status_enum(self):
    """测试抓取结果状态枚举"""

    # 测试所有状态
    success_result = ScrapingResult(
        scraper_name="test",
        status=ScrapingStatus.SUCCESS,
        items=[]
    )
    assert success_result.success == True

    partial_result = ScrapingResult(
        scraper_name="test",
        status=ScrapingStatus.PARTIAL_SUCCESS,
        items=[]
    )
    assert partial_result.success == True

    failure_result = ScrapingResult(
        scraper_name="test",
        status=ScrapingStatus.FAILURE,
        items=[]
    )
    assert failure_result.success == False

    timeout_result = ScrapingResult(
        scraper_name="test",
        status=ScrapingStatus.TIMEOUT,
        items=[]
    )
    assert timeout_result.success == False
```

### TaskModel 生命周期测试

```python
def test_task_model_lifecycle(self):
    """测试任务模型生命周期"""

    # 创建任务
    task = TaskModel(
        task_id="test-task-001",
        task_type="scraper",
        priority=TaskPriority.HIGH,
        max_retries=3
    )

    # 验证初始状态
    assert task.task_id == "test-task-001"
    assert task.status == TaskStatus.PENDING
    assert task.priority == TaskPriority.HIGH
    assert task.is_running == False
    assert task.is_completed == False
    assert task.can_retry == False

    # 开始执行
    task.start_execution()
    assert task.status == TaskStatus.RUNNING
    assert task.start_time is not None
    assert task.is_running == True
    assert task.is_completed == False

    # 模拟执行时间
    time.sleep(0.1)

    # 成功完成
    result_data = {"items_processed": 10}
    task.complete_execution(result_data)

    assert task.status == TaskStatus.COMPLETED
    assert task.end_time is not None
    assert task.result_data == result_data
    assert task.execution_time > 0
    assert task.is_running == False
    assert task.is_completed == True

    # 验证执行时间计算
    expected_time = (task.end_time - task.start_time).total_seconds()
    assert abs(task.execution_time - expected_time) < 0.01

def test_task_model_failure_and_retry(self):
    """测试任务失败和重试"""

    task = TaskModel(
        task_id="retry-task",
        task_type="scraper",
        max_retries=2
    )

    # 开始执行
    task.start_execution()

    # 失败
    error_msg = "网络连接失败"
    traceback_info = "Traceback (most recent call last)..."
    task.fail_execution(error_msg, traceback_info)

    assert task.status == TaskStatus.FAILED
    assert task.error_message == error_msg
    assert task.error_traceback == traceback_info
    assert task.can_retry == True  # 还可以重试

    # 增加重试次数
    task.increment_retry()
    assert task.retry_count == 1
    assert task.status == TaskStatus.PENDING
    assert task.error_message is None
    assert task.can_retry == True

    # 再次失败
    task.start_execution()
    task.fail_execution("第二次失败")
    task.increment_retry()
    assert task.retry_count == 2

    # 第三次失败（达到最大重试次数）
    task.start_execution()
    task.fail_execution("第三次失败")
    assert task.can_retry == False  # 不能再重试

def test_task_model_cancellation(self):
    """测试任务取消"""

    task = TaskModel(
        task_id="cancel-task",
        task_type="scraper"
    )

    task.start_execution()
    time.sleep(0.1)

    # 取消任务
    reason = "用户请求取消"
    task.cancel_execution(reason)

    assert task.status == TaskStatus.CANCELLED
    assert task.end_time is not None
    assert f"Cancelled: {reason}" in task.error_message
    assert task.is_completed == True
```

### 调度器模型测试

```python
class TestScheduleModel:
    """调度模型测试"""

    def test_schedule_model_creation(self):
        """测试调度模型创建"""

        schedule = ScheduleModel(
            schedule_id="test-schedule-001",
            name="每日数据抓取",
            description="每天凌晨2点执行数据抓取任务",
            cron_expression="0 2 * * *",
            scraper_config={
                "name": "daily_scraper",
                "url": "https://example.com/api/data",
                "timeout": 30
            }
        )

        assert schedule.schedule_id == "test-schedule-001"
        assert schedule.name == "每日数据抓取"
        assert schedule.cron_expression == "0 2 * * *"
        assert schedule.is_enabled == True  # 默认启用
        assert schedule.created_at is not None
        assert schedule.updated_at is not None
        assert schedule.next_run is None  # 未计算

    def test_schedule_model_validation(self):
        """测试调度模型验证"""

        # 测试有效的cron表达式
        valid_expressions = [
            "0 2 * * *",       # 每天2点
            "*/15 * * * *",    # 每15分钟
            "0 0 1 * *",       # 每月1号
            "0 9-17 * * 1-5"   # 工作日9-17点
        ]

        for expr in valid_expressions:
            schedule = ScheduleModel(
                schedule_id=f"test-{expr.replace(' ', '-').replace('*', 'x')}",
                name="测试调度",
                cron_expression=expr
            )
            # 应该成功创建，不抛出异常
            assert schedule.is_valid_cron()

        # 测试无效的cron表达式
        invalid_expressions = [
            "invalid",
            "60 * * * *",      # 分钟超出范围
            "* 25 * * *",      # 小时超出范围
            "* * 32 * *",      # 日期超出范围
            "* * * 13 *"       # 月份超出范围
        ]

        for expr in invalid_expressions:
            try:
                schedule = ScheduleModel(
                    schedule_id=f"invalid-{expr}",
                    name="无效调度",
                    cron_expression=expr
                )
                assert not schedule.is_valid_cron()
            except ValueError:
                # 预期的验证错误
                pass

    def test_schedule_model_lifecycle(self):
        """测试调度模型生命周期"""

        schedule = ScheduleModel(
            schedule_id="lifecycle-test",
            name="生命周期测试",
            cron_expression="0 * * * *"  # 每小时
        )

        # 初始状态
        assert schedule.is_enabled == True
        assert schedule.last_run is None
        assert schedule.run_count == 0

        # 禁用调度
        schedule.disable()
        assert schedule.is_enabled == False

        # 启用调度
        schedule.enable()
        assert schedule.is_enabled == True

        # 更新下次运行时间
        next_time = datetime.now() + timedelta(hours=1)
        schedule.update_next_run(next_time)
        assert schedule.next_run == next_time

        # 记录执行
        start_time = datetime.now()
        schedule.record_execution(start_time, True)
        assert schedule.last_run == start_time
        assert schedule.run_count == 1
        assert schedule.success_count == 1
        assert schedule.failure_count == 0

        # 记录失败执行
        fail_time = datetime.now()
        schedule.record_execution(fail_time, False, "网络错误")
        assert schedule.last_run == fail_time
        assert schedule.run_count == 2
        assert schedule.success_count == 1
        assert schedule.failure_count == 1
        assert schedule.last_error == "网络错误"

    def test_schedule_model_statistics(self):
        """测试调度模型统计"""

        schedule = ScheduleModel(
            schedule_id="stats-test",
            name="统计测试",
            cron_expression="*/5 * * * *"
        )

        # 模拟多次执行
        base_time = datetime.now()
        for i in range(10):
            run_time = base_time + timedelta(minutes=i*5)
            success = i % 3 != 0  # 每3次失败1次
            error = None if success else f"错误 {i}"
            schedule.record_execution(run_time, success, error)

        # 验证统计
        assert schedule.run_count == 10
        assert schedule.success_count == 7
        assert schedule.failure_count == 3
        assert schedule.success_rate == 0.7

        # 获取统计摘要
        stats = schedule.get_statistics()
        expected_keys = [
            'schedule_id', 'name', 'is_enabled', 'run_count',
            'success_count', 'failure_count', 'success_rate',
            'last_run', 'next_run', 'last_error'
        ]
        for key in expected_keys:
            assert key in stats

class TestSchedulerStatus:
    """调度器状态测试"""

    def test_scheduler_status_creation(self):
        """测试调度器状态创建"""

        status = SchedulerStatus(
            is_running=True,
            start_time=datetime.now(),
            total_schedules=5,
            active_schedules=3,
            pending_tasks=2
        )

        assert status.is_running == True
        assert status.total_schedules == 5
        assert status.active_schedules == 3
        assert status.pending_tasks == 2
        assert status.uptime_seconds >= 0
        assert status.created_at is not None

    def test_scheduler_status_uptime_calculation(self):
        """测试调度器运行时间计算"""

        start_time = datetime.now() - timedelta(hours=2, minutes=30)
        status = SchedulerStatus(
            is_running=True,
            start_time=start_time,
            total_schedules=3
        )

        # 运行时间应该大约是2.5小时
        uptime_hours = status.uptime_seconds / 3600
        assert 2.4 < uptime_hours < 2.6

        # 测试停止状态
        status.is_running = False
        status.stop_time = datetime.now()
        assert status.uptime_seconds > 0

    def test_scheduler_status_statistics_update(self):
        """测试调度器状态统计更新"""

        status = SchedulerStatus(
            is_running=True,
            start_time=datetime.now(),
            total_schedules=0
        )

        # 添加调度
        status.add_schedule()
        assert status.total_schedules == 1
        assert status.active_schedules == 0  # 需要手动激活

        # 激活调度
        status.activate_schedule()
        assert status.active_schedules == 1

        # 添加待处理任务
        status.add_pending_task()
        status.add_pending_task()
        assert status.pending_tasks == 2

        # 完成任务
        status.complete_task()
        assert status.pending_tasks == 1
        assert status.completed_tasks == 1

        # 移除调度
        status.remove_schedule()
        assert status.total_schedules == 0
        assert status.active_schedules == 0

    def test_scheduler_status_performance_metrics(self):
        """测试调度器性能指标"""

        status = SchedulerStatus(
            is_running=True,
            start_time=datetime.now(),
            total_schedules=10,
            active_schedules=8,
            completed_tasks=100,
            failed_tasks=5
        )

        # 计算成功率
        success_rate = status.get_success_rate()
        assert success_rate == 0.95  # 100/(100+5)

        # 计算平均任务执行时间（如果有执行时间数据）
        execution_times = [1.2, 2.1, 0.8, 1.5, 3.0]
        status.add_execution_times(execution_times)
        avg_time = status.get_average_execution_time()
        assert abs(avg_time - 1.72) < 0.01  # 平均值

        # 获取性能摘要
        metrics = status.get_performance_metrics()
        expected_keys = [
            'success_rate', 'average_execution_time', 'tasks_per_hour',
            'active_schedule_ratio', 'uptime_hours'
        ]
        for key in expected_keys:
            assert key in metrics

    def test_scheduler_status_health_check(self):
        """测试调度器健康检查"""

        # 健康状态
        healthy_status = SchedulerStatus(
            is_running=True,
            start_time=datetime.now() - timedelta(hours=1),
            total_schedules=5,
            active_schedules=5,
            failed_tasks=0
        )

        health = healthy_status.get_health_status()
        assert health['status'] == 'healthy'
        assert health['issues'] == []

        # 不健康状态
        unhealthy_status = SchedulerStatus(
            is_running=False,
            start_time=datetime.now() - timedelta(hours=1),
            total_schedules=5,
            active_schedules=0,
            failed_tasks=10
        )

        health = unhealthy_status.get_health_status()
        assert health['status'] == 'unhealthy'
        assert len(health['issues']) > 0
        assert any('停止运行' in issue for issue in health['issues'])
```

### 响应模型测试

```python
class TestResponseModels:
    """响应模型测试"""

    def test_admin_response_success(self):
        """测试成功响应"""

        data = {"items": 10, "status": "completed"}
        response = AdminResponse.success_response(
            data=data,
            message="操作成功",
            stats={"execution_time": 2.5}
        )

        assert response.success == True
        assert response.message == "操作成功"
        assert response.data == data
        assert response.stats["execution_time"] == 2.5
        assert len(response.errors) == 0
        assert response.timestamp is not None

    def test_admin_response_error(self):
        """测试错误响应"""

        errors = ["配置错误", "网络异常"]
        response = AdminResponse.error_response(
            message="操作失败",
            errors=errors
        )

        assert response.success == False
        assert response.message == "操作失败"
        assert response.errors == errors
        assert response.data is None

    def test_admin_response_add_error(self):
        """测试添加错误"""

        response = AdminResponse.success_response(data={})
        assert response.success == True

        response.add_error("新增错误")
        assert response.success == False
        assert "新增错误" in response.errors
        assert response.message != ""

    def test_error_response_from_exception(self):
        """测试从异常创建错误响应"""

        try:
            raise ValueError("测试异常")
        except Exception as e:
            error_response = ErrorResponse.from_exception(
                e,
                context={"operation": "test"}
            )

            assert error_response.error_code == "ValueError"
            assert error_response.error_message == "测试异常"
            assert error_response.error_type == "exception"
            assert error_response.traceback is not None
            assert error_response.context["operation"] == "test"

    def test_error_response_suggestions(self):
        """测试错误响应建议"""

        error_response = ErrorResponse(
            error_code="CONFIG_ERROR",
            error_message="配置文件格式错误"
        )

        error_response.add_suggestion("检查配置文件语法")
        error_response.add_suggestion("参考示例配置")

        assert len(error_response.suggestions) == 2
        assert "检查配置文件语法" in error_response.suggestions
```

### 统计模型测试

```python
class TestStatisticsModels:
    """统计模型测试"""

    def test_task_statistics_calculation(self):
        """测试任务统计计算"""

        # 创建测试任务
        tasks = [
            TaskModel(task_id="1", task_type="scraper", status=TaskStatus.COMPLETED, execution_time=1.0),
            TaskModel(task_id="2", task_type="scraper", status=TaskStatus.COMPLETED, execution_time=2.0),
            TaskModel(task_id="3", task_type="scraper", status=TaskStatus.FAILED),
            TaskModel(task_id="4", task_type="scraper", status=TaskStatus.PENDING),
            TaskModel(task_id="5", task_type="scraper", status=TaskStatus.RUNNING),
        ]

        stats = TaskStatistics()
        stats.update_from_tasks(tasks)

        assert stats.total_tasks == 5
        assert stats.completed_tasks == 2
        assert stats.failed_tasks == 1
        assert stats.pending_tasks == 1
        assert stats.running_tasks == 1
        assert stats.active_tasks == 2

        # 验证性能统计
        assert stats.average_execution_time == 1.5  # (1.0 + 2.0) / 2
        assert stats.total_execution_time == 3.0

        # 验证成功率
        assert stats.success_rate == 66.67  # 2/(2+1) * 100，四舍五入

    def test_scraper_statistics_update(self):
        """测试抓取器统计更新"""

        stats = ScraperStatistics(
            scraper_name="test_scraper",
            scraper_type="direct_rss"
        )

        # 第一次成功运行
        success_result = ScrapingResult(
            scraper_name="test_scraper",
            status=ScrapingStatus.SUCCESS,
            items=[ScrapingItem(title="Item 1", url="https://example.com/1")],
            execution_time=1.5,
            new_items=1
        )

        stats.update_from_result(success_result)

        assert stats.total_runs == 1
        assert stats.successful_runs == 1
        assert stats.failed_runs == 0
        assert stats.total_items_scraped == 1
        assert stats.total_new_items == 1
        assert stats.average_execution_time == 1.5
        assert stats.success_rate == 100.0
        assert stats.last_success_time is not None

        # 第二次失败运行
        failure_result = ScrapingResult(
            scraper_name="test_scraper",
            status=ScrapingStatus.FAILURE,
            items=[],
            execution_time=0.5,
            error_message="网络错误"
        )

        stats.update_from_result(failure_result)

        assert stats.total_runs == 2
        assert stats.successful_runs == 1
        assert stats.failed_runs == 1
        assert stats.error_count == 1
        assert stats.last_error == "网络错误"
        assert stats.success_rate == 50.0
        assert stats.average_execution_time == 1.0  # (1.5 + 0.5) / 2

        # 验证平均项目数
        assert stats.average_items_per_run == 1.0  # 1/1
```

## 序列化和数据转换测试

### 序列化测试

```python
class TestSerialization:
    """序列化测试"""

    def test_complex_model_serialization(self):
        """测试复杂模型序列化"""

        # 创建复杂的嵌套数据
        items = [
            ScrapingItem(
                title=f"Article {i}",
                url=f"https://example.com/{i}",
                published_date=datetime.now(),
                tags=["tag1", "tag2"]
            )
            for i in range(3)
        ]

        result = ScrapingResult(
            scraper_name="complex_scraper",
            status=ScrapingStatus.SUCCESS,
            items=items,
            start_time=datetime.now(),
            end_time=datetime.now()
        )

        # 转换为字典
        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert result_dict['scraper_name'] == "complex_scraper"
        assert result_dict['status'] == ScrapingStatus.SUCCESS.value
        assert len(result_dict['items']) == 3
        assert isinstance(result_dict['items'][0], dict)

        # 验证日期时间序列化
        assert isinstance(result_dict['start_time'], str)
        assert 'T' in result_dict['start_time']  # ISO format

        # 转换为 JSON
        result_json = result.to_json()

        assert isinstance(result_json, str)
        assert "complex_scraper" in result_json

        # 验证可以解析
        import json
        parsed = json.loads(result_json)
        assert parsed['scraper_name'] == "complex_scraper"

    def test_database_serialization(self):
        """测试数据库序列化格式"""

        item = ScrapingItem(
            title="Database Test",
            url="https://example.com/db",
            tags=["db", "test", "serialization"],
            published_date=datetime(2023, 11, 15, 10, 30, 0)
        )

        # 转换为数据库格式
        db_dict = item.to_database_dict()

        assert isinstance(db_dict['tags'], str)
        assert db_dict['tags'] == "db,test,serialization"
        assert isinstance(db_dict['published_date'], (int, float))

        # 从数据库格式恢复
        restored_item = ScrapingItem.from_database_dict(db_dict)

        assert restored_item.title == item.title
        assert restored_item.tags == item.tags
        assert isinstance(restored_item.published_date, datetime)
        assert restored_item.published_date == item.published_date
```

## 数据验证测试

### 验证混入测试

```python
class TestValidationMixin:
    """验证混入测试"""

    def test_url_validation(self):
        """测试 URL 验证"""

        class TestModel(BaseModel, ValidationMixin):
            def __init__(self, url: str):
                super().__init__()
                self.url = url

        # 有效 URL
        valid_urls = [
            "https://example.com",
            "http://localhost:8080",
            "https://sub.domain.co.uk/path?param=value",
            "http://192.168.1.1:3000"
        ]

        for url in valid_urls:
            model = TestModel(url)
            assert model.validate_url(url) == True

        # 无效 URL
        invalid_urls = [
            "not-a-url",
            "ftp://example.com",
            "https://",
            "http://",
            "example.com"  # 缺少协议
        ]

        for url in invalid_urls:
            model = TestModel(url)
            assert model.validate_url(url) == False

    def test_required_fields_validation(self):
        """测试必需字段验证"""

        class TestModel(BaseModel, ValidationMixin):
            def __init__(self, title=None, url=None, content=None):
                super().__init__()
                self.title = title
                self.url = url
                self.content = content

        # 完整模型
        complete_model = TestModel(title="Test", url="https://example.com", content="Content")
        missing = complete_model.validate_required_fields(['title', 'url'])
        assert len(missing) == 0

        # 缺少字段的模型
        incomplete_model = TestModel(title="Test")
        missing = incomplete_model.validate_required_fields(['title', 'url', 'content'])
        assert len(missing) == 2
        assert 'url' in missing
        assert 'content' in missing
        assert 'title' not in missing

    def test_custom_validators(self):
        """测试自定义验证器"""

        def min_length_validator(value, min_len=5):
            return len(str(value)) >= min_len

        def max_length_validator(value, max_len=100):
            return len(str(value)) <= max_len

        class TestModel(BaseModel, ValidationMixin):
            def __init__(self, title: str):
                super().__init__()
                self.title = title

        model = TestModel("Valid Title")

        # 通过验证
        assert model.validate_field(
            'title',
            model.title,
            [
                lambda x: min_length_validator(x, 5),
                lambda x: max_length_validator(x, 50)
            ]
        ) == True

        # 验证失败
        short_model = TestModel("Hi")
        assert short_model.validate_field(
            'title',
            short_model.title,
            [lambda x: min_length_validator(x, 5)]
        ) == False
```

## 性能测试

### 大量数据测试

```python
def test_large_dataset_performance():
    """测试大量数据性能"""

    import time

    # 创建大量项目
    start_time = time.time()

    items = []
    for i in range(1000):
        item = ScrapingItem(
            title=f"Article {i}",
            url=f"https://example.com/article/{i}",
            content=f"This is the content for article {i}. " * 50,
            tags=[f"tag{j}" for j in range(5)],
            published_date=datetime.now()
        )
        items.append(item)

    creation_time = time.time() - start_time
    print(f"Created 1000 items in {creation_time:.2f} seconds")

    # 创建大型结果
    start_time = time.time()

    result = ScrapingResult(
        scraper_name="performance_test",
        status=ScrapingStatus.SUCCESS,
        items=items
    )

    result_creation_time = time.time() - start_time
    print(f"Created result with 1000 items in {result_creation_time:.2f} seconds")

    # 序列化性能
    start_time = time.time()
    result_dict = result.to_dict()
    serialization_time = time.time() - start_time
    print(f"Serialized to dict in {serialization_time:.2f} seconds")

    start_time = time.time()
    result_json = result.to_json()
    json_time = time.time() - start_time
    print(f"Serialized to JSON in {json_time:.2f} seconds")

    # 性能断言
    assert creation_time < 5.0  # 5秒内创建1000个项目
    assert serialization_time < 2.0  # 2秒内序列化
    assert json_time < 3.0  # 3秒内转换为JSON

def test_memory_usage():
    """测试内存使用"""

    import psutil
    import os

    process = psutil.Process(os.getpid())

    # 记录初始内存
    initial_memory = process.memory_info().rss

    # 创建大量对象
    results = []
    for i in range(100):
        items = [
            ScrapingItem(title=f"Item {j}", url=f"https://example.com/{j}")
            for j in range(100)
        ]

        result = ScrapingResult(
            scraper_name=f"scraper_{i}",
            status=ScrapingStatus.SUCCESS,
            items=items
        )
        results.append(result)

    # 记录峰值内存
    peak_memory = process.memory_info().rss
    memory_increase = peak_memory - initial_memory

    print(f"Memory increase: {memory_increase / 1024 / 1024:.2f} MB")

    # 清理对象
    del results
    import gc
    gc.collect()

    # 记录清理后内存
    final_memory = process.memory_info().rss
    print(f"Memory after cleanup: {(final_memory - initial_memory) / 1024 / 1024:.2f} MB")

    # 内存使用应该在合理范围内 (100MB)
    assert memory_increase < 100 * 1024 * 1024
```

## Mock 和 Fixture

### 通用 Fixture

```python
@pytest.fixture
def sample_scraping_item():
    """示例抓取项目"""
    return ScrapingItem(
        title="Sample Article",
        url="https://example.com/article",
        content="This is a sample article content.",
        author="Sample Author",
        tags=["sample", "test"],
        published_date=datetime(2023, 11, 15, 10, 30, 0)
    )

@pytest.fixture
def sample_scraping_result(sample_scraping_item):
    """示例抓取结果"""
    return ScrapingResult(
        scraper_name="sample_scraper",
        status=ScrapingStatus.SUCCESS,
        items=[sample_scraping_item],
        execution_time=1.5
    )

@pytest.fixture
def sample_task_model():
    """示例任务模型"""
    return TaskModel(
        task_id="sample-task-001",
        task_type="scraper",
        priority=TaskPriority.NORMAL
    )

@pytest.fixture
def multiple_tasks():
    """多个任务实例"""
    return [
        TaskModel(task_id=f"task-{i}", task_type="scraper",
                 status=TaskStatus.COMPLETED if i % 2 == 0 else TaskStatus.FAILED)
        for i in range(10)
    ]
```

### Mock 工具

```python
def create_mock_scraping_items(count: int) -> List[ScrapingItem]:
    """创建模拟抓取项目"""
    return [
        ScrapingItem(
            title=f"Mock Article {i}",
            url=f"https://example.com/mock/{i}",
            content=f"Mock content for article {i}",
            tags=[f"tag{i}", "mock"]
        )
        for i in range(count)
    ]

def create_mock_task_with_status(status: TaskStatus) -> TaskModel:
    """创建指定状态的模拟任务"""
    task = TaskModel(
        task_id=f"mock-{status.value}",
        task_type="mock",
        status=status
    )

    if status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
        task.start_time = datetime.now() - timedelta(seconds=10)
        task.end_time = datetime.now()
        task.execution_time = 10.0

    return task
```

## 测试运行

### 运行所有模型测试

```bash
# 运行所有服务模型测试
poetry run pytest tests/octopus_scraper/service_models_test.py -v

# 运行特定模型测试
poetry run pytest tests/octopus_scraper/models/validation_test.py -v
poetry run pytest tests/octopus_scraper/models/serialization_test.py -v

# 运行性能测试
poetry run pytest tests/octopus_scraper/models/performance_test.py -v
```

### 运行覆盖率测试

```bash
# 运行带覆盖率的测试
poetry run pytest tests/octopus_scraper/service_models_test.py \
  --cov=src/octopus_scraper/service_models \
  --cov-report=html \
  --cov-report=term

# 查看覆盖率报告
open htmlcov/index.html
```

### 运行特定类型测试

```bash
# 运行验证测试
poetry run pytest -k "validation" -v

# 运行序列化测试
poetry run pytest -k "serialization" -v

# 运行性能测试
poetry run pytest -k "performance" -v
```

## 故障排除

### 常见测试问题

1. **时间敏感测试**
   ```python
   # 使用时间容差
   time_diff = abs(actual_time - expected_time)
   assert time_diff < timedelta(seconds=1)
   ```

2. **浮点数比较**
   ```python
   # 使用近似比较
   assert abs(actual_value - expected_value) < 0.01
   ```

3. **内存泄漏检测**
   ```python
   # 确保清理测试数据
   del large_objects
   import gc
   gc.collect()
   ```

## 测试最佳实践

1. **数据隔离**: 每个测试使用独立的测试数据
2. **边界测试**: 测试边界条件和异常情况
3. **性能监控**: 包含性能和内存使用测试
4. **验证覆盖**: 测试所有验证逻辑
5. **序列化测试**: 确保数据正确序列化和反序列化
6. **向后兼容**: 测试模型版本兼容性

## 相关文档

- [Service Models](./service-models.md)
- [ConfigManager Testing](../config/config-manager-testing.md)
- [TaskManager Testing](../task_manager/task-manager-testing.md)
- [Scrapers Testing](../scrapers/scrapers-testing.md)
