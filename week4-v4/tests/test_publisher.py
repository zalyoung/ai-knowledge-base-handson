"""distribution.publisher 单元测试。"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from distribution.publisher import (
    BasePublisher,
    FeishuPublisher,
    PublishResult,
    TelegramPublisher,
    publish_daily_digest,
)


class TestPublishResult:
    """测试 PublishResult 数据类。"""

    def test_success_result(self):
        """测试成功结果创建。"""
        result = PublishResult(
            channel="telegram",
            success=True,
            message_id="12345",
        )
        assert result.channel == "telegram"
        assert result.success is True
        assert result.message_id == "12345"
        assert result.error is None

    def test_failure_result(self):
        """测试失败结果创建。"""
        result = PublishResult(
            channel="feishu",
            success=False,
            error="网络异常",
        )
        assert result.channel == "feishu"
        assert result.success is False
        assert result.message_id is None
        assert result.error == "网络异常"

    def test_default_values(self):
        """测试默认值。"""
        result = PublishResult(channel="test", success=True)
        assert result.message_id is None
        assert result.error is None


class TestTelegramPublisher:
    """测试 TelegramPublisher。"""

    def test_init_with_params(self):
        """测试使用参数初始化。"""
        publisher = TelegramPublisher(
            bot_token="test_token",
            chat_id="test_chat_id",
        )
        assert publisher.bot_token == "test_token"
        assert publisher.chat_id == "test_chat_id"
        assert publisher.channel_name == "telegram"

    def test_init_with_env_vars(self):
        """测试使用环境变量初始化。"""
        with patch.dict(os.environ, {
            "TELEGRAM_BOT_TOKEN": "env_token",
            "TELEGRAM_CHAT_ID": "env_chat_id",
        }):
            publisher = TelegramPublisher()
            assert publisher.bot_token == "env_token"
            assert publisher.chat_id == "env_chat_id"

    def test_init_missing_token(self):
        """测试缺少 token 的情况。"""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
                TelegramPublisher()

    def test_init_missing_chat_id(self):
        """测试缺少 chat_id 的情况。"""
        with patch.dict(os.environ, {
            "TELEGRAM_BOT_TOKEN": "test_token",
        }, clear=True):
            with pytest.raises(ValueError, match="TELEGRAM_CHAT_ID"):
                TelegramPublisher()

    @pytest.mark.asyncio
    async def test_send_message_success(self):
        """测试成功发送消息。"""
        publisher = TelegramPublisher(
            bot_token="test_token",
            chat_id="test_chat_id",
        )

        mock_response_data = {
            "ok": True,
            "result": {"message_id": 12345},
        }

        mock_response = AsyncMock()
        mock_response.ok = True
        mock_response.json = AsyncMock(return_value=mock_response_data)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await publisher.send_message("Test message")

            assert result.success is True
            assert result.message_id == "12345"
            assert result.channel == "telegram"

    @pytest.mark.asyncio
    async def test_send_message_failure(self):
        """测试发送消息失败。"""
        publisher = TelegramPublisher(
            bot_token="test_token",
            chat_id="test_chat_id",
        )

        mock_response_data = {
            "ok": False,
            "description": "Bad Request",
        }

        mock_response = AsyncMock()
        mock_response.ok = False
        mock_response.json = AsyncMock(return_value=mock_response_data)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await publisher.send_message("Test message")

            assert result.success is False
            assert result.error == "Bad Request"

    @pytest.mark.asyncio
    async def test_send_digest_success(self):
        """测试成功发送简报。"""
        publisher = TelegramPublisher(
            bot_token="test_token",
            chat_id="test_chat_id",
        )

        digest = {
            "telegram": "Test telegram content",
            "markdown": "Test markdown content",
            "feishu": {"msg_type": "interactive"},
        }

        mock_response_data = {
            "ok": True,
            "result": {"message_id": 12345},
        }

        mock_response = AsyncMock()
        mock_response.ok = True
        mock_response.json = AsyncMock(return_value=mock_response_data)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await publisher.send_digest(digest)

            assert result.success is True

    @pytest.mark.asyncio
    async def test_send_digest_no_content(self):
        """测试简报无 Telegram 内容。"""
        publisher = TelegramPublisher(
            bot_token="test_token",
            chat_id="test_chat_id",
        )

        digest = {
            "markdown": "Test markdown content",
            "feishu": {"msg_type": "interactive"},
        }

        result = await publisher.send_digest(digest)

        assert result.success is False
        assert "无 Telegram 格式内容" in result.error


class TestFeishuPublisher:
    """测试 FeishuPublisher。"""

    def test_init_with_params(self):
        """测试使用参数初始化。"""
        publisher = FeishuPublisher(
            webhook_url="https://test.feishu.cn/webhook",
        )
        assert publisher.webhook_url == "https://test.feishu.cn/webhook"
        assert publisher.channel_name == "feishu"

    def test_init_with_env_vars(self):
        """测试使用环境变量初始化。"""
        with patch.dict(os.environ, {
            "FEISHU_WEBHOOK_URL": "https://env.feishu.cn/webhook",
        }):
            publisher = FeishuPublisher()
            assert publisher.webhook_url == "https://env.feishu.cn/webhook"

    def test_init_missing_webhook_url(self):
        """测试缺少 webhook_url 的情况。"""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="FEISHU_WEBHOOK_URL"):
                FeishuPublisher()

    @pytest.mark.asyncio
    async def test_send_message_success(self):
        """测试成功发送消息。"""
        publisher = FeishuPublisher(
            webhook_url="https://test.feishu.cn/webhook",
        )

        mock_response_data = {
            "code": 0,
            "data": {"message_id": "msg_123"},
        }

        mock_response = AsyncMock()
        mock_response.ok = True
        mock_response.json = AsyncMock(return_value=mock_response_data)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await publisher.send_message({"msg_type": "interactive"})

            assert result.success is True
            assert result.message_id == "msg_123"
            assert result.channel == "feishu"

    @pytest.mark.asyncio
    async def test_send_message_string_content(self):
        """测试发送字符串内容。"""
        publisher = FeishuPublisher(
            webhook_url="https://test.feishu.cn/webhook",
        )

        mock_response_data = {
            "code": 0,
            "data": {"message_id": "msg_456"},
        }

        mock_response = AsyncMock()
        mock_response.ok = True
        mock_response.json = AsyncMock(return_value=mock_response_data)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await publisher.send_message("Test text message")

            assert result.success is True

    @pytest.mark.asyncio
    async def test_send_message_failure(self):
        """测试发送消息失败。"""
        publisher = FeishuPublisher(
            webhook_url="https://test.feishu.cn/webhook",
        )

        mock_response_data = {
            "code": 9499,
            "msg": "Invalid webhook",
        }

        mock_response = AsyncMock()
        mock_response.ok = False
        mock_response.json = AsyncMock(return_value=mock_response_data)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await publisher.send_message({"msg_type": "interactive"})

            assert result.success is False
            assert result.error == "Invalid webhook"

    @pytest.mark.asyncio
    async def test_send_digest_success(self):
        """测试成功发送简报。"""
        publisher = FeishuPublisher(
            webhook_url="https://test.feishu.cn/webhook",
        )

        digest = {
            "telegram": "Test telegram content",
            "markdown": "Test markdown content",
            "feishu": {"msg_type": "interactive"},
        }

        mock_response_data = {
            "code": 0,
            "data": {"message_id": "msg_789"},
        }

        mock_response = AsyncMock()
        mock_response.ok = True
        mock_response.json = AsyncMock(return_value=mock_response_data)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await publisher.send_digest(digest)

            assert result.success is True

    @pytest.mark.asyncio
    async def test_send_digest_no_content(self):
        """测试简报无飞书内容。"""
        publisher = FeishuPublisher(
            webhook_url="https://test.feishu.cn/webhook",
        )

        digest = {
            "telegram": "Test telegram content",
            "markdown": "Test markdown content",
        }

        result = await publisher.send_digest(digest)

        assert result.success is False
        assert "无飞书格式内容" in result.error


class TestPublishDailyDigest:
    """测试 publish_daily_digest 函数。"""

    @pytest.mark.asyncio
    async def test_with_custom_publishers(self, tmp_path):
        """测试使用自定义发布器。"""
        # 创建测试文章文件
        articles_dir = tmp_path / "articles"
        articles_dir.mkdir()

        import json
        article = {
            "id": "2026-05-24-001",
            "title": "Test Article",
            "source_url": "https://example.com",
            "source_type": "github",
            "summary": "Test summary",
            "tags": ["test"],
            "relevance_score": 0.9,
        }
        (articles_dir / "2026-05-24-001.json").write_text(json.dumps(article))

        # 创建 mock 发布器
        mock_publisher = MagicMock(spec=BasePublisher)
        mock_publisher.channel_name = "test"
        mock_publisher.send_digest = AsyncMock(
            return_value=PublishResult(
                channel="test",
                success=True,
                message_id="test_msg_id",
            )
        )

        results = await publish_daily_digest(
            knowledge_dir=str(articles_dir),
            date="2026-05-24",
            publishers=[mock_publisher],
        )

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].channel == "test"

    @pytest.mark.asyncio
    async def test_with_no_publishers(self, tmp_path):
        """测试无发布器的情况。"""
        articles_dir = tmp_path / "articles"
        articles_dir.mkdir()

        with patch.dict(os.environ, {}, clear=True):
            results = await publish_daily_digest(
                knowledge_dir=str(articles_dir),
                publishers=[],
            )

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_with_publisher_exception(self, tmp_path):
        """测试发布器抛出异常的情况。"""
        articles_dir = tmp_path / "articles"
        articles_dir.mkdir()

        import json
        article = {
            "id": "2026-05-24-001",
            "title": "Test Article",
            "source_url": "https://example.com",
            "source_type": "github",
            "summary": "Test summary",
            "tags": ["test"],
            "relevance_score": 0.9,
        }
        (articles_dir / "2026-05-24-001.json").write_text(json.dumps(article))

        # 创建会抛出异常的 mock 发布器
        mock_publisher = MagicMock(spec=BasePublisher)
        mock_publisher.channel_name = "test"
        mock_publisher.send_digest = AsyncMock(side_effect=Exception("Test error"))

        results = await publish_daily_digest(
            knowledge_dir=str(articles_dir),
            date="2026-05-24",
            publishers=[mock_publisher],
        )

        assert len(results) == 1
        assert results[0].success is False
        assert "Test error" in results[0].error