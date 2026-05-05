---
name: github-trending
description: 当需要采集 GitHub 热门开源项目时使用此技能
allowed-tools:
  - Read
  - Grep
  - Glob
  - WebFetch
---

# GitHub Trending 采集技能

## 使用场景

当需要从 GitHub 获取当前热门的 AI/LLM/Agent 相关开源项目时使用此技能。适用于：
- 每日技术情报采集
- 追踪 AI 领域最新项目动态
- 为知识库提供原始数据输入

## 执行步骤

### 1. 搜索热门仓库

通过 GitHub API 获取当日热门项目：
- 使用 WebFetch 工具访问 `https://api.github.com/search/repositories`
- 查询参数：`q=stars:>1000+pushed:>YYYY-MM-DD&sort=stars&order=desc`
- 获取最近一周内活跃且星标数超过 1000 的仓库

### 2. 提取信息

从 API 返回的 JSON 中提取关键字段：
- `name`：仓库名称
- `full_name`：完整路径（owner/repo）
- `html_url`：项目链接
- `description`：项目描述
- `stargazers_count`：星标数
- `language`：主要编程语言
- `topics`：项目标签列表
- `created_at`：创建时间
- `pushed_at`：最后推送时间

### 3. 过滤相关项目

按以下规则筛选：
- **纳入条件**：项目描述或标题包含以下关键词之一（不区分大小写）：
  - `AI`, `LLM`, `GPT`, `Claude`, `Gemini`, `agent`, `RAG`, `embedding`
  - `transformer`, `diffusion`, `fine-tune`, `inference`, `prompt`
  - `langchain`, `llamaindex`, `autogen`, `crewai`
- **排除条件**：
  - Awesome 列表类项目（标题包含 "awesome"）
  - 教程和课程类项目（标题包含 "tutorial", "course", "learn"）
  - 纯资源汇总项目

### 4. 去重检查

- 读取 `knowledge/raw/` 目录下最近 7 天的 JSON 文件
- 基于 `html_url` 字段进行去重
- 跳过已存在项目的采集

### 5. 撰写中文摘要

为每个项目生成中文摘要，遵循公式：

**项目名 + 做什么 + 为什么值得关注**

示例：
> LangGraph：基于 LangChain 的有状态多 Agent 编排框架，通过有向图定义 Agent 间协作流程，支持循环和条件分支，适合构建复杂对话系统。

要求：
- 摘要长度：50-150 字
- 突出技术亮点和应用场景
- 使用简洁专业的技术语言

### 6. 排序取 Top15

- 按星标数（stargazers_count）降序排列
- 取前 15 个项目作为最终输出
- 确保每个项目的质量和相关性

### 7. 输出 JSON 文件

将采集结果写入 `knowledge/raw/github-trending-YYYY-MM-DD.json`

## 注意事项

1. **API 限制**：GitHub API 未认证请求限制为每小时 60 次，注意控制请求频率
2. **时间范围**：采集最近 7 天内有活动的项目，确保数据时效性
3. **错误处理**：API 请求失败时记录日志，不阻断整体流程
4. **编码规范**：摘要使用 UTF-8 编码，确保中文字符正确显示
5. **文件命名**：日期格式为 YYYY-MM-DD，使用当天实际日期

## 输出格式

```json
{
  "source": "github_trending",
  "skill": "github-trending",
  "collected_at": "2026-05-05T09:00:00Z",
  "items": [
    {
      "name": "langgraph",
      "url": "https://github.com/langchain-ai/langgraph",
      "summary": "LangGraph：基于 LangChain 的有状态多 Agent 编排框架，通过有向图定义 Agent 间协作流程，支持循环和条件分支，适合构建复杂对话系统。",
      "stars": 12500,
      "language": "Python",
      "topics": ["langchain", "agent", "graph", "multi-agent"]
    }
  ]
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `source` | string | ✓ | 固定值 `github_trending` |
| `skill` | string | ✓ | 技能名称 `github-trending` |
| `collected_at` | string | ✓ | 采集时间 ISO 8601 格式 |
| `items` | array | ✓ | 项目列表，最多 15 项 |
| `items[].name` | string | ✓ | 仓库名称 |
| `items[].url` | string | ✓ | 项目 GitHub 链接 |
| `items[].summary` | string | ✓ | 中文摘要（50-150 字） |
| `items[].stars` | integer | ✓ | 星标数 |
| `items[].language` | string | ✓ | 主要编程语言 |
| `items[].topics` | array | ✓ | 项目标签列表 |
