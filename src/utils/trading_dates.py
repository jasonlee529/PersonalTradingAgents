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


def is_weekend(value: date | str | None = None) -> bool:
    """Check whether a date falls on a weekend.

    Args:
        value: A date object, YYYY-MM-DD string, or None for today.
    """
    if value is None:
        d = date.today()
    elif isinstance(value, str):
        d = datetime.strptime(value, "%Y-%m-%d").date()
    else:
        d = value
    return d.weekday() >= 5


def get_recent_trade_dates(
    date_str: str | None = None,
    count: int = 5,
) -> list[str]:
    """Return *count* recent weekday dates going backwards from the given date.

    Useful for data-source fallback: if the primary date yields no data (e.g.
    run on a weekend or when the API only serves the latest trading day),
    callers can try earlier dates in sequence.

    Args:
        date_str: Starting date in YYYY-MM-DD format. Defaults to today.
        count: Number of weekday dates to return.

    Returns:
        List of YYYY-MM-DD strings, most recent first.
    """
    if date_str:
        current = datetime.strptime(date_str, "%Y-%m-%d").date()
    else:
        current = date.today()

    dates: list[str] = []
    # Start from the nearest weekday
    current = previous_weekday(current)
    while len(dates) < count:
        dates.append(current.strftime("%Y-%m-%d"))
        # Go back one day and find the previous weekday
        current = previous_weekday(current - timedelta(days=1))
    return dates
