"""Reviser 节点：根据审核反馈修正 analyses。

读取 state["analyses"] 和 state["review_feedback"]，
将 feedback 注入修改 prompt，调用 LLM 返回修正后的 analyses 列表。

Example:
    >>> from workflows.reviser import revise_node
    >>> result = revise_node(state)
    >>> print(len(result.get("analyses", [])))
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

try:
    from workflows.model_client import accumulate_usage, chat_json
    from workflows.state import AnalysisResult, KBState
except ImportError:
    from model_client import accumulate_usage, chat_json  # type: ignore[no-redef]
    from state import AnalysisResult, KBState  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

REVISE_SYSTEM_PROMPT = """\
你是一个技术内容编辑专家。根据审核反馈修正文章的标题、摘要和标签。

修正要求：
1. 保持原文核心观点不变
2. 根据反馈改进摘要质量和技术深度
3. 优化标签准确性和覆盖面
4. 确保标题、摘要、标签一致

返回严格 JSON 格式：
{
  "analyses": [
    {
      "source_url": "原始链接",
      "title": "修正后的中文标题",
      "summary": "修正后的摘要（100-300字）",
      "tags": ["tag1", "tag2", "tag3"]
    }
  ]
}"""


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


def revise_node(state: KBState) -> dict:
    """根据审核反馈修正 analyses。

    读取 state["analyses"] 和 state["review_feedback"]，
    将 feedback 注入修改 prompt，调用 LLM 返回修正后的 analyses 列表。
    当 analyses 或 feedback 为空时跳过，返回空字典。

    Args:
        state: 当前工作流状态，需包含 analyses 和 review_feedback 字段。

    Returns:
        包含 analyses 和 cost_tracker 字段的部分状态更新。
        当 analyses 或 feedback 为空时返回空字典。
    """
    analyses = state.get("analyses", [])
    feedback = state.get("review_feedback", "")

    # analyses 或 feedback 空时跳过
    if not analyses or not feedback:
        logger.info(
            "[revise_node] 跳过修正（analyses=%d条, feedback=%s）",
            len(analyses),
            "空" if not feedback else "有",
        )
        return {}

    logger.info("[revise_node] 开始修正 %d 条 analyses", len(analyses))

    tracker = dict(state.get("cost_tracker") or _empty_cost_tracker())

    # 构建修正 prompt
    analyses_text = ""
    for i, a in enumerate(analyses, 1):
        analyses_text += f"""
--- 分析结果 {i} ---
source_url: {a.get('source_url', '')}
标题: {a.get('title', '')}
摘要: {a.get('summary', '')}
标签: {', '.join(a.get('tags', []))}
评分: {a.get('score', 0)}
"""

    prompt = f"""请根据审核反馈修正以下分析结果：

{analyses_text}

审核反馈：
{feedback}

请返回修正后的 JSON，包含所有分析结果。"""

    try:
        result, usage = chat_json(
            prompt=prompt,
            system=REVISE_SYSTEM_PROMPT,
            temperature=0.4,  # 允许创造性改写
        )
        accumulate_usage(tracker, usage)

        revised_analyses = result.get("analyses", [])

        # 构建修正后的 AnalysisResult 列表
        improved: List[AnalysisResult] = []
        now = datetime.now(timezone.utc).isoformat()

        for i, original in enumerate(analyses):
            if i < len(revised_analyses):
                revised = revised_analyses[i]
                improved.append(
                    AnalysisResult(
                        source_url=original.get("source_url", ""),
                        title=revised.get("title", original.get("title", "")),
                        summary=revised.get("summary", original.get("summary", "")),
                        score=original.get("score", 5),
                        tags=revised.get("tags", original.get("tags", [])),
                        analyzed_at=now,
                    )
                )
            else:
                # 修正结果不足时保留原始数据
                improved.append(original)

        logger.info(
            "[revise_node] 修正完成，%d 条分析结果已更新",
            len(improved),
        )

        return {
            "analyses": improved,
            "cost_tracker": tracker,
        }
    except Exception as exc:
        logger.warning("[revise_node] 修正失败: %s", exc)
        # 修正失败时返回原始 analyses
        return {
            "analyses": analyses,
            "cost_tracker": tracker,
        }
