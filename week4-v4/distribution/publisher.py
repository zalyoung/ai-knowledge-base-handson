"""推送模块：将格式化内容分发到多个渠道。

本模块提供异步推送能力，支持以下渠道：
- Telegram：通过 Bot API 发送 MarkdownV2 消息
- 飞书：通过 Webhook 发送 Interactive Card 消息

所有推送器继承自 BasePublisher 抽象基类，遵循统一接口规范。
"""

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import aiohttp

from distribution.formatter import generate_daily_digest

logger = logging.getLogger(__name__)

# 默认超时时间（秒）
DEFAULT_TIMEOUT = 30


@dataclass
class PublishResult:
    """发布结果数据类。

    Attributes:
        channel: 发布渠道名称。
        success: 是否成功。
        message_id: 消息 ID（成功时）。
        error: 错误信息（失败时）。
    """

    channel: str
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None


class BasePublisher(ABC):
    """发布器抽象基类。

    所有渠道发布器必须继承此类并实现抽象方法。

    Attributes:
        channel_name: 渠道名称标识。
    """

    channel_name: str = "base"

    @abstractmethod
    async def send_message(self, content: str) -> PublishResult:
        """发送单条消息。

        Args:
            content: 消息内容。

        Returns:
            PublishResult: 发布结果。
        """
        pass

    @abstractmethod
    async def send_digest(self, digest: Dict[str, Any]) -> PublishResult:
        """发送每日简报。

        Args:
            digest: 每日简报字典，包含 markdown、telegram、feishu 等格式。

        Returns:
            PublishResult: 发布结果。
        """
        pass


class TelegramPublisher(BasePublisher):
    """Telegram Bot API 推送器。

    通过 Telegram Bot API 异步发送 MarkdownV2 格式消息。

    环境变量：
        TELEGRAM_BOT_TOKEN: Bot Token。
        TELEGRAM_CHAT_ID: 目标聊天 ID。

    Example:
        >>> publisher = TelegramPublisher()
        >>> result = await publisher.send_message("Hello")
        >>> print(result.success)
        True
    """

    channel_name = "telegram"

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        """初始化 Telegram 推送器。

        Args:
            bot_token: Bot Token，默认从环境变量读取。
            chat_id: 目标聊天 ID，默认从环境变量读取。
            timeout: 请求超时时间（秒）。

        Raises:
            ValueError: 当未提供必要的环境变量时。
        """
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.timeout = timeout

        if not self.bot_token:
            raise ValueError("未设置 TELEGRAM_BOT_TOKEN 环境变量")
        if not self.chat_id:
            raise ValueError("未设置 TELEGRAM_CHAT_ID 环境变量")

        self.api_base = f"https://api.telegram.org/bot{self.bot_token}"

    async def send_message(self, content: str) -> PublishResult:
        """通过 Telegram Bot API 发送 MarkdownV2 消息。

        Args:
            content: MarkdownV2 格式的消息内容。

        Returns:
            PublishResult: 发布结果，包含 message_id 或 error。
        """
        url = f"{self.api_base}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": content,
            "parse_mode": "MarkdownV2",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as response:
                    data = await response.json()

                    if response.ok and data.get("ok"):
                        message_id = str(data["result"]["message_id"])
                        logger.info(
                            "Telegram 消息发送成功: message_id=%s",
                            message_id,
                        )
                        return PublishResult(
                            channel=self.channel_name,
                            success=True,
                            message_id=message_id,
                        )
                    else:
                        error_msg = data.get("description", "未知错误")
                        logger.error(
                            "Telegram 消息发送失败: %s",
                            error_msg,
                        )
                        return PublishResult(
                            channel=self.channel_name,
                            success=False,
                            error=error_msg,
                        )

        except aiohttp.ClientError as e:
            error_msg = f"网络请求异常: {e}"
            logger.error("Telegram 推送异常: %s", error_msg)
            return PublishResult(
                channel=self.channel_name,
                success=False,
                error=error_msg,
            )
        except asyncio.TimeoutError:
            error_msg = f"请求超时（{self.timeout}秒）"
            logger.error("Telegram 推送超时: %s", error_msg)
            return PublishResult(
                channel=self.channel_name,
                success=False,
                error=error_msg,
            )
        except Exception as e:
            error_msg = f"未知异常: {e}"
            logger.error("Telegram 推送异常: %s", error_msg)
            return PublishResult(
                channel=self.channel_name,
                success=False,
                error=error_msg,
            )

    async def send_digest(self, digest: Dict[str, Any]) -> PublishResult:
        """发送 Telegram 格式的每日简报。

        Args:
            digest: 每日简报字典，需包含 telegram 字段。

        Returns:
            PublishResult: 发布结果。
        """
        telegram_content = digest.get("telegram", "")
        if not telegram_content:
            return PublishResult(
                channel=self.channel_name,
                success=False,
                error="简报中无 Telegram 格式内容",
            )

        return await self.send_message(telegram_content)


