#!/usr/bin/env python
"""知识条目 JSON 文件校验脚本。

支持单文件和多文件（通配符）两种输入模式，对知识条目 JSON
进行全面的结构和内容校验。

用法:
    python hooks/validate_json.py <json_file> [json_file2 ...]
    python hooks/validate_json.py knowledge/articles/*.json
"""

import glob as globmod
import json
import re
import sys
from pathlib import Path

REQUIRED_FIELDS: dict[str, type] = {
    "id": str,
    "title": str,
    "source_url": str,
    "summary": str,
    "tags": list,
    "status": str,
}

VALID_STATUSES = {"draft", "review", "published", "archived"}

VALID_AUDIENCES = {"beginner", "intermediate", "advanced"}

URL_PATTERN = re.compile(r"^https?://\S+$")

ID_PATTERN = re.compile(r"^[a-z]+-\d{8}-\d{3}$")

SUMMARY_MIN_LENGTH = 20

TAGS_MIN_COUNT = 1

SCORE_MIN = 1
SCORE_MAX = 10


def validate_entry(data: dict, file_path: Path) -> list[str]:
    """校验单个知识条目。

    Args:
        data: 解析后的 JSON 字典。
        file_path: 文件路径，用于错误信息定位。

    Returns:
        该条目的所有校验错误列表。
    """
    errors: list[str] = []
    prefix = f"[{file_path}]"

    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in data:
            errors.append(f"{prefix} 缺少必填字段: {field}")
        elif not isinstance(data[field], expected_type):
            actual = type(data[field]).__name__
            errors.append(
                f"{prefix} 字段类型错误: {field} "
                f"期望 {expected_type.__name__}，实际 {actual}"
            )

    if "id" in data and isinstance(data["id"], str):
        if not ID_PATTERN.match(data["id"]):
            errors.append(
                f"{prefix} ID 格式错误: '{data['id']}' "
                f"应为 {{source}}-{{YYYYMMDD}}-{{NNN}}"
            )

    if "status" in data and isinstance(data["status"], str):
        if data["status"] not in VALID_STATUSES:
            errors.append(
                f"{prefix} status 值无效: '{data['status']}' "
                f"应为 {VALID_STATUSES}"
            )

    if "source_url" in data and isinstance(data["source_url"], str):
        if not URL_PATTERN.match(data["source_url"]):
            errors.append(
                f"{prefix} URL 格式无效: '{data['source_url']}'"
            )

    if "summary" in data and isinstance(data["summary"], str):
        if len(data["summary"]) < SUMMARY_MIN_LENGTH:
            errors.append(
                f"{prefix} 摘要过短: {len(data['summary'])} 字"
                f"（最少 {SUMMARY_MIN_LENGTH} 字）"
            )

    if "tags" in data and isinstance(data["tags"], list):
        if len(data["tags"]) < TAGS_MIN_COUNT:
            errors.append(
                f"{prefix} 标签数量不足: {len(data['tags'])} 个"
                f"（最少 {TAGS_MIN_COUNT} 个）"
            )

    if "score" in data:
        score = data["score"]
        if not isinstance(score, (int, float)):
            errors.append(
                f"{prefix} score 类型错误: 期望数值，"
                f"实际 {type(score).__name__}"
            )
        elif not (SCORE_MIN <= score <= SCORE_MAX):
            errors.append(
                f"{prefix} score 超出范围: {score}"
                f"（应在 {SCORE_MIN}-{SCORE_MAX}）"
            )

    if "audience" in data and isinstance(data["audience"], str):
        if data["audience"] not in VALID_AUDIENCES:
            errors.append(
                f"{prefix} audience 值无效: '{data['audience']}'"
                f" 应为 {VALID_AUDIENCES}"
            )

    return errors


def validate_file(file_path: Path) -> list[str]:
    """校验单个 JSON 文件。

    Args:
        file_path: JSON 文件路径。

    Returns:
        该文件的所有校验错误列表。
    """
    errors: list[str] = []
    prefix = f"[{file_path}]"

    if not file_path.exists():
        return [f"{prefix} 文件不存在"]

    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{prefix} 读取失败: {exc}"]

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [f"{prefix} JSON 解析失败: {exc}"]

    if isinstance(data, list):
        for idx, entry in enumerate(data):
            if not isinstance(entry, dict):
                errors.append(
                    f"{prefix} 第 {idx} 项不是对象"
                )
                continue
            errors.extend(validate_entry(entry, file_path))
    elif isinstance(data, dict):
        errors.extend(validate_entry(data, file_path))
    else:
        errors.append(
            f"{prefix} JSON 根类型无效: 期望 object 或 array"
        )

    return errors


def main() -> None:
    """入口函数：解析参数并执行校验。"""
    if len(sys.argv) < 2:
        print("用法: python hooks/validate_json.py "
              "<json_file> [json_file2 ...]")
        sys.exit(1)

    all_errors: list[str] = []
    file_count = 0

    for arg in sys.argv[1:]:
        path = Path(arg)
        if path.is_file():
            file_count += 1
            all_errors.extend(validate_file(path))
        elif "*" in arg or "?" in arg:
            matches = sorted(
                Path(p) for p in globmod.glob(arg)
            )
            if not matches:
                all_errors.append(f"[{arg}] 未匹配到任何文件")
                continue
            for match in matches:
                if match.is_file():
                    file_count += 1
                    all_errors.extend(validate_file(match))
        elif path.exists():
            all_errors.append(f"[{arg}] 不是文件")
        else:
            all_errors.append(f"[{arg}] 文件不存在")

    if all_errors:
        print(f"校验失败，共 {len(all_errors)} 个错误:\n")
        for err in all_errors:
            print(f"  - {err}")
        print(f"\n统计: {file_count} 个文件, "
              f"{len(all_errors)} 个错误")
        sys.exit(1)

    print(f"校验通过: {file_count} 个文件全部合格")
    sys.exit(0)


if __name__ == "__main__":
    main()
