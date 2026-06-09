import pytest

from src.knowledge.raw_migrate import classify_legacy_file, migrate_raw


def test_classify_legacy_stock_analysis(test_settings):
    path = test_settings.knowledge_dir / "603738" / "2026-06-04" / "01_market_report_095641.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# report", encoding="utf-8")

    classified = classify_legacy_file(path, test_settings.knowledge_dir)
    assert classified is not None
    assert classified["source_kind"] == "stock_analysis"
    assert classified["metadata"]["analysis_node"] == "market_report"


@pytest.mark.asyncio
async def test_raw_migrate_dry_run_counts(test_settings):
    stock_path = test_settings.knowledge_dir / "603738" / "2026-06-04" / "99_full_report_095641.md"
    stock_path.parent.mkdir(parents=True, exist_ok=True)
    stock_path.write_text("# full", encoding="utf-8")

    direction_path = test_settings.knowledge_dir / "market_overview" / "2026-06-04" / "50_sector_discovery_092027.md"
    direction_path.parent.mkdir(parents=True, exist_ok=True)
    direction_path.write_text("# direction", encoding="utf-8")

    chunk_path = test_settings.knowledge_dir / "ab" / "abcdef.md"
    chunk_path.parent.mkdir(parents=True, exist_ok=True)
    chunk_path.write_text("# chunk", encoding="utf-8")

    summary = await migrate_raw(test_settings, dry_run=True)
    assert summary["stock_analysis"] == 1
    assert summary["daily_direction"] == 1
    assert summary["skipped_chunks"] == 1
    assert summary["errors"] == []
