"""distribution.formatter 单元测试。"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from distribution.formatter import (
    _escape_telegram_markdown,
    _get_article_field,
    _get_feishu_template_color,
    _get_score_emoji,
    generate_daily_digest,
    json_to_feishu,
    json_to_markdown,
    json_to_telegram,
)

# 测试用文章数据
SAMPLE_ARTICLE = {
    "id": "2026-04-11-000",
    "title": "langgenius/dify",
    "source": "github",
    "url": "https://github.com/langgenius/dify",
    "collected_at": "2026-04-11T16:03:47.946653+00:00",
    "summary": "Dify 是一个开源 LLM 应用开发平台...",
    "tags": ["LLM应用开发", "智能体工作流", "RAG"],
    "relevance_score": 0.9,
    "category": "framework",
    "key_insight": "Dify 通过一体化平台显著降低 AI 工作流开发门槛",
}

# 实际项目中的文章数据格式
REAL_ARTICLE = {
    "id": "github-20260505-001",
    "title": "Karpathy 的自动研究项目：单GPU nanochat训练的AI代理",
    "source_url": "https://github.com/karpathy/autoresearch",
    "source_type": "github_trending",
    "summary": "该项目由Andrej Karpathy创建，利用AI代理自动执行单GPU上nanochat模型的训练研究。",
    "tags": ["ai-agents", "automated-ml", "nanochat"],
    "score": 9,
    "published_at": "2026-03-06T22:00:43Z",
    "fetched_at": "2026-05-05T13:32:42.464158+00:00",
    "analyzed_at": "2026-05-05T13:33:31.892899+00:00",
    "status": "published",
}


class TestGetArticleField:
    """测试 _get_article_field 辅助函数。"""

    def test_direct_field(self):
        """测试直接字段匹配。"""
        assert _get_article_field(SAMPLE_ARTICLE, "title") == "langgenius/dify"

    def test_url_alias(self):
        """测试 url 字段别名。"""
        assert _get_article_field(SAMPLE_ARTICLE, "source_url") == "https://github.com/langgenius/dify"

    def test_source_alias(self):
        """测试 source 字段别名。"""
        assert _get_article_field(SAMPLE_ARTICLE, "source_type") == "github"

    def test_score_alias(self):
        """测试 score 字段别名。"""
        assert _get_article_field(SAMPLE_ARTICLE, "relevance_score") == 0.9

    def test_default_value(self):
        """测试默认值返回。"""
        assert _get_article_field(SAMPLE_ARTICLE, "nonexistent", "default") == "default"

    def test_real_article_source_url(self):
        """测试实际文章格式的 source_url。"""
        assert _get_article_field(REAL_ARTICLE, "source_url") == "https://github.com/karpathy/autoresearch"


class TestEscapeTelegramMarkdown:
    """测试 _escape_telegram_markdown 辅助函数。"""

    def test_escape_special_chars(self):
        """测试特殊字符转义。"""
        text = "Hello_World*test[special]"
        expected = "Hello\\_World\\*test\\[special\\]"
        assert _escape_telegram_markdown(text) == expected

    def test_no_special_chars(self):
        """测试无特殊字符的情况。"""
        text = "Hello World 123"
        assert _escape_telegram_markdown(text) == text

    def test_all_special_chars(self):
        """测试所有特殊字符。"""
        text = "_*[]()~`>#+-=|{}.!"
        expected = "\\_\\*\\[\\]\\(\\)\\~\\`\\>\\#\\+\\-\\=\\|\\{\\}\\.\\!"
        assert _escape_telegram_markdown(text) == expected


class TestGetScoreEmoji:
    """测试 _get_score_emoji 辅助函数。"""

    def test_high_score(self):
        """测试高分 emoji。"""
        assert _get_score_emoji(0.9) == "🟢"

    def test_medium_score(self):
        """测试中分 emoji。"""
        assert _get_score_emoji(0.7) == "🟡"

    def test_low_score(self):
        """测试低分 emoji。"""
        assert _get_score_emoji(0.5) == "🔴"

    def test_boundary_high(self):
        """测试高分边界值。"""
        assert _get_score_emoji(0.8) == "🟢"

    def test_boundary_medium(self):
        """测试中分边界值。"""
        assert _get_score_emoji(0.6) == "🟡"


class TestGetFeishuTemplateColor:
    """测试 _get_feishu_template_color 辅助函数。"""

    def test_high_score(self):
        """测试高分颜色。"""
        assert _get_feishu_template_color(0.9) == "green"

    def test_medium_score(self):
        """测试中分颜色。"""
        assert _get_feishu_template_color(0.7) == "yellow"

    def test_low_score(self):
        """测试低分颜色。"""
        assert _get_feishu_template_color(0.5) == "red"


class TestJsonToMarkdown:
    """测试 json_to_markdown 函数。"""

    def test_basic_format(self):
        """测试基本 Markdown 格式。"""
        result = json_to_markdown(SAMPLE_ARTICLE)
        assert "# langgenius/dify" in result
        assert "**来源**: github" in result
        assert "**日期**: 2026-04-11" in result
        assert "🟢 0.90" in result
        assert "LLM应用开发, 智能体工作流, RAG" in result
        assert "Dify 是一个开源 LLM 应用开发平台..." in result
        assert "[查看原文](https://github.com/langgenius/dify)" in result

    def test_real_article_format(self):
        """测试实际文章格式。"""
        result = json_to_markdown(REAL_ARTICLE)
        assert "# Karpathy 的自动研究项目：单GPU nanochat训练的AI代理" in result
        assert "**来源**: github_trending" in result

    def test_missing_fields(self):
        """测试缺少字段的情况。"""
        minimal_article = {"id": "test-001"}
        result = json_to_markdown(minimal_article)
        assert "未知标题" in result
        assert "未知来源" in result
        assert "未知日期" in result


class TestJsonToTelegram:
    """测试 json_to_telegram 函数。"""

    def test_basic_format(self):
        """测试基本 Telegram 格式。"""
        result = json_to_telegram(SAMPLE_ARTICLE)
        assert "*langgenius/dify*" in result
        assert "🟢 0.90" in result
        assert "github" in result
        assert "查看原文" in result

    def test_special_chars_escaped(self):
        """测试特殊字符转义。"""
        article = SAMPLE_ARTICLE.copy()
        article["title"] = "Test_Title*Special"
        result = json_to_telegram(article)
        assert "Test\\_Title\\*Special" in result

    def test_tags_with_spaces(self):
        """测试标签空格替换为下划线。"""
        article = SAMPLE_ARTICLE.copy()
        article["tags"] = ["AI Agent", "LLM App"]
        result = json_to_telegram(article)
        assert "AI\\_Agent, LLM\\_App" in result


class TestJsonToFeishu:
    """测试 json_to_feishu 函数。"""

    def test_basic_structure(self):
        """测试基本飞书卡片结构。"""
        result = json_to_feishu(SAMPLE_ARTICLE)
        assert result["msg_type"] == "interactive"
        assert "card" in result
        assert "header" in result["card"]
        assert "elements" in result["card"]

    def test_header_template_green(self):
        """测试绿色模板（高分）。"""
        result = json_to_feishu(SAMPLE_ARTICLE)
        assert result["card"]["header"]["template"] == "green"

    def test_header_template_yellow(self):
        """测试黄色模板（中分）。"""
        article = SAMPLE_ARTICLE.copy()
        article["relevance_score"] = 0.7
        result = json_to_feishu(article)
        assert result["card"]["header"]["template"] == "yellow"

    def test_header_template_red(self):
        """测试红色模板（低分）。"""
        article = SAMPLE_ARTICLE.copy()
        article["relevance_score"] = 0.5
        result = json_to_feishu(article)
        assert result["card"]["header"]["template"] == "red"

    def test_elements_content(self):
        """测试卡片元素内容。"""
        result = json_to_feishu(SAMPLE_ARTICLE)
        elements = result["card"]["elements"]
        assert len(elements) >= 4  # 至少包含来源、评分、标签、分隔线、摘要、按钮

    def test_button_url(self):
        """测试按钮链接。"""
        result = json_to_feishu(SAMPLE_ARTICLE)
        actions = result["card"]["elements"][-1]["actions"]
        assert actions[0]["url"] == "https://github.com/langgenius/dify"


class TestGenerateDailyDigest:
    """测试 generate_daily_digest 函数。"""

    def test_with_articles(self, tmp_path):
        """测试有文章的情况。"""
        # 创建临时目录和文件
        articles_dir = tmp_path / "articles"
        articles_dir.mkdir()

        # 创建测试文章文件
        article1 = SAMPLE_ARTICLE.copy()
        article1["id"] = "2026-04-11-001"
        article1["relevance_score"] = 0.9

        article2 = SAMPLE_ARTICLE.copy()
        article2["id"] = "2026-04-11-002"
        article2["title"] = "另一个项目"
        article2["relevance_score"] = 0.7

        (articles_dir / "2026-04-11-001.json").write_text(json.dumps(article1))
        (articles_dir / "2026-04-11-002.json").write_text(json.dumps(article2))

        result = generate_daily_digest(str(articles_dir), "2026-04-11", top_n=5)

        assert "markdown" in result
        assert "telegram" in result
        assert "feishu" in result
        assert "每日知识简报" in result["markdown"]
        assert "2026-04-11" in result["markdown"]

    def test_no_articles(self, tmp_path):
        """测试无文章的情况。"""
        articles_dir = tmp_path / "articles"
        articles_dir.mkdir()

        result = generate_daily_digest(str(articles_dir), "2026-04-11")

        assert "📭 2026-04-11 暂无新增知识条目" in result["markdown"]
        assert "📭 2026-04-11 暂无新增知识条目" in result["telegram"]
        assert result["feishu"]["msg_type"] == "interactive"

    def test_nonexistent_directory(self):
        """测试不存在的目录。"""
        result = generate_daily_digest("/nonexistent/path", "2026-04-11")

        assert "📭 2026-04-11 暂无新增知识条目" in result["markdown"]

    def test_top_n_limit(self, tmp_path):
        """测试 Top N 限制。"""
        articles_dir = tmp_path / "articles"
        articles_dir.mkdir()

        # 创建 10 篇文章
        for i in range(10):
            article = SAMPLE_ARTICLE.copy()
            article["id"] = f"2026-04-11-{i:03d}"
            article["relevance_score"] = 0.9 - i * 0.1
            (articles_dir / f"2026-04-11-{i:03d}.json").write_text(json.dumps(article))

        result = generate_daily_digest(str(articles_dir), "2026-04-11", top_n=3)

        # Markdown 简报中应该只有 3 篇文章
        assert result["markdown"].count("## ") == 3

    def test_sort_by_score(self, tmp_path):
        """测试按评分排序。"""
        articles_dir = tmp_path / "articles"
        articles_dir.mkdir()

        article_low = SAMPLE_ARTICLE.copy()
        article_low["id"] = "2026-04-11-001"
        article_low["relevance_score"] = 0.5

        article_high = SAMPLE_ARTICLE.copy()
        article_high["id"] = "2026-04-11-002"
        article_high["title"] = "高分文章"
        article_high["relevance_score"] = 0.9

        (articles_dir / "2026-04-11-001.json").write_text(json.dumps(article_low))
        (articles_dir / "2026-04-11-002.json").write_text(json.dumps(article_high))

        result = generate_daily_digest(str(articles_dir), "2026-04-11", top_n=5)

        # 高分文章应该在前面
        markdown = result["markdown"]
        high_pos = markdown.find("高分文章")
        low_pos = markdown.find("langgenius/dify")
        assert high_pos < low_pos

    def test_default_date(self, tmp_path):
        """测试默认日期（今天）。"""
        articles_dir = tmp_path / "articles"
        articles_dir.mkdir()

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        article = SAMPLE_ARTICLE.copy()
        article["id"] = f"{today}-001"
        (articles_dir / f"{today}-001.json").write_text(json.dumps(article))

        result = generate_daily_digest(str(articles_dir))

        assert today in result["markdown"]