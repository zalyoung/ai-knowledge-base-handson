"""Router pattern with two-layer intent classification.

Layer 1: Keyword-based fast matching (zero cost, no LLM call).
Layer 2: LLM classification fallback for ambiguous intents.

Supports three intents:
- github_search: Query GitHub Search API.
- knowledge_query: Search local knowledge/articles/.
- general_chat: Direct LLM conversation.
"""

import json
import logging
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple

from pipeline.model_client import chat

logger = logging.getLogger(__name__)

# ============================================================
# Layer 1: Keyword-based fast matching
# ============================================================

_GITHUB_KEYWORDS: List[str] = [
    "github",
    "github trending",
    "github.com",
    "github search",
]

_KNOWLEDGE_KEYWORDS: List[str] = [
    "知识库",
    "本地知识库",
    "本地文章",
    "hacker news",
    "hackernews",
    "技术资讯",
    "技术动态",
    "技术前沿",
    "检索",
    "查询",
]

_KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge" / "articles"

_GITHUB_API_URL = "https://api.github.com/search/repositories"


def _match_intent_by_keywords(query: str) -> Optional[str]:
    """Match intent using keyword rules.

    Args:
        query: User query string.

    Returns:
        Matched intent string, or None if no keyword matches.
    """
    lower = query.lower()

    for kw in _GITHUB_KEYWORDS:
        if kw.lower() in lower:
            return "github_search"

    for kw in _KNOWLEDGE_KEYWORDS:
        if kw.lower() in lower:
            return "knowledge_query"

    return None


# ============================================================
# Layer 2: LLM-based classification
# ============================================================

_CLASSIFICATION_SYSTEM_PROMPT = (
    "你是一个意图分类器，将用户查询归为以下三类之一：\n"
    "1. github_search — 用户想在 GitHub 上搜索开源项目、代码仓库\n"
    "2. knowledge_query — 用户想查询本地 AI 技术知识库的文章、资讯\n"
    "3. general_chat — 一般性对话、问答，无需搜索外部数据\n"
    "\n"
    "只返回 JSON，不要输出其他内容：\n"
    '{"intent": "github_search|knowledge_query|general_chat", "reasoning": "..."}'
)


def _chat_json(prompt: str, system_prompt: str = "") -> dict:
    """Call LLM and return parsed JSON response.

    Args:
        prompt: User prompt.
        system_prompt: System prompt for the LLM.

    Returns:
        Parsed JSON dict.

    Raises:
        json.JSONDecodeError: If response is not valid JSON.
    """
    response = chat(
        prompt=prompt,
        system_prompt=system_prompt,
        temperature=0.0,
        max_tokens=300,
    )
    text = response.content.strip()

    if "```" in text:
        lines = text.split("\n")
        text = "\n".join(
            line for line in lines if not line.strip().startswith("```")
        )

    return json.loads(text)


def _classify_by_llm(query: str) -> str:
    """Classify intent using LLM.

    Args:
        query: User query string.

    Returns:
        Intent string, falls back to general_chat on failure.
    """
    prompt = f"查询: {query}"
    try:
        result = _chat_json(prompt, system_prompt=_CLASSIFICATION_SYSTEM_PROMPT)
        intent = result.get("intent", "general_chat")
        logger.info("LLM 分类: %.50s -> %s", query, intent)
        return intent
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("LLM 分类失败: %s，降级为 general_chat", exc)
        return "general_chat"


# ============================================================
# Intent classification entry point
# ============================================================

def _classify_intent(query: str) -> str:
    """Two-layer intent classification.

    Layer 1: Keyword matching (fast, zero cost).
    Layer 2: LLM classification (fallback).

    Args:
        query: User query string.

    Returns:
        Intent string.
    """
    intent = _match_intent_by_keywords(query)
    if intent:
        logger.info("关键词匹配: %.50s -> %s", query, intent)
        return intent

    logger.info("关键词未匹配，使用 LLM 分类: %.50s", query)
    return _classify_by_llm(query)


# ============================================================
# Handler: github_search
# ============================================================

_GITHUB_TRIGGERS = [
    "github trending", "github 项目", "github search", "github.com",
    "github上", "github", "有什么新", "有什么", "有哪些",
    "有没有", "搜索github",
    "搜索", "搜", "查找", "找", "我想", "帮我",
    "在", "帮", "我", "一个", "一下", "的",
    "什么", "新", "项目",
]


