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

## Agent 与 Skill 的关系

### 设计原则

采用**方案 C：职责完全分离**，最大化激发 Agent 的自主性。

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent（决策层）                            │
│  回答：我是谁？能做什么？不能做什么？质量底线是什么？             │
├─────────────────────────────────────────────────────────────┤
│  • 角色定位：一句话说清职责                                    │
│  • 权限控制：allowed / forbidden tools                       │
│  • 质量红线：必须遵守的底线规则                                │
│  • 推荐 Skill：列出可搭配的 Skill（仅供参考，不约束）           │
│  ❌ 不包含：具体业务规则（评分标准、字数要求等）                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Skill（执行层）                            │
│  回答：什么时候用？怎么做？输出什么格式？                        │
├─────────────────────────────────────────────────────────────┤
│  • 使用场景：什么时候调用这个 Skill                            │
│  • 执行步骤：Step 1, 2, 3...                                 │
│  • 业务规则：评分标准、字数、数量等具体参数                      │
│  • 输出格式：JSON Schema                                     │
│  • 约束：业务相关限制（如评分分布）                             │
│  ❌ 不包含：权限控制、质量红线                                 │
└─────────────────────────────────────────────────────────────┘
```

### 职责边界

| 维度 | Agent 负责 | Skill 负责 |
|------|-----------|-----------|
| 角色定位 | ✅ 我是谁、负责什么 | ❌ |
| 权限控制 | ✅ 能用什么工具、禁止什么 | ❌ |
| 质量红线 | ✅ 底线规则（禁止编造等） | ❌ |
| 执行步骤 | ❌ | ✅ 具体怎么做 |
| 业务规则 | ❌ | ✅ 评分标准、字数、数量等 |
| 输出格式 | ❌ | ✅ JSON 结构定义 |
| 业务约束 | ❌ | ✅ 评分分布等 |

### 冲突解决

当 Agent 定义与 Skill 定义出现冲突时：
1. **调用时必须显式指定 Skill**，例如："使用 github-trending 技能采集"
2. **Skill 中的业务规则优先**于任何隐含的默认规则
3. **Agent 中的质量红线始终生效**，不可被 Skill 覆盖

### 目录结构

```
.opencode/
├── agents/                  # Agent 定义（决策层）
│   ├── collector.md         # 采集 Agent：角色 + 权限 + 红线
│   ├── analyzer.md          # 分析 Agent：角色 + 权限 + 红线
│   └── publisher.md         # 发布 Agent：角色 + 权限 + 红线
└── skills/                  # Skill 定义（执行层）
    ├── github-trending/     # GitHub 采集技能：步骤 + 规则 + 格式
    ├── tech-summary/        # 技术分析技能：步骤 + 规则 + 格式
    └── ...
```