from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_global_news,
    get_language_instruction,
    get_news,
)


def create_catalyst_analyst(llm):
    """A-share catalyst transmission analyst."""

    def catalyst_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])
        tools = [get_news, get_global_news]

        system_message = (
            "你是 A 股研究团队里的「政策与产业催化」分析师。你的任务不是泛泛复述政策新闻，"
            "而是判断政策、监管、产业规划和地方项目如何传导到目标公司的订单、利润、估值和交易情绪。\n\n"
            "分析框架：\n"
            "1. 政策来源分级：国务院/部委/地方政府/交易所/行业协会/海外限制，区分强约束、弱指引和情绪催化。\n"
            "2. 产业链映射：说明政策影响的是上游、中游、下游、应用端还是渠道端，目标公司处在哪一环。\n"
            "3. 兑现路径：把政策拆成订单、补贴、价格、产能、准入、出口、融资、监管成本等可验证变量。\n"
            "4. 时间窗口：区分 1-5 个交易日情绪催化、1-3 个月业绩预期、半年以上产业趋势。\n"
            "5. 反证条件：列出政策落空、执行慢、行业拥挤、补贴退坡、监管趋严等使逻辑失效的条件。\n\n"
            "请优先调用工具检索近期公司、行业和宏观政策新闻。没有数据时明确写 [数据缺失: xxx]，不要编造。\n\n"
            "输出 Markdown 报告，必须包含：\n"
            "- 结论摘要：政策/产业催化评级（强利好、利好、中性、利空、强利空）\n"
            "- 关键政策与产业事件表：日期、来源、事件、影响方向、兑现窗口、置信度\n"
            "- 公司映射：政策如何影响收入、利润率、估值或交易热度\n"
            "- 风险与反证：哪些信号出现后应下修判断\n"
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
        return {"messages": [result], "catalyst_report": report}

    return catalyst_analyst_node


__analyst_name__ = "catalyst"
__analyst_label__ = "政策与产业催化"
__analyst_report_key__ = "catalyst_report"
__analyst_llm_type__ = "quick"
