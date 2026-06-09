from datetime import datetime
from decimal import Decimal
from typing import Optional

from src.portfolio.manager import PortfolioManager
from src.portfolio.models import TradeRecord
from src.knowledge.raw_renderers import render_daily_trade_log
from src.knowledge.raw_store import RawStore


class TradeRecorder:
    """Record trades in portfolio DB and generate raw daily trade sources."""

    def __init__(
        self,
        portfolio_manager: PortfolioManager,
        raw_store: RawStore,
    ):
        self.portfolio = portfolio_manager
        self.raw_store = raw_store

    async def record_and_ingest(self, trade: TradeRecord) -> None:
        """Save trade to DB and generate a raw daily trade source."""
        await self.portfolio.record_trade(trade)

        trade_date = trade.recorded_at.strftime("%Y-%m-%d")
        await self.raw_store.add_source(
            source_kind="daily_trade_log",
            origin="user",
            title=f"{trade_date} 每日操作记录",
            markdown=render_daily_trade_log(
                trade_date,
                [
                    {
                        "symbol": trade.symbol,
                        "action": trade.action,
                        "quantity": trade.quantity,
                        "price": float(trade.price),
                        "commission": float(trade.commission),
                        "tax": float(trade.tax),
                        "other_fees": float(trade.other_fees),
                        "reason": trade.reason,
                        "amount": float(trade.amount),
                    }
                ],
                notes="由持仓变更自动记录。",
                audit={
                    "before_positions": {
                        trade.symbol: {
                            "quantity": trade.old_quantity,
                            "avg_cost": float(trade.price),
                        }
                    },
                    "system_positions": {
                        trade.symbol: {
                            "quantity": trade.new_quantity,
                            "avg_cost": float(trade.price),
                        }
                    },
                    "final_positions": {
                        trade.symbol: {
                            "quantity": trade.new_quantity,
                            "avg_cost": float(trade.price),
                        }
                    },
                    "overrides": [],
                },
            ),
            metadata={
                "trade_date": trade_date,
                "symbols": [trade.symbol],
                "tags": ["trade_log", f"date/{trade_date}", f"stock/{trade.symbol}"],
                "source_ref": f"trade_recorder:{trade.symbol}:{trade.recorded_at.isoformat()}",
            },
        )

    async def record_position_change(
        self,
        symbol: str,
        old_quantity: int,
        new_quantity: int,
        price: float,
        reason: str = "",
    ) -> Optional[TradeRecord]:
        """Detect trade from position change and record it."""
        delta = new_quantity - old_quantity
        if delta == 0:
            return None

        action = "买入" if old_quantity == 0 else ("加仓" if delta > 0 else ("清仓" if new_quantity == 0 else "减仓"))
        trade = TradeRecord(
            symbol=symbol,
            action=action,
            quantity=abs(delta),
            price=Decimal(str(price)),
            old_quantity=old_quantity,
            new_quantity=new_quantity,
            reason=reason,
            recorded_at=datetime.now(),
        )
        await self.record_and_ingest(trade)
        return trade
