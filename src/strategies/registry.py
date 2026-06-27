"""策略注册表。"""

from __future__ import annotations

from typing import Optional

from src.strategies.base import BaseStrategy
from src.strategies.strong_pullback import StrongPullbackStrategy
from src.strategies.volume_pullback import VolumePullbackStrategy

_REGISTRY: dict[str, BaseStrategy] = {}


def _register(strategy: BaseStrategy) -> None:
    _REGISTRY[strategy.id] = strategy


_register(VolumePullbackStrategy())
_register(StrongPullbackStrategy())


def list_strategies() -> list[BaseStrategy]:
    """返回所有已注册策略。"""
    return list(_REGISTRY.values())


def get_strategy(strategy_id: str) -> Optional[BaseStrategy]:
    """按 id 获取策略。"""
    return _REGISTRY.get(strategy_id)
