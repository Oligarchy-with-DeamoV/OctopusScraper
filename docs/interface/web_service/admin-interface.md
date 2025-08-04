# OctopusService 管理接口文档

本文档描述了 OctopusService 新增的管理接口，用于配置管理、系统监控、热更新等功能。

## 概览接口

### GET /admin
获取所有可用管理接口的概览和当前系统状态。

```json
{
  "status": "success",
  "message": "OctopusService Admin Interface",
  "system_health": {
    "overall_healthy": true,
    "summary": {
      "configuration": {"healthy": true, "scrapers_count": 3, "active_scrapers": 2},
      "notion": {"healthy": true},
      "octopus": {"scrapers_configured": 3, "task_manager_enabled": false}
    }
  },
  "admin_endpoints": {...},
  "service_info": {...}
}
```

## 配置管理接口

### POST /admin/config/hotreload
热更新配置，最小化服务中断。

**请求体：**
```json
{}  // 空请求体，自动检测配置变更
```

**响应示例：**
```json
{
  "status": "success",
  "message": "Hot reload completed successfully",
  "reload_performed": true,
  "changes": {
    "old_version": "v20250719_120000_abc123",
    "new_version": "v20250719_120500_def456",
    "old_scrapers_count": 2,
    "new_scrapers_count": 3,
    "change_summary": "Added 1 scrapers (2 → 3)"
  },
  "timestamp": "2025-07-19T12:05:00.123456"
}
```

## 系统信息接口

### GET /admin/system/info
获取详细的系统信息。

**响应示例：**
```json
{
  "status": "success",
  "system_info": {
    "service": {
      "name": "OctopusService",
      "version": "0.1.2",
      "uptime_seconds": null,
      "environment": "development",
      "debug_mode": false
    },
    "configuration": {
      "config_refresh_interval": 300,
      "scraper_timeout": 10,
      "upload_timeout": 15,
      "upload_max_retries": 3,
      "log_level": "INFO",
      "log_format": "plain"
    },
    "octopus_instance": {
      "scrapers_configured": 3,
      "fetched_contents_cached": 15,
      "max_concurrent_scrapers": 5,
      "use_task_manager": false
    },
    "task_manager": {"enabled": false},
    "memory_usage": {"rss_mb": 128.5}
  }
}
```

### GET /admin/monitoring/metrics
获取综合监控指标。

**响应示例：**
```json
{
  "status": "success",
  "metrics": {
    "timestamp": "2025-07-19T12:05:00.123456",
    "service": {...},
    "performance": {
      "memory_usage": {"rss_mb": 128.5},
      "response_times": {...}
    },
    "configuration": {
      "status": "healthy",
      "version": "v20250719_120500_def456",
      "scrapers_count": 3,
      "active_scrapers_count": 2,
      "refresh_interval_seconds": 300
    },
    "notion": {
      "connectivity": "healthy",
      "api_key_configured": true
    },
    "task_manager": {"enabled": false}
  }
}
```

## 抓取器管理接口

### GET /admin/scrapers/list
列出所有配置的抓取器及其详细信息。

**响应示例：**
```json
{
  "status": "success",
  "scrapers": [
    {
      "index": 0,
      "name": "example_scraper",
      "status": "Active",
      "fetcher": "rsshub",
      "hub_root": "https://rsshub.app",
      "route": "/example/route",
      "priority": 1,
      "fetch_params": {"limit": 10},
      "is_active": true,
      "runtime": {
        "initialized": true,
        "fetcher_type": "RssHub",
        "has_storage": true,
        "processors_count": 0
      }
    }
  ],
  "summary": {
    "total_count": 3,
    "active_count": 2,
    "inactive_count": 1,
    "fetcher_distribution": {"rsshub": 2, "direct_rss": 1}
  }
}
```

### POST /admin/scrapers/{scraper_name}/test
测试特定的抓取器。

