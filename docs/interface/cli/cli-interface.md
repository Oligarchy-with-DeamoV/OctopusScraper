# CLI 接口文档

## 概述

OctopusScraper 提供了两个主要的命令行工具：`octopus_go` 用于执行一次性抓取任务，`octopus_service` 用于启动 Web 服务。这些工具适合自动化脚本、定时任务和服务部署使用。

## 可用命令

OctopusScraper 提供以下命令行工具：

```
octopus_go       # 一次性抓取执行
octopus_service  # Web 服务启动
```

## octopus_go - 执行抓取任务

`octopus_go` 命令用于执行一次性的抓取任务，支持配置文件和可选的 Notion 上传功能。

### 语法

```bash
octopus_go --config CONFIG_FILE [--notion_upload]
```

### 选项

- `--config CONFIG_FILE` (必需): 指定 YAML 配置文件路径
- `--notion_upload` (可选): 抓取完成后自动上传到 Notion

### 示例

#### 基本抓取

```bash
# 使用配置文件执行抓取
octopus_go --config config.yml
```

#### 抓取并上传到 Notion

```bash
# 抓取完成后自动上传到 Notion
octopus_go --config config.yml --notion_upload
```

#### 使用不同配置文件

```bash
# 使用生产环境配置
octopus_go --config config.prod.yml --notion_upload

# 使用开发环境配置
octopus_go --config config.dev.yml
```

### 配置文件要求

`octopus_go` 命令需要一个 YAML 配置文件，使用任务管理系统格式：

```yaml
# 抓取器配置（使用任务管理系统格式）
scrapers_config_with_fetch_params:
  - scraper_config:
      fetcher_name: "direct_rss"
      fetcher_config:
        rss_url: "https://example.com/rss.xml"
      content_processor_configs: {}
    fetch_params:
      limit: 20

  - scraper_config:
      fetcher_name: "rsshub"
      fetcher_config:
        hub_root: "https://rsshub.app"
        route: "/sspai/matrix"
      content_processor_configs: {}
    fetch_params:
      limit: 30

# Notion 配置（如果使用 --notion_upload）
notion:
  token: "${NOTION_TOKEN}"
  database_id: "${NOTION_DATABASE_ID}"

# 其他配置...
```

## octopus_service - 启动 Web 服务

`octopus_service` 命令用于启动 OctopusScraper 的 Web 服务，提供 HTTP API 和管理界面。

### 语法

```bash
octopus_service [OPTIONS]
```

### 选项

#### 网络配置

- `--host HOST`: 绑定的主机地址 (默认: 0.0.0.0)
- `--port PORT`: 绑定的端口 (默认: 8000)

#### 运行模式

- `--debug`: 启用调试模式 (默认: false)
- `--workers NUM`: 工作进程数量 (默认: 1)
- `--single-process`: 启用单进程模式 (默认: false)

#### 日志配置

- `--log-level LEVEL`: 设置日志级别 [DEBUG|INFO|WARNING|ERROR] (默认: INFO)
- `--log-format FORMAT`: 设置日志格式 [plain|json] (默认: plain)

### 环境变量支持

所有选项都支持通过环境变量配置：

#### 服务配置
- `OCTOPUS_HOST`: 对应 --host
- `OCTOPUS_PORT`: 对应 --port
- `OCTOPUS_DEBUG`: 对应 --debug
- `OCTOPUS_WORKERS`: 对应 --workers
- `OCTOPUS_SINGLE_PROCESS`: 对应 --single-process
- `OCTOPUS_LOG_LEVEL`: 对应 --log-level
- `OCTOPUS_LOG_FORMAT`: 对应 --log-format

#### 调度器配置
- `ENABLE_SCHEDULER`: 启用/禁用调度器功能 (默认: false)
- `AUTO_START_SCHEDULER`: 服务启动时自动启动调度器 (默认: false)
- `MAX_CONCURRENT_SCHEDULES`: 最大并发调度任务数 (默认: 3)
- `SCHEDULE_CHECK_INTERVAL`: 调度检查间隔秒数 (默认: 60)

### 示例

#### 基本启动

```bash
# 使用默认设置启动服务
octopus_service
```

服务将在 http://0.0.0.0:8000 启动。

#### 自定义主机和端口

```bash
# 在本地地址启动，使用自定义端口
octopus_service --host 127.0.0.1 --port 8080
```

#### 调试模式

```bash
# 启用调试模式和详细日志
octopus_service --debug --log-level DEBUG
```

#### 生产环境配置

```bash
# 生产环境配置：多进程、JSON 日志
octopus_service --host 0.0.0.0 --port 8000 --workers 4 --log-format json --log-level INFO
```

#### 单进程模式

```bash
# 单进程模式（适合开发和调试）
octopus_service --single-process --debug
```

#### 启用调度器功能

```bash
# 启用调度器并自动启动
export ENABLE_SCHEDULER=true
export AUTO_START_SCHEDULER=true
export MAX_CONCURRENT_SCHEDULES=5
export SCHEDULE_CHECK_INTERVAL=30

octopus_service --host 0.0.0.0 --port 8000
```

### 环境变量配置

```bash
# 通过环境变量配置服务
export OCTOPUS_HOST=127.0.0.1
export OCTOPUS_PORT=8080
export OCTOPUS_DEBUG=true
export OCTOPUS_LOG_LEVEL=DEBUG

# 配置调度器功能
export ENABLE_SCHEDULER=true
export AUTO_START_SCHEDULER=false
export MAX_CONCURRENT_SCHEDULES=3
export SCHEDULE_CHECK_INTERVAL=60

octopus_service
```

