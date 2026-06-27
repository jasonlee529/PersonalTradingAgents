"""量化策略 API。

提供策略列表与策略全市场扫描接口。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.api.dependencies import get_services, AppServices
from src.strategies import list_strategies
from src.strategies.scanner import StrategyScanner

router = APIRouter(prefix="/strategies", tags=["strategies"])


class StrategyParamInfo(BaseModel):
    name: str
    default: Any
    description: str = ""


class StrategyInfo(BaseModel):
    id: str
    name: str
    description: str
    available: bool = True
    params: list[StrategyParamInfo] = []


class StrategyListResponse(BaseModel):
    strategies: list[StrategyInfo]


class StrategyMatchItem(BaseModel):
    symbol: str
    name: str = ""
    market: str = ""
    trade_date: str = ""
    strategy_id: str = ""
    strategy_name: str = ""
    rally_pct: Optional[float] = None
    peak_price: Optional[float] = None
    peak_date: Optional[str] = None
    ma_period: Optional[int] = None
    touch_date: Optional[str] = None
    latest_price: Optional[float] = None
    latest_volume: Optional[int] = None
    rally_avg_volume: Optional[int] = None
    pullback_avg_volume: Optional[int] = None
    contraction_ratio: Optional[float] = None
    expansion_ratio: Optional[float] = None
    bounce_up: bool = False
    description: str = ""


class StrategyScanResponse(BaseModel):
    strategy_id: str
    trade_date: str
    market: str
    total: int
    limit: int
    offset: int
    items: list[StrategyMatchItem]
    error: str = ""


# 策略参数人类可读说明
_PARAM_DESCRIPTIONS = {
    "rally_days": "上涨回看窗口（交易日）",
    "min_rally_pct": "最小涨幅（%）",
    "ma_period": "回踩均线周期",
    "pullback_tolerance": "触及均线容差（小数，0.02=2%）",
    "contraction_ratio": "缩量比例上限（回调均量/上涨均量）",
    "expansion_ratio": "放量比例下限（今日量/回调均量）",
    "min_pullback_days": "峰值后最少回调天数",
    "require_bounce_up": "是否要求今日收阳",
}


def _strategy_to_info(strategy) -> StrategyInfo:
    params = [
        StrategyParamInfo(
            name=k,
            default=v,
            description=_PARAM_DESCRIPTIONS.get(k, ""),
        )
        for k, v in strategy.default_params.items()
    ]
    return StrategyInfo(
        id=strategy.id,
        name=strategy.name,
        description=strategy.description,
        available=True,
        params=params,
    )


@router.get("", response_model=StrategyListResponse)
async def list_all_strategies():
    """返回所有可用量化策略。"""
    strategies = [_strategy_to_info(s) for s in list_strategies()]
    return StrategyListResponse(strategies=strategies)


def _matches_query(item: dict, q: str) -> bool:
    if not q:
        return True
    needle = q.strip().lower()
    return (
        needle in str(item.get("symbol", "")).lower()
        or needle in str(item.get("name", "")).lower()
    )


@router.get("/{strategy_id}/scan", response_model=StrategyScanResponse)
async def scan_strategy(
    strategy_id: str,
    trade_date: str = Query(default_factory=lambda: datetime.now().strftime("%Y-%m-%d")),
    market: str = Query("all", description="市场筛选: all | sh | sz | bj"),
    q: str = Query("", description="代码或名称搜索"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    # 策略参数（均可选，覆盖默认值）
    rally_days: Optional[int] = Query(None, ge=5, le=60),
    min_rally_pct: Optional[float] = Query(None, ge=0, le=500),
    ma_period: Optional[int] = Query(None, ge=2, le=60),
    pullback_tolerance: Optional[float] = Query(None, ge=0, le=0.2),
    contraction_ratio: Optional[float] = Query(None, ge=0, le=2),
    expansion_ratio: Optional[float] = Query(None, ge=1, le=10),
    min_pullback_days: Optional[int] = Query(None, ge=1, le=20),
    require_bounce_up: Optional[bool] = Query(None),
    max_stocks: int = Query(200, ge=10, le=1000, description="扫描股票数量上限"),
    services: AppServices = Depends(get_services),
):
    """运行指定策略的全市场扫描。"""
    params: dict[str, Any] = {}
    if rally_days is not None:
        params["rally_days"] = rally_days
    if min_rally_pct is not None:
        params["min_rally_pct"] = min_rally_pct
    if ma_period is not None:
        params["ma_period"] = ma_period
    if pullback_tolerance is not None:
        params["pullback_tolerance"] = pullback_tolerance
    if contraction_ratio is not None:
        params["contraction_ratio"] = contraction_ratio
    if expansion_ratio is not None:
        params["expansion_ratio"] = expansion_ratio
    if min_pullback_days is not None:
        params["min_pullback_days"] = min_pullback_days
    if require_bounce_up is not None:
        params["require_bounce_up"] = require_bounce_up

    scanner = StrategyScanner(services.collector)
    matches, error = await scanner.scan(
        strategy_id=strategy_id,
        trade_date=trade_date,
        market=market,
        params=params or None,
        max_stocks=max_stocks,
    )

    if matches is None:
        matches = []

    filtered = [item for item in matches if _matches_query(item, q)]
    total = len(filtered)
    page = filtered[offset:offset + limit]

    return StrategyScanResponse(
        strategy_id=strategy_id,
        trade_date=trade_date,
        market=market,
        total=total,
        limit=limit,
        offset=offset,
        items=[StrategyMatchItem(**item) for item in page],
        error=error,
    )


# ---- 回测 ----

class BacktestRequest(BaseModel):
    """回测请求体。"""
    strategy_id: str = "strong_pullback"
    start_date: str = ""
    end_date: str = ""
    symbols: list[str] = []
    max_universe: int = 50
    market: str = "all"
    initial_capital: float = 1_000_000
    kline_limit: int = 120
    strategy_params: dict[str, Any] = {}
    # 风控
    stop_loss_type: str = "ma20"
    stop_loss_pct: float = 0.08
    max_position_pct: float = 0.20
    max_holdings: int = 5
    slippage: float = 0.003
    commission_rate: float = 0.00025
    stamp_tax_rate: float = 0.0005


class BacktestTradeItem(BaseModel):
    symbol: str
    name: str = ""
    action: str
    date: str
    price: float
    shares: int
    amount: float
    cost: float
    pnl: float = 0.0
    pnl_pct: float = 0.0
    holding_days: int = 0
    reason: str = ""


class BacktestEquityPoint(BaseModel):
    date: str
    equity: float
    cash: float
    holdings_value: float
    positions: int


class BacktestMetrics(BaseModel):
    initial_capital: float = 0
    final_equity: float = 0
    total_return_pct: float = 0
    annualized_return_pct: float = 0
    max_drawdown_pct: float = 0
    volatility_pct: float = 0
    total_trades: int = 0
    win_rate_pct: float = 0
    profit_loss_ratio: float = 0
    avg_holding_days: float = 0
    buy_count: int = 0
    sell_count: int = 0


class BacktestResponse(BaseModel):
    strategy_id: str
    universe_size: int
    trading_days: int
    metrics: BacktestMetrics
    trades: list[BacktestTradeItem]
    equity_curve: list[BacktestEquityPoint]
    error: str = ""


@router.post("/backtest", response_model=BacktestResponse)
async def run_backtest(
    req: BacktestRequest,
    services: AppServices = Depends(get_services),
):
    """运行策略历史回测。"""
    from src.strategies.backtest import BacktestConfig, BacktestEngine
    from src.strategies.risk import RiskConfig

    risk_config = RiskConfig(
        stop_loss_type=req.stop_loss_type,  # type: ignore
        stop_loss_pct=req.stop_loss_pct,
        max_position_pct=req.max_position_pct,
        max_holdings=req.max_holdings,
        slippage=req.slippage,
        commission_rate=req.commission_rate,
        stamp_tax_rate=req.stamp_tax_rate,
    )
    bt_config = BacktestConfig(
        strategy_id=req.strategy_id,
        start_date=req.start_date,
        end_date=req.end_date,
        symbols=req.symbols,
        max_universe=req.max_universe,
        market=req.market,
        initial_capital=req.initial_capital,
        kline_limit=req.kline_limit,
        strategy_params=req.strategy_params,
        risk_config=risk_config,
    )

    engine = BacktestEngine(services.collector)
    result = await engine.run(bt_config)

    return BacktestResponse(
        strategy_id=req.strategy_id,
        universe_size=result.universe_size,
        trading_days=result.trading_days,
        metrics=BacktestMetrics(**result.metrics),
        trades=[BacktestTradeItem(**{
            "symbol": t.symbol, "name": t.name, "action": t.action,
            "date": t.date, "price": t.price, "shares": t.shares,
            "amount": t.amount, "cost": t.cost, "pnl": t.pnl,
            "pnl_pct": t.pnl_pct, "holding_days": t.holding_days,
            "reason": t.reason,
        }) for t in result.trades],
        equity_curve=[BacktestEquityPoint(**p) for p in result.equity_curve],
        error=result.error,
    )
