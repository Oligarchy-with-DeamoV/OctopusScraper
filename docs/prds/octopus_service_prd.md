# OctopusService 产品需求文档（PRD）

## 一、项目背景

Octopus 模块已具备读取 Notion 上配置信息，从多个 RSS 源抓取内容，并将抓取结果上传至 Notion Database 的核心业务逻辑。
当前仅能通过本地脚本操作，缺乏服务化能力。为提升系统可集成性、可部署性，需封装为 REST 风格服务组件。

---

## 二、产品目标

构建 OctopusService 服务模块，基于已有 Octopus 功能对外暴露接口，支持远程触发抓取任务与上传任务，便于部署、调试和系统集成。

---

## 三、核心功能

| 编号 | 功能名称                 | 描述                                                                |
| ---- | ------------------------ | ------------------------------------------------------------------- |
| F1   | 启动与初始化             | 启动服务时加载 Notion 中的 RSS 配置，初始化抓取器                   |
| F2   | 手动触发抓取任务         | 提供接口用于手动调用抓取流程，从 RSS 获取内容并缓存                 |
| F3   | 手动触发上传任务         | 提供接口用于上传缓存中的内容至 Notion Database                      |
| F4   | 任务执行状态反馈         | 接口响应应包含成功数量、失败提示等执行结果数据                      |
| F5   | 错误处理与日志记录       | 捕捉异常、输出日志，便于排查和监控                                  |
| F6   | 企业级健康检查系统       | 提供三层健康检查：全面检查、存活探针、就绪探针，支持智能缓存和性能监控 |
| F7   | 配置管理                 | 提供配置状态查询、配置刷新、配置验证等管理功能                      |
| F8   | CLI 工具支持             | 提供 `octopus_service` 命令行工具，支持灵活的启动参数配置           |
| F9   | 任务管理系统             | 统一的任务队列管理、优先级调度、并发控制和实时监控                  |
| F10  | 定时任务调度             | 基于 Cron 表达式的自动任务调度，支持灵活的时间配置                  |
| F11  | 任务重试机制             | 智能重试机制，支持指数退避和可配置的最大重试次数                    |

---

## 四、用户角色与使用场景

| 用户角色   | 使用动机                           | 使用方式                          |
| ---------- | ---------------------------------- | --------------------------------- |
| 系统管理员 | 远程触发抓取任务、纳入定时任务控制 | 通过 REST 接口调用或 CLI 工具     |
| 运维人员   | 手动排查任务失败，主动触发上传     | 使用 Postman、curl 等工具调试接口 |
| 开发人员   | 本地开发测试、配置管理和监控       | 使用 `octopus_service` CLI 工具   |
| 第三方系统 | 集成抓取/上传逻辑至业务流程        | 将接口集成进系统流程链            |
| 运维团队   | 监控任务执行状态、配置定时调度     | 使用任务管理API和调度器配置       |

---

## 五、功能流程说明

### 5.1 服务启动流程

1. 启动 OctopusService；
2. 从 Notion 读取并加载 RSS 源配置信息；
3. 初始化 Octopus 实例与任务缓存区；
4. 持续运行，监听对外接口。

### 5.2 抓取任务流程

1. 调用 `POST /trigger_scraper`；
2. 遍历配置的 RSS 源；
3. 拉取内容写入 `_fetched_contents` 缓存；
4. 返回抓取结果（如条目数量、成功状态等）。

### 5.3 上传任务流程

1. 调用 `POST /trigger_upload`；
2. 读取 `_fetched_contents`；
3. 上传到 Notion 指定的数据库；
4. 返回上传状态及结果统计。

---

## 六、接口设计

### POST /trigger_scraper

- 描述：立即触发一次抓取任务
- 响应示例：

```json
{
  "status": "success",
  "message": "Scraping completed successfully.",
  "data": {
    "source_count": 3,
    "item_count": 18
  }
}
```

### POST /trigger_upload

