"""量化选股策略模块。

提供可扩展的策略框架，首期实现"放量回踩"形态策略。
"""

from src.strategies.registry import list_strategies, get_strategy
from src.strategies.scanner import StrategyScanner

__all__ = ["list_strategies", "get_strategy", "StrategyScanner"]
