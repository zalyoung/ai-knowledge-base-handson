"""LangGraph 工作流节点函数定义。

每个节点是纯函数：接收 KBState，返回 dict（部分状态更新）。
节点列表：
    - collect_node: 调用 GitHub Search API 采集 AI 相关仓库
    - analyze_node: 用 LLM 对每条数据生成中文摘要、标签、评分
    - organize_node: 过滤低分条目、按 URL 去重、如有审核反馈则用 LLM 修正
    - review_node: LLM 四维度评分，iteration >= 2 强制通过
    - save_node: 将 articles 写入 knowledge/articles/ 目录的 JSON 文件

Example:
    >>> from workflows.nodes import collect_node, analyze_node
    >>> state = create_initial_state()
    >>> state.update(collect_node(state))
    >>> state.update(analyze_node(state))
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

try:
    from workflows.model_client import accumulate_usage, chat_json
    from workflows.state import (
        AnalysisResult,
        Article,
        CostTracker,
        KBState,
        SourceItem,
    )
except ImportError:
    from model_client import accumulate_usage, chat_json  # type: ignore[no-redef]
    from state import (  # type: ignore[no-redef]
        AnalysisResult,
        Article,
        CostTracker,
        KBState,
        SourceItem,
    )

logger = logging.getLogger(__name__)

# GitHub Search API 配置
GITHUB_API_BASE = "https://api.github.com"
GITHUB_SEARCH_QUERIES = [
    "language:python stars:>100 pushed:>2025-01-01 AI agent",
    "language:python stars:>100 pushed:>2025-01-01 LLM framework",
    "language:typescript stars:>100 pushed:>2025-01-01 AI assistant",
]

# 文章存储路径
PROJECT_ROOT = Path(__file__).parent.parent
ARTICLES_DIR = PROJECT_ROOT / "knowledge" / "articles"
INDEX_FILE = ARTICLES_DIR / "index.json"

# 评分阈值（1-10 分制，低于此值的条目将被过滤）
SCORE_THRESHOLD = 6

# 审核通过阈值（0-1 分制）
REVIEW_PASS_THRESHOLD = 0.7


# =============================================================================
# 辅助函数
# =============================================================================


def _load_index() -> Dict[str, str]:
    """加载去重索引。

    Returns:
        URL 到文章 ID 的映射字典。
    """
    if INDEX_FILE.exists():
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_index(index: Dict[str, str]) -> None:
    """保存去重索引。

    Args:
        index: URL 到文章 ID 的映射字典。
    """
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def _generate_article_id(source_type: str, index: Dict[str, str]) -> str:
    """生成文章 ID，格式：{source}-{YYYYMMDD}-{NNN}。

    Args:
        source_type: 来源类型（github_trending / hackernews）。
        index: 现有索引，用于避免 ID 冲突。

    Returns:
        格式化的文章 ID。
    """
    date_str = datetime.now().strftime("%Y%m%d")
    source_map = {"github_trending": "github", "hackernews": "hn"}
    source = source_map.get(source_type, "unknown")
    prefix = f"{source}-{date_str}"

    max_seq = 0
    for article_id in index.values():
        if article_id.startswith(prefix):
            try:
                seq = int(article_id.split("-")[-1])
                max_seq = max(max_seq, seq)
            except ValueError:
                pass

    return f"{prefix}-{max_seq + 1:03d}"


def _empty_cost_tracker() -> CostTracker:
    """创建空的 CostTracker。

    Returns:
        所有字段归零的 CostTracker 实例。
    """
    return CostTracker(
        total_tokens=0,
        total_cost=0.0,
        input_tokens=0,
        output_tokens=0,
        call_count=0,
    )


# =============================================================================
# 节点 1: 采集
# =============================================================================


def collect_node(state: KBState) -> dict:
    """调用 GitHub Search API 采集 AI 相关仓库。

    使用 urllib.request 发送请求，采集 GitHub 上与 AI/LLM/Agent
    相关的热门项目，返回 SourceItem 列表。

    Args:
        state: 当前工作流状态。

    Returns:
        包含 sources 字段的部分状态更新。
    """
    logger.info("[collect_node] 开始采集 GitHub 仓库")

    sources: List[SourceItem] = []
    seen_ids: set = set()
    now = datetime.now(timezone.utc).isoformat()

    headers: Dict[str, str] = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "AI-Knowledge-Base/1.0",
    }
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"

    for query in GITHUB_SEARCH_QUERIES:
        if len(sources) >= 30:
            break

        url = (
            f"{GITHUB_API_BASE}/search/repositories"
            f"?q={urllib.parse.quote(query)}&sort=stars&per_page=10"
        )
        req = urllib.request.Request(url, headers=headers)

        logger.info("[collect_node] 搜索: %s", query)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            logger.warning("[collect_node] 请求失败: %s", exc)
            continue

        for repo in data.get("items", []):
            repo_id = repo["id"]
            if repo_id in seen_ids:
                continue
            seen_ids.add(repo_id)

            sources.append(
                SourceItem(
                    source_type="github_trending",
                    source_id=str(repo_id),
                    title=repo["full_name"],
                    description=(repo.get("description") or "")[:500],
                    url=repo["html_url"],
                    stars=repo.get("stargazers_count", 0),
                    language=repo.get("language") or "",
                    topics=repo.get("topics") or [],
                    published_at=repo.get("created_at") or now,
                    fetched_at=now,
                )
            )

    logger.info("[collect_node] 采集完成，共 %d 条", len(sources))
    return {"sources": sources}


# =============================================================================
# 节点 2: 分析
# =============================================================================

ANALYSIS_SYSTEM_PROMPT = """\
你是一个技术内容分析专家。请分析以下技术内容，返回 JSON 格式的分析结果。

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


