# OctopusScraper 文档

[README](../README.md) 只介绍产品用途和首次运行流程。完整配置、接口、存储、
监控和架构说明放在本目录。

## 使用与配置

- [配置参考](configuration.md)：环境变量、scraper YAML、fetcher 和 processor。
- [HTTP API 与 MCP](api.md)：触发、健康检查、管理接口和只读 MCP 工具。

## 运行与维护

- [PostgreSQL 与 Notion 同步](storage.md)：schema、导出状态、租约、重试和恢复。
- [日志与监控](monitoring.md)：结构化日志、Prometheus 指标、Grafana 查询和
  Vector 告警。

## 开发与架构

- [系统架构](architecture.md)：进程启动、采集链路、配置热更新、任务调度、
  存储导出和优雅停机。
- [贡献指南](../CONTRIBUTING.md)：本地开发、测试和 Pull Request 流程。
- [Agent 指南](../AGENTS.md)：修改代码前必须遵守的工程约束。

## 文档归属

每类信息只保留一份完整说明：

- `README.md` 负责产品定位和最短使用路径。
- `configuration.md` 负责环境变量和 YAML 配置。
- `api.md` 负责 HTTP 与 MCP 接口。
- `architecture.md` 负责组件职责和运行机制。
- `storage.md` 负责持久化、迁移、租约和恢复。
- `monitoring.md` 负责日志、指标和告警。
- `CONTRIBUTING.md` 负责开发流程。

实现是运行行为的最终依据。环境变量默认值以
`internal/config/env.go` 为准，HTTP 路由以 `internal/httpapi/server.go`
为准，数据库版本以 `internal/storage/storage.go` 中的 `SchemaVersion`
为准。
