"""A-share market profile construction."""
from src.utils.ticker import detect_market


CN_MARKET_RULES = """
## A股市场交易规则

- **交易制度**: T+1（当日买入，次日才能卖出）
- **涨跌幅限制**: 主板 ±10%，创业板/科创板 ±20%，北交所 ±30%
- **最小交易单位**: 100股 = 1手（买入必须为100股的整数倍）
- **交易时间**: 9:30-11:30, 13:00-15:00（集合竞价 9:15-9:25）
- **价格笼子**: 买入申报不得高于基准价格的102%，卖出不得低于98%（主板）

请在所有交易决策中严格遵守上述规则。
"""


def build_market_profile(ticker: str) -> dict:
    if detect_market(ticker) != "CN":
        return {}
    return {
        "market": "CN",
        "t_plus": "1",
        "lot_size": "100",
        "rules": CN_MARKET_RULES,
    }
