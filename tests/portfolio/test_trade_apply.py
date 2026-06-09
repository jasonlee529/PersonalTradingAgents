import pytest

from src.portfolio.manager import PortfolioManager
from src.portfolio.trade_apply import TradeApplyService


@pytest.mark.asyncio
async def test_trade_apply_uses_user_overrides(test_settings):
    manager = PortfolioManager(test_settings)
    await manager.init_db()
    service = TradeApplyService(manager)

    audit = await service.apply_daily_trade_log(
        "2026-06-04",
        [
            {
                "symbol": "603738",
                "action": "buy",
                "quantity": 1000,
                "price": 12.3,
                "commission": 5,
                "tax": 0,
                "other_fees": 0,
                "reason": "建仓",
            }
        ],
        [
            {
                "symbol": "603738",
                "final_quantity": 900,
                "final_avg_cost": 12.5,
                "final_current_price": 12.3,
                "override_reason": "按券商页面修正",
            }
        ],
        raw_source_id="daily_trade_log:test",
    )

    assert audit["system_positions"]["603738"]["quantity"] == 1000
    assert audit["final_positions"]["603738"]["quantity"] == 900
    assert audit["overrides"]

    pos = await manager.get_position("603738")
    assert pos is not None
    assert pos.quantity == 900
    assert str(pos.avg_cost) == "12.5"
    assert pos.user_adjusted is True
    assert "券商" in pos.adjustment_reason

    trades = await manager.list_trades("603738")
    assert len(trades) == 1
    assert trades[0].raw_source_id == "daily_trade_log:test"


@pytest.mark.asyncio
async def test_trade_apply_calculates_fees_from_settings(test_settings):
    test_settings.trade_commission_rate = 0.001
    test_settings.trade_min_commission = 5
    test_settings.trade_stamp_tax_rate = 0.0005
    test_settings.trade_transfer_fee_rate = 0.00001

    manager = PortfolioManager(test_settings)
    await manager.init_db()
    await manager.set_position("603738", 1000, 10)
    service = TradeApplyService(manager, test_settings)

    audit = await service.apply_daily_trade_log(
        "2026-06-04",
        [
            {
                "symbol": "603738",
                "action": "sell",
                "quantity": 100,
                "price": 12,
                "commission": 999,
                "tax": 999,
                "other_fees": 999,
                "reason": "止盈",
            }
        ],
        [
            {
                "symbol": "603738",
                "final_quantity": 900,
                "final_avg_cost": 10,
                "final_current_price": 12,
            }
        ],
    )

    entry = audit["entries"][0]
    assert entry["amount"] == 1200.0
    assert entry["commission"] == 5.0
    assert entry["tax"] == 0.6
    assert entry["other_fees"] == 0.01

    trades = await manager.list_trades("603738")
    assert float(trades[0].commission) == 5.0
    assert float(trades[0].tax) == 0.6
    assert float(trades[0].other_fees) == 0.01
