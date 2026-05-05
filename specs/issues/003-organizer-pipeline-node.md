# Organizer 管线节点：去重 → 格式化 → 写入 articles + 更新 index.json

| 字段 | 值 |
|------|-----|
| 类型 | AFK |
| 标签 | needs-triage |
| 阻塞 | #2 Analyzer 管线节点 |

## Parent

`specs/agents-prd.md`

## What to build

实现 LangGraph 管线中 organizer 节点：接收 analyzer 输出的增强数据，执行去重检查（基于 `index.json`）、标准 JSON 格式化、分类存储到 `knowledge/articles/{date}-{source}-{slug}.json`，并原子更新 `index.json`。

端到端行为：增强数据输入 → 检查 index.json 去重 → 校验必填字段 → 格式化标准 JSON → 写入文件 → 更新 index.json → 返回统计摘要。

## Acceptance criteria

- [ ] 每条写入前必须通过 `index.json` 去重检查，`source_url` 已存在则跳过
- [ ] 写入文件格式符合 AGENTS.md 定义的知识条目 JSON 格式
- [ ] 文件命名：`{date}-{source}-{slug}.json`，slug ≤ 50 字符
- [ ] `id` 为有效 UUID v4，时间字段使用 ISO 8601 格式
- [ ] 写入文件与更新 `index.json` 为原子操作——文件写入成功但索引更新失败则回滚
- [ ] 返回统计摘要（total/new/skipped_duplicates/failed/files/index_updated）
- [ ] 所有条目 `status` 统一设为 `draft`
- [ ] 校验必填字段（title/source_url/source_type/summary）非空

## Blocked by

- #2 Analyzer 管线节点
