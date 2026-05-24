"""LangGraph 工作流组装模块。

将 nodes.py 中定义的 5 个节点组装为有向图：
    collect → analyze → organize → review
                                   ├─ (passed) → save → END
                                   └─ (failed) → organize（回到整理修正）

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
    from workflows.nodes import (
        analyze_node,
        collect_node,
        organize_node,
        review_node,
        save_node,
    )
    from workflows.state import KBState, create_initial_state
except ImportError:
    from nodes import (  # type: ignore[no-redef]
        analyze_node,
        collect_node,
        organize_node,
        review_node,
        save_node,
    )
    from state import KBState, create_initial_state  # type: ignore[no-redef]

logger = logging.getLogger(__name__)


def _review_router(state: KBState) -> str:
    """审核节点的路由函数。

    根据 review_passed 决定下一步走向：
        - True  → "save"（进入保存节点）
        - False → "organize"（回到整理节点修正）

    Args:
        state: 当前工作流状态。

    Returns:
        路由目标的键名。
    """
    if state.get("review_passed", False):
        logger.info("[router] 审核通过 → save")
        return "save"
    logger.info("[router] 审核未通过 → organize（重新修正）")
    return "organize"


def build_graph() -> Any:
    """构建并编译 LangGraph 工作流图。

    节点与边的定义：
        节点: collect, analyze, organize, review, save
        线性边: collect → analyze → organize → review
        条件边: review → (save | organize)
        终止边: save → END

    Returns:
        编译后的 LangGraph app，可调用 .invoke() 或 .stream()。
    """
    graph = StateGraph(KBState)

    # 注册节点
    graph.add_node("collect", collect_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("organize", organize_node)
    graph.add_node("review", review_node)
    graph.add_node("save", save_node)

    # 线性边: collect → analyze → organize → review
    graph.add_edge("collect", "analyze")
    graph.add_edge("analyze", "organize")
    graph.add_edge("organize", "review")

    # 条件边: review 之后根据 review_passed 分支
    graph.add_conditional_edges(
        "review",
        _review_router,
        {
            "save": "save",
            "organize": "organize",
        },
    )

    # 终止边: save → END
    graph.add_edge("save", END)

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
