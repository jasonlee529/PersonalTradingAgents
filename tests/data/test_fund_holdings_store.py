import pytest
from src.config import Settings
from src.data.fund_holdings_store import FundHoldingsStore


@pytest.fixture
async def store(tmp_path):
    db_path = tmp_path / "fund_holdings.db"
    settings = Settings(data_dir=tmp_path, fund_holdings_db_path=db_path)
    s = FundHoldingsStore(settings)
    await s.init_db()
    return s


@pytest.mark.asyncio
async def test_init_db_creates_tables(store):
    periods = await store.get_periods()
    assert periods == []


@pytest.mark.asyncio
async def test_save_and_get_fund_holders(store):
    await store.save_holdings(
        "600519",
        [
            {"fund_code": "110022", "fund_name": "易方达消费", "hold_ratio": 2.5, "is_new": 1},
            {"fund_code": "000083", "fund_name": "汇添富消费", "hold_ratio": 1.2, "is_new": 0},
        ],
        period="2026Q1",
    )

    holders = await store.get_fund_holders("600519", period="2026Q1")
    assert len(holders) == 2
    assert holders[0]["fund_code"] == "110022"
    assert holders[0]["hold_ratio"] == 2.5
    assert holders[0]["is_new"] == 1
    assert holders[1]["fund_code"] == "000083"
    assert holders[1]["is_new"] == 0


@pytest.mark.asyncio
async def test_get_fund_holders_with_min_ratio(store):
    await store.save_holdings(
        "000001",
        [
            {"fund_code": "F001", "fund_name": "A基金", "hold_ratio": 3.0},
            {"fund_code": "F002", "fund_name": "B基金", "hold_ratio": 0.5},
        ],
        period="2026Q1",
    )

    holders = await store.get_fund_holders("000001", period="2026Q1", min_hold_ratio=1.0)
    assert len(holders) == 1
    assert holders[0]["fund_code"] == "F001"


@pytest.mark.asyncio
async def test_get_fund_holders_latest_period_default(store):
    await store.save_holdings(
        "600519",
        [{"fund_code": "F001", "fund_name": "A基金", "hold_ratio": 1.0}],
        period="2026Q2",
    )

    holders = await store.get_fund_holders("600519")
    assert len(holders) == 1
    assert holders[0]["period"] == "2026Q2"


@pytest.mark.asyncio
async def test_get_fund_holders_empty_when_no_data(store):
    holders = await store.get_fund_holders("999999", period="2026Q1")
    assert holders == []


@pytest.mark.asyncio
async def test_get_holdings_by_fund(store):
    await store.save_holdings(
        "600519",
        [{"fund_code": "110022", "fund_name": "易方达消费", "hold_ratio": 2.5}],
        period="2026Q1",
    )
    await store.save_holdings(
        "000001",
        [{"fund_code": "110022", "fund_name": "易方达消费", "hold_ratio": 1.0}],
        period="2026Q1",
    )

    stocks = await store.get_holdings_by_fund("110022", period="2026Q1")
    assert len(stocks) == 2
    symbols = {s["symbol"] for s in stocks}
    assert symbols == {"600519", "000001"}


@pytest.mark.asyncio
async def test_get_new_holdings(store):
    await store.save_holdings(
        "600519",
        [
            {"fund_code": "F001", "fund_name": "A基金", "hold_ratio": 2.0, "is_new": 1},
            {"fund_code": "F002", "fund_name": "B基金", "hold_ratio": 1.0, "is_new": 0},
        ],
        period="2026Q1",
    )
    await store.save_holdings(
        "000001",
        [
            {"fund_code": "F003", "fund_name": "C基金", "hold_ratio": 1.5, "is_new": 1},
        ],
        period="2026Q1",
    )

    new_holds = await store.get_new_holdings(period="2026Q1")
    assert len(new_holds) == 2
    symbols = {h["symbol"] for h in new_holds}
    assert symbols == {"600519", "000001"}


@pytest.mark.asyncio
async def test_get_periods(store):
    await store.save_holdings("600519", [{"fund_code": "F001", "hold_ratio": 1.0}], period="2026Q2")
    await store.save_holdings("600519", [{"fund_code": "F001", "hold_ratio": 1.0}], period="2026Q1")

    periods = await store.get_periods()
    assert periods == ["2026Q2", "2026Q1"]


@pytest.mark.asyncio
async def test_delete_period(store):
    await store.save_holdings("600519", [{"fund_code": "F001", "hold_ratio": 1.0}], period="2026Q1")

    deleted = await store.delete_period("2026Q1")
    assert deleted == 1

    holders = await store.get_fund_holders("600519", period="2026Q1")
    assert holders == []


@pytest.mark.asyncio
async def test_upsert_overwrites(store):
    await store.save_holdings(
        "600519",
        [{"fund_code": "F001", "fund_name": "A基金", "hold_ratio": 1.0}],
        period="2026Q1",
    )
    await store.save_holdings(
        "600519",
        [{"fund_code": "F001", "fund_name": "A基金改名", "hold_ratio": 3.0}],
        period="2026Q1",
    )

    holders = await store.get_fund_holders("600519", period="2026Q1")
    assert len(holders) == 1
    assert holders[0]["fund_name"] == "A基金改名"
    assert holders[0]["hold_ratio"] == 3.0
