# src/agents/trading_agents_wrapper.py
import sys
from pathlib import Path

_ta_dir = Path(__file__).resolve().parent
if str(_ta_dir) not in sys.path:
    sys.path.insert(0, str(_ta_dir))

import asyncio
import logging
from datetime import datetime
from typing import Any, Tuple

from src.config import Settings
from src.agents.analysis_memory import load_raw_memory_context
from src.agents.wrapper import (
    TAConfigBuilder,
    TAGraphFactory,
    PhaseReporterEventHandler,
)
from src.agents.wrapper.market_rules import build_market_profile
from src.knowledge.raw_store import RawStore
from tradingagents.agents.analyst_registry import AnalystRegistry

logger = logging.getLogger(__name__)


class TradingAgentsWrapper:
    """Thin orchestrator: delegates all work to focused helper classes."""

    def __init__(
        self,
        settings: Settings,
        cache: Any = None,
    ):
        self.settings = settings
        self._lock = asyncio.Lock()
        self._data_bridge = None
        self._raw_store = RawStore(settings)
        self._ta = None

        settings.ensure_dirs()
        self._ensure_internal_tradingagents_on_path()
        self._inject_api_key_to_env("deepseek")

        from tradingagents.default_config import DEFAULT_CONFIG

        if cache is not None:
            from src.data.collector import DataCollector
            from src.agents.data_bridge import DataBridge

            collector = DataCollector(settings, cache)
            self._data_bridge = DataBridge(settings)
            self._data_bridge.set_collector(collector)
            self._data_bridge.register_vendor()
            self._data_bridge.patch_load_ohlcv()

            # Wire collector into signal tools so they can fetch real data
            from src.agents import signal_tools
            signal_tools.set_collector(collector)

        config_builder = TAConfigBuilder(settings)
        self._ta_config = config_builder.build(DEFAULT_CONFIG)
        self._default_analysts = AnalystRegistry.default_names()

        self._graph_factory = TAGraphFactory(self._ta_config)
        if settings.signal_tools_enabled:
            from src.agents.signal_tools import SIGNAL_TOOLS

            self._ta_config["extra_tools"] = list(SIGNAL_TOOLS)

        if settings.signal_tools_enabled:
            logger.debug("Signal tools enabled via TradingAgentsGraph extra_tools config")

    @staticmethod
    def _ensure_internal_tradingagents_on_path() -> None:
        agents_dir = Path(__file__).resolve().parent
        agents_str = str(agents_dir)
        if agents_str not in sys.path:
            sys.path.insert(0, agents_str)

    def _inject_api_key_to_env(self, provider: str | None = None) -> None:
        """Inject API key for the given (or configured) provider into os.environ.

        When config_overrides change the provider mid-run (e.g. user picks
        Kimi on the Analysis page), the correct key must be present in the
        environment before the LLM client is created.
        """
        p = provider or "deepseek"
        try:
            from tradingagents.llm_clients.api_key_env import get_api_key_env
            from tradingagents.llm_clients.provider_catalog import get_api_key_field
        except ImportError:
            logger.debug("TradingAgents LLM provider catalog unavailable; skipping API key env injection")
            return
        env_var = get_api_key_env(p)
        if not env_var:
            # Provider might have been added after the worker started;
            # reload the catalog and retry once.
            if self._try_reload_provider_catalog():
                env_var = get_api_key_env(p)
            if not env_var:
                return
        key_field = get_api_key_field(p)
        if key_field:
            api_key = getattr(self.settings, key_field, "")
            if api_key:
                import os
                os.environ[env_var] = api_key

    @staticmethod
    def _try_reload_provider_catalog() -> bool:
        """Reload cached provider modules so long-running workers pick up
        newly registered providers without a full restart."""
        import importlib
        import sys
        import types

        reloaded = False
        for key in (
            "tradingagents.llm_clients.provider_catalog",
            "tradingagents.llm_clients.factory",
        ):
            mod = sys.modules.get(key)
            if isinstance(mod, types.ModuleType):
                try:
                    importlib.reload(mod)
                    reloaded = True
                except Exception:
                    pass
        return reloaded

    async def analyze(
        self,
        ticker: str,
        trade_date: str = None,
        selected_analysts: list[str] = None,
        config_overrides: dict = None,
        company_name: str = None,
        phase_reporter: Any = None,
    ) -> Tuple[dict, Any]:
        if trade_date is None:
            trade_date = datetime.now().strftime("%Y-%m-%d")

        past_context = await load_raw_memory_context(self._raw_store, ticker)

        use_custom = (
            selected_analysts is not None
            and selected_analysts != self._default_analysts
        ) or bool(config_overrides)

        # If user overrides the provider (e.g. via AnalysisPage), ensure the
        # matching API key is in the environment before the graph is built.
        if config_overrides and config_overrides.get("llm_provider"):
            provider = str(config_overrides["llm_provider"]).lower()
            self._inject_api_key_to_env(provider)
            config_overrides = {
                **config_overrides,
                "api_key": self.settings.get_llm_api_key(provider),
                "deep_think_llm": self.settings.get_llm_model(provider, "deep"),
                "quick_think_llm": self.settings.get_llm_model(provider, "quick"),
            }

        if use_custom:
            graph = self._graph_factory.create(selected_analysts, config_overrides)
        else:
            if self._ta is None:
                self._ta = self._graph_factory.create(selected_analysts=self._default_analysts)
            graph = self._ta

        loop = asyncio.get_running_loop()
        if phase_reporter:
            await phase_reporter.on_node_start("preparing", "初始化分析环境...")
            await phase_reporter.on_node_end("preparing")
            await phase_reporter.on_node_start("data_start", "收集市场数据...")

        async with self._lock:
            event_handler = None
            stream = False
            if phase_reporter:
                event_handler = PhaseReporterEventHandler(phase_reporter, loop)
                stream = True

            def context_provider(company_name, context_trade_date, asset_type):
                return past_context

            previous_market_profile = graph.config.get("market_profile")
            graph.config["market_profile"] = build_market_profile(ticker)

            try:
                final_state, signal = await asyncio.to_thread(
                    graph.propagate,
                    ticker,
                    trade_date,
                    context_provider=context_provider,
                    event_handler=event_handler,
                    stream=stream,
                )
                if phase_reporter:
                    await phase_reporter.on_complete()

                if self.settings.quality_gate_enabled:
                    from src.agents.quality_gate import run_quality_gate

                    llm_client = None
                    try:
                        from tradingagents.llm_clients import create_llm_client

                        qg_kwargs = {}
                        if self.settings.test_mode:
                            qg_kwargs["test_mode"] = True
                        provider = (
                            config_overrides.get("llm_provider")
                            if config_overrides
                            else None
                        ) or "deepseek"
                        client = create_llm_client(
                            provider=provider,
                            model=self.settings.get_llm_model(provider, "quick"),
                            **qg_kwargs,
                        )
                        llm_client = client.get_llm()
                    except Exception as e:
                        logger.warning(
                            "Failed to create LLM client for quality gate: %s", e
                        )

                    final_state["data_quality_summary"] = await asyncio.to_thread(
                        run_quality_gate, final_state, llm_client
                    )

                return final_state, signal
            finally:
                if previous_market_profile is None:
                    graph.config.pop("market_profile", None)
                else:
                    graph.config["market_profile"] = previous_market_profile
