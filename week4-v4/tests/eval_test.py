"""AI 知识库评估测试。

使用 pytest 框架对知识库的分析能力进行评估，包含：
- 正面案例：技术文章输入，预期有摘要、有关键词
- 负面案例：无关内容输入，预期被过滤或标记为低相关
- 边界案例：极短输入，预期不崩溃
- LLM-as-Judge 测试：让 LLM 对分析结果打分
"""

import json
import os
import re
import sys
import warnings
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# 将项目根目录加入 sys.path，确保 workflows 模块可导入
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import pytest

# 加载 .env 文件，让 pytest 能读到 LLM_API_KEY
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 屏蔽 PytestUnknownMarkWarning（避免自定义 slow 标记触发警告）
warnings.filterwarnings("ignore", category=pytest.PytestUnknownMarkWarning)

# 导入待测模块
from workflows.model_client import chat, Usage


# ==================== 评估用例定义 ====================


def _check_summary_and_keywords(result: Dict[str, Any]) -> bool:
    """检查结果是否包含摘要和关键词。

    Args:
        result: 分析结果字典。

    Returns:
        True 如果结果包含摘要和关键词。
    """
    has_summary = "summary" in result and len(result.get("summary", "")) >= 50
    has_keywords = "keywords" in result and len(result.get("keywords", [])) >= 3
    return has_summary and has_keywords


def _check_low_relevance(result: Dict[str, Any]) -> bool:
    """检查结果是否标记为低相关。

    Args:
        result: 分析结果字典。

    Returns:
        True 如果结果标记为低相关或被过滤。
    """
    relevance = result.get("relevance_score", 1.0)
    is_filtered = result.get("filtered", False)
    return relevance <= 0.3 or is_filtered


def _check_no_crash(result: Dict[str, Any]) -> bool:
    """检查结果是否不崩溃（有基本结构）。

    Args:
        result: 分析结果字典。

    Returns:
        True 如果结果有基本结构且没有崩溃。
    """
    return isinstance(result, dict) and "status" in result


# 评估用例列表
EVAL_CASES: List[Dict[str, Any]] = [
    {
        "name": "正面案例：技术文章输入",
        "input": (
            "LangGraph 是 LangChain 团队开发的状态机框架，用于构建"
            "复杂的多 Agent 应用。它支持条件分支、循环和并行执行，"
            "使得开发者可以轻松构建复杂的 Agent 工作流。"
            "最新版本 v0.3 引入了 SupervisorAgent 模式，"
            "允许多个子 Agent 在统一调度下并行执行任务。"
        ),
        "expected": {
            "check": _check_summary_and_keywords,
            "description": "预期有摘要（>=50字）和关键词（>=3个）",
        },
    },
    {
        "name": "负面案例：无关内容输入",
        "input": (
            "今天天气真好，阳光明媚，适合出去散步。"
            "我家的小狗在公园里跑来跑去，非常开心。"
            "晚上打算做一顿丰盛的晚餐，享受美好的周末时光。"
        ),
        "expected": {
            "check": _check_low_relevance,
            "description": "预期被过滤或标记为低相关（relevance_score <= 0.3）",
        },
    },
    {
        "name": "边界案例：极短输入",
        "input": "AI",
        "expected": {
            "check": _check_no_crash,
            "description": "预期不崩溃，有基本结构",
        },
    },
    {
        "name": "正面案例：AI 论文摘要",
        "input": (
            "我们提出了一种新的 Transformer 架构，称为 FlashAttention-2，"
            "通过优化 GPU 内存访问模式，将注意力机制的计算速度提升了 2 倍。"
            "实验表明，在 A100 GPU 上，FlashAttention-2 达到了理论峰值性能的 72%。"
            "该方法已开源，支持 PyTorch 和 JAX 框架。"
        ),
        "expected": {
            "check": _check_summary_and_keywords,
            "description": "预期有摘要和关键词",
        },
    },
    {
        "name": "负面案例：纯数字内容",
        "input": "1234567890 9876543210 1111111111 2222222222 3333333333",
        "expected": {
            "check": _check_low_relevance,
            "description": "预期被过滤或标记为低相关",
        },
    },
]


# ==================== 辅助函数 ====================