**请求体：**
```json
{
  "params": {"limit": 5},  // 可选，覆盖默认参数
  "timeout": 30            // 可选，超时时间（秒）
}
```

**响应示例：**
```json
{
  "status": "success",
  "message": "Scraper 'example_scraper' test completed successfully",
  "test_results": {
    "scraper_name": "example_scraper",
    "fetcher": "rsshub",
    "execution_time_seconds": 2.45,
    "items_fetched": 5,
    "test_params": {"limit": 5},
    "sample_items": [
      {
        "title": "Sample Article Title...",
        "link": "https://example.com/article/1",
        "published": "2025-07-19T10:00:00Z",
        "content_id": "abc123"
      }
    ]
  },
  "timestamp": "2025-07-19T12:05:00.123456"
}
```

## 任务管理接口（仅在启用任务管理器时可用）

### GET /admin/tasks/stats
获取任务管理器统计信息。

**响应示例：**
```json
{
  "status": "success",
  "statistics": {
    "total_tasks": 150,
    "completed_tasks": 120,
    "failed_tasks": 5,
    "cancelled_tasks": 2,
    "current_queue_size": 3,
    "running_tasks_count": 2,
    "success_rate_percent": 96.0,
    "average_task_duration_seconds": 45.2,
    "task_manager_enabled": true,
    "legacy_mode": false,
    "uptime_info": {
      "queue_capacity_usage": "3/1000",
      "worker_utilization": "2/5"
    }
  }
}
```

### GET /admin/tasks/list
列出任务，支持过滤。

**查询参数：**
- `status`: 过滤状态（pending/running/completed/failed/cancelled）
- `limit`: 限制返回数量（最大200）

**响应示例：**
```json
{
  "status": "success",
  "tasks": [
    {
      "task_id": "task_456",
      "status": "completed",
      "start_time": "2025-07-19T12:00:00.123456",
      "end_time": "2025-07-19T12:01:30.654321",
      "duration_seconds": 90.53,
      "items_fetched": 15,
      "items_processed": 15,
      "items_uploaded": 0,
      "error_message": null,
      "metadata": {...}
    }
  ],
  "filters": {"status": "completed", "limit": 50},
  "total_returned": 25,
  "task_manager_enabled": true
}
```

### POST /admin/tasks/submit
提交单个抓取器任务。

**请求体：**
```json
{
  "scraper_name": "example_scraper",  // 必需
  "fetch_params": {"limit": 10}       // 可选，覆盖默认参数
}
```

**响应示例：**
```json
{
  "status": "success",
  "message": "Task submitted successfully",
  "task_id": "task_789",
  "scraper_name": "example_scraper",
  "fetch_params": {"limit": 10}
}
```

### GET /admin/tasks/{task_id}
获取特定任务的详细信息。

### POST /admin/tasks/{task_id}/cancel
取消特定任务。

## 调度器管理接口（仅在启用调度器时可用）

### GET /admin/scheduler/status
获取调度器运行状态和统计信息。

**响应示例：**
```json
{
  "status": "success",
  "scheduler_status": {
    "is_running": true,
    "start_time": "2025-08-04T10:00:00.123456",
    "uptime_seconds": 7200,
    "total_schedules": 5,
    "active_schedules": 3,
    "pending_tasks": 2,
    "completed_tasks": 48,
    "failed_tasks": 2,
    "success_rate": 0.96,
    "average_execution_time": 45.5,
    "scheduler_enabled": true,
    "environment_config": {
      "enable_scheduler": true,
      "auto_start_scheduler": true,
      "max_concurrent_schedules": 5,
      "schedule_check_interval": 30
    }
  },
  "timestamp": "2025-08-04T12:00:00.123456"
}
```

### GET /admin/scheduler/schedules
列出所有调度任务。

**查询参数：**
- `status`: 过滤状态（enabled/disabled）
- `limit`: 限制返回数量（最大100）

**响应示例：**
```json
{
  "status": "success",
  "schedules": [
    {
      "schedule_id": "daily-news-001",
      "name": "每日新闻抓取",
      "description": "每天早上8点抓取新闻内容",
      "cron_expression": "0 8 * * *",
      "is_enabled": true,
      "scraper_config": {
        "name": "news_scraper",
        "fetch_params": {"limit": 20}
      },
      "created_at": "2025-08-01T10:00:00.123456",
      "updated_at": "2025-08-03T15:30:00.654321",
      "last_run": "2025-08-04T08:00:00.123456",
      "next_run": "2025-08-05T08:00:00.000000",
      "run_count": 15,
      "success_count": 14,
      "failure_count": 1,
      "success_rate": 0.93,
      "last_error": null
    }
  ],
  "total_schedules": 5,
  "active_schedules": 3,
  "scheduler_enabled": true
}
```

### POST /admin/scheduler/schedules
创建新的调度任务。

**请求体：**
```json
{
  "schedule_id": "weekly-report-001",
  "name": "周报数据抓取",
  "description": "每周一上午9点抓取周报数据",
  "cron_expression": "0 9 * * 1",
  "scraper_config": {
    "name": "report_scraper",
    "fetch_params": {"report_type": "weekly"}
  },
  "is_enabled": true
}
```

**响应示例：**
```json
{
  "status": "success",
  "message": "Schedule created successfully",
  "schedule": {
    "schedule_id": "weekly-report-001",
    "name": "周报数据抓取",
    "cron_expression": "0 9 * * 1",
    "is_enabled": true,
    "created_at": "2025-08-04T12:00:00.123456",
    "next_run": "2025-08-05T09:00:00.000000"
  }
}
```

### GET /admin/scheduler/schedules/{schedule_id}
获取特定调度任务的详细信息。

**响应示例：**
```json
{
  "status": "success",
  "schedule": {
    "schedule_id": "daily-news-001",
    "name": "每日新闻抓取",
    "description": "每天早上8点抓取新闻内容",
    "cron_expression": "0 8 * * *",
    "is_enabled": true,
    "scraper_config": {...},
    "statistics": {
      "run_count": 15,
      "success_count": 14,
      "failure_count": 1,
      "success_rate": 0.93,
      "average_execution_time": 42.3
    },
    "recent_runs": [
      {
        "run_time": "2025-08-04T08:00:00.123456",
        "success": true,
        "execution_time": 38.5,
        "items_processed": 18
      }
    ],
    "next_run": "2025-08-05T08:00:00.000000"
  }
}
```

### PUT /admin/scheduler/schedules/{schedule_id}
更新调度任务配置。

**请求体：**
```json
{
  "name": "每日新闻抓取（更新版）",
  "description": "每天早上8点和下午2点抓取新闻内容",
  "cron_expression": "0 8,14 * * *",
  "scraper_config": {
    "name": "news_scraper",
    "fetch_params": {"limit": 30}
  }
}
```

### DELETE /admin/scheduler/schedules/{schedule_id}
删除调度任务。

**响应示例：**
```json
{
  "status": "success",
  "message": "Schedule deleted successfully",
  "schedule_id": "daily-news-001"
}
```

### POST /admin/scheduler/schedules/{schedule_id}/enable
启用调度任务。

### POST /admin/scheduler/schedules/{schedule_id}/disable
禁用调度任务。

### POST /admin/scheduler/schedules/{schedule_id}/run-now
立即执行调度任务（不影响正常调度）。

**响应示例：**
```json
{
  "status": "success",
  "message": "Schedule executed immediately",
  "task_id": "manual-task-789",
  "schedule_id": "daily-news-001"
}
```

### POST /admin/scheduler/start
启动调度器。

**响应示例：**
```json
{
  "status": "success",
  "message": "Scheduler started successfully",
  "scheduler_status": {
    "is_running": true,
    "start_time": "2025-08-04T12:05:00.123456",
    "active_schedules": 3
  }
}
```

