from fastapi import APIRouter, Depends

from src.api.dependencies import get_services, AppServices
from src.api.models import (
    QuoteResponse, KlineResponse, KlineRecord, FundamentalsResponse,
    StockSnapshotResponse, NewsItem, AnnouncementItem, ResearchReportItem,
    IndicatorResponse,
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
