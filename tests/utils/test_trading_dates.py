"""Tests for trading_dates utility functions."""

from datetime import date

from src.utils.trading_dates import (
    get_recent_trade_dates,
    is_weekend,
    normalize_trade_date,
    previous_weekday,
)


class TestNormalizeTradeDate:
    def test_weekday_unchanged(self):
        # 2026-06-04 is a Thursday
        assert normalize_trade_date("2026-06-04") == "2026-06-04"

    def test_saturday_falls_back_to_friday(self):
        # 2026-06-13 is a Saturday → fallback to Friday 2026-06-12
        assert normalize_trade_date("2026-06-13") == "2026-06-12"

    def test_sunday_falls_back_to_friday(self):
        # 2026-06-14 is a Sunday → fallback to Friday 2026-06-12
        assert normalize_trade_date("2026-06-14") == "2026-06-12"

    def test_none_defaults_to_today(self):
        result = normalize_trade_date(None)
        # Should return a weekday date string
        result_date = date.fromisoformat(result)
        assert result_date.weekday() < 5


class TestIsWeekend:
    def test_saturday(self):
        assert is_weekend("2026-06-13") is True

    def test_sunday(self):
        assert is_weekend("2026-06-14") is True

    def test_weekday(self):
        assert is_weekend("2026-06-12") is False

    def test_date_object(self):
        assert is_weekend(date(2026, 6, 13)) is True

    def test_none_defaults_to_today(self):
        result = is_weekend(None)
        assert isinstance(result, bool)


class TestPreviousWeekday:
    def test_monday(self):
        # Monday 2026-06-08 stays Monday
        assert previous_weekday(date(2026, 6, 8)) == date(2026, 6, 8)

    def test_saturday(self):
        # Saturday 2026-06-13 → Friday 2026-06-12
        assert previous_weekday(date(2026, 6, 13)) == date(2026, 6, 12)

    def test_sunday(self):
        # Sunday 2026-06-14 → Friday 2026-06-12
        assert previous_weekday(date(2026, 6, 14)) == date(2026, 6, 12)


class TestGetRecentTradeDates:
    def test_from_weekday(self):
        # 2026-06-12 is a Friday
        dates = get_recent_trade_dates("2026-06-12", count=3)
        assert len(dates) == 3
        # All should be weekdays
        for d in dates:
            dt = date.fromisoformat(d)
            assert dt.weekday() < 5

    def test_from_weekend(self):
        # 2026-06-14 is a Sunday → should start from Friday 2026-06-12
        dates = get_recent_trade_dates("2026-06-14", count=3)
        assert dates[0] == "2026-06-12"

    def test_default_count(self):
        dates = get_recent_trade_dates("2026-06-12")
        assert len(dates) == 5

    def test_going_back_across_weekend(self):
        # Starting from Friday 2026-06-12, count=4 should give:
        # Fri 06-12, Thu 06-11, Wed 06-10, Tue 06-09
        # (Monday 06-08 is the 5th)
        dates = get_recent_trade_dates("2026-06-12", count=4)
        assert len(dates) == 4
        assert dates[0] == "2026-06-12"
        assert dates[1] == "2026-06-11"
        assert dates[2] == "2026-06-10"
        assert dates[3] == "2026-06-09"

    def test_none_defaults_to_today(self):
        dates = get_recent_trade_dates(None, count=3)
        assert len(dates) == 3
        for d in dates:
            dt = date.fromisoformat(d)
            assert dt.weekday() < 5