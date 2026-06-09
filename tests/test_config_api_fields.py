from pathlib import Path
from src.config import Settings


def test_api_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    s = Settings(_env_file=None)
    assert s.api_host == "127.0.0.1"
    assert s.api_port == 8000
    assert s.cors_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]
    assert isinstance(s.cors_origins, list)
    assert "http://localhost:5173" in s.cors_origins
    assert "http://127.0.0.1:5173" in s.cors_origins


def test_api_env_override(monkeypatch):
    monkeypatch.setenv("API_HOST", "0.0.0.0")
    monkeypatch.setenv("API_PORT", "8080")
    monkeypatch.setenv("XUEQIU_COOKIE", "xq_a_token=abc")
    monkeypatch.setenv("XUEQIU_AUTO_COOKIE", "false")
    monkeypatch.setenv("XUEQIU_TIMEOUT", "7")
    s = Settings(_env_file=None)
    assert s.api_host == "0.0.0.0"
    assert s.api_port == 8080
    assert s.xueqiu_cookie == "xq_a_token=abc"
    assert s.xueqiu_auto_cookie is False
    assert s.xueqiu_timeout == 7.0


def test_portfolio_driven_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    s = Settings(_env_file=None)
    assert s.wiki_auto_analysis_enabled is False
    assert s.critical_event_score_threshold == 0.85
    assert s.news_ingest_limit_per_symbol == 10


def test_portfolio_driven_env_override(monkeypatch):
    monkeypatch.setenv("WIKI_AUTO_ANALYSIS_ENABLED", "true")
    monkeypatch.setenv("CRITICAL_EVENT_SCORE_THRESHOLD", "0.90")
    monkeypatch.setenv("NEWS_INGEST_LIMIT_PER_SYMBOL", "20")
    s = Settings(_env_file=None)
    assert s.wiki_auto_analysis_enabled is True
    assert s.critical_event_score_threshold == 0.90
    assert s.news_ingest_limit_per_symbol == 20


def test_wiki_settings_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    defaults = Settings.model_fields
    assert defaults["knowledge_dir"].default == Path("./data/knowledge")
    assert defaults["raw_knowledge_dir"].default == Path("./data/knowledge/raw")
    assert defaults["raw_knowledge_db_path"].default == Path("./data/knowledge/raw/index.db")
    assert defaults["wiki_knowledge_dir"].default == Path("./data/knowledge/wiki")
    assert defaults["wiki_knowledge_db_path"].default == Path("./data/knowledge/wiki/index.db")
    assert defaults["wiki_schema_dir"].default == Path("./data/knowledge/schema")
    assert defaults["wiki_ingest_batch_size"].default == 10
    assert defaults["wiki_llm_provider"].default == ""


def test_wiki_settings_env_override(monkeypatch):
    monkeypatch.setenv("WIKI_INGEST_BATCH_SIZE", "20")
    monkeypatch.setenv("WIKI_LLM_PROVIDER", "kimi")
    s = Settings(_env_file=None)
    assert s.wiki_ingest_batch_size == 20
    assert s.wiki_llm_provider == "kimi"


def test_derived_settings_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    defaults = Settings.model_fields
    assert defaults["derived_knowledge_dir"].default == Path("./data/knowledge/derived")
    assert defaults["derived_knowledge_db_path"].default == Path("./data/knowledge/derived/index.db")


def test_runtime_path_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    defaults = Settings.model_fields
    assert defaults["runtime_cache_dir"].default == Path("./data/cache")
    assert defaults["analysis_artifacts_dir"].default == Path("./data/artifacts/analysis")
    assert defaults["cache_db_path"].default == Path("./data/db/cache.db")
    assert defaults["portfolio_db_path"].default == Path("./data/db/portfolio.db")
    assert defaults["analysis_db_path"].default == Path("./data/db/analysis.db")
    assert defaults["historical_db_path"].default == Path("./data/db/historical.db")
    assert defaults["fund_holdings_db_path"].default == Path("./data/db/fund_holdings.db")
    assert defaults["checkpoint_dir"].default == Path("./data/db/checkpoints")


def test_derived_settings_env_override(monkeypatch):
    monkeypatch.setenv("DERIVED_KNOWLEDGE_DIR", "./custom/derived")
    monkeypatch.setenv("DERIVED_KNOWLEDGE_DB_PATH", "./custom/derived/db.sqlite")
    s = Settings(_env_file=None)
    assert s.derived_knowledge_dir == Path("./custom/derived")
    assert s.derived_knowledge_db_path == Path("./custom/derived/db.sqlite")

def test_get_llm_api_key_mapping():
    from src.config import Settings

    s = Settings()
    s.openai_api_key = "sk-openai"
    assert s.get_llm_api_key("openai") == "sk-openai"

    s.deepseek_api_key = "sk-deepseek"
    assert s.get_llm_api_key("deepseek") == "sk-deepseek"

    s.kimi_api_key = "sk-kimi"
    assert s.get_llm_api_key("kimi") == "sk-kimi"

    assert s.get_llm_api_key("unknown-provider") == ""


def test_get_llm_model_uses_provider_override_or_catalog_default(monkeypatch):
    monkeypatch.delenv("KIMI_QUICK_MODEL", raising=False)
    s = Settings(_env_file=None)
    assert s.get_llm_model("kimi", "quick") == "kimi-k2.6"

    s.kimi_quick_model = "custom-kimi-quick"
    assert s.get_llm_model("kimi", "quick") == "custom-kimi-quick"