- 描述：立即将缓存中的内容上传至 Notion
- 响应示例：

```json
{
  "status": "success",
  "message": "Upload completed successfully.",
  "data": {
    "uploaded_count": 18
  }
}
```

### 任务管理接口

#### GET /tasks/stats

- 描述：获取任务统计信息
- 响应示例：

```json
{
  "status": "success",
  "data": {
    "total_tasks": 150,
    "completed_tasks": 120,
    "failed_tasks": 5,
    "pending_tasks": 25,
    "active_tasks": 3,
    "queue_size": 22,
    "workers_count": 4,
    "uptime_seconds": 3600,
    "tasks_per_minute": 2.5,
    "average_task_duration": 45.2,
    "success_rate": 0.96
  }
}
```

#### GET /tasks/active

- 描述：获取当前正在执行的任务列表
- 响应示例：

```json
{
  "status": "success",
  "data": {
    "active_tasks": [
      {
        "id": "task_123",
        "name": "news_scraper",
        "scraper_name": "daily_news",
        "status": "running",
        "priority": "high",
        "started_at": "2025-01-20T10:30:00Z",
        "timeout": 300,
        "retry_count": 0,
        "worker_id": "worker_1"
      }
    ]
  }
}
```

#### POST /tasks/submit

- 描述：提交新的抓取任务
- 请求体：

```json
{
  "name": "custom_task",
  "scraper_name": "example_scraper",
  "priority": "normal",
  "timeout": 120,
  "max_retries": 2,
  "params": {
    "custom_param": "value"
  }
}
```

- 响应示例：

```json
{
  "status": "success",
  "message": "Task submitted successfully",
  "data": {
    "task_id": "task_456",
    "name": "custom_task",
    "status": "queued",
    "priority": "normal",
    "created_at": "2025-01-20T10:35:00Z"
  }
}
```

#### GET /scheduler/status

- 描述：获取任务调度器状态
- 响应示例：

```json
{
  "status": "success",
  "data": {
    "scheduler_running": true,
    "schedules_count": 3,
    "next_run_times": [
      {
        "name": "daily_news",
        "next_run": "2025-01-21T08:00:00Z",
        "cron_expression": "0 8 * * *"
      }
    ]
  }
}
```

#### POST /scheduler/add

- 描述：添加新的定时任务
- 请求体：

```json
{
  "name": "weekly_report",
  "scraper_name": "report_scraper",
  "cron_expression": "0 9 * * 1",
  "priority": "normal",
  "timeout": 600,
  "max_retries": 1
}
```

- 响应示例：

```json
{
  "status": "success",
  "message": "Schedule added successfully",
  "data": {
    "name": "weekly_report",
    "next_run": "2025-01-27T09:00:00Z"
  }
}
```

### 健康检查接口

OctopusService 提供企业级三层健康检查体系，支持不同的监控场景：

#### GET /health

- **描述**：全面的系统健康检查，包含依赖项验证、配置状态、性能指标
- **参数**：
  - `cache` (可选): `true`/`false` - 是否使用缓存（30秒），默认 `true`
- **响应示例**：

```json
{
  "status": "healthy",
  "timestamp": "2025-07-18T15:56:22.080523",
  "service": {
    "name": "OctopusService",
    "version": "0.1.3",
    "uptime_seconds": 1234.56
  },
  "dependencies": {
    "notion_api": {
      "status": "healthy",
      "scrapers_database": {
        "id": "your_scrapers_db_id",
        "accessible": true
      },
      "content_database": {
        "id": "your_content_db_id",
        "accessible": true
      }
    },
    "octopus_instance": {
      "status": "healthy",
      "scrapers_configured": 3,
      "fetched_contents_cached": 15
    }
  },
  "configuration": {
    "status": "healthy",
    "last_check": "2025-07-18T15:56:20.123456",
    "version": "v20250718_155620_abc123",
    "scrapers_count": 3,
    "active_scrapers": 2
  },
  "performance": {
    "response_time_ms": 45.67,
    "memory_usage": {
      "rss_mb": 128.5
    }
  },
  "cached": false
}
```

