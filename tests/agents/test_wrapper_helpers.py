from src.agents.wrapper import (
    TAConfigBuilder,
    build_market_profile,
)


def test_wrapper_helpers_do_not_export_position_context_builder():
    import src.agents.wrapper as wrapper_helpers

    assert not hasattr(wrapper_helpers, "PositionContextBuilder")


def test_config_builder_sets_benchmark_map():
    from src.config import Settings

    s = Settings()
    builder = TAConfigBuilder(s)
    cfg = builder.build({})
    assert cfg["benchmark_map"][".SS"] == "000300.SS"
    assert cfg["benchmark_map"][".SH"] == "000300.SS"
    assert cfg["benchmark_map"][".BJ"] == "000300.SS"
    assert cfg["benchmark_map"][".HK"] == "^HSI"
    assert cfg["benchmark_map"][""] == "000300.SS"


def test_build_market_profile_for_cn_ticker():
    profile = build_market_profile("600519")

    assert profile["market"] == "CN"
    assert "A股市场交易规则" in profile["rules"]


def test_default_config_uses_a_h_benchmarks():
    from src.agents.tradingagents.default_config import DEFAULT_CONFIG

    bm = DEFAULT_CONFIG["benchmark_map"]
    assert bm[".SS"] == "000300.SS"
    assert bm[".SH"] == "000300.SS"
    assert bm[".SZ"] == "000300.SS"
    assert bm[".BJ"] == "000300.SS"
    assert bm[".HK"] == "^HSI"
    assert bm[""] == "000300.SS"
    assert "SPY" not in set(bm.values())


def test_graph_resolves_a_h_benchmarks():
    import sys
    from pathlib import Path

    agents_dir = Path("src/agents").resolve()
    if str(agents_dir) not in sys.path:
        sys.path.insert(0, str(agents_dir))

    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    graph.config = {
        "benchmark_ticker": None,
        "benchmark_map": {
            ".SS": "000300.SS",
            ".SH": "000300.SS",
            ".SZ": "000300.SS",
            ".BJ": "000300.SS",
            ".HK": "^HSI",
            "": "000300.SS",
        },
    }

    assert graph._resolve_benchmark("600519") == "000300.SS"
    assert graph._resolve_benchmark("600519.SH") == "000300.SS"
    assert graph._resolve_benchmark("000001.SZ") == "000300.SS"
    assert graph._resolve_benchmark("00700") == "^HSI"
    assert graph._resolve_benchmark("00700.HK") == "^HSI"
