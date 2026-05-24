"""知识库交互模块：提供 Bot 对话式知识库访问能力。

本模块实现四个核心类：
- KnowledgeSearchEngine: 搜索引擎，支持关键词、标签、日期范围过滤
- SubscriptionManager: 用户订阅管理（增删查）
- PermissionManager: 三级权限控制（READ/WRITE/DELETE）
- KnowledgeBot: 整合以上模块的主入口

所有操作通过 recognize_intent 进行意图识别，支持命令前缀和自然语言。
"""

import json
import logging
import re
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 知识库文章目录
ARTICLES_DIR = Path(__file__).parent.parent / "knowledge" / "articles"

# 默认返回结果数量
DEFAULT_SEARCH_LIMIT = 5
DEFAULT_TOP_LIMIT = 10


class Intent(Enum):
    """用户意图枚举。

    Attributes:
        SEARCH: 搜索知识库文章。
        TODAY: 获取今日新增文章。
        TOP: 获取热门/高分文章。
        SUBSCRIBE: 订阅标签或关键词。
        UNSUBSCRIBE: 取消订阅。
        HELP: 查看帮助信息。
        UNKNOWN: 无法识别的意图。
    """

    SEARCH = auto()
    TODAY = auto()
    TOP = auto()
    SUBSCRIBE = auto()
    UNSUBSCRIBE = auto()
    HELP = auto()
    UNKNOWN = auto()


class Permission(Enum):
    """权限级别枚举。

    Attributes:
        READ: 读取权限，可搜索和查看文章。
        WRITE: 写入权限，可订阅和管理个人设置。
        DELETE: 删除权限，可管理订阅和其他用户数据。
    """

    READ = "read"
    WRITE = "write"
    DELETE = "delete"


# 权限层级映射（数值越大权限越高）
PERMISSION_HIERARCHY: Dict[Permission, int] = {
    Permission.READ: 1,
    Permission.WRITE: 2,
    Permission.DELETE: 3,
}

# 意图所需最低权限
INTENT_PERMISSION_MAP: Dict[Intent, Permission] = {
    Intent.SEARCH: Permission.READ,
    Intent.TODAY: Permission.READ,
    Intent.TOP: Permission.READ,
    Intent.SUBSCRIBE: Permission.WRITE,
    Intent.UNSUBSCRIBE: Permission.WRITE,
    Intent.HELP: Permission.READ,
}


def recognize_intent(text: str) -> Tuple[Intent, str]:
    """识别用户输入的意图。

    优先匹配命令前缀（/search, /today, /top, /subscribe, /help），
    再匹配自然语言关键词（搜索、查询、今天、简报、订阅等）。

    Args:
        text: 用户输入的文本。

    Returns:
        (Intent, 参数字符串) 元组。Intent 为识别出的意图枚举，
        参数字符串为命令后的附加内容（如搜索关键词）。

    Example:
        >>> recognize_intent("/search langgraph")
        (<Intent.SEARCH: 1>, 'langgraph')
        >>> recognize_intent("帮我搜索 agent 相关内容")
        (<Intent.SEARCH: 1>, 'agent 相关内容')
    """
    if not text or not text.strip():
        return Intent.UNKNOWN, ""

    text = text.strip()

    # 第一优先级：命令前缀匹配
    command_patterns: List[Tuple[str, Intent]] = [
        (r"^/search\s*(.*)", Intent.SEARCH),
        (r"^/today\s*(.*)", Intent.TODAY),
        (r"^/top\s*(.*)", Intent.TOP),
        (r"^/subscribe\s*(.*)", Intent.SUBSCRIBE),
        (r"^/unsubscribe\s*(.*)", Intent.UNSUBSCRIBE),
        (r"^/help\s*(.*)", Intent.HELP),
    ]

    for pattern, intent in command_patterns:
        match = re.match(pattern, text, re.IGNORECASE)
        if match:
            args = match.group(1).strip()
            return intent, args

    # 第二优先级：自然语言关键词匹配
    keyword_patterns: List[Tuple[List[str], Intent]] = [
        (["搜索", "查询", "查找", "找", "search", "query"], Intent.SEARCH),
        (["今天", "今日", "最新", "today", "recent"], Intent.TODAY),
        (["热门", "排行", "top", "最佳", "推荐", "hot"], Intent.TOP),
        (["订阅", "关注", "subscribe", "follow"], Intent.SUBSCRIBE),
        (["取消订阅", "取消关注", "unsubscribe", "unfollow"], Intent.UNSUBSCRIBE),
        (["帮助", "怎么用", "使用说明", "help", "usage"], Intent.HELP),
    ]

    text_lower = text.lower()

    # 取消订阅优先于订阅匹配
    for keywords, intent in keyword_patterns:
        for keyword in keywords:
            if keyword in text_lower:
                # 提取关键词后的参数
                idx = text_lower.find(keyword)
                args = text[idx + len(keyword):].strip()
                return intent, args

    return Intent.UNKNOWN, ""


