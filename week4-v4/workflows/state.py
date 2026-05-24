"""LangGraph 工作流共享状态定义。

使用 TypedDict 定义 KBState，作为 LangGraph 图中所有节点的共享数据载体。
遵循"报告式通信"原则：每个字段存储结构化摘要，而非原始数据。

Example:
    >>> state: KBState = {
    ...     "sources": [],
    ...     "analyses": [],
    ...     "articles": [],
    ...     "review_feedback": "",
    ...     "review_passed": False,
    ...     "iteration": 0,
    ...     "cost_tracker": {"total_tokens": 0, "total_cost": 0.0},
    ... }
"""

from __future__ import annotations

from typing import TypedDict


class CostTracker(TypedDict, total=False):
    """Token 用量与费用追踪。

    Attributes:
        total_tokens: 累计消耗的 Token 总数（输入 + 输出）。
        total_cost: 累计费用（单位：美元）。
        input_tokens: 累计输入 Token 数。
        output_tokens: 累计输出 Token 数。
        call_count: LLM 调用次数。
    """

    total_tokens: int
    total_cost: float
    input_tokens: int
    output_tokens: int
    call_count: int


class SourceItem(TypedDict, total=False):
    """采集到的原始数据摘要。

    Attributes:
        source_type: 来源类型，如 "github_trending" 或 "hackernews"。
        source_id: 来源平台的唯一标识。
        title: 原始标题。
        description: 原始描述（截断至 500 字以内）。
        url: 原始链接。
        stars: GitHub 星标数（仅 GitHub 来源）。
        language: 主要编程语言（仅 GitHub 来源）。
        topics: 标签列表（仅 GitHub 来源）。
        published_at: 原文发布时间（ISO 8601）。
        fetched_at: 采集时间（ISO 8601）。
    """

    source_type: str
    source_id: str
    title: str
    description: str
    url: str
    stars: int
    language: str
    topics: list[str]
    published_at: str
    fetched_at: str


class AnalysisResult(TypedDict, total=False):
    """LLM 分析后的结构化结果。

    Attributes:
        source_url: 原始来源链接，用于与 sources 关联。
        title: AI 生成的中文标题。
        summary: AI 生成的摘要（100-300 字）。
        score: 质量评分（1-10）。
        tags: 标签列表（3-8 个小写英文标签）。
        analyzed_at: 分析完成时间（ISO 8601）。
    """

    source_url: str
    title: str
    summary: str
    score: int
    tags: list[str]
    analyzed_at: str


class Article(TypedDict, total=False):
    """格式化、去重后的知识条目。

    符合 AGENTS.md 中定义的知识条目 JSON 格式。

    Attributes:
        id: 文章唯一标识，格式 "{source}-{YYYYMMDD}-{NNN}"。
        title: 中文标题。
        source_url: 原始来源链接。
        source_type: 来源类型。
        summary: AI 生成的摘要。
        tags: 标签列表。
        score: 质量评分（1-10）。
        published_at: 原文发布时间（ISO 8601）。
        fetched_at: 采集时间（ISO 8601）。
        analyzed_at: 分析完成时间（ISO 8601）。
        status: 状态，"draft" / "published" / "archived"。
    """

    id: str
    title: str
    source_url: str
    source_type: str
    summary: str
    tags: list[str]
    score: int
    published_at: str
    fetched_at: str
    analyzed_at: str
    status: str


class KBState(TypedDict, total=False):
    """LangGraph 工作流共享状态。

    所有节点通过读写此状态进行通信。遵循"报告式通信"原则：
    每个字段存储的是结构化摘要（如评分、标签、摘要文本），
    而非原始的 LLM 响应或网页内容。

    Attributes:
        sources: 采集到的原始数据摘要列表。每个元素包含来源类型、
            标题、描述、URL 等元信息，不含完整网页内容。
        analyses: LLM 分析后的结构化结果列表。每个元素包含 AI 生成
            的标题、摘要、评分和标签，不含原始 prompt 或 token 明细。
        articles: 格式化、去重后的知识条目列表。符合 AGENTS.md 定义
            的标准格式，可直接用于持久化或推送。
        review_feedback: 审核节点的反馈意见。记录不通过原因或改进建议，
            供分析节点在下一轮迭代中参考。
        review_passed: 审核是否通过。True 表示质量达标，可进入发布；
            False 表示需要重新分析。
        iteration: 当前审核循环次数（从 0 开始）。用于控制重试上限，
            防止无限循环。最多允许 3 次（0, 1, 2）。
        needs_human_review: 是否需要人工介入。当 iteration >= 3 仍未
            通过审核时，由 HumanFlag 节点设为 True。
        cost_tracker: Token 用量追踪。记录累计 Token 消耗、费用和
            调用次数，用于成本监控和预算控制。
    """

    sources: list[SourceItem]
    analyses: list[AnalysisResult]
    articles: list[Article]
    review_feedback: str
    review_passed: bool
    iteration: int
    needs_human_review: bool
    cost_tracker: CostTracker


def create_initial_state() -> KBState:
    """创建初始状态。

    Returns:
        包含所有字段默认值的初始 KBState 实例。
    """
    return KBState(
        sources=[],
        analyses=[],
        articles=[],
        review_feedback="",
        review_passed=False,
        iteration=0,
        needs_human_review=False,
        cost_tracker=CostTracker(
            total_tokens=0,
            total_cost=0.0,
            input_tokens=0,
            output_tokens=0,
            call_count=0,
        ),
    )
