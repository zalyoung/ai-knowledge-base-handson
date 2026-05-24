"""Supervisor 监督模式实现。

Worker Agent 执行任务并输出分析报告，Supervisor Agent 对输出进行质量审核。
审核不通过时，Worker 根据反馈重新执行，最多重试指定轮数。

审核评分维度：
- 准确性 (1-10)
- 深度 (1-10)
- 格式 (1-10)

综合评分 >= 7 视为通过。
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# 确保项目根目录在 Python 路径中
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from pipeline.model_client import chat

logger = logging.getLogger(__name__)

# ============================================================
# Prompts
# ============================================================

_WORKER_SYSTEM_PROMPT = (
    "你是一个专业的技术分析师。请根据用户给出的任务，输出一份结构化的分析报告。\n"
    "要求：\n"
    "1. 内容准确、有深度、逻辑清晰\n"
    "2. 使用 JSON 格式输出，包含以下字段：\n"
    '   - "title": 报告标题\n'
    '   - "summary": 核心摘要 (100-300字)\n'
    '   - "key_points": 关键要点列表\n'
    '   - "conclusion": 结论\n'
    "3. 只输出 JSON，不要输出其他内容"
)

_SUPERVISOR_SYSTEM_PROMPT = (
    "你是一个严格的质量审核员。请对 Worker 输出的分析报告进行质量评估。\n"
    "评分维度（每项 1-10 分）：\n"
    "- 准确性：内容是否准确、无事实错误\n"
    "- 深度：分析是否深入、有洞察力\n"
    "- 格式：JSON 结构是否规范、内容是否完整\n"
    "\n"
    "综合评分 = (准确性 + 深度 + 格式) / 3，向下取整。\n"
    "综合评分 >= 7 视为通过。\n"
    "\n"
    "请严格按以下 JSON 格式输出，不要输出其他内容：\n"
    '{"passed": true/false, "score": int, "accuracy": int, "depth": int, '
    '"format_score": int, "feedback": "具体改进建议"}'
)

_REVISE_PROMPT_TEMPLATE = (
    "你之前的报告未通过质量审核，请根据反馈重新编写。\n\n"
    "原始任务：{task}\n\n"
    "上一版报告：\n{previous_output}\n\n"
    "审核反馈：{feedback}\n\n"
    "请输出改进后的完整报告（JSON 格式）。"
)


# ============================================================
# Core functions
# ============================================================


def _call_llm(prompt: str, system_prompt: str) -> str:
    """调用 LLM 并返回文本内容。

    Args:
        prompt: 用户提示词。
        system_prompt: 系统提示词。

    Returns:
        模型生成的文本内容。
    """
    response = chat(
        prompt=prompt,
        system_prompt=system_prompt,
        temperature=0.3,
        max_tokens=2000,
    )
    return response.content


def _parse_json(text: str) -> dict:
    """从 LLM 输出中解析 JSON。

    支持处理被 markdown 代码块包裹的 JSON。

    Args:
        text: LLM 输出的原始文本。

    Returns:
        解析后的字典。

    Raises:
        json.JSONDecodeError: 无法解析为有效 JSON。
    """
    cleaned = text.strip()

    # 去除 markdown 代码块
    if "```" in cleaned:
        lines = cleaned.split("\n")
        cleaned = "\n".join(
            line for line in lines if not line.strip().startswith("```")
        )
        cleaned = cleaned.strip()

    return json.loads(cleaned)


def _execute_worker(task: str, feedback: Optional[str] = None,
                    previous_output: Optional[str] = None) -> dict:
    """执行 Worker Agent 生成分析报告。

    Args:
        task: 分析任务描述。
        feedback: Supervisor 的审核反馈（重做时提供）。
        previous_output: 上一版输出内容（重做时提供）。

    Returns:
        解析后的报告字典。
    """
    if feedback and previous_output:
        prompt = _REVISE_PROMPT_TEMPLATE.format(
            task=task,
            previous_output=previous_output,
            feedback=feedback,
        )
    else:
        prompt = task

    raw = _call_llm(prompt, _WORKER_SYSTEM_PROMPT)
    logger.debug("Worker 原始输出: %.200s", raw)
    return _parse_json(raw)


def _execute_supervisor(report: dict) -> dict:
    """执行 Supervisor Agent 审核报告质量。

    Args:
        report: Worker 输出的报告字典。

    Returns:
        审核结果字典，包含 passed、score、feedback 等字段。
    """
    prompt = f"请审核以下分析报告：\n\n{json.dumps(report, ensure_ascii=False, indent=2)}"
    raw = _call_llm(prompt, _SUPERVISOR_SYSTEM_PROMPT)
    logger.debug("Supervisor 原始输出: %.200s", raw)
    return _parse_json(raw)


def supervisor(task: str, max_retries: int = 3) -> Dict[str, Any]:
    """Supervisor 监督模式入口。

    Worker 执行任务生成报告，Supervisor 审核质量。
    审核不通过时，Worker 根据反馈重做，最多重试指定轮数。

    Args:
        task: 分析任务描述。
        max_retries: 最大重试次数，默认 3。

    Returns:
        结果字典，包含以下字段：
        - output: 最终分析报告（dict）
        - attempts: 实际尝试次数（int）
        - final_score: 最终评分（int）
        - warning: 警告信息，仅在超限时出现（str，可选）
    """
    feedback: Optional[str] = None
    previous_output: Optional[str] = None
    last_report: Optional[dict] = None
    last_score: int = 0

    for attempt in range(1, max_retries + 2):  # 1-based, 包含首次 + max_retries 次重试
        logger.info("第 %d 轮执行 Worker...", attempt)

        try:
            report = _execute_worker(task, feedback, previous_output)
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Worker 输出解析失败: %s", exc)
            # 无法解析的输出视为格式零分，跳过 Supervisor 直接重做
            feedback = f"输出格式错误，无法解析为有效 JSON: {exc}"
            previous_output = str(exc)
            continue

        logger.info("第 %d 轮执行 Supervisor 审核...", attempt)

        try:
            review = _execute_supervisor(report)
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Supervisor 输出解析失败: %s，视为通过", exc)
            # Supervisor 解析失败时，保守处理：接受当前报告
            return {
                "output": report,
                "attempts": attempt,
                "final_score": 7,
                "warning": f"Supervisor 审核解析失败，已跳过: {exc}",
            }

        passed = review.get("passed", False)
        score = review.get("score", 0)
        review_feedback = review.get("feedback", "")

        last_report = report
        last_score = score

        logger.info(
            "审核结果: passed=%s, score=%d, feedback=%.100s",
            passed, score, review_feedback,
        )

        if passed or score >= 7:
            logger.info("审核通过，返回结果")
            return {
                "output": report,
                "attempts": attempt,
                "final_score": score,
            }

        # 未通过，准备重做
        feedback = review_feedback
        previous_output = json.dumps(report, ensure_ascii=False)

        if attempt <= max_retries:
            logger.info("审核未通过 (score=%d)，准备第 %d 潼重做...", score, attempt + 1)

    # 超过最大重试次数，强制返回
    logger.warning("已达最大重试次数 (%d)，强制返回最后结果", max_retries)
    return {
        "output": last_report,
        "attempts": max_retries + 1,
        "final_score": last_score,
        "warning": f"已达最大重试次数 ({max_retries})，质量可能未达标",
    }


# ============================================================
# Test entry
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    if len(sys.argv) > 1:
        test_task = " ".join(sys.argv[1:])
    else:
        test_task = (
            "请分析 LangGraph 框架的技术特点、核心概念和适用场景，"
            "并与 AutoGen、CrewAI 等同类框架进行简要对比。"
        )

    print("=" * 60)
    print("Supervisor 监督模式测试")
    print("=" * 60)

    print(f"\n任务: {test_task}")
    print("-" * 60)

    result = supervisor(test_task, max_retries=2)

    print("\n最终结果:")
    print(f"  尝试次数: {result['attempts']}")
    print(f"  最终评分: {result['final_score']}")

    if "warning" in result:
        print(f"  警告: {result['warning']}")

    print(f"\n分析报告:")
    print(json.dumps(result["output"], ensure_ascii=False, indent=2))

    print(f"\n{'=' * 60}")
    print("测试完成")
    print("=" * 60)
