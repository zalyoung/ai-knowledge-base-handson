"""格式化模块：将知识条目 JSON 转换为多种分发渠道所需格式。

本模块提供纯函数，不进行任何网络请求。支持以下输出格式：
- Markdown：用于静态展示
- Telegram MarkdownV2：用于 Telegram 消息推送
- 飞书 Interactive Card：用于飞书机器人消息
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Telegram MarkdownV2 需要转义的特殊字符
_TELEGRAM_SPECIAL_CHARS = r"_*[]()~`>#+-=|{}.!"

# 飞书卡片模板颜色映射
_FEISHU_TEMPLATE_COLORS = {
    "green": "green",
    "yellow": "yellow",
    "red": "red",
}


def _get_article_field(article: Dict[str, Any], field_name: str, default: Any = None) -> Any:
    """从文章字典中获取字段值，支持多种字段名称变体。

    Args:
        article: 文章字典。
        field_name: 字段名称。
        default: 默认值，当字段不存在时返回。

    Returns:
        字段值或默认值。
    """
    # 直接匹配
    if field_name in article:
        return article[field_name]

    # 字段名称变体映射
    field_aliases = {
        "source_url": ["url", "link", "source"],
        "source_type": ["source", "type"],
        "relevance_score": ["score", "relevance", "priority"],
        "published_at": ["date", "published", "created_at"],
    }

    if field_name in field_aliases:
        for alias in field_aliases[field_name]:
            if alias in article:
                return article[alias]

    return default


def _escape_telegram_markdown(text: str) -> str:
    """转义 Telegram MarkdownV2 特殊字符。

    Args:
        text: 需要转义的文本。

    Returns:
        转义后的文本。
    """
    escaped = text
    for char in _TELEGRAM_SPECIAL_CHARS:
        escaped = escaped.replace(char, f"\\{char}")
    return escaped


def _get_score_emoji(score: float) -> str:
    """根据相关性评分返回对应的 emoji。

    Args:
        score: 相关性评分（0-1 之间）。

    Returns:
        对应的 emoji 字符。
    """
    if score >= 0.8:
        return "🟢"
    elif score >= 0.6:
        return "🟡"
    else:
        return "🔴"


def _get_feishu_template_color(score: float) -> str:
    """根据相关性评分返回飞书卡片模板颜色。

    Args:
        score: 相关性评分（0-1 之间）。

    Returns:
        飞书卡片模板颜色名称。
    """
    if score >= 0.8:
        return "green"
    elif score >= 0.6:
        return "yellow"
    else:
        return "red"


def json_to_markdown(article: Dict[str, Any]) -> str:
    """将单篇文章 JSON 转换为 Markdown 格式。

    Args:
        article: 文章字典，包含以下字段：
            - id: 文章唯一标识符
            - title: 文章标题
            - source_url 或 url: 原文链接
            - source_type 或 source: 来源类型
            - collected_at: 采集时间（ISO 8601 格式）
            - summary: 文章摘要
            - tags: 标签列表
            - relevance_score 或 score: 相关性评分（0-1 之间）

    Returns:
        格式化后的 Markdown 字符串。

    Raises:
        KeyError: 当缺少必要字段时。
    """
    title = article.get("title", "未知标题")
    source_url = _get_article_field(article, "source_url", "")
    source_type = _get_article_field(article, "source_type", "未知来源")
    collected_at = article.get("collected_at", "")
    summary = article.get("summary", "暂无摘要")
    tags = article.get("tags", [])
    score = _get_article_field(article, "relevance_score", 0.0)

    # 截取日期部分（前10位）
    date_str = collected_at[:10] if collected_at else "未知日期"

    # 获取评分 emoji
    score_emoji = _get_score_emoji(score)

    # 构建标签部分
    tags_str = ", ".join(tags) if tags else "无标签"

    # 构建 Markdown
    markdown_lines = [
        f"# {title}",
        "",
        f"**来源**: {source_type}",
        f"**日期**: {date_str}",
        f"**相关性评分**: {score_emoji} {score:.2f}",
        f"**标签**: {tags_str}",
        "",
        "## 摘要",
        "",
        summary,
        "",
        f"[查看原文]({source_url})",
    ]

    return "\n".join(markdown_lines)


def json_to_telegram(article: Dict[str, Any]) -> str:
    """将单篇文章 JSON 转换为 Telegram MarkdownV2 格式。

    Args:
        article: 文章字典，包含以下字段：
            - id: 文章唯一标识符
            - title: 文章标题
            - source_url 或 url: 原文链接
            - source_type 或 source: 来源类型
            - summary: 文章摘要
            - tags: 标签列表
            - relevance_score 或 score: 相关性评分（0-1 之间）

    Returns:
        格式化后的 Telegram MarkdownV2 字符串。

    Raises:
        KeyError: 当缺少必要字段时。
    """
    title = article.get("title", "未知标题")
    source_url = _get_article_field(article, "source_url", "")
    source_type = _get_article_field(article, "source_type", "未知来源")
    summary = article.get("summary", "暂无摘要")
    tags = article.get("tags", [])
    score = _get_article_field(article, "relevance_score", 0.0)

    # 获取评分 emoji
    score_emoji = _get_score_emoji(score)

    # 转义特殊字符
    escaped_title = _escape_telegram_markdown(title)
    escaped_summary = _escape_telegram_markdown(summary)
    escaped_source = _escape_telegram_markdown(source_type)

    # 处理标签：空格替换为下划线，然后转义
    processed_tags = []
    for tag in tags:
        processed_tag = tag.replace(" ", "_")
        processed_tags.append(_escape_telegram_markdown(processed_tag))
    tags_str = ", ".join(processed_tags) if processed_tags else "无标签"

    # 构建 Telegram MarkdownV2
    telegram_lines = [
        f"*{escaped_title}*",
        "",
        f"📊 相关性: {score_emoji} {score:.2f}",
        f"📡 来源: {escaped_source}",
        f"🏷️ 标签: {tags_str}",
        "",
        escaped_summary,
        "",
        f"[查看原文]({source_url})",
    ]

    return "\n".join(telegram_lines)


def json_to_feishu(article: Dict[str, Any]) -> Dict[str, Any]:
    """将单篇文章 JSON 转换为飞书 Interactive Card 格式。

    Args:
        article: 文章字典，包含以下字段：
            - id: 文章唯一标识符
            - title: 文章标题
            - source_url 或 url: 原文链接
            - source_type 或 source: 来源类型
            - summary: 文章摘要
            - tags: 标签列表
            - relevance_score 或 score: 相关性评分（0-1 之间）

    Returns:
        飞书 Interactive Card 字典。

    Raises:
        KeyError: 当缺少必要字段时。
    """
    title = article.get("title", "未知标题")
    source_url = _get_article_field(article, "source_url", "")
    source_type = _get_article_field(article, "source_type", "未知来源")
    summary = article.get("summary", "暂无摘要")
    tags = article.get("tags", [])
    score = _get_article_field(article, "relevance_score", 0.0)

    # 获取飞书卡片模板颜色
    template_color = _get_feishu_template_color(score)

    # 构建标签文本
    tags_str = "、".join(tags) if tags else "无标签"

    # 构建飞书 Interactive Card
    feishu_card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": title,
                },
                "template": template_color,
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**来源**: {source_type}",
                    },
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**相关性评分**: {score:.2f}",
                    },
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**标签**: {tags_str}",
                    },
                },
                {
                    "tag": "hr",
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": summary,
                    },
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "查看原文",
                            },
                            "url": source_url,
                            "type": "primary",
                        }
                    ],
                },
            ],
        },
    }

    return feishu_card


def generate_daily_digest(
    knowledge_dir: str = "knowledge/articles",
    date: Optional[str] = None,
    top_n: int = 5,
) -> Dict[str, Any]:
    """生成当日知识简报。

    Args:
        knowledge_dir: 知识库文章目录路径。
        date: 日期字符串（YYYY-MM-DD 格式），默认为今天。
        top_n: 返回的文章数量上限。

    Returns:
        包含以下字段的字典：
            - markdown: Markdown 格式的简报
            - telegram: Telegram MarkdownV2 格式的简报
            - feishu: 飞书 Interactive Card 格式的简报
        当日无文章时返回包含提示信息的字典。
    """
    # 确定日期
    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 扫描目录中的 JSON 文件
    knowledge_path = Path(knowledge_dir)
    if not knowledge_path.exists():
        logger.warning("知识库目录不存在: %s", knowledge_dir)
        return _generate_empty_digest(date)

    # 使用 glob 模式匹配文件
    pattern = f"{date}-*.json"
    json_files = list(knowledge_path.glob(pattern))

    if not json_files:
        logger.info("当日无新增知识条目: %s", date)
        return _generate_empty_digest(date)

    # 读取并解析 JSON 文件
    articles: List[Dict[str, Any]] = []
    for json_file in json_files:
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                article = json.load(f)
                articles.append(article)
        except (json.JSONDecodeError, IOError) as e:
            logger.error("读取文件失败 %s: %s", json_file, e)

    # 按相关性评分降序排序
    score_field = "relevance_score"
    articles.sort(
        key=lambda x: _get_article_field(x, score_field, 0.0),
        reverse=True,
    )

    # 取 Top N
    top_articles = articles[:top_n]

    # 生成各格式的简报
    markdown_digest = _generate_markdown_digest(top_articles, date)
    telegram_digest = _generate_telegram_digest(top_articles, date)
    feishu_digest = _generate_feishu_digest(top_articles, date)

    return {
        "markdown": markdown_digest,
        "telegram": telegram_digest,
        "feishu": feishu_digest,
    }


def _generate_empty_digest(date: str) -> Dict[str, Any]:
    """生成空简报。

    Args:
        date: 日期字符串。

    Returns:
        包含空简报信息的字典。
    """
    empty_message = f"📭 {date} 暂无新增知识条目"
    return {
        "markdown": empty_message,
        "telegram": empty_message,
        "feishu": {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"每日知识简报 - {date}",
                    },
                    "template": "blue",
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": empty_message,
                        },
                    }
                ],
            },
        },
    }


def _generate_markdown_digest(articles: List[Dict[str, Any]], date: str) -> str:
    """生成 Markdown 格式的简报。

    Args:
        articles: 文章列表。
        date: 日期字符串。

    Returns:
        Markdown 格式的简报字符串。
    """
    if not articles:
        return f"📭 {date} 暂无新增知识条目"

    lines = [
        f"# 每日知识简报 - {date}",
        "",
        f"共收录 {len(articles)} 篇知识条目",
        "",
    ]

    for i, article in enumerate(articles, 1):
        title = article.get("title", "未知标题")
        score = _get_article_field(article, "relevance_score", 0.0)
        score_emoji = _get_score_emoji(score)
        summary = article.get("summary", "暂无摘要")
        source_url = _get_article_field(article, "source_url", "")

        lines.extend([
            f"## {i}. {title}",
            "",
            f"相关性: {score_emoji} {score:.2f}",
            "",
            summary,
            "",
            f"[查看原文]({source_url})",
            "",
            "---",
            "",
        ])

    return "\n".join(lines)


def _generate_telegram_digest(articles: List[Dict[str, Any]], date: str) -> str:
    """生成 Telegram MarkdownV2 格式的简报。

    Args:
        articles: 文章列表。
        date: 日期字符串。

    Returns:
        Telegram MarkdownV2 格式的简报字符串。
    """
    if not articles:
        return f"📭 {date} 暂无新增知识条目"

    lines = [
        f"*📊 每日知识简报 \\- {_escape_telegram_markdown(date)}*",
        "",
        f"共收录 {len(articles)} 篇知识条目",
        "",
    ]

    for i, article in enumerate(articles, 1):
        title = article.get("title", "未知标题")
        score = _get_article_field(article, "relevance_score", 0.0)
        score_emoji = _get_score_emoji(score)
        source_url = _get_article_field(article, "source_url", "")

        escaped_title = _escape_telegram_markdown(title)

        lines.extend([
            f"*{i}\\. {escaped_title}*",
            f"相关性: {score_emoji} {score:.2f}",
            f"[查看原文]({source_url})",
            "",
        ])

    return "\n".join(lines)


def _generate_feishu_digest(articles: List[Dict[str, Any]], date: str) -> Dict[str, Any]:
    """生成飞书 Interactive Card 格式的简报。

    Args:
        articles: 文章列表。
        date: 日期字符串。

    Returns:
        飞书 Interactive Card 字典。
    """
    if not articles:
        return _generate_empty_digest(date)["feishu"]

    elements = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"共收录 {len(articles)} 篇知识条目",
            },
        },
        {
            "tag": "hr",
        },
    ]

    for i, article in enumerate(articles, 1):
        title = article.get("title", "未知标题")
        score = _get_article_field(article, "relevance_score", 0.0)
        score_emoji = _get_score_emoji(score)
        summary = article.get("summary", "暂无摘要")
        source_url = _get_article_field(article, "source_url", "")

        elements.extend([
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**{i}\\. {title}**\n相关性: {score_emoji} {score:.2f}",
                },
            },
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": summary,
                },
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {
                            "tag": "plain_text",
                            "content": "查看原文",
                        },
                        "url": source_url,
                        "type": "primary",
                    }
                ],
            },
            {
                "tag": "hr",
            },
        ])

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"每日知识简报 - {date}",
                },
                "template": "blue",
            },
            "elements": elements,
        },
    }