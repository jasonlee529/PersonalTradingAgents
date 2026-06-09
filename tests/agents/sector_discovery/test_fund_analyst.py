import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agents.sector_discovery.scanners.fund_analyst import FundAnalyst
from src.config import Settings
from src.data.fund_holdings_store import FundHoldingsStore


@pytest.fixture
def settings(tmp_path):
    db_path = tmp_path / "fund_holdings.db"
    return Settings(
        data_dir=tmp_path,
        fund_holdings_db_path=db_path,
        fund_analyst_price_threshold=10.0,
    )


@pytest.fixture
async def store(settings):
    s = FundHoldingsStore(settings)
    await s.init_db()
    return s


@pytest.fixture
def scanner(settings, store):
    mock_cache = MagicMock()
    mock_collector = MagicMock()
    s = FundAnalyst(settings, mock_cache, mock_collector, store=store)
    return s


# ── Basic scan ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fund_analyst_empty_when_no_holdings(scanner):
    result = await scanner.scan()
    assert result.dimension == "fund"
    assert result.stocks == []


@pytest.mark.asyncio
async def test_fund_analyst_detects_new_holding_low_price_change(scanner, store):
    # Seed store with new holdings
    await store.save_holdings(
        "600519",
        [
            {"fund_code": "110022.OF", "fund_name": "易方达消费", "hold_ratio": 2.5, "is_new": 1},
            {"fund_code": "000083.OF", "fund_name": "汇添富消费", "hold_ratio": 1.2, "is_new": 1},
        ],
        period="2026Q1",
    )

    # Mock collector: low price change (5%)
    scanner.collector.get_quote = AsyncMock(return_value={"change_pct": 5.0})

    result = await scanner.scan()

    assert len(result.stocks) == 1
    assert result.stocks[0].symbol == "600519"
    assert result.stocks[0].dimension == "fund"
    assert result.stocks[0].time_horizon == "medium"
    assert result.stocks[0].score > 0
    assert "新增2只基金" in result.stocks[0].reason


@pytest.mark.asyncio
async def test_fund_analyst_skips_high_price_change(scanner, store):
    await store.save_holdings(
        "000001",
        [{"fund_code": "F001", "fund_name": "A基金", "hold_ratio": 3.0, "is_new": 1}],
        period="2026Q1",
    )

    # Price already moved 15% > threshold (10%)
    scanner.collector.get_quote = AsyncMock(return_value={"change_pct": 15.0})

    result = await scanner.scan()
    assert result.stocks == []


@pytest.mark.asyncio
async def test_fund_analyst_star_fund_bonus(scanner, store):
    await store.save_holdings(
        "600519",
        [
            {"fund_code": "110022.OF", "fund_name": "易方达消费", "hold_ratio": 2.0, "is_new": 1},
        ],
        period="2026Q1",
    )

    scanner.collector.get_quote = AsyncMock(return_value={"change_pct": 3.0})

    result = await scanner.scan()

    assert len(result.stocks) == 1
    # Star fund (110022 in DEFAULT_STAR_FUNDS) should boost score
    assert result.stocks[0].score >= 5.0
    assert "明星基金经理" in result.stocks[0].reason
    assert "萧楠" in result.stocks[0].reason
    assert "易方达消费" in result.stocks[0].reason


@pytest.mark.asyncio
async def test_fund_analyst_uses_kline_fallback_when_quote_fails(scanner, store):
    await store.save_holdings(
        "600519",
        [{"fund_code": "F001", "fund_name": "A基金", "hold_ratio": 2.0, "is_new": 1}],
        period="2026Q1",
    )

    scanner.collector.get_quote = AsyncMock(return_value=None)
    scanner.collector.get_kline = AsyncMock(return_value=[
        {"date": "2026-03-01", "close": 100.0},
        {"date": "2026-03-20", "close": 105.0},
    ])

    result = await scanner.scan()

    assert len(result.stocks) == 1
    # 5% change = (105-100)/100 * 100 = 5% < threshold
    assert result.stocks[0].score > 0


@pytest.mark.asyncio
async def test_fund_analyst_skips_over_owned(scanner, store):
    # Too many funds (>20) = might be over-owned
    holdings = [
        {"fund_code": f"F{i:03d}", "fund_name": f"基金{i}", "hold_ratio": 0.5, "is_new": 1}
        for i in range(25)
    ]
    await store.save_holdings("600519", holdings, period="2026Q1")

    scanner.collector.get_quote = AsyncMock(return_value={"change_pct": 3.0})

    result = await scanner.scan()
    assert result.stocks == []


@pytest.mark.asyncio
async def test_fund_analyst_sorts_by_score(scanner, store):
    await store.save_holdings(
        "600519",
        [{"fund_code": "110022.OF", "fund_name": "易方达消费", "hold_ratio": 5.0, "is_new": 1}],
        period="2026Q1",
    )
    await store.save_holdings(
        "000001",
        [{"fund_code": "F002", "fund_name": "B基金", "hold_ratio": 1.0, "is_new": 1}],
        period="2026Q1",
    )

    scanner.collector.get_quote = AsyncMock(return_value={"change_pct": 2.0})

    result = await scanner.scan()

    assert len(result.stocks) == 2
    # 600519 has higher hold_ratio + star fund = should rank first
    assert result.stocks[0].symbol == "600519"
    assert result.stocks[0].score > result.stocks[1].score


@pytest.mark.asyncio
async def test_fund_analyst_includes_when_no_price_data(scanner, store):
    await store.save_holdings(
        "600519",
        [{"fund_code": "F001", "fund_name": "A基金", "hold_ratio": 2.0, "is_new": 1}],
        period="2026Q1",
    )

    scanner.collector.get_quote = AsyncMock(return_value=None)
    scanner.collector.get_kline = AsyncMock(return_value=None)

    result = await scanner.scan()

    # No price data but still included (price_change defaults to 0)
    assert len(result.stocks) == 1
