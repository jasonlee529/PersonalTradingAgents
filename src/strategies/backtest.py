"""回测引擎：支持 A 股 T+1、涨跌停、滑点、佣金。

回测流程：
1. 确定股票池（symbols 或市场 TopN）
2. 预加载 K 线并计算因子
3. 遍历交易日：检测信号 → 次日开盘买入 → 检查止损/止盈
4. 计算绩效指标
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import pandas as pd

from src.strategies.factors import compute_factors
from src.strategies.risk import (
    RiskConfig,
    Position,
    calc_buy_cost,
    calc_buy_shares,
    calc_sell_cost,
    check_exit,
)
from src.strategies.registry import get_strategy

logger = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 250


@dataclass
class BacktestConfig:
    """回测配置。"""

    strategy_id: str = "strong_pullback"
    start_date: str = ""
    end_date: str = ""
    symbols: list[str] = field(default_factory=list)  # 为空时用市场 TopN
    max_universe: int = 50  # 市场选股上限
    market: str = "all"
    initial_capital: float = 1_000_000.0
    kline_limit: int = 120  # 每只股票加载的 K 线根数
    strategy_params: dict[str, Any] = field(default_factory=dict)
    risk_config: RiskConfig = field(default_factory=RiskConfig)


@dataclass
class TradeRecord:
    """交易记录。"""

    symbol: str
    name: str
    action: str  # buy | sell_stop | sell_profit
    date: str
    price: float
    shares: int
    amount: float
    cost: float
    pnl: float = 0.0
    pnl_pct: float = 0.0
    holding_days: int = 0
    reason: str = ""


@dataclass
class BacktestResult:
    """回测结果。"""

    config: BacktestConfig
    trades: list[TradeRecord]
    equity_curve: list[dict]  # [{date, equity, cash, holdings_value}]
    metrics: dict[str, Any]
    universe_size: int
    trading_days: int
    error: str = ""


class BacktestEngine:
    """回测引擎。"""

    def __init__(self, collector):
        self.collector = collector

    async def run(self, config: BacktestConfig) -> BacktestResult:
        """执行回测。"""
        strategy = get_strategy(config.strategy_id)
        if strategy is None:
            return BacktestResult(
                config=config, trades=[], equity_curve=[], metrics={},
                universe_size=0, trading_days=0,
                error=f"未知策略: {config.strategy_id}",
            )

        # 1. 确定股票池
        symbols, names = await self._resolve_universe(config)
        if not symbols:
            return BacktestResult(
                config=config, trades=[], equity_curve=[], metrics={},
                universe_size=0, trading_days=0, error="无法确定股票池",
            )

        # 2. 预加载 K 线并计算因子
        kline_cache = await self._preload_klines(symbols, names, config)
        if not kline_cache:
            return BacktestResult(
                config=config, trades=[], equity_curve=[], metrics={},
                universe_size=len(symbols), trading_days=0, error="无法加载K线数据",
            )

        # 3. 收集所有交易日（取交集）
        all_dates: set[str] = set()
        for data in kline_cache.values():
            all_dates.update(data["df"]["date"].tolist())
        trading_dates = sorted(
            d for d in all_dates
            if (not config.start_date or d >= config.start_date)
            and (not config.end_date or d <= config.end_date)
        )

        if len(trading_dates) < 60:
            return BacktestResult(
                config=config, trades=[], equity_curve=[], metrics={},
                universe_size=len(symbols), trading_days=len(trading_dates),
                error=f"交易日不足: {len(trading_dates)}",
            )

        # 4. 执行回测
        trades, equity_curve = self._simulate(
            strategy, kline_cache, trading_dates, config
        )

        # 5. 计算绩效
        metrics = self._calc_metrics(trades, equity_curve, config)

        return BacktestResult(
            config=config,
            trades=trades,
            equity_curve=equity_curve,
            metrics=metrics,
            universe_size=len(symbols),
            trading_days=len(trading_dates),
        )

    async def _resolve_universe(
        self, config: BacktestConfig
    ) -> tuple[list[str], dict[str, str]]:
        """确定股票池。"""
        if config.symbols:
            return list(config.symbols), {s: s for s in config.symbols}

        rows, err = await self.collector.get_market_list()
        if rows is None:
            return [], {}

        candidates: list[dict] = []
        for stock in rows:
            symbol = str(stock.get("symbol", ""))
            if symbol.startswith(("300", "301", "688")):
                continue
            inferred = self.collector._infer_market(symbol)
            if config.market != "all":
                if config.market == "sh" and inferred != "sh":
                    continue
                if config.market == "sz" and inferred != "sz":
                    continue
                if config.market == "bj" and inferred != "bj":
                    continue
            if not stock.get("price") or float(stock.get("price", 0)) <= 0:
                continue
            candidates.append(stock)

        candidates.sort(key=lambda x: float(x.get("turnover") or 0), reverse=True)
        candidates = candidates[: config.max_universe]

        symbols = [str(s["symbol"]) for s in candidates]
        names = {str(s["symbol"]): str(s.get("name", "")) for s in candidates}
        return symbols, names

    async def _preload_klines(
        self, symbols: list[str], names: dict[str, str], config: BacktestConfig
    ) -> dict[str, dict]:
        """预加载 K 线并计算因子。"""
        semaphore = asyncio.Semaphore(10)
        cache: dict[str, dict] = {}

        async def _load(symbol: str):
            async with semaphore:
                try:
                    kline = await self.collector.get_kline(symbol, limit=config.kline_limit)
                    if not kline or len(kline) < 70:
                        return
                    df = pd.DataFrame(kline)
                    df = compute_factors(df)
                    if len(df) < 70:
                        return
                    cache[symbol] = {"df": df, "name": names.get(symbol, "")}
                except Exception as e:
                    logger.debug("加载 %s K线失败: %s", symbol, e)

        await asyncio.gather(*[_load(s) for s in symbols])
        return cache

    def _simulate(
        self,
        strategy,
        kline_cache: dict[str, dict],
        trading_dates: list[str],
        config: BacktestConfig,
    ) -> tuple[list[TradeRecord], list[dict]]:
        """执行回测模拟。"""
        risk = config.risk_config
        capital = config.initial_capital
        positions: dict[str, Position] = {}
        pending_buys: list[dict] = []  # T+1 待买入
        trades: list[TradeRecord] = []
        equity_curve: list[dict] = []

        for i, today in enumerate(trading_dates):
            # T+1：执行昨日挂单的买入
            if pending_buys:
                for order in pending_buys:
                    symbol = order["symbol"]
                    data = kline_cache.get(symbol)
                    if not data:
                        continue
                    df = data["df"]
                    row = df[df["date"] == today]
                    if row.empty:
                        continue
                    open_price = float(row.iloc[0]["open"])
                    prev_close = float(
                        df[df["date"] < today]["close"].iloc[-1]
                    ) if len(df[df["date"] < today]) > 0 else open_price

                    # 涨停不可买
                    if open_price >= prev_close * 1.097:
                        continue

                    buy_price = open_price * (1 + risk.slippage)
                    shares = order["shares"]
                    amount = buy_price * shares
                    cost = calc_buy_cost(amount, risk)
                    capital -= (amount + cost)

                    # 计算止损价
                    ma20_series = df[df["date"] <= today]["ma20"]
                    ma20_val = float(ma20_series.iloc[-1]) if not ma20_series.empty and pd.notna(ma20_series.iloc[-1]) else None

                    from src.strategies.risk import calc_stop_loss_price
                    stop_loss = calc_stop_loss_price(
                        buy_price, risk.stop_loss_type, risk.stop_loss_pct, ma20_val
                    )

                    positions[symbol] = Position(
                        symbol=symbol,
                        name=data["name"],
                        entry_date=today,
                        entry_price=buy_price,
                        shares=shares,
                        initial_shares=shares,
                        stop_loss_price=stop_loss,
                        ma_period=risk.stop_loss_type == "ma20" and 20 or 0,
                    )
                    trades.append(TradeRecord(
                        symbol=symbol, name=data["name"], action="buy",
                        date=today, price=round(buy_price, 3), shares=shares,
                        amount=round(amount, 2), cost=round(cost, 2),
                    ))
                pending_buys = []

            # 检查持仓止损/止盈
            to_remove = []
            for symbol, pos in positions.items():
                data = kline_cache.get(symbol)
                if not data:
                    continue
                df = data["df"]
                row = df[df["date"] == today]
                if row.empty:
                    continue
                current_price = float(row.iloc[0]["close"])
                ma20_series = df[df["date"] <= today]["ma20"]
                current_ma20 = float(ma20_series.iloc[-1]) if not ma20_series.empty and pd.notna(ma20_series.iloc[-1]) else None

                holding_days = i - trading_dates.index(pos.entry_date) if pos.entry_date in trading_dates else 0
                action, exit_price, shares_to_sell = check_exit(pos, current_price, current_ma20, risk)

                if action == "hold":
                    continue

                sell_price = exit_price * (1 - risk.slippage)
                amount = sell_price * shares_to_sell
                cost = calc_sell_cost(amount, risk)
                capital += (amount - cost)

                pnl = (sell_price - pos.entry_price) * shares_to_sell - cost
                pnl_pct = (sell_price / pos.entry_price - 1) * 100 if pos.entry_price > 0 else 0
                pos.realized_pnl += pnl
                pos.shares -= shares_to_sell

                trades.append(TradeRecord(
                    symbol=symbol, name=pos.name,
                    action="sell_stop" if action == "stop_loss" else "sell_profit",
                    date=today, price=round(sell_price, 3), shares=shares_to_sell,
                    amount=round(amount, 2), cost=round(cost, 2),
                    pnl=round(pnl, 2), pnl_pct=round(pnl_pct, 2),
                    holding_days=holding_days,
                    reason="止损" if action == "stop_loss" else "止盈",
                ))

                if pos.shares <= 0:
                    to_remove.append(symbol)

            for s in to_remove:
                del positions[s]

            # 检测今日信号 → 挂单（T+1 次日买入）
            if len(positions) + len(pending_buys) < risk.max_holdings:
                for symbol, data in kline_cache.items():
                    if symbol in positions:
                        continue
                    if any(o["symbol"] == symbol for o in pending_buys):
                        continue
                    if len(positions) + len(pending_buys) >= risk.max_holdings:
                        break

                    df = data["df"]
                    df_up_to = df[df["date"] <= today]
                    if len(df_up_to) < 70:
                        continue
                    # 最后一根必须是 today
                    if df_up_to.iloc[-1]["date"] != today:
                        continue

                    kline_list = df_up_to.to_dict("records")
                    result = strategy.detect(
                        symbol=symbol,
                        name=data["name"],
                        market=self.collector._infer_market(symbol),
                        kline=kline_list,
                        trade_date=today,
                        params=config.strategy_params or None,
                    )
                    if result is None:
                        continue

                    close_price = float(df_up_to.iloc[-1]["close"])
                    shares = calc_buy_shares(capital, close_price, risk, len(positions) + len(pending_buys))
                    if shares > 0:
                        pending_buys.append({"symbol": symbol, "shares": shares})

            # 记录权益曲线
            holdings_value = 0.0
            for symbol, pos in positions.items():
                data = kline_cache.get(symbol)
                if data:
                    df = data["df"]
                    row = df[df["date"] == today]
                    if not row.empty:
                        holdings_value += float(row.iloc[0]["close"]) * pos.shares

            equity_curve.append({
                "date": today,
                "equity": round(capital + holdings_value, 2),
                "cash": round(capital, 2),
                "holdings_value": round(holdings_value, 2),
                "positions": len(positions),
            })

        return trades, equity_curve

    @staticmethod
    def _calc_metrics(
        trades: list[TradeRecord],
        equity_curve: list[dict],
        config: BacktestConfig,
    ) -> dict[str, Any]:
        """计算绩效指标。"""
        if not equity_curve:
            return {}

        initial = config.initial_capital
        final = equity_curve[-1]["equity"]
        total_return = (final / initial - 1) * 100 if initial > 0 else 0

        trading_days = len(equity_curve)
        annualized = (
            ((final / initial) ** (TRADING_DAYS_PER_YEAR / trading_days) - 1) * 100
            if initial > 0 and trading_days > 0 and final > 0
            else 0
        )

        # 最大回撤
        peak = initial
        max_drawdown = 0.0
        for point in equity_curve:
            eq = point["equity"]
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100 if peak > 0 else 0
            if dd > max_drawdown:
                max_drawdown = dd

        # 波动率（日收益率标准差 × 年化）
        equities = [p["equity"] for p in equity_curve]
        if len(equities) > 1:
            returns = pd.Series(equities).pct_change().dropna()
            volatility = float(returns.std() * (TRADING_DAYS_PER_YEAR ** 0.5) * 100) if len(returns) > 0 else 0
        else:
            volatility = 0

        # 交易统计
        sell_trades = [t for t in trades if t.action.startswith("sell")]
        win_trades = [t for t in sell_trades if t.pnl > 0]
        lose_trades = [t for t in sell_trades if t.pnl <= 0]
        win_rate = (len(win_trades) / len(sell_trades) * 100) if sell_trades else 0.0

        total_profit = sum(t.pnl for t in win_trades)
        total_loss = abs(sum(t.pnl for t in lose_trades))
        profit_loss_ratio = (total_profit / total_loss) if total_loss > 0 else 0.0

        avg_holding_days = (
            sum(t.holding_days for t in sell_trades) / len(sell_trades)
            if sell_trades else 0.0
        )

        return {
            "initial_capital": round(initial, 2),
            "final_equity": round(final, 2),
            "total_return_pct": round(total_return, 2),
            "annualized_return_pct": round(annualized, 2),
            "max_drawdown_pct": round(max_drawdown, 2),
            "volatility_pct": round(volatility, 2),
            "total_trades": len(sell_trades),
            "win_rate_pct": round(win_rate, 2),
            "profit_loss_ratio": round(profit_loss_ratio, 2),
            "avg_holding_days": round(avg_holding_days, 1),
            "buy_count": len([t for t in trades if t.action == "buy"]),
            "sell_count": len(sell_trades),
        }
