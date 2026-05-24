# AI 知识库助手 — 自动化技术情报管线

每日从 GitHub Trending 和 Hacker News 抓取 AI/LLM/Agent 领域的热门项目与讨论，由大模型进行语义分析、去重和摘要生成，最终输出结构化的知识条目（JSON），并通过 MCP Server 供 AI 工具检索。

## 架构概览

```
                          ┌──────────────┐
                          │   Planner    │  动态规划采集策略
                          │  lite/std/full│  (target_count → tier)
                          └──────┬───────┘
                                 ▼
┌────────────┐    ┌────────────────────────┐    ┌──────────────┐
│  GitHub    │───▶│     Collect (采集)      │───▶│  Analyze     │
│  Search API│    │  GitHub + RSS(HN)      │    │  LLM 语义分析 │
└────────────┘    └────────────────────────┘    └──────┬───────┘
                                                       ▼
                                              ┌──────────────┐
                                              │   Review      │
                                              │ 5 维度质量审核 │
                                              └──┬────┬───┬──┘
                                          pass │  │   │ fail×3
                                               ▼  │   ▼
                                     ┌──────────┐ │ ┌────────────┐
                                     │ Organize │ │ │ HumanFlag  │
                                     │ 去重+保存 │ │ │ 人工介入    │
                                     └──────────┘ │ └────────────┘
                                                  ▼
                                           ┌────────────┐
                                           │   Revise    │
                                           │  LLM 修正   │
                                           └────────────┘
```

**工作流节点**：`plan → collect → analyze → review → (organize | revise | human_flag)`

审核最多迭代 3 轮：通过则保存，未通过则由 LLM 修正后重新审核，3 轮仍未通过则转入人工介入。

## 目录结构

```
week3-v3/
├── AGENTS.md                        # Agent/Skill 职责定义
├── opencode.json                    # MCP Server 配置
├── requirements.txt                 # Python 依赖
├── cost_comparison.md               # 模型成本对比报告
│
├── workflows/                       # LangGraph 工作流（核心）
│   ├── state.py                     #   共享状态 TypedDict (KBState)
│   ├── graph.py                     #   有向图组装 + 条件路由
│   ├── planner.py                   #   采集策略规划 (lite/standard/full)
│   ├── nodes.py                     #   collect / analyze / organize / save 节点
│   ├── reviewer.py                  #   5 维度质量审核节点
│   ├── reviser.py                   #   LLM 修正节点
│   ├── human_flag.py                #   人工介入兜底节点
│   └── model_client.py              #   统一 LLM 客户端 (DeepSeek/Xiaomi/OpenAI)
│
├── pipeline/                        # 独立流水线（非 LangGraph）
│   ├── pipeline.py                  #   四步流水线: 采集→分析→整理→保存
│   └── model_client.py              #   LLM 客户端 (pipeline 版)
│
├── patterns/                        # 多 Agent 设计模式
│   ├── supervisor.py                #   Supervisor 监督模式
│   └── router.py                    #   Router 路由模式 (两层意图分类)
│
├── hooks/                           # 质量保障钩子
│   ├── validate_json.py             #   JSON 结构校验
│   ├── check_quality.py             #   5 维度质量评分 (A/B/C)
│   └── tests/                       #   钩子单元测试 + 测试 fixtures
│
├── tests/                           # 测试
│   ├── eval_test.py                 #   LLM 评估测试 (pytest)
│   ├── cost_guard.py                #   预算守卫模块
│   └── security.py                  #   Agent 安全防护模块
│
├── mcp_knowledge_server.py          # MCP Server (JSON-RPC over stdio)
├── test_mcp_server.py               # MCP Server 测试
│
└── knowledge/                       # 数据存储
    ├── raw/                         #   原始采集数据
    └── articles/                    #   结构化知识条目
        ├── index.json               #     URL→ID 去重索引
        ├── github-YYYYMMDD-NNN.json #     GitHub 来源条目
        └── hn-YYYYMMDD-NNN.json     #     Hacker News 来源条目
```

## 核心模块

### 1. LangGraph 工作流 (`workflows/`)

基于 LangGraph 的有向图工作流，7 个节点通过共享状态 `KBState` 通信：

| 节点 | 职责 | 关键逻辑 |
|------|------|----------|
| **plan** | 采集策略规划 | 根据 target_count 选择 lite/standard/full 三档 |
| **collect** | 数据采集 | GitHub Search API，按关键词搜索 AI 仓库 |
| **analyze** | LLM 语义分析 | 生成中文标题、摘要(100-300字)、评分(1-10)、标签 |
| **review** | 质量审核 | 5 维度加权评分：摘要质量/技术深度/相关性/原创性/格式 |
| **revise** | LLM 修正 | 根据审核反馈修正分析结果 |
| **organize** | 整理输出 | 过滤低分(\<6)、URL 去重、生成标准 Article 格式 |
| **human_flag** | 人工介入 | 3 轮审核未通过时写入 `pending_review/` |

**条件路由** (`route_after_review`)：
- 审核通过 → `organize`
- 未通过且 iteration < 3 → `revise`（循环回 `review`）
- 未通过且 iteration >= 3 → `human_flag`

### 2. LLM 客户端 (`workflows/model_client.py`)

统一的 LLM 调用层，支持三家提供商通过环境变量切换：

| 提供商 | 环境变量 | 默认模型 | 输入价格 (元/百万token) |
|--------|----------|----------|------------------------|
| DeepSeek | `DEEPSEEK_API_KEY` | deepseek-v4-flash | 1.0 |
| Xiaomi | `XIAOMI_API_KEY` | mimo-v2.5 | 2.80 |
| OpenAI | `OPENAI_API_KEY` | gpt-4o-mini | 150.0 |

