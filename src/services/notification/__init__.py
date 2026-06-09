"""Notification service - push any raw file to WeChat, Feishu, or Email."""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import Settings

from .routing import get_route_config, split_channels
from .sender import EmailSender, FeishuSender, WechatSender

logger = logging.getLogger(__name__)

CHANNEL_NAMES = {
    "wechat": "企业微信",
    "feishu": "飞书",
    "email": "邮件",
}


@dataclass
class ChannelResult:
    channel: str
    success: bool
    latency_ms: Optional[int] = None
    error: Optional[str] = None


@dataclass
class PushResult:
    success: bool
    channel_results: List[ChannelResult] = field(default_factory=list)
    message: Optional[str] = None


class NotificationService:
    """Unified notification service supporting WeChat, Feishu, and Email.

    Usage:
        service = NotificationService(settings)
        # Push a raw file
        await service.push_raw("sources/daily_direction/2026-06-06/...", route_type="report")
        # Push raw content
        await service.send("## Hello", route_type="alert")
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._wechat = WechatSender(settings)
        self._feishu = FeishuSender(settings)
        self._email = EmailSender(settings)

        self._senders: Dict[str, Any] = {
            "wechat": self._wechat,
            "feishu": self._feishu,
            "email": self._email,
        }
        self._available = [ch for ch, s in self._senders.items() if s.is_configured]

        if not self._available:
            logger.warning("No notification channels configured")
        else:
            names = [CHANNEL_NAMES[ch] for ch in self._available]
            logger.info(f"Notification channels: {', '.join(names)}")

    @property
    def available_channels(self) -> List[str]:
        return list(self._available)

    def is_available(self) -> bool:
        return len(self._available) > 0

    def _resolve_channels(self, route_type: Optional[str]) -> List[str]:
        """Return channels allowed for a route type."""
        if route_type is None:
            return list(self._available)

        route_config = get_route_config(route_type)
        if route_config is None:
            logger.warning(f"Unknown route type {route_type}, using all channels")
            return list(self._available)

        configured = getattr(self._settings, route_config["config_attr"], None) or []
        if not configured:
            return list(self._available)

        valid, invalid = split_channels(configured)
        if invalid:
            logger.warning(f"Invalid channels in {route_type}: {', '.join(invalid)}")

        allowed = set(valid)
        return [ch for ch in self._available if ch in allowed]

    async def push_raw(
        self,
        raw_path: str | Path,
        *,
        route_type: Optional[str] = None,
        channels: Optional[List[str]] = None,
        subject: Optional[str] = None,
    ) -> PushResult:
        """Push a raw markdown file to configured channels.

        Args:
            raw_path: Relative or absolute path to the raw markdown file.
            route_type: "report" | "alert" | "system_error" | None for all.
            channels: Override channels to use.
            subject: Email subject override.

        Returns:
            PushResult with per-channel results.
        """
        path = Path(raw_path)
        if not path.is_absolute():
            # Resolve relative to raw_knowledge_dir
            base = getattr(self._settings, "raw_knowledge_dir", Path("./data/knowledge/raw"))
            path = base / path

        if not path.exists():
            return PushResult(
                success=False,
                message=f"Raw file not found: {path}",
            )

        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            return PushResult(
                success=False,
                message=f"Failed to read raw file: {e}",
            )

        # Extract body from frontmatter
        body = self._extract_body(content)
        title = self._extract_title(content) or path.stem

        if not subject:
            date_str = datetime.now().strftime("%Y-%m-%d")
            subject = f"📈 {title} - {date_str}"

        return await self.send(
            body,
            route_type=route_type,
            channels=channels,
            subject=subject,
        )

    async def send(
        self,
        content: str,
        *,
        route_type: Optional[str] = None,
        channels: Optional[List[str]] = None,
        subject: Optional[str] = None,
    ) -> PushResult:
        """Send content to configured channels.

        Args:
            content: Markdown content to send.
            route_type: "report" | "alert" | "system_error" | None for all.
            channels: Override channels to use.
            subject: Email subject override.

        Returns:
            PushResult with per-channel results.
        """
        target_channels = channels if channels is not None else self._resolve_channels(route_type)

        if not target_channels:
            logger.warning("No channels available for notification")
            return PushResult(
                success=False,
                message="No channels available",
            )

        channel_results: List[ChannelResult] = []
        success_count = 0

        for ch in target_channels:
            sender = self._senders.get(ch)
            if not sender or not sender.is_configured:
                logger.warning(f"Channel {ch} not configured, skipping")
                channel_results.append(
                    ChannelResult(channel=ch, success=False, error="Not configured")
                )
                continue

            started = time.monotonic()
            try:
                if ch == "email" and subject:
                    result = sender._send_email(content, subject=subject)
                else:
                    result = sender.send(content)
                latency = int((time.monotonic() - started) * 1000)
                channel_results.append(
                    ChannelResult(channel=ch, success=result, latency_ms=latency)
                )
                if result:
                    success_count += 1
            except Exception as e:
                latency = int((time.monotonic() - started) * 1000)
                logger.error(f"Notification to {ch} failed: {e}")
                channel_results.append(
                    ChannelResult(channel=ch, success=False, latency_ms=latency, error=str(e))
                )

        logger.info(f"Notification done: {success_count}/{len(target_channels)} channels succeeded")

        return PushResult(
            success=success_count > 0,
            channel_results=channel_results,
            message=f"{success_count}/{len(target_channels)} channels succeeded",
        )

    @staticmethod
    def _extract_body(text: str) -> str:
        """Extract markdown body from frontmatter."""
        if text.startswith("---\n"):
            end = text.find("\n---", 4)
            if end != -1:
                body = text[end + 4 :]
                return body.lstrip("\n")
        return text

    @staticmethod
    def _extract_title(text: str) -> Optional[str]:
        """Extract title from frontmatter or first heading."""
        import yaml

        if text.startswith("---\n"):
            end = text.find("\n---", 4)
            if end != -1:
                raw = text[4:end]
                try:
                    fm = yaml.safe_load(raw) or {}
                    return fm.get("title")
                except Exception:
                    pass
        # Fallback: first # heading
        for line in text.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return None


def get_notification_service() -> NotificationService:
    from src.config import settings

    return NotificationService(settings)
