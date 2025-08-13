# CLI 接口文档

## 概述

OctopusScraper 提供了两个主要的命令行工具：`octopus_go` 用于执行一次性抓取任务，`octopus_service` 用于启动 Web 服务。这些工具完全集成了最新的任务管理系统，所有抓取操作都通过 TaskManager 执行，提供统一的任务调度、监控和管理功能。

> 📢 **架构更新**: CLI 工具现已完全集成 TaskManager，所有任务都通过统一的任务管理系统执行，提供更好的并发控制、错误处理和监控功能。

## 可用命令

OctopusScraper 提供以下命令行工具：

```
octopus_go       # 一次性抓取执行 (通过 TaskManager)
octopus_service  # Web 服务启动 (包含任务管理和调度功能)
```

## octopus_go - 执行抓取任务

`octopus_go` 命令用于执行一次性的抓取任务，支持配置文件和可选的 Notion 上传功能。所有任务都通过 TaskManager 执行，提供优先级调度、并发控制和监控功能。

### 主要特性

- 🎛️ **统一任务管理**: 所有抓取都通过 TaskManager 执行
- 📊 **实时监控**: 支持任务状态跟踪和进度显示
- 🔄 **智能重试**: 自动处理失败任务的重试
- ⚡ **并发执行**: 支持多抓取器并发运行
- 📝 **详细日志**: 提供完整的执行日志和调试信息

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

`octopus_go` 命令需要一个 YAML 配置文件，使用最新的配置格式：

```yaml
# 抓取器配置
scrapers_config_with_fetch_params:
  - scraper_config:
      fetcher_name: "direct_rss"
      fetcher_config:
        rss_url: "https://example.com/rss.xml"
      content_processor_configs:
        html_content:
          remove_tags: ["script", "style"]
          preserve_links: true
        llm:
          generate_summary: true
          generate_tags: true
    fetch_params:
      limit: 20

  - scraper_config:
      fetcher_name: "rsshub"
      fetcher_config:
        hub_root: "https://rsshub.app"
        route: "/sspai/matrix"
      content_processor_configs:
        html_content:
          max_content_length: 5000
    fetch_params:
      limit: 30

# Notion 配置（如果使用 --notion_upload）
notion_api_config:
  api_key: "${NOTION_API_KEY}"
  database_id: "${NOTION_DATABASE_ID}"

# 任务管理配置 (可选)
task_manager_config:
  max_concurrent_tasks: 5
  max_queue_size: 100
  result_retention_hours: 24

# 启用调度器 (可选)
enable_scheduler: false
auto_start_scheduler: false
```

## octopus_service - 启动 Web 服务

`octopus_service` 命令用于启动 OctopusScraper 的 Web 服务，提供完整的 HTTP API、任务管理、调度功能和管理界面。

### 主要特性

- 🌐 **RESTful API**: 完整的 Web API 接口
- 🎛️ **任务管理**: 集成 TaskManager 的 Web 管理界面
- 📅 **调度功能**: 支持 Cron 表达式的定时任务调度
- 📊 **监控面板**: 实时任务状态和性能监控
- 🔧 **配置管理**: 动态配置加载和热重载
- 🔒 **健康检查**: 系统健康状态监控

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

#### 日志配置

- `--log-level LEVEL`: 设置日志级别 [DEBUG|INFO|WARNING|ERROR] (默认: INFO)
- `--log-format FORMAT`: 设置日志格式 [plain|json] (默认: plain)

### 环境变量支持

所有选项都支持通过环境变量配置：

#### 服务配置
- `OCTOPUS_HOST`: 对应 --host
- `OCTOPUS_PORT`: 对应 --port
- `OCTOPUS_DEBUG`: 对应 --debug
- `OCTOPUS_LOG_LEVEL`: 对应 --log-level
- `OCTOPUS_LOG_FORMAT`: 对应 --log-format

#### 任务管理配置
- `MAX_CONCURRENT_TASKS`: TaskManager 最大并发任务数 (默认: 5)
- `MAX_QUEUE_SIZE`: 任务队列最大容量 (默认: 1000) 
- `RESULT_RETENTION_HOURS`: 任务结果保留时间 (默认: 24)

#### 调度器配置
- `ENABLE_SCHEDULER`: 启用/禁用调度器功能 (默认: false)
- `AUTO_START_SCHEDULER`: 服务启动时自动启动调度器 (默认: false)
- `MAX_CONCURRENT_SCHEDULES`: 最大并发调度任务数 (默认: 3)
- `SCHEDULE_CHECK_INTERVAL`: 调度检查间隔秒数 (默认: 60)

