import pytest
from unittest.mock import MagicMock
from src.agents.signal_tools import (
    set_collector,
    get_consensus_expectations,
    get_market_heatmap,
    get_cross_border_flow,
    get_theme_exposure,
    get_order_flow_profile,
    get_trading_seat_activity,
    get_supply_unlock_schedule,
    get_peer_industry_snapshot,
    SIGNAL_TOOLS,
)


@pytest.fixture(autouse=True)
def reset_collector():
    set_collector(None)
    yield
    set_collector(None)


def test_get_consensus_expectations_returns_data():
    mock_collector = MagicMock()
    mock_collector.fetch_consensus_expectations = MagicMock(return_value={"eps": 2.5, "pe": 15})
    set_collector(mock_collector)

    result = get_consensus_expectations.invoke({"ticker": "600519"})
    assert "600519" in result
    assert "2.5" in result
    mock_collector.fetch_consensus_expectations.assert_called_once_with("600519")


def test_get_consensus_expectations_fallback_when_no_collector():
    result = get_consensus_expectations.invoke({"ticker": "600519"})
    assert "暂不支持" in result


def test_get_market_heatmap_returns_data():
    mock_collector = MagicMock()
    mock_collector.fetch_market_heatmap = MagicMock(return_value=[{"name": "某股", "reason": "AI概念"}])
    set_collector(mock_collector)

    result = get_market_heatmap.invoke({})
    assert "某股" in result
    mock_collector.fetch_market_heatmap.assert_called_once_with("")


def test_get_cross_border_flow_returns_data():
    mock_collector = MagicMock()
    mock_collector.fetch_cross_border_flow = MagicMock(return_value={"net_buy": 100.5})
    set_collector(mock_collector)

    result = get_cross_border_flow.invoke({"curr_date": "2024-01-01", "include_history": True})
    assert "100.5" in result
    mock_collector.fetch_cross_border_flow.assert_called_once_with(include_history=True)


def test_get_theme_exposure_returns_data():
    mock_collector = MagicMock()
    mock_collector.fetch_theme_exposure = MagicMock(return_value=["半导体", "AI芯片"])
    set_collector(mock_collector)

    result = get_theme_exposure.invoke({"ticker": "600519"})
    assert "半导体" in result
    mock_collector.fetch_theme_exposure.assert_called_once_with("600519")


def test_get_order_flow_profile_returns_data():
    mock_collector = MagicMock()
    mock_collector.fetch_order_flow_profile = MagicMock(return_value={"main_inflow": 5000})
    set_collector(mock_collector)

    result = get_order_flow_profile.invoke({"ticker": "600519", "include_history": False})
    assert "5000" in result
    mock_collector.fetch_order_flow_profile.assert_called_once_with("600519", include_history=False)


def test_get_trading_seat_activity_returns_data():
    mock_collector = MagicMock()
    mock_collector.fetch_trading_seat_activity = MagicMock(return_value={"appearances": 3})
    set_collector(mock_collector)

    result = get_trading_seat_activity.invoke({"ticker": "600519", "look_back_days": 15})
    assert "3" in result
    mock_collector.fetch_trading_seat_activity.assert_called_once_with(
        "600519", trade_date="", look_back_days=15
    )


def test_get_supply_unlock_schedule_returns_data():
    mock_collector = MagicMock()
    mock_collector.fetch_supply_unlock_schedule = MagicMock(return_value=[{"date": "2024-06-01", "shares": 1000}])
    set_collector(mock_collector)

    result = get_supply_unlock_schedule.invoke({"ticker": "600519", "forward_days": 60})
    assert "1000" in result
    mock_collector.fetch_supply_unlock_schedule.assert_called_once_with(
        "600519", trade_date="", forward_days=60
    )


def test_get_peer_industry_snapshot_returns_data():
    mock_collector = MagicMock()
    mock_collector.fetch_peer_industry_snapshot = MagicMock(return_value={"rank": 5})
    set_collector(mock_collector)

    result = get_peer_industry_snapshot.invoke({"ticker": "600519"})
    assert "5" in result
    mock_collector.fetch_peer_industry_snapshot.assert_called_once_with("600519")


def test_all_tools_in_signal_tools_list():
    assert len(SIGNAL_TOOLS) == 8
    names = [t.name for t in SIGNAL_TOOLS]
    assert "get_consensus_expectations" in names
    assert "get_market_heatmap" in names
    assert "get_cross_border_flow" in names
    assert "get_theme_exposure" in names
    assert "get_order_flow_profile" in names
    assert "get_trading_seat_activity" in names
    assert "get_supply_unlock_schedule" in names
    assert "get_peer_industry_snapshot" in names

