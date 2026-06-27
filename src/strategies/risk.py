"""风控模块：止损、止盈、仓位控制。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional


@dataclass
class RiskConfig:
    """风控配置。"""

    # 止损
    stop_loss_type: Literal["ma20", "fixed"] = "ma20"
    stop_loss_pct: float = 0.08  # 固定止损百分比（0.08 = -8%）
    # 止盈（三段止盈）
    take_profit_levels: list[tuple[float, float]] = field(
        default_factory=lambda: [(0.10, 0.30), (0.20, 0.30), (0.30, 1.0)]
    )
    # 仓位
    max_position_pct: float = 0.20  # 单票最大仓位占比
    max_holdings: int = 5  # 最大持仓数
    # 交易成本
    slippage: float = 0.003  # 滑点 0.3%
    commission_rate: float = 0.00025  # 佣金费率
    min_commission: float = 5.0  # 最低佣金
    stamp_tax_rate: float = 0.0005  # 印花税（卖出）


@dataclass
class Position:
    """持仓信息。"""

    symbol: str
    name: str
    entry_date: str
    entry_price: float  # 实际成交价（含滑点）
    shares: int
    initial_shares: int
    stop_loss_price: float
    ma_period: int = 20
    take_profit_triggered: list[bool] = field(default_factory=list)
    # 已实现盈亏（来自部分止盈）
    realized_pnl: float = 0.0

    def __post_init__(self):
        if not self.take_profit_triggered:
            self.take_profit_triggered = [False] * 3

    @property
    def cost(self) -> float:
        return self.entry_price * self.initial_shares

    @property
    def current_value(self) -> float:
        return self._current_price * self.shares

    @property
    def holding_days(self) -> int:
        return self._holding_days

    def update_price(self, price: float, holding_days: int) -> None:
        self._current_price = price
        self._holding_days = holding_days

    def unrealized_pnl_pct(self) -> float:
        if self.entry_price <= 0:
            return 0.0
        return (self._current_price / self.entry_price - 1) if hasattr(self, "_current_price") else 0.0


def calc_stop_loss_price(
    entry_price: float,
    stop_loss_type: str,
    stop_loss_pct: float,
    ma20_price: Optional[float] = None,
) -> float:
    """计算止损价。"""
    if stop_loss_type == "ma20" and ma20_price is not None and ma20_price > 0:
        return ma20_price
    return entry_price * (1 - stop_loss_pct)


def check_exit(
    position: Position,
    current_price: float,
    current_ma20: Optional[float],
    config: RiskConfig,
) -> tuple[Literal["hold", "stop_loss", "take_profit"], float, int]:
    """检查持仓是否触发止损/止盈。

    Returns:
        (action, exit_price, shares_to_sell)
        - action="hold": 不操作
        - action="stop_loss": 止损，全仓卖出
        - action="take_profit": 止盈，部分或全部卖出
    """
    # 更新止损价（MA20 类型时跟随 MA20 下移）
    if config.stop_loss_type == "ma20" and current_ma20 is not None and current_ma20 > 0:
        position.stop_loss_price = current_ma20

    # 止损检查
    if current_price <= position.stop_loss_price:
        return "stop_loss", current_price, position.shares

    # 止盈检查（三段）
    gain_pct = (current_price / position.entry_price - 1) if position.entry_price > 0 else 0
    for i, (threshold, sell_ratio) in enumerate(config.take_profit_levels):
        if gain_pct >= threshold and not position.take_profit_triggered[i]:
            position.take_profit_triggered[i] = True
            shares_to_sell = int(position.initial_shares * sell_ratio)
            shares_to_sell = min(shares_to_sell, position.shares)
            if shares_to_sell >= position.shares:
                return "take_profit", current_price, position.shares
            return "take_profit", current_price, shares_to_sell

    return "hold", 0.0, 0


def calc_buy_shares(
    capital: float,
    price: float,
    config: RiskConfig,
    current_holdings: int,
) -> int:
    """计算可买入股数（A股100股整数倍）。"""
    if current_holdings >= config.max_holdings:
        return 0
    max_invest = capital * config.max_position_pct
    # 实际买入价含滑点
    buy_price = price * (1 + config.slippage)
    if buy_price <= 0:
        return 0
    raw_shares = int(max_invest / buy_price)
    # A股100股整数倍
    shares = (raw_shares // 100) * 100
    return max(shares, 0)


def calc_sell_cost(amount: float, config: RiskConfig) -> float:
    """计算卖出交易成本（佣金+印花税）。"""
    commission = max(amount * config.commission_rate, config.min_commission)
    stamp_tax = amount * config.stamp_tax_rate
    return commission + stamp_tax


def calc_buy_cost(amount: float, config: RiskConfig) -> float:
    """计算买入交易成本（佣金）。"""
    return max(amount * config.commission_rate, config.min_commission)