#### Notion 配置
- `NOTION_API_KEY`: Notion API 密钥
- `NOTION_CONTENT_DATABASE_ID`: 内容数据库 ID
- `NOTION_SCRAPERS_DATABASE_ID`: 抓取器配置数据库 ID

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
# 生产环境配置：JSON 日志
octopus_service --host 0.0.0.0 --port 8000 --log-format json --log-level INFO
```

#### 启用调度器的生产环境

```bash
# 启用调度器和自动启动
ENABLE_SCHEDULER=true AUTO_START_SCHEDULER=true octopus_service
```

#### 使用环境变量配置

```bash
# 通过环境变量配置所有参数
export OCTOPUS_HOST=0.0.0.0
export OCTOPUS_PORT=8000
export OCTOPUS_DEBUG=false
export MAX_CONCURRENT_TASKS=8
export ENABLE_SCHEDULER=true
export NOTION_API_KEY=your_notion_key

octopus_service
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

### 服务架构

启动后，Web 服务提供以下核心功能：

#### 核心组件
- **TaskManager**: 统一任务执行引擎 (自动启用)
- **TaskScheduler**: 定时任务调度器 (可选启用)
- **ConfigManager**: 动态配置管理
- **Admin API**: 完整的管理接口

#### 主要功能
- 🎛️ **任务管理**: 查看、监控和管理所有后台任务
- 📅 **调度管理**: 创建、管理和监控定时抓取任务
- 🔧 **配置管理**: 在线配置编辑、验证和热重载
- 🕷️ **抓取器控制**: 配置和运行各种抓取器
- 📊 **系统监控**: 实时状态、统计信息和性能指标
- 🔍 **健康检查**: 系统健康状态和故障排除

#### API 端点概览
- `/trigger/scraper` - 触发抓取任务
- `/trigger/upload` - 触发上传任务  
- `/admin/tasks/*` - 任务管理 API
- `/admin/scheduler/*` - 调度器管理 API
- `/admin/config/*` - 配置管理 API
- `/health` - 健康检查端点

详细的 API 文档请参考：[管理接口文档](../web_service/admin-interface.md)

## 使用场景和最佳实践

### 开发和测试

#### 快速原型和测试
```bash
# 单次测试抓取 (任务自动通过 TaskManager 执行)
octopus_go --config config.dev.yml

# 开发环境调试服务
octopus_service --debug --log-level DEBUG
```

#### 本地开发环境
```bash
# 启动本地开发服务器，启用调度器
export ENABLE_SCHEDULER=true
export AUTO_START_SCHEDULER=false  # 手动控制调度器启动
export MAX_CONCURRENT_TASKS=3
export OCTOPUS_DEBUG=true

octopus_service --host 127.0.0.1 --port 8000
```

### 生产部署

#### 传统 Cron 方式 (向后兼容)
```bash
# 定时任务抓取 (仍然通过 TaskManager 执行)
0 */6 * * * /usr/local/bin/octopus_go --config /etc/octopus/config.yml --notion_upload
```

#### 现代调度器方式 (推荐)
```bash
# 生产环境：使用内置调度器
export ENABLE_SCHEDULER=true
export AUTO_START_SCHEDULER=true
export MAX_CONCURRENT_SCHEDULES=10
export MAX_CONCURRENT_TASKS=8
export RESULT_RETENTION_HOURS=48

octopus_service --host 0.0.0.0 --port 8000 --log-format json
```

#### 高可用部署
```bash
# 多实例部署 (调度器只在一个实例启用)
# 实例 1: 主服务 + 调度器
ENABLE_SCHEDULER=true AUTO_START_SCHEDULER=true octopus_service --port 8000

# 实例 2: 仅 API 服务  
ENABLE_SCHEDULER=false octopus_service --port 8001

# 实例 3: 仅 API 服务
ENABLE_SCHEDULER=false octopus_service --port 8002
```

### 调度器使用场景

### 监控和管理

#### 任务状态监控
```bash
# 通过 API 检查任务状态
curl http://localhost:8000/admin/tasks/stats

# 查看当前运行的任务
curl http://localhost:8000/admin/tasks/running

# 查看调度器状态 (如果启用)
curl http://localhost:8000/admin/scheduler/status
```

