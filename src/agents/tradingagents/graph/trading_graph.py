# TradingAgents/graph/trading_graph.py

import logging
import os
from pathlib import Path
import json
from datetime import datetime
from typing import Dict, Any, Tuple, List, Optional

logger = logging.getLogger(__name__)

from langgraph.prebuilt import ToolNode

from tradingagents.llm_clients import create_llm_client

from tradingagents.agents import *
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.agents.analyst_registry import AnalystRegistry
from tradingagents.dataflows.utils import safe_ticker_component
from tradingagents.agents.utils.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)
from tradingagents.dataflows.config import set_config

# Import the new abstract tool methods from agent_utils
from tradingagents.agents.utils.agent_utils import (
    get_stock_data,
    get_indicators,
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
    get_news,
    get_insider_transactions,
    get_global_news,
    get_cross_border_flow,
    get_market_heatmap,
    get_order_flow_profile,
    get_peer_industry_snapshot,
    get_supply_unlock_schedule,
    get_theme_exposure,
    get_trading_seat_activity,
)
from .checkpointer import checkpoint_step, clear_checkpoint, get_checkpointer, thread_id
from .conditional_logic import ConditionalLogic
from .setup import GraphSetup
from .propagation import Propagator
from .reflection import Reflector
from .signal_processing import SignalProcessor


