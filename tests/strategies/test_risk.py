"""风控模块单元测试。"""

from src.strategies.risk import (
    RiskConfig,
    Position,
    calc_stop_loss_price,
    check_exit,
    calc_buy_shares,
    calc_buy_cost,
    calc_sell_cost,
)


def test_calc_stop_loss_price_fixed():
    price = calc_stop_loss_price(10.0, "fixed", 0.08, ma20_price=9.5)
    assert abs(price - 9.2) < 0.01  # 10 * 0.92


def test_calc_stop_loss_price_ma20():
    price = calc_stop_loss_price(10.0, "ma20", 0.08, ma20_price=9.5)
    assert price == 9.5


def test_calc_stop_loss_price_ma20_none():
    """ma20=None 时回退到固定止损。"""
    price = calc_stop_loss_price(10.0, "ma20", 0.08, ma20_price=None)
    assert abs(price - 9.2) < 0.01


def test_check_exit_hold():
    config = RiskConfig(stop_loss_type="fixed", stop_loss_pct=0.08)
    pos = Position(
        symbol="600001", name="测试", entry_date="2024-01-01",
        entry_price=10.0, shares=1000, initial_shares=1000,
        stop_loss_price=9.2,
    )
    action, price, shares = check_exit(pos, 10.5, None, config)
    assert action == "hold"
    assert shares == 0


def test_check_exit_stop_loss():
    config = RiskConfig(stop_loss_type="fixed", stop_loss_pct=0.08)
    pos = Position(
        symbol="600001", name="测试", entry_date="2024-01-01",
        entry_price=10.0, shares=1000, initial_shares=1000,
        stop_loss_price=9.2,
    )
    action, price, shares = check_exit(pos, 9.0, None, config)
    assert action == "stop_loss"
    assert shares == 1000


def test_check_exit_take_profit_level1():
    """+10% 触发第一段止盈，卖30%。"""
    config = RiskConfig(
        stop_loss_type="fixed", stop_loss_pct=0.08,
        take_profit_levels=[(0.10, 0.30), (0.20, 0.30), (0.30, 1.0)],
    )
    pos = Position(
        symbol="600001", name="测试", entry_date="2024-01-01",
        entry_price=10.0, shares=1000, initial_shares=1000,
        stop_loss_price=9.2,
    )
    action, price, shares = check_exit(pos, 11.1, None, config)
    assert action == "take_profit"
    assert shares == 300  # 30% of 1000


def test_check_exit_take_profit_all():
    """+30% 触发第三段止盈，清仓。"""
    config = RiskConfig(
        stop_loss_type="fixed", stop_loss_pct=0.08,
        take_profit_levels=[(0.10, 0.30), (0.20, 0.30), (0.30, 1.0)],
    )
    pos = Position(
        symbol="600001", name="测试", entry_date="2024-01-01",
        entry_price=10.0, shares=1000, initial_shares=1000,
        stop_loss_price=9.2,
        take_profit_triggered=[True, True, False],
    )
    action, price, shares = check_exit(pos, 13.5, None, config)
    assert action == "take_profit"
    assert shares == 1000


def test_check_exit_ma20_updates_stop():
    """MA20 止损时，止损价跟随 MA20 更新。"""
    config = RiskConfig(stop_loss_type="ma20", stop_loss_pct=0.08)
    pos = Position(
        symbol="600001", name="测试", entry_date="2024-01-01",
        entry_price=10.0, shares=1000, initial_shares=1000,
        stop_loss_price=9.0,
    )
    # MA20 上移到 9.8
    action, price, shares = check_exit(pos, 9.9, 9.8, config)
    assert pos.stop_loss_price == 9.8
    assert action == "hold"


def test_calc_buy_shares():
    config = RiskConfig(max_position_pct=0.20, max_holdings=5)
    shares = calc_buy_shares(1_000_000, 10.0, config, current_holdings=0)
    # 20% of 1M = 200k, price ~10.03 (with slippage) → ~19940 → 19900 (100股整数倍)
    assert shares > 0
    assert shares % 100 == 0


def test_calc_buy_shares_max_holdings():
    config = RiskConfig(max_holdings=5)
    shares = calc_buy_shares(1_000_000, 10.0, config, current_holdings=5)
    assert shares == 0


def test_calc_buy_cost():
    config = RiskConfig(commission_rate=0.00025, min_commission=5.0)
    # 大额：按费率
    cost = calc_buy_cost(100_000, config)
    assert abs(cost - 25.0) < 0.01  # 100000 * 0.00025
    # 小额：最低佣金
    cost_small = calc_buy_cost(1000, config)
    assert cost_small == 5.0


def test_calc_sell_cost():
    config = RiskConfig(commission_rate=0.00025, min_commission=5.0, stamp_tax_rate=0.0005)
    cost = calc_sell_cost(100_000, config)
    # 佣金 25 + 印花税 50 = 75
    assert abs(cost - 75.0) < 0.01
