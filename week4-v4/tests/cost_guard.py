"""多 Agent 预算守卫模块。

提供 LLM 调用成本追踪、预算预警和超限保护功能。
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CostRecord:
    """单次 LLM 调用的成本记录。

    Attributes:
        timestamp: 调用时间戳
        node_name: 节点名称（Agent 名称）
        prompt_tokens: 输入 token 数量
        completion_tokens: 输出 token 数量
        cost_yuan: 本次调用费用（元）
        model: 使用的模型名称
    """

    timestamp: float
    node_name: str
    prompt_tokens: int
    completion_tokens: int
    cost_yuan: float
    model: str = ""


class BudgetExceededError(Exception):
    """预算超限异常。

    当 LLM 调用总费用超过预算时抛出。

    Attributes:
        total_cost: 当前总费用
        budget: 预算上限
    """

    def __init__(self, total_cost: float, budget: float) -> None:
        self.total_cost = total_cost
        self.budget = budget
        super().__init__(
            f"预算超限：当前费用 ¥{total_cost:.4f} 已超过预算 ¥{budget:.4f}"
        )


class CostGuard:
    """多 Agent 预算守卫。

    提供三重保护机制：
    1. 记录每次 LLM 调用的 token 用量和费用
    2. 接近预算时发出预警（status="warning"）
    3. 超出预算时抛出 BudgetExceededError 异常

    Args:
        budget_yuan: 总预算（元），默认 1.0
        alert_threshold: 预警阈值（0-1），默认 0.8
        input_price_per_million: 输入 token 每百万价格（元），默认 1.0
        output_price_per_million: 输出 token 每百万价格（元），默认 2.0
    """

    def __init__(
        self,
        budget_yuan: float = 1.0,
        alert_threshold: float = 0.8,
        input_price_per_million: float = 1.0,
        output_price_per_million: float = 2.0,
    ) -> None:
        self.budget_yuan = budget_yuan
        self.alert_threshold = alert_threshold
        self.input_price_per_million = input_price_per_million
        self.output_price_per_million = output_price_per_million
        self._records: list[CostRecord] = []

    def record(
        self,
        node_name: str,
        usage: dict[str, int],
        model: str = "",
    ) -> CostRecord:
        """记录一次 LLM 调用的 token 用量。

        Args:
            node_name: 节点名称（Agent 名称）
            usage: token 用量，格式 {"prompt_tokens": int, "completion_tokens": int}
            model: 使用的模型名称

        Returns:
            本次生成的 CostRecord 记录

        Raises:
            BudgetExceededError: 当累计费用超过预算时
        """
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        cost_yuan = (
            prompt_tokens / 1_000_000 * self.input_price_per_million
            + completion_tokens / 1_000_000 * self.output_price_per_million
        )

        record = CostRecord(
            timestamp=time.time(),
            node_name=node_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_yuan=cost_yuan,
            model=model,
        )
        self._records.append(record)

        self.check()

        return record

    def check(self) -> dict[str, Any]:
        """检查预算状态。

        Returns:
            包含预算状态的字典：
            - status: "ok" | "warning" | "exceeded"
            - total_cost: 当前总费用
            - budget: 预算上限
            - usage_ratio: 使用比例
            - message: 状态描述

        Raises:
            BudgetExceededError: 当总费用超过预算时
        """
        total_cost = sum(r.cost_yuan for r in self._records)
        usage_ratio = total_cost / self.budget_yuan if self.budget_yuan > 0 else 0.0

        if total_cost >= self.budget_yuan:
            raise BudgetExceededError(total_cost, self.budget_yuan)

        if usage_ratio >= self.alert_threshold:
            return {
                "status": "warning",
                "total_cost": total_cost,
                "budget": self.budget_yuan,
                "usage_ratio": usage_ratio,
                "message": f"接近预算上限：已使用 {usage_ratio:.1%}",
            }

        return {
            "status": "ok",
            "total_cost": total_cost,
            "budget": self.budget_yuan,
            "usage_ratio": usage_ratio,
            "message": f"预算正常：已使用 {usage_ratio:.1%}",
        }

    def get_report(self) -> dict[str, Any]:
        """生成成本报告（按节点分组统计）。

        Returns:
            包含总览和按节点分组统计的报告字典
        """
        total_prompt_tokens = sum(r.prompt_tokens for r in self._records)
        total_completion_tokens = sum(r.completion_tokens for r in self._records)
        total_cost_yuan = sum(r.cost_yuan for r in self._records)

        nodes: dict[str, dict[str, Any]] = {}
        for r in self._records:
            if r.node_name not in nodes:
                nodes[r.node_name] = {
                    "call_count": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "cost_yuan": 0.0,
                }
            node = nodes[r.node_name]
            node["call_count"] += 1
            node["prompt_tokens"] += r.prompt_tokens
            node["completion_tokens"] += r.completion_tokens
            node["cost_yuan"] += r.cost_yuan

        return {
            "total_calls": len(self._records),
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
            "total_cost_yuan": total_cost_yuan,
            "budget_yuan": self.budget_yuan,
            "usage_ratio": total_cost_yuan / self.budget_yuan
            if self.budget_yuan > 0
            else 0.0,
            "nodes": nodes,
        }

    def save_report(self, path: str | Path | None = None) -> Path:
        """保存成本报告到 JSON 文件。

        Args:
            path: 输出文件路径，默认为 cost_report.json

        Returns:
            保存的文件路径
        """
        if path is None:
            path = Path("cost_report.json")
        else:
            path = Path(path)

        report = self.get_report()
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return path


if __name__ == "__main__":
    print("=" * 50)
    print("CostGuard 单元测试")
    print("=" * 50)

    # 测试 1: 成本追踪正确
    print("\n[测试 1] 成本追踪正确性")
    guard = CostGuard(budget_yuan=1.0)
    guard.record("agent_a", {"prompt_tokens": 100_000, "completion_tokens": 50_000})
    guard.record("agent_b", {"prompt_tokens": 200_000, "completion_tokens": 100_000})

    report = guard.get_report()
    assert report["total_prompt_tokens"] == 300_000, (
        f"expected 300000, got {report['total_prompt_tokens']}"
    )
    # 100000/1M * 1.0 + 50000/1M * 2.0 = 0.1 + 0.1 = 0.2
    # 200000/1M * 1.0 + 100000/1M * 2.0 = 0.2 + 0.2 = 0.4
    # total = 0.6
    assert abs(report["total_cost_yuan"] - 0.6) < 1e-6, (
        f"expected 0.6, got {report['total_cost_yuan']}"
    )
    assert report["total_calls"] == 2
    assert report["nodes"]["agent_a"]["call_count"] == 1
    assert report["nodes"]["agent_b"]["call_count"] == 1
    print("  ✓ total_prompt_tokens = 300000")
    print("  ✓ total_cost_yuan = 0.6")
    print("  ✓ 按节点分组统计正确")

    # 测试 2: 预算超限检测
    print("\n[测试 2] 预算超限检测")
    guard2 = CostGuard(budget_yuan=0.5)
    guard2.record("agent_a", {"prompt_tokens": 200_000, "completion_tokens": 100_000})
    # cost = 0.2 + 0.2 = 0.4 < 0.5, not exceeded
    try:
        guard2.record("agent_b", {"prompt_tokens": 200_000, "completion_tokens": 0})
        # cost = 0.4 + 0.2 = 0.6 > 0.5, should raise
        assert False, "应该抛出 BudgetExceededError"
    except BudgetExceededError as e:
        assert e.total_cost > e.budget
        print(f"  ✓ 抛出 BudgetExceededError: {e}")

    # 测试 3: 预警阈值触发
    print("\n[测试 3] 预警阈值触发")
    guard3 = CostGuard(budget_yuan=1.0, alert_threshold=0.8)
    guard3.record("agent_a", {"prompt_tokens": 500_000, "completion_tokens": 200_000})
    # cost = 0.5 + 0.4 = 0.9, ratio = 0.9 >= 0.8 => warning
    result = guard3.check()
    assert result["status"] == "warning", f"expected 'warning', got {result['status']}"
    assert result["usage_ratio"] >= 0.8
    print(f"  ✓ status = 'warning', usage_ratio = {result['usage_ratio']:.1%}")

    # 测试 4: save_report
    print("\n[测试 4] 报告保存")
    report_path = guard3.save_report("/tmp/test_cost_report.json")
    assert report_path.exists()
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved["total_cost_yuan"] == guard3.get_report()["total_cost_yuan"]
    print(f"  ✓ 报告已保存到 {report_path}")

    print("\n" + "=" * 50)
    print("所有测试通过 ✓")
    print("=" * 50)
