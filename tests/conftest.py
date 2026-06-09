# tests/conftest.py
import pytest
from pathlib import Path
import tempfile
import shutil


@pytest.fixture
def temp_dir():
    path = Path(tempfile.mkdtemp())
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def test_settings(temp_dir):
    from src.config import Settings
    s = Settings(
        _env_file=None,
        settings_env_path=temp_dir / ".env",
        data_dir=temp_dir / "data",
        knowledge_dir=temp_dir / "data" / "knowledge",
        cache_db_path=temp_dir / "data" / "db" / "cache.db",
        portfolio_db_path=temp_dir / "data" / "db" / "portfolio.db",
        analysis_db_path=temp_dir / "data" / "db" / "analysis.db",
        raw_knowledge_db_path=temp_dir / "data" / "knowledge" / "raw" / "index.db",
        wiki_knowledge_dir=temp_dir / "data" / "knowledge" / "wiki",
        wiki_knowledge_db_path=temp_dir / "data" / "knowledge" / "wiki" / "index.db",
        wiki_schema_dir=temp_dir / "data" / "knowledge" / "schema",
        derived_knowledge_dir=temp_dir / "data" / "knowledge" / "derived",
        derived_knowledge_db_path=temp_dir / "data" / "knowledge" / "derived" / "index.db",
        analysis_worker_enabled=False,
        historical_db_path=temp_dir / "data" / "db" / "historical.db",
        runtime_cache_dir=temp_dir / "data" / "cache",
        analysis_artifacts_dir=temp_dir / "data" / "artifacts" / "analysis",
        checkpoint_dir=temp_dir / "data" / "db" / "checkpoints",
        test_mode=True,
        xueqiu_auto_cookie=False,
    )
    s.ensure_dirs()
    return s