class TradingAgentsGraph:
    """Main class that orchestrates the trading agents framework."""

    def __init__(
        self,
        selected_analysts=None,
        debug=False,
        config: Dict[str, Any] = None,
        callbacks: Optional[List] = None,
    ):
        """Initialize the trading agents graph and components.

        Args:
            selected_analysts: List of analyst types to include
            debug: Whether to run in debug mode
            config: Configuration dictionary. If None, uses default config
            callbacks: Optional list of callback handlers (e.g., for tracking LLM/tool stats)
        """
        if selected_analysts is None:
            selected_analysts = AnalystRegistry.default_names()
        self.debug = debug
        self.config = config or DEFAULT_CONFIG
        self.callbacks = callbacks or []

        # Update the interface's config
        set_config(self.config)

        # Create necessary directories
        os.makedirs(self.config["data_cache_dir"], exist_ok=True)
        os.makedirs(self.config["results_dir"], exist_ok=True)

        # Initialize LLMs with provider-specific thinking configuration
        llm_kwargs = self._get_provider_kwargs()

        # Add callbacks to kwargs if provided (passed to LLM constructor)
        if self.callbacks:
            llm_kwargs["callbacks"] = self.callbacks

        if self.config.get("test_mode"):
            llm_kwargs["test_mode"] = True

        deep_client = create_llm_client(
            provider=self.config["llm_provider"],
            model=self.config["deep_think_llm"],
            base_url=self.config.get("backend_url"),
            **llm_kwargs,
        )
        quick_client = create_llm_client(
            provider=self.config["llm_provider"],
            model=self.config["quick_think_llm"],
            base_url=self.config.get("backend_url"),
            **llm_kwargs,
        )

        self.deep_thinking_llm = deep_client.get_llm()
        self.quick_thinking_llm = quick_client.get_llm()
        
        # Create tool nodes
        self.tool_nodes = self._create_tool_nodes()

        # Initialize components
        self.conditional_logic = ConditionalLogic(
            max_debate_rounds=self.config["max_debate_rounds"],
            max_risk_discuss_rounds=self.config["max_risk_discuss_rounds"],
        )
        self.graph_setup = GraphSetup(
            self.quick_thinking_llm,
            self.deep_thinking_llm,
            self.tool_nodes,
            self.conditional_logic,
            analyst_concurrency_limit=self.config.get("analyst_concurrency_limit", 1),
        )

        self.propagator = Propagator(
            max_recur_limit=self.config.get("max_recur_limit", 100),
        )
        self.reflector = Reflector(self.quick_thinking_llm)
        self.signal_processor = SignalProcessor(self.quick_thinking_llm)

        # State tracking
        self.curr_state = None
        self.ticker = None
        self.log_states_dict = {}  # date to full state dict

        # Set up the graph: keep the workflow for recompilation with a checkpointer.
        self.workflow = self.graph_setup.setup_graph(selected_analysts)
        self.graph = self.workflow.compile()
        self._checkpointer_ctx = None

    def _get_provider_kwargs(self) -> Dict[str, Any]:
        """Get provider-specific kwargs for LLM client creation."""
        kwargs = {}
        api_key = self.config.get("api_key")
        if api_key:
            kwargs["api_key"] = api_key
        timeout = self.config.get("llm_timeout")
        if timeout is not None:
            kwargs["timeout"] = timeout
        kwargs["max_retries"] = self.config.get("llm_max_retries", 0)
        provider = self.config.get("llm_provider", "").lower()

        if provider == "google":
            thinking_level = self.config.get("google_thinking_level")
            if thinking_level:
                kwargs["thinking_level"] = thinking_level

        elif provider == "openai":
            reasoning_effort = self.config.get("openai_reasoning_effort")
            if reasoning_effort:
                kwargs["reasoning_effort"] = reasoning_effort

        elif provider == "anthropic":
            effort = self.config.get("anthropic_effort")
            if effort:
                kwargs["effort"] = effort

        return kwargs

    def _create_tool_nodes(self) -> Dict[str, ToolNode]:
        """Create tool nodes for different data sources using abstract methods."""
        nodes = {
            "market": ToolNode(
                [
                    # Core stock data tools
                    get_stock_data,
                    # Technical indicators
                    get_indicators,
                ]
            ),
            "social": ToolNode(
                [
                    # News tools for social media analysis
                    get_news,
                ]
            ),
            "news": ToolNode(
                [
                    # News and insider information
                    get_news,
                    get_global_news,
                    get_insider_transactions,
                ]
            ),
            "fundamentals": ToolNode(
                [
                    # Fundamental analysis tools
                    get_fundamentals,
                    get_balance_sheet,
                    get_cashflow,
                    get_income_statement,
                ]
            ),
            "catalyst": ToolNode(
                [
                    get_news,
                    get_global_news,
                ]
            ),
            "flow_risk": ToolNode(
                [
                    get_stock_data,
                    get_news,
                    get_insider_transactions,
                    get_market_heatmap,
                    get_cross_border_flow,
                    get_theme_exposure,
                    get_order_flow_profile,
                    get_trading_seat_activity,
                    get_supply_unlock_schedule,
                    get_peer_industry_snapshot,
                ]
            ),
        }
        extra_tools = self.config.get("extra_tools") or []
        if extra_tools:
            for key, node in list(nodes.items()):
                nodes[key] = ToolNode(list(node.tools) + list(extra_tools))
        return nodes

    def _resolve_benchmark(self, ticker: str) -> str:
        """Resolve the alpha benchmark for A-share/HK reflection."""
        configured = self.config.get("benchmark_ticker")
        if configured:
            return configured

        benchmark_map = self.config.get("benchmark_map") or {}
        symbol = str(ticker or "").strip().upper()
        base_symbol = symbol.split(".", 1)[0]

        if base_symbol.isdigit() and len(base_symbol) == 6:
            return benchmark_map.get(".SS", "000300.SS")
        if base_symbol.isdigit() and len(base_symbol) == 5:
            return benchmark_map.get(".HK", "^HSI")

        for suffix, benchmark in benchmark_map.items():
            if suffix and symbol.endswith(suffix.upper()):
                return benchmark
        return benchmark_map.get("", "000300.SS")

    def propagate(
        self,
        company_name,
        trade_date,
        asset_type: str = "stock",
        context_provider=None,
        event_handler=None,
        stream: Optional[bool] = None,
    ):
        """Run the trading agents graph for a company on a specific date.

        ``asset_type`` selects between the stock pipeline (default) and the
        crypto pipeline (``"crypto"``) shipped in #567 鈥?the CLI auto-detects
        from the ticker; programmatic callers pass it explicitly. When
        ``checkpoint_enabled`` is set in config, the graph is recompiled with
        a per-ticker SqliteSaver so a crashed run can resume from the last
        successful node on a subsequent invocation with the same ticker+date.
        """
        self.ticker = company_name

        # Recompile with a checkpointer if the user opted in.
        resume_from_checkpoint = False
        if self.config.get("checkpoint_enabled"):
            checkpoint_dir = self.config.get("checkpoint_dir", self.config["data_cache_dir"])
            self._checkpointer_ctx = get_checkpointer(
                checkpoint_dir, company_name
            )
            saver = self._checkpointer_ctx.__enter__()
            self.graph = self.workflow.compile(checkpointer=saver)

            step = checkpoint_step(
                checkpoint_dir, company_name, str(trade_date)
            )
            if step is not None:
                resume_from_checkpoint = True
                logger.info(
                    "Resuming from step %d for %s on %s", step, company_name, trade_date
                )
            else:
                logger.info("Starting fresh for %s on %s", company_name, trade_date)

        try:
            return self._run_graph(
                company_name,
                trade_date,
                asset_type=asset_type,
                context_provider=context_provider,
                event_handler=event_handler,
                stream=stream,
                resume_from_checkpoint=resume_from_checkpoint,
            )
        finally:
            if self._checkpointer_ctx is not None:
                self._checkpointer_ctx.__exit__(None, None, None)
                self._checkpointer_ctx = None
                self.graph = self.workflow.compile()

    def _run_graph(
        self,
        company_name,
        trade_date,
        asset_type: str = "stock",
        context_provider=None,
        event_handler=None,
        stream: Optional[bool] = None,
        resume_from_checkpoint: bool = False,
    ):
        """Execute the graph and write the resulting state to disk and memory log."""
        past_context = ""
        provider = context_provider or self.config.get("past_context_provider")
        if provider:
            past_context = provider(company_name, trade_date, asset_type)

        market_profile = {}
        market_rules = ""
        market_provider = self.config.get("market_profile_provider")
        if market_provider:
            market_profile = market_provider(company_name, trade_date, asset_type) or {}
            if isinstance(market_profile, dict):
                market_rules = str(market_profile.get("rules") or "")
        configured_market_profile = self.config.get("market_profile")
        if configured_market_profile:
            market_profile = configured_market_profile
            if isinstance(market_profile, dict):
                market_rules = str(market_profile.get("rules") or market_rules)
        configured_market_rules = self.config.get("market_rules")
        if configured_market_rules:
            market_rules = str(configured_market_rules)

        # Initialize state 鈥?no pre-injected past_context (moved to optional tool call).
        init_agent_state = self.propagator.create_initial_state(
            company_name,
            trade_date,
            asset_type=asset_type,
            past_context=past_context,
            market_profile=market_profile,
            market_rules=market_rules,
        )
        args = self.propagator.get_graph_args()

        # Inject thread_id so same ticker+date resumes, different date starts fresh.
        if self.config.get("checkpoint_enabled"):
            tid = thread_id(company_name, str(trade_date))
            args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = tid

        if self.config.get("checkpoint_enabled") and not resume_from_checkpoint:
            resume_from_checkpoint = self._seed_resume_checkpoint(args, init_agent_state)

        should_stream = self.config.get("stream_graph", False) if stream is None else stream
        handler = event_handler or self.config.get("event_handler")

        graph_input = None if resume_from_checkpoint else init_agent_state

        if should_stream or handler:
            final_state = self._stream_graph_with_events(
                graph_input,
                args,
                handler,
            )
        elif self.debug:
            final_state = self._checkpoint_state(args) if resume_from_checkpoint else {}
            trace = []
            for chunk in self.graph.stream(graph_input, **args):
                if len(chunk["messages"]) == 0:
                    pass
                else:
                    chunk["messages"][-1].pretty_print()
                    trace.append(chunk)
            # Streamed chunks are per-node deltas. Merge them so the returned
            # state matches what graph.invoke() yields in the non-debug path.
            for chunk in trace:
                final_state.update(chunk)
        else:
            final_state = self.graph.invoke(graph_input, **args)

        # Store current state for reflection.
        self.curr_state = final_state

        # Log state to disk.
        self._log_state(trade_date, final_state)

        # Clear checkpoint on successful completion to avoid stale state.
        if self.config.get("checkpoint_enabled"):
            checkpoint_dir = self.config.get("checkpoint_dir", self.config["data_cache_dir"])
            clear_checkpoint(
                checkpoint_dir, company_name, str(trade_date)
            )

        return final_state, self.process_signal(final_state["final_trade_decision"])

    def _stream_graph_with_events(self, graph_input, args, event_handler=None):
        """Stream graph updates and optionally report node lifecycle events."""
        final_state = (
            self._checkpoint_state(args)
            if graph_input is None
            else dict(graph_input)
        )
        last_node = "unknown"
        stream_args = dict(args)
        stream_args.pop("stream_mode", None)
        pending_end_node = None
        pending_end_state = {}

        try:
            for chunk in self.graph.stream(
                graph_input,
                stream_mode="updates",
                **stream_args,
            ):
                for node_name, node_state in chunk.items():
                    last_node = node_name
                    if pending_end_node and pending_end_node != node_name:
                        self._emit_event(
                            event_handler,
                            "on_node_end",
                            pending_end_node,
                            pending_end_state,
                        )
                        pending_end_node = None

                    self._emit_event(event_handler, "on_node_start", node_name)

                    if node_state:
                        final_state.update(node_state)
                        pending_end_state = node_state
                    else:
                        pending_end_state = {}
                    pending_end_node = node_name

            if pending_end_node:
                self._emit_event(
                    event_handler,
                    "on_node_end",
                    pending_end_node,
                    pending_end_state,
                )
        except Exception as e:
            if pending_end_node:
                self._emit_event(
                    event_handler,
                    "on_node_end",
                    pending_end_node,
                    pending_end_state,
                )
            self._emit_event(event_handler, "on_error", last_node, str(e))
            raise

        return final_state

    def _seed_resume_checkpoint(self, args, init_agent_state) -> bool:
        """Seed a checkpoint from persisted job artifacts when no real one exists."""
        resume_state = self.config.get("resume_state")
        resume_as_node = self.config.get("resume_as_node")
        if not isinstance(resume_state, dict) or not resume_as_node:
            return False
        try:
            seeded_state = dict(init_agent_state)
            seeded_state.update(resume_state)
            self.graph.update_state(
                args.get("config", {}),
                seeded_state,
                as_node=str(resume_as_node),
            )
            logger.info("Seeded resume checkpoint from persisted artifacts at %s", resume_as_node)
            return True
        except Exception:
            logger.warning(
                "Failed to seed resume checkpoint from persisted artifacts; starting fresh",
                exc_info=True,
            )
            return False

    def _checkpoint_state(self, args) -> Dict[str, Any]:
        """Return the latest checkpointed state for a resumable stream."""
        try:
            snapshot = self.graph.get_state(args.get("config", {}))
            values = getattr(snapshot, "values", None)
            if isinstance(values, dict):
                return dict(values)
        except Exception:
            logger.debug("Unable to read checkpoint state before resume", exc_info=True)
        return {}

    @staticmethod
    def _emit_event(event_handler, method_name: str, *args) -> None:
        if not event_handler:
            return
        method = getattr(event_handler, method_name, None)
        if method:
            method(*args)

    def _log_state(self, trade_date, final_state):
        """Log the final state to a JSON file."""
        self.log_states_dict[str(trade_date)] = {
            "company_of_interest": final_state["company_of_interest"],
            "trade_date": final_state["trade_date"],
            "market_report": final_state["market_report"],
            "sentiment_report": final_state["sentiment_report"],
            "news_report": final_state["news_report"],
            "fundamentals_report": final_state["fundamentals_report"],
            "investment_debate_state": {
                "bull_history": final_state["investment_debate_state"]["bull_history"],
                "bear_history": final_state["investment_debate_state"]["bear_history"],
                "history": final_state["investment_debate_state"]["history"],
                "current_response": final_state["investment_debate_state"][
                    "current_response"
                ],
                "judge_decision": final_state["investment_debate_state"][
                    "judge_decision"
                ],
            },
            "trader_investment_decision": final_state["trader_investment_plan"],
            "risk_debate_state": {
                "aggressive_history": final_state["risk_debate_state"]["aggressive_history"],
                "conservative_history": final_state["risk_debate_state"]["conservative_history"],
                "neutral_history": final_state["risk_debate_state"]["neutral_history"],
                "history": final_state["risk_debate_state"]["history"],
                "judge_decision": final_state["risk_debate_state"]["judge_decision"],
            },
            "investment_plan": final_state["investment_plan"],
            "final_trade_decision": final_state["final_trade_decision"],
        }

        # Save to file. Reject ticker values that would escape the
        # results directory when joined as a path component.
        safe_ticker = safe_ticker_component(self.ticker)
        directory = Path(self.config["results_dir"]) / safe_ticker / "TradingAgentsStrategy_logs"
        directory.mkdir(parents=True, exist_ok=True)

        log_path = directory / f"full_states_log_{trade_date}.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(self.log_states_dict[str(trade_date)], f, indent=4)

    def process_signal(self, full_signal):
        """Process a signal to extract the core decision."""
        return self.signal_processor.process_signal(full_signal)