#### 日志监控
```bash
# 实时监控日志
tail -f /var/log/octopus/service.log

# 过滤任务相关日志
journalctl -u octopus-scraper -f | grep "TaskManager"

# 过滤调度器日志
journalctl -u octopus-scraper -f | grep "TaskScheduler"
```

### 集群和高可用部署

#### 负载均衡配置
```bash
# 实例 1: 主服务 + 调度器
ENABLE_SCHEDULER=true AUTO_START_SCHEDULER=true octopus_service --port 8000

# 实例 2-N: 仅 API 服务  
ENABLE_SCHEDULER=false octopus_service --port 8001
ENABLE_SCHEDULER=false octopus_service --port 8002
```

#### 健康检查配置
```bash
# 配置负载均衡器健康检查
# 健康检查 URL: http://instance:port/health
# 检查间隔: 30s
# 超时: 5s
# 重试次数: 3
```

### 自动化脚本

#### 基本抓取脚本
```bash
#!/bin/bash
# 抓取脚本示例 (任务通过 TaskManager 执行)

CONFIG_FILE="/path/to/config.yml"
LOG_FILE="/var/log/octopus/scrape.log"

echo "$(date): Starting scrape with TaskManager..." >> "$LOG_FILE"

if octopus_go --config "$CONFIG_FILE" --notion_upload >> "$LOG_FILE" 2>&1; then
    echo "$(date): Scrape completed successfully" >> "$LOG_FILE"
else
    echo "$(date): Scrape failed" >> "$LOG_FILE"
    exit 1
fi
```

#### 健康检查脚本
```bash
#!/bin/bash
# 服务健康检查脚本

HEALTH_URL="http://localhost:8000/health"
MAX_RETRIES=3
RETRY_DELAY=5

for i in $(seq 1 $MAX_RETRIES); do
    if curl -sf "$HEALTH_URL" > /dev/null; then
        echo "Service is healthy"
        exit 0
    fi
    echo "Health check failed (attempt $i/$MAX_RETRIES)"
    sleep $RETRY_DELAY
done

echo "Service is unhealthy"
exit 1
```

#### 任务监控脚本
```bash
#!/bin/bash
# 任务状态监控脚本

API_BASE="http://localhost:8000/admin"

# 检查任务管理器状态
TASK_STATS=$(curl -s "$API_BASE/tasks/stats")
echo "Task Manager Stats: $TASK_STATS"

# 检查调度器状态 (如果启用)
SCHEDULER_STATUS=$(curl -s "$API_BASE/scheduler/status" 2>/dev/null)
if [ $? -eq 0 ]; then
    echo "Scheduler Status: $SCHEDULER_STATUS"
else
    echo "Scheduler not enabled or unreachable"
fi
```

## 故障排除

### 常见问题

#### TaskManager 相关问题

```bash
# 问题：任务执行缓慢
# 检查并发配置
curl http://localhost:8000/admin/tasks/stats
# 调整并发数
export MAX_CONCURRENT_TASKS=8

# 问题：任务队列满
# 检查队列状态
curl http://localhost:8000/admin/tasks/queue
# 调整队列容量
export MAX_QUEUE_SIZE=2000
```

#### 调度器相关问题

```bash
# 问题：调度器未启动
# 检查调度器状态
curl http://localhost:8000/admin/scheduler/status
# 手动启动调度器
curl -X POST http://localhost:8000/admin/scheduler/start

# 问题：调度任务不执行
# 检查调度配置
curl http://localhost:8000/admin/scheduler/schedules
# 验证 Cron 表达式
python -c "from croniter import croniter; print(croniter('0 9 * * *').get_next())"
```

#### 配置和连接问题

```bash
# 问题：配置文件格式错误
ERROR: YAML parsing failed
# 解决：检查 YAML 语法
python -c "import yaml; yaml.safe_load(open('config.yml'))"

# 问题：Notion API 连接失败
ERROR: Notion API authentication failed
# 解决：检查 API 密钥和数据库 ID
export NOTION_API_KEY=your_actual_key
export NOTION_CONTENT_DATABASE_ID=your_db_id
```

#### 服务启动问题

```bash
# 问题：端口占用
ERROR: [Errno 48] Address already in use
# 解决：更换端口或停止占用进程
octopus_service --port 8001
# 或查找并终止占用进程
lsof -ti:8000 | xargs kill -9

# 问题：权限问题
ERROR: [Errno 13] Permission denied
# 解决：使用非特权端口
octopus_service --port 8080  # 替代 80 端口
```

