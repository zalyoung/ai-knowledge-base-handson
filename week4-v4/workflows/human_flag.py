"""HumanFlag 节点：人工介入节点（异常终点）。

审核循环超过上限时的兜底，将问题条目写入 pending_review/ 目录，
不污染主知识库。

Example:
    >>> from workflows.human_flag import human_flag_node
    >>> result = human_flag_node(state)
    >>> print(result["needs_human_review"])
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

try:
    from workflows.state import AnalysisResult, KBState
except ImportError:
    from state import AnalysisResult, KBState  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
PENDING_DIR = PROJECT_ROOT / "knowledge" / "pending_review"


def human_flag_node(state: KBState) -> dict:
    """审核循环超过上限时的兜底 —— 写入 pending_review/ 目录。

    当 iteration >= 3 仍未通过审核时，将 analyses 和审核反馈
    保存到独立目录，等待人工判断。

    Args:
        state: 当前工作流状态，需包含 analyses、iteration 和
            review_feedback 字段。

    Returns:
        包含 needs_human_review=True 的部分状态更新。
    """
    analyses: List[AnalysisResult] = state.get("analyses", [])
    iteration: int = state.get("iteration", 0)
    feedback: str = state.get("review_feedback", "")

    logger.warning("[HumanFlag] ⚠️ 达到 %d 次审核仍未通过", iteration)
    logger.warning("[HumanFlag] 最后反馈: %s", feedback[:200])

    # 创建 pending_review 目录
    PENDING_DIR.mkdir(parents=True, exist_ok=True)

    # 生成带时间戳的文件名
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    filepath = PENDING_DIR / f"pending-{timestamp}.json"

    # 保存待审核数据
    pending_data: Dict[str, Any] = {
        "timestamp": timestamp,
        "iterations_used": iteration,
        "last_feedback": feedback,
        "analyses": analyses,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(pending_data, f, ensure_ascii=False, indent=2)

    logger.info("[HumanFlag] 已保存到 %s", filepath)

    return {"needs_human_review": True}
