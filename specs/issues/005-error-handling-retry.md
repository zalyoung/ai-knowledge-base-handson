# 容错与重试策略：指数退避 + 部分失败容忍 + 状态恢复

| 字段 | 值 |
|------|-----|
| 类型 | AFK |
| 标签 | needs-triage |
| 阻塞 | #4 端到端管线串联 |

## Parent

`specs/agents-prd.md`

## What to build

为管线三个节点实现统一容错机制：collector 阶段对外部 API 采用指数退避重试；analyzer 阶段 LLM 调用失败时标记 draft 保留原始数据；organizer 阶段文件写入与索引更新视为原子事务；全管线支持部分失败容忍和断点续跑。

端到端行为：任何阶段遇到临时故障 → 按策略重试 → 超过最大重试则降级处理 → 记录详细错误日志 → 不影响其他阶段继续。

## Acceptance criteria

- [ ] Collector：GitHub API / HN API 请求采用指数退避重试（初始 1s，最大 3 次）
- [ ] Collector：部分源失败不影响另一源（如 GitHub 挂了，HN 照常采集）
- [ ] Analyzer：LLM 调用失败时标记条目 `status: draft`，保留原始数据供下次重试
- [ ] Organizer：文件写入与 index.json 更新为原子事务——任一失败则回滚
- [ ] 重试过程中使用 `logging` 记录每次重试的等待时间和原因
- [ ] 管线不因单点故障完全中断

## Blocked by

- #4 端到端管线串联