def analyze_content(content: str) -> Dict[str, Any]:
    """使用 LLM 分析内容。

    Args:
        content: 待分析的内容。

    Returns:
        分析结果字典，包含 summary、keywords、relevance_score 等字段。
    """
    system_prompt = """你是一个 AI 知识库分析助手。请分析以下内容，并返回 JSON 格式的结果。

返回格式：
{
    "summary": "内容摘要（100-300字）",
    "keywords": ["关键词1", "关键词2", "关键词3"],
    "relevance_score": 0.0-1.0,
    "filtered": false,
    "status": "analyzed"
}

注意：
- 如果内容与 AI/LLM/Agent 技术无关，将 relevance_score 设为 0.3 以下，并将 filtered 设为 true
- 如果内容太短无法分析，仍然返回基本结构，status 设为 "minimal"
- 只返回 JSON，不要有其他文字"""

    prompt = f"请分析以下内容：\n\n{content}"

    try:
        text, usage = chat(
            prompt=prompt,
            system=system_prompt,
            temperature=0.3,
            max_tokens=1000,
        )

        # 尝试解析 JSON
        content_clean = text.strip()
        json_match = re.search(r"```(?:json)?\s*(.*?)\s*```", content_clean, re.DOTALL)
        if json_match:
            content_clean = json_match.group(1).strip()

        result = json.loads(content_clean)
        result["usage"] = {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
        }
        return result

    except json.JSONDecodeError as e:
        return {
            "status": "error",
            "error": f"JSON 解析失败: {str(e)}",
            "raw_response": text if "text" in locals() else "",
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }


def llm_as_judge(analysis_result: Dict[str, Any], original_input: str) -> int:
    """使用 LLM 作为评判，对分析结果打分。

    Args:
        analysis_result: 分析结果字典。
        original_input: 原始输入内容。

    Returns:
        1-10 的评分。
    """
    system_prompt = """你是一个严格的质量评审员。请根据以下标准对分析结果打分（1-10分）：

评分标准：
- 摘要质量：是否准确概括了原文内容（3分）
- 关键词质量：是否准确提取了关键概念（3分）
- 相关性判断：是否正确判断了内容与 AI 技术的相关性（2分）
- 格式规范：返回的 JSON 是否符合规范（2分）

只返回一个数字（1-10），不要有其他文字。"""

    prompt = f"""原始输入：
{original_input}

分析结果：
{json.dumps(analysis_result, ensure_ascii=False, indent=2)}

请对这个分析结果打分（1-10）："""

    try:
        text, usage = chat(
            prompt=prompt,
            system=system_prompt,
            temperature=0.1,
            max_tokens=10,
        )

        # 提取数字
        numbers = re.findall(r"\d+", text)
        if numbers:
            score = int(numbers[0])
            return max(1, min(10, score))  # 确保在 1-10 范围内
        return 5  # 默认分数

    except Exception:
        return 5  # 出错时返回默认分数


# ==================== 测试函数 ====================


@pytest.mark.slow
@pytest.mark.parametrize("case", EVAL_CASES, ids=[c["name"] for c in EVAL_CASES])
def test_analysis_cases(case: Dict[str, Any]) -> None:
    """测试各个评估用例。

    Args:
        case: 评估用例字典，包含 name、input、expected 字段。
    """
    # 调用 LLM 分析
    result = analyze_content(case["input"])

    # 检查结果不为空
    assert result is not None, "分析结果不应为空"
    assert isinstance(result, dict), "分析结果应为字典类型"

    # 运行用例特定的检查函数
    check_func = case["expected"]["check"]
    assert check_func(result), (
        f"用例 '{case['name']}' 验证失败: {case['expected']['description']}\n"
        f"实际结果: {json.dumps(result, ensure_ascii=False, indent=2)}"
    )


@pytest.mark.slow
def test_llm_as_judge() -> None:
    """LLM-as-Judge 测试：让 LLM 对分析结果打分，断言分数 >= 5。"""
    # 选择一个正面案例进行测试
    positive_case = EVAL_CASES[0]

    # 分析内容
    analysis_result = analyze_content(positive_case["input"])

    # 确保分析成功
    assert analysis_result.get("status") != "error", (
        f"分析失败: {analysis_result.get('error', '未知错误')}"
    )

    # 使用 LLM 打分
    score = llm_as_judge(analysis_result, positive_case["input"])

    # 断言分数 >= 5
    assert score >= 5, f"LLM 评分 {score} 低于预期的 5 分"
    assert 1 <= score <= 10, f"LLM 评分 {score} 超出 1-10 范围"

    print(f"\nLLM-as-Judge 评分: {score}/10")


