# src/portfolio/manager.py
import aiosqlite
from decimal import Decimal
from datetime import datetime
from pathlib import Path
from typing import Optional
from src.config import Settings
from src.portfolio.models import DataStatus, Holding, Position, TradeRecord

SCHEMA = """
CREATE TABLE IF NOT EXISTS holdings (
    symbol TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    market TEXT NOT NULL,
    tags TEXT DEFAULT '[]',
    data_status TEXT DEFAULT 'pending',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS positions (
    symbol TEXT PRIMARY KEY,
    quantity INTEGER NOT NULL DEFAULT 0,
    avg_cost TEXT NOT NULL DEFAULT '0',
    current_price TEXT,
    market_value TEXT,
    unrealized_pnl TEXT,
    unrealized_pnl_pct TEXT,
    last_trade_date TEXT DEFAULT '',
    user_adjusted INTEGER DEFAULT 0,
    adjustment_reason TEXT DEFAULT '',
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price TEXT NOT NULL,
    old_quantity INTEGER DEFAULT 0,
    new_quantity INTEGER DEFAULT 0,
    reason TEXT DEFAULT '',
    commission TEXT DEFAULT '0',
    tax TEXT DEFAULT '0',
    other_fees TEXT DEFAULT '0',
    amount TEXT DEFAULT '0',
    raw_source_id TEXT DEFAULT '',
    recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_recorded_at ON trades(recorded_at);
"""


