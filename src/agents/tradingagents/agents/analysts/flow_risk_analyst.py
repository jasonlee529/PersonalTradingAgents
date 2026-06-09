from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_cross_border_flow,
    get_insider_transactions,
    get_language_instruction,
    get_market_heatmap,
    get_news,
    get_order_flow_profile,
    get_peer_industry_snapshot,
    get_supply_unlock_schedule,
    get_theme_exposure,
    get_trading_seat_activity,
    get_stock_data,
)


def create_flow_risk_analyst(llm):
    """A-share capital-flow and supply-risk analyst."""

    def flow_risk_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])
        tools = [
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

        system_message = (
            "你是 A 股研究团队里的「资金与供给风险」分析师。你的职责是把短线资金行为和股票供给压力合并判断，"
            "不要只看游资热度，也不要把解禁减持孤立成单点风险。\n\n"
            "分析框架：\n"
            "1. 资金热度：成交量、换手率、主力资金、北向资金、行业横向强度、热门股/概念归因。\n"
            "2. 资金质量：区分趋势性增量、事件套利、板块轮动、龙虎榜席位博弈和缩量一致。\n"
            "3. 供给压力：检查未来 90 天限售解禁、大股东/董监高减持、定增成本、历史减持习惯。\n"
            "4. 交易结构：判断当前是主力吸筹、资金接力、冲高出货、无明显资金信号，还是供给压力压制。\n"
            "5. A 股约束：结合涨跌停、T+1、流动性、题材退潮和监管问询风险，给出短期交易含义。\n\n"
            "请优先调用工具获取 K 线/成交、资金流、龙虎榜、北向、概念板块和解禁减持数据。"
            "没有数据时明确写 [数据缺失: xxx]，不要编造。\n\n"
            "输出 Markdown 报告，必须包含：\n"
            "- 结论摘要：资金与供给评级（资金强化、资金分歧、资金转弱、供给压制、信号不足）\n"
            "- 资金信号表：指标、观察结果、方向、可靠性\n"
            "- 供给风险表：解禁/减持事项、规模、窗口、压力等级\n"
            "- 短期交易含义：适合追踪、等待回踩、规避冲高，或仅观察\n"
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant collaborating with an investment research team. "
                    "Use the provided tools when useful. You have access to: {tool_names}.\n"
                    "{system_message}\n"
                    "Current date: {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        result = (prompt | llm.bind_tools(tools)).invoke(state["messages"])
        report = result.content if len(result.tool_calls) == 0 else ""
        return {"messages": [result], "flow_risk_report": report}

    return flow_risk_analyst_node


__analyst_name__ = "flow_risk"
__analyst_label__ = "资金与供给风险"
__analyst_report_key__ = "flow_risk_report"
__analyst_llm_type__ = "quick"