def _extract_search_terms(query: str) -> str:
    """Extract core search terms by stripping trigger words.

    Args:
        query: Raw user query.

    Returns:
        Cleaned search terms.
    """
    terms = query
    for trigger in sorted(_GITHUB_TRIGGERS, key=len, reverse=True):
        terms = terms.replace(trigger, " ")
    terms = " ".join(terms.split())
    result = terms.strip()
    if len(result) < 4:
        result = f"ai {result}".strip()
    return result or "ai agent"


def _handle_github_search(query: str) -> str:
    """Search GitHub repositories via GitHub Search API.

    Args:
        query: User query with search terms.

    Returns:
        Formatted search results string.
    """
    search_query = _extract_search_terms(query)
    encoded = urllib.parse.quote(search_query)
    url = f"{_GITHUB_API_URL}?q={encoded}&sort=stars&order=desc&per_page=5"

    logger.info("GitHub 搜索: %s", url)

    try:
        req = urllib.request.Request(
            url, headers={"Accept": "application/vnd.github.v3+json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.error("GitHub API 请求失败: %s", exc)
        return f"GitHub 搜索失败: {exc}"

    items = data.get("items", [])
    if not items:
        return f'未找到与 "{search_query}" 相关的 GitHub 仓库。'

    total = data.get("total_count", 0)
    lines = [f"GitHub 搜索结果 (共 {total} 个仓库，展示前 5):"]
    for idx, item in enumerate(items, 1):
        name = item.get("full_name", "N/A")
        desc = item.get("description", "无描述")
        stars = item.get("stargazers_count", 0)
        html_url = item.get("html_url", "")
        lang = item.get("language", "")
        lines.append(
            f"\n{idx}. {name}"
            f"\n   Stars: {stars}  |  语言: {lang or 'N/A'}"
            f"\n   {desc or '无描述'}"
            f"\n   {html_url}"
        )

    return "\n".join(lines)


# ============================================================
# Handler: knowledge_query
# ============================================================

def _load_all_articles() -> List[dict]:
    """Load all articles from the local knowledge base.

    Returns:
        List of article dicts.
    """
    index_path = _KNOWLEDGE_DIR / "index.json"
    if not index_path.exists():
        logger.warning("知识库索引不存在: %s", index_path)
        return []

    with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)

    article_ids = list(set(index.values()))
    articles: List[dict] = []

    for aid in article_ids:
        article_path = _KNOWLEDGE_DIR / f"{aid}.json"
        if article_path.exists():
            with open(article_path, "r", encoding="utf-8") as f:
                articles.append(json.load(f))

    return articles


def _score_article(article: dict, query: str) -> int:
    """Score an article against the query.

    Args:
        article: Article dict with title, summary, tags.
        query: Search query string.

    Returns:
        Relevance score (higher = more relevant).
    """
    title = article.get("title", "").lower()
    summary = article.get("summary", "").lower()
    tags = " ".join(article.get("tags", [])).lower()
    query_lower = query.lower()

    score = 0

    if query_lower in title:
        score += 10
    if query_lower in summary:
        score += 5
    for tag in article.get("tags", []):
        if query_lower in tag.lower():
            score += 8

    if score == 0:
        words = query_lower.split()
        combined = f"{title} {summary} {tags}"
        if len(words) == 1:
            score = sum(1 for ch in query_lower if ch in combined)
        else:
            score = sum(1 for w in words if w in combined)

    return score


def _search_articles(articles: List[dict], query: str) -> List[dict]:
    """Search articles by relevance to query.

    Args:
        articles: List of article dicts.
        query: Search query string.

    Returns:
        Scored and sorted list of matching articles (top 5).
    """
    scored = []
    for article in articles:
        score = _score_article(article, query)
        if score > 0:
            scored.append((score, article))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [article for _, article in scored[:5]]


def _format_article(article: dict) -> str:
    """Format a single article for display.

    Args:
        article: Article dict.

    Returns:
        Formatted article string.
    """
    title = article.get("title", "无标题")
    summary = article.get("summary", "")
    source_type = article.get("source_type", "unknown")
    tags = ", ".join(article.get("tags", []))
    source_url = article.get("source_url", "")
    published = article.get("published_at", "")[:10]

    return (
        f"\n  {title}\n"
        f"  来源: {source_type}  |  标签: {tags}  |  日期: {published}\n"
        f"  {summary[:200]}{'...' if len(summary) > 200 else ''}\n"
        f"  {source_url}"
    )


_KNOWLEDGE_STOP_PHRASES = [
    "知识库里有没有关于", "知识库里有没有", "知识库有没有",
    "有没有关于", "有没有", "的文章", "相关的文章",
    "最近有什么", "最近有什么新", "最近有",
    "检索一下", "检索", "查询", "查找",
    "帮我", "帮我找", "帮我搜索", "帮我查",
    "关于", "一下", "一个", "的",
]


def _clean_knowledge_query(query: str) -> str:
    """Strip natural language noise to extract search terms.

    Args:
        query: Raw user query (e.g. "知识库里有没有关于agent的文章").

    Returns:
        Cleaned search terms (e.g. "agent").
    """
    terms = query
    for phrase in sorted(_KNOWLEDGE_STOP_PHRASES, key=len, reverse=True):
        terms = terms.replace(phrase, " ")
    terms = " ".join(terms.split())
    return terms.strip() or query


def _handle_knowledge_query(query: str) -> str:
    """Search local knowledge base for matching articles.

    Args:
        query: User query string.

    Returns:
        Formatted search results.
    """
    articles = _load_all_articles()
    if not articles:
        return "知识库为空，暂无可用文章。"

    search_query = _clean_knowledge_query(query)
    results = _search_articles(articles, search_query)
    if not results:
        articles.sort(
            key=lambda a: a.get("published_at", ""), reverse=True
        )
        results = articles[:5]
        lines = [
            f'未找到与 "{search_query}" 直接匹配的文章，以下是最新的知识条目:'
        ]
    else:
        lines = [f"知识库检索结果 (共 {len(results)} 条):"]

    for article in results:
        lines.append(_format_article(article))

    return "\n".join(lines)


# ============================================================
# Handler: general_chat
# ============================================================

_GENERAL_CHAT_SYSTEM = "你是一个有帮助的AI助手，请简洁、准确地回答用户的问题。"


def _handle_general_chat(query: str) -> str:
    """Handle general conversation by calling LLM directly.

    Args:
        query: User query string.

    Returns:
        LLM response text.
    """
    response = chat(
        prompt=query,
        system_prompt=_GENERAL_CHAT_SYSTEM,
        temperature=0.7,
    )
    return response.content


# ============================================================
# Router entry point
# ============================================================

_HANDLERS = {
    "github_search": _handle_github_search,
    "knowledge_query": _handle_knowledge_query,
    "general_chat": _handle_general_chat,
}


def route(query: str) -> str:
    """Route user query to the appropriate handler.

    Two-layer intent classification:
    1. Keyword matching — fast, zero-cost, no LLM call.
    2. LLM classification — fallback for queries without clear keywords.

    Args:
        query: User query string.

    Returns:
        Handler response string.
    """
    intent = _classify_intent(query)
    handler = _HANDLERS.get(intent, _handle_general_chat)
    return handler(query)


# ============================================================
# Test entry
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    if len(sys.argv) > 1:
        query = sys.argv[1]
        print(f"查询: {query}")
        print(f"结果:\n{route(query)}")
    else:
        test_queries = [
            ("在github上搜索langgraph项目", "github_search"),
            ("github trending有什么新项目", "github_search"),
            ("知识库里有没有关于agent的文章", "knowledge_query"),
            ("最近有什么AI技术资讯", "knowledge_query"),
            ("你好，介绍一下你自己", "general_chat"),
            ("什么是大语言模型", "general_chat"),
        ]

        print("=" * 60)
        print("Router 路由模式测试")
        print("=" * 60)

        for query, expected in test_queries:
            print(f"\n{'─' * 60}")
            print(f"查询: {query}")
            print(f"期望意图: {expected}")
            print(f"{'─' * 60}")

            result = route(query)
            print(f"结果:\n{result[:600]}")

        print(f"\n{'=' * 60}")
        print("测试完成")
        print("=" * 60)
