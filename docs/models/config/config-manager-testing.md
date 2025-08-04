# ConfigManager 测试文档

## 概述

ConfigManager 组件的测试覆盖了配置加载、热重载、文件监控、错误处理等核心功能。

## 测试文件位置

- **主测试文件**: `tests/octopus_scraper/config_manager_test.py`
- **集成测试**: `tests/octopus_scraper/config_integration_test.py`
- **Web 服务测试**: `tests/octopus_scraper/octopus_service_test.py` (配置相关部分)

## 测试结构

### 单元测试

#### 测试类: `TestConfigManager`

```python
class TestConfigManager:
    """ConfigManager 核心功能测试"""

    def test_init_with_file_path(self):
        """测试使用文件路径初始化"""

    def test_init_with_notion_config(self):
        """测试使用 Notion 配置初始化"""

    async def test_load_config_from_file(self):
        """测试从文件加载配置"""

    async def test_load_config_from_notion(self):
        """测试从 Notion 加载配置"""

    async def test_reload_config_with_changes(self):
        """测试配置变更时的重载"""

    async def test_reload_config_no_changes(self):
        """测试无变更时的重载"""

    def test_get_scrapers_config(self):
        """测试获取抓取器配置"""

    def test_get_service_config(self):
        """测试获取服务配置"""

    def test_is_config_healthy(self):
        """测试配置健康状态检查"""

    def test_get_scheduler_config(self):
        """测试获取调度器配置"""

    def test_scheduler_environment_variables(self):
        """测试调度器环境变量配置"""

    def test_scheduler_config_validation(self):
        """测试调度器配置验证"""
```

#### 测试类: `TestConfigVersion`

```python
class TestConfigVersion:
    """配置版本管理测试"""

    def test_create_version(self):
        """测试创建配置版本"""

    def test_version_comparison(self):
        """测试版本比较"""

    def test_version_serialization(self):
        """测试版本序列化"""
```

#### 测试类: `TestNotionConfig`

```python
class TestNotionConfig:
    """Notion 配置测试"""

    def test_create_from_env(self):
        """测试从环境变量创建配置"""

    def test_validate_config(self):
        """测试配置验证"""

    def test_api_key_security(self):
        """测试 API 密钥安全性"""
```

### 集成测试

#### 测试类: `TestConfigIntegration`

```python
class TestConfigIntegration:
    """配置管理集成测试"""

    async def test_file_watcher_integration(self):
        """测试文件监控集成"""

    async def test_notion_api_integration(self):
        """测试 Notion API 集成"""

    async def test_config_reload_in_service(self):
        """测试服务中的配置重载"""

    async def test_error_recovery(self):
        """测试错误恢复机制"""
```

## 测试用例详解

### 配置加载测试

```python
async def test_load_config_from_file(self):
    """测试从 YAML 文件加载配置"""

    # 准备测试配置文件
    config_data = {
        'scrapers_config_with_fetch_params': [
            {
                'scraper_config': {
                    'fetcher_name': 'rsshub',
                    'fetcher_config': {
                        'hub_root': 'https://rsshub.app',
                        'route': '/test'
                    }
                },
                'fetch_params': {'limit': 10}
            }
        ],
        'service': {
            'host': '0.0.0.0',
            'port': 8000
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        yaml.dump(config_data, f)
        config_file = f.name

    try:
        config_manager = ConfigManager(config_file_path=config_file)
        result = await config_manager.load_config()

        assert result is True
        assert len(config_manager.get_scrapers_config()) == 1
        assert config_manager.get_service_config().port == 8000
    finally:
        os.unlink(config_file)
```

### 热重载测试

```python
async def test_config_hot_reload(self):
    """测试配置热重载功能"""

    # 创建初始配置
    initial_config = {'service': {'port': 8000}}
    updated_config = {'service': {'port': 8080}}

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        yaml.dump(initial_config, f)
        config_file = f.name

    try:
        config_manager = ConfigManager(config_file_path=config_file)
        await config_manager.load_config()

        # 验证初始配置
        assert config_manager.get_service_config().port == 8000

        # 更新配置文件
        with open(config_file, 'w') as f:
            yaml.dump(updated_config, f)

        # 触发重载
        config_changed, message = await config_manager.reload_config()

        assert config_changed is True
        assert config_manager.get_service_config().port == 8080
        assert "Configuration reloaded" in message
    finally:
        os.unlink(config_file)
```

### 调度器配置测试

