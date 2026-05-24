"""Planner 节点：根据目标采集量动态规划采集策略。

根据 target_count 自动选择 lite/standard/full 三档策略，
控制每个数据源的采集量、相关性阈值和审核迭代次数。

Example:
    >>> from workflows.planner import plan_strategy, planner_node
    >>> plan = plan_strategy(target_count=15)
    >>> print(plan["tier"])
    standard
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

try:
    from workflows.state import KBState
except ImportError:
    from state import KBState  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

# 默认目标采集量（从环境变量读取）
DEFAULT_TARGET_COUNT = 10


def plan_strategy(target_count: Optional[int] = None) -> Dict[str, Any]:
    """根据目标采集量返回策略 dict。

    三档策略：
        - lite (target < 10): 轻量模式，快速采集
        - standard (10 <= target < 20): 标准模式，平衡效率与质量
        - full (target >= 20): 完整模式，深度采集

    Args:
        target_count: 目标采集量。若为 None，则从环境变量
            PLANNER_TARGET_COUNT 读取，默认 10。

    Returns:
        策略字典，包含 tier、per_source_limit、relevance_threshold、
        max_iterations 和 rationale 字段。
    """
    # 从环境变量读取默认值
    if target_count is None:
        env_val = os.getenv("PLANNER_TARGET_COUNT", str(DEFAULT_TARGET_COUNT))
        try:
            target_count = int(env_val)
        except ValueError:
            logger.warning(
                "[planner] 无效的 PLANNER_TARGET_COUNT=%s，使用默认值 %d",
                env_val,
                DEFAULT_TARGET_COUNT,
            )
            target_count = DEFAULT_TARGET_COUNT

    # 确保 target_count 为正整数
    target_count = max(1, target_count)

    # 三档策略
    if target_count < 10:
        # lite: 轻量模式
        plan: Dict[str, Any] = {
            "tier": "lite",
            "target_count": target_count,
            "per_source_limit": 5,
            "relevance_threshold": 0.7,
            "max_iterations": 1,
            "rationale": (
                f"目标采集量 {target_count} < 10，选择 lite 轻量模式。"
                "每个数据源限制采集 5 条，相关性阈值 0.7（较高，严格筛选），"
                "最多审核 1 轮。适合快速预览或资源受限场景。"
            ),
        }
    elif target_count < 20:
        # standard: 标准模式
        plan = {
            "tier": "standard",
            "target_count": target_count,
            "per_source_limit": 10,
            "relevance_threshold": 0.5,
            "max_iterations": 2,
            "rationale": (
                f"目标采集量 10 <= {target_count} < 20，选择 standard 标准模式。"
                "每个数据源限制采集 10 条，相关性阈值 0.5（适中），"
                "最多审核 2 轮。平衡效率与质量，适合日常使用。"
            ),
        }
    else:
        # full: 完整模式
        plan = {
            "tier": "full",
            "target_count": target_count,
            "per_source_limit": 20,
            "relevance_threshold": 0.4,
            "max_iterations": 3,
            "rationale": (
                f"目标采集量 {target_count} >= 20，选择 full 完整模式。"
                "每个数据源限制采集 20 条，相关性阈值 0.4（较低，广采精筛），"
                "最多审核 3 轮。适合深度调研或批量生成知识库。"
            ),
        }

    logger.info(
        "[planner] 策略: tier=%s, target=%d, per_source=%d, threshold=%.1f, "
        "max_iter=%d",
        plan["tier"],
        plan["target_count"],
        plan["per_source_limit"],
        plan["relevance_threshold"],
        plan["max_iterations"],
    )

    return plan


def planner_node(state: KBState) -> dict:
    """LangGraph 节点包装：调用 plan_strategy 并返回 {"plan": plan}。

    从 state 中读取可选的 target_count（若已设置），否则使用默认逻辑。

    Args:
        state: 当前工作流状态。

    Returns:
        包含 plan 字段的部分状态更新。
    """
    # 优先从 state 读取，否则走默认逻辑
    target_count = state.get("plan", {}).get("target_count") if "plan" in state else None

    plan = plan_strategy(target_count=target_count)

    logger.info("[planner_node] 已生成采集策略: %s", plan["tier"])
    return {"plan": plan}