#### GET /health/liveness

- **描述**：轻量级存活探针，适用于容器环境的 liveness probe
- **响应示例**：

```json
{
  "status": "alive",
  "timestamp": "2025-07-18T15:56:22.080523",
  "service": {
    "name": "OctopusService",
    "version": "0.1.3"
  }
}
```

#### GET /health/readiness

- **描述**：就绪探针，检查服务是否准备好接收流量
- **参数**：
  - `skip_notion` (可选): `true`/`false` - 是否跳过 Notion API 检查，默认 `false`
- **响应示例**：

```json
{
  "status": "ready",
  "timestamp": "2025-07-18T15:56:22.080523",
  "service": {
    "name": "OctopusService",
    "version": "0.1.3"
  },
  "dependencies": {
    "notion_api": {
      "status": "healthy",
      "checked": true
    },
    "octopus_instance": {
      "status": "healthy"
    }
  }
}
```

**状态码说明**：
- **200 OK**: 健康/就绪/存活
- **503 Service Unavailable**: 不健康/未就绪
- **500 Internal Server Error**: 检查过程出错

**特性**：
- 🚀 **智能缓存**：全面健康检查支持 30 秒缓存，减少性能开销
- 🔍 **实时监控**：内存使用、响应时间、依赖项状态跟踪
- 🏥 **容器友好**：专为 Docker 等容器环境设计的探针

### 配置管理接口

### GET /admin/config/status

- 描述：获取当前配置状态和健康信息
- 响应示例：

```json
{
  "is_healthy": true,
  "last_check": "2025-06-20T17:34:47.123456",
  "error_message": null,
  "current_version": {
    "version_id": "v20250620_173447_abc123",
    "timestamp": "2025-06-20T17:34:47.123456",
    "config_hash": "abc123def456",
    "scrapers_count": 3
  },
  "scrapers": [
    {
      "name": "示例抓取器",
      "status": "Active",
      "fetcher": "rsshub",
      "priority": 1
    }
  ]
}
```

### POST /admin/config/refresh

- 描述：手动刷新配置
- 响应示例：

```json
{
  "status": "success",
  "message": "Configuration refreshed successfully",
  "config_changed": true,
  "current_version": "v20250620_173447_abc123",
  "scrapers_count": 3
}
```

### POST /admin/config/validate

- 描述：验证当前配置的有效性
- 响应示例：

```json
{
  "status": "success",
  "is_valid": true,
  "validation_errors": [],
  "scrapers_count": 3,
  "scrapers": [
    {
      "name": "示例抓取器",
      "status": "Active",
      "fetcher": "rsshub"
    }
  ]
}
```
- 响应示例：

```json
{
  "status": "healthy",
  "timestamp": "2025-07-18T10:30:00Z",
  "uptime": 3600.5,
  "version": "0.1.3",
  "dependencies": {
    "config_manager": "healthy",
    "data_storage": "healthy"
  },
  "metrics": {
    "memory_usage_mb": 128.5,
    "cpu_usage_percent": 15.2
  }
}
```

- 状态码
  - 200: 服务健康
  - 503: 服务不健康
  - 500: 服务错误

## 七、CLI 工具设计

### octopus_service 命令

提供命令行工具用于灵活启动服务：

```bash
# 基本启动
octopus_service

# 自定义配置启动
octopus_service --host 127.0.0.1 --port 8080 --debug --single-process
```

### 支持参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--host` | 服务监听地址 | `0.0.0.0` |
| `--port` | 服务监听端口 | `8000` |
| `--debug` | 启用调试模式 | `false` |
| `--log-level` | 日志级别 | `INFO` |
| `--log-format` | 日志格式 | `plain` |
| `--workers` | 工作进程数 | `1` |
| `--single-process` | 单进程模式 | `false` |