```python
def test_get_scheduler_config(self):
    """测试获取调度器配置"""

    # 准备包含调度器配置的测试数据
    config_data = {
        'scheduler': {
            'enabled': True,
            'auto_start': True,
            'max_concurrent_schedules': 5,
            'check_interval': 30
        },
        'service': {'port': 8000}
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        yaml.dump(config_data, f)
        config_file = f.name

    try:
        config_manager = ConfigManager(config_file_path=config_file)
        scheduler_config = config_manager.get_scheduler_config()

        assert scheduler_config.enabled == True
        assert scheduler_config.auto_start == True
        assert scheduler_config.max_concurrent_schedules == 5
        assert scheduler_config.check_interval == 30
    finally:
        os.unlink(config_file)

def test_scheduler_environment_variables(self):
    """测试调度器环境变量配置"""

    # 设置环境变量
    test_env = {
        'ENABLE_SCHEDULER': 'true',
        'AUTO_START_SCHEDULER': 'false',
        'MAX_CONCURRENT_SCHEDULES': '10',
        'SCHEDULE_CHECK_INTERVAL': '60'
    }

    with patch.dict(os.environ, test_env):
        config_manager = ConfigManager()
        scheduler_config = config_manager.get_scheduler_config_from_env()

        assert scheduler_config.enabled == True
        assert scheduler_config.auto_start == False
        assert scheduler_config.max_concurrent_schedules == 10
        assert scheduler_config.check_interval == 60

def test_scheduler_config_validation(self):
    """测试调度器配置验证"""

    # 测试有效配置
    valid_config = {
        'enabled': True,
        'auto_start': True,
        'max_concurrent_schedules': 3,
        'check_interval': 30
    }

    config_manager = ConfigManager()
    assert config_manager.validate_scheduler_config(valid_config) == True

    # 测试无效配置
    invalid_configs = [
        {'max_concurrent_schedules': 0},      # 并发数不能为0
        {'check_interval': -1},               # 检查间隔不能为负数
        {'enabled': 'invalid'},               # enabled必须是布尔值
        {'max_concurrent_schedules': 'abc'}   # 并发数必须是整数
    ]

    for invalid_config in invalid_configs:
        assert config_manager.validate_scheduler_config(invalid_config) == False

async def test_scheduler_config_reload(self):
    """测试调度器配置重载"""

    # 初始配置 - 调度器禁用
    initial_config = {
        'scheduler': {'enabled': False},
        'service': {'port': 8000}
    }

    # 更新配置 - 启用调度器
    updated_config = {
        'scheduler': {
            'enabled': True,
            'auto_start': True,
            'max_concurrent_schedules': 5
        },
        'service': {'port': 8000}
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        yaml.dump(initial_config, f)
        config_file = f.name

    try:
        config_manager = ConfigManager(config_file_path=config_file)
        await config_manager.load_config()

        # 验证初始调度器配置
        scheduler_config = config_manager.get_scheduler_config()
        assert scheduler_config.enabled == False

        # 更新配置文件
        with open(config_file, 'w') as f:
            yaml.dump(updated_config, f)

        # 重载配置
        config_changed, message = await config_manager.reload_config()

        # 验证调度器配置已更新
        updated_scheduler_config = config_manager.get_scheduler_config()
        assert config_changed == True
        assert updated_scheduler_config.enabled == True
        assert updated_scheduler_config.auto_start == True
        assert updated_scheduler_config.max_concurrent_schedules == 5

    finally:
        os.unlink(config_file)
```

### 错误处理测试

```python
async def test_invalid_config_handling(self):
    """测试无效配置的处理"""

    # 创建无效配置
    invalid_config = {
        'invalid_key': 'invalid_value'
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        yaml.dump(invalid_config, f)
        config_file = f.name

    try:
        config_manager = ConfigManager(config_file_path=config_file)

        with pytest.raises(ConfigurationError):
            await config_manager.load_config()
    finally:
        os.unlink(config_file)
```

### Notion 集成测试

```python
async def test_notion_config_loading(self):
    """测试从 Notion 加载配置"""

    # Mock Notion API
    with patch('octopus_scraper.config.notion_api.NotionAPI') as mock_notion:
        mock_notion.return_value.query_database.return_value = {
            'results': [
                {
                    'properties': {
                        'Name': {'title': [{'text': {'content': 'test_scraper'}}]},
                        'Status': {'select': {'name': 'Active'}},
                        'Fetcher': {'select': {'name': 'rsshub'}},
                        'Hub Root': {'url': 'https://rsshub.app'},
                        'Route': {'rich_text': [{'text': {'content': '/test'}}]}
                    }
                }
            ]
        }

        notion_config = NotionConfig(
            api_key="test_key",
            scrapers_database_id="test_db_id"
        )

        config_manager = ConfigManager(notion_config=notion_config)
        result = await config_manager.load_config()

        assert result is True
        scrapers = config_manager.get_scrapers_config()
        assert len(scrapers) == 1
        assert scrapers[0].name == 'test_scraper'
```

## Web 服务集成测试

### 管理接口测试

位置: `tests/octopus_scraper/octopus_service_test.py`

```python
class TestConfigEndpoints:
    """配置管理 API 端点测试"""

    async def test_get_config_status_success(self):
        """测试获取配置状态"""

    async def test_refresh_config_success(self):
        """测试刷新配置"""

    async def test_validate_config_success(self):
        """测试验证配置"""

    async def test_hotreload_config_success(self):
        """测试热重载配置"""

    async def test_config_watcher_management(self):
        """测试配置监控管理"""
```

