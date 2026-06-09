"""Email SMTP sender."""

import logging
from datetime import datetime
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Any, List, Optional

import smtplib

from .base import BaseSender
from ..formatters import markdown_to_html_document

logger = logging.getLogger(__name__)

SMTP_CONFIGS = {
    "qq.com": {"server": "smtp.qq.com", "port": 465, "ssl": True},
    "foxmail.com": {"server": "smtp.qq.com", "port": 465, "ssl": True},
    "163.com": {"server": "smtp.163.com", "port": 465, "ssl": True},
    "126.com": {"server": "smtp.126.com", "port": 465, "ssl": True},
    "gmail.com": {"server": "smtp.gmail.com", "port": 587, "ssl": False},
    "outlook.com": {"server": "smtp-mail.outlook.com", "port": 587, "ssl": False},
    "hotmail.com": {"server": "smtp-mail.outlook.com", "port": 587, "ssl": False},
    "live.com": {"server": "smtp-mail.outlook.com", "port": 587, "ssl": False},
    "sina.com": {"server": "smtp.sina.com", "port": 465, "ssl": True},
    "sohu.com": {"server": "smtp.sohu.com", "port": 465, "ssl": True},
    "aliyun.com": {"server": "smtp.aliyun.com", "port": 465, "ssl": True},
    "139.com": {"server": "smtp.139.com", "port": 465, "ssl": True},
}


class EmailSender(BaseSender):
    """Send messages via SMTP email."""

    def __init__(self, settings: Any):
        self._sender = getattr(settings, "email_sender", None) or ""
        self._sender_name = getattr(settings, "email_sender_name", "TradingAgents")
        self._password = getattr(settings, "email_password", None) or ""
        receivers = getattr(settings, "email_receivers", None)
        if isinstance(receivers, str):
            receivers = [r.strip() for r in receivers.split(",") if r.strip()]
        self._receivers = receivers or ([self._sender] if self._sender else [])

    @property
    def is_configured(self) -> bool:
        return bool(self._sender and self._password)

    def send(self, content: str, *, timeout_seconds: Optional[float] = None) -> bool:
        return self._send_email(content, timeout_seconds=timeout_seconds)

    def _send_email(
        self,
        content: str,
        subject: Optional[str] = None,
        receivers: Optional[List[str]] = None,
        *,
        timeout_seconds: Optional[float] = None,
    ) -> bool:
        if not self._sender or not self._password:
            logger.warning("Email not configured, skipping")
            return False

        sender = self._sender
        password = self._password
        receivers = receivers or self._receivers
        server: Optional[smtplib.SMTP] = None

        try:
            if subject is None:
                date_str = datetime.now().strftime("%Y-%m-%d")
                subject = f"📈 TradingAgents 报告 - {date_str}"

            html_content = markdown_to_html_document(content)

            msg = MIMEMultipart("alternative")
            msg["Subject"] = Header(subject, "utf-8")
            msg["From"] = formataddr((str(Header(str(self._sender_name), "utf-8")), sender))
            msg["To"] = ", ".join(receivers)

            msg.attach(MIMEText(content, "plain", "utf-8"))
            msg.attach(MIMEText(html_content, "html", "utf-8"))

            domain = sender.split("@")[-1].lower()
            smtp_config = SMTP_CONFIGS.get(domain)

            if smtp_config:
                smtp_server = smtp_config["server"]
                smtp_port = smtp_config["port"]
                use_ssl = smtp_config["ssl"]
                logger.info(f"Auto-detected SMTP: {domain} -> {smtp_server}:{smtp_port}")
            else:
                smtp_server = f"smtp.{domain}"
                smtp_port = 465
                use_ssl = True
                logger.warning(f"Unknown email domain {domain}, trying {smtp_server}:{smtp_port}")

            if use_ssl:
                server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=timeout_seconds or 30)
            else:
                server = smtplib.SMTP(smtp_server, smtp_port, timeout=timeout_seconds or 30)
                server.starttls()

            server.login(sender, password)
            server.send_message(msg)

            logger.info(f"Email sent successfully to: {receivers}")
            return True

        except smtplib.SMTPAuthenticationError:
            logger.error("Email auth failed, check sender/password")
            return False
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return False
        finally:
            if server:
                try:
                    server.quit()
                except Exception:
                    try:
                        server.close()
                    except Exception:
                        pass
