"""Reviewer 节点：对 analyses 进行 5 维度质量评分。

审核对象是 state["analyses"]（不是 articles，articles 在 organize 之后才存在）。
5 维度评分，每维 1-10 分，加权总分 >= 7.0 为通过。

Example:
    >>> from workflows.reviewer import review_node
    >>> result = review_node(state)
    >>> print(result["review_passed"])
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

try:
    from workflows.model_client import accumulate_usage, chat_json
    from workflows.state import KBState
except ImportError:
    from model_client import accumulate_usage, chat_json  # type: ignore[no-redef]
    from state import KBState  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

# 评分维度及权重
REVIEW_DIMENSIONS = {
    "summary_quality": 0.25,  # 摘要质量
    "technical_depth": 0.25,  # 技术深度
    "relevance": 0.20,        # 相关性
    "originality": 0.15,      # 原创性
    "formatting": 0.15,       # 格式规范
}

# 通过阈值
PASS_THRESHOLD = 7.0

# 最大审核条数
MAX_REVIEW_ITEMS = 5

REVIEW_SYSTEM_PROMPT = """\
你是一个技术内容质量审核专家。请从以下五个维度评估每篇文章的质量，每个维度评分 1-10 分（10 最高）：

1. summary_quality（摘要质量）：摘要是否准确、完整、有深度，能否概括核心内容
2. technical_depth（技术深度）：是否深入分析技术细节，而非泛泛而谈
3. relevance（相关性）：内容是否与 AI/LLM/Agent 领域相关，是否有实用价值
4. originality（原创性）：观点或技术方案是否有创新性，而非简单复述
5. formatting（格式规范）：标题、摘要、标签是否规范、一致

返回严格 JSON 格式：
{
  "reviews": [
    {
      "index": 1,
      "scores": {
        "summary_quality": 8,
        "technical_depth": 7,
        "relevance": 9,
        "originality": 6,
        "formatting": 8
      },
      "comment": "简短评语"
    }
  ],
  "feedback": "整体改进建议（如不通过则详细说明问题）"
}"""


def _calculate_weighted_score(scores: Dict[str, float]) -> float:
    """用代码重算加权总分，不信任模型算术。

    Args:
        scores: 各维度评分字典，key 为维度名，value 为 1-10 分。

    Returns:
        加权总分（0-10 分）。
    """
    total = 0.0
    for dim, weight in REVIEW_DIMENSIONS.items():
        dim_score = scores.get(dim, 0)
        # 确保评分在 1-10 范围内
        dim_score = max(1, min(10, dim_score))
        total += dim_score * weight
    return total


def _empty_cost_tracker() -> Dict[str, Any]:
    """创建空的 cost_tracker。

    Returns:
        所有字段归零的 cost_tracker 字典。
    """
    return {
        "total_tokens": 0,
        "total_cost": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "call_count": 0,
    }


def review_node(state: KBState) -> dict:
    """对 analyses 进行 5 维度质量评分。

    审核对象是 state["analyses"]（不是 articles）。
    只审核前 MAX_REVIEW_ITEMS 条，控制 token 消耗。
    加权总分 >= PASS_THRESHOLD 为通过。
    LLM 调用失败时自动通过，不阻塞流程。

    Args:
        state: 当前工作流状态，需包含 analyses 和 iteration 字段。

    Returns:
        包含 review_passed、review_feedback、iteration 和 cost_tracker
        字段的部分状态更新。
    """
    iteration = state.get("iteration", 0)
    logger.info("[review_node] 开始审核（iteration=%d）", iteration)

    # iteration >= 2 强制通过，避免无限循环
    if iteration >= 2:
        logger.info("[review_node] iteration >= 2，强制通过")
        return {
            "review_passed": True,
            "review_feedback": "",
            "iteration": iteration + 1,
            "cost_tracker": state.get("cost_tracker") or _empty_cost_tracker(),
        }

    analyses = state.get("analyses", [])
    if not analyses:
        logger.warning("[review_node] 无 analyses 可审核")
        return {
            "review_passed": True,
            "review_feedback": "",
            "iteration": iteration + 1,
            "cost_tracker": state.get("cost_tracker") or _empty_cost_tracker(),
        }

    # 只审核前 5 条，控制 token 消耗
    items_to_review = analyses[:MAX_REVIEW_ITEMS]
    logger.info(
        "[review_node] 审核前 %d 条 analyses（共 %d 条）",
        len(items_to_review),
        len(analyses),
    )

    tracker = dict(state.get("cost_tracker") or _empty_cost_tracker())

    # 构建审核 prompt
    analyses_text = ""
    for i, a in enumerate(items_to_review, 1):
        analyses_text += f"""
--- 分析结果 {i} ---
标题: {a.get('title', '')}
摘要: {a.get('summary', '')}
标签: {', '.join(a.get('tags', []))}
评分: {a.get('score', 0)}
来源: {a.get('source_url', '')}
"""

    prompt = f"""请对以下 {len(items_to_review)} 条分析结果进行质量评估：

{analyses_text}

请对每条结果进行五维度评分，返回 JSON。"""

    try:
        result, usage = chat_json(
            prompt=prompt,
            system=REVIEW_SYSTEM_PROMPT,
            temperature=0.1,  # 低温度，保证评分一致性
        )
        accumulate_usage(tracker, usage)

        reviews = result.get("reviews", [])
        feedback = str(result.get("feedback", ""))

        # 用代码重算加权总分，不信任模型算术
        all_scores: List[float] = []
        for review in reviews:
            scores = review.get("scores", {})
            weighted_score = _calculate_weighted_score(scores)
            all_scores.append(weighted_score)
            logger.info(
                "[review_node] 文章 %d: 加权总分=%.2f, 评语=%s",
                review.get("index", 0),
                weighted_score,
                review.get("comment", ""),
            )

        # 计算整体平均分
        if all_scores:
            avg_score = sum(all_scores) / len(all_scores)
        else:
            avg_score = 0.0

        passed = avg_score >= PASS_THRESHOLD

        logger.info(
            "[review_node] 审核结果: avg_score=%.2f, threshold=%.1f, passed=%s",
            avg_score,
            PASS_THRESHOLD,
            passed,
        )

        if not passed and not feedback:
            feedback = f"加权平均分 {avg_score:.2f} 低于阈值 {PASS_THRESHOLD}，请改进摘要质量和技术深度。"

        return {
            "review_passed": passed,
            "review_feedback": feedback,
            "iteration": iteration + 1,
            "cost_tracker": tracker,
        }
    except Exception as exc:
        # LLM 调用失败时自动通过，不阻塞流程
        logger.warning("[review_node] 审核异常，自动通过: %s", exc)
        return {
            "review_passed": True,
            "review_feedback": "",
            "iteration": iteration + 1,
            "cost_tracker": tracker,
        }
