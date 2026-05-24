# AI 知识库系统

> 基于多 Agent 协作的 AI 技术知识库——自动采集、智能分析、定时推送

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

每日从 GitHub Trending 和 Hacker News 自动抓取 AI/LLM/Agent 领域的热门项目与讨论，由多 Agent 协作完成语义分析、质量审核和摘要生成，最终通过 Telegram 和飞书定时推送给团队。

---

## 架构概览

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Agent 层                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │
│  │  Collector    │  │  Analyzer    │  │  Publisher   │                  │
│  │  采集 Agent   │  │  分析 Agent   │  │  发布 Agent   │                  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                  │
│         │                 │                 │                           │
│         ▼                 ▼                 ▼                           │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    Supervisor / Router                           │   │
│  │              多 Agent 调度 & 意图路由                             │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Pipeline 层                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │    Plan       │  │   Collect    │  │   Analyze    │  │   Review   │ │
│  │  策略规划     │  │  数据采集     │  │  LLM 分析     │  │  质量审核   │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └────────────┘ │
│         │                 │                 │                 │        │
│         └─────────────────┴─────────────────┴─────────────────┘        │
│                                    │                                    │
│                           LangGraph 工作流                              │
│                   plan → collect → analyze → review                     │
│                            → organize / revise                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         工程层                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │  MCP Server   │  │ JSON Schema  │  │ 质量保障 Hooks│  │ 安全防护   │ │
│  │  知识检索     │  │  数据校验     │  │  5 维评分     │  │ PII 过滤   │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └────────────┘ │
│                                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │
│  │ LLM 客户端   │  │  预算守卫     │  │  审计日志     │                  │
│  │ 多模型切换   │  │  成本追踪     │  │  操作记录     │                  │
│  └──────────────┘  └──────────────┘  └──────────────┘                  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         分发层                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │  Telegram     │  │    飞书      │  │  Knowledge   │  │  定时任务   │ │
│  │  Bot API      │  │  Webhook     │  │  Bot 对话    │  │  Cron Job  │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └────────────┘ │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    OpenClaw 统一消息推送层                        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

**工作流节点**：`plan → collect → analyze → review → (organize | revise | human_flag)`

审核最多迭代 3 轮：通过则保存，未通过则由 LLM 修正后重新审核，3 轮仍未通过则转入人工介入。

---

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/your-org/ai-knowledge-base.git
cd ai-knowledge-base
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入以下配置：

```bash
# LLM 提供商 (deepseek / xiaomi / openai)
LLM_PROVIDER=deepseek

# API 密钥（按所选提供商设置一个即可）
DEEPSEEK_API_KEY=your_deepseek_key
# XIAOMI_API_KEY=your_xiaomi_key
# OPENAI_API_KEY=your_openai_key

# GitHub Token（提高 API 速率限制）
GITHUB_TOKEN=your_github_token

# Telegram Bot（可选）
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# 飞书 Webhook（可选）
FEISHU_WEBHOOK_URL=your_webhook_url
```

### 3. 启动服务

```bash
docker compose up -d
```

服务启动后：
- 知识库 Pipeline 每日自动运行
- MCP Server 可供 AI 工具调用
- Telegram/飞书 Bot 自动推送每日简报

---

## 目录结构

| 目录 | 说明 | 版本 |
|------|------|------|
| `week1-v1/` | 基础框架：Agent 定义、知识条目格式规范 | V1 |
| `week2-v2/` | MCP Server：知识库检索协议、GitHub Action 集成 | V2 |
| `week3-v3/` | LangGraph 工作流：多节点有向图、质量审核、安全防护 | V3 |
| `week4-v4/` | 分发系统：Telegram/飞书推送、Bot 对话、订阅管理 | V4 |
| `.opencode/` | Agent 和 Skill 定义（采集/分析/发布） | - |
| `.github/` | GitHub Action 工作流配置 | - |

### 核心模块说明

| 模块 | 路径 | 功能 |
|------|------|------|
| **LangGraph 工作流** | `*/workflows/` | 7 节点有向图：plan → collect → analyze → review → organize/revise/human_flag |
| **独立流水线** | `*/pipeline/` | 四步流水线：采集 → 分析 → 整理 → 保存 |
| **多 Agent 模式** | `*/patterns/` | Supervisor 监督模式 + Router 路由模式 |
| **MCP Server** | `*/mcp_knowledge_server.py` | JSON-RPC 2.0 over stdio，提供 3 个工具 |
| **质量保障** | `*/hooks/` | JSON 校验 + 5 维度质量评分（A/B/C） |
| **安全防护** | `*/tests/security.py` | Prompt 注入检测、PII 过滤、速率限制、审计日志 |
| **分发系统** | `*/distribution/` | Telegram Bot API + 飞书 Webhook 推送 |
| **Bot 对话** | `*/bot/` | 意图识别、订阅管理、三级权限控制 |

