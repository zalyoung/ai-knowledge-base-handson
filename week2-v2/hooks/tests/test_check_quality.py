"""hooks/check_quality.py 单元测试（TDD 先行）。

覆盖 5 维度评分、等级判定、退出码等全部逻辑。
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SCRIPT = Path(__file__).parent.parent / "check_quality.py"


# ─── helpers ─────────────────────────────────────────────────


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _entry(**overrides) -> dict:
    base = {
        "id": "github-20260505-001",
        "title": "LangGraph v0.3 发布：支持多 Agent 协同",
        "source_url": "https://github.com/langchain-ai/langgraph/releases/tag/v0.3.0",
        "summary": "LangGraph 在 v0.3 中引入了 SupervisorAgent 模式，允许多个子 Agent 在统一调度下并行执行，显著提升了复杂工作流的编排能力。",
        "tags": ["langgraph", "multi-agent", "orchestration"],
        "score": 8,
        "status": "draft",
        "published_at": "2026-05-02T08:30:00Z",
        "fetched_at": "2026-05-02T09:00:00Z",
        "analyzed_at": "2026-05-02T09:15:00Z",
    }
    base.update(overrides)
    return base


def _run_main(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
    )


# ─── dataclass 结构 ──────────────────────────────────────────


class TestDataclassStructure:
    """验证 DimensionScore 和 QualityReport 的字段定义。"""

    def test_dimension_score_fields(self):
        from hooks.check_quality import DimensionScore

        ds = DimensionScore(name="测试", score=10, max_score=25, detail="")
        assert ds.name == "测试"
        assert ds.score == 10
        assert ds.max_score == 25
        assert ds.detail == ""

    def test_quality_report_fields(self):
        from hooks.check_quality import QualityReport, DimensionScore

        dims = [DimensionScore("d1", 5, 10, "")]
        report = QualityReport(
            file_path=Path("test.json"),
            dimensions=dims,
            total=5,
            grade="C",
        )
        assert report.file_path == Path("test.json")
        assert len(report.dimensions) == 1
        assert report.total == 5
        assert report.grade == "C"


# ─── 摘要质量 (25 分) ───────────────────────────────────────


class TestSummaryQuality:
    MAX = 25

    def test_empty_summary_zero(self):
        from hooks.check_quality import score_summary

        result = score_summary("")
        assert result.score == 0

    def test_under_20_chars_zero(self):
        from hooks.check_quality import score_summary

        result = score_summary("太短了")
        assert result.score == 0

    def test_exactly_20_chars_basic(self):
        from hooks.check_quality import score_summary

        text = "一二三四五六七八九十壹贰叁肆伍陆柒捌玖拾"
        assert len(text) == 20
        result = score_summary(text)
        assert result.score > 0
        assert result.score < self.MAX

    def test_50_chars_full(self):
        from hooks.check_quality import score_summary

        text = "这是一段五十个字符的摘要文本，用于测试满分情况。" \
               "需要包含足够的内容来达到五十个字符的要求，这是最后的补充文字。"
        assert len(text) >= 50
        result = score_summary(text)
        assert result.score == self.MAX

    def test_tech_keyword_bonus(self):
        from hooks.check_quality import score_summary

        base = "这段摘要刚好二十个字符。"
        with_kw = "这段摘要包含 Agent 和 RAG 技术关键词。"
        r1 = score_summary(base)
        r2 = score_summary(with_kw)
        assert r2.score >= r1.score

    def test_max_not_exceeded(self):
        from hooks.check_quality import score_summary

        long = "这是一个非常长的摘要" * 20 + "Agent LLM RAG"
        result = score_summary(long)
        assert result.score <= self.MAX


# ─── 技术深度 (25 分) ───────────────────────────────────────


class TestTechnicalDepth:
    MAX = 25

    def test_no_score_field_zero(self):
        from hooks.check_quality import score_depth

        result = score_depth({})
        assert result.score == 0

    def test_score_10_full(self):
        from hooks.check_quality import score_depth

        result = score_depth({"score": 10})
        assert result.score == self.MAX

    def test_score_1_low(self):
        from hooks.check_quality import score_depth

        result = score_depth({"score": 1})
        assert 0 < result.score < self.MAX

    def test_score_5_half(self):
        from hooks.check_quality import score_depth

        result = score_depth({"score": 5})
        assert result.score == pytest.approx(self.MAX / 2, abs=1)

    def test_score_0_zero(self):
        from hooks.check_quality import score_depth

        result = score_depth({"score": 0})
        assert result.score == 0

    def test_proportional(self):
        from hooks.check_quality import score_depth

        r3 = score_depth({"score": 3})
        r7 = score_depth({"score": 7})
        assert r3.score < r7.score


# ─── 格式规范 (20 分) ───────────────────────────────────────


class TestFormatCompliance:
    MAX = 20

    def test_all_present_full(self):
        from hooks.check_quality import score_format

        data = _entry()
        result = score_format(data)
        assert result.score == self.MAX

    def test_missing_id_deducted(self):
        from hooks.check_quality import score_format

        data = _entry()
        del data["id"]
        result = score_format(data)
        assert result.score < self.MAX

    def test_missing_title_deducted(self):
        from hooks.check_quality import score_format

        data = _entry()
        del data["title"]
        result = score_format(data)
        assert result.score < self.MAX

    def test_missing_source_url_deducted(self):
        from hooks.check_quality import score_format

        data = _entry()
        del data["source_url"]
        result = score_format(data)
        assert result.score < self.MAX

    def test_missing_status_deducted(self):
        from hooks.check_quality import score_format

        data = _entry()
        del data["status"]
        result = score_format(data)
        assert result.score < self.MAX

    def test_missing_timestamps_deducted(self):
        from hooks.check_quality import score_format

        data = _entry()
        del data["published_at"]
        del data["fetched_at"]
        del data["analyzed_at"]
        result = score_format(data)
        assert result.score < self.MAX

    def test_empty_dict_zero(self):
        from hooks.check_quality import score_format

        result = score_format({})
        assert result.score == 0


# ─── 标签精度 (15 分) ───────────────────────────────────────


class TestTagPrecision:
    MAX = 15

    def test_3_tags_full(self):
        from hooks.check_quality import score_tags

        result = score_tags(["python", "api", "agent"])
        assert result.score == self.MAX

    def test_1_tag_full(self):
        from hooks.check_quality import score_tags

        result = score_tags(["python"])
        assert result.score == self.MAX

    def test_no_tags_zero(self):
        from hooks.check_quality import score_tags

        result = score_tags([])
        assert result.score == 0

    def test_too_many_tags_deducted(self):
        from hooks.check_quality import score_tags

        result = score_tags(["a", "b", "c", "d", "e", "f"])
        assert result.score < self.MAX

    def test_mixed_valid_invalid(self):
        from hooks.check_quality import score_tags

        result = score_tags(["python", "UPPERCASE", "!!!"])
        assert result.score < self.MAX

    def test_invalid_format_deducted(self):
        from hooks.check_quality import score_tags

        result = score_tags(["valid-tag", "INVALID TAG!", ""])
        assert result.score < self.MAX


# ─── 空洞词检测 (15 分) ─────────────────────────────────────


class TestBuzzwordDetection:
    MAX = 15

    def test_clean_summary_full(self):
        from hooks.check_quality import score_buzzwords

        result = score_buzzwords("这是一个干净的技术摘要，介绍 Agent 协同架构。")
        assert result.score == self.MAX

    def test_one_chinese_buzzword(self):
        from hooks.check_quality import score_buzzwords

        result = score_buzzwords("这个方案具有强大的赋能能力，提升效率。")
        assert result.score < self.MAX

    def test_one_english_buzzword(self):
        from hooks.check_quality import score_buzzwords

        result = score_buzzwords(
            "This is a groundbreaking framework for AI agents."
        )
        assert result.score < self.MAX

    def test_multiple_buzzwords_lower(self):
        from hooks.check_quality import score_buzzwords

        r1 = score_buzzwords("这个方案有赋能效果。")
        r2 = score_buzzwords("赋能抓手闭环打通全链路。")
        assert r2.score < r1.score

    def test_empty_string_full(self):
        from hooks.check_quality import score_buzzwords

        result = score_buzzwords("")
        assert result.score == self.MAX

    def test_all_chinese_blacklist_words(self):
        from hooks.check_quality import BUZZWORDS_CN, score_buzzwords

        for word in BUZZWORDS_CN:
            result = score_buzzwords(f"摘要中包含{word}这个词。")
            assert result.score < self.MAX, f"'{word}' 应被检测"

    def test_all_english_blacklist_words(self):
        from hooks.check_quality import BUZZWORDS_EN, score_buzzwords

        for word in BUZZWORDS_EN:
            result = score_buzzwords(f"This has {word} inside.")
            assert result.score < self.MAX, f"'{word}' should be detected"


# ─── 等级判定 ────────────────────────────────────────────────


class TestGrade:
    def test_grade_a(self):
        from hooks.check_quality import compute_grade

        assert compute_grade(80) == "A"
        assert compute_grade(95) == "A"
        assert compute_grade(100) == "A"

    def test_grade_b(self):
        from hooks.check_quality import compute_grade

        assert compute_grade(60) == "B"
        assert compute_grade(79) == "B"

    def test_grade_c(self):
        from hooks.check_quality import compute_grade

        assert compute_grade(0) == "C"
        assert compute_grade(59) == "C"


# ─── evaluate_entry 集成 ─────────────────────────────────────


class TestEvaluateEntry:
    def test_full_entry_high_score(self):
        from hooks.check_quality import evaluate_entry

        data = _entry()
        report = evaluate_entry(data, Path("test.json"))
        assert report.total >= 80
        assert report.grade == "A"

    def test_minimal_entry_low_score(self):
        from hooks.check_quality import evaluate_entry

        data = {
            "id": "x-20260101-001",
            "title": "T",
            "source_url": "https://x.com",
            "summary": "短",
            "tags": [],
            "status": "draft",
        }
        report = evaluate_entry(data, Path("test.json"))
        assert report.total < 60
        assert report.grade == "C"

    def test_total_is_sum_of_dimensions(self):
        from hooks.check_quality import evaluate_entry

        report = evaluate_entry(_entry(), Path("test.json"))
        dim_sum = sum(d.score for d in report.dimensions)
        assert report.total == dim_sum

    def test_dimensions_count_is_5(self):
        from hooks.check_quality import evaluate_entry

        report = evaluate_entry(_entry(), Path("test.json"))
        assert len(report.dimensions) == 5

    def test_total_max_100(self):
        from hooks.check_quality import evaluate_entry

        report = evaluate_entry(_entry(), Path("test.json"))
        assert report.total <= 100

    def test_buzzword_entry_penalized(self):
        from hooks.check_quality import evaluate_entry

        clean = evaluate_entry(_entry(), Path("test.json"))
        dirty = evaluate_entry(
            _entry(summary="这个赋能抓手具有革命性的groundbreaking效果"),
            Path("test.json"),
        )
        assert dirty.total < clean.total


# ─── score_file 文件级 ───────────────────────────────────────


class TestScoreFile:
    def test_valid_file_returns_report(self):
        from hooks.check_quality import score_file

        report = score_file(FIXTURES_DIR / "valid_full.json")
        assert report is not None
        assert report.grade in ("A", "B", "C")

    def test_nonexistent_file_none(self):
        from hooks.check_quality import score_file

        report = score_file(FIXTURES_DIR / "nonexistent.json")
        assert report is None

    def test_malformed_json_none(self):
        from hooks.check_quality import score_file

        report = score_file(FIXTURES_DIR / "malformed.json")
        assert report is None

    def test_array_file_returns_list(self):
        from hooks.check_quality import score_file

        result = score_file(FIXTURES_DIR / "valid_array.json")
        assert isinstance(result, list)
        assert len(result) == 2


# ─── main 集成 ───────────────────────────────────────────────


class TestMain:
    def test_no_args_exits_1(self):
        result = _run_main()
        assert result.returncode == 1

    def test_valid_full_exits_0(self):
        result = _run_main(str(FIXTURES_DIR / "valid_full.json"))
        assert result.returncode == 0

    def test_output_contains_grade(self):
        result = _run_main(str(FIXTURES_DIR / "valid_full.json"))
        assert "A" in result.stdout or "B" in result.stdout or "C" in result.stdout

    def test_output_contains_dimensions(self):
        result = _run_main(str(FIXTURES_DIR / "valid_full.json"))
        assert "摘要质量" in result.stdout
        assert "技术深度" in result.stdout
        assert "格式规范" in result.stdout
        assert "标签精度" in result.stdout
        assert "空洞词" in result.stdout

    def test_c_grade_exits_1(self):
        result = _run_main(str(FIXTURES_DIR / "short_summary.json"))
        assert result.returncode == 1

    def test_glob_pattern(self):
        result = _run_main(str(FIXTURES_DIR / "valid_*.json"))
        assert result.returncode in (0, 1)

    def test_multiple_files(self):
        result = _run_main(
            str(FIXTURES_DIR / "valid_full.json"),
            str(FIXTURES_DIR / "valid_minimal.json"),
        )
        assert "总分" in result.stdout or "汇总" in result.stdout
