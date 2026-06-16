from datetime import datetime

from fastapi import APIRouter, Depends, Query

from src.api.dependencies import get_services, AppServices
from src.api.models import (
    QuoteResponse, KlineResponse, KlineRecord, FundamentalsResponse,
    StockSnapshotResponse, NewsItem, AnnouncementItem, ResearchReportItem,
    IndicatorResponse, LimitUpStockItem, LimitUpStockListResponse,
)
from src.data.collector import DEFAULT_KLINE_LIMIT

router = APIRouter(prefix="/stocks", tags=["stocks"])


def _fundamentals_response(symbol: str, data: dict | None) -> FundamentalsResponse:
    raw = dict(data or {})
    raw.setdefault("symbol", symbol)
    for key in ("pe_ttm", "pb", "roe", "revenue_growth", "profit_growth", "debt_ratio"):
        if key not in raw:
            continue
        try:
            raw[key] = float(raw[key]) if raw[key] not in ("", None, "-") else None
        except (TypeError, ValueError):
            raw[key] = None
    return FundamentalsResponse(**raw)


def _matches_query(item: dict, q: str) -> bool:
    if not q:
        return True
    needle = q.strip().lower()
    return needle in str(item.get("symbol", "")).lower() or needle in str(item.get("name", "")).lower()


class MarketStockItem(dict):
    pass


class MarketListResponse(dict):
    pass


