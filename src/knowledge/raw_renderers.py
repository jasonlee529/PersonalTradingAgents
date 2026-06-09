from __future__ import annotations

from decimal import Decimal
from typing import Any


ACTION_LABELS = {
    "buy": "买入",
    "sell": "卖出",
    "add": "加仓",
    "reduce": "减仓",
    "clear": "清仓",
    "hold": "持有",
    "watch": "观察",
}


def _money(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        return f"{Decimal(str(value)):.2f}"
    except Exception:
        return str(value)


def _num(value: Any) -> str:
    if value is None or value == "":
        return ""
    return str(value)


def _position_row(symbol: str, position: dict | None) -> list[str]:
    p = position or {}
    return [
        symbol,
        _num(p.get("quantity", 0)),
        _money(p.get("avg_cost", 0)),
        _money(p.get("current_price")),
        _money(p.get("market_value")),
    ]


def render_daily_trade_log(
    trade_date: str,
    entries: list[dict],
    notes: str = "",
    audit: dict | None = None,
) -> str:
    audit = audit or {}
    lines: list[str] = [
        f"# {trade_date} 每日操作记录",
        "",
        "## 汇总",
        "",
        "| 股票 | 操作 | 数量 | 均价 | 金额 | 费用 | 结果 |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]

    final_positions = audit.get("final_positions") or {}
    for entry in entries:
        symbol = entry.get("symbol", "")
        quantity = entry.get("quantity") or 0
        price = entry.get("price") or 0
        amount = Decimal(str(quantity)) * Decimal(str(price)) if quantity and price else Decimal("0")
        fees = (
            Decimal(str(entry.get("commission") or 0))
            + Decimal(str(entry.get("tax") or 0))
            + Decimal(str(entry.get("other_fees") or 0))
        )
        final = final_positions.get(symbol, {})
        result = f"最终 {final.get('quantity', 0)} 股 @ {_money(final.get('avg_cost', 0))}"
        lines.append(
            "| "
            + " | ".join(
                [
                    symbol,
                    ACTION_LABELS.get(entry.get("action", ""), entry.get("action", "")),
                    _num(quantity),
                    _money(price),
                    _money(amount),
                    _money(fees),
                    result,
                ]
            )
            + " |"
        )

    lines.extend(["", "## 明细", ""])
    for entry in entries:
        symbol = entry.get("symbol", "")
        lines.extend(
            [
                f"### {symbol}",
                "",
                f"- 名称：{entry.get('name', '')}",
                f"- 操作：{ACTION_LABELS.get(entry.get('action', ''), entry.get('action', ''))}",
                f"- 数量：{_num(entry.get('quantity'))}",
                f"- 价格：{_money(entry.get('price'))}",
                f"- 金额：{_money(entry.get('amount'))}",
                f"- 交易费用：{_money(entry.get('commission', 0))}",
                f"- 税费：{_money(entry.get('tax', 0))}",
                f"- 其他费用：{_money(entry.get('other_fees', 0))}",
                f"- 理由：{entry.get('reason', '')}",
                f"- 关联分析：{entry.get('linked_analysis_run_id', '')}",
                f"- 关联材料：{', '.join(entry.get('linked_source_ids') or [])}",
                "",
            ]
        )

    lines.extend(
        [
            "## 持仓更新",
            "",
            "### 执行前",
            "",
            "| 股票 | 数量 | 成本价 | 当前价 | 市值 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    before_positions = audit.get("before_positions") or {}
    for symbol in sorted(set(before_positions) | {e.get("symbol", "") for e in entries}):
        if symbol:
            lines.append("| " + " | ".join(_position_row(symbol, before_positions.get(symbol))) + " |")

    lines.extend(
        [
            "",
            "### 系统计算",
            "",
            "| 股票 | 数量 | 成本价 | 当前价 | 市值 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    system_positions = audit.get("system_positions") or {}
    for symbol in sorted(set(system_positions) | {e.get("symbol", "") for e in entries}):
        if symbol:
            lines.append("| " + " | ".join(_position_row(symbol, system_positions.get(symbol))) + " |")

    lines.extend(
        [
            "",
            "### 用户确认",
            "",
            "| 股票 | 数量 | 成本价 | 当前价 | 市值 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for symbol in sorted(set(final_positions) | {e.get("symbol", "") for e in entries}):
        if symbol:
            lines.append("| " + " | ".join(_position_row(symbol, final_positions.get(symbol))) + " |")

    overrides = audit.get("overrides") or []
    if overrides:
        lines.extend(["", "### 覆盖记录", ""])
        for item in overrides:
            lines.append(
                "- "
                f"{item.get('symbol', '')} {item.get('field', '')}: "
                f"系统={item.get('system_value', '')}，最终={item.get('final_value', '')}，"
                f"原因={item.get('reason', '')}"
            )

    if notes:
        lines.extend(["", "## 备注", "", notes])

    return "\n".join(lines).rstrip() + "\n"


def render_news_article(symbol: str, item: dict) -> str:
    title = item.get("title", "未命名新闻")
    provider = item.get("provider") or item.get("source", "")
    published_at = item.get("published_at") or item.get("time", "")
    url = item.get("canonical_uri") or item.get("url", "")
    content = item.get("content") or item.get("summary") or "当前接口仅返回链接/摘要，未返回完整正文。"
    return "\n".join(
        [
            f"# {title}",
            "",
            f"**股票:** {symbol}",
            f"**来源:** {provider}",
            f"**发布时间:** {published_at}",
            f"**链接:** {url}",
            "",
            str(content),
        ]
    ).rstrip() + "\n"


def render_announcement(symbol: str, item: dict) -> str:
    title = item.get("title", "未命名公告")
    provider = item.get("provider") or item.get("source", "")
    published_at = item.get("published_at") or item.get("date", "")
    url = item.get("canonical_uri") or item.get("url", "")
    content = item.get("content") or item.get("summary") or "当前接口仅返回链接/摘要，未返回完整公告正文。"
    return "\n".join(
        [
            f"# {title}",
            "",
            f"**股票:** {symbol}",
            f"**来源:** {provider}",
            f"**发布时间:** {published_at}",
            f"**链接:** {url}",
            f"**公告类型:** {item.get('type', '')}",
            "",
            str(content),
        ]
    ).rstrip() + "\n"


def render_research_report(symbol: str, item: dict) -> str:
    title = item.get("title", "未命名研报")
    provider = item.get("provider") or item.get("source", "eastmoney")
    published_at = item.get("published_at") or item.get("date", "")
    url = item.get("canonical_uri") or item.get("pdf_url") or item.get("url", "")
    content = item.get("content") or item.get("summary") or "当前接口仅返回链接/摘要，未返回完整研报正文。"
    return "\n".join(
        [
            f"# {title}",
            "",
            f"**股票:** {symbol}",
            f"**来源:** {provider}",
            f"**机构:** {item.get('institution', '')}",
            f"**分析师:** {item.get('analyst', '')}",
            f"**评级:** {item.get('rating', '')}",
            f"**目标价:** {item.get('target_price', '')}",
            f"**发布时间:** {published_at}",
            f"**链接:** {url}",
            "",
            str(content),
        ]
    ).rstrip() + "\n"
