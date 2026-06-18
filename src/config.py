# src/config.py
from pathlib import Path
from typing import Any
from pydantic_settings import BaseSettings, SettingsConfigDict


PERSISTED_SETTINGS_FIELDS: dict[str, str] = {
    "daily_direction_llm_provider": "DAILY_DIRECTION_LLM_PROVIDER",
    "wiki_llm_provider": "WIKI_LLM_PROVIDER",
    "openai_quick_model": "OPENAI_QUICK_MODEL",
    "openai_deep_model": "OPENAI_DEEP_MODEL",
    "deepseek_quick_model": "DEEPSEEK_QUICK_MODEL",
    "deepseek_deep_model": "DEEPSEEK_DEEP_MODEL",
    "anthropic_quick_model": "ANTHROPIC_QUICK_MODEL",
    "anthropic_deep_model": "ANTHROPIC_DEEP_MODEL",
    "google_quick_model": "GOOGLE_QUICK_MODEL",
    "google_deep_model": "GOOGLE_DEEP_MODEL",
    "azure_quick_model": "AZURE_QUICK_MODEL",
    "azure_deep_model": "AZURE_DEEP_MODEL",
    "xai_quick_model": "XAI_QUICK_MODEL",
    "xai_deep_model": "XAI_DEEP_MODEL",
    "qwen_quick_model": "QWEN_QUICK_MODEL",
    "qwen_deep_model": "QWEN_DEEP_MODEL",
    "qwen_cn_quick_model": "QWEN_CN_QUICK_MODEL",
    "qwen_cn_deep_model": "QWEN_CN_DEEP_MODEL",
    "glm_quick_model": "GLM_QUICK_MODEL",
    "glm_deep_model": "GLM_DEEP_MODEL",
    "glm_cn_quick_model": "GLM_CN_QUICK_MODEL",
    "glm_cn_deep_model": "GLM_CN_DEEP_MODEL",
    "minimax_quick_model": "MINIMAX_QUICK_MODEL",
    "minimax_deep_model": "MINIMAX_DEEP_MODEL",
    "minimax_cn_quick_model": "MINIMAX_CN_QUICK_MODEL",
    "minimax_cn_deep_model": "MINIMAX_CN_DEEP_MODEL",
    "openrouter_quick_model": "OPENROUTER_QUICK_MODEL",
    "openrouter_deep_model": "OPENROUTER_DEEP_MODEL",
    "kimi_quick_model": "KIMI_QUICK_MODEL",
    "kimi_deep_model": "KIMI_DEEP_MODEL",
    "opencode_go_quick_model": "OPENCODE_GO_QUICK_MODEL",
    "opencode_go_deep_model": "OPENCODE_GO_DEEP_MODEL",
    "ollama_quick_model": "OLLAMA_QUICK_MODEL",
    "ollama_deep_model": "OLLAMA_DEEP_MODEL",
    "llamacpp_quick_model": "LLAMACPP_QUICK_MODEL",
    "llamacpp_deep_model": "LLAMACPP_DEEP_MODEL",
    "openai_api_key": "OPENAI_API_KEY",
    "deepseek_api_key": "DEEPSEEK_API_KEY",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "google_api_key": "GOOGLE_API_KEY",
    "azure_openai_api_key": "AZURE_OPENAI_API_KEY",
    "xai_api_key": "XAI_API_KEY",
    "dashscope_api_key": "DASHSCOPE_API_KEY",
    "dashscope_cn_api_key": "DASHSCOPE_CN_API_KEY",
    "zhipu_api_key": "ZHIPU_API_KEY",
    "zhipu_cn_api_key": "ZHIPU_CN_API_KEY",
    "minimax_api_key": "MINIMAX_API_KEY",
    "minimax_cn_api_key": "MINIMAX_CN_API_KEY",
    "openrouter_api_key": "OPENROUTER_API_KEY",
    "kimi_api_key": "KIMI_API_KEY",
    "opencode_go_api_key": "OPENCODE_GO_API_KEY",
    "scheduler_enabled": "SCHEDULER_ENABLED",
    "analysis_schedule": "ANALYSIS_SCHEDULE",
    "daily_direction_notification_enabled": "DAILY_DIRECTION_NOTIFICATION_ENABLED",
    "notification_report_channels": "NOTIFICATION_REPORT_CHANNELS",
    "wechat_webhook_url": "WECHAT_WEBHOOK_URL",
    "wechat_msg_type": "WECHAT_MSG_TYPE",
    "wechat_max_bytes": "WECHAT_MAX_BYTES",
    "feishu_webhook_url": "FEISHU_WEBHOOK_URL",
    "feishu_webhook_secret": "FEISHU_WEBHOOK_SECRET",
    "feishu_webhook_keyword": "FEISHU_WEBHOOK_KEYWORD",
    "feishu_max_bytes": "FEISHU_MAX_BYTES",
    "email_sender": "EMAIL_SENDER",
    "email_password": "EMAIL_PASSWORD",
    "email_receivers": "EMAIL_RECEIVERS",
    "email_sender_name": "EMAIL_SENDER_NAME",
    "webhook_verify_ssl": "WEBHOOK_VERIFY_SSL",
    "test_mode": "TEST_MODE",
    "trade_commission_rate": "TRADE_COMMISSION_RATE",
    "trade_min_commission": "TRADE_MIN_COMMISSION",
    "trade_stamp_tax_rate": "TRADE_STAMP_TAX_RATE",
    "trade_transfer_fee_rate": "TRADE_TRANSFER_FEE_RATE",
    "news_article_limit": "NEWS_ARTICLE_LIMIT",
    "global_news_article_limit": "GLOBAL_NEWS_ARTICLE_LIMIT",
    "global_news_lookback_days": "GLOBAL_NEWS_LOOKBACK_DAYS",
    "xueqiu_cookie": "XUEQIU_COOKIE",
    "xueqiu_auto_cookie": "XUEQIU_AUTO_COOKIE",
    "xueqiu_timeout": "XUEQIU_TIMEOUT",
    "tushare_api_key": "TUSHARE_API_KEY",
    "fund_holdings_refresh_enabled": "FUND_HOLDINGS_REFRESH_ENABLED",
    "fund_holdings_refresh_schedule": "FUND_HOLDINGS_REFRESH_SCHEDULE",
}


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _stringify_env_value(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def persist_env_file_values(path: Path | str, values: dict[str, Any]) -> None:
    """Update or append key/value pairs in a .env file."""
    env_path = Path(path)
    if not env_path.is_absolute():
        env_path = Path(__file__).resolve().parents[1] / env_path
    if not env_path.exists():
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text("", encoding="utf-8")

    lines = env_path.read_text(encoding="utf-8").splitlines()
    existing: dict[str, int] = {}
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        existing[key] = idx

    for key, value in values.items():
        if value is None:
            continue
        str_value = _stringify_env_value(value)
        if key in existing:
            lines[existing[key]] = f"{key}={str_value}"
        else:
            lines.append(f"{key}={str_value}")
            existing[key] = len(lines) - 1

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_settings_from_env_file(path: Path | str = ".env") -> "Settings":
    """Load settings from .env with those values overriding stale process env.

    The analysis worker is a child process, so its environment does not change
    when the web UI saves a new .env. Passing parsed .env values as init kwargs
    gives them priority over stale inherited environment variables.
    """
    env_path = Path(path)
    if not env_path.is_absolute():
        env_path = Path(__file__).resolve().parents[1] / env_path
    env_values = _parse_env_file(env_path)
    kwargs = {
        field: env_values[env_var]
        for field, env_var in PERSISTED_SETTINGS_FIELDS.items()
        if env_var in env_values
    }
    return Settings(**kwargs)


class Settings(BaseSettings):
    deploy_mode: int = 0
    settings_env_path: Path = Path(".env")
    data_dir: Path = Path("./data")
    knowledge_dir: Path = Path("./data/knowledge")
    raw_knowledge_dir: Path = Path("./data/knowledge/raw")

    # Wiki knowledge layer
    wiki_knowledge_dir: Path = Path("./data/knowledge/wiki")
    wiki_knowledge_db_path: Path = Path("./data/knowledge/wiki/index.db")
    wiki_schema_dir: Path = Path("./data/knowledge/schema")

    # Derived knowledge layer
    derived_knowledge_dir: Path = Path("./data/knowledge/derived")
    derived_knowledge_db_path: Path = Path("./data/knowledge/derived/index.db")
    wiki_ingest_batch_size: int = 10

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Databases
    cache_db_path: Path = Path("./data/db/cache.db")
    portfolio_db_path: Path = Path("./data/db/portfolio.db")
    analysis_db_path: Path = Path("./data/db/analysis.db")
    raw_knowledge_db_path: Path = Path("./data/knowledge/raw/index.db")
    runtime_cache_dir: Path = Path("./data/cache")
    analysis_artifacts_dir: Path = Path("./data/artifacts/analysis")
    checkpoint_dir: Path = Path("./data/db/checkpoints")

    # Cache TTLs (seconds)
    cache_ttl_quotes: int = 300
    cache_ttl_kline: int = 3600
    cache_ttl_news: int = 86400
    cache_ttl_fundamentals: int = 604800
    cache_ttl_indicators: int = 3600
    cache_ttl_announcements: int = 86400
    cache_ttl_research_reports: int = 604800

    # Local historical data storage (default on, not exposed in settings UI)
    local_history_enabled: bool = True
    historical_db_path: Path = Path("./data/db/historical.db")
    historical_refresh_schedule: str = "0 6 * * 1-5"

    # News limits used by survey scripts and yfinance-based data flows
    news_article_limit: int = 20
    global_news_article_limit: int = 10
    global_news_lookback_days: int = 7

    # Fund holdings (Tushare Pro, config-driven, default off)
    tushare_api_key: str = ""
    fund_holdings_db_path: Path = Path("./data/db/fund_holdings.db")
    fund_holdings_refresh_enabled: bool = False
    fund_holdings_refresh_schedule: str = "0 2 * * 1-5"

    # LLM
    daily_direction_llm_provider: str = ""
    wiki_llm_provider: str = ""
    openai_quick_model: str = ""
    openai_deep_model: str = ""
    deepseek_quick_model: str = ""
    deepseek_deep_model: str = ""
    anthropic_quick_model: str = ""
    anthropic_deep_model: str = ""
    google_quick_model: str = ""
    google_deep_model: str = ""
    azure_quick_model: str = ""
    azure_deep_model: str = ""
    xai_quick_model: str = ""
    xai_deep_model: str = ""
    qwen_quick_model: str = ""
    qwen_deep_model: str = ""
    qwen_cn_quick_model: str = ""
    qwen_cn_deep_model: str = ""
    glm_quick_model: str = ""
    glm_deep_model: str = ""
    glm_cn_quick_model: str = ""
    glm_cn_deep_model: str = ""
    minimax_quick_model: str = ""
    minimax_deep_model: str = ""
    minimax_cn_quick_model: str = ""
    minimax_cn_deep_model: str = ""
    openrouter_quick_model: str = ""
    openrouter_deep_model: str = ""
    kimi_quick_model: str = ""
    kimi_deep_model: str = ""
    opencode_go_quick_model: str = ""
    opencode_go_deep_model: str = ""
    ollama_quick_model: str = ""
    ollama_deep_model: str = ""
    llamacpp_quick_model: str = ""
    llamacpp_deep_model: str = ""
    llm_timeout: float = 600.0

    # Sector Discovery — mock mode returns hard-coded templates without LLM calls
    sector_discovery_mock_mode: bool = False

    # API keys per provider (mirrors TradingAgents api_key_env.py)
    openai_api_key: str = ""
    deepseek_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""
    azure_openai_api_key: str = ""
    xai_api_key: str = ""
    dashscope_api_key: str = ""
    dashscope_cn_api_key: str = ""
    zhipu_api_key: str = ""
    zhipu_cn_api_key: str = ""
    minimax_api_key: str = ""
    minimax_cn_api_key: str = ""
    openrouter_api_key: str = ""
    kimi_api_key: str = ""
    opencode_go_api_key: str = ""

    # Graph
    max_debate_rounds: int = 2
    max_risk_discuss_rounds: int = 2
    max_recur_limit: int = 100

    # Scheduler
    scheduler_enabled: bool = False
    analysis_schedule: str = "0 9 * * 1-5"
    analysis_worker_enabled: bool = True
    # Maximum seconds a single analysis job may run before being cancelled.
    # Prevents orphaned "running" status when an LLM call hangs indefinitely.
    analysis_timeout_seconds: int = 600  # 10 minutes

    # Data source priority (fallback chain per data type)
    # Priority: sina/eastmoney/tencent > baostock
    data_source_priority: dict[str, list[str]] = {
        "quote": ["tencent", "eastmoney", "sina", "baostock"],
        "kline": ["sina", "eastmoney", "tencent", "baostock"],
        "fundamentals": ["tencent", "eastmoney", "sina"],
        "news": ["xueqiu", "eastmoney", "sina"],
        "global_news": ["eastmoney", "cls"],
        "balance_sheet": ["sina", "eastmoney"],
        "cashflow": ["sina", "eastmoney"],
        "income_statement": ["sina", "eastmoney"],
        "consensus_expectations": ["ths"],
        "market_heatmap": ["ths"],
        "cross_border_flow": ["ths"],
        "theme_exposure": ["baidu"],
        "concept_boards": ["eastmoney"],
        "industry_boards": ["eastmoney"],
        "board_stocks": ["eastmoney"],
        "order_flow_profile": ["eastmoney"],
        "trading_seat_activity": ["eastmoney"],
        "supply_unlock_schedule": ["eastmoney"],
        "peer_industry_snapshot": ["eastmoney"],
        "announcements": ["ths", "cninfo"],
        "research_reports": ["eastmoney"],
        "limit_up_stocks": ["eastmoney", "tdx", "sina", "tushare"],
        "market_list": ["eastmoney", "tushare"],
    }

    # TradingAgents integration
    ta_output_language: str = "Chinese"
    ta_data_vendor: str = "data"

    # Xueqiu requires an authenticated Cookie. Missing/invalid cookies simply
    # disable the source and let news collection fall back to lower-priority sources.
    xueqiu_cookie: str = ""
    xueqiu_auto_cookie: bool = True
    xueqiu_timeout: float = 10.0

    # Logging
    log_retention_days: int = 7

    # Test mode: bypass real LLM calls with mock responses (saves tokens)
    test_mode: bool = False

    # Task 4: Quality Gate + Signal Tools (config-driven, default off)
    quality_gate_enabled: bool = False
    signal_tools_enabled: bool = False

    # Checkpoint / resume
    checkpoint_enabled: bool = False

    # Trade fee defaults for CN A-share daily trade log.
    # Rates are decimal fractions: 0.00025 = 0.025%.
    trade_commission_rate: float = 0.00025
    trade_min_commission: float = 5.0
    trade_stamp_tax_rate: float = 0.0005
    trade_transfer_fee_rate: float = 0.00001

    # Portfolio-driven auto analysis
    wiki_auto_analysis_enabled: bool = False
    critical_event_score_threshold: float = 0.85
    news_ingest_limit_per_symbol: int = 10

    # Embedding (config-driven, default off)
    auto_embedding_enabled: bool = False

    # Notification channels
    notification_enabled: bool = False
    daily_direction_notification_enabled: bool = False
    wechat_webhook_url: str = ""
    wechat_msg_type: str = "markdown"  # markdown | text
    wechat_max_bytes: int = 4000
    feishu_webhook_url: str = ""
    feishu_webhook_secret: str = ""
    feishu_webhook_keyword: str = ""
    feishu_max_bytes: int = 20000
    email_sender: str = ""
    email_password: str = ""
    email_receivers: str = ""  # comma-separated
    email_sender_name: str = "TradingAgents"
    webhook_verify_ssl: bool = True
    notification_report_channels: str = ""  # comma-separated: wechat,feishu,email
    notification_alert_channels: str = ""
    notification_system_error_channels: str = ""

    # Feature flags
    feature_flags: dict[str, bool] = {}

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=("model_",),
    )

    def ensure_dirs(self) -> None:
        if self.knowledge_dir != Path("./data/knowledge"):
            if self.raw_knowledge_dir == Path("./data/knowledge/raw"):
                self.raw_knowledge_dir = self.knowledge_dir / "raw"
            if self.raw_knowledge_db_path == Path("./data/knowledge/raw/index.db"):
                self.raw_knowledge_db_path = self.raw_knowledge_dir / "index.db"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        self.raw_knowledge_dir.mkdir(parents=True, exist_ok=True)
        self.raw_knowledge_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.wiki_knowledge_dir.mkdir(parents=True, exist_ok=True)
        self.wiki_knowledge_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.wiki_schema_dir.mkdir(parents=True, exist_ok=True)
        self.derived_knowledge_dir.mkdir(parents=True, exist_ok=True)
        self.derived_knowledge_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.portfolio_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.analysis_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.historical_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.fund_holdings_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.runtime_cache_dir.mkdir(parents=True, exist_ok=True)
        self.analysis_artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def _reload_provider_catalog(self) -> None:
        """Reload the provider catalog module so long-running workers pick up
        code changes without needing a full restart."""
        import importlib
        import sys
        import types

        for key in (
            "src.agents.tradingagents.llm_clients.provider_catalog",
            "tradingagents.llm_clients.provider_catalog",
            "src.agents.tradingagents.llm_clients.factory",
            "tradingagents.llm_clients.factory",
        ):
            mod = sys.modules.get(key)
            if isinstance(mod, types.ModuleType):
                try:
                    importlib.reload(mod)
                except Exception:
                    pass

    def get_llm_api_key(self, provider: str) -> str:
        """Return the API key for an LLM provider."""
        self._reload_provider_catalog()
        from src.agents.tradingagents.llm_clients.provider_catalog import get_api_key_field

        key_field = get_api_key_field(provider)
        return getattr(self, key_field, "") if key_field else ""

    def get_llm_model(self, provider: str, llm_type: str) -> str:
        """Return provider-specific model override, falling back to catalog default."""
        self._reload_provider_catalog()
        from src.agents.tradingagents.llm_clients.provider_catalog import (
            get_model_settings_field,
            resolve_model,
        )

        field = get_model_settings_field(provider, llm_type)
        model = getattr(self, field, "")
        return model or resolve_model(provider, llm_type)


settings = Settings()

