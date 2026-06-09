import pytest

from src.agents.analysis_memory import load_raw_memory_context, save_analysis_memory
from src.knowledge.raw_store import RawStore


@pytest.mark.asyncio
async def test_save_and_load_raw_analysis_memory(test_settings):
    store = RawStore(test_settings)

    full_report = await store.add_source(
        source_kind="stock_analysis",
        origin="agent",
        title="603738 2026-06-06 Full Report",
        markdown="# Full Report\n\nDetails",
        metadata={
            "symbol": "603738",
            "symbols": ["603738"],
            "trade_date": "2026-06-06",
            "run_id": "analysis:603738:2026-06-06:101010",
            "run_time": "101010",
            "analysis_node": "full_report",
            "tags": ["stock/603738", "node/full_report"],
        },
    )

    memory = await save_analysis_memory(
        store,
        symbol="603738",
        trade_date="2026-06-06",
        run_id="analysis:603738:2026-06-06:101010",
        run_time="101010",
        final_trade_decision="Rating: **Hold**\nReason: wait for confirmation.",
        linked_full_report_source_id=full_report["source_id"],
    )

    assert memory is not None
    assert memory["source_kind"] == "analysis_memory"
    assert memory["origin"] == "agent"
    assert memory["symbol"] == "603738"

    source = await store.read_source(memory["source_id"])
    assert "Rating: hold" in source["markdown"]
    assert source["metadata"]["analysis_node"] == "portfolio_memory"
    assert source["metadata"]["linked_full_report_source_id"] == full_report["source_id"]
    assert source["metadata"]["raw_return"] is None
    assert source["metadata"]["alpha_return"] is None
    assert source["metadata"]["reflection_status"] == "pending"

    context = await load_raw_memory_context(store, "603738", limit=3)
    assert "Past analyses of 603738" in context
    assert "wait for confirmation" in context
