import yaml


def render_frontmatter(metadata: dict) -> str:
    return f"---\n{yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False)}---\n\n"


def _section(name: str, content: str = "") -> str:
    return f"<!-- wiki-section:start:{name} -->\n{content}<!-- wiki-section:end:{name} -->\n"


def render_stock_profile_template(symbol: str, title: str = "") -> str:
    t = title or f"{symbol} 股票档案"
    return (
        f"# {t}\n\n"
        + _section("summary", "## 当前摘要\n\n")
        + "\n"
        + _section("position", "## 持仓状态\n\n")
        + "\n"
        + _section("thesis", "## 投资主线\n\n")
        + "\n"
        + _section("catalysts", "## 催化剂\n\n")
        + "\n"
        + _section("risks", "## 风险\n\n")
        + "\n"
        + _section("evidence", "## 证据链\n\n")
        + "\n"
        + _section("recent_updates", "## 最近更新\n\n")
        + "\n"
        + _section("links", "## 相关页面\n\n")
    )


def render_stock_timeline_template(symbol: str, title: str = "") -> str:
    t = title or f"{symbol} 时间线"
    return f"# {t}\n\n"


def render_stock_analysis_runs_template(symbol: str, title: str = "") -> str:
    t = title or f"{symbol} 分析 Run 列表"
    return (
        f"# {t}\n\n"
        "| 日期时间 | 决策 | 主要利多 | 主要利空 | 与上次变化 | 页面 |\n"
        "|---|---|---|---|---|---|\n"
    )


def render_topic_template(topic: str, slug: str) -> str:
    return (
        f"# {topic}\n\n"
        + _section("definition", "## 定义\n\n")
        + "\n"
        + _section("current_view", "## 当前观点\n\n")
        + "\n"
        + _section("related_stocks", "## 相关股票\n\n")
        + "\n"
        + _section("catalysts", "## 催化剂\n\n")
        + "\n"
        + _section("risks", "## 风险\n\n")
        + "\n"
        + _section("evidence", "## 证据链\n\n")
    )


def render_daily_direction_template(trade_date: str) -> str:
    return (
        f"# {trade_date} 今日方向\n\n"
        + _section("latest", "## 最新结论\n\n")
        + "\n"
        + _section("runs", "## 方向 Run\n\n")
        + "\n"
        + _section("portfolio_relation", "## 与持仓关系\n\n")
        + "\n"
        + _section("validation", "## 当日后续验证\n\n")
    )


def render_trade_month_template(month: str) -> str:
    return (
        f"# {month} 交易记录\n\n"
        + _section("summary", "## 汇总\n\n")
        + "\n"
        + _section("entries", "## 明细\n\n")
        + "\n"
        + _section("ai_vs_actual", "## AI 建议 vs 实际操作\n\n")
        + "\n"
        + _section("review", "## 复盘\n\n")
    )


def render_portfolio_overview_template() -> str:
    return (
        "# 组合总览\n\n"
        + _section("structure", "## 当前结构\n\n")
        + "\n"
        + _section("theme_distribution", "## 主题分布\n\n")
        + "\n"
        + _section("risk", "## 最大风险\n\n")
        + "\n"
        + _section("recent_trades", "## 最近操作\n\n")
        + "\n"
        + _section("open_issues", "## 待跟踪问题\n\n")
    )


def render_claims_page_template(page_type: str) -> str:
    if page_type == "contradictions":
        return "# 观点冲突\n\n"
    return "# 待验证问题\n\n"


def render_source_digest_page(source: dict, summary: str, claims: list[dict]) -> str:
    title = source.get("title", "Source Digest")
    source_id = source.get("source_id", "")
    source_kind = source.get("source_kind", "")
    provider = source.get("provider", "")
    published_at = source.get("published_at", "")
    sha256 = source.get("content_sha256", "")

    lines = [
        f"# {title}\n",
        "## 来源\n",
        f"- raw: `{source_id}`",
        f"- provider: {provider}",
        f"- published_at: {published_at}",
        f"- raw_sha256: `{sha256}`",
        "",
        "## 摘要\n",
        summary or "...",
        "",
        "## 关键事实\n",
    ]
    for i, claim in enumerate(claims, 1):
        statement = claim.get("statement", "")
        lines.append(f"{i}. {statement}")
    if not claims:
        lines.append("1. 暂无关键事实")

    lines.extend([
        "",
        "## 交易相关性\n",
        "- 利多：",
        "- 利空：",
        "- 待确认：",
        "",
        "## 产生或更新的 claims\n",
    ])
    for claim in claims:
        cid = claim.get("claim_id", "")
        statement = claim.get("statement", "")
        lines.append(f"- `{cid}` {statement}")
    if not claims:
        lines.append("- 无")

    lines.append("")
    return "\n".join(lines) + "\n"