def analyze_node(state: KBState) -> dict:
    """用 LLM 对每条数据生成中文摘要、标签、评分。

    遍历 sources 列表，调用 chat_json 解析 LLM 返回的结构化分析结果，
    生成 AnalysisResult 列表。

    Args:
        state: 当前工作流状态，需包含 sources 字段。

    Returns:
        包含 analyses 和 cost_tracker 字段的部分状态更新。
    """
    sources = state.get("sources", [])
    logger.info("[analyze_node] 开始分析 %d 条数据", len(sources))

    analyses: List[AnalysisResult] = []
    tracker = dict(state.get("cost_tracker") or _empty_cost_tracker())

    for i, source in enumerate(sources, 1):
        title = source.get("title", "N/A")
        logger.info("[analyze_node] 分析进度: %d/%d - %s", i, len(sources), title)

        prompt = f"""请分析以下技术内容：

标题: {source.get('title', 'N/A')}
描述: {source.get('description', 'N/A')}
URL: {source.get('url', 'N/A')}
来源: {source.get('source_type', 'N/A')}
星标数: {source.get('stars', 'N/A')}
编程语言: {source.get('language', 'N/A')}
标签: {', '.join(source.get('topics', []))}"""

        try:
            result, usage = chat_json(
                prompt=prompt,
                system=ANALYSIS_SYSTEM_PROMPT,
                temperature=0.3,
            )
            accumulate_usage(tracker, usage)

            analyses.append(
                AnalysisResult(
                    source_url=source["url"],
                    title=result.get("title", ""),
                    summary=result.get("summary", ""),
                    score=result.get("score", 5),
                    tags=result.get("tags", []),
                    analyzed_at=datetime.now(timezone.utc).isoformat(),
                )
            )
        except Exception as exc:
            logger.warning(
                "[analyze_node] 分析失败: %s - %s", title, exc
            )

    logger.info(
        "[analyze_node] 分析完成，成功 %d/%d 条",
        len(analyses),
        len(sources),
    )
    return {"analyses": analyses, "cost_tracker": tracker}


# =============================================================================
# 节点 3: 整理
# =============================================================================

REVISE_SYSTEM_PROMPT = """\
你是一个技术内容编辑专家。根据审核反馈修正文章的摘要和标签。

返回 JSON 格式：
{
  "title": "修正后的中文标题",
  "summary": "修正后的摘要",
  "tags": ["tag1", "tag2"]
}"""


