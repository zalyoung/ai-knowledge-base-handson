"""AI 知识库自动化流水线。

四步流水线：采集 → 分析 → 整理 → 保存。
支持 GitHub Search API 和 RSS 源采集 AI 相关内容。

Example:
    >>> python pipeline/pipeline.py --sources github,rss --limit 20
    >>> python pipeline/pipeline.py --sources github --limit 5 --dry-run
"""

import argparse
import json
import logging
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

# 支持直接运行和模块导入两种方式
try:
    from pipeline.model_client import chat_with_retry, get_provider, tracker
except ImportError:
    from model_client import chat_with_retry, get_provider, tracker

logger = logging.getLogger(__name__)

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
RAW_DIR = PROJECT_ROOT / "knowledge" / "raw"
ARTICLES_DIR = PROJECT_ROOT / "knowledge" / "articles"
INDEX_FILE = ARTICLES_DIR / "index.json"

# GitHub Search API 配置
GITHUB_API_BASE = "https://api.github.com"
GITHUB_SEARCH_QUERIES = [
    "language:python stars:>100 pushed:>2025-01-01 AI agent",
    "language:python stars:>100 pushed:>2025-01-01 LLM framework",
    "language:typescript stars:>100 pushed:>2025-01-01 AI assistant",
]

# RSS 源配置
RSS_FEEDS = [
    "https://hnrss.org/newest?q=AI+agent",
    "https://hnrss.org/newest?q=LLM",
    "https://hnrss.org/newest?q=large+language+model",
]

# HTTP 请求配置
REQUEST_TIMEOUT = 30.0
REQUEST_HEADERS = {
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "AI-Knowledge-Base/1.0",
}


