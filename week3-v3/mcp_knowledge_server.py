"""MCP Knowledge Server - 让 AI 工具搜索本地知识库。

基于 JSON-RPC 2.0 over stdio 协议，实现 MCP (Model Context Protocol) 服务端。
提供文章搜索、详情查询、统计分析三个工具。
"""

import json
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ARTICLES_DIR = Path(__file__).parent / "knowledge" / "articles"


def load_articles() -> list[dict[str, Any]]:
    """加载 knowledge/articles/ 目录下所有 JSON 文件（排除 index.json）。

    Returns:
        文章列表，每个元素为一个文章字典。

    Raises:
        FileNotFoundError: 如果 articles 目录不存在。
    """
    articles: list[dict[str, Any]] = []
    if not ARTICLES_DIR.exists():
        logger.warning("文章目录不存在: %s", ARTICLES_DIR)
        return articles

    for file_path in ARTICLES_DIR.glob("*.json"):
        if file_path.name == "index.json":
            continue
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                articles.append(data)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("跳过文件 %s: %s", file_path.name, exc)

    return articles


def search_articles(keyword: str, limit: int = 5) -> list[dict[str, Any]]:
    """按关键词搜索文章标题和摘要。

    Args:
        keyword: 搜索关键词，不区分大小写。
        limit: 返回结果数量上限，默认 5。

    Returns:
        匹配的文章摘要列表（含 id、title、summary、score、tags）。
    """
    keyword_lower = keyword.lower()
    articles = load_articles()

    matched: list[dict[str, Any]] = []
    for article in articles:
        title = article.get("title", "").lower()
        summary = article.get("summary", "").lower()
        tags = [t.lower() for t in article.get("tags", [])]

        if keyword_lower in title or keyword_lower in summary or keyword_lower in tags:
            matched.append({
                "id": article.get("id", ""),
                "title": article.get("title", ""),
                "summary": article.get("summary", ""),
                "score": article.get("score", 0),
                "tags": article.get("tags", []),
            })

    matched.sort(key=lambda x: x.get("score", 0), reverse=True)
    return matched[:limit]


def get_article(article_id: str) -> Optional[dict[str, Any]]:
    """按 ID 获取文章完整内容。

    Args:
        article_id: 文章唯一标识符。

    Returns:
        文章完整字典，未找到时返回 None。
    """
    articles = load_articles()
    for article in articles:
        if article.get("id") == article_id:
            return article
    return None


def knowledge_stats() -> dict[str, Any]:
    """返回知识库统计信息。

    Returns:
        包含文章总数、来源分布、热门标签的统计字典。
    """
    articles = load_articles()
    total = len(articles)

    source_counter: Counter[str] = Counter()
    tag_counter: Counter[str] = Counter()
    score_sum = 0

    for article in articles:
        source = article.get("source_type", "unknown")
        source_counter[source] += 1
        score_sum += article.get("score", 0)

        for tag in article.get("tags", []):
            tag_counter[tag] += 1

    top_tags = [{"tag": tag, "count": count} for tag, count in tag_counter.most_common(10)]

    return {
        "total_articles": total,
        "source_distribution": dict(source_counter),
        "average_score": round(score_sum / total, 2) if total > 0 else 0,
        "top_tags": top_tags,
    }


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "search_articles",
        "description": "按关键词搜索知识库文章（标题、摘要、标签），返回匹配结果列表。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "搜索关键词",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回结果数量上限，默认 5",
                    "default": 5,
                },
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "get_article",
        "description": "按文章 ID 获取完整内容。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "article_id": {
                    "type": "string",
                    "description": "文章唯一标识符，如 github-20260505-001",
                },
            },
            "required": ["article_id"],
        },
    },
    {
        "name": "knowledge_stats",
        "description": "获取知识库统计信息：文章总数、来源分布、平均评分、热门标签。",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]


def handle_initialize(request_id: Any) -> dict[str, Any]:
    """处理 MCP initialize 请求。

    Args:
        request_id: JSON-RPC 请求 ID。

    Returns:
        initialize 响应，包含服务器能力和协议版本。
    """
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
            },
            "serverInfo": {
                "name": "knowledge-server",
                "version": "1.0.0",
            },
        },
    }


def handle_tools_list(request_id: Any) -> dict[str, Any]:
    """处理 tools/list 请求。

    Args:
        request_id: JSON-RPC 请求 ID。

    Returns:
        包含所有可用工具定义的响应。
    """
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "tools": TOOL_DEFINITIONS,
        },
    }


def handle_tools_call(request_id: Any, params: dict[str, Any]) -> dict[str, Any]:
    """处理 tools/call 请求。

    Args:
        request_id: JSON-RPC 请求 ID。
        params: 包含 toolName 和 arguments 的参数字典。

    Returns:
        工具执行结果或错误响应。
    """
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    try:
        if tool_name == "search_articles":
            keyword = arguments.get("keyword", "")
            limit = arguments.get("limit", 5)
            results = search_articles(keyword, limit)
            content = json.dumps(results, ensure_ascii=False, indent=2)

        elif tool_name == "get_article":
            article_id = arguments.get("article_id", "")
            article = get_article(article_id)
            if article is None:
                content = json.dumps({"error": f"未找到文章: {article_id}"}, ensure_ascii=False)
            else:
                content = json.dumps(article, ensure_ascii=False, indent=2)

        elif tool_name == "knowledge_stats":
            stats = knowledge_stats()
            content = json.dumps(stats, ensure_ascii=False, indent=2)

        else:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": f"未知工具: {tool_name}",
                },
            }

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": content,
                    }
                ],
            },
        }

    except Exception as exc:
        logger.error("工具执行失败 %s: %s", tool_name, exc)
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({"error": str(exc)}, ensure_ascii=False),
                    }
                ],
                "isError": True,
            },
        }


def handle_request(request: dict[str, Any]) -> Optional[dict[str, Any]]:
    """分发 JSON-RPC 请求到对应处理器。

    Args:
        request: 解析后的 JSON-RPC 请求字典。

    Returns:
        JSON-RPC 响应字典，通知类请求返回 None。
    """
    method = request.get("method", "")
    request_id = request.get("id")
    params = request.get("params", {})

    logger.info("收到请求: method=%s, id=%s", method, request_id)

    if method == "initialize":
        return handle_initialize(request_id)

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return handle_tools_list(request_id)

    if method == "tools/call":
        return handle_tools_call(request_id, params)

    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": -32601,
            "message": f"未知方法: {method}",
        },
    }


def send_response(response: dict[str, Any]) -> None:
    """将响应写入 stdout。

    Args:
        response: JSON-RPC 响应字典。
    """
    message = json.dumps(response, ensure_ascii=False)
    sys.stdout.write(message + "\n")
    sys.stdout.flush()
    logger.debug("已发送响应: %s", message[:200])


def main() -> None:
    """MCP Server 主循环：从 stdin 读取 JSON-RPC 请求，处理后写入 stdout。"""
    logger.info("MCP Knowledge Server 启动，文章目录: %s", ARTICLES_DIR)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            error_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "JSON 解析错误"},
            }
            send_response(error_resp)
            continue

        response = handle_request(request)
        if response is not None:
            send_response(response)


if __name__ == "__main__":
    main()
