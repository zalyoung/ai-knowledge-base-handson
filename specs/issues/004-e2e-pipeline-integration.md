# 端到端管线串联：LangGraph StateGraph + 三节点数据流转

| 字段 | 值 |
|------|-----|
| 类型 | AFK |
| 标签 | needs-triage |
| 阻塞 | #3 Organizer 管线节点 |

## Parent

`specs/agents-prd.md`

## What to build

将 collector、analyzer、organizer 三个节点串入 LangGraph `StateGraph`，实现串行执行流水线：collector → analyzer → organizer。通过共享 State 在节点间传递数据，确保上游产出可被下游消费。

端到端行为：触发管线 → collector 抓取写入 raw → analyzer 读取 raw 输出增强数据 → organizer 去重写入 articles → 返回最终统计。

## Acceptance criteria

- [ ] 基于 LangGraph 构建 StateGraph，定义三个节点和串行边
- [ ] 定义共享 State 结构（TypedDict），含 raw_data / analyzed_data / organizer_result
- [ ] 节点间数据正确传递：collector 产物 → analyzer 输入，analyzer 产物 → organizer 输入
- [ ] 管线可端到端执行（从调用入口到 articles 文件落盘）
- [ ] 上游部分失败时，下游仍处理可用数据（不因部分缺失而中断）
- [ ] 执行完成后返回最终统计摘要

## Blocked by

- #3 Organizer 管线节点
