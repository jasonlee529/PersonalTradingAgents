"""Base class for notification senders."""

import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


class BaseSender(ABC):
    """Abstract base for all notification senders."""

    @abstractmethod
    def send(self, content: str, *, timeout_seconds: Optional[float] = None) -> bool:
        """Send content to the channel. Returns True on success."""
        ...

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Whether this sender has valid configuration."""
        ...
