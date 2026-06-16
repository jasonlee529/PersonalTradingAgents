class DummyPropagator:
    def create_initial_state(
        self,
        company_name,
        trade_date,
        asset_type="stock",
        past_context="",
        market_profile=None,
        market_rules="",
    ):
        return {
            "company_of_interest": company_name,
            "trade_date": str(trade_date),
            "asset_type": asset_type,
            "past_context": past_context,
            "market_profile": market_profile or {},
            "market_rules": market_rules,
        }

    def get_graph_args(self):
        return {"stream_mode": "values", "config": {"recursion_limit": 10}}


class DummyStreamGraph:
    def stream(self, init_state, stream_mode="updates", **kwargs):
        assert stream_mode == "updates"
        yield {"market_analyst": {"market_report": "market ok"}}
        yield {"portfolio_manager": {"final_trade_decision": "hold"}}


class RecordingEventHandler:
    def __init__(self):
        self.events = []

    def on_node_start(self, node_name):
        self.events.append(("start", node_name))

    def on_node_end(self, node_name, state_delta=None):
        self.events.append(("end", node_name, state_delta or {}))

    def on_error(self, node_name, error):
        self.events.append(("error", node_name, error))


def test_trading_graph_supports_context_provider_and_stream_events():
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    graph.propagator = DummyPropagator()
    graph.graph = DummyStreamGraph()
    graph.config = {"checkpoint_enabled": False}
    graph.debug = False
    graph.curr_state = {}
    graph.logged_state = None
    graph._log_state = lambda trade_date, state: setattr(graph, "logged_state", dict(state))
    graph.process_signal = lambda decision: decision

    handler = RecordingEventHandler()

    final_state, signal = TradingAgentsGraph._run_graph(
        graph,
        "600519",
        "2026-06-01",
        context_provider=lambda company, trade_date, asset_type: "raw context",
        stream=True,
        event_handler=handler,
    )

    assert signal == "hold"
    assert final_state["past_context"] == "raw context"
    assert final_state["market_report"] == "market ok"
    assert graph.logged_state["final_trade_decision"] == "hold"
    assert handler.events[0] == ("start", "market_analyst")
    assert handler.events[-1][0:2] == ("end", "portfolio_manager")


def test_trading_graph_supports_market_profile_config():
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    graph.propagator = DummyPropagator()
    graph.graph = DummyStreamGraph()
    graph.config = {
        "checkpoint_enabled": False,
        "market_profile": {"market": "CN", "rules": "T+1 rule"},
    }
    graph.debug = False
    graph.curr_state = {}
    graph.logged_state = None
    graph._log_state = lambda trade_date, state: setattr(graph, "logged_state", dict(state))
    graph.process_signal = lambda decision: decision
    handler = RecordingEventHandler()

    final_state, signal = TradingAgentsGraph._run_graph(
        graph,
        "600519",
        "2026-06-01",
        event_handler=handler,
        stream=True,
    )

    assert signal == "hold"
    assert final_state["market_profile"]["market"] == "CN"
    assert final_state["market_rules"] == "T+1 rule"
    assert final_state["market_report"] == "market ok"


class ResumeStreamGraph:
    def __init__(self):
        self.stream_input = object()
        self.state_config = None
        self.updated_state = None
        self.updated_as_node = None

    def update_state(self, config, values, as_node=None):
        self.state_config = config
        self.updated_state = dict(values)
        self.updated_as_node = as_node

    def get_state(self, config):
        self.state_config = config
        if self.updated_state is not None:
            return type("Snapshot", (), {"values": self.updated_state})()
        return type(
            "Snapshot",
            (),
            {
                "values": {
                    "company_of_interest": "600519",
                    "trade_date": "2026-06-01",
                    "market_report": "previous market report",
                    "sentiment_report": "previous sentiment report",
                    "news_report": "previous news report",
                    "fundamentals_report": "previous fundamentals report",
                }
            },
        )()

    def stream(self, init_state, stream_mode="updates", **kwargs):
        assert stream_mode == "updates"
        self.stream_input = init_state
        yield {"Portfolio Manager": {"final_trade_decision": "hold"}}


def test_trading_graph_stream_resume_uses_checkpoint_input(tmp_path):
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    graph.propagator = DummyPropagator()
    graph.graph = ResumeStreamGraph()
    graph.config = {
        "checkpoint_enabled": True,
        "checkpoint_dir": str(tmp_path / "checkpoints"),
        "data_cache_dir": str(tmp_path / "cache"),
    }
    graph.debug = False
    graph.curr_state = {}
    graph.logged_state = None
    graph._log_state = lambda trade_date, state: setattr(graph, "logged_state", dict(state))
    graph.process_signal = lambda decision: decision
    handler = RecordingEventHandler()

    final_state, signal = TradingAgentsGraph._run_graph(
        graph,
        "600519",
        "2026-06-01",
        event_handler=handler,
        stream=True,
        resume_from_checkpoint=True,
    )

    assert signal == "hold"
    assert graph.graph.stream_input is None
    assert final_state["market_report"] == "previous market report"
    assert final_state["final_trade_decision"] == "hold"
    assert graph.logged_state["sentiment_report"] == "previous sentiment report"


def test_trading_graph_seeds_resume_checkpoint_from_config(tmp_path):
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    graph.propagator = DummyPropagator()
    graph.graph = ResumeStreamGraph()
    graph.config = {
        "checkpoint_enabled": True,
        "checkpoint_dir": str(tmp_path / "checkpoints"),
        "data_cache_dir": str(tmp_path / "cache"),
        "resume_as_node": "Bear Researcher",
        "resume_state": {
            "market_report": "seeded market report",
            "final_trade_decision": "",
        },
    }
    graph.debug = False
    graph.curr_state = {}
    graph.logged_state = None
    graph._log_state = lambda trade_date, state: setattr(graph, "logged_state", dict(state))
    graph.process_signal = lambda decision: decision

    final_state, signal = TradingAgentsGraph._run_graph(
        graph,
        "600519",
        "2026-06-01",
        event_handler=RecordingEventHandler(),
        stream=True,
    )

    assert signal == "hold"
    assert graph.graph.updated_as_node == "Bear Researcher"
    assert graph.graph.updated_state["market_report"] == "seeded market report"
    assert graph.graph.stream_input is None
    assert final_state["final_trade_decision"] == "hold"
import sys
from pathlib import Path

agents_dir = Path(__file__).resolve().parents[2] / "src" / "agents"
if str(agents_dir) not in sys.path:
    sys.path.insert(0, str(agents_dir))
