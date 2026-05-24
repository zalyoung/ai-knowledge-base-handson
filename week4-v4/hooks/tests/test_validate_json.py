"""hooks/validate_json.py 单元测试。

覆盖 validate_entry、validate_file、main 三个层级，
使用 hooks/tests/fixtures/ 下的 JSON 文件作为测试数据。
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
VALIDATE_SCRIPT = Path(__file__).parent.parent / "validate_json.py"


# ─── helpers ─────────────────────────────────────────────────


def _load_fixture(name: str) -> dict | list:
    """加载 fixture JSON 文件并返回解析后的数据。"""
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _valid_entry(**overrides) -> dict:
    """生成一个有效条目，可通过 overrides 覆盖任意字段。"""
    entry = {
        "id": "github-20260505-001",
        "title": "测试项目",
        "source_url": "https://github.com/test/repo",
        "summary": "这是一个超过二十个字符的测试摘要，用于校验脚本的长度检查。",
        "tags": ["test"],
        "status": "draft",
    }
    entry.update(overrides)
    return entry


def _run_main(*args: str) -> subprocess.CompletedProcess:
    """以子进程方式运行 validate_json.py。"""
    return subprocess.run(
        [sys.executable, str(VALIDATE_SCRIPT), *args],
        capture_output=True,
        text=True,
    )


# ─── validate_entry: 必填字段 ────────────────────────────────


class TestRequiredFields:
    """必填字段存在性与类型校验。"""

    def test_valid_entry_no_errors(self):
        from hooks.validate_json import validate_entry

        errors = validate_entry(_valid_entry(), Path("test.json"))
        assert errors == []

    def test_missing_id(self):
        from hooks.validate_json import validate_entry

        data = _valid_entry()
        del data["id"]
        errors = validate_entry(data, Path("test.json"))
        assert any("id" in e and "缺少" in e for e in errors)

    def test_missing_title(self):
        from hooks.validate_json import validate_entry

        data = _valid_entry()
        del data["title"]
        errors = validate_entry(data, Path("test.json"))
        assert any("title" in e and "缺少" in e for e in errors)

    def test_missing_source_url(self):
        from hooks.validate_json import validate_entry

        data = _valid_entry()
        del data["source_url"]
        errors = validate_entry(data, Path("test.json"))
        assert any("source_url" in e and "缺少" in e for e in errors)

    def test_missing_summary(self):
        from hooks.validate_json import validate_entry

        data = _valid_entry()
        del data["summary"]
        errors = validate_entry(data, Path("test.json"))
        assert any("summary" in e and "缺少" in e for e in errors)

    def test_missing_tags(self):
        from hooks.validate_json import validate_entry

        data = _valid_entry()
        del data["tags"]
        errors = validate_entry(data, Path("test.json"))
        assert any("tags" in e and "缺少" in e for e in errors)

    def test_missing_status(self):
        from hooks.validate_json import validate_entry

        data = _valid_entry()
        del data["status"]
        errors = validate_entry(data, Path("test.json"))
        assert any("status" in e and "缺少" in e for e in errors)

    def test_missing_all_required(self):
        from hooks.validate_json import validate_entry

        errors = validate_entry({}, Path("test.json"))
        assert len(errors) == 6

    def test_wrong_type_id(self):
        from hooks.validate_json import validate_entry

        errors = validate_entry(
            _valid_entry(id=12345), Path("test.json")
        )
        assert any("id" in e and "类型错误" in e for e in errors)

    def test_wrong_type_title(self):
        from hooks.validate_json import validate_entry

        errors = validate_entry(
            _valid_entry(title=["not", "str"]), Path("test.json")
        )
        assert any("title" in e and "类型错误" in e for e in errors)

    def test_wrong_type_source_url(self):
        from hooks.validate_json import validate_entry

        errors = validate_entry(
            _valid_entry(source_url=99), Path("test.json")
        )
        assert any("source_url" in e and "类型错误" in e for e in errors)

    def test_wrong_type_summary(self):
        from hooks.validate_json import validate_entry

        errors = validate_entry(
            _valid_entry(summary=False), Path("test.json")
        )
        assert any("summary" in e and "类型错误" in e for e in errors)

    def test_wrong_type_tags(self):
        from hooks.validate_json import validate_entry

        errors = validate_entry(
            _valid_entry(tags="should-be-list"), Path("test.json")
        )
        assert any("tags" in e and "类型错误" in e for e in errors)

    def test_wrong_type_status(self):
        from hooks.validate_json import validate_entry

        errors = validate_entry(
            _valid_entry(status=1), Path("test.json")
        )
        assert any("status" in e and "类型错误" in e for e in errors)


# ─── validate_entry: ID 格式 ─────────────────────────────────


class TestIdFormat:
    """ID 格式 {source}-{YYYYMMDD}-{NNN} 校验。"""

    @pytest.mark.parametrize("valid_id", [
        "github-20260505-001",
        "hackernews-20260317-042",
        "arxiv-20261231-999",
    ])
    def test_valid_ids(self, valid_id):
        from hooks.validate_json import validate_entry

        errors = validate_entry(
            _valid_entry(id=valid_id), Path("test.json")
        )
        id_errors = [e for e in errors if "ID 格式" in e]
        assert id_errors == []

    @pytest.mark.parametrize("invalid_id", [
        "69513680-0613-4457-8358-177e56620c95",
        "github-2026050-001",
        "github-202605050-001",
        "GitHub-20260505-001",
        "github-20260505-01",
        "github-20260505-0001",
        "20260505-001",
        "github-001",
        "",
    ])
    def test_invalid_ids(self, invalid_id):
        from hooks.validate_json import validate_entry

        errors = validate_entry(
            _valid_entry(id=invalid_id), Path("test.json")
        )
        assert any("ID 格式" in e for e in errors)


# ─── validate_entry: status 枚举 ─────────────────────────────


class TestStatusEnum:
    """status 枚举值校验。"""

    @pytest.mark.parametrize("valid_status", [
        "draft", "review", "published", "archived",
    ])
    def test_valid_statuses(self, valid_status):
        from hooks.validate_json import validate_entry

        errors = validate_entry(
            _valid_entry(status=valid_status), Path("test.json")
        )
        status_errors = [e for e in errors if "status" in e]
        assert status_errors == []

    @pytest.mark.parametrize("invalid_status", [
        "pending", "active", "done", "PUBLISHED", "",
    ])
    def test_invalid_statuses(self, invalid_status):
        from hooks.validate_json import validate_entry

        errors = validate_entry(
            _valid_entry(status=invalid_status), Path("test.json")
        )
        assert any("status" in e and "无效" in e for e in errors)


# ─── validate_entry: URL 格式 ─────────────────────────────────


class TestUrlFormat:
    """URL 格式校验。"""

    @pytest.mark.parametrize("valid_url", [
        "https://github.com/test/repo",
        "http://example.com/path",
        "https://news.ycombinator.com/item?id=12345",
    ])
    def test_valid_urls(self, valid_url):
        from hooks.validate_json import validate_entry

        errors = validate_entry(
            _valid_entry(source_url=valid_url), Path("test.json")
        )
        url_errors = [e for e in errors if "URL" in e]
        assert url_errors == []

    @pytest.mark.parametrize("invalid_url", [
        "ftp://files.example.com/repo",
        "not-a-url",
        "",
        "://missing-scheme.com",
    ])
    def test_invalid_urls(self, invalid_url):
        from hooks.validate_json import validate_entry

        errors = validate_entry(
            _valid_entry(source_url=invalid_url), Path("test.json")
        )
        assert any("URL" in e for e in errors)


# ─── validate_entry: 摘要长度 ─────────────────────────────────


class TestSummaryLength:
    """摘要最少 20 字校验。"""

    def test_summary_exactly_20_chars(self):
        from hooks.validate_json import validate_entry

        summary = "一二三四五六七八九十壹贰叁肆伍陆柒捌玖拾"
        assert len(summary) == 20
        errors = validate_entry(
            _valid_entry(summary=summary), Path("test.json")
        )
        summary_errors = [e for e in errors if "摘要" in e]
        assert summary_errors == []

    def test_summary_19_chars(self):
        from hooks.validate_json import validate_entry

        summary = "一二三四五六七八九十壹贰叁肆伍陆柒捌玖"
        assert len(summary) == 19
        errors = validate_entry(
            _valid_entry(summary=summary), Path("test.json")
        )
        assert any("摘要过短" in e for e in errors)

    def test_summary_empty(self):
        from hooks.validate_json import validate_entry

        errors = validate_entry(
            _valid_entry(summary=""), Path("test.json")
        )
        assert any("摘要过短" in e for e in errors)


# ─── validate_entry: 标签数量 ─────────────────────────────────


class TestTagsCount:
    """标签至少 1 个校验。"""

    def test_one_tag(self):
        from hooks.validate_json import validate_entry

        errors = validate_entry(
            _valid_entry(tags=["only-one"]), Path("test.json")
        )
        tag_errors = [e for e in errors if "标签" in e]
        assert tag_errors == []

    def test_multiple_tags(self):
        from hooks.validate_json import validate_entry

        errors = validate_entry(
            _valid_entry(tags=["a", "b", "c"]), Path("test.json")
        )
        tag_errors = [e for e in errors if "标签" in e]
        assert tag_errors == []

    def test_empty_tags(self):
        from hooks.validate_json import validate_entry

        errors = validate_entry(
            _valid_entry(tags=[]), Path("test.json")
        )
        assert any("标签数量不足" in e for e in errors)


# ─── validate_entry: 可选字段 score ───────────────────────────


class TestScore:
    """score 可选字段校验（1-10 范围，数值类型）。"""

    def test_no_score_field(self):
        from hooks.validate_json import validate_entry

        errors = validate_entry(_valid_entry(), Path("test.json"))
        score_errors = [e for e in errors if "score" in e]
        assert score_errors == []

    def test_score_int_in_range(self):
        from hooks.validate_json import validate_entry

        errors = validate_entry(
            _valid_entry(score=5), Path("test.json")
        )
        score_errors = [e for e in errors if "score" in e]
        assert score_errors == []

    def test_score_float_in_range(self):
        from hooks.validate_json import validate_entry

        errors = validate_entry(
            _valid_entry(score=7.5), Path("test.json")
        )
        score_errors = [e for e in errors if "score" in e]
        assert score_errors == []

    def test_score_boundary_min(self):
        from hooks.validate_json import validate_entry

        errors = validate_entry(
            _valid_entry(score=1), Path("test.json")
        )
        score_errors = [e for e in errors if "score" in e]
        assert score_errors == []

    def test_score_boundary_max(self):
        from hooks.validate_json import validate_entry

        errors = validate_entry(
            _valid_entry(score=10), Path("test.json")
        )
        score_errors = [e for e in errors if "score" in e]
        assert score_errors == []

    def test_score_below_min(self):
        from hooks.validate_json import validate_entry

        errors = validate_entry(
            _valid_entry(score=0), Path("test.json")
        )
        assert any("score" in e and "超出范围" in e for e in errors)

    def test_score_above_max(self):
        from hooks.validate_json import validate_entry

        errors = validate_entry(
            _valid_entry(score=11), Path("test.json")
        )
        assert any("score" in e and "超出范围" in e for e in errors)

    def test_score_negative(self):
        from hooks.validate_json import validate_entry

        errors = validate_entry(
            _valid_entry(score=-1), Path("test.json")
        )
        assert any("score" in e and "超出范围" in e for e in errors)

    def test_score_wrong_type(self):
        from hooks.validate_json import validate_entry

        errors = validate_entry(
            _valid_entry(score="high"), Path("test.json")
        )
        assert any("score" in e and "类型错误" in e for e in errors)

    def test_score_bool_true_is_valid(self):
        """bool 是 int 子类，True==1 在范围内，应通过。"""
        from hooks.validate_json import validate_entry

        errors = validate_entry(
            _valid_entry(score=True), Path("test.json")
        )
        score_errors = [e for e in errors if "score" in e]
        assert score_errors == []

    def test_score_bool_false_rejected(self):
        """bool 是 int 子类，False==0 超出范围。"""
        from hooks.validate_json import validate_entry

        errors = validate_entry(
            _valid_entry(score=False), Path("test.json")
        )
        assert any("score" in e and "超出范围" in e for e in errors)


# ─── validate_entry: 可选字段 audience ────────────────────────


class TestAudience:
    """audience 可选字段枚举校验。"""

    def test_no_audience_field(self):
        from hooks.validate_json import validate_entry

        errors = validate_entry(_valid_entry(), Path("test.json"))
        aud_errors = [e for e in errors if "audience" in e]
        assert aud_errors == []

    @pytest.mark.parametrize("valid_audience", [
        "beginner", "intermediate", "advanced",
    ])
    def test_valid_audiences(self, valid_audience):
        from hooks.validate_json import validate_entry

        errors = validate_entry(
            _valid_entry(audience=valid_audience), Path("test.json")
        )
        aud_errors = [e for e in errors if "audience" in e]
        assert aud_errors == []

    @pytest.mark.parametrize("invalid_audience", [
        "expert", "all", "ADVANCED", "",
    ])
    def test_invalid_audiences(self, invalid_audience):
        from hooks.validate_json import validate_entry

        errors = validate_entry(
            _valid_entry(audience=invalid_audience), Path("test.json")
        )
        assert any("audience" in e and "无效" in e for e in errors)


# ─── validate_entry: 错误累计 ─────────────────────────────────


class TestErrorAccumulation:
    """多个错误应被同时报告，而非短路。"""

    def test_multiple_errors_collected(self):
        from hooks.validate_json import validate_entry

        errors = validate_entry(
            _valid_entry(
                id="bad-id",
                status="pending",
                source_url="not-url",
                summary="短",
                tags=[],
                score=99,
            ),
            Path("test.json"),
        )
        assert len(errors) >= 6


# ─── validate_entry: 文件路径前缀 ─────────────────────────────


class TestFilePathPrefix:
    """错误信息中应包含文件路径。"""

    def test_prefix_in_error_message(self):
        from hooks.validate_json import validate_entry

        path = Path("some/path.json")
        errors = validate_entry({}, path)
        assert all(f"[{path}]" in e for e in errors)


# ─── validate_file: 文件级校验 ────────────────────────────────


class TestValidateFile:
    """validate_file 文件级校验。"""

    def test_valid_full_entry(self):
        from hooks.validate_json import validate_file

        errors = validate_file(FIXTURES_DIR / "valid_full.json")
        assert errors == []

    def test_valid_minimal_entry(self):
        from hooks.validate_json import validate_file

        errors = validate_file(FIXTURES_DIR / "valid_minimal.json")
        assert errors == []

    def test_valid_array(self):
        from hooks.validate_json import validate_file

        errors = validate_file(FIXTURES_DIR / "valid_array.json")
        assert errors == []

    def test_valid_boundary(self):
        from hooks.validate_json import validate_file

        errors = validate_file(FIXTURES_DIR / "valid_boundary.json")
        assert errors == []

    def test_file_not_exist(self):
        from hooks.validate_json import validate_file

        errors = validate_file(FIXTURES_DIR / "nonexistent.json")
        assert len(errors) == 1
        assert "文件不存在" in errors[0]

    def test_malformed_json(self):
        from hooks.validate_json import validate_file

        errors = validate_file(FIXTURES_DIR / "malformed.json")
        assert any("JSON 解析失败" in e for e in errors)

    def test_root_string(self):
        from hooks.validate_json import validate_file

        errors = validate_file(FIXTURES_DIR / "root_string.json")
        assert any("根类型无效" in e for e in errors)

    def test_array_mixed(self):
        from hooks.validate_json import validate_file

        errors = validate_file(FIXTURES_DIR / "array_mixed.json")
        assert any("第 1 项不是对象" in e for e in errors)
        assert any("第 2 项不是对象" in e for e in errors)

    def test_missing_fields(self):
        from hooks.validate_json import validate_file

        errors = validate_file(FIXTURES_DIR / "missing_fields.json")
        assert len(errors) >= 4

    def test_wrong_types(self):
        from hooks.validate_json import validate_file

        errors = validate_file(FIXTURES_DIR / "wrong_types.json")
        assert len(errors) >= 6

    def test_invalid_id(self):
        from hooks.validate_json import validate_file

        errors = validate_file(FIXTURES_DIR / "invalid_id.json")
        assert any("ID 格式" in e for e in errors)

    def test_invalid_status(self):
        from hooks.validate_json import validate_file

        errors = validate_file(FIXTURES_DIR / "invalid_status.json")
        assert any("status" in e and "无效" in e for e in errors)

    def test_invalid_url(self):
        from hooks.validate_json import validate_file

        errors = validate_file(FIXTURES_DIR / "invalid_url.json")
        assert any("URL" in e for e in errors)

    def test_short_summary(self):
        from hooks.validate_json import validate_file

        errors = validate_file(FIXTURES_DIR / "short_summary.json")
        assert any("摘要过短" in e for e in errors)

    def test_empty_tags(self):
        from hooks.validate_json import validate_file

        errors = validate_file(FIXTURES_DIR / "empty_tags.json")
        assert any("标签数量不足" in e for e in errors)

    def test_invalid_score_range(self):
        from hooks.validate_json import validate_file

        errors = validate_file(FIXTURES_DIR / "invalid_score.json")
        assert any("score" in e and "超出范围" in e for e in errors)
        assert any("audience" in e and "无效" in e for e in errors)

    def test_score_wrong_type(self):
        from hooks.validate_json import validate_file

        errors = validate_file(
            FIXTURES_DIR / "score_wrong_type.json"
        )
        assert any("score" in e and "类型错误" in e for e in errors)


# ─── main: 集成测试 ───────────────────────────────────────────


class TestMain:
    """命令行入口集成测试。"""

    def test_no_arguments_exits_1(self):
        result = _run_main()
        assert result.returncode == 1
        assert "用法" in result.stdout

    def test_valid_file_exits_0(self):
        result = _run_main(str(FIXTURES_DIR / "valid_full.json"))
        assert result.returncode == 0
        assert "校验通过" in result.stdout

    def test_invalid_file_exits_1(self):
        result = _run_main(str(FIXTURES_DIR / "invalid_id.json"))
        assert result.returncode == 1
        assert "校验失败" in result.stdout

    def test_nonexistent_path_exits_1(self):
        result = _run_main("/tmp/definitely_not_exist_12345.json")
        assert result.returncode == 1
        assert "文件不存在" in result.stdout

    def test_multiple_files_mixed(self):
        result = _run_main(
            str(FIXTURES_DIR / "valid_full.json"),
            str(FIXTURES_DIR / "invalid_id.json"),
        )
        assert result.returncode == 1
        assert "校验失败" in result.stdout

    def test_multiple_files_all_valid(self):
        result = _run_main(
            str(FIXTURES_DIR / "valid_full.json"),
            str(FIXTURES_DIR / "valid_minimal.json"),
        )
        assert result.returncode == 0
        assert "2 个文件" in result.stdout

    def test_glob_pattern(self):
        result = _run_main(str(FIXTURES_DIR / "valid_*.json"))
        assert result.returncode == 0
        assert "校验通过" in result.stdout

    def test_glob_no_match(self):
        result = _run_main(str(FIXTURES_DIR / "zzz_*.json"))
        assert result.returncode == 1
        assert "未匹配到任何文件" in result.stdout

    def test_directory_path_exits_1(self):
        result = _run_main(str(FIXTURES_DIR))
        assert result.returncode == 1
        assert "不是文件" in result.stdout

    def test_error_count_in_output(self):
        result = _run_main(str(FIXTURES_DIR / "missing_fields.json"))
        assert result.returncode == 1
        assert "统计" in result.stdout
