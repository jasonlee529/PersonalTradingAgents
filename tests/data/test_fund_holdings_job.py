import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.config import Settings
from src.data.fund_holdings_job import FundHoldingsRefreshJob, _to_store_period


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path, tushare_api_key="fake_token")


@pytest.fixture
def job(settings):
    return FundHoldingsRefreshJob(settings)


# ── _to_store_period ──────────────────────────────────────────────────────

def test_to_store_period_q1():
    assert _to_store_period("20260331") == "2026Q1"


def test_to_store_period_q2():
    assert _to_store_period("20260630") == "2026Q2"


def test_to_store_period_q3():
    assert _to_store_period("20260930") == "2026Q3"


def test_to_store_period_q4():
    assert _to_store_period("20261231") == "2026Q4"


def test_to_store_period_invalid():
    assert _to_store_period("bad") == "bad"


# ── _to_tushare_symbol ────────────────────────────────────────────────────

def test_to_tushare_symbol_sh():
    assert FundHoldingsRefreshJob._to_tushare_symbol("600519") == "600519.SH"


def test_to_tushare_symbol_sz():
    assert FundHoldingsRefreshJob._to_tushare_symbol("000001") == "000001.SZ"


def test_to_tushare_symbol_cy():
    assert FundHoldingsRefreshJob._to_tushare_symbol("300001") == "300001.SZ"


def test_to_tushare_symbol_bj():
    assert FundHoldingsRefreshJob._to_tushare_symbol("839001") == "839001.BJ"


def test_to_tushare_symbol_already_suffixed():
    assert FundHoldingsRefreshJob._to_tushare_symbol("600519.SH") == "600519.SH"


# ── run ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_skips_when_tushare_not_installed(job):
    with patch("src.data.fund_holdings_job.logger"):
        result = await job.run(["600519"])
    assert result["skipped"] is True
    assert result["reason"] == "tushare_unavailable"


@pytest.mark.asyncio
async def test_run_skips_when_no_symbols(job):
    # Mock tushare as available
    mock_pro = MagicMock()
    job._pro = mock_pro
    result = await job.run([])
    assert result == {"processed": 0, "skipped": 0, "failed": 0}


@pytest.mark.asyncio
async def test_run_processes_symbols(job, tmp_path):
    db_path = tmp_path / "run1" / "fund_holdings.db"
    settings = Settings(data_dir=tmp_path, tushare_api_key="fake_token", fund_holdings_db_path=db_path)
    job = FundHoldingsRefreshJob(settings)

    # Mock tushare pro client
    mock_pro = MagicMock()
    job._pro = mock_pro

    # Mock DataFrame response
    mock_df = MagicMock()
    mock_df.empty = False
    mock_df.iterrows.return_value = [
        (0, {"ts_code": "110022.OF", "stk_mkv_ratio": 2.5, "end_date": "20260331"}),
        (1, {"ts_code": "000083.OF", "stk_mkv_ratio": 1.2, "end_date": "20260331"}),
    ]
    mock_pro.fund_portfolio.return_value = mock_df

    # Patch asyncio.to_thread to call synchronously
    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    with patch("asyncio.to_thread", side_effect=fake_to_thread), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        result = await job.run(["600519", "000001"])

    assert result["processed"] == 2
    assert result["skipped"] == 0
    assert result["failed"] == 0

    # Verify store has data
    holders = await job.store.get_fund_holders("600519", period="2026Q1")
    assert len(holders) == 2
    codes = {h["fund_code"] for h in holders}
    assert codes == {"110022.OF", "000083.OF"}


@pytest.mark.asyncio
async def test_run_retries_then_fails(job, tmp_path):
    db_path = tmp_path / "run2" / "fund_holdings.db"
    settings = Settings(data_dir=tmp_path, tushare_api_key="fake_token", fund_holdings_db_path=db_path)
    job = FundHoldingsRefreshJob(settings)

    mock_pro = MagicMock()
    mock_pro.fund_portfolio.side_effect = Exception("API error")
    job._pro = mock_pro

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    with patch("asyncio.to_thread", side_effect=fake_to_thread), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        result = await job.run(["600519"])

    assert result["processed"] == 0
    assert result["skipped"] == 0
    assert result["failed"] == 1
    # 3 retries = 3 calls
    assert mock_pro.fund_portfolio.call_count == 3


@pytest.mark.asyncio
async def test_run_skips_empty_response(job, tmp_path):
    db_path = tmp_path / "run3" / "fund_holdings.db"
    settings = Settings(data_dir=tmp_path, tushare_api_key="fake_token", fund_holdings_db_path=db_path)
    job = FundHoldingsRefreshJob(settings)

    mock_pro = MagicMock()
    mock_df = MagicMock()
    mock_df.empty = True
    mock_pro.fund_portfolio.return_value = mock_df
    job._pro = mock_pro

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    with patch("asyncio.to_thread", side_effect=fake_to_thread), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        result = await job.run(["600519"])

    assert result["processed"] == 0
    assert result["skipped"] == 1
    assert result["failed"] == 0


@pytest.mark.asyncio
async def test_run_with_custom_period(job, tmp_path):
    unique_path = tmp_path / "custom_period"
    db_path = unique_path / "fund_holdings.db"
    settings = Settings(data_dir=unique_path, tushare_api_key="fake_token", fund_holdings_db_path=db_path)
    job = FundHoldingsRefreshJob(settings)

    mock_pro = MagicMock()
    mock_df = MagicMock()
    mock_df.empty = False
    mock_df.iterrows.return_value = [
        (0, {"ts_code": "F001", "stk_mkv_ratio": 1.0, "end_date": "20260331"}),
    ]
    mock_pro.fund_portfolio.return_value = mock_df
    job._pro = mock_pro

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    with patch("asyncio.to_thread", side_effect=fake_to_thread), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        result = await job.run(["600519"], period="2026Q1")

    assert result["processed"] == 1
    holders = await job.store.get_fund_holders("600519", period="2026Q1")
    assert len(holders) == 1
    assert holders[0]["fund_code"] == "F001"