## 八、非功能性要求

| 类别     | 描述                                                            |
| -------- | --------------------------------------------------------------- |
| 性能     | 单次抓取任务应在 3～5 秒内完成（数据量在合理范围内）            |
| 性能优化 | 批量上传去重优化：API 调用从 N+1 次减少到 1 次，大幅提升批量处理性能 |
| 任务管理 | 支持并发任务执行，默认4个工作线程，可配置队列大小和重试策略     |
| 任务调度 | 基于Cron表达式的定时任务调度，支持秒级精度和复杂时间规则        |
| 可部署性 | 支持通过命令行或 Docker 启动服务，适配 CI/CD 环境               |
| 易用性   | 接口应提供统一的响应格式，错误提示应简洁明确，便于调用方处理    |
| 日志能力 | 所有任务执行与异常信息需写入日志（控制台 + 文件），方便追踪问题 |
| 扩展性   | 接口结构预留拓展空间，未来可支持定时任务、权限校验等功能        |
| CLI 支持 | 提供命令行工具，支持灵活的参数配置和环境变量覆盖                |
| 监控能力 | 提供实时任务状态监控、统计信息和性能指标                        |

---

## 九、功能边界说明

| 项目       | 当前版本行为说明                                                     |
| ---------- | -------------------------------------------------------------------- |
| 配置更新   | 配置信息由 Notion Database 提供，手动修改后服务可自动读取更新        |
| 配置管理   | 已提供配置状态查询、手动刷新、配置验证等管理接口                      |
| 任务管理   | 已提供统一的任务队列、优先级调度、并发控制和实时监控                  |
| 定时调度   | 已提供基于Cron表达式的内置定时调度机制，支持灵活的时间配置            |
| 任务重试   | 已提供智能重试机制，支持指数退避和可配置的最大重试次数                |
| 接口鉴权   | 当前接口为开放状态，未接入鉴权或 Token 校验机制                      |
| Web 控制台 | 不包含图形界面，所有功能通过 API 接口和 CLI 工具访问                  |
| 并发控制   | 已支持任务并发控制，可配置工作线程数量和队列大小                      |

---

## 九、后续版本规划（版本路线图）

| 版本号 | 功能方向说明                       |
| ------ | ---------------------------------- |
| v1.1   | 加入基础鉴权机制（Token 鉴权）     |
| v1.2   | 支持定时任务调度（内部或外部集成） |
| v1.3   | 接入 Web 控制台（任务查看、触发）  |
| v2.0   | 多租户支持、配置隔离、任务并发控制 |

---

## 十、验收标准

| 项目                 | 验收标准说明                                                         |
| -------------------- | -------------------------------------------------------------------- |
| 服务可启动           | 可通过命令行或容器方式启动服务，控制台输出包含 Ready 信息            |
| CLI 工具功能         | `octopus_service` 命令可正常执行，支持所有预定义参数                  |
| 接口功能正常         | 所有 API 接口可正常访问、响应结构正确                                |
| 配置读取成功         | Octopus 实例可成功加载 Notion 中的配置信息，初始化完成               |
| 抓取与上传逻辑完整   | 抓取后的数据写入缓存，上传后内容写入 Notion，流程无中断或数据丢失    |
| 配置管理功能         | 配置状态查询、刷新、验证接口正常工作                                 |
| 任务管理系统         | 任务队列、优先级调度、并发控制功能正常，任务统计信息准确             |
| 定时调度功能         | 基于Cron表达式的定时任务可正常添加、执行和管理                       |
| 任务重试机制         | 失败任务能够按配置进行重试，重试次数和延迟策略生效                   |
| 任务监控功能         | 任务状态监控、统计信息、性能指标等API正常工作                        |
| 错误处理机制健全     | 异常场景下接口可返回结构化报错信息，日志中记录关键错误点             |
| 原业务逻辑保持完整性 | 新增服务封装不会破坏现有 Octopus 模块的结构与调用方式                |

---