def load_articles() -> List[Dict[str, Any]]:
    """加载知识库文章目录下所有 JSON 文件。

    Returns:
        文章列表，每个元素为一个文章字典。

    Raises:
        FileNotFoundError: 如果文章目录不存在。
    """
    articles: List[Dict[str, Any]] = []
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


class KnowledgeSearchEngine:
    """知识库搜索引擎。

    支持关键词、标签、日期范围过滤，返回匹配的文章列表。

    Attributes:
        articles: 已加载的文章缓存。

    Example:
        >>> engine = KnowledgeSearchEngine()
        >>> results = engine.search("langgraph", limit=5)
        >>> len(results) > 0
        True
    """

    def __init__(self) -> None:
        """初始化搜索引擎，加载文章缓存。"""
        self._articles: Optional[List[Dict[str, Any]]] = None

    @property
    def articles(self) -> List[Dict[str, Any]]:
        """获取文章列表（带缓存）。

        Returns:
            文章字典列表。
        """
        if self._articles is None:
            self._articles = load_articles()
        return self._articles

    def reload(self) -> None:
        """强制重新加载文章缓存。"""
        self._articles = None

    def search(
        self,
        keyword: str,
        tags: Optional[List[str]] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> List[Dict[str, Any]]:
        """按关键词搜索文章，支持标签和日期范围过滤。

        Args:
            keyword: 搜索关键词，不区分大小写。
            tags: 标签过滤列表，文章需包含至少一个匹配标签。
            date_from: 起始日期（YYYY-MM-DD 格式）。
            date_to: 结束日期（YYYY-MM-DD 格式）。
            limit: 返回结果数量上限，默认 5。

        Returns:
            匹配的文章摘要列表（含 id、title、summary、tags、score）。

        Example:
            >>> engine = KnowledgeSearchEngine()
            >>> results = engine.search("agent", tags=["llm"])
        """
        keyword_lower = keyword.lower() if keyword else ""
        matched: List[Dict[str, Any]] = []

        for article in self.articles:
            # 关键词匹配
            if keyword_lower:
                title = article.get("title", "").lower()
                summary = article.get("summary", "").lower()
                article_tags = [t.lower() for t in article.get("tags", [])]

                if not (
                    keyword_lower in title
                    or keyword_lower in summary
                    or keyword_lower in article_tags
                ):
                    continue

            # 标签过滤
            if tags:
                article_tags_lower = {t.lower() for t in article.get("tags", [])}
                tags_lower = {t.lower() for t in tags}
                if not article_tags_lower.intersection(tags_lower):
                    continue

            # 日期范围过滤
            published_at = article.get("published_at", "")
            if date_from and published_at:
                if published_at < date_from:
                    continue
            if date_to and published_at:
                if published_at > date_to + "T23:59:59Z":
                    continue

            matched.append({
                "id": article.get("id", ""),
                "title": article.get("title", ""),
                "summary": article.get("summary", ""),
                "tags": article.get("tags", []),
                "score": article.get("score", 0),
                "published_at": article.get("published_at", ""),
            })

        # 按分数降序排序
        matched.sort(key=lambda x: x.get("score", 0), reverse=True)
        return matched[:limit]

    def get_today_articles(
        self, limit: int = DEFAULT_SEARCH_LIMIT
    ) -> List[Dict[str, Any]]:
        """获取今日新增文章。

        Args:
            limit: 返回结果数量上限，默认 5。

        Returns:
            今日发布的文章列表。
        """
        today = datetime.now().strftime("%Y-%m-%d")
        return self.search("", date_from=today, date_to=today, limit=limit)

    def get_top_articles(
        self, limit: int = DEFAULT_TOP_LIMIT
    ) -> List[Dict[str, Any]]:
        """获取热门/高分文章。

        Args:
            limit: 返回结果数量上限，默认 10。

        Returns:
            按分数排序的文章列表。
        """
        articles_with_score = [
            {
                "id": a.get("id", ""),
                "title": a.get("title", ""),
                "summary": a.get("summary", ""),
                "tags": a.get("tags", []),
                "score": a.get("score", 0),
                "published_at": a.get("published_at", ""),
            }
            for a in self.articles
        ]
        articles_with_score.sort(key=lambda x: x.get("score", 0), reverse=True)
        return articles_with_score[:limit]


class SubscriptionManager:
    """用户订阅管理器。

    管理用户的标签和关键词订阅，支持增删查操作。

    Attributes:
        subscriptions_file: 订阅数据存储文件路径。

    Example:
        >>> manager = SubscriptionManager()
        >>> manager.add_subscription("user123", "langgraph")
        >>> manager.get_subscriptions("user123")
        ['langgraph']
    """

    def __init__(
        self, subscriptions_file: Optional[Path] = None
    ) -> None:
        """初始化订阅管理器。

        Args:
            subscriptions_file: 订阅数据存储文件路径，
                默认为 knowledge/subscriptions.json。
        """
        self.subscriptions_file = subscriptions_file or (
            ARTICLES_DIR.parent / "subscriptions.json"
        )
        self._subscriptions: Optional[Dict[str, List[str]]] = None

    @property
    def subscriptions(self) -> Dict[str, List[str]]:
        """获取所有订阅数据（带缓存）。

        Returns:
            用户订阅字典，键为 user_id，值为订阅列表。
        """
        if self._subscriptions is None:
            self._subscriptions = self._load_subscriptions()
        return self._subscriptions

    def _load_subscriptions(self) -> Dict[str, List[str]]:
        """从文件加载订阅数据。

        Returns:
            用户订阅字典。
        """
        if not self.subscriptions_file.exists():
            return {}
        try:
            data = json.loads(
                self.subscriptions_file.read_text(encoding="utf-8")
            )
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("加载订阅数据失败: %s", exc)
            return {}

    def _save_subscriptions(self) -> None:
        """保存订阅数据到文件。"""
        try:
            self.subscriptions_file.parent.mkdir(parents=True, exist_ok=True)
            self.subscriptions_file.write_text(
                json.dumps(self.subscriptions, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.error("保存订阅数据失败: %s", exc)

    def add_subscription(self, user_id: str, keyword: str) -> bool:
        """添加用户订阅。

        Args:
            user_id: 用户唯一标识。
            keyword: 订阅关键词或标签。

        Returns:
            是否成功添加（已存在则返回 False）。
        """
        if user_id not in self.subscriptions:
            self.subscriptions[user_id] = []

        if keyword.lower() in [k.lower() for k in self.subscriptions[user_id]]:
            return False

        self.subscriptions[user_id].append(keyword)
        self._save_subscriptions()
        logger.info("用户 %s 订阅: %s", user_id, keyword)
        return True

    def remove_subscription(self, user_id: str, keyword: str) -> bool:
        """移除用户订阅。

        Args:
            user_id: 用户唯一标识。
            keyword: 要取消的订阅关键词或标签。

        Returns:
            是否成功移除（不存在则返回 False）。
        """
        if user_id not in self.subscriptions:
            return False

        original_len = len(self.subscriptions[user_id])
        self.subscriptions[user_id] = [
            k for k in self.subscriptions[user_id]
            if k.lower() != keyword.lower()
        ]

        if len(self.subscriptions[user_id]) == original_len:
            return False

        self._save_subscriptions()
        logger.info("用户 %s 取消订阅: %s", user_id, keyword)
        return True

    def get_subscriptions(self, user_id: str) -> List[str]:
        """获取用户订阅列表。

        Args:
            user_id: 用户唯一标识。

        Returns:
            用户的订阅关键词列表。
        """
        return self.subscriptions.get(user_id, [])

    def get_all_subscribers(self) -> Dict[str, List[str]]:
        """获取所有用户订阅。

        Returns:
            所有用户订阅字典。
        """
        return self.subscriptions.copy()


class PermissionManager:
    """三级权限管理器。

    管理用户的权限级别（READ/WRITE/DELETE），支持权限校验。

    Attributes:
        permissions_file: 权限数据存储文件路径。

    Example:
        >>> manager = PermissionManager()
        >>> manager.set_permission("user123", Permission.WRITE)
        >>> manager.check_permission("user123", Permission.READ)
        True
    """

    def __init__(
        self, permissions_file: Optional[Path] = None
    ) -> None:
        """初始化权限管理器。

        Args:
            permissions_file: 权限数据存储文件路径，
                默认为 knowledge/permissions.json。
        """
        self.permissions_file = permissions_file or (
            ARTICLES_DIR.parent / "permissions.json"
        )
        self._permissions: Optional[Dict[str, str]] = None

    @property
    def permissions(self) -> Dict[str, str]:
        """获取所有权限数据（带缓存）。

        Returns:
            用户权限字典，键为 user_id，值为权限级别字符串。
        """
        if self._permissions is None:
            self._permissions = self._load_permissions()
        return self._permissions

    def _load_permissions(self) -> Dict[str, str]:
        """从文件加载权限数据。

        Returns:
            用户权限字典。
        """
        if not self.permissions_file.exists():
            return {}
        try:
            data = json.loads(
                self.permissions_file.read_text(encoding="utf-8")
            )
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("加载权限数据失败: %s", exc)
            return {}

    def _save_permissions(self) -> None:
        """保存权限数据到文件。"""
        try:
            self.permissions_file.parent.mkdir(parents=True, exist_ok=True)
            self.permissions_file.write_text(
                json.dumps(self.permissions, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.error("保存权限数据失败: %s", exc)

    def get_permission(self, user_id: str) -> Permission:
        """获取用户权限级别。

        未设置权限的用户默认为 READ 权限。

        Args:
            user_id: 用户唯一标识。

        Returns:
            用户的权限枚举值。
        """
        perm_str = self.permissions.get(user_id, Permission.READ.value)
        try:
            return Permission(perm_str)
        except ValueError:
            return Permission.READ

    def set_permission(self, user_id: str, permission: Permission) -> None:
        """设置用户权限级别。

        Args:
            user_id: 用户唯一标识。
            permission: 要设置的权限枚举值。
        """
        self.permissions[user_id] = permission.value
        self._save_permissions()
        logger.info("设置用户 %s 权限: %s", user_id, permission.value)

    def check_permission(
        self, user_id: str, required: Permission
    ) -> bool:
        """检查用户是否拥有所需权限。

        Args:
            user_id: 用户唯一标识。
            required: 所需的最低权限级别。

        Returns:
            是否拥有足够权限。
        """
        user_perm = self.get_permission(user_id)
        user_level = PERMISSION_HIERARCHY.get(user_perm, 0)
        required_level = PERMISSION_HIERARCHY.get(required, 0)
        return user_level >= required_level


class KnowledgeBot:
    """知识库交互机器人主入口。

    整合搜索引擎、订阅管理、权限控制，提供统一的消息处理接口。

    Attributes:
        search_engine: 搜索引擎实例。
        subscription_manager: 订阅管理器实例。
        permission_manager: 权限管理器实例。

    Example:
        >>> bot = KnowledgeBot()
        >>> response = bot.handle_message("user123", "/search langgraph")
        >>> print(response)
    """

    def __init__(
        self,
        search_engine: Optional[KnowledgeSearchEngine] = None,
        subscription_manager: Optional[SubscriptionManager] = None,
        permission_manager: Optional[PermissionManager] = None,
    ) -> None:
        """初始化知识库机器人。

        Args:
            search_engine: 搜索引擎实例，默认自动创建。
            subscription_manager: 订阅管理器实例，默认自动创建。
            permission_manager: 权限管理器实例，默认自动创建。
        """
        self.search_engine = search_engine or KnowledgeSearchEngine()
        self.subscription_manager = (
            subscription_manager or SubscriptionManager()
        )
        self.permission_manager = permission_manager or PermissionManager()

    def handle_message(self, user_id: str, text: str) -> str:
        """处理用户消息的统一入口。

        根据 recognize_intent 结果分发到对应处理器。

        Args:
            user_id: 用户唯一标识。
            text: 用户输入的文本消息。

        Returns:
            格式化后的响应文本。
        """
        intent, args = recognize_intent(text)
        logger.info(
            "用户 %s 意图识别: intent=%s, args=%s",
            user_id,
            intent.name,
            args,
        )

        # 权限检查
        required_perm = INTENT_PERMISSION_MAP.get(intent, Permission.READ)
        if not self.permission_manager.check_permission(
            user_id, required_perm
        ):
            return (
                f"权限不足：此操作需要 {required_perm.value} 权限，"
                f"您当前权限为 "
                f"{self.permission_manager.get_permission(user_id).value}"
            )

        # 意图分发
        handlers = {
            Intent.SEARCH: self._handle_search,
            Intent.TODAY: self._handle_today,
            Intent.TOP: self._handle_top,
            Intent.SUBSCRIBE: self._handle_subscribe,
            Intent.UNSUBSCRIBE: self._handle_unsubscribe,
            Intent.HELP: self._handle_help,
        }

        handler = handlers.get(intent)
        if handler:
            return handler(user_id, args)

        return self._handle_unknown(args)

    def _handle_search(self, user_id: str, args: str) -> str:
        """处理搜索意图。

        Args:
            user_id: 用户唯一标识。
            args: 搜索关键词。

        Returns:
            搜索结果格式化文本。
        """
        if not args:
            return "请提供搜索关键词，例如：/search langgraph"

        results = self.search_engine.search(args, limit=DEFAULT_SEARCH_LIMIT)

        if not results:
            return f"未找到与「{args}」相关的文章。"

        lines = [f"🔍 搜索「{args}」找到 {len(results)} 篇相关文章：\n"]
        for i, article in enumerate(results, 1):
            tags_str = ", ".join(article.get("tags", [])[:3])
            lines.append(
                f"{i}. **{article['title']}**\n"
                f"   标签: {tags_str}\n"
                f"   摘要: {article['summary'][:100]}...\n"
            )
        return "\n".join(lines)

    def _handle_today(self, user_id: str, args: str) -> str:
        """处理今日文章意图。

        Args:
            user_id: 用户唯一标识。
            args: 附加参数（未使用）。

        Returns:
            今日文章格式化文本。
        """
        results = self.search_engine.get_today_articles(
            limit=DEFAULT_SEARCH_LIMIT
        )

        if not results:
            return "📰 今日暂无新增文章。"

        lines = [f"📰 今日新增 {len(results)} 篇文章：\n"]
        for i, article in enumerate(results, 1):
            tags_str = ", ".join(article.get("tags", [])[:3])
            lines.append(
                f"{i}. **{article['title']}**\n"
                f"   标签: {tags_str}\n"
                f"   摘要: {article['summary'][:100]}...\n"
            )
        return "\n".join(lines)

    def _handle_top(self, user_id: str, args: str) -> str:
        """处理热门文章意图。

        Args:
            user_id: 用户唯一标识。
            args: 附加参数（未使用）。

        Returns:
            热门文章格式化文本。
        """
        results = self.search_engine.get_top_articles(
            limit=DEFAULT_TOP_LIMIT
        )

        if not results:
            return "📊 暂无热门文章数据。"

        lines = [f"📊 热门 Top {len(results)} 文章：\n"]
        for i, article in enumerate(results, 1):
            score = article.get("score", 0)
            tags_str = ", ".join(article.get("tags", [])[:3])
            lines.append(
                f"{i}. **{article['title']}** (评分: {score})\n"
                f"   标签: {tags_str}\n"
                f"   摘要: {article['summary'][:100]}...\n"
            )
        return "\n".join(lines)

    def _handle_subscribe(self, user_id: str, args: str) -> str:
        """处理订阅意图。

        Args:
            user_id: 用户唯一标识。
            args: 要订阅的关键词或标签。

        Returns:
            订阅结果文本。
        """
        if not args:
            # 显示当前订阅
            subs = self.subscription_manager.get_subscriptions(user_id)
            if subs:
                return f"📌 您当前的订阅：{', '.join(subs)}"
            return "📌 您暂无订阅。使用 /subscribe <关键词> 添加订阅。"

        success = self.subscription_manager.add_subscription(user_id, args)
        if success:
            return f"✅ 成功订阅「{args}」，后续将为您推送相关内容。"
        return f"ℹ️ 您已订阅「{args}」，无需重复订阅。"

    def _handle_unsubscribe(self, user_id: str, args: str) -> str:
        """处理取消订阅意图。

        Args:
            user_id: 用户唯一标识。
            args: 要取消的订阅关键词或标签。

        Returns:
            取消订阅结果文本。
        """
        if not args:
            return "请指定要取消的订阅，例如：/unsubscribe langgraph"

        success = self.subscription_manager.remove_subscription(
            user_id, args
        )
        if success:
            return f"✅ 已取消订阅「{args}」。"
        return f"ℹ️ 未找到订阅「{args}」。"

    def _handle_help(self, user_id: str, args: str) -> str:
        """处理帮助意图。

        Args:
            user_id: 用户唯一标识。
            args: 附加参数（未使用）。

        Returns:
            帮助信息文本。
        """
        return (
            "📖 知识库助手使用指南：\n\n"
            "🔍 **搜索文章**\n"
            "  /search <关键词> - 搜索知识库文章\n\n"
            "📰 **今日简报**\n"
            "  /today - 查看今日新增文章\n\n"
            "📊 **热门排行**\n"
            "  /top - 查看热门高分文章\n\n"
            "📌 **订阅管理**\n"
            "  /subscribe <关键词> - 订阅关键词\n"
            "  /subscribe - 查看当前订阅\n"
            "  /unsubscribe <关键词> - 取消订阅\n\n"
            "❓ **帮助**\n"
            "  /help - 显示本帮助信息\n\n"
            "💡 也支持自然语言输入，如「搜索 agent」「今天有什么新内容」"
        )

    def _handle_unknown(self, args: str) -> str:
        """处理未知意图。

        Args:
            args: 用户原始输入。

        Returns:
            引导用户使用正确命令的提示文本。
        """
        return (
            "🤔 抱歉，我没有理解您的意思。\n\n"
            "您可以尝试以下命令：\n"
            "  /search <关键词> - 搜索文章\n"
            "  /today - 今日简报\n"
            "  /top - 热门排行\n"
            "  /help - 查看帮助"
        )