class PortfolioManager:
    def __init__(self, settings: Settings):
        self.db_path = settings.portfolio_db_path
        self._listeners: list = []

    def add_listener(self, callback) -> None:
        """Register an async callback(event_type, symbol)."""
        self._listeners.append(callback)

    def remove_listener(self, callback) -> None:
        """Unregister a callback."""
        if callback in self._listeners:
            self._listeners.remove(callback)

    async def _notify_listeners(self, event_type: str, symbol: str) -> None:
        """Fire all registered listeners, swallowing exceptions."""
        import logging
        logger = logging.getLogger(__name__)
        for cb in self._listeners:
            try:
                await cb(event_type, symbol)
            except Exception as e:
                logger.warning("Portfolio listener failed for %s %s: %s", event_type, symbol, e)

    async def init_db(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(SCHEMA)
            await self._run_migrations(db)
            await db.commit()

    async def _run_migrations(self, db: aiosqlite.Connection) -> None:
        cursor = await db.execute("PRAGMA table_info(trades)")
        trade_cols = {row[1] for row in await cursor.fetchall()}
        for column, ddl in {
            "commission": "ALTER TABLE trades ADD COLUMN commission TEXT DEFAULT '0'",
            "tax": "ALTER TABLE trades ADD COLUMN tax TEXT DEFAULT '0'",
            "other_fees": "ALTER TABLE trades ADD COLUMN other_fees TEXT DEFAULT '0'",
            "amount": "ALTER TABLE trades ADD COLUMN amount TEXT DEFAULT '0'",
            "raw_source_id": "ALTER TABLE trades ADD COLUMN raw_source_id TEXT DEFAULT ''",
        }.items():
            if column not in trade_cols:
                await db.execute(ddl)

        cursor = await db.execute("PRAGMA table_info(positions)")
        position_cols = {row[1] for row in await cursor.fetchall()}
        for column, ddl in {
            "last_trade_date": "ALTER TABLE positions ADD COLUMN last_trade_date TEXT DEFAULT ''",
            "user_adjusted": "ALTER TABLE positions ADD COLUMN user_adjusted INTEGER DEFAULT 0",
            "adjustment_reason": "ALTER TABLE positions ADD COLUMN adjustment_reason TEXT DEFAULT ''",
        }.items():
            if column not in position_cols:
                await db.execute(ddl)

    async def add_holding(self, holding: Holding) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO holdings (symbol, name, market, tags, data_status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (holding.symbol, holding.name, holding.market.value, str(holding.tags), holding.data_status.value, holding.created_at.isoformat()),
            )
            await db.commit()
        await self._notify_listeners("added", holding.symbol)

    async def remove_holding(self, symbol: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM holdings WHERE symbol = ?", (symbol,))
            await db.execute("DELETE FROM positions WHERE symbol = ?", (symbol,))
            await db.commit()
        await self._notify_listeners("removed", symbol)

    async def list_holdings(self) -> list[Holding]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM holdings") as cursor:
                rows = await cursor.fetchall()
                return [
                    Holding(
                        symbol=r["symbol"], name=r["name"], market=r["market"],
                        tags=eval(r["tags"]), data_status=DataStatus(r["data_status"] if r["data_status"] else "pending"),
                        created_at=datetime.fromisoformat(r["created_at"]),
                    )
                    for r in rows
                ]

    async def set_position(self, symbol: str, quantity: int, avg_cost: Decimal) -> None:
        pos = Position(symbol=symbol, quantity=quantity, avg_cost=avg_cost)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT OR REPLACE INTO positions
                   (symbol, quantity, avg_cost, current_price, market_value,
                    unrealized_pnl, unrealized_pnl_pct, last_trade_date,
                    user_adjusted, adjustment_reason, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (pos.symbol, pos.quantity, str(pos.avg_cost),
                 str(pos.current_price) if pos.current_price else None,
                 str(pos.market_value) if pos.market_value else None,
                 str(pos.unrealized_pnl) if pos.unrealized_pnl else None,
                 str(pos.unrealized_pnl_pct) if pos.unrealized_pnl_pct else None,
                 pos.last_trade_date, int(pos.user_adjusted), pos.adjustment_reason,
                 pos.updated_at.isoformat()),
            )
            await db.commit()

    async def upsert_position(
        self,
        position: Position,
        *,
        last_trade_date: str = "",
        user_adjusted: bool = False,
        adjustment_reason: str = "",
    ) -> None:
        position.last_trade_date = last_trade_date
        position.user_adjusted = user_adjusted
        position.adjustment_reason = adjustment_reason
        position.updated_at = datetime.utcnow()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT OR REPLACE INTO positions
                   (symbol, quantity, avg_cost, current_price, market_value,
                    unrealized_pnl, unrealized_pnl_pct, last_trade_date,
                    user_adjusted, adjustment_reason, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    position.symbol,
                    position.quantity,
                    str(position.avg_cost),
                    str(position.current_price) if position.current_price is not None else None,
                    str(position.market_value) if position.market_value is not None else None,
                    str(position.unrealized_pnl) if position.unrealized_pnl is not None else None,
                    str(position.unrealized_pnl_pct) if position.unrealized_pnl_pct is not None else None,
                    last_trade_date,
                    int(user_adjusted),
                    adjustment_reason,
                    position.updated_at.isoformat(),
                ),
            )
            await db.commit()

    async def get_position(self, symbol: str) -> Optional[Position]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM positions WHERE symbol = ?", (symbol,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return Position(
                    symbol=row["symbol"], quantity=row["quantity"],
                    avg_cost=Decimal(row["avg_cost"]),
                    current_price=Decimal(row["current_price"]) if row["current_price"] else None,
                    market_value=Decimal(row["market_value"]) if row["market_value"] else None,
                    unrealized_pnl=Decimal(row["unrealized_pnl"]) if row["unrealized_pnl"] else None,
                    unrealized_pnl_pct=Decimal(row["unrealized_pnl_pct"]) if row["unrealized_pnl_pct"] else None,
                    last_trade_date=row["last_trade_date"] if "last_trade_date" in row.keys() else "",
                    user_adjusted=bool(row["user_adjusted"]) if "user_adjusted" in row.keys() else False,
                    adjustment_reason=row["adjustment_reason"] if "adjustment_reason" in row.keys() else "",
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                )

    async def update_data_status(self, symbol: str, status: DataStatus) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE holdings SET data_status = ? WHERE symbol = ?",
                (status.value, symbol),
            )
            await db.commit()

    async def update_holding_name(self, symbol: str, name: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE holdings SET name = ? WHERE symbol = ?",
                (name, symbol),
            )
            await db.commit()

    async def get_holding(self, symbol: str) -> Optional[Holding]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM holdings WHERE symbol = ?", (symbol,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return Holding(
                    symbol=row["symbol"], name=row["name"], market=row["market"],
                    tags=eval(row["tags"]), data_status=DataStatus(row["data_status"] if row["data_status"] else "pending"),
                    created_at=datetime.fromisoformat(row["created_at"]),
                )

    async def list_symbols(self) -> list[str]:
        holdings = await self.list_holdings()
        return [h.symbol for h in holdings]

    async def record_trade(self, trade: TradeRecord) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO trades
                   (symbol, action, quantity, price, old_quantity, new_quantity, reason,
                    commission, tax, other_fees, amount, raw_source_id, recorded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    trade.symbol, trade.action, trade.quantity,
                    str(trade.price), trade.old_quantity, trade.new_quantity,
                    trade.reason, str(trade.commission), str(trade.tax),
                    str(trade.other_fees), str(trade.amount), trade.raw_source_id,
                    trade.recorded_at.isoformat(),
                ),
            )
            await db.commit()

    async def record_trade_return_id(self, trade: TradeRecord) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """INSERT INTO trades
                   (symbol, action, quantity, price, old_quantity, new_quantity, reason,
                    commission, tax, other_fees, amount, raw_source_id, recorded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    trade.symbol, trade.action, trade.quantity,
                    str(trade.price), trade.old_quantity, trade.new_quantity,
                    trade.reason, str(trade.commission), str(trade.tax),
                    str(trade.other_fees), str(trade.amount), trade.raw_source_id,
                    trade.recorded_at.isoformat(),
                ),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def list_trades(self, symbol: Optional[str] = None, limit: int = 100) -> list[TradeRecord]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if symbol:
                cursor = await db.execute(
                    "SELECT * FROM trades WHERE symbol = ? ORDER BY recorded_at DESC LIMIT ?",
                    (symbol, limit),
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM trades ORDER BY recorded_at DESC LIMIT ?",
                    (limit,),
                )
            rows = await cursor.fetchall()
            return [
                TradeRecord(
                    id=r["id"],
                    symbol=r["symbol"],
                    action=r["action"],
                    quantity=r["quantity"],
                    price=Decimal(r["price"]),
                    old_quantity=r["old_quantity"],
                    new_quantity=r["new_quantity"],
                    reason=r["reason"],
                    commission=Decimal(r["commission"]) if "commission" in r.keys() else Decimal("0"),
                    tax=Decimal(r["tax"]) if "tax" in r.keys() else Decimal("0"),
                    other_fees=Decimal(r["other_fees"]) if "other_fees" in r.keys() else Decimal("0"),
                    amount=Decimal(r["amount"]) if "amount" in r.keys() else Decimal("0"),
                    raw_source_id=r["raw_source_id"] if "raw_source_id" in r.keys() else "",
                    recorded_at=datetime.fromisoformat(r["recorded_at"]),
                )
                for r in rows
            ]