## Mock 和 Fixture

### 通用 Fixture

```python
@pytest.fixture
def mock_config_manager():
    """Mock ConfigManager fixture"""
    manager = Mock(spec=ConfigManager)
    manager.is_config_healthy.return_value = True
    manager.get_service_config.return_value = ServiceConfig()
    manager.get_scrapers_config.return_value = []
    return manager

@pytest.fixture
def sample_config_data():
    """示例配置数据 fixture"""
    return {
        'scrapers_config_with_fetch_params': [
            {
                'scraper_config': {
                    'fetcher_name': 'rsshub',
                    'fetcher_config': {
                        'hub_root': 'https://rsshub.app',
                        'route': '/test'
                    }
                },
                'fetch_params': {'limit': 10}
            }
        ],
        'service': {
            'host': '0.0.0.0',
            'port': 8000,
            'debug': False
        }
    }
```

## 测试运行

### 运行所有 ConfigManager 测试

```bash
# 运行核心配置管理测试
poetry run pytest tests/octopus_scraper/config_manager_test.py -v

# 运行集成测试
poetry run pytest tests/octopus_scraper/config_integration_test.py -v

# 运行 Web 服务配置测试
poetry run pytest tests/octopus_scraper/octopus_service_test.py::TestConfigEndpoints -v
```

### 运行特定测试

```bash
# 测试配置加载
poetry run pytest tests/octopus_scraper/config_manager_test.py::TestConfigManager::test_load_config_from_file -v

# 测试热重载
poetry run pytest tests/octopus_scraper/octopus_service_test.py::TestAdminEndpoints::test_hotreload_config_success -v
```

### 覆盖率测试

```bash
# 生成覆盖率报告
poetry run pytest tests/octopus_scraper/config_manager_test.py --cov=src/octopus_scraper/config --cov-report=html

# 查看覆盖率
open htmlcov/index.html
```

## 测试数据

### 示例配置文件

```yaml
# tests/fixtures/sample_config.yml
scrapers_config_with_fetch_params:
  - scraper_config:
      fetcher_name: "rsshub"
      fetcher_config:
        hub_root: "https://rsshub.app"
        route: "/github/issues/microsoft/vscode"
    fetch_params:
      limit: 20

notion_api_config:
  api_key: "test_api_key"
  database_id: "test_database_id"

service:
  host: "0.0.0.0"
  port: 8000
  debug: false
```

### 环境变量测试

```python
@pytest.fixture
def mock_env_vars(monkeypatch):
    """Mock 环境变量"""
    monkeypatch.setenv("NOTION_API_KEY", "test_key")
    monkeypatch.setenv("NOTION_CONTENT_DATABASE_ID", "test_db_id")
    monkeypatch.setenv("SERVICE_PORT", "8080")
```

## 性能测试

### 配置加载性能

```python
def test_config_loading_performance(benchmark):
    """测试配置加载性能"""

    def load_config():
        config_manager = ConfigManager(config_file_path="test_config.yml")
        asyncio.run(config_manager.load_config())

    result = benchmark(load_config)
    assert result is not None
```

### 内存使用测试

```python
def test_config_memory_usage():
    """测试配置管理内存使用"""

    import psutil
    import os

    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss

    # 加载大量配置
    config_manager = ConfigManager()
    for i in range(1000):
        asyncio.run(config_manager.load_config())

    final_memory = process.memory_info().rss
    memory_increase = final_memory - initial_memory

    # 内存增长应该在合理范围内
    assert memory_increase < 50 * 1024 * 1024  # 50MB
```

## 故障排除

### 常见测试问题

1. **异步测试失败**
   ```python
   # 确保使用 pytest-asyncio
   @pytest.mark.asyncio
   async def test_async_function():
       result = await async_function()
       assert result is not None
   ```

2. **文件清理问题**
   ```python
   # 使用 try/finally 确保文件清理
   temp_file = None
   try:
       temp_file = create_temp_config()
       # 执行测试
   finally:
       if temp_file:
           os.unlink(temp_file)
   ```

3. **Mock 配置问题**
   ```python
   # 确保 Mock 对象正确配置
   mock_manager = Mock(spec=ConfigManager)
   mock_manager.load_config = AsyncMock(return_value=True)
   ```

## 测试最佳实践

1. **独立性**: 每个测试应该独立运行
2. **清理**: 测试后清理临时文件和资源
3. **覆盖率**: 确保关键路径有测试覆盖
4. **错误场景**: 测试错误和异常情况
5. **性能**: 包含性能和内存使用测试

## 相关文档

- [ConfigManager Models](./config-manager.md)
- [Admin Interface Testing](../../interface/web_service/admin-interface-testing.md)
- [Task Manager Testing](../task_manager/task-manager-testing.md)
