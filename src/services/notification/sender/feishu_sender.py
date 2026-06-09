"""Feishu (Lark) webhook sender."""

import base64
import hashlib
import hmac
import logging
import time
from typing import Any, Dict, Optional

import requests

from .base import BaseSender
from ..formatters import chunk_content_by_max_bytes, format_feishu_markdown

logger = logging.getLogger(__name__)


class FeishuSender(BaseSender):
    """Send messages via Feishu webhook robot."""

    def __init__(self, settings: Any):
        self._url = getattr(settings, "feishu_webhook_url", None) or ""
        self._secret = (getattr(settings, "feishu_webhook_secret", None) or "").strip()
        self._keyword = (getattr(settings, "feishu_webhook_keyword", None) or "").strip()
        self._max_bytes = getattr(settings, "feishu_max_bytes", 20000)
        self._verify_ssl = getattr(settings, "webhook_verify_ssl", True)

    @property
    def is_configured(self) -> bool:
        return bool(self._url)

    def _keyword_prefix(self) -> str:
        return f"{self._keyword}\n" if self._keyword else ""

    def _apply_keyword(self, content: str) -> str:
        prefix = self._keyword_prefix()
        return f"{prefix}{content}" if prefix else content

    def _build_security(self) -> Dict[str, str]:
        if not self._secret:
            return {}
        timestamp = str(int(time.time()))
        string_to_sign = f"{timestamp}\n{self._secret}"
        sign = base64.b64encode(
            hmac.new(
                string_to_sign.encode("utf-8"),
                digestmod=hashlib.sha256,
            ).digest()
        ).decode("utf-8")
        return {"timestamp": timestamp, "sign": sign}

    def send(self, content: str, *, timeout_seconds: Optional[float] = None) -> bool:
        if not self._url:
            logger.warning("Feishu webhook not configured, skipping")
            return False

        formatted = format_feishu_markdown(content)
        max_bytes = self._max_bytes
        keyword_overhead = len(self._keyword_prefix().encode("utf-8"))
        effective_max = max_bytes - keyword_overhead

        if effective_max <= 0:
            logger.error("Feishu keyword too long")
            return False

        content_bytes = len(formatted.encode("utf-8")) + keyword_overhead
        if content_bytes > max_bytes:
            logger.info(f"Feishu message too long ({content_bytes} bytes), chunking")
            return self._send_chunked(formatted, effective_max)

        try:
            return self._send_message(formatted, timeout_seconds=timeout_seconds)
        except Exception as e:
            logger.error(f"Feishu send failed: {e}")
            return False

    def _send_message(self, content: str, *, timeout_seconds: Optional[float] = None) -> bool:
        prepared = self._apply_keyword(content)
        security = self._build_security()

        card_payload = {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": "今日方向报告"}
                },
                "elements": [
                    {"tag": "div", "text": {"tag": "lark_md", "content": prepared}}
                ],
            },
        }

        if self._post(card_payload, security, timeout_seconds):
            return True

        text_payload = {
            "msg_type": "text",
            "content": {"text": prepared},
        }
        return self._post(text_payload, security, timeout_seconds)

    def _post(self, payload: dict, security: dict, timeout_seconds: Optional[float]) -> bool:
        request_payload = {**payload, **security}
        response = requests.post(
            self._url,
            json=request_payload,
            timeout=timeout_seconds or 30,
            verify=self._verify_ssl,
        )
        if response.status_code == 200:
            result = response.json()
            code = result.get("code") if "code" in result else result.get("StatusCode")
            if code == 0:
                logger.info("Feishu message sent successfully")
                return True
            logger.error(f"Feishu API error [code={code}]: {result}")
        else:
            logger.error(f"Feishu HTTP error: {response.status_code}")
        return False

    def _send_chunked(self, content: str, max_bytes: int) -> bool:
        chunks = chunk_content_by_max_bytes(content, max_bytes, add_page_marker=True)
        success_count = 0
        for i, chunk in enumerate(chunks):
            if self._send_message(chunk):
                success_count += 1
            else:
                logger.error(f"Feishu chunk {i+1}/{len(chunks)} failed")
            if i < len(chunks) - 1:
                time.sleep(1)
        return success_count == len(chunks)
