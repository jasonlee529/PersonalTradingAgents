"""Monkey-patch _run_graph for real-time phase reporting via stream_mode."""
import asyncio
from typing import Any


class PhaseReporterPatch:
    """Patch a TradingAgentsGraph._run_graph to emit phase events."""

    ORIGINAL_ATTR = "_pta_phase_reporter_original_run_graph"

    @staticmethod
    def apply(graph: Any, phase_reporter: Any, loop: asyncio.AbstractEventLoop) -> Any:
        """Return the original _run_graph method for restoration."""
        from tradingagents.graph.checkpointer import thread_id, clear_checkpoint

        if hasattr(graph, PhaseReporterPatch.ORIGINAL_ATTR):
            return getattr(graph, PhaseReporterPatch.ORIGINAL_ATTR)

        original_run_graph = graph._run_graph
        setattr(graph, PhaseReporterPatch.ORIGINAL_ATTR, original_run_graph)

        def _streaming_run_graph(self_graph, company_name, trade_date, asset_type="stock"):
            init_agent_state = self_graph.propagator.create_initial_state(
                company_name, trade_date, asset_type=asset_type
            )
            args = self_graph.propagator.get_graph_args()
            if self_graph.config.get("checkpoint_enabled"):
                tid = thread_id(company_name, str(trade_date))
                args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = tid

            final_state = dict(init_agent_state)
            last_node = "unknown"
            args.pop("stream_mode", None)

            # Track pending node end so nodes stay RUNNING until the next one starts
            pending_end_node = None
            pending_end_state = {}

            try:
                for chunk in self_graph.graph.stream(init_agent_state, stream_mode="updates", **args):
                    for node_name, node_state in chunk.items():
                        last_node = node_name

                        # End previous node before starting the next one
                        if pending_end_node and pending_end_node != node_name:
                            asyncio.run_coroutine_threadsafe(
                                phase_reporter.on_node_end(pending_end_node, pending_end_state), loop
                            ).result()
                            pending_end_node = None

                        asyncio.run_coroutine_threadsafe(
                            phase_reporter.on_node_start(node_name), loop
                        ).result()

                        if node_state:
                            final_state.update(node_state)
                            pending_end_state = node_state
                        else:
                            pending_end_state = {}

                        pending_end_node = node_name

                # End the last node when stream finishes
                if pending_end_node:
                    asyncio.run_coroutine_threadsafe(
                        phase_reporter.on_node_end(pending_end_node, pending_end_state), loop
                    ).result()
            except Exception as e:
                # End current node before reporting error
                if pending_end_node:
                    asyncio.run_coroutine_threadsafe(
                        phase_reporter.on_node_end(pending_end_node, pending_end_state), loop
                    ).result()
                asyncio.run_coroutine_threadsafe(
                    phase_reporter.on_error(last_node, str(e)), loop
                ).result()
                raise

            self_graph.curr_state = final_state
            self_graph._log_state(trade_date, final_state)
            if self_graph.config.get("checkpoint_enabled"):
                checkpoint_dir = self_graph.config.get(
                    "checkpoint_dir", self_graph.config["data_cache_dir"]
                )
                clear_checkpoint(
                    checkpoint_dir, company_name, str(trade_date)
                )
            return final_state, self_graph.process_signal(final_state["final_trade_decision"])

        graph._run_graph = _streaming_run_graph.__get__(graph, type(graph))
        return original_run_graph

    @staticmethod
    def restore(graph: Any) -> None:
        if not hasattr(graph, PhaseReporterPatch.ORIGINAL_ATTR):
            return
        graph._run_graph = getattr(graph, PhaseReporterPatch.ORIGINAL_ATTR)
        delattr(graph, PhaseReporterPatch.ORIGINAL_ATTR)


class PhaseReporterEventHandler:
    """Synchronous graph event adapter for async phase reporters."""

    def __init__(self, phase_reporter: Any, loop: asyncio.AbstractEventLoop):
        self.phase_reporter = phase_reporter
        self.loop = loop

    def on_node_start(self, node_name: str) -> None:
        asyncio.run_coroutine_threadsafe(
            self.phase_reporter.on_node_start(node_name),
            self.loop,
        ).result()

    def on_node_end(self, node_name: str, state_delta=None) -> None:
        asyncio.run_coroutine_threadsafe(
            self.phase_reporter.on_node_end(node_name, state_delta),
            self.loop,
        ).result()

    def on_error(self, node_name: str, error: str) -> None:
        asyncio.run_coroutine_threadsafe(
            self.phase_reporter.on_error(node_name, error),
            self.loop,
        ).result()
