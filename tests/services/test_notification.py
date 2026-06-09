"""Tests for notification service."""

import pytest
from unittest.mock import MagicMock, patch

from src.services.notification.sender import WechatSender, FeishuSender, EmailSender
from src.services.notification.routing import parse_channels, split_channels, get_route_config
from src.services.notification.formatters import chunk_content_by_max_bytes, format_feishu_markdown, slice_at_max_bytes


class TestWechatSender:
    def test_not_configured(self):
        settings = MagicMock()
        settings.wechat_webhook_url = ""
        sender = WechatSender(settings)
        assert not sender.is_configured
        assert sender.send("hello") is False

    @patch("src.services.notification.sender.wechat_sender.requests.post")
    def test_send_markdown(self, mock_post):
        settings = MagicMock()
        settings.wechat_webhook_url = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test"
        settings.wechat_msg_type = "markdown"
        settings.wechat_max_bytes = 4000
        settings.webhook_verify_ssl = True

        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"errcode": 0}

        sender = WechatSender(settings)
        assert sender.is_configured
        assert sender.send("## Hello") is True

        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs["json"]
        assert payload["msgtype"] == "markdown"
        assert payload["markdown"]["content"] == "## Hello"


class TestFeishuSender:
    def test_not_configured(self):
        settings = MagicMock()
        settings.feishu_webhook_url = ""
        sender = FeishuSender(settings)
        assert not sender.is_configured
        assert sender.send("hello") is False

    @patch("src.services.notification.sender.feishu_sender.requests.post")
    def test_send_card(self, mock_post):
        settings = MagicMock()
        settings.feishu_webhook_url = "https://open.feishu.cn/open-apis/bot/v2/hook/test"
        settings.feishu_webhook_secret = ""
        settings.feishu_webhook_keyword = ""
        settings.feishu_max_bytes = 20000
        settings.webhook_verify_ssl = True

        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"code": 0}

        sender = FeishuSender(settings)
        assert sender.is_configured
        assert sender.send("## Hello") is True

        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs["json"]
        assert payload["msg_type"] == "interactive"


class TestEmailSender:
    def test_not_configured(self):
        settings = MagicMock()
        settings.email_sender = ""
        settings.email_password = ""
        sender = EmailSender(settings)
        assert not sender.is_configured
        assert sender.send("hello") is False

    @patch("src.services.notification.sender.email_sender.smtplib.SMTP_SSL")
    def test_send_email(self, mock_smtp):
        settings = MagicMock()
        settings.email_sender = "test@qq.com"
        settings.email_password = "password"
        settings.email_receivers = "receiver@qq.com"
        settings.email_sender_name = "Test"

        mock_instance = MagicMock()
        mock_smtp.return_value = mock_instance

        sender = EmailSender(settings)
        assert sender.is_configured
        assert sender.send("## Hello") is True

        mock_smtp.assert_called_once_with("smtp.qq.com", 465, timeout=30)
        mock_instance.login.assert_called_once_with("test@qq.com", "password")
        mock_instance.send_message.assert_called_once()
        mock_instance.quit.assert_called_once()


class TestFormatters:
    def test_slice_at_max_bytes(self):
        text = "Hello World"
        a, b = slice_at_max_bytes(text, 5)
        assert a == "Hello"
        assert b == " World"

    def test_slice_at_max_bytes_utf8(self):
        text = "你好世界"
        a, b = slice_at_max_bytes(text, 6)
        assert a == "你好"
        assert b == "世界"

    def test_chunk_content_by_max_bytes(self):
        content = "A\n---\nB\n---\nC"
        chunks = chunk_content_by_max_bytes(content, 100)
        assert len(chunks) == 1
        assert chunks[0] == content

    def test_format_feishu_markdown(self):
        md = "# Title\n> Quote\n- item"
        result = format_feishu_markdown(md)
        assert "**Title**" in result
        assert "💬 Quote" in result
        assert "• item" in result


class TestRouting:
    def test_parse_channels(self):
        assert parse_channels("wechat,feishu,email") == ["wechat", "feishu", "email"]
        assert parse_channels(["wechat", "email"]) == ["wechat", "email"]
        assert parse_channels(None) == []

    def test_split_channels(self):
        valid, invalid = split_channels(["wechat", "feishu", "unknown"])
        assert valid == ["wechat", "feishu"]
        assert invalid == ["unknown"]

    def test_get_route_config(self):
        assert get_route_config("report") is not None
        assert get_route_config("unknown") is None


class TestNotificationService:
    @pytest.mark.asyncio
    async def test_push_raw_file_not_found(self, tmp_path):
        from src.services.notification import NotificationService

        settings = MagicMock()
        settings.raw_knowledge_dir = tmp_path
        settings.notification_enabled = False
        settings.wechat_webhook_url = ""
        settings.feishu_webhook_url = ""
        settings.email_sender = ""

        service = NotificationService(settings)
        result = await service.push_raw("nonexistent.md")
        assert not result.success
        assert "not found" in result.message

    @pytest.mark.asyncio
    async def test_send_no_channels(self):
        from src.services.notification import NotificationService

        settings = MagicMock()
        settings.wechat_webhook_url = ""
        settings.feishu_webhook_url = ""
        settings.email_sender = ""
        settings.notification_report_channels = ""

        service = NotificationService(settings)
        result = await service.send("hello")
        assert not result.success
        assert "No channels available" in result.message

    @pytest.mark.asyncio
    async def test_send_with_wechat(self):
        from src.services.notification import NotificationService

        settings = MagicMock()
        settings.wechat_webhook_url = "https://test"
        settings.feishu_webhook_url = ""
        settings.email_sender = ""
        settings.notification_report_channels = ""
        settings.webhook_verify_ssl = True
        settings.wechat_msg_type = "markdown"
        settings.wechat_max_bytes = 4000

        service = NotificationService(settings)
        with patch.object(service._wechat, "send", return_value=True):
            result = await service.send("hello", channels=["wechat"])
            assert result.success
            assert len(result.channel_results) == 1
            assert result.channel_results[0].channel == "wechat"
            assert result.channel_results[0].success is True
