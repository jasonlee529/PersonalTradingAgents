# src/portfolio/models.py
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class DataStatus(str, Enum):
    PENDING = "pending"
    COLLECTING = "collecting"
    READY = "ready"
    ERROR = "error"


class Market(str, Enum):
    CN = "CN"
    US = "US"
    HK = "HK"


class Holding(BaseModel):
    symbol: str
    name: str = ""
    market: Market = Market.CN
    tags: list[str] = Field(default_factory=list)
    data_status: DataStatus = DataStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Position(BaseModel):
    symbol: str
    quantity: int = 0
    avg_cost: Decimal = Decimal("0")
    current_price: Optional[Decimal] = None
    market_value: Optional[Decimal] = None
    unrealized_pnl: Optional[Decimal] = None
    unrealized_pnl_pct: Optional[Decimal] = None
    last_trade_date: str = ""
    user_adjusted: bool = False
    adjustment_reason: str = ""
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def update_price(self, price: Decimal) -> None:
        self.current_price = price
        self.market_value = price * self.quantity
        if self.avg_cost and self.quantity > 0:
            cost = self.avg_cost * self.quantity
            self.unrealized_pnl = self.market_value - cost
            self.unrealized_pnl_pct = (self.unrealized_pnl / cost) * 100 if cost else Decimal("0")
        self.updated_at = datetime.utcnow()


class TradeRecord(BaseModel):
    id: int = 0
    symbol: str
    action: str
    quantity: int
    price: Decimal
    old_quantity: int = 0
    new_quantity: int = 0
    reason: str = ""
    commission: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")
    other_fees: Decimal = Decimal("0")
    amount: Decimal = Decimal("0")
    raw_source_id: str = ""
    recorded_at: datetime = Field(default_factory=datetime.now)
