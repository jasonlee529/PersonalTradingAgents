"""Map our Settings to TradingAgents config format."""
from src.config import Settings


class TAConfigBuilder:
    """Build TradingAgents config dict from our Settings."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def build(self, base_config: dict) -> dict:
        cfg = base_config.copy()
        provider = str(cfg.get("llm_provider") or "deepseek").lower()
        cfg.update({
            "llm_provider": provider,
            # Pass the configured API key through the TradingAgents config so
            # LLM client creation does not depend on inherited process env.
            "api_key": self.settings.get_llm_api_key(provider),
            "deep_think_llm": self.settings.get_llm_model(provider, "deep"),
            "quick_think_llm": self.settings.get_llm_model(provider, "quick"),
            "backend_url": None,
            "max_debate_rounds": self.settings.max_debate_rounds,
            "max_risk_discuss_rounds": self.settings.max_risk_discuss_rounds,
            "max_recur_limit": self.settings.max_recur_limit,
            "output_language": self.settings.ta_output_language,
            "results_dir": str(self.settings.analysis_artifacts_dir),
            "data_cache_dir": str(self.settings.runtime_cache_dir / "tradingagents"),
            "checkpoint_dir": str(self.settings.checkpoint_dir),
            "memory_log_path": "",
            "checkpoint_enabled": self.settings.checkpoint_enabled,
            "test_mode": self.settings.test_mode,
            "llm_timeout": self.settings.llm_timeout,
        })
        cfg.setdefault("benchmark_map", {})
        cfg["benchmark_map"].update({
            ".SS": "000300.SS",
            ".SH": "000300.SS",
            ".SZ": "000300.SS",
            ".BJ": "000300.SS",
            ".HK": "^HSI",
            "": "000300.SS",
        })
        cfg["data_vendors"] = {
            "core_stock_apis": self.settings.ta_data_vendor,
            "technical_indicators": self.settings.ta_data_vendor,
            "fundamental_data": self.settings.ta_data_vendor,
            "news_data": self.settings.ta_data_vendor,
        }
        return cfg