def organize_node(state: KBState) -> dict:
    """过滤低分条目、按 URL 去重、如有审核反馈则用 LLM 修正。

    处理流程：
    1. 过滤 score < 6 的低分条目
    2. 按 source_url 去重
    3. 若 iteration > 0 且有 review_feedback，调用 LLM 做定向修改
    4. 将 AnalysisResult 转换为 Article 格式

    Args:
        state: 当前工作流状态，需包含 analyses 字段。

    Returns:
        包含 articles 和 cost_tracker 字段的部分状态更新。
    """
    analyses = state.get("analyses", [])
    sources = state.get("sources", [])
    iteration = state.get("iteration", 0)
    feedback = state.get("review_feedback", "")
    logger.info("[organize_node] 开始整理 %d 条分析结果", len(analyses))

    # 构建 source 元数据查找表
    source_meta: Dict[str, SourceItem] = {}
    for s in sources:
        source_meta[s.get("url", "")] = s

    # 过滤低分条目
    filtered = [a for a in analyses if a.get("score", 0) >= SCORE_THRESHOLD]
    logger.info(
        "[organize_node] 过滤低分后剩余 %d 条（阈值=%d）",
        len(filtered),
        SCORE_THRESHOLD,
    )

    # 按 URL 去重
    seen_urls: set = set()
    unique: List[AnalysisResult] = []
    for a in filtered:
        url = a.get("source_url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique.append(a)
    logger.info("[organize_node] 去重后剩余 %d 条", len(unique))

    # 若有审核反馈，调用 LLM 修正
    if iteration > 0 and feedback:
        logger.info("[organize_node] 检测到审核反馈，使用 LLM 定向修正")
        tracker = dict(state.get("cost_tracker") or _empty_cost_tracker())

        revised: List[AnalysisResult] = []
        for a in unique:
            prompt = f"""请根据审核反馈修正以下文章：

标题: {a.get('title', '')}
摘要: {a.get('summary', '')}
标签: {', '.join(a.get('tags', []))}

审核反馈:
{feedback}

请返回修正后的 JSON。"""

            try:
                result, usage = chat_json(
                    prompt=prompt,
                    system=REVISE_SYSTEM_PROMPT,
                    temperature=0.3,
                )
                accumulate_usage(tracker, usage)

                a["title"] = result.get("title", a["title"])
                a["summary"] = result.get("summary", a["summary"])
                a["tags"] = result.get("tags", a["tags"])
            except Exception as exc:
                logger.warning(
                    "[organize_node] 修正失败: %s - %s",
                    a.get("title"),
                    exc,
                )
            revised.append(a)
        unique = revised
    else:
        tracker = state.get("cost_tracker")

    # 转换为 Article 格式
    articles: List[Article] = []
    for a in unique:
        url = a.get("source_url", "")
        meta = source_meta.get(url, SourceItem())

        articles.append(
            Article(
                id="",
                title=a.get("title", ""),
                source_url=url,
                source_type=meta.get("source_type", "unknown"),
                summary=a.get("summary", ""),
                tags=a.get("tags", []),
                score=a.get("score", 5),
                published_at=(
                    meta.get("published_at")
                    or meta.get("created_at")
                    or ""
                ),
                fetched_at=meta.get("fetched_at", ""),
                analyzed_at=a.get("analyzed_at", ""),
                status="draft",
            )
        )

    logger.info("[organize_node] 整理完成，共 %d 条文章", len(articles))
    result: Dict[str, Any] = {"articles": articles}
    if tracker is not None:
        result["cost_tracker"] = tracker
    return result


# =============================================================================
# 节点 4: 审核
# =============================================================================

REVIEW_SYSTEM_PROMPT = """\
你是一个技术内容质量审核专家。请从以下四个维度评估文章质量：

1. 摘要质量（summary_quality）：摘要是否准确、完整、有深度
2. 标签准确（tag_accuracy）：标签是否准确反映内容
3. 分类合理（category_validity）：来源分类是否合理
4. 一致性（consistency）：标题、摘要、标签是否一致

返回 JSON 格式：
{
  "passed": true,
  "overall_score": 0.85,
  "feedback": "改进建议（如不通过则详细说明问题）",
  "scores": {
    "summary_quality": 0.9,
    "tag_accuracy": 0.8,
    "category_validity": 0.85,
    "consistency": 0.85
  }
}"""


def review_node(state: KBState) -> dict:
    """LLM 四维度评分（摘要质量/标签准确/分类合理/一致性）。

    当 iteration >= 2 时强制通过，避免无限循环。

    Args:
        state: 当前工作流状态，需包含 articles 和 iteration 字段。

    Returns:
        包含 review_passed、review_feedback、iteration 和 cost_tracker
        字段的部分状态更新。
    """
    iteration = state.get("iteration", 0)
    logger.info("[review_node] 开始审核（iteration=%d）", iteration)

    # iteration >= 2 强制通过
    if iteration >= 2:
        logger.info("[review_node] iteration >= 2，强制通过")
        return {
            "review_passed": True,
            "review_feedback": "",
            "iteration": iteration + 1,
        }

    articles = state.get("articles", [])
    if not articles:
        logger.warning("[review_node] 无文章可审核")
        return {
            "review_passed": False,
            "review_feedback": "无文章可审核",
            "iteration": iteration + 1,
        }

    tracker = dict(state.get("cost_tracker") or _empty_cost_tracker())

    # 构建审核 prompt
    articles_text = ""
    for i, a in enumerate(articles, 1):
        articles_text += f"""
--- 文章 {i} ---
标题: {a.get('title', '')}
摘要: {a.get('summary', '')}
标签: {', '.join(a.get('tags', []))}
评分: {a.get('score', 0)}
来源: {a.get('source_type', '')}
"""

    prompt = f"""请审核以下 {len(articles)} 篇文章的整体质量：

{articles_text}

请对整体质量进行评估，返回 JSON。"""

    try:
        result, usage = chat_json(
            prompt=prompt,
            system=REVIEW_SYSTEM_PROMPT,
            temperature=0.3,
        )
        accumulate_usage(tracker, usage)

        passed = bool(result.get("passed", False))
        overall_score = float(result.get("overall_score", 0.0))
        feedback = str(result.get("feedback", ""))
        scores = result.get("scores", {})

        logger.info(
            "[review_node] 审核结果: passed=%s, overall_score=%.2f, "
            "scores=%s",
            passed,
            overall_score,
            scores,
        )

        return {
            "review_passed": passed,
            "review_feedback": feedback,
            "iteration": iteration + 1,
            "cost_tracker": tracker,
        }
    except Exception as exc:
        logger.warning("[review_node] 审核异常: %s", exc)
        return {
            "review_passed": False,
            "review_feedback": f"审核异常: {exc}",
            "iteration": iteration + 1,
            "cost_tracker": tracker,
        }


def review_node_test(state: KBState) -> dict:
    """[临时测试] 模拟审核循环，不调用 LLM。

    前 2 次返回不通过 + 不同 feedback，第 3 次强制通过。
    验证后请删除此函数，改回 review_node。

    Args:
        state: 当前工作流状态。

    Returns:
        包含 review_passed、review_feedback、iteration 的部分状态更新。
    """
    iteration = state.get("iteration", 0)

    test_feedbacks = [
        "摘要过于简短，缺少技术亮点；标签不够精确，建议增加具体框架名称",
        "标签分类不合理，缺少应用场景标签；一致性有待提高，标题与摘要关联度低",
    ]

    if iteration < 2:
        passed = False
        feedback = test_feedbacks[iteration]
    else:
        passed = True
        feedback = ""

    logger.info(
        "[review_node_test] iteration=%d, review_passed=%s",
        iteration,
        passed,
    )
    if feedback:
        logger.info("[review_node_test] feedback: %s", feedback)

    return {
        "review_passed": passed,
        "review_feedback": feedback,
        "iteration": iteration + 1,
    }


# =============================================================================
# 节点 5: 保存
# =============================================================================


def save_node(state: KBState) -> dict:
    """将 articles 写入 knowledge/articles/ 目录的 JSON 文件。

    同时更新 index.json 索引文件，实现按 URL 去重。
    跳过索引中已存在的 URL，避免重复保存。

    Args:
        state: 当前工作流状态，需包含 articles 字段。

    Returns:
        包含 articles 字段的部分状态更新（仅包含实际保存的文章）。
    """
    articles = state.get("articles", [])
    logger.info("[save_node] 开始保存 %d 篇文章", len(articles))

    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    index = _load_index()

    saved: List[Article] = []
    for article in articles:
        url = article.get("source_url", "")
        if url in index:
            logger.info("[save_node] 跳过已存在: %s", url)
            continue

        # 生成并分配 ID
        article_id = _generate_article_id(
            article.get("source_type", ""), index
        )
        article["id"] = article_id
        article["status"] = "published"

        # 写入 JSON 文件
        filepath = ARTICLES_DIR / f"{article_id}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(article, f, ensure_ascii=False, indent=2)

        # 更新索引
        index[url] = article_id
        saved.append(article)
        logger.info("[save_node] 已保存: %s", filepath.name)

    _save_index(index)
    logger.info("[save_node] 保存完成，共 %d 篇文章", len(saved))
    return {"articles": saved}