def render_analysis_run_digest_page(sources: list[dict], summary: str, claims: list[dict]) -> str:
    if not sources:
        title = "Analysis Run Digest"
    else:
        first = sources[0]
        symbol = first.get("symbol", "")
        trade_date = first.get("trade_date", "")
        title = f"{symbol} {trade_date} 分析 Run"

    lines = [
        f"# {title}\n",
        "## 分析结论\n",
        summary or "...",
        "",
        "## 各节点摘要\n",
    ]
    for src in sources:
        node = src.get("metadata", {}).get("analysis_node", "")
        src_title = src.get("title", "")
        lines.append(f"- **{node}**: {src_title}")
    if not sources:
        lines.append("- 无节点数据")

    lines.extend([
        "",
        "## 关键依据\n",
        "...",
        "",
        "## 风险和反方观点\n",
        "...",
        "",
        "## 关键 claims\n",
    ])
    for claim in claims:
        cid = claim.get("claim_id", "")
        statement = claim.get("statement", "")
        lines.append(f"- `{cid}` {statement}")
    if not claims:
        lines.append("- 无")

    lines.append("")
    return "\n".join(lines) + "\n"


def render_index_page(pages: list[dict], pending_sources: list[dict], active_claims: list[dict]) -> str:
    lines = ["# PersonalTradingAgents Wiki\n"]

    stock_pages = [p for p in pages if p.get("page_type") == "stock_profile"]
    topic_pages = [p for p in pages if p.get("page_type") == "topic"]
    digest_pages = [p for p in pages if p.get("page_type") in ("source_digest", "analysis_run_digest")]
    recent = sorted(pages, key=lambda p: p.get("updated_at", ""), reverse=True)[:20]

    lines.append("## 最近更新\n")
    if recent:
        for p in recent:
            slug = p.get("slug", "")
            title = p.get("title", "")
            lines.append(f"- [[{slug}|{title}]]")
    else:
        lines.append("- 暂无页面")
    lines.append("")

    lines.append("## 股票\n")
    if stock_pages:
        for p in stock_pages:
            slug = p.get("slug", "")
            title = p.get("title", "")
            lines.append(f"- [[{slug}|{title}]]")
    else:
        lines.append("- 暂无股票页面")
    lines.append("")

    lines.append("## 主题\n")
    if topic_pages:
        for p in topic_pages:
            slug = p.get("slug", "")
            title = p.get("title", "")
            lines.append(f"- [[{slug}|{title}]]")
    else:
        lines.append("- 暂无主题页面")
    lines.append("")

    lines.append("## Source Digest\n")
    if digest_pages:
        for p in digest_pages[:10]:
            slug = p.get("slug", "")
            title = p.get("title", "")
            lines.append(f"- [[{slug}|{title}]]")
    else:
        lines.append("- 暂无 source digest")
    lines.append("")

    lines.append(f"## 待处理来源 ({len(pending_sources)})\n")
    if pending_sources:
        lines.append("- 有 raw source 等待 ingest")
    else:
        lines.append("- 无待处理来源")
    lines.append("")

    lines.append("## 风险和冲突\n")
    lines.append("- [[pages/claims/contradictions|观点冲突]]")
    lines.append("- [[pages/claims/open_questions|待验证问题]]")
    lines.append("")

    lines.append("## 操作\n")
    lines.append("- [[pages/portfolio/overview|组合总览]]")
    lines.append("- [[pages/portfolio/trade_review|交易复盘]]")
    lines.append("")

    return "\n".join(lines) + "\n"


def render_log_entry(run: dict) -> str:
    now = run.get("completed_at") or run.get("started_at", "")
    trigger = run.get("trigger_type", "")
    source_id = run.get("source_id", "")
    status = run.get("status", "")
    pages = run.get("pages_touched", [])
    claims = run.get("claims_touched", [])

    lines = [
        f"## [{now}] {trigger} | {source_id}",
        "",
        f"- run_id: {run.get('run_id', '')}",
        f"- source_id: {source_id}",
        f"- status: {status}",
        "- pages_touched:",
    ]
    for p in pages:
        if isinstance(p, dict):
            lines.append(f"  - [[{p.get('slug', '')}|{p.get('title', '')}]]")
        else:
            lines.append(f"  - {p}")
    lines.append(f"- claims_added: {len(claims)}")
    lines.append("")

    return "\n".join(lines)
