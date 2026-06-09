"""Small date helpers for market-facing workflows."""

from __future__ import annotations

from datetime import date, datetime, timedelta


def previous_weekday(value: date) -> date:
    """Return value if it is Mon-Fri, otherwise the previous Friday."""
    current = value
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current


def normalize_trade_date(date_str: str | None = None) -> str:
    """Normalize a YYYY-MM-DD date to a weekday trading-date approximation."""
    if date_str:
        value = datetime.strptime(date_str, "%Y-%m-%d").date()
    else:
        value = date.today()
    return previous_weekday(value).strftime("%Y-%m-%d")
