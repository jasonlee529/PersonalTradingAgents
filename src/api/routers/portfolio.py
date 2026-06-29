import re
from decimal import Decimal
from fastapi import APIRouter, Depends

from src.api.dependencies import get_services, AppServices
from src.api.models import (
    HoldingCreate, HoldingDetailResponse, HoldingResponse, PositionResponse,
    PositionUpdate, TradeRecordResponse,
)
from src.portfolio.models import Holding, Position, DataStatus
from src.services.data_collection import DataCollectionService

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


async def _resolve_holding_name(symbol: str, fallback: str, services: AppServices) -> str:
    clean_symbol = symbol.strip()
    if not re.fullmatch(r"\d{6}", clean_symbol):
        return fallback or clean_symbol
    try:
        quote = await services.collector.get_quote(clean_symbol)
    except Exception:
        quote = None
    resolved = (quote or {}).get("name", "")
    if not resolved:
        try:
            fundamentals = await services.collector.get_fundamentals(clean_symbol)
        except Exception:
            fundamentals = None
        resolved = (fundamentals or {}).get("name", "")
    return resolved or fallback or clean_symbol


@router.get("/holdings", response_model=list[HoldingDetailResponse])
async def list_holdings(services: AppServices = Depends(get_services)):
    holdings = await services.portfolio.list_holdings()
    results = []
    for h in holdings:
        holding_name = h.name or h.symbol
        pos = await services.portfolio.get_position(h.symbol)
        results.append(HoldingDetailResponse(
            holding=HoldingResponse(
                symbol=h.symbol, name=holding_name, market=h.market.value,
                tags=h.tags, data_status=h.data_status.value, created_at=h.created_at,
            ),
            position=PositionResponse(
                symbol=pos.symbol, quantity=pos.quantity, avg_cost=float(pos.avg_cost),
                current_price=float(pos.current_price) if pos.current_price is not None else None,
                market_value=float(pos.market_value) if pos.market_value is not None else None,
                unrealized_pnl=float(pos.unrealized_pnl) if pos.unrealized_pnl is not None else None,
                unrealized_pnl_pct=float(pos.unrealized_pnl_pct) if pos.unrealized_pnl_pct is not None else None,
                updated_at=pos.updated_at,
            ) if pos else None,
        ))
    return results


@router.post("/holdings", response_model=dict)
async def add_holding(body: HoldingCreate, services: AppServices = Depends(get_services)):
    symbol = body.symbol.strip()
    name = await _resolve_holding_name(symbol, body.name, services)
    holding = Holding(
        symbol=symbol,
        name=name,
        market=body.market,
        data_status=DataStatus.PENDING,
    )
    await services.portfolio.add_holding(holding)
    pos = await services.portfolio.get_position(symbol)
    if not pos:
        await services.portfolio.set_position(
            holding.symbol, body.quantity or 0, Decimal(str(body.avg_cost or 0))
        )
    # Auto-fetch initial price if available
    try:
        quote = await services.collector.get_quote(symbol)
        if quote and quote.get("price"):
            price = Decimal(str(quote["price"]))
            pos = await services.portfolio.get_position(symbol)
            if pos:
                pos.update_price(price)
                await services.portfolio.upsert_position(pos)
    except Exception:
        pass
    # Start background data collection
    svc = DataCollectionService(services.collector, services.portfolio)
    svc.start_collection(holding.symbol)
    return {"symbol": holding.symbol, "status": "added", "data_collection": "started"}


@router.delete("/holdings/{symbol}", response_model=dict)
async def remove_holding(symbol: str, services: AppServices = Depends(get_services)):
    await services.portfolio.remove_holding(symbol)
    return {"symbol": symbol, "status": "removed"}


@router.patch("/holdings/{symbol}/position", response_model=dict)
async def update_position(
    symbol: str,
    body: PositionUpdate,
    services: AppServices = Depends(get_services),
):
    old_pos = await services.portfolio.get_position(symbol)
    from decimal import Decimal
    pos = Position(
        symbol=symbol,
        quantity=body.quantity,
        avg_cost=Decimal(str(body.avg_cost)),
    )
    # User edits only the final position inputs. PnL is always derived from
    # quantity, average cost, and current price.
    if body.current_price is not None:
        pos.update_price(Decimal(str(body.current_price)))
    elif old_pos and old_pos.current_price is not None:
        pos.update_price(old_pos.current_price)
    await services.portfolio.upsert_position(
        pos,
        user_adjusted=True,
        adjustment_reason=body.override_reason or "用户手动修改",
    )
    return {"symbol": symbol, "status": "updated"}


@router.post("/refresh-prices", response_model=dict)
async def refresh_prices(services: AppServices = Depends(get_services)):
    from src.services.price_updater import PriceUpdater
    updater = PriceUpdater(services.collector, services.portfolio)
    await updater.refresh_all()
    return {"status": "prices refreshed"}


@router.get("/trades", response_model=list[TradeRecordResponse])
async def list_trades(
    symbol: str | None = None,
    limit: int = 50,
    services: AppServices = Depends(get_services),
):
    records = await services.portfolio.list_trades(symbol=symbol, limit=limit)
    return [
        TradeRecordResponse(
            id=r.id,
            symbol=r.symbol,
            action=r.action,
            quantity=r.quantity,
            price=float(r.price),
            old_quantity=r.old_quantity,
            new_quantity=r.new_quantity,
            reason=r.reason,
            commission=float(r.commission),
            tax=float(r.tax),
            other_fees=float(r.other_fees),
            amount=float(r.amount),
            raw_source_id=r.raw_source_id,
            recorded_at=r.recorded_at,
        )
        for r in records
    ]