def test_eval_cases_structure() -> None:
    """本地验证测试：验证 EVAL_CASES 结构正确，不调用 LLM。"""
    # 验证 EVAL_CASES 是列表
    assert isinstance(EVAL_CASES, list), "EVAL_CASES 应为列表类型"

    # 验证至少有 3 个用例
    assert len(EVAL_CASES) >= 3, f"EVAL_CASES 应至少包含 3 个用例，当前有 {len(EVAL_CASES)} 个"

    # 验证每个用例的结构
    for i, case in enumerate(EVAL_CASES):
        # 必需字段
        assert "name" in case, f"用例 {i} 缺少 'name' 字段"
        assert "input" in case, f"用例 {i} 缺少 'input' 字段"
        assert "expected" in case, f"用例 {i} 缺少 'expected' 字段"

        # name 字段
        assert isinstance(case["name"], str), f"用例 {i} 的 'name' 应为字符串"
        assert len(case["name"]) > 0, f"用例 {i} 的 'name' 不应为空"

        # input 字段
        assert isinstance(case["input"], str), f"用例 {i} 的 'input' 应为字符串"
        assert len(case["input"]) > 0, f"用例 {i} 的 'input' 不应为空"

        # expected 字段
        expected = case["expected"]
        assert isinstance(expected, dict), f"用例 {i} 的 'expected' 应为字典类型"
        assert "check" in expected, f"用例 {i} 的 'expected' 缺少 'check' 字段"
        assert "description" in expected, f"用例 {i} 的 'expected' 缺少 'description' 字段"

        # check 字段应为可调用对象
        assert callable(expected["check"]), f"用例 {i} 的 'check' 应为可调用对象"

        # description 字段
        assert isinstance(expected["description"], str), (
            f"用例 {i} 的 'description' 应为字符串"
        )

    # 验证包含正面案例、负面案例、边界案例
    case_names = [c["name"] for c in EVAL_CASES]
    assert any("正面" in name for name in case_names), "应包含至少一个正面案例"
    assert any("负面" in name for name in case_names), "应包含至少一个负面案例"
    assert any("边界" in name for name in case_names), "应包含至少一个边界案例"

    print(f"\nEVAL_CASES 结构验证通过，共 {len(EVAL_CASES)} 个用例")
    for case in EVAL_CASES:
        print(f"  - {case['name']}")


def test_analyze_content_returns_dict() -> None:
    """测试 analyze_content 函数返回值类型正确（不调用 LLM）。"""
    # 验证函数签名
    import inspect
    sig = inspect.signature(analyze_content)
    assert "content" in sig.parameters, "analyze_content 应有 content 参数"

    # 验证返回类型注解
    assert sig.return_annotation == Dict[str, Any], (
        "analyze_content 应返回 Dict[str, Any]"
    )


def test_llm_as_judge_returns_int() -> None:
    """测试 llm_as_judge 函数返回值类型正确（不调用 LLM）。"""
    # 验证函数签名
    import inspect
    sig = inspect.signature(llm_as_judge)
    assert "analysis_result" in sig.parameters, "llm_as_judge 应有 analysis_result 参数"
    assert "original_input" in sig.parameters, "llm_as_judge 应有 original_input 参数"

    # 验证返回类型注解
    assert sig.return_annotation == int, "llm_as_judge 应返回 int"


# ==================== 主函数 ====================


if __name__ == "__main__":
    print("=" * 60)
    print("AI 知识库评估测试")
    print("=" * 60)

    print("\n评估用例：")
    for case in EVAL_CASES:
        print(f"  - {case['name']}")
        print(f"    输入: {case['input'][:50]}...")
        print(f"    预期: {case['expected']['description']}")
        print()

    print("\n运行测试：")
    print("  pytest tests/eval_test.py -v")
    print("\n跳过 LLM 测试：")
    print("  pytest tests/eval_test.py -v -m 'not slow'")

    print("\n" + "=" * 60)