class FeishuPublisher(BasePublisher):
    """飞书 Webhook 推送器。

    通过飞书 Webhook 发送 Interactive Card 消息。

    环境变量：
        FEISHU_WEBHOOK_URL: 飞书 Webhook 地址。

    Example:
        >>> publisher = FeishuPublisher()
        >>> result = await publisher.send_message({"msg_type": "interactive", ...})
        >>> print(result.success)
        True
    """

    channel_name = "feishu"

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        """初始化飞书推送器。

        Args:
            webhook_url: 飞书 Webhook 地址，默认从环境变量读取。
            timeout: 请求超时时间（秒）。

        Raises:
            ValueError: 当未提供必要的环境变量时。
        """
        self.webhook_url = webhook_url or os.getenv("FEISHU_WEBHOOK_URL")
        self.timeout = timeout

        if not self.webhook_url:
            raise ValueError("未设置 FEISHU_WEBHOOK_URL 环境变量")

    async def send_message(self, content: Any) -> PublishResult:
        """通过飞书 Webhook 发送卡片消息。

        Args:
            content: 飞书 Interactive Card 字典或字符串内容。

        Returns:
            PublishResult: 发布结果。
        """
        # 如果是字符串，包装为文本消息
        if isinstance(content, str):
            payload = {
                "msg_type": "text",
                "content": {"text": content},
            }
        else:
            payload = content

        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                ) as response:
                    data = await response.json()

                    if response.ok and data.get("code") == 0:
                        msg_id = data.get("data", {}).get("message_id", "")
                        logger.info(
                            "飞书消息发送成功: message_id=%s",
                            msg_id,
                        )
                        return PublishResult(
                            channel=self.channel_name,
                            success=True,
                            message_id=msg_id,
                        )
                    else:
                        error_msg = data.get("msg", "未知错误")
                        logger.error(
                            "飞书消息发送失败: %s",
                            error_msg,
                        )
                        return PublishResult(
                            channel=self.channel_name,
                            success=False,
                            error=error_msg,
                        )

        except aiohttp.ClientError as e:
            error_msg = f"网络请求异常: {e}"
            logger.error("飞书推送异常: %s", error_msg)
            return PublishResult(
                channel=self.channel_name,
                success=False,
                error=error_msg,
            )
        except asyncio.TimeoutError:
            error_msg = f"请求超时（{self.timeout}秒）"
            logger.error("飞书推送超时: %s", error_msg)
            return PublishResult(
                channel=self.channel_name,
                success=False,
                error=error_msg,
            )
        except Exception as e:
            error_msg = f"未知异常: {e}"
            logger.error("飞书推送异常: %s", error_msg)
            return PublishResult(
                channel=self.channel_name,
                success=False,
                error=error_msg,
            )

    async def send_digest(self, digest: Dict[str, Any]) -> PublishResult:
        """发送飞书格式的每日简报。

        Args:
            digest: 每日简报字典，需包含 feishu 字段。

        Returns:
            PublishResult: 发布结果。
        """
        feishu_content = digest.get("feishu", {})
        if not feishu_content:
            return PublishResult(
                channel=self.channel_name,
                success=False,
                error="简报中无飞书格式内容",
            )

        return await self.send_message(feishu_content)


async def publish_daily_digest(
    knowledge_dir: str = "knowledge/articles",
    date: Optional[str] = None,
    top_n: int = 5,
    publishers: Optional[List[BasePublisher]] = None,
) -> List[PublishResult]:
    """统一异步入口：生成并发布每日知识简报。

    调用 generate_daily_digest() 生成三种格式，然后并发发布到所有渠道。

    Args:
        knowledge_dir: 知识库文章目录路径。
        date: 日期字符串（YYYY-MM-DD 格式），默认为今天。
        top_n: 返回的文章数量上限。
        publishers: 发布器列表，默认自动创建 Telegram 和飞书发布器。

    Returns:
        List[PublishResult]: 所有渠道的发布结果列表。
    """
    # 生成每日简报
    digest = generate_daily_digest(knowledge_dir, date, top_n)
    logger.info("每日简报生成完成: date=%s, top_n=%d", date or "today", top_n)

    # 初始化发布器列表
    if publishers is None:
        publishers = []
        try:
            publishers.append(TelegramPublisher())
        except ValueError as e:
            logger.warning("跳过 Telegram 推送器: %s", e)

        try:
            publishers.append(FeishuPublisher())
        except ValueError as e:
            logger.warning("跳过飞书推送器: %s", e)

    if not publishers:
        logger.warning("无可用的发布器，跳过推送")
        return []

    # 并发发布到所有渠道
    tasks = [publisher.send_digest(digest) for publisher in publishers]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 处理异常结果
    publish_results: List[PublishResult] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            publish_results.append(
                PublishResult(
                    channel=publishers[i].channel_name,
                    success=False,
                    error=f"发布异常: {result}",
                )
            )
        else:
            publish_results.append(result)

    # 记录发布结果摘要
    success_count = sum(1 for r in publish_results if r.success)
    logger.info(
        "推送完成: %d/%d 渠道成功",
        success_count,
        len(publish_results),
    )

    return publish_results