### POST /admin/scheduler/stop
停止调度器。

**响应示例：**
```json
{
  "status": "success",
  "message": "Scheduler stopped successfully",
  "scheduler_status": {
    "is_running": false,
    "stop_time": "2025-08-04T12:10:00.123456",
    "uptime_seconds": 300
  }
}
```

### POST /admin/scheduler/restart
重启调度器。

**响应示例：**
```json
{
  "status": "success",
  "message": "Scheduler restarted successfully",
  "scheduler_status": {
    "is_running": true,
    "start_time": "2025-08-04T12:15:00.123456",
    "previous_uptime_seconds": 300
  }
}
```

## 运行时控制接口

### POST /admin/cache/clear
清除各种缓存。

**请求体：**
```json
{
  "cache_types": ["health", "contents", "task_results"]  // 可选，默认清除 health 和 contents
}
```

**响应示例：**
```json
{
  "status": "success",
  "message": "Cache cleared successfully",
  "cleared_caches": [
    "health_check_cache",
    "fetched_contents_cache (15 items)",
    "task_manager_old_results"
  ],
  "timestamp": "2025-07-19T12:05:00.123456"
}
```

### POST /admin/runtime/gc
强制垃圾回收。

**响应示例：**
```json
{
  "status": "success",
  "message": "Garbage collection completed",
  "results": {
    "objects_collected": 42,
    "memory_before_mb": 150.2,
    "memory_after_mb": 128.5,
    "memory_freed_mb": 21.7
  },
  "timestamp": "2025-07-19T12:05:00.123456"
}
```

### GET /admin/runtime/config-watcher
获取配置监控器状态。

### POST /admin/runtime/config-watcher
控制配置监控器。

**请求体：**
```json
{
  "action": "restart"  // "start" | "stop" | "restart"
}
```

## 调试接口

### POST /admin/debug/dump-state
导出完整的服务状态信息（用于调试）。

**请求体：**
```json
{
  "include_sensitive": false,    // 是否包含敏感信息（如API密钥）
  "include_task_details": true   // 是否包含详细的任务管理器信息
}
```

## 安全注意事项

1. **生产环境访问控制**: 所有管理接口都应该配置适当的认证和授权机制
2. **敏感信息保护**: 避免在日志或响应中暴露API密钥等敏感信息
3. **操作审计**: 记录所有管理操作，特别是配置变更和热更新
4. **网络隔离**: 建议将管理接口与业务接口分离或使用内网访问

## 使用最佳实践

1. **监控指标**: 定期检查 `/admin/monitoring/metrics` 获取系统健康状态
2. **配置管理**: 使用 `/admin/config/hotreload` 实现零停机配置更新
3. **性能优化**: 利用 `/admin/cache/clear` 和 `/admin/runtime/gc` 优化内存使用
4. **故障排查**: 使用 `/admin/debug/dump-state` 和任务管理接口诊断问题
5. **抓取器测试**: 在生产部署前使用 `/admin/scrapers/{name}/test` 验证配置
6. **调度器管理**: 
   - 使用 `/admin/scheduler/status` 监控调度器健康状态
   - 通过环境变量配置调度器参数以提高灵活性
   - 定期检查调度任务的成功率和执行时间
   - 使用 `/admin/scheduler/schedules/{id}/run-now` 测试调度任务
   - 合理设置 `MAX_CONCURRENT_SCHEDULES` 避免资源竞争

## 兼容性说明

- 任务管理相关接口仅在启用任务管理器时可用
- 调度器管理相关接口仅在启用调度器时可用（通过环境变量 `ENABLE_SCHEDULER=true` 控制）
- 某些功能依赖于 ConfigManager 和 NotionClient 的正常工作
- 调试接口可能会暴露敏感信息，建议仅在开发环境或安全环境中使用
- 调度器功能需要有效的cron表达式，支持标准的五字段格式（分 时 日 月 周）
