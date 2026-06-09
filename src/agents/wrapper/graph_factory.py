"""Factory for TradingAgentsGraph with A-share benchmark patch."""
from typing import Any

from src.agents.tradingagents.llm_clients.provider_catalog import resolve_model
from src.utils.ticker import detect_market


class TAGraphFactory:
    """Create TradingAgentsGraph instances with A-share benchmark patching."""

    def __init__(self, ta_config: dict):
        self.ta_config = ta_config

    def create(
        self,
        selected_analysts: list[str] = None,
        config_overrides: dict = None,
    ) -> Any:
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        cfg = self.ta_config.copy()
        if config_overrides:
            cfg.update(config_overrides)
        self._resolve_provider_models(cfg)

        graph = TradingAgentsGraph(
            selected_analysts=selected_analysts or self.ta_config.get("_default_analysts", ["market", "social", "news", "fundamentals"]),
            debug=False,
            config=cfg,
        )
        self._apply_benchmark_patch(graph)
        return graph

    @staticmethod
    def _resolve_provider_models(cfg: dict) -> None:
        provider = str(cfg.get("llm_provider") or "").lower()
        if not provider:
            return
        cfg.setdefault("deep_think_llm", resolve_model(provider, "deep"))
        cfg.setdefault("quick_think_llm", resolve_model(provider, "quick"))

    def _apply_benchmark_patch(self, graph: Any) -> None:
        """Override _resolve_benchmark so A-share tickers use CSI 300."""
        if not hasattr(graph, "_resolve_benchmark"):
            return
        original_resolve = graph._resolve_benchmark

        def _resolve_benchmark_for_cn(ticker: str) -> str:
            if detect_market(ticker) == "CN":
                return "000300.SS"
            return original_resolve(ticker)

        graph._resolve_benchmark = _resolve_benchmark_for_cn
