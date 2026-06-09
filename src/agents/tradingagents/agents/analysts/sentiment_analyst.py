"""Sentiment analyst using the configured DataCollector news path only."""

from datetime import datetime, timedelta

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
    get_news,
)


def _seven_days_back(trade_date: str) -> str:
    return (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")


def create_sentiment_analyst(llm):
    """Create a sentiment analyst node for the trading graph.

    Data is pre-fetched only through get_news, which routes to the
    DataCollector-backed vendor. No Reddit, StockTwits, X, yfinance, or other
    foreign/social dataflows are queried.
    """

    def sentiment_analyst_node(state):
        ticker = state["company_of_interest"]
        end_date = state["trade_date"]
        start_date = _seven_days_back(end_date)
        instrument_context = build_instrument_context(ticker)

        news_block = get_news.func(ticker, start_date, end_date)

        system_message = _build_system_message(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            news_block=news_block,
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    "\n{system_message}\n"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=end_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm
        result = chain.invoke(state["messages"])

        return {
            "messages": [result],
            "sentiment_report": result.content,
        }

    return sentiment_analyst_node


def _build_system_message(
    *,
    ticker: str,
    start_date: str,
    end_date: str,
    news_block: str,
) -> str:
    """Assemble the sentiment-analyst system message."""
    return f"""You are a financial market sentiment analyst. Your task is to produce a sentiment report for {ticker} covering the period from {start_date} to {end_date}, drawing only on the DataCollector-backed domestic news data already collected for you.

## Data sources

### Domestic news headlines, past 7 days
Fact-driven company, market, and policy framing from the configured domestic data sources.

<start_of_news>
{news_block}
<end_of_news>

## How to analyze this data

1. Separate event from tone. A factual company event and a media framing signal are different. Weight hard events more than adjective-heavy headlines.
2. Look for repeated narratives: policy, orders, earnings, litigation, financing, supply chain, industry cycle, or capital-market activity.
3. Map sentiment to trading relevance: short-term risk appetite, medium-term valuation, or long-term fundamentals.
4. Be honest about data limits. If DataCollector returns no news, sparse news, or an error placeholder, state that the sentiment read is weak.
5. Do not invent Reddit, StockTwits, X, yfinance, foreign media, or any source not present in the news block.
6. Past sentiment is not predictive. Frame conclusions as one signal to weigh alongside fundamentals and technicals.

## Output

Produce a sentiment report covering, in order:

1. Overall sentiment direction: Bullish / Bearish / Neutral / Mixed, with a confidence note based on data quality.
2. News evidence breakdown with specific evidence from available headlines.
3. Key narratives and whether they are aligned or mixed.
4. Catalysts and risks surfaced by the data.
5. Markdown table summarizing key sentiment signals, direction, source, and evidence.

{get_language_instruction()}"""


def create_social_media_analyst(llm):
    """Deprecated alias for create_sentiment_analyst."""
    import warnings

    warnings.warn(
        "create_social_media_analyst is deprecated and will be removed in a "
        "future version. Use create_sentiment_analyst instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return create_sentiment_analyst(llm)


__analyst_name__ = "social"
__analyst_label__ = "情绪分析"
__analyst_report_key__ = "sentiment_report"
__analyst_llm_type__ = "quick"