@router.get("/market-list")
async def list_market_stocks(
    trade_date: str = Query(default_factory=lambda: datetime.now().strftime("%Y-%m-%d")),
    market: str = Query("all", description="市场筛选: all | sh | sz"),
    q: str = Query("", description="代码或名称搜索"),
    sort: str = Query("change_pct_desc", description="排序: change_pct_desc/asc, turnover_desc/asc, price_desc/asc"),
    limit: int = Query(200, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    refresh: bool = Query(False, description="是否强制刷新（重新抓取远程数据）"),
    services: AppServices = Depends(get_services),
):
    """获取全市场股票列表及当日行情数据。数据自动保存到本地文件。"""
    rows, error = await services.collector.get_market_list(
        trade_date=trade_date,
        refresh=refresh,
    )
    if rows is None:
        rows = []

    filtered = [item for item in rows if _matches_query(item, q)]
    if market == "sh":
        filtered = [item for item in filtered if str(item.get("symbol", "")).startswith("6")]
    elif market == "sz":
        filtered = [item for item in filtered if not str(item.get("symbol", "")).startswith("6")]

    sort_parts = sort.split("_")
    sort_key_base = "_".join(sort_parts[:-1])
    sort_order = sort_parts[-1] if sort_parts else "desc"

    def _safe_num(item, key):
        v = item.get(key)
        try:
            return float(v) if v not in (None, "", "-") else 0.0
        except (TypeError, ValueError):
            return 0.0

    if sort_key_base == "change_pct":
        filtered.sort(key=lambda x: _safe_num(x, "change_pct"), reverse=sort_order == "desc")
    elif sort_key_base == "turnover":
        filtered.sort(key=lambda x: _safe_num(x, "turnover"), reverse=sort_order == "desc")
    elif sort_key_base == "price":
        filtered.sort(key=lambda x: _safe_num(x, "price"), reverse=sort_order == "desc")
    elif sort_key_base == "volume":
        filtered.sort(key=lambda x: _safe_num(x, "volume"), reverse=sort_order == "desc")

    total = len(filtered)
    page = filtered[offset:offset + limit]
    return {
        "trade_date": trade_date,
        "market": market,
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": page,
        "error": error,
    }


@router.post("/market-list/refresh")
async def refresh_market_list(
    trade_date: str = Query(default_factory=lambda: datetime.now().strftime("%Y-%m-%d")),
    services: AppServices = Depends(get_services),
):
    """强制刷新全市场数据（从远程重新抓取并保存到本地）。"""
    rows, error = await services.collector.get_market_list(
        trade_date=trade_date,
        refresh=True,
    )
    return {
        "trade_date": trade_date,
        "total": len(rows) if rows else 0,
        "status": "ok" if rows else "error",
        "error": error,
    }


@router.get("/limit-up-filtered")
async def list_limit_up_filtered(
    trade_date: str = Query(default_factory=lambda: datetime.now().strftime("%Y-%m-%d")),
    market: str = Query("all"),
    q: str = Query(""),
    min_change_pct: float = Query(9.5, ge=0, le=30, description="最小涨跌幅阈值(%)"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    services: AppServices = Depends(get_services),
):
    """从全市场行情数据中筛选出涨停股。数据优先从本地文件读取。"""
    rows, error = await services.collector.get_limit_up_from_market_list(
        trade_date=trade_date,
        market=market,
        min_change_pct=min_change_pct,
    )
    if rows is None:
        rows = []
    filtered = [item for item in rows if _matches_query(item, q)]
    filtered.sort(key=lambda x: float(x.get("change_pct") or 0), reverse=True)
    total = len(filtered)
    page = filtered[offset:offset + limit]
    return LimitUpStockListResponse(
        trade_date=trade_date,
        market=market,
        total=total,
        limit=limit,
        offset=offset,
        items=[LimitUpStockItem(**item) for item in page],
        error=error,
    )


@router.get("/limit-up", response_model=LimitUpStockListResponse)
async def list_limit_up_stocks(
    trade_date: str = Query(default_factory=lambda: datetime.now().strftime("%Y-%m-%d")),
    market: str = "all",
    q: str = "",
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    services: AppServices = Depends(get_services),
):
    rows, error = await services.collector.get_limit_up_stocks(trade_date=trade_date, market=market)
    if rows is None:
        rows = []
    filtered = [item for item in rows if _matches_query(item, q)]
    total = len(filtered)
    page = filtered[offset:offset + limit]
    return LimitUpStockListResponse(
        trade_date=trade_date,
        market=market,
        total=total,
        limit=limit,
        offset=offset,
        items=[LimitUpStockItem(**item) for item in page],
        error=error,
    )


@router.get("/{symbol}/quote", response_model=QuoteResponse)
async def get_quote(symbol: str, services: AppServices = Depends(get_services)):
    quote = await services.collector.get_quote(symbol)
    if not quote:
        return QuoteResponse(symbol=symbol, price=0, open=0, high=0, low=0, prev_close=0, volume=0, turnover=0, change_pct=0)
    return QuoteResponse(**quote)


@router.get("/{symbol}/kline", response_model=KlineResponse)
async def get_kline(
    symbol: str,
    period: str = "1d",
    limit: int = DEFAULT_KLINE_LIMIT,
    services: AppServices = Depends(get_services),
):
    data = await services.collector.get_kline(symbol, period=period, limit=limit)
    records = [KlineRecord(**r) for r in (data or [])]
    return KlineResponse(symbol=symbol, period=period, data=records)


@router.get("/{symbol}/fundamentals", response_model=FundamentalsResponse)
async def get_fundamentals(symbol: str, services: AppServices = Depends(get_services)):
    data = await services.collector.get_fundamentals(symbol) or {}
    return _fundamentals_response(symbol, data)


@router.get("/{symbol}/indicators", response_model=IndicatorResponse)
async def get_indicators(symbol: str, period: str = "1d", services: AppServices = Depends(get_services)):
    data = await services.collector.get_indicators(symbol, period=period)
    return IndicatorResponse(symbol=symbol, indicators=data or {})


@router.get("/{symbol}/news")
async def get_news(symbol: str, limit: int = 20, services: AppServices = Depends(get_services)):
    items = await services.news_collector.get_news(symbol, limit=limit)
    return [NewsItem(**i.model_dump()) for i in items]


@router.get("/{symbol}/announcements")
async def get_announcements(symbol: str, limit: int = 10, services: AppServices = Depends(get_services)):
    items = await services.news_collector.get_announcements(symbol, limit=limit)
    return [AnnouncementItem(**i.model_dump()) for i in items]


@router.get("/{symbol}/research-reports")
async def get_research_reports(symbol: str, limit: int = 10, services: AppServices = Depends(get_services)):
    items = await services.news_collector.get_research_reports(symbol, limit=limit)
    return [ResearchReportItem(**i.model_dump()) for i in items]


@router.get("/{symbol}/snapshot", response_model=StockSnapshotResponse)
async def get_snapshot(symbol: str, services: AppServices = Depends(get_services)):
    snapshot = await services.collector.get_full_snapshot(symbol)
    news = await services.news_collector.get_news(symbol, limit=10)
    announcements = await services.news_collector.get_announcements(symbol, limit=5)
    reports = await services.news_collector.get_research_reports(symbol, limit=5)

    quote_data = snapshot.get("quote")
    quote = QuoteResponse(**quote_data) if quote_data else None

    kline_data = snapshot.get("kline", [])
    kline = [KlineRecord(**r) for r in kline_data]

    fund_data = snapshot.get("fundamentals") or {}
    fundamentals = _fundamentals_response(symbol, fund_data) if fund_data else None

    ind_data = snapshot.get("indicators")
    indicators = IndicatorResponse(symbol=symbol, indicators=ind_data) if ind_data else None

    return StockSnapshotResponse(
        symbol=symbol,
        quote=quote,
        kline=kline,
        fundamentals=fundamentals,
        indicators=indicators,
        news=[NewsItem(**i.model_dump()) for i in news],
        announcements=[AnnouncementItem(**i.model_dump()) for i in announcements],
        research_reports=[ResearchReportItem(**i.model_dump()) for i in reports],
    )