### 调试技巧

#### 启用详细日志和监控

```bash
# 启用最详细的日志输出
octopus_service --debug --log-level DEBUG --log-format json

# 监控 TaskManager 日志
journalctl -u octopus-scraper -f | grep "TaskManager"

# 监控调度器日志
journalctl -u octopus-scraper -f | grep "TaskScheduler"
```

#### 服务状态检查

```bash
# 检查服务健康状态
curl http://localhost:8000/health

# 检查任务管理器状态
curl http://localhost:8000/admin/tasks/stats

# 检查调度器状态 (如果启用)
curl http://localhost:8000/admin/scheduler/status

# 检查配置状态
curl http://localhost:8000/admin/config/status
```

#### 性能分析

```bash
# 查看任务队列状态
curl http://localhost:8000/admin/tasks/queue

# 查看最近任务历史
curl http://localhost:8000/admin/tasks/recent

# 查看系统资源使用
curl http://localhost:8000/admin/system/metrics
```

#### 配置验证工具

```bash
# 验证配置文件格式和内容
python -c "
import yaml
import sys

try:
    with open('config.yml') as f:
        config = yaml.safe_load(f)
    
    # 检查必要字段
    required_fields = ['scrapers_config_with_fetch_params', 'notion_api_config']
    for field in required_fields:
        if field not in config:
            print(f'缺少必要字段: {field}')
            sys.exit(1)
    
    scrapers = config.get('scrapers_config_with_fetch_params', [])
    print(f'配置文件格式正确，发现 {len(scrapers)} 个抓取器')
    
    # 检查任务管理配置
    tm_config = config.get('task_manager_config', {})
    print(f'TaskManager 配置: {tm_config}')
    
    # 检查调度器配置
    scheduler_enabled = config.get('enable_scheduler', False)
    print(f'调度器启用状态: {scheduler_enabled}')
    
except Exception as e:
    print(f'配置文件错误: {e}')
    sys.exit(1)
"
```

## 系统集成

### systemd 服务

创建系统服务文件 `/etc/systemd/system/octopus-scraper.service`：

```ini
[Unit]
Description=OctopusScraper Web Service with TaskManager
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=octopus
Group=octopus
WorkingDirectory=/opt/octopus-scraper

# 基础服务配置
Environment=OCTOPUS_HOST=0.0.0.0
Environment=OCTOPUS_PORT=8000
Environment=OCTOPUS_WORKERS=4
Environment=OCTOPUS_LOG_FORMAT=json
Environment=OCTOPUS_LOG_LEVEL=INFO

# TaskManager 配置
Environment=MAX_CONCURRENT_TASKS=8
Environment=MAX_QUEUE_SIZE=1000
Environment=RESULT_RETENTION_HOURS=48

# 调度器配置
Environment=ENABLE_SCHEDULER=true
Environment=AUTO_START_SCHEDULER=true
Environment=MAX_CONCURRENT_SCHEDULES=10
Environment=SCHEDULE_CHECK_INTERVAL=60

# Notion 配置 (从环境文件加载)
EnvironmentFile=-/etc/octopus-scraper/environment

# 服务启动配置
ExecStart=/usr/local/bin/octopus_service
ExecReload=/bin/kill -HUP $MAINPID
KillMode=mixed
KillSignal=SIGTERM
TimeoutStopSec=30

# 重启策略
Restart=always
RestartSec=3
StartLimitInterval=300
StartLimitBurst=5

# 安全设置
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/log/octopus

# 资源限制
LimitNOFILE=65536
LimitCORE=0

[Install]
WantedBy=multi-user.target
```

环境文件 `/etc/octopus-scraper/environment`：

```bash
# Notion 配置
NOTION_API_KEY=your_notion_api_key
NOTION_CONTENT_DATABASE_ID=your_content_db_id
NOTION_SCRAPERS_DATABASE_ID=your_scrapers_db_id

# 其他敏感配置
# OPENAI_API_KEY=your_openai_key
```

启用和管理服务：

```bash
# 创建用户和目录
sudo useradd -r -s /bin/false octopus
sudo mkdir -p /opt/octopus-scraper /var/log/octopus /etc/octopus-scraper
sudo chown octopus:octopus /var/log/octopus

# 安装和启用服务
sudo systemctl daemon-reload
sudo systemctl enable octopus-scraper
sudo systemctl start octopus-scraper

# 查看服务状态
sudo systemctl status octopus-scraper

# 查看服务日志
sudo journalctl -u octopus-scraper -f

# 重启服务
sudo systemctl restart octopus-scraper
```

