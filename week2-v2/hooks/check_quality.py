#!/usr/bin/env python
"""知识条目质量评分脚本。

对知识条目 JSON 文件进行 5 维度质量评分，输出可视化报告。

用法:
    python hooks/check_quality.py <json_file> [json_file2 ...]
    python hooks/check_quality.py knowledge/articles/*.json
"""

from __future__ import annotations

import glob as globmod
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ─── 常量 ─────────────────────────────────────────────────────

BUZZWORDS_CN = [
    "赋能", "抓手", "闭环", "打通", "全链路", "底层逻辑",
    "颗粒度", "对齐", "拉通", "沉淀", "强大的", "革命性的",
]

BUZZWORDS_EN = [
    "groundbreaking", "revolutionary", "game-changing",
    "cutting-edge", "next-level", "world-class",
    "best-in-class", "state-of-the-art",
]

TECH_KEYWORDS = [
    "agent", "llm", "rag", "embedding", "vector",
    "transformer", "fine-tune", "prompt", "chain",
    "workflow", "pipeline", "架构", "模型", "推理",
    "微调", "向量", "检索", "增强", "生成",
]

SUMMARY_FULL = 25
DEPTH_FULL = 25
FORMAT_FULL = 20
TAGS_FULL = 15
BUZZWORD_FULL = 15

SUMMARY_THRESHOLD_BASIC = 20
SUMMARY_THRESHOLD_FULL = 50

TAG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# ─── 数据结构 ─────────────────────────────────────────────────


@dataclass
class DimensionScore:
    name: str
    score: int
    max_score: int
    detail: str


@dataclass
class QualityReport:
    file_path: Path
    dimensions: list[DimensionScore] = field(default_factory=list)
    total: int = 0
    grade: str = "C"


# ─── 评分函数 ─────────────────────────────────────────────────


def score_summary(summary: str) -> DimensionScore:
    if not summary:
        return DimensionScore("摘要质量", 0, SUMMARY_FULL, "摘要为空")

    length = len(summary)

    if length < SUMMARY_THRESHOLD_BASIC:
        base = 0
    elif length < SUMMARY_THRESHOLD_FULL:
        base = 15
    else:
        base = SUMMARY_FULL

    bonus = 0
    lower = summary.lower()
    for kw in TECH_KEYWORDS:
        if kw.lower() in lower:
            bonus += 1
    bonus = min(bonus, SUMMARY_FULL - base)

    total = min(base + bonus, SUMMARY_FULL)
    detail = f"{length} 字"
    if bonus:
        detail += f"，含 {bonus} 个技术关键词"

    return DimensionScore("摘要质量", total, SUMMARY_FULL, detail)


def score_depth(data: dict) -> DimensionScore:
    raw = data.get("score")
    if raw is None or not isinstance(raw, (int, float)):
        return DimensionScore("技术深度", 0, DEPTH_FULL, "无 score 字段")

    score_val = max(0, min(10, float(raw)))
    mapped = round(score_val / 10 * DEPTH_FULL)
    return DimensionScore(
        "技术深度", mapped, DEPTH_FULL, f"score={raw} → {mapped}/{DEPTH_FULL}"
    )


def score_format(data: dict) -> DimensionScore:
    checks = [
        ("id", "id" in data and bool(data["id"])),
        ("title", "title" in data and bool(data["title"])),
        ("source_url", "source_url" in data and bool(data["source_url"])),
        ("status", "status" in data and bool(data["status"])),
        ("timestamps", all(
            k in data for k in ("published_at", "fetched_at", "analyzed_at")
        )),
    ]
    passed = sum(1 for _, ok in checks if ok)
    total = passed * 4
    missing = [name for name, ok in checks if not ok]
    detail = "缺少: " + ", ".join(missing) if missing else "全部合规"
    return DimensionScore("格式规范", total, FORMAT_FULL, detail)


def score_tags(tags: list) -> DimensionScore:
    if not isinstance(tags, list):
        return DimensionScore("标签精度", 0, TAGS_FULL, "tags 非列表")

    if not tags:
        return DimensionScore("标签精度", 0, TAGS_FULL, "无标签")

    valid = [t for t in tags if isinstance(t, str) and TAG_PATTERN.match(t)]
    invalid = len(tags) - len(valid)

    if len(valid) <= 3 and invalid == 0:
        total = TAGS_FULL
    elif len(valid) <= 3:
        total = max(0, TAGS_FULL - invalid * 3)
    else:
        excess = len(valid) - 3
        total = max(0, TAGS_FULL - excess * 2 - invalid * 3)

    detail = f"{len(valid)} 个有效标签"
    if invalid:
        detail += f"，{invalid} 个无效"
    if len(valid) > 3:
        detail += f"，建议精简至 3 个以内"

    return DimensionScore("标签精度", total, TAGS_FULL, detail)