def setup_logging(verbose: bool = False) -> None:
    """配置日志系统。

    Args:
        verbose: 是否启用详细日志模式。
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def ensure_directories() -> None:
    """确保必要的目录存在。"""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    logger.debug("目录已就绪: %s, %s", RAW_DIR, ARTICLES_DIR)


# =============================================================================
# Step 1: 采集（Collect）
# =============================================================================


def collect_from_github(limit: int) -> List[Dict[str, Any]]:
    """从 GitHub Search API 采集 AI 相关项目。

    Args:
        limit: 最大采集数量。

    Returns:
        原始采集数据列表。

    Raises:
        httpx.HTTPStatusError: API 请求失败。
        httpx.TimeoutException: 请求超时。
    """
    items: List[Dict[str, Any]] = []
    seen_ids: set = set()

    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        for query in GITHUB_SEARCH_QUERIES:
            if len(items) >= limit:
                break

            logger.info("GitHub 搜索: %s", query)
            response = client.get(
                f"{GITHUB_API_BASE}/search/repositories",
                params={"q": query, "sort": "stars", "per_page": min(limit, 30)},
                headers=REQUEST_HEADERS,
            )
            response.raise_for_status()
            data = response.json()

            for repo in data.get("items", []):
                if len(items) >= limit:
                    break

                repo_id = repo["id"]
                if repo_id in seen_ids:
                    continue
                seen_ids.add(repo_id)

                items.append({
                    "source_type": "github_trending",
                    "source_id": str(repo_id),
                    "title": repo["full_name"],
                    "description": repo.get("description", ""),
                    "url": repo["html_url"],
                    "stars": repo.get("stargazers_count", 0),
                    "language": repo.get("language", ""),
                    "topics": repo.get("topics", []),
                    "created_at": repo.get("created_at"),
                    "updated_at": repo.get("updated_at"),
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                })

    logger.info("GitHub 采集完成，共 %d 条", len(items))
    return items


def collect_from_rss(limit: int) -> List[Dict[str, Any]]:
    """从 RSS 源采集 AI 相关内容。

    使用简易正则解析 RSS XML，避免额外依赖。

    Args:
        limit: 最大采集数量。

    Returns:
        原始采集数据列表。

    Raises:
        httpx.HTTPStatusError: RSS 请求失败。
        httpx.TimeoutException: 请求超时。
    """
    items: List[Dict[str, Any]] = []
    seen_links: set = set()

    with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
        for feed_url in RSS_FEEDS:
            if len(items) >= limit:
                break

            logger.info("RSS 采集: %s", feed_url)
            try:
                response = client.get(feed_url)
                response.raise_for_status()
                xml_content = response.text
            except (httpx.HTTPStatusError, httpx.TimeoutException) as exc:
                logger.warning("RSS 请求失败: %s - %s", feed_url, exc)
                continue

            # 简易正则解析 RSS
            entries = re.findall(r"<item>(.*?)</item>", xml_content, re.DOTALL)

            for entry in entries:
                if len(items) >= limit:
                    break

                title_match = re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>", entry)
                link_match = re.search(r"<link>(.*?)</link>", entry)
                desc_match = re.search(
                    r"<description><!\[CDATA\[(.*?)\]\]></description>", entry, re.DOTALL
                )
                pub_match = re.search(r"<pubDate>(.*?)</pubDate>", entry)

                if not title_match or not link_match:
                    continue

                link = link_match.group(1).strip()
                if link in seen_links:
                    continue
                seen_links.add(link)

                items.append({
                    "source_type": "hackernews",
                    "source_id": str(uuid.uuid4()),
                    "title": title_match.group(1).strip(),
                    "description": desc_match.group(1).strip() if desc_match else "",
                    "url": link,
                    "published_at": pub_match.group(1).strip() if pub_match else None,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                })

    logger.info("RSS 采集完成，共 %d 条", len(items))
    return items


def collect(sources: List[str], limit: int) -> List[Dict[str, Any]]:
    """执行采集步骤。

    Args:
        sources: 数据源列表，可选 "github" 和 "rss"。
        limit: 每个源的最大采集数量。

    Returns:
        合并后的原始采集数据列表。
    """
    items: List[Dict[str, Any]] = []

    if "github" in sources:
        try:
            items.extend(collect_from_github(limit))
        except (httpx.HTTPStatusError, httpx.TimeoutException) as exc:
            logger.error("GitHub 采集失败: %s", exc)

    if "rss" in sources:
        try:
            items.extend(collect_from_rss(limit))
        except (httpx.HTTPStatusError, httpx.TimeoutException) as exc:
            logger.error("RSS 采集失败: %s", exc)

    logger.info("采集步骤完成，共 %d 条原始数据", len(items))
    return items


def save_raw_data(items: List[Dict[str, Any]], sources: List[str]) -> Path:
    """保存原始采集数据到 knowledge/raw/。

    Args:
        items: 原始采集数据列表。
        sources: 数据源列表，用于生成文件名。

    Returns:
        保存的文件路径。
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sources_str = "_".join(sources)
    filename = f"raw_{sources_str}_{timestamp}.json"
    filepath = RAW_DIR / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    logger.info("原始数据已保存: %s (%d 条)", filepath, len(items))
    return filepath


# =============================================================================
# Step 2: 分析（Analyze）
# =============================================================================


ANALYSIS_SYSTEM_PROMPT = """你是一个技术内容分析专家。请分析以下技术内容，返回 JSON 格式的分析结果。

要求：
1. 生成中文标题（准确概括内容）
2. 生成 100-300 字的中文摘要（突出技术亮点和适用场景）
3. 评分 1-10（10 最高，基于技术创新性、实用性、社区活跃度）
4. 生成 3-8 个标签（小写英文）

返回格式（严格 JSON）：
{
  "title": "中文标题",
  "summary": "中文摘要",
  "score": 8,
  "tags": ["tag1", "tag2", "tag3"]
}"""


