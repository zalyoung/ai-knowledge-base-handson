"""LangGraph 工作流组装模块。

将 6 个节点组装为有向图，支持 3 路条件路由：
    collect → analyze → review
                        ├─ (passed) → organize → END
                        ├─ (failed, iteration < 3) → revise → review
                        └─ (failed, iteration >= 3) → human_flag → END

Example:
    >>> from workflows.graph import build_graph
    >>> app = build_graph()
    >>> from workflows.state import create_initial_state
    >>> result = app.invoke(create_initial_state())
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, StateGraph

try:
    from workflows.human_flag import human_flag_node
    from workflows.nodes import (
        analyze_node,
        collect_node,
        organize_node,
    )
    from workflows.reviewer import review_node
    from workflows.reviser import revise_node
    from workflows.state import KBState, create_initial_state
except ImportError:
    from human_flag import human_flag_node  # type: ignore[no-redef]
    from nodes import (  # type: ignore[no-redef]
        analyze_node,
        collect_node,
        organize_node,
    )
    from reviewer import review_node  # type: ignore[no-redef]
    from reviser import revise_node  # type: ignore[no-redef]
    from state import KBState, create_initial_state  # type: ignore[no-redef]

logger = logging.getLogger(__name__)


def route_after_review(state: KBState) -> str:
    """条件路由：审核后 3 条出口。

    根据 review_passed 和 iteration 决定下一步走向：
        - 通过 → "organize"（进入整理节点，生成 articles）
        - 不通过且 iteration < 3 → "revise"（进入修正节点）
        - 不通过且 iteration >= 3 → "human_flag"（人工介入）

    Args:
        state: 当前工作流状态。

    Returns:
        路由目标的键名。
    """
    if state.get("review_passed", False):
        logger.info("[router] 审核通过 → organize")
        return "organize"
    elif state.get("iteration", 0) >= 3:
        logger.info("[router] 达到 %d 次审核上限 → human_flag", state.get("iteration", 0))
        return "human_flag"
    else:
        logger.info("[router] 审核未通过 → revise（修正分析结果）")
        return "revise"


def build_graph() -> Any:
    """构建并编译 LangGraph 工作流图。

    节点与边的定义：
        节点: collect, analyze, organize, review, revise, human_flag
        线性边: collect → analyze → review
        条件边: review → (organize | revise | human_flag)
        循环边: revise → review
        终止边: organize → END, human_flag → END

    Returns:
        编译后的 LangGraph app，可调用 .invoke() 或 .stream()。
    """
    graph = StateGraph(KBState)

    # 注册节点
    graph.add_node("collect", collect_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("review", review_node)
    graph.add_node("revise", revise_node)
    graph.add_node("organize", organize_node)
    graph.add_node("human_flag", human_flag_node)

    # 线性边: collect → analyze → review
    graph.add_edge("collect", "analyze")
    graph.add_edge("analyze", "review")

    # 条件边: review 之后根据 review_passed 和 iteration 分支
    graph.add_conditional_edges(
        "review",
        route_after_review,
        {
            "organize": "organize",
            "revise": "revise",
            "human_flag": "human_flag",
        },
    )

    # revise → review（修正后重新审核，形成循环）
    graph.add_edge("revise", "review")

    # 两个终点
    graph.add_edge("organize", END)
    graph.add_edge("human_flag", END)

    # 入口点
    graph.set_entry_point("collect")

    return graph.compile()


def main() -> None:
    """流式执行工作流并打印每个节点的关键输出。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    app = build_graph()
    initial_state = create_initial_state()

    logger.info("=" * 60)
    logger.info("工作流启动")
    logger.info("=" * 60)

    for event in app.stream(initial_state):
        for node_name, output in event.items():
            logger.info("-" * 40)
            logger.info("[节点: %s] 输出完成", node_name)

            # 打印关键输出摘要
            if "sources" in output:
                sources = output["sources"]
                logger.info("  采集: %d 条数据", len(sources))
                for s in sources[:3]:
                    logger.info("    - %s (★%s)", s.get("title", ""), s.get("stars", 0))
                if len(sources) > 3:
                    logger.info("    ... 还有 %d 条", len(sources) - 3)

            if "analyses" in output:
                analyses = output["analyses"]
                logger.info("  分析: %d 条结果", len(analyses))
                for a in analyses[:3]:
                    logger.info(
                        "    - %s [score=%s]",
                        a.get("title", ""),
                        a.get("score", 0),
                    )
                if len(analyses) > 3:
                    logger.info("    ... 还有 %d 条", len(analyses) - 3)

            if "articles" in output:
                articles = output["articles"]
                logger.info("  文章: %d 篇", len(articles))
                for art in articles[:3]:
                    logger.info(
                        "    - %s (%s)",
                        art.get("title", ""),
                        art.get("id", ""),
                    )
                if len(articles) > 3:
                    logger.info("    ... 还有 %d 篇", len(articles) - 3)

            if "review_passed" in output:
                passed = output["review_passed"]
                feedback = output.get("review_feedback", "")
                iteration = output.get("iteration", 0)
                logger.info("  审核: passed=%s, iteration=%s", passed, iteration)
                if feedback:
                    logger.info("  反馈: %s", feedback[:200])

            if "needs_human_review" in output:
                logger.info("  ⚠️ 需要人工介入")

            if "cost_tracker" in output:
                ct = output["cost_tracker"]
                logger.info(
                    "  成本: tokens=%s, calls=%s",
                    ct.get("total_tokens", 0),
                    ct.get("call_count", 0),
                )

    logger.info("=" * 60)
    logger.info("工作流完成")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
