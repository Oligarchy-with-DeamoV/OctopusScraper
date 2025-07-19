# ConfigManager 模型文档

## 概述

ConfigManager 是 OctopusScraper 的核心配置管理组件，负责动态配置加载、热重载、文件监控等功能。

## 核心类

### ConfigManager

位置: `src/octopus_scraper/config/config_manager.py`

#### 主要功能
- **配置加载**: 从 YAML 文件或 Notion 数据库加载配置
- **热重载**: 支持配置文件变更的实时监控和重载
- **版本管理**: 配置版本控制和变更跟踪
- **验证**: 配置有效性验证

#### 核心方法

```python
class ConfigManager:
    def __init__(self, config_file_path: str = None, notion_config: NotionConfig = None)

    async def load_config(self) -> bool
    async def reload_config(self) -> Tuple[bool, str]
    async def start_watcher(self) -> None
    async def stop_watcher(self) -> None

    def get_scrapers_config(self) -> List[ScraperConfig]
    def get_service_config(self) -> ServiceConfig
    def is_config_healthy(self) -> bool
```

#### 配置数据结构

```python
@dataclass
class ServiceConfig:
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    config_refresh_interval: int = 300
    scraper_timeout: int = 300
    upload_timeout: int = 60
    upload_max_retries: int = 3
```

### ConfigVersion

位置: `src/octopus_scraper/config/models.py`

#### 功能
配置版本信息跟踪，用于版本控制和变更历史。

```python
@dataclass
class ConfigVersion:
    version_id: str
    timestamp: datetime
    config_hash: str
    scrapers_count: int
    change_summary: str = ""
```

### NotionConfig

位置: `src/octopus_scraper/config/notion_config.py`

#### 功能
Notion API 配置管理，处理 Notion 数据库的连接和认证。

```python
@dataclass
class NotionConfig:
    api_key: str
    scrapers_database_id: str = ""
    content_database_id: str = ""
```

## 使用示例

### 基本用法

```python
from octopus_scraper.config import ConfigManager, create_config_from_env

# 从环境变量创建配置
config = create_config_from_env()
config_manager = ConfigManager(notion_config=config)

# 加载配置
await config_manager.load_config()

# 获取服务配置
service_config = config_manager.get_service_config()

# 启动文件监控
await config_manager.start_watcher()
```

### 配置热重载

```python
# 手动重载配置
config_changed, message = await config_manager.reload_config()
if config_changed:
    print(f"配置已更新: {message}")

# 检查配置健康状态
if config_manager.is_config_healthy():
    print("配置状态正常")
```

## 配置文件格式

### YAML 配置

```yaml
# 抓取器配置
scrapers_config_with_fetch_params:
  - scraper_config:
      fetcher_name: "rsshub"
      fetcher_config:
        hub_root: "https://rsshub.app"
        route: "/github/issues/microsoft/vscode"
    fetch_params:
      limit: 20

# Notion 配置
notion_api_config:
  api_key: "${NOTION_API_KEY}"
  database_id: "${NOTION_CONTENT_DATABASE_ID}"

# 服务配置
service:
  host: "0.0.0.0"
  port: 8000
  debug: false
```

### 环境变量支持

配置支持以下环境变量：
- `NOTION_API_KEY`: Notion API 密钥
- `NOTION_CONTENT_DATABASE_ID`: Notion 内容数据库 ID
- `NOTION_SCRAPERS_DATABASE_ID`: Notion 抓取器数据库 ID
- `SERVICE_HOST`: 服务监听地址
- `SERVICE_PORT`: 服务端口
- `DEBUG`: 调试模式

## 错误处理

ConfigManager 提供了完善的错误处理机制：

```python
try:
    await config_manager.load_config()
except ConfigurationError as e:
    logger.error(f"配置加载失败: {e}")
except NotionAPIError as e:
    logger.error(f"Notion API 错误: {e}")
```

## 监控和日志

ConfigManager 集成了详细的日志记录：

```python
# 启用详细日志
import logging
logging.getLogger('octopus_scraper.config').setLevel(logging.DEBUG)
```

## 性能特性

- **缓存机制**: 配置数据本地缓存，减少 API 调用
- **增量更新**: 只重载发生变更的配置项
- **异步处理**: 所有 I/O 操作使用异步处理
- **文件监控**: 使用文件系统事件，实时响应配置变更

## 扩展性

ConfigManager 支持插件式扩展：

```python
# 自定义配置来源
class CustomConfigSource:
    async def load_config(self) -> dict:
        # 自定义配置加载逻辑
        pass

# 注册自定义来源
config_manager.register_source(CustomConfigSource())
```

## 最佳实践

1. **环境变量**: 敏感信息使用环境变量
2. **版本控制**: 配置文件纳入版本控制
3. **验证**: 部署前验证配置有效性
4. **监控**: 监控配置加载和更新状态
5. **备份**: 定期备份重要配置

## 相关文档

- [Web Service Admin Interface](../../interface/web_service/admin-interface.md)
- [Task Manager Models](../task_manager/task-manager.md)
- [Service Models](../service/service-models.md)
