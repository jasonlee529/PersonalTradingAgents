# tests/agents/test_trading_agents_wrapper.py
import pytest
from unittest.mock import MagicMock, patch


class TestTradingAgentsWrapper:
    """Tests for TradingAgentsWrapper with mocked TradingAgentsGraph."""

    def test_cannot_import_deleted_graph_adapter(self):
        """Verify GraphAdapter module no longer exists."""
        with pytest.raises(ImportError):
            import src.agents.graph_adapter

    def test_wrapper_imports(self):
        """TradingAgentsWrapper should be importable without TradingAgents."""
        with patch(
            "src.agents.trading_agents_wrapper.TradingAgentsWrapper._ensure_internal_tradingagents_on_path",
            return_value=None,
        ):
            from src.agents.trading_agents_wrapper import TradingAgentsWrapper
            assert TradingAgentsWrapper is not None

    def test_ensure_tradingagents_on_path_no_error(self):
        """_ensure_internal_tradingagents_on_path should not raise even without TradingAgents dir."""
        from src.agents.trading_agents_wrapper import TradingAgentsWrapper

        # Simply call it — no crash expected regardless of environment
        TradingAgentsWrapper._ensure_internal_tradingagents_on_path()

    def test_config_builder_maps_settings(self, test_settings):
        """TAConfigBuilder should map our Settings to TA config format."""
        from src.agents.wrapper import TAConfigBuilder

        builder = TAConfigBuilder(test_settings)

        mock_default = {
            "llm_provider": "deepseek",
            "deep_think_llm": "gpt-5.4",
            "quick_think_llm": "gpt-5.4-mini",
            "backend_url": None,
            "max_debate_rounds": 1,
            "max_risk_discuss_rounds": 1,
            "max_recur_limit": 100,
            "output_language": "English",
            "results_dir": "/tmp/old",
            "data_cache_dir": "/tmp/old_cache",
            "memory_log_path": "/tmp/old_memory",
            "checkpoint_enabled": False,
            "some_other_key": "should_survive",
        }

        cfg = builder.build(mock_default)

        assert cfg["llm_provider"] == "deepseek"
        assert cfg["api_key"] == test_settings.deepseek_api_key
        assert cfg["deep_think_llm"] == test_settings.get_llm_model("deepseek", "deep")
        assert cfg["quick_think_llm"] == test_settings.get_llm_model("deepseek", "quick")
        assert cfg["max_debate_rounds"] == test_settings.max_debate_rounds
        assert cfg["max_risk_discuss_rounds"] == test_settings.max_risk_discuss_rounds
        assert cfg["output_language"] == "Chinese"
        assert cfg["results_dir"] == str(test_settings.analysis_artifacts_dir)
        assert cfg["data_cache_dir"] == str(test_settings.runtime_cache_dir / "tradingagents")
        assert cfg["checkpoint_dir"] == str(test_settings.checkpoint_dir)
        assert cfg["memory_log_path"] == ""
        assert cfg["checkpoint_enabled"] is False
        # Unrelated keys should survive
        assert cfg["some_other_key"] == "should_survive"

    def test_graph_factory_preserves_frozen_job_models(self):
        from src.agents.wrapper.graph_factory import TAGraphFactory

        cfg = {
            "llm_provider": "deepseek",
            "deep_think_llm": "old-deep",
            "quick_think_llm": "old-quick",
        }

        TAGraphFactory._resolve_provider_models(cfg)

        assert cfg["deep_think_llm"] == "old-deep"
        assert cfg["quick_think_llm"] == "old-quick"

    def test_trading_graph_passes_config_api_key_to_clients(self):
        from src.agents.tradingagents.graph.trading_graph import TradingAgentsGraph

        graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
        graph.config = {
            "api_key": "sk-test",
            "llm_timeout": 123,
            "llm_max_retries": 2,
        }

        kwargs = graph._get_provider_kwargs()

        assert kwargs["api_key"] == "sk-test"
        assert kwargs["timeout"] == 123
        assert kwargs["max_retries"] == 2

    def test_analyze_works_without_knowledge_store(self, test_settings):
        """analyze() should work when knowledge_store is not provided."""
        import asyncio
        from src.knowledge.raw_store import RawStore
        from src.agents.trading_agents_wrapper import TradingAgentsWrapper

        mock_ta = MagicMock()
        mock_ta.propagator.create_initial_state = MagicMock(return_value={})
        mock_ta.propagate = MagicMock(return_value=(
            {"final_trade_decision": "hold"},
            "hold"
        ))

        wrapper = TradingAgentsWrapper.__new__(TradingAgentsWrapper)
        wrapper.settings = test_settings
        wrapper._ta = mock_ta
        wrapper._raw_store = RawStore(test_settings)
        wrapper._default_analysts = []
        wrapper._lock = asyncio.Lock()

        result = asyncio.run(wrapper.analyze("AAPL"))

        final_state, signal = result
        assert final_state["final_trade_decision"] == "hold"
        mock_ta.propagate.assert_called_once()

    def test_analyze_defaults_date_to_today(self, test_settings):
        """analyze() should default trade_date to today."""
        import asyncio
        from datetime import date
        from src.knowledge.raw_store import RawStore
        from src.agents.trading_agents_wrapper import TradingAgentsWrapper

        mock_ta = MagicMock()
        mock_ta.propagator.create_initial_state = MagicMock(return_value={})
        mock_ta.propagate = MagicMock(return_value=(
            {"final_trade_decision": "watch"},
            "watch"
        ))

        wrapper = TradingAgentsWrapper.__new__(TradingAgentsWrapper)
        wrapper.settings = test_settings
        wrapper._ta = mock_ta
        wrapper._raw_store = RawStore(test_settings)
        wrapper._default_analysts = []
        wrapper._lock = asyncio.Lock()

        asyncio.run(wrapper.analyze("TSLA"))

        call_args = mock_ta.propagate.call_args
        trade_date = call_args[0][1]
        assert trade_date == date.today().strftime("%Y-%m-%d")

    def test_wrapper_accepts_cache_param(self, test_settings):
        """TradingAgentsWrapper should accept an optional cache parameter."""
        import sys
        from unittest.mock import MagicMock, patch

        # Inject mock tradingagents modules so import succeeds
        mock_graph_mod = MagicMock()
        mock_graph_mod.TradingAgentsGraph = MagicMock()
        sys.modules["tradingagents"] = MagicMock()
        sys.modules["tradingagents.graph"] = MagicMock()
        sys.modules["tradingagents.graph.trading_graph"] = mock_graph_mod
        sys.modules["tradingagents.default_config"] = MagicMock()
        sys.modules["tradingagents.default_config"].DEFAULT_CONFIG = {}
        sys.modules["tradingagents.dataflows"] = MagicMock()
        sys.modules["tradingagents.dataflows.interface"] = MagicMock()
        sys.modules["tradingagents.dataflows.interface"].VENDOR_METHODS = {}
        sys.modules["tradingagents.dataflows.stockstats_utils"] = MagicMock()
        sys.modules["tradingagents.dataflows.stockstats_utils"].load_ohlcv = MagicMock()
        sys.modules["tradingagents.llm_clients"] = MagicMock()
        sys.modules["tradingagents.llm_clients.api_key_env"] = MagicMock()
        sys.modules["tradingagents.llm_clients.api_key_env"].get_api_key_env = MagicMock(return_value=None)
        sys.modules["tradingagents.llm_clients.provider_catalog"] = MagicMock()
        sys.modules["tradingagents.llm_clients.provider_catalog"].get_api_key_field = MagicMock(return_value="")
        sys.modules["tradingagents.agents"] = MagicMock()
        sys.modules["tradingagents.agents.analyst_registry"] = MagicMock()
        sys.modules["tradingagents.agents.analyst_registry"].AnalystRegistry = MagicMock()

        mock_cache = MagicMock()
        with patch("src.agents.trading_agents_wrapper.TradingAgentsWrapper._ensure_internal_tradingagents_on_path", return_value=None):
            from src.agents.trading_agents_wrapper import TradingAgentsWrapper
            wrapper = TradingAgentsWrapper(
                settings=test_settings,
                cache=mock_cache,
            )
            assert wrapper._data_bridge is not None

        # Cleanup
        for mod in [
            "tradingagents", "tradingagents.graph", "tradingagents.graph.trading_graph",
            "tradingagents.default_config", "tradingagents.dataflows", "tradingagents.dataflows.interface",
            "tradingagents.dataflows.stockstats_utils", "tradingagents.llm_clients", "tradingagents.llm_clients.api_key_env",
            "tradingagents.llm_clients.provider_catalog",
            "tradingagents.agents", "tradingagents.agents.analyst_registry",
        ]:
            sys.modules.pop(mod, None)