### 服务功能

启动后，Web 服务提供以下功能：

- **管理 API**: RESTful API 用于系统管理
- **抓取器控制**: 配置和运行抓取器
- **任务管理**: 查看和管理后台任务
- **调度器管理**: 创建、管理和监控定时抓取任务（可选功能）
- **系统监控**: 实时状态和统计信息
- **配置管理**: 在线配置编辑和验证

详细的 API 文档请参考：[管理接口文档](../web_service/admin-interface.md)

## 使用场景

### 开发和测试

```bash
# 开发环境：单次测试抓取
octopus_go --config config.dev.yml

# 开发环境：启动调试服务
octopus_service --single-process --debug --log-level DEBUG
```

### 生产部署

```bash
# 生产环境：定时任务抓取（传统方式）
0 */6 * * * /usr/local/bin/octopus_go --config /etc/octopus/config.yml --notion_upload

# 生产环境：使用调度器功能（推荐）
export ENABLE_SCHEDULER=true
export AUTO_START_SCHEDULER=true
export MAX_CONCURRENT_SCHEDULES=5
octopus_service --host 0.0.0.0 --port 8000 --workers 4 --log-format json
```

### 调度器使用场景

```bash
# 场景1：启用调度器的Web服务
export ENABLE_SCHEDULER=true
export AUTO_START_SCHEDULER=true
export MAX_CONCURRENT_SCHEDULES=3
export SCHEDULE_CHECK_INTERVAL=60
octopus_service --host 0.0.0.0 --port 8000

# 场景2：手动管理调度器
export ENABLE_SCHEDULER=true
export AUTO_START_SCHEDULER=false  # 手动启动调度器
octopus_service --port 8000

# 然后通过API启动调度器：
# curl -X POST http://localhost:8000/admin/scheduler/start

# 场景3：高频调度配置
export ENABLE_SCHEDULER=true
export AUTO_START_SCHEDULER=true
export MAX_CONCURRENT_SCHEDULES=10
export SCHEDULE_CHECK_INTERVAL=30  # 30秒检查一次
octopus_service --port 8000
```

### 自动化脚本

```bash
#!/bin/bash
# 抓取脚本示例

CONFIG_FILE="/path/to/config.yml"
LOG_FILE="/var/log/octopus/scrape.log"

echo "$(date): Starting scrape..." >> "$LOG_FILE"

if octopus_go --config "$CONFIG_FILE" --notion_upload >> "$LOG_FILE" 2>&1; then
    echo "$(date): Scrape completed successfully" >> "$LOG_FILE"
else
    echo "$(date): Scrape failed" >> "$LOG_FILE"
    exit 1
fi
```

## 故障排除

### 常见问题

#### 配置文件错误

```bash
# 问题：配置文件格式错误
ERROR: YAML parsing failed

# 解决：检查 YAML 语法
python -c "import yaml; yaml.safe_load(open('config.yml'))"
```

#### 端口占用

```bash
# 问题：Address already in use
ERROR: [Errno 48] Address already in use

# 解决：更换端口或停止占用进程
octopus_service --port 8001
# 或
lsof -ti:8000 | xargs kill -9
```

#### 权限问题

```bash
# 问题：Permission denied
ERROR: [Errno 13] Permission denied

# 解决：使用非特权端口
octopus_service --port 8080  # 替代 80 端口
```

### 调试技巧

#### 启用详细日志

```bash
# 启用最详细的日志输出
octopus_service --debug --log-level DEBUG --log-format json
```

#### 检查服务状态

```bash
# 检查服务是否正常启动
curl http://localhost:8000/admin/health
```

#### 配置验证

```bash
# 验证配置文件格式
python -c "
import yaml
try:
    with open('config.yml') as f:
        config = yaml.safe_load(f)
    print('配置文件格式正确')
    print(f'发现 {len(config.get(\"scrapers\", {}))} 个抓取器')
except Exception as e:
    print(f'配置文件错误: {e}')
"
```

## 系统集成

### systemd 服务

创建系统服务文件 `/etc/systemd/system/octopus-scraper.service`：

```ini
[Unit]
Description=OctopusScraper Web Service
After=network.target

[Service]
Type=simple
User=octopus
WorkingDirectory=/opt/octopus-scraper
Environment=OCTOPUS_HOST=0.0.0.0
Environment=OCTOPUS_PORT=8000
Environment=OCTOPUS_WORKERS=4
Environment=OCTOPUS_LOG_FORMAT=json
Environment=ENABLE_SCHEDULER=true
Environment=AUTO_START_SCHEDULER=true
Environment=MAX_CONCURRENT_SCHEDULES=5
Environment=SCHEDULE_CHECK_INTERVAL=60
ExecStart=/usr/local/bin/octopus_service
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

启用和管理服务：

```bash
sudo systemctl enable octopus-scraper
sudo systemctl start octopus-scraper
sudo systemctl status octopus-scraper
```

### Docker 部署

Dockerfile 示例：

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN pip install -e .

EXPOSE 8000

CMD ["octopus_service", "--host", "0.0.0.0", "--port", "8000"]
```

### 定时任务

crontab 配置示例：

```bash
# 每 6 小时执行一次抓取
0 */6 * * * /usr/local/bin/octopus_go --config /etc/octopus/config.yml --notion_upload

# 每天凌晨重启服务
0 0 * * * sudo systemctl restart octopus-scraper
```

## 相关文档

- [管理接口文档](../web_service/admin-interface.md) - Web API 详细参考
- [配置管理文档](../../models/config/config-manager.md) - 配置文件格式和选项
- [系统架构文档](../../README.md) - 整体架构概览
