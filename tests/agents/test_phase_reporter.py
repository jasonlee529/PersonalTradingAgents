import asyncio
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

agents_dir = Path(__file__).resolve().parents[2] / "src" / "agents"
if str(agents_dir) not in sys.path:
    sys.path.insert(0, str(agents_dir))

from src.agents.wrapper.phase_reporter import PhaseReporterPatch


class DummyPropagator:
    def create_initial_state(self, company_name, trade_date, asset_type="stock", past_context=""):
        return {
            "messages": [("human", company_name)],
            "company_of_interest": company_name,
            "trade_date": str(trade_date),
            "asset_type": asset_type,
            "past_context": past_context,
        }

    def get_graph_args(self):
        return {"stream_mode": "values", "config": {"recursion_limit": 10}}


class DummyStreamGraph:
    def stream(self, init_state, stream_mode="updates", **kwargs):
        assert stream_mode == "updates"
        yield {"market_analyst": {"market_report": "market ok"}}
        yield {
            "portfolio_manager": {
                "final_trade_decision": "hold",
                "trader_investment_plan": "hold",
            }
        }


class DummyTradingGraph:
    def __init__(self):
        self.memory_log = SimpleNamespace(
            get_past_context=lambda ticker: "past",
            store_decision=lambda **kwargs: None,
        )
        self.propagator = DummyPropagator()
        self.config = {"checkpoint_enabled": False}
        self.graph = DummyStreamGraph()
        self.logged_state = None

    def _run_graph(self, company_name, trade_date, asset_type="stock"):
        raise AssertionError("original _run_graph should be patched")

    def _log_state(self, trade_date, final_state):
        self.logged_state = dict(final_state)

    def process_signal(self, full_signal):
        return full_signal


class DummyReporter:
    async def on_node_start(self, node_name):
        return None

    async def on_node_end(self, node_name, state_delta=None):
        return None

    async def on_error(self, node_name, error):
        return None


def test_phase_reporter_streaming_preserves_initial_state():
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever)
    thread.start()
    try:
        graph = DummyTradingGraph()
        PhaseReporterPatch.apply(graph, DummyReporter(), loop)

        final_state, signal = graph._run_graph("600519", "2026-06-01")

        assert signal == "hold"
        assert final_state["company_of_interest"] == "600519"
        assert final_state["trade_date"] == "2026-06-01"
        assert final_state["market_report"] == "market ok"
        assert graph.logged_state["company_of_interest"] == "600519"
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join()
        loop.close()


def test_phase_reporter_patch_is_idempotent_and_restorable():
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever)
    thread.start()
    try:
        graph = DummyTradingGraph()
        original = graph._run_graph

        returned_first = PhaseReporterPatch.apply(graph, DummyReporter(), loop)
        patched = graph._run_graph
        returned_second = PhaseReporterPatch.apply(graph, DummyReporter(), loop)

        assert returned_first.__self__ is original.__self__
        assert returned_first.__func__ is original.__func__
        assert returned_second.__self__ is original.__self__
        assert returned_second.__func__ is original.__func__
        assert graph._run_graph is patched

        PhaseReporterPatch.restore(graph)
        assert graph._run_graph.__self__ is original.__self__
        assert graph._run_graph.__func__ is original.__func__
        assert not hasattr(graph, PhaseReporterPatch.ORIGINAL_ATTR)
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join()
        loop.close()