### Docker 部署

#### Dockerfile 示例

```dockerfile
FROM python:3.10-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 创建应用用户
RUN useradd -r -s /bin/false octopus

# 设置工作目录
WORKDIR /app

# 复制并安装 Python 依赖
COPY pyproject.toml poetry.lock ./
RUN pip install poetry && \
    poetry config virtualenvs.create false && \
    poetry install --no-dev

# 复制应用代码
COPY src/ ./src/
COPY config.example.yml ./

# 设置权限
RUN chown -R octopus:octopus /app
USER octopus

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
CMD ["octopus_service", "--host", "0.0.0.0", "--port", "8000"]
```

#### docker-compose.yml 示例

```yaml
version: '3.8'

services:
  octopus-scraper:
    build: .
    container_name: octopus-scraper
    ports:
      - "8000:8000"
    environment:
      # 基础配置
      OCTOPUS_HOST: 0.0.0.0
      OCTOPUS_PORT: 8000
      OCTOPUS_LOG_FORMAT: json
      
      # TaskManager 配置
      MAX_CONCURRENT_TASKS: 8
      MAX_QUEUE_SIZE: 1000
      RESULT_RETENTION_HOURS: 48
      
      # 调度器配置
      ENABLE_SCHEDULER: "true"
      AUTO_START_SCHEDULER: "true"
      MAX_CONCURRENT_SCHEDULES: 10
      
      # Notion 配置 (从 .env 文件加载)
      NOTION_API_KEY: ${NOTION_API_KEY}
      NOTION_CONTENT_DATABASE_ID: ${NOTION_CONTENT_DATABASE_ID}
      NOTION_SCRAPERS_DATABASE_ID: ${NOTION_SCRAPERS_DATABASE_ID}
    
    volumes:
      - ./logs:/app/logs
      - ./config:/app/config:ro
    
    restart: unless-stopped
    
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

# 可选：添加反向代理
  nginx:
    image: nginx:alpine
    container_name: octopus-nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - octopus-scraper
    restart: unless-stopped
```

### 监控集成

#### Prometheus 指标

```bash
# 添加自定义指标端点
curl http://localhost:8000/admin/monitoring/metrics

# 示例 prometheus.yml 配置
# scrape_configs:
#   - job_name: 'octopus-scraper'
#     static_configs:
#       - targets: ['localhost:8000']
#     metrics_path: '/admin/monitoring/metrics'
#     scrape_interval: 30s
```

#### 日志聚合

```bash
# 使用 journald 聚合日志
sudo journalctl -u octopus-scraper --output=json | \
    jq 'select(.PRIORITY <= "4")' | \
    while read log; do
        # 发送到日志聚合系统
        echo "$log" >> /var/log/octopus/aggregated.log
    done
```

## 最佳实践总结

### 1. 配置管理

- ✅ 使用环境变量存储敏感信息
- ✅ 为不同环境维护不同的配置文件
- ✅ 定期验证配置文件的有效性
- ✅ 使用配置管理工具进行版本控制

### 2. 任务管理

- ✅ 根据系统资源调整并发任务数
- ✅ 设置合理的任务超时时间
- ✅ 监控任务队列状态，防止积压
- ✅ 定期清理过期的任务结果

### 3. 调度管理

- ✅ 使用标准 Cron 表达式
- ✅ 避免调度任务之间的冲突
- ✅ 设置合理的重试策略
- ✅ 监控调度任务的执行状态

### 4. 运维管理

- ✅ 配置完善的日志记录和监控
- ✅ 设置健康检查和自动重启
- ✅ 定期备份重要配置和数据
- ✅ 建立故障处理和恢复流程

### 5. 安全考虑

- ✅ 使用非特权用户运行服务
- ✅ 限制服务的系统权限
- ✅ 定期更新依赖和安全补丁
- ✅ 配置适当的网络访问控制

## 相关文档

- **[管理接口文档](../web_service/admin-interface.md)** - 完整的 Web API 参考
- **[TaskManager 模型文档](../../models/task_manager/task-manager.md)** - 任务管理系统详解
- **[ConfigManager 文档](../../models/config/config-manager.md)** - 配置管理系统
- **[主要 README](../../../README.md)** - 完整的安装和使用指南

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
