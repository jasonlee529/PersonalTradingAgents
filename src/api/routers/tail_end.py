"""尾盘策略监控 API。

提供尾盘时段多维度筛选接口。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.api.dependencies import get_services, AppServices
from src.strategies.tail_end_monitor import TailEndMonitor

router = APIRouter(prefix="/tail-end", tags=["tail-end"])


class TailEndItem(BaseModel):
    symbol: str
    name: str = ""
    market: str = ""
    price: float = 0.0
    change_pct: float = 0.0
    turnover_rate: Optional[float] = None
    total_market_cap: Optional[float] = None
    volume_ratio: Optional[float] = None
    change_since_1430: Optional[float] = None
    above_vwap: bool = False
    recent_limit_up: bool = False
    limit_up_date: str = ""
    kline_3d: list[dict] = []


class TailEndScanResponse(BaseModel):
    total: int
    items: list[TailEndItem]
    scan_time: str
    error: str = ""


@router.get("/scan", response_model=TailEndScanResponse)
async def scan_tail_end(
    trade_date: str = Query(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"), description="交易日 (YYYY-MM-DD)"),
    turnover_min: float = Query(6.0, ge=0, le=100, description="换手率下限(%)"),
    turnover_max: float = Query(15.0, ge=0, le=100, description="换手率上限(%)"),
    mcap_min: float = Query(50.0, ge=0, description="市值下限(亿)"),
    mcap_max: float = Query(300.0, ge=0, description="市值上限(亿)"),
    change_min: float = Query(3.0, ge=-20, le=20, description="14:30后涨幅下限(%)"),
    change_max: float = Query(6.0, ge=-20, le=20, description="14:30后涨幅上限(%)"),
    vol_ratio_min: float = Query(2.0, ge=0, description="量比下限"),
    vol_ratio_max: float = Query(5.0, ge=0, description="量比上限"),
    q: str = Query("", description="搜索代码或名称"),
    services: AppServices = Depends(get_services),
):
    """执行尾盘策略扫描。"""
    monitor = TailEndMonitor(services.collector)
    items, error = await monitor.scan(
        turnover_min=turnover_min,
        turnover_max=turnover_max,
        mcap_min=mcap_min,
        mcap_max=mcap_max,
        change_min=change_min,
        change_max=change_max,
        vol_ratio_min=vol_ratio_min,
        vol_ratio_max=vol_ratio_max,
        q=q,
        trade_date=trade_date,
    )

    return TailEndScanResponse(
        total=len(items),
        items=[TailEndItem(**item) for item in items],
        scan_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        error=error,
    )