---

## 技术栈

| 类别 | 技术 | 说明 |
|------|------|------|
| **AI 编排** | OpenCode | Agent 框架，多 Agent 协作调度 |
| **工作流引擎** | LangGraph | 有向图工作流，支持条件路由和状态管理 |
| **大模型** | DeepSeek / Xiaomi MiMo / OpenAI | 统一 LLM 客户端，支持多模型切换 |
| **容器化** | Docker + Docker Compose | 一键部署，环境隔离 |
| **消息推送** | Telegram Bot API | MarkdownV2 格式消息推送 |
| **消息推送** | 飞书 Webhook | Interactive Card 卡片消息 |
| **知识检索** | MCP Server | JSON-RPC 2.0 over stdio 协议 |
| **HTTP 客户端** | httpx / aiohttp | 异步 HTTP 请求 |
| **数据存储** | 本地 JSON 文件 | 轻量级，易于版本控制 |
| **运行时** | Python 3.12+ | 类型注解、异步支持 |

---

## 版本历史

### V1 — 基础框架（Week 1）

**核心能力**：Agent 定义与知识条目规范

- 定义三个 Agent 角色：采集 Agent、分析 Agent、发布 Agent
- 建立知识条目 JSON 格式规范（id、title、summary、tags、score）
- 实现 Agent 与 Skill 职责分离设计
- 制定编码规范和红线规则

### V2 — MCP Server 与 CI/CD（Week 2）

**核心能力**：知识库检索协议与自动化集成

- 实现 MCP Server（JSON-RPC 2.0 over stdio）
- 提供 3 个工具：`search_articles`、`get_article`、`knowledge_stats`
- 集成 GitHub Action，实现自动测试和部署
- 支持通过 `opencode.json` 配置供 AI 工具调用

### V3 — LangGraph 工作流（Week 3）

**核心能力**：多节点有向图工作流与质量保障

- 基于 LangGraph 构建 7 节点有向图工作流
- 实现 5 维度质量审核：摘要质量、技术深度、相关性、原创性、格式
- 支持条件路由：审核通过 → 保存，未通过 → 修正/人工介入
- 集成安全防护：Prompt 注入检测、PII 过滤、速率限制
- 实现预算守卫：LLM 调用成本追踪与预算保护

### V4 — 分发系统（Week 4）

**核心能力**：多渠道推送与 Bot 对话

- 实现 Telegram Bot API 推送（MarkdownV2 格式）
- 实现飞书 Webhook 推送（Interactive Card 卡片）
- 开发 Knowledge Bot：意图识别、订阅管理、三级权限控制
- 统一异步推送入口，支持并发分发到多渠道
- 支持用户订阅关键词，定时推送匹配内容

---

## 月度成本估算

### 大模型成本

基于每日处理 50 条知识条目的估算：

| 模型 | 单条成本 | 日成本 | 月成本 | 适用场景 |
|------|----------|--------|--------|----------|
| **DeepSeek v4 Flash** | ¥0.001 | ¥0.05 | ¥1.50 | 日常批量处理（推荐） |
| **Xiaomi MiMo v2.5** | ¥0.025 | ¥1.25 | ¥37.50 | 深度分析场景 |
| **OpenAI gpt-4o-mini** | ¥0.15 | ¥7.50 | ¥225.00 | 高质量需求 |

**推荐方案**：日常使用 DeepSeek，重要条目使用 Xiaomi MiMo，月均成本约 **¥5-10**。

### 服务器成本

| 资源 | 配置 | 月成本 | 说明 |
|------|------|--------|------|
| **云服务器** | 2C4G | ¥50-100 | 运行 Docker 容器 |
| **GitHub API** | 免费额度 | ¥0 | 5000 次/小时 |
| **Telegram Bot** | 免费 | ¥0 | 无限制 |
| **飞书 Webhook** | 免费 | ¥0 | 无限制 |

**月度总成本估算**：¥55-110（大模型 + 服务器）

---

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

---

## License

MIT License

Copyright (c) 2026 AI Knowledge Base

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

---

## 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feature/your-feature`
3. 提交更改：`git commit -m 'Add your feature'`
4. 推送分支：`git push origin feature/your-feature`
5. 提交 Pull Request

---

## 联系方式

- 问题反馈：[GitHub Issues](https://github.com/your-org/ai-knowledge-base/issues)
- 邮箱：your-email@example.com
