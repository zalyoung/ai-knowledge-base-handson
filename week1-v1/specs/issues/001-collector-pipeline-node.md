# Collector 管线节点：抓取 → 过滤 → 写入 raw JSON

| 字段 | 值 |
|------|-----|
| 类型 | AFK |
| 标签 | needs-triage |
| 阻塞 | 无 |

## Parent

`specs/agents-prd.md`

## What to build

实现 LangGraph 管线中 collector 节点：调用 collector agent（`.opencode/agents/collector.md`），抓取 GitHub Trending + Hacker News 当日 AI/LLM/Agent 相关内容，过滤后输出结构化 JSON 到 `knowledge/raw/YYYY-MM-DD.json`。

端到端行为：管线触发 → WebFetch GitHub Trending API / HN API → 按 AI 关键词过滤 → 排序 → 写入 raw JSON 文件。

## Acceptance criteria

- [ ] LangGraph 节点可独立执行，完成 GitHub Trending + HN 双源抓取
- [ ] 输出文件 `knowledge/raw/YYYY-MM-DD.json` 包含 15+ 条有效条目
- [ ] 条目含 `title`、`url`、`source`、`popularity`、`summary` 五字段，无缺失
- [ ] 按 `popularity` 降序排序，`source` 字段枚举正确
- [ ] API 请求间隔 ≥ 30 秒（遵守 Rate Limiting）
- [ ] 部分源失败不阻断整体流程，缺失数据记录日志
- [ ] 使用 `logging` 模块输出日志，禁止 `print()`

## Blocked by

None - can start immediately
