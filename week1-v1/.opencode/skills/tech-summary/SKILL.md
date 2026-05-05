---
name: tech-summary
description: 当需要对采集的技术内容进行深度分析总结时使用此技能
allowed-tools:
  - Read
  - Grep
  - Glob
  - WebFetch
---

# 技术内容深度分析技能

## 使用场景

当需要对已采集的 GitHub Trending 等原始数据进行深度分析、提炼技术亮点、评估项目价值时使用此技能。适用于：
- 从原始采集数据生成结构化分析报告
- 发现技术趋势和新兴概念
- 为发布渠道提供高质量内容

## 执行步骤

### 1. 读取最新采集文件

- 使用 Glob 工具查找 `knowledge/raw/` 目录下最新的 JSON 文件
- 优先级：`github-trending-YYYY-MM-DD.json` > 其他日期文件
- 使用 Read 工具读取文件内容，获取 `items` 数组

### 2. 逐条深度分析

对每个项目进行以下维度的分析：

#### 摘要生成（≤50 字）
- 精炼概括项目核心功能
- 示例：`LangGraph：有状态多 Agent 编排框架，支持图定义复杂协作流程`

#### 技术亮点提取（2-3 个）
- 使用事实描述，避免主观评价
- 格式：`[亮点名称]：具体技术实现或创新点`
- 示例：
  - `[图编排]：基于有向无环图定义 Agent 间协作流程`
  - `[状态管理]：内置持久化层支持对话中断恢复`

#### 评分（1-10 分）
- 按照评分标准打分
- 必须附带评分理由（1-2 句话）

#### 标签建议（3-5 个）
- 使用小写英文标签
- 优先复用已有标签库
- 示例：`langgraph`, `multi-agent`, `orchestration`

### 3. 趋势发现

分析所有项目的共同特征：

#### 共同主题
- 识别多个项目涉及的技术方向
- 示例：`多 Agent 协作成为主流，8/15 个项目涉及 Agent 编排`

#### 新兴概念
- 提取首次出现或快速兴起的技术概念
- 示例：`MCP（Model Context Protocol）首次进入 Top15，可能成为 Agent 工具调用新标准`

#### 生态变化
- 观察工具链和依赖关系的变化
- 示例：`LangChain 生态项目占比下降，独立 Agent 框架增多`

### 4. 输出分析结果 JSON

将分析结果写入 `knowledge/articles/analysis-YYYY-MM-DD.json`

## 评分标准

| 分值范围 | 含义 | 判断依据 |
|---------|------|---------|
| **9-10** | 改变格局 | 可能重塑技术路线，具有里程碑意义 |
| **7-8** | 直接有帮助 | 解决实际问题，可立即应用于生产环境 |
| **5-6** | 值得了解 | 有创新点，但实用性或成熟度有限 |
| **1-4** | 可略过 | 意义不大或与其他项目高度重复 |

### 评分约束

- 15 个项目中，9-10 分项目**不超过 2 个**
- 确保评分分布合理，避免分数通胀

## 注意事项

1. **客观性**：技术亮点必须基于事实，使用项目实际功能描述，避免营销用语
2. **一致性**：标签命名保持统一，优先复用 `knowledge/articles/index.json` 中的已有标签
3. **时效性**：分析应结合当前技术热点，关注项目近期活跃度
4. **可追溯**：评分理由应具体，便于后续审核和调整
5. **编码规范**：所有文本使用 UTF-8 编码，中文摘要简洁专业

## 输出格式

```json
{
  "source": "github_trending",
  "skill": "tech-summary",
  "analyzed_at": "2026-05-05T10:00:00Z",
  "input_file": "knowledge/raw/github-trending-2026-05-05.json",
  "items": [
    {
      "name": "langgraph",
      "url": "https://github.com/langchain-ai/langgraph",
      "summary": "LangGraph：有状态多 Agent 编排框架，支持图定义复杂协作流程",
      "highlights": [
        "[图编排]：基于有向无环图定义 Agent 间协作流程",
        "[状态管理]：内置持久化层支持对话中断恢复"
      ],
      "score": 9,
      "score_reason": "重新定义多 Agent 编排范式，已被多家企业采用",
      "tags": ["langgraph", "multi-agent", "orchestration", "stateful"]
    }
  ],
  "trends": {
    "common_themes": [
      "多 Agent 协作成为主流，8/15 个项目涉及 Agent 编排"
    ],
    "emerging_concepts": [
      "MCP（Model Context Protocol）首次进入 Top15"
    ],
    "ecosystem_changes": [
      "LangChain 生态项目占比下降，独立 Agent 框架增多"
    ]
  }
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `source` | string | ✓ | 数据来源，固定值 `github_trending` |
| `skill` | string | ✓ | 技能名称 `tech-summary` |
| `analyzed_at` | string | ✓ | 分析时间 ISO 8601 格式 |
| `input_file` | string | ✓ | 输入文件路径 |
| `items` | array | ✓ | 分析结果列表 |
| `items[].name` | string | ✓ | 项目名称 |
| `items[].url` | string | ✓ | 项目链接 |
| `items[].summary` | string | ✓ | 精炼摘要（≤50 字） |
| `items[].highlights` | array | ✓ | 技术亮点（2-3 个） |
| `items[].score` | integer | ✓ | 评分（1-10） |
| `items[].score_reason` | string | ✓ | 评分理由 |
| `items[].tags` | array | ✓ | 标签建议（3-5 个） |
| `trends` | object | ✓ | 趋势分析 |
| `trends.common_themes` | array | ✓ | 共同主题 |
| `trends.emerging_concepts` | array | ✓ | 新兴概念 |
| `trends.ecosystem_changes` | array | ✓ | 生态变化 |
