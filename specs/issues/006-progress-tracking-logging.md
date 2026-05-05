# 进度追踪与结构化日志：阶段级状态 + 最终摘要报告

| 字段 | 值 |
|------|-----|
| 类型 | AFK |
| 标签 | needs-triage |
| 阻塞 | #4 端到端管线串联 |

## Parent

`specs/agents-prd.md`

## What to build

为管线每个阶段实现结构化进度追踪和日志输出：collector/analyzer/organizer 各阶段输出 started/completed/failed 事件及计数；管线结束时输出完整摘要报告。

端到端行为：管线执行全程 → 每阶段输出结构化日志 → 完成后打印摘要报告 → 所有日志使用 Python `logging` 模块。

## Acceptance criteria

- [ ] 每阶段开始时输出 `STARTED` 日志（含阶段名、时间戳）
- [ ] 每阶段完成时输出 `COMPLETED` 日志（含处理条目数、耗时）
- [ ] 每阶段失败时输出 `FAILED` 日志（含失败原因、失败条目数）
- [ ] 管线结束输出最终摘要：total / new / skipped / failed / duration
- [ ] 日志级别按需配置（DEBUG/INFO/WARNING/ERROR），默认 INFO
- [ ] 严禁使用 `print()` 或 `sys.stdout.write()` 输出日志
- [ ] 日志格式含时间戳、模块名、级别

## Blocked by

- #4 端到端管线串联
