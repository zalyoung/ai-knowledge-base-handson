# Analyzer 管线节点：读取 raw → 语义分析 → 输出增强数据

| 字段 | 值 |
|------|-----|
| 类型 | AFK |
| 标签 | needs-triage |
| 阻塞 | #1 Collector 管线节点 |

## Parent

`specs/agents-prd.md`

## What to build

实现 LangGraph 管线中 analyzer 节点：读取 `knowledge/raw/YYYY-MM-DD.json`，逐条调用 analyzer agent（`.opencode/agents/analyzer.md`）进行语义分析：通过 WebFetch 访问原文生成 100-300 字中文摘要、2-4 条技术亮点、1-10 分评级及理由、3-8 个建议标签。

端到端行为：raw JSON 输入 → 逐条 WebFetch 原文 → LLM 分析 → 输出增强数据（含 summary/highlights/score/suggested_tags）。

## Acceptance criteria

- [ ] 节点读取 `knowledge/raw/YYYY-MM-DD.json`，逐条处理
- [ ] 每条输出含完整增强字段：`summary`(100-300 字中文)、`highlights`(2-4 条)、`score`(1-10)、`score_reason`、`suggested_tags`(3-8 个小写英文)
- [ ] 评分在批次内有梯度分布，不集中在中间段
- [ ] WebFetch 失败时：保留原 summary，highlights 置空，score 标记 5
- [ ] LLM 调用失败时：条目标记 `status: draft`，保留原始数据
- [ ] 使用 `logging` 模块输出日志

## Blocked by

- #1 Collector 管线节点
