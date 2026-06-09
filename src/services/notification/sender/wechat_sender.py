"""WeChat Work webhook sender."""

import logging
import time
from typing import Any, Optional

import requests

from .base import BaseSender
from ..formatters import chunk_content_by_max_bytes

logger = logging.getLogger(__name__)

WECHAT_IMAGE_MAX_BYTES = 2 * 1024 * 1024


class WechatSender(BaseSender):
    """Send messages via WeChat Work webhook robot."""

    def __init__(self, settings: Any):
        self._url = getattr(settings, "wechat_webhook_url", None) or ""
        self._max_bytes = getattr(settings, "wechat_max_bytes", 4000)
        self._msg_type = getattr(settings, "wechat_msg_type", "markdown")
        self._verify_ssl = getattr(settings, "webhook_verify_ssl", True)

    @property
    def is_configured(self) -> bool:
        return bool(self._url)

    def send(self, content: str, *, timeout_seconds: Optional[float] = None) -> bool:
        if not self._url:
            logger.warning("WeChat webhook not configured, skipping")
            return False

        if self._msg_type == "text":
            max_bytes = min(self._max_bytes, 2000)
        else:
            max_bytes = self._max_bytes

        content_bytes = len(content.encode("utf-8"))
        if content_bytes > max_bytes:
            logger.info(f"WeChat message too long ({content_bytes} bytes), chunking")
            return self._send_chunked(content, max_bytes)

        try:
            return self._send_message(content, timeout_seconds=timeout_seconds)
        except Exception as e:
            logger.error(f"WeChat send failed: {e}")
            return False

    def _send_message(self, content: str, *, timeout_seconds: Optional[float] = None) -> bool:
        payload = self._gen_payload(content)
        response = requests.post(
            self._url,
            json=payload,
            timeout=timeout_seconds or 10,
            verify=self._verify_ssl,
        )
        if response.status_code == 200:
            result = response.json()
            if result.get("errcode") == 0:
                logger.info("WeChat message sent successfully")
                return True
            logger.error(f"WeChat API error: {result}")
        else:
            logger.error(f"WeChat HTTP error: {response.status_code}")
        return False

    def _send_chunked(self, content: str, max_bytes: int) -> bool:
        chunks = chunk_content_by_max_bytes(content, max_bytes, add_page_marker=True)
        success_count = 0
        for i, chunk in enumerate(chunks):
            if self._send_message(chunk):
                success_count += 1
            else:
                logger.error(f"WeChat chunk {i+1}/{len(chunks)} failed")
            if i < len(chunks) - 1:
                time.sleep(1)
        return success_count == len(chunks)

    def _gen_payload(self, content: str) -> dict:
        if self._msg_type == "text":
            return {"msgtype": "text", "text": {"content": content}}
        return {"msgtype": "markdown", "markdown": {"content": content}}