def score_buzzwords(summary: str) -> DimensionScore:
    if not summary:
        return DimensionScore("空洞词检测", BUZZWORD_FULL, BUZZWORD_FULL, "无摘要")

    found = []
    for word in BUZZWORDS_CN:
        if word in summary:
            found.append(word)
    lower = summary.lower()
    for word in BUZZWORDS_EN:
        if word in lower:
            found.append(word)

    deduction = len(found) * 3
    total = max(0, BUZZWORD_FULL - deduction)

    if found:
        detail = f"发现 {len(found)} 个空洞词: {', '.join(found)}"
    else:
        detail = "无空洞词"

    return DimensionScore("空洞词检测", total, BUZZWORD_FULL, detail)


# ─── 等级与汇总 ──────────────────────────────────────────────


def compute_grade(total: int) -> str:
    if total >= 80:
        return "A"
    if total >= 60:
        return "B"
    return "C"


def evaluate_entry(data: dict, file_path: Path) -> QualityReport:
    dims = [
        score_summary(data.get("summary", "")),
        score_depth(data),
        score_format(data),
        score_tags(data.get("tags", [])),
        score_buzzwords(data.get("summary", "")),
    ]
    total = sum(d.score for d in dims)
    grade = compute_grade(total)
    return QualityReport(file_path, dims, total, grade)


# ─── 文件级处理 ───────────────────────────────────────────────


def score_file(
    file_path: Path,
) -> QualityReport | list[QualityReport] | None:
    if not file_path.exists():
        return None

    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError:
        return None

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None

    if isinstance(data, dict):
        return evaluate_entry(data, file_path)
    if isinstance(data, list):
        return [
            evaluate_entry(item, file_path)
            for item in data
            if isinstance(item, dict)
        ]
    return None


# ─── 输出格式化 ───────────────────────────────────────────────


def _progress_bar(score: int, max_score: int, width: int = 20) -> str:
    filled = round(score / max_score * width) if max_score else 0
    return "█" * filled + "░" * (width - filled)


def print_report(report: QualityReport) -> None:
    grade_colors = {"A": "🟢", "B": "🟡", "C": "🔴"}
    icon = grade_colors.get(report.grade, "⚪")

    print(f"\n{'─' * 50}")
    print(f"  {report.file_path}")
    print(f"{'─' * 50}")

    for dim in report.dimensions:
        bar = _progress_bar(dim.score, dim.max_score)
        pct = round(dim.score / dim.max_score * 100) if dim.max_score else 0
        print(f"  {dim.name:<6} {bar} {dim.score:>3}/{dim.max_score}  {dim.detail}")

    print(f"{'─' * 50}")
    print(f"  总分: {report.total}/100  等级: {icon} {report.grade}")


def print_summary(reports: list[QualityReport]) -> None:
    if not reports:
        return

    grade_counts = {"A": 0, "B": 0, "C": 0}
    for r in reports:
        grade_counts[r.grade] += 1

    total = sum(r.total for r in reports)
    avg = round(total / len(reports)) if reports else 0

    print(f"\n{'═' * 50}")
    print(f"  汇总: {len(reports)} 个条目")
    print(f"  平均分: {avg}/100")
    print(f"  等级分布: 🟢 A={grade_counts['A']}  "
          f"🟡 B={grade_counts['B']}  🔴 C={grade_counts['C']}")
    print(f"{'═' * 50}")


# ─── 入口 ─────────────────────────────────────────────────────


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python hooks/check_quality.py "
              "<json_file> [json_file2 ...]")
        sys.exit(1)

    all_reports: list[QualityReport] = []

    for arg in sys.argv[1:]:
        path = Path(arg)
        if path.is_file():
            result = score_file(path)
            if result is None:
                print(f"[{arg}] 无法评分（文件不存在或 JSON 无效）")
                continue
            if isinstance(result, list):
                for r in result:
                    print_report(r)
                    all_reports.append(r)
            else:
                print_report(result)
                all_reports.append(result)
        elif "*" in arg or "?" in arg:
            matches = sorted(Path(p) for p in globmod.glob(arg))
            if not matches:
                print(f"[{arg}] 未匹配到任何文件")
                continue
            for match in matches:
                if match.is_file():
                    result = score_file(match)
                    if result is None:
                        print(f"[{match}] 无法评分")
                        continue
                    if isinstance(result, list):
                        for r in result:
                            print_report(r)
                            all_reports.append(r)
                    else:
                        print_report(result)
                        all_reports.append(result)
        elif path.exists():
            print(f"[{arg}] 不是文件")
        else:
            print(f"[{arg}] 文件不存在")

    print_summary(all_reports)

    has_c = any(r.grade == "C" for r in all_reports)
    sys.exit(1 if has_c else 0)


if __name__ == "__main__":
    main()
