# OctopusService Scheduler Environment Variables

## Scheduler Configuration

The OctopusService now supports TaskScheduler functionality through environment variables.

### Basic Scheduler Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_SCHEDULER` | `False` | Enable/disable the TaskScheduler functionality |
| `AUTO_START_SCHEDULER` | `False` | Automatically start the scheduler when service starts |
| `MAX_CONCURRENT_SCHEDULES` | `10` | Maximum number of concurrent scheduled tasks |
| `SCHEDULE_CHECK_INTERVAL` | `60` | Interval (in seconds) for checking scheduled tasks |

### TaskManager Environment Variables (Always Enabled)

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_CONCURRENT_TASKS` | `8` | Maximum number of concurrent tasks |
| `MAX_QUEUE_SIZE` | `1000` | Maximum task queue size |
| `RESULT_RETENTION_HOURS` | `48` | How long to keep task results (hours) |

### Example Configuration

#### Enable Scheduler with Auto-start
```bash
export ENABLE_SCHEDULER=true
export AUTO_START_SCHEDULER=true
export MAX_CONCURRENT_SCHEDULES=5
export SCHEDULE_CHECK_INTERVAL=30
```

#### Enable Scheduler without Auto-start (Manual Control)
```bash
export ENABLE_SCHEDULER=true
export AUTO_START_SCHEDULER=false
```

#### Disable Scheduler (TaskManager Only)
```bash
export ENABLE_SCHEDULER=false
# or simply don't set ENABLE_SCHEDULER (defaults to false)
```

## Usage Examples

### 1. Docker Compose Configuration

```yaml
version: '3.8'
services:
  octopus-service:
    build: .
    environment:
      - ENABLE_SCHEDULER=true
      - AUTO_START_SCHEDULER=true
      - MAX_CONCURRENT_SCHEDULES=10
      - SCHEDULE_CHECK_INTERVAL=60
      - MAX_CONCURRENT_TASKS=8
      - NOTION_API_KEY=your_notion_api_key
      - NOTION_SCRAPERS_DATABASE_ID=your_database_id
    ports:
      - "8000:8000"
```

### 2. Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: octopus-service
spec:
  template:
    spec:
      containers:
      - name: octopus-service
        image: octopus-service:latest
        env:
        - name: ENABLE_SCHEDULER
          value: "true"
        - name: AUTO_START_SCHEDULER
          value: "true"
        - name: MAX_CONCURRENT_SCHEDULES
          value: "15"
        - name: SCHEDULE_CHECK_INTERVAL
          value: "45"
```

### 3. Development Environment

```bash
# .env file
ENABLE_SCHEDULER=true
AUTO_START_SCHEDULER=false
MAX_CONCURRENT_SCHEDULES=3
SCHEDULE_CHECK_INTERVAL=120
MAX_CONCURRENT_TASKS=4
DEBUG=true
LOG_LEVEL=DEBUG
```

## API Endpoints

Once the scheduler is enabled, the following API endpoints become available:

### Scheduler Management
- `GET /admin/scheduler/status` - Get scheduler status
- `POST /admin/scheduler/start` - Start the scheduler
- `POST /admin/scheduler/stop` - Stop the scheduler

### Schedule Management
- `GET /admin/scheduler/schedules` - List all schedules
- `POST /admin/scheduler/schedules` - Add a new schedule
- `GET /admin/scheduler/schedules/{schedule_id}` - Get specific schedule
- `DELETE /admin/scheduler/schedules/{schedule_id}` - Remove schedule
- `POST /admin/scheduler/schedules/{schedule_id}/enable` - Enable schedule
- `POST /admin/scheduler/schedules/{schedule_id}/disable` - Disable schedule
- `POST /admin/scheduler/schedules/{schedule_id}/trigger` - Trigger schedule manually

### Monitoring
- `GET /admin/monitoring/metrics` - Includes scheduler metrics when enabled

## Scheduler Behavior

### Auto-start Behavior
- When `ENABLE_SCHEDULER=true` and `AUTO_START_SCHEDULER=true`:
  - Scheduler is created and started automatically during service initialization
  - Service logs will show "TaskScheduler started automatically"

### Manual Control
- When `ENABLE_SCHEDULER=true` and `AUTO_START_SCHEDULER=false`:
  - Scheduler is created but not started
  - Use `POST /admin/scheduler/start` to start it manually
  - Use `POST /admin/scheduler/stop` to stop it

### Disabled Scheduler
- When `ENABLE_SCHEDULER=false` (default):
  - No scheduler functionality is available
  - Scheduler API endpoints will return appropriate error messages
  - TaskManager still operates normally for immediate tasks

## Monitoring and Health Checks

### Health Check Integration
The scheduler status is included in health checks:
- `/health` - Includes scheduler status in dependencies
- `/admin/monitoring/metrics` - Detailed scheduler metrics

### Log Messages
Key log messages to watch for:
```
TaskScheduler started automatically
TaskScheduler stopped and cleaned up
Octopus instance initialized successfully with TaskManager and optional Scheduler
```

## Best Practices

1. **Development**: Start with `AUTO_START_SCHEDULER=false` for manual control
2. **Production**: Use `AUTO_START_SCHEDULER=true` for automatic operation
3. **Resource Planning**: Monitor `MAX_CONCURRENT_SCHEDULES` vs actual usage
4. **Debugging**: Enable DEBUG logging to see scheduler operations
5. **Graceful Shutdown**: The service automatically stops the scheduler on shutdown