def analyze_item(
    item: Dict[str, Any],
    provider: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    """分析单条内容。

    Args:
        item: 原始采集数据。
        provider: LLM 提供商实例，若不提供则使用默认。

    Returns:
        分析结果字典，失败时返回 None。
    """
    prompt = f"""请分析以下技术内容：

标题: {item.get('title', 'N/A')}
描述: {item.get('description', 'N/A')}
URL: {item.get('url', 'N/A')}
来源: {item.get('source_type', 'N/A')}
星标数: {item.get('stars', 'N/A')}
编程语言: {item.get('language', 'N/A')}
标签: {', '.join(item.get('topics', []))}"""

    try:
        response = chat_with_retry(
            prompt=prompt,
            system_prompt=ANALYSIS_SYSTEM_PROMPT,
            provider=provider,
            temperature=0.3,
            max_tokens=2000,
        )

        # 解析 JSON 响应
        content = response.content.strip()
        # 提取 JSON 部分（处理可能的 markdown 代码块）
        json_match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
        if json_match:
            content = json_match.group(1)

        result = json.loads(content)

        # 验证必需字段
        required_fields = ["title", "summary", "score", "tags"]
        if not all(field in result for field in required_fields):
            logger.warning("分析结果缺少必需字段: %s", item.get("title"))
            return None

        return result

    except json.JSONDecodeError as exc:
        logger.warning("JSON 解析失败: %s - %s", item.get("title"), exc)
        logger.debug("原始响应内容: %s", content[:500])
        return None
    except Exception as exc:
        logger.warning("分析失败: %s - %s", item.get("title"), exc)
        return None


def analyze(
    items: List[Dict[str, Any]],
    provider: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """执行分析步骤。

    Args:
        items: 原始采集数据列表。
        provider: LLM 提供商实例，若不提供则使用默认。

    Returns:
        含分析结果的数据列表。
    """
    analyzed_items: List[Dict[str, Any]] = []
    total = len(items)

    for idx, item in enumerate(items, 1):
        logger.info("分析进度: %d/%d - %s", idx, total, item.get("title", "N/A"))

        analysis = analyze_item(item, provider=provider)
        if analysis:
            merged = {**item, **analysis}
            merged["analyzed_at"] = datetime.now(timezone.utc).isoformat()
            analyzed_items.append(merged)
        else:
            logger.warning("跳过分析失败的条目: %s", item.get("title"))

    logger.info("分析步骤完成，成功 %d/%d 条", len(analyzed_items), total)
    return analyzed_items


# =============================================================================
# Step 3: 整理（Organize）
# =============================================================================


def load_index() -> Dict[str, str]:
    """加载去重索引。

    Returns:
        URL 到文章 ID 的映射字典。
    """
    if INDEX_FILE.exists():
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_index(index: Dict[str, str]) -> None:
    """保存去重索引。

    Args:
        index: URL 到文章 ID 的映射字典。
    """
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def deduplicate(
    items: List[Dict[str, Any]], index: Dict[str, str]
) -> List[Dict[str, Any]]:
    """去重处理。

    Args:
        items: 待去重的数据列表。
        index: 现有的去重索引。

    Returns:
        去重后的数据列表。
    """
    unique_items: List[Dict[str, Any]] = []
    seen_urls: set = set(index.keys())

    for item in items:
        url = item.get("url", "")
        if url and url not in seen_urls:
            unique_items.append(item)
            seen_urls.add(url)

    removed_count = len(items) - len(unique_items)
    if removed_count > 0:
        logger.info("去重: 移除 %d 条重复内容", removed_count)

    return unique_items


def validate_article(article: Dict[str, Any]) -> bool:
    """校验文章格式。

    Args:
        article: 文章数据。

    Returns:
        校验是否通过。
    """
    required_fields = ["id", "title", "source_url", "source_type", "summary", "tags"]
    for field in required_fields:
        if field not in article:
            logger.warning("校验失败: 缺少字段 '%s'", field)
            return False

    # 校验 ID 格式（{source}-{YYYYMMDD}-{NNN}）
    id_pattern = re.compile(r"^[a-z]+-\d{8}-\d{3}$")
    if not id_pattern.match(article.get("id", "")):
        logger.warning("校验失败: 无效的 ID 格式 '%s'", article.get("id"))
        return False

    # 校验 tags 类型
    if not isinstance(article["tags"], list):
        logger.warning("校验失败: tags 应为列表")
        return False

    # 校验 score 范围
    score = article.get("score", 0)
    if not (1 <= score <= 10):
        logger.warning("校验失败: score 应在 1-10 之间，当前值 %s", score)
        return False

    return True


# 文章 ID 计数器（用于生成 {source}-{YYYYMMDD}-{NNN} 格式）
_id_counters: Dict[str, int] = {}


def _generate_article_id(source_type: str) -> str:
    """生成文章 ID，格式：{source}-{YYYYMMDD}-{NNN}。

    Args:
        source_type: 来源类型（github_trending / hackernews）。

    Returns:
        格式化的文章 ID。
    """
    date_str = datetime.now().strftime("%Y%m%d")
    # 简化来源类型：github_trending -> github, hackernews -> hn
    source_map = {"github_trending": "github", "hackernews": "hn"}
    source = source_map.get(source_type, "unknown")

    key = f"{source}-{date_str}"
    _id_counters[key] = _id_counters.get(key, 0) + 1
    seq = _id_counters[key]

    return f"{source}-{date_str}-{seq:03d}"


def standardize_article(item: Dict[str, Any]) -> Dict[str, Any]:
    """标准化文章格式。

    Args:
        item: 含分析结果的数据。

    Returns:
        标准化的文章数据。
    """
    now = datetime.now(timezone.utc).isoformat()
    source_type = item.get("source_type", "unknown")

    return {
        "id": _generate_article_id(source_type),
        "title": item.get("title", ""),
        "source_url": item.get("url", ""),
        "source_type": source_type,
        "summary": item.get("summary", ""),
        "tags": item.get("tags", []),
        "score": item.get("score", 5),
        "published_at": item.get("published_at") or item.get("created_at") or now,
        "fetched_at": item.get("fetched_at", now),
        "analyzed_at": item.get("analyzed_at", now),
        "status": "published",
    }


def organize(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """执行整理步骤：去重 + 格式标准化 + 校验。

    Args:
        items: 待整理的数据列表。

    Returns:
        整理后的文章列表。
    """
    # 加载去重索引
    index = load_index()

    # 去重
    unique_items = deduplicate(items, index)

    # 格式标准化 + 校验
    valid_articles: List[Dict[str, Any]] = []
    for item in unique_items:
        article = standardize_article(item)
        if validate_article(article):
            valid_articles.append(article)
        else:
            logger.warning("跳过校验失败的文章: %s", item.get("title"))

    logger.info("整理步骤完成，有效文章 %d/%d 条", len(valid_articles), len(unique_items))
    return valid_articles


# =============================================================================
# Step 4: 保存（Save）
# =============================================================================


def save_articles(articles: List[Dict[str, Any]]) -> List[Path]:
    """保存文章为独立 JSON 文件。

    Args:
        articles: 文章列表。

    Returns:
        保存的文件路径列表。
    """
    index = load_index()
    saved_files: List[Path] = []

    for article in articles:
        article_id = article["id"]
        filename = f"{article_id}.json"
        filepath = ARTICLES_DIR / filename

        # 保存文章
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(article, f, ensure_ascii=False, indent=2)

        # 更新索引
        index[article["source_url"]] = article_id
        saved_files.append(filepath)

    # 保存索引
    save_index(index)

    logger.info("保存步骤完成，共 %d 篇文章", len(saved_files))
    return saved_files


# =============================================================================
# Pipeline 主流程
# =============================================================================


def run_pipeline(
    sources: List[str],
    limit: int = 20,
    dry_run: bool = False,
    provider_name: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """执行完整流水线。

    Args:
        sources: 数据源列表。
        limit: 每个源的最大采集数量。
        dry_run: 是否为干跑模式。
        provider_name: LLM 提供商名称，默认从环境变量读取。
        model: 模型名称，默认使用提供商默认模型。

    Returns:
        流水线执行结果统计。
    """
    result = {
        "sources": sources,
        "limit": limit,
        "dry_run": dry_run,
        "collected": 0,
        "analyzed": 0,
        "organized": 0,
        "saved": 0,
        "status": "success",
    }

    # 初始化 LLM 提供商
    provider = get_provider(
        provider_name=provider_name,
        model=model,
    )

    logger.info("=" * 60)
    logger.info("流水线启动")
    logger.info("数据源: %s", sources)
    logger.info("采集限制: %d", limit)
    logger.info("模式: %s", "干跑" if dry_run else "正常")
    logger.info("LLM: %s / %s", provider.provider_name, provider.model)
    logger.info("=" * 60)

    try:
        # Step 1: 采集
        logger.info("\n[Step 1/4] 采集（Collect）")
        raw_items = collect(sources, limit)
        result["collected"] = len(raw_items)

        if not raw_items:
            logger.warning("未采集到任何数据，流水线终止")
            result["status"] = "empty"
            return result

        # 保存原始数据
        save_raw_data(raw_items, sources)

        if dry_run:
            logger.info("\n[干跑模式] 跳过分析/整理/保存步骤")
            logger.info("采集到 %d 条原始数据", len(raw_items))
            for item in raw_items[:5]:
                logger.info("  - %s", item.get("title", "N/A"))
            if len(raw_items) > 5:
                logger.info("  ... 还有 %d 条", len(raw_items) - 5)
            return result

        # Step 2: 分析
        logger.info("\n[Step 2/4] 分析（Analyze）")
        analyzed_items = analyze(raw_items, provider=provider)
        result["analyzed"] = len(analyzed_items)

        if not analyzed_items:
            logger.warning("分析结果为空，流水线终止")
            result["status"] = "analysis_failed"
            return result

        # Step 3: 整理
        logger.info("\n[Step 3/4] 整理（Organize）")
        valid_articles = organize(analyzed_items)
        result["organized"] = len(valid_articles)

        if not valid_articles:
            logger.warning("整理后无有效文章，流水线终止")
            result["status"] = "organize_failed"
            return result

        # Step 4: 保存
        logger.info("\n[Step 4/4] 保存（Save）")
        saved_files = save_articles(valid_articles)
        result["saved"] = len(saved_files)

        # 输出统计
        logger.info("\n" + "=" * 60)
        logger.info("流水线完成")
        logger.info("采集: %d 条", result["collected"])
        logger.info("分析: %d 条", result["analyzed"])
        logger.info("整理: %d 条", result["organized"])
        logger.info("保存: %d 篇", result["saved"])
        logger.info("=" * 60)

        return result

    finally:
        # 输出 LLM 调用成本报告（无论成功或失败）
        tracker.report()


# =============================================================================
# CLI 入口
# =============================================================================


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """解析命令行参数。

    Args:
        argv: 命令行参数列表，默认使用 sys.argv。

    Returns:
        解析后的参数对象。
    """
    parser = argparse.ArgumentParser(
        description="AI 知识库自动化流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python pipeline/pipeline.py --sources github,rss --limit 20
  python pipeline/pipeline.py --sources github --limit 5 --dry-run
  python pipeline/pipeline.py --limit 5 --provider deepseek
  python pipeline/pipeline.py --limit 5 --provider xiaomi --model mimo-v2.5-pro
        """,
    )

    parser.add_argument(
        "--sources",
        type=str,
        default="github,rss",
        help="数据源，逗号分隔 (默认: github,rss)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="每个源的最大采集数量 (默认: 20)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="干跑模式，只采集不分析",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="详细日志模式",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default=None,
        help="LLM 提供商 (默认: 从环境变量 LLM_PROVIDER 读取)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="模型名称 (默认: 使用提供商默认模型)",
    )

    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """主入口函数。

    Args:
        argv: 命令行参数列表。

    Returns:
        退出码，0 表示成功。
    """
    args = parse_args(argv)
    setup_logging(args.verbose)
    ensure_directories()

    # 解析数据源
    sources = [s.strip().lower() for s in args.sources.split(",")]
    valid_sources = {"github", "rss"}
    invalid_sources = set(sources) - valid_sources
    if invalid_sources:
        logger.error("无效的数据源: %s，可选: %s", invalid_sources, valid_sources)
        return 1

    try:
        result = run_pipeline(
            sources=sources,
            limit=args.limit,
            dry_run=args.dry_run,
            provider_name=args.provider,
            model=args.model,
        )

        if result["status"] != "success":
            logger.warning("流水线状态: %s", result["status"])
            return 1

        return 0

    except KeyboardInterrupt:
        logger.info("\n用户中断，流水线终止")
        return 130
    except Exception as exc:
        logger.exception("流水线异常: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
