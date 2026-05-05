---
name: github-trending
description: >
  抓取 GitHub Trending 页面并过滤 AI/LLM/Agent 相关的热门开源项目，输出 JSON 数组。
  Use when user wants to: get trending GitHub projects, find popular AI/LLM/Agent repositories, 
  fetch GitHub trending data, scrape GitHub trending page, collect trending repositories, 
  get hot GitHub projects, find trending AI projects, monitor GitHub trends, 
  track popular open source projects, discover trending machine learning repositories,
  get GitHub trending AI projects, find LLM repositories, collect Agent projects,
  scrape GitHub trending page for AI projects, monitor AI/ML trends on GitHub.
allowed-tools:
  - WebFetch
  - Bash
  - Read
---

# GitHub Trending 采集技能

## 使用场景

当需要从 GitHub Trending 页面获取当前热门的 AI/LLM/Agent 相关开源项目时使用此技能。适用于：
- 每日技术情报采集
- 追踪 AI 领域最新项目动态
- 为知识库提供原始数据输入

## 执行步骤

### 1. 获取 GitHub Trending 页面

通过 HTML 解析获取 GitHub Trending 页面：
- 使用 WebFetch 工具访问 `https://github.com/trending`
- 解析 HTML 内容，提取仓库信息
- 不使用 GitHub API（避免 rate limit 限制）

### 2. 提取 Top 50 项目

从 HTML 中提取前 50 个热门项目：
- 解析 `<article>` 标签中的仓库信息
- 提取以下字段：
  - `name`：仓库名称（owner/repo 格式）
  - `url`：项目链接（完整 GitHub URL）
  - `stars`：星标数（当前星标数）
  - `topics`：项目标签列表（从仓库页面提取）
  - `description`：项目描述（英文原文）

### 3. 过滤相关项目

按以下规则筛选 AI/LLM/Agent 相关项目：
- **纳入条件**：项目 topics 包含以下关键词之一（不区分大小写）：
  - `ai`, `artificial-intelligence`
  - `llm`, `large-language-models`
  - `agent`, `agents`
  - `ml`, `machine-learning`
  - `deep-learning`, `neural-network`
  - `gpt`, `transformer`
  - `rag`, `embedding`
  - `langchain`, `llamaindex`
  - `autogen`, `crewai`

### 4. 输出 JSON 数组

将过滤后的项目输出为 JSON 数组：
- 输出到 stdout，不写入文件
- 失败时返回空数组 `[]`，不抛异常
- 输出必须通过 JSON Schema 验证（schema 定义见 [schema.json](schema.json)）

## 输出格式

```json
[
  {
    "name": "langchain-ai/langgraph",
    "url": "https://github.com/langchain-ai/langgraph",
    "stars": 12500,
    "topics": ["langchain", "agent", "graph", "multi-agent"],
    "description": "Library for building stateful, multi-actor applications with LLMs"
  }
]
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | ✓ | 仓库名称（owner/repo 格式） |
| `url` | string | ✓ | 项目 GitHub 链接 |
| `stars` | integer | ✓ | 星标数 |
| `topics` | array | ✓ | 项目标签列表 |
| `description` | string | ✓ | 项目描述（英文原文） |

## 性能要求

- 单次执行时间 < 10 秒
- 网络请求超时设置：5 秒
- 解析超时设置：3 秒

## 错误处理

- 网络请求失败：返回空数组 `[]`
- HTML 解析失败：返回空数组 `[]`
- 任何异常：捕获并返回空数组 `[]`，不抛异常

## 验证方式

1. 调用技能：`skill-invoke github-trending`
2. 检查输出是否为有效 JSON 数组
3. 检查每个项目是否包含所有必填字段
4. 检查过滤是否正确（只包含 AI/LLM/Agent 相关项目）
5. 检查执行时间是否 < 10 秒