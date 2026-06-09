from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from src.config import Settings
from src.portfolio.manager import PortfolioManager
from src.portfolio.models import Position, TradeRecord


OPEN_ACTIONS = {"buy", "add"}
CLOSE_ACTIONS = {"sell", "reduce"}
NEUTRAL_ACTIONS = {"hold", "watch"}
FEE_ACTIONS = OPEN_ACTIONS | CLOSE_ACTIONS | {"clear"}
SELL_SIDE_ACTIONS = CLOSE_ACTIONS | {"clear"}


def _decimal(value, default: str = "0") -> Decimal:
    if value is None or value == "":
        return Decimal(default)
    return Decimal(str(value))


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _position_to_dict(pos: Position | None, symbol: str) -> dict:
    if pos is None:
        return {
            "symbol": symbol,
            "quantity": 0,
            "avg_cost": 0.0,
            "current_price": None,
            "market_value": None,
            "unrealized_pnl": None,
            "unrealized_pnl_pct": None,
        }
    return {
        "symbol": pos.symbol,
        "quantity": pos.quantity,
        "avg_cost": float(pos.avg_cost),
        "current_price": float(pos.current_price) if pos.current_price is not None else None,
        "market_value": float(pos.market_value) if pos.market_value is not None else None,
        "unrealized_pnl": float(pos.unrealized_pnl) if pos.unrealized_pnl is not None else None,
        "unrealized_pnl_pct": (
            float(pos.unrealized_pnl_pct) if pos.unrealized_pnl_pct is not None else None
        ),
    }


def _dict_to_position(symbol: str, data: dict) -> Position:
    pos = Position(
        symbol=symbol,
        quantity=int(data.get("quantity") or 0),
        avg_cost=_decimal(data.get("avg_cost")),
        current_price=(
            _decimal(data.get("current_price")) if data.get("current_price") is not None else None
        ),
    )
    if pos.current_price is not None:
        pos.update_price(pos.current_price)
    return pos


def _market_value(quantity: int, price: Decimal | None) -> float | None:
    if price is None:
        return None
    return float(price * Decimal(quantity))


