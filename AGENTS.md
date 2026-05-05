# AGENTS.md

## 项目概述

AI 知识库助手 —— 自动化技术情报管线。每日从 GitHub Trending 和 Hacker News 抓取 AI/LLM/Agent 领域的热门项目与讨论，由大模型进行语义分析、去重和摘要生成，最终输出结构化的知识条目（JSON）。分析结果通过 Telegram 和飞书双渠道推送，帮助团队高效追踪 AI 领域前沿动态。

## 技术栈

- **运行时**：Python 3.12
- **AI 编排**：OpenCode（Agent 框架）+ 国产大模型
- **工作流引擎**：LangGraph
- **多渠道分发**：OpenClaw（统一消息推送层）
- **数据存储**：本地 JSON 文件（knowledge/raw/ → knowledge/articles/）
- **虚拟环境和包管理**：必须使用虚拟环境运行项目，禁止直接使用系统级 Python 解释器。创建命令：`python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`。

## 编码规范

- 严格遵循 [PEP 8](https://peps.python.org/pep-0008/)。
- 命名约定：变量/函数/方法使用 `snake_case`，类名使用 `PascalCase`，常量使用 `UPPER_SNAKE_CASE`。
- 所有公共函数/方法必须包含 [Google 风格 docstring](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings)（含 `Args`、`Returns`、`Raises` 段落）。
- 禁止使用裸 `print()` 输出日志，统一使用 `logging` 模块。
- 类型注解：所有函数签名必须包含完整的类型标注。
- 每行不超过 100 字符，缩进使用 4 个空格。

## 项目结构

```
ai-knowledge-base/
├── AGENTS.md                    # 本文件
├── .opencode/
│   ├── agents/                  # Agent 角色定义（.yml 或 .md）
│   ├── skills/                  # Skill 定义（采集/分析/发布等）
│   └── .gitignore
└── knowledge/
    ├── raw/                     # 原始采集数据（未处理）
    └── articles/                # AI 分析后的结构化知识条目
        └── index.json           # 去重索引（source_url → id 映射）
```

## 知识条目 JSON 格式

每一条经过分析的知识条目存储为一个独立的 JSON 文件，字段定义如下：

```json
{
  "id": "c8a7b3f1-4d2e-4a9b-b8c6-1f3e5a7b9d0c",
  "title": "LangGraph v0.3 发布：支持多 Agent 协同",
  "source_url": "https://github.com/langchain-ai/langgraph/releases/tag/v0.3.0",
  "source_type": "github_trending",
  "summary": "LangGraph 在 v0.3 中引入了 SupervisorAgent 模式，允许多个子 Agent 在统一调度下并行执行……",
  "tags": ["langgraph", "multi-agent", "orchestration"],
  "published_at": "2026-05-02T08:30:00Z",
  "fetched_at": "2026-05-02T09:00:00Z",
  "analyzed_at": "2026-05-02T09:15:00Z",
  "status": "published"
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `str` | UUID v4，全局唯一标识 |
| `title` | `str` | 中文标题（由 AI 生成，准确概括内容） |
| `source_url` | `str` | 原始来源链接 |
| `source_type` | `str` | 来源类型，枚举值：`github_trending` / `hackernews` |
| `summary` | `str` | AI 生成的摘要（100-300 字，突出技术亮点和适用场景） |
| `tags` | `List[str]` | 标签列表（3-8 个，小写英文） |
| `published_at` | `str` | 原文发布时间（ISO 8601） |
| `fetched_at` | `str` | 采集时间（ISO 8601） |
| `analyzed_at` | `str` | AI 分析完成时间（ISO 8601） |
| `status` | `str` | 状态，枚举值：`draft` / `published` / `archived` |

## Agent 角色概览

| 角色名称 | 文件位置 | 职责 | 输入 | 输出 |
|---------|---------|------|------|------|
| **采集 Agent** | `.opencode/agents/collector.md` | 调用 GitHub Trending API 和 Hacker News API 抓取当日热门内容，按 AI/LLM/Agent 关键词过滤 | 无（定时触发） | `knowledge/raw/YYYY-MM-DD.json` |
| **分析 Agent** | `.opencode/agents/analyzer.md` | 对原始数据进行去重（基于 URL）、语义分析、摘要生成、标签分类 | `knowledge/raw/YYYY-MM-DD.json` | `knowledge/articles/{id}.json` |
| **发布 Agent** | `.opencode/agents/publisher.md` | 从 `knowledge/articles/` 读取 `status: published` 的条目，通过 OpenClaw 分发至 Telegram 和飞书 | `knowledge/articles/*.json` | Telegram 消息 + 飞书卡片消息 |

## 数据流转

```
采集 Agent                      分析 Agent                      发布 Agent
     │                               │                               │
     ├─ 抓取 GitHub/HN          ├─ 读取 raw/YYYY-MM-DD.json          │
     ├─ 关键词过滤              ├─ 基于 index.json 去重              │
     ├─ 写入 raw/               ├─ LLM 生成摘要/标签                │
     │                          ├─ 写入 articles/{id}.json          │
     │                          │   （status: draft）               │
     │                          │               ↓                   │
     │                          │         人工确认                   │
     │                          │   draft → published               │
     │                          │               ↓                   │
     │                          │               └─────────────────> ├─ 读取 published 条目
     │                          │                                   ├─ 生成预览摘要
     │                          │                                   └─ 推送 Telegram + 飞书
```

### 去重机制

写入 `knowledge/articles/` 前，必须检查 `knowledge/articles/index.json`：若 `source_url` 已存在则跳过，不存在则追加条目并更新索引。

### 状态流转

| 状态 | 含义 | 由谁设置 |
|------|------|---------|
| `draft` | 分析 Agent 产出，待人工确认 | 分析 Agent |
| `published` | 人工确认通过，允许发布 | 人工操作 |
| `archived` | 已发布历史条目 | 发布 Agent（发布后自动归档） |

### 错误处理

- **外部 API 调用失败**（GitHub Trending / Hacker News）：允许部分源失败，不阻断整体流程，缺失数据记录日志即可。
- **LLM 调用失败**：将对应条目标记为 `status: draft`，保留原始数据，下次执行时重试。
- **重试策略**：对外部 API 请求采用指数退避重试。

## 红线（绝对禁止）

1. **禁止将凭证写入代码**。API Key、Webhook URL、Bot Token 等敏感信息必须通过环境变量或 `.env` 文件加载，且 `.env` 文件不得提交到 Git。
2. **禁止跳过去重逻辑**。在写入 `knowledge/articles/` 之前，必须基于 `source_url` 检查是否已存在，避免重复存储和分析。
3. **禁止对同一来源发起高频请求**。采集 Agent 对各 API 的请求间隔不得小于 30 秒，遵守 Rate Limiting 规范。
4. **禁止直接修改 `knowledge/articles/` 中的文件**。所有对知识条目的修改必须通过分析 Agent 完成，以保持数据一致性和审计追溯。
5. **禁止在生产环境中使用裸 `print()` 或 `sys.stdout.write()` 输出日志**。统一使用 `logging` 模块，日志级别按需配置。
6. **禁止在未经人工确认的情况下自动发布**。发布 Agent 在执行分发前必须生成预览摘要，由人工确认后再推送至外部渠道。