特性：指数退避重试 (3 次)、全局 `CostTracker` 成本追踪、`chat_json()` 自动解析 JSON 响应。

### 3. 多 Agent 模式 (`patterns/`)

**Supervisor 模式** (`supervisor.py`)：Worker 生成分析报告 → Supervisor 质量审核 → 不通过则 Worker 根据反馈重做，最多重试 3 轮。

**Router 模式** (`router.py`)：两层意图分类：
- Layer 1：关键词匹配（零成本，无 LLM 调用）
- Layer 2：LLM 分类兜底

支持三种意图：`github_search` / `knowledge_query` / `general_chat`

### 4. MCP Server (`mcp_knowledge_server.py`)

基于 JSON-RPC 2.0 over stdio 协议的 MCP 服务端，提供 3 个工具：

| 工具 | 功能 |
|------|------|
| `search_articles` | 按关键词搜索知识库文章 |
| `get_article` | 按 ID 获取文章完整内容 |
| `knowledge_stats` | 获取知识库统计信息 |

通过 `opencode.json` 配置，可被 OpenCode 等 AI 工具直接调用。

### 5. 质量保障 (`hooks/`)

**validate_json.py**：校验知识条目 JSON 结构（必填字段、ID 格式、URL 格式、摘要长度、标签数量、评分范围）。

**check_quality.py**：5 维度质量评分（满分 100）：

| 维度 | 满分 | 评分逻辑 |
|------|------|----------|
| 摘要质量 | 25 | 长度 + 技术关键词密度 |
| 技术深度 | 25 | 映射自 score 字段 |
| 格式规范 | 20 | 必填字段完整性 |
| 标签精度 | 15 | 有效标签数 + 格式校验 |
| 空洞词检测 | 15 | 检测中英文空洞词并扣分 |

等级：A (≥80) / B (≥60) / C (\<60)

### 6. 安全防护 (`tests/security.py`)

生产级 Agent 安全防护模块：

| 能力 | 说明 |
|------|------|
| 输入清洗 | 26 条中英 Prompt 注入检测正则 + 5 类 PII 模式 + 控制字符清除 |
| 输出过滤 | PII 检测与 `[TYPE_MASKED]` 掩码替换，重叠匹配去重 |
| 速率限制 | 滑动窗口限流器 (`RateLimiter`) |
| 审计日志 | `AuditLogger` 支持 input/output/security 事件记录与 JSON 导出 |

### 7. 预算守卫 (`tests/cost_guard.py`)

LLM 调用成本追踪与预算保护：记录 token 用量、按节点分组统计、接近预算时预警、超出预算时抛出 `BudgetExceededError`。

## 快速开始

### 环境准备

```bash
# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 配置环境变量

```bash
# LLM 提供商 (deepseek / xiaomi / openai)
export LLM_PROVIDER=deepseek

# API 密钥（按所选提供商设置一个即可）
export DEEPSEEK_API_KEY=your_key
# export XIAOMI_API_KEY=your_key
# export OPENAI_API_KEY=your_key

# 可选：GitHub Token（提高 API 速率限制）
export GITHUB_TOKEN=your_github_token
```

### 运行方式

**方式 1：LangGraph 工作流**

```bash
python workflows/graph.py
```

**方式 2：独立流水线**

```bash
# 完整流水线
python pipeline/pipeline.py --sources github,rss --limit 20

# 干跑模式（只采集不分析）
python pipeline/pipeline.py --sources github --limit 5 --dry-run

# 指定模型
python pipeline/pipeline.py --limit 5 --provider xiaomi --model mimo-v2.5-pro
```

**方式 3：MCP Server**

```bash
# 启动 MCP Server（供 AI 工具调用）
python mcp_knowledge_server.py
```

**方式 4：多 Agent 模式测试**

```bash
# Supervisor 监督模式
python patterns/supervisor.py "分析 LangGraph 的技术特点"

# Router 路由模式
python patterns/router.py "github上有什么新项目"
```

## 测试

```bash
# 运行全部测试
pytest tests/ -v

# 跳过需要 LLM 的测试
pytest tests/ -v -m "not slow"

# 运行安全模块自测
python tests/security.py

# 运行预算守卫自测
python tests/cost_guard.py

# JSON 校验
python hooks/validate_json.py knowledge/articles/*.json

# 质量评分
python hooks/check_quality.py knowledge/articles/*.json
```

## 知识条目格式

每条知识条目为独立 JSON 文件：

```json
{
  "id": "github-20260524-001",
  "title": "RAGFlow：融合Agent能力的开源RAG引擎",
  "source_url": "https://github.com/infiniflow/ragflow",
  "source_type": "github_trending",
  "summary": "RAGFlow 是一款领先的开源检索增强生成（RAG）引擎……",
  "tags": ["rag", "llm-apps", "agentic-ai"],
  "score": 9,
  "published_at": "2023-12-12T06:13:13Z",
  "fetched_at": "2026-05-24T06:49:05Z",
  "analyzed_at": "2026-05-24T06:49:42Z",
  "status": "published"
}
```

ID 格式：`{source}-{YYYYMMDD}-{NNN}`，其中 source 为 `github` 或 `hn`。

## 技术栈

| 类别 | 技术 |
|------|------|
| 运行时 | Python 3.12+ |
| 工作流引擎 | LangGraph |
| HTTP 客户端 | httpx / urllib |
| 数据存储 | 本地 JSON 文件 |
| MCP 协议 | JSON-RPC 2.0 over stdio |
| LLM 提供商 | DeepSeek / Xiaomi MiMo / OpenAI |