class TradeApplyService:
    def __init__(self, portfolio: PortfolioManager, settings: Settings | None = None):
        self.portfolio = portfolio
        self.settings = settings or Settings()

    def apply_fee_config(self, entries: list[dict]) -> list[dict]:
        normalized: list[dict] = []
        commission_rate = _decimal(getattr(self.settings, "trade_commission_rate", 0))
        min_commission = _decimal(getattr(self.settings, "trade_min_commission", 0))
        stamp_tax_rate = _decimal(getattr(self.settings, "trade_stamp_tax_rate", 0))
        transfer_fee_rate = _decimal(getattr(self.settings, "trade_transfer_fee_rate", 0))

        for entry in entries:
            item = dict(entry)
            action = str(item.get("action", ""))
            quantity = int(item.get("quantity") or 0)
            price = _decimal(item.get("price"))
            amount = Decimal(quantity) * price

            if action in FEE_ACTIONS and amount > 0:
                commission = _money(amount * commission_rate)
                if min_commission > 0 and commission < min_commission:
                    commission = min_commission
                item["commission"] = float(commission)
                item["tax"] = float(_money(amount * stamp_tax_rate)) if action in SELL_SIDE_ACTIONS else 0.0
                item["other_fees"] = float(_money(amount * transfer_fee_rate))
            else:
                item["commission"] = 0.0
                item["tax"] = 0.0
                item["other_fees"] = 0.0

            item["amount"] = float(amount) if amount else 0.0
            normalized.append(item)
        return normalized

    async def prepare_daily_trade_log(
        self,
        trade_date: str,
        entries: list[dict],
        position_overrides: list[dict],
    ) -> dict:
        self._validate(trade_date, entries, position_overrides)
        entries = self.apply_fee_config(entries)
        symbols = sorted({str(e.get("symbol", "")).strip() for e in entries if e.get("symbol")})
        before_positions: dict[str, dict] = {}
        for symbol in symbols:
            before_positions[symbol] = _position_to_dict(await self.portfolio.get_position(symbol), symbol)

        system_positions = self._calculate_system_positions(before_positions, entries)
        final_positions, overrides = self._apply_overrides(system_positions, position_overrides)
        return {
            "before_positions": before_positions,
            "system_positions": system_positions,
            "final_positions": final_positions,
            "entries": entries,
            "trade_ids": [],
            "overrides": overrides,
            "fee_config": {
                "commission_rate": float(getattr(self.settings, "trade_commission_rate", 0)),
                "min_commission": float(getattr(self.settings, "trade_min_commission", 0)),
                "stamp_tax_rate": float(getattr(self.settings, "trade_stamp_tax_rate", 0)),
                "transfer_fee_rate": float(getattr(self.settings, "trade_transfer_fee_rate", 0)),
            },
        }

    async def apply_daily_trade_log(
        self,
        trade_date: str,
        entries: list[dict],
        position_overrides: list[dict],
        raw_source_id: str = "",
    ) -> dict:
        audit = await self.prepare_daily_trade_log(trade_date, entries, position_overrides)
        entries = audit["entries"]
        trade_ids: list[int] = []
        now = datetime.now()
        for entry in entries:
            symbol = str(entry.get("symbol", "")).strip()
            before = audit["before_positions"].get(symbol, {})
            system = audit["system_positions"].get(symbol, {})
            quantity = int(entry.get("quantity") or 0)
            price = _decimal(entry.get("price"))
            amount = _decimal(entry.get("amount")) or (Decimal(quantity) * price)
            trade = TradeRecord(
                symbol=symbol,
                action=str(entry.get("action", "")),
                quantity=quantity,
                price=price,
                old_quantity=int(before.get("quantity") or 0),
                new_quantity=int(system.get("quantity") or 0),
                reason=str(entry.get("reason") or ""),
                commission=_decimal(entry.get("commission")),
                tax=_decimal(entry.get("tax")),
                other_fees=_decimal(entry.get("other_fees")),
                amount=amount,
                raw_source_id=raw_source_id,
                recorded_at=now,
            )
            trade_ids.append(await self.portfolio.record_trade_return_id(trade))

        for symbol, final in audit["final_positions"].items():
            system = audit["system_positions"].get(symbol, {})
            symbol_overrides = [
                item for item in audit["overrides"] if item.get("symbol") == symbol
            ]
            reason = "; ".join(
                item.get("reason", "") for item in symbol_overrides if item.get("reason")
            )
            user_adjusted = bool(symbol_overrides)
            if not user_adjusted:
                user_adjusted = (
                    int(final.get("quantity") or 0) != int(system.get("quantity") or 0)
                    or _decimal(final.get("avg_cost")) != _decimal(system.get("avg_cost"))
                )
            await self.portfolio.upsert_position(
                _dict_to_position(symbol, final),
                last_trade_date=trade_date,
                user_adjusted=user_adjusted,
                adjustment_reason=reason,
            )

        audit["trade_ids"] = trade_ids
        return audit

    async def attach_raw_source(self, trade_ids: list[int], raw_source_id: str) -> None:
        if not trade_ids or not raw_source_id:
            return
        import aiosqlite

        placeholders = ",".join("?" for _ in trade_ids)
        async with aiosqlite.connect(self.portfolio.db_path) as db:
            await db.execute(
                f"UPDATE trades SET raw_source_id = ? WHERE id IN ({placeholders})",
                [raw_source_id, *trade_ids],
            )
            await db.commit()

    def _validate(
        self,
        trade_date: str,
        entries: list[dict],
        position_overrides: list[dict],
    ) -> None:
        if not trade_date:
            raise ValueError("trade_date is required")
        if not entries:
            raise ValueError("at least one trade entry is required")
        for entry in entries:
            symbol = str(entry.get("symbol", "")).strip()
            if not symbol:
                raise ValueError("entry symbol is required")
            action = str(entry.get("action", ""))
            if action in OPEN_ACTIONS | CLOSE_ACTIONS | {"clear"}:
                quantity = int(entry.get("quantity") or 0)
                price = _decimal(entry.get("price"))
                if quantity <= 0:
                    raise ValueError(f"{symbol} quantity must be greater than 0")
                if price <= 0:
                    raise ValueError(f"{symbol} price must be greater than 0")
            if action not in OPEN_ACTIONS | CLOSE_ACTIONS | NEUTRAL_ACTIONS | {"clear"}:
                raise ValueError(f"unsupported trade action: {action}")
        for override in position_overrides:
            if int(override.get("final_quantity") or 0) < 0:
                raise ValueError("final_quantity cannot be negative")
            if _decimal(override.get("final_avg_cost")) < 0:
                raise ValueError("final_avg_cost cannot be negative")

    def _calculate_system_positions(
        self,
        before_positions: dict[str, dict],
        entries: list[dict],
    ) -> dict[str, dict]:
        positions = {symbol: dict(pos) for symbol, pos in before_positions.items()}
        for entry in entries:
            symbol = str(entry.get("symbol", "")).strip()
            pos = positions.setdefault(symbol, _position_to_dict(None, symbol))
            action = str(entry.get("action", ""))
            quantity = int(entry.get("quantity") or 0)
            price = _decimal(entry.get("price"))
            commission = _decimal(entry.get("commission"))
            tax = _decimal(entry.get("tax"))
            other_fees = _decimal(entry.get("other_fees"))
            fees = commission + tax + other_fees

            old_qty = int(pos.get("quantity") or 0)
            old_cost = _decimal(pos.get("avg_cost"))
            old_total_cost = Decimal(old_qty) * old_cost

            if action in OPEN_ACTIONS:
                new_qty = old_qty + quantity
                total_cost = old_total_cost + Decimal(quantity) * price + fees
                new_cost = total_cost / Decimal(new_qty) if new_qty else Decimal("0")
                pos["quantity"] = new_qty
                pos["avg_cost"] = float(new_cost)
                pos["current_price"] = float(price)
                pos["market_value"] = _market_value(new_qty, price)

            elif action in CLOSE_ACTIONS:
                new_qty = max(0, old_qty - quantity)
                pos["quantity"] = new_qty
                pos["avg_cost"] = float(old_cost if new_qty else Decimal("0"))
                pos["current_price"] = float(price)
                pos["market_value"] = _market_value(new_qty, price)

            elif action == "clear":
                pos["quantity"] = 0
                pos["avg_cost"] = 0.0
                pos["current_price"] = float(price)
                pos["market_value"] = 0.0

            elif action in NEUTRAL_ACTIONS:
                if price > 0:
                    pos["current_price"] = float(price)
                    pos["market_value"] = _market_value(old_qty, price)

        return positions

    def _apply_overrides(
        self,
        system_positions: dict[str, dict],
        position_overrides: list[dict],
    ) -> tuple[dict[str, dict], list[dict]]:
        final_positions = {symbol: dict(pos) for symbol, pos in system_positions.items()}
        override_rows: list[dict] = []
        for override in position_overrides:
            symbol = str(override.get("symbol", "")).strip()
            if not symbol:
                continue
            final = final_positions.setdefault(symbol, _position_to_dict(None, symbol))
            system = system_positions.get(symbol, _position_to_dict(None, symbol))
            fields = [
                ("quantity", "final_quantity"),
                ("avg_cost", "final_avg_cost"),
                ("current_price", "final_current_price"),
            ]
            for field, source_field in fields:
                if source_field not in override or override.get(source_field) is None:
                    continue
                final_value = override[source_field]
                system_value = system.get(field)
                if str(final_value) != str(system_value):
                    override_rows.append(
                        {
                            "symbol": symbol,
                            "field": field,
                            "system_value": system_value,
                            "final_value": final_value,
                            "reason": str(override.get("override_reason") or ""),
                        }
                    )
                final[field] = final_value
            if final.get("current_price") is not None:
                final["market_value"] = _market_value(
                    int(final.get("quantity") or 0),
                    _decimal(final.get("current_price")),
                )
        return final_positions, override_rows
