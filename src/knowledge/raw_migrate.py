from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path

from src.config import Settings
from src.knowledge.raw_store import RawStore


ANALYSIS_NODE_BY_PREFIX = {
    "01_market_report": "market_report",
    "02_sentiment_report": "sentiment_report",
    "03_news_report": "news_report",
    "04_fundamentals_report": "fundamentals_report",
    "05_catalyst_report": "catalyst_report",
    "06_flow_risk_report": "flow_risk_report",
    "08_data_quality_summary": "data_quality_summary",
    "10_bull_bear_debate": "bull_bear_debate",
    "20_trader_investment_plan": "trader_investment_plan",
    "30_risk_debate": "risk_debate",
    "31_final_trade_decision": "final_trade_decision",
    "99_full_report": "full_report",
}


def _empty_summary() -> dict:
    return {
        "daily_direction": 0,
        "stock_analysis": 0,
        "manual_source": 0,
        "news_article": 0,
        "skipped_chunks": 0,
        "missing_files": 0,
        "errors": [],
    }


def _is_date(value: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))


def _is_two_hex(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F]{2}", value))


def _run_time_from_name(path: Path) -> str:
    match = re.search(r"_(\d{6})\.md$", path.name)
    if not match:
        return ""
    raw = match.group(1)
    return f"{raw[:2]}:{raw[2:4]}:{raw[4:]}"


def classify_legacy_file(path: Path, knowledge_dir: Path) -> dict | None:
    rel = path.relative_to(knowledge_dir)
    parts = rel.parts
    if len(parts) < 2:
        return None
    if parts[0] == "raw":
        return None
    if _is_two_hex(parts[0]):
        return {"source_kind": "skip_chunk"}
    if len(parts) >= 3 and parts[0] == "market_overview" and _is_date(parts[1]):
        if path.name.startswith("50_sector_discovery_"):
            trade_date = parts[1]
            return {
                "source_kind": "daily_direction",
                "origin": "agent",
                "title": f"{trade_date} 今日方向",
                "metadata": {
                    "trade_date": trade_date,
                    "run_id": f"daily_direction:{trade_date}:{path.stem.split('_')[-1]}",
                    "run_time": _run_time_from_name(path),
                    "symbols": [],
                    "tags": [],
                    "agent_flow": "direction_discovery",
                    "source_ref": rel.as_posix(),
                },
            }
    if len(parts) >= 3 and _is_date(parts[1]):
        symbol = parts[0]
        trade_date = parts[1]
        for prefix, analysis_node in ANALYSIS_NODE_BY_PREFIX.items():
            if path.name.startswith(prefix):
                run_token = path.stem.split("_")[-1]
                return {
                    "source_kind": "stock_analysis",
                    "origin": "agent",
                    "title": f"{symbol} {trade_date} {analysis_node}",
                    "metadata": {
                        "symbol": symbol,
                        "symbols": [symbol],
                        "trade_date": trade_date,
                        "run_id": f"analysis:{symbol}:{trade_date}:{run_token}",
                        "run_time": _run_time_from_name(path),
                        "analysis_node": analysis_node,
                        "agent_flow": "trading_agents",
                        "tags": [f"stock/{symbol}", f"node/{analysis_node}"],
                        "source_ref": rel.as_posix(),
                    },
                }
    return None


async def migrate_raw(settings: Settings, dry_run: bool = True) -> dict:
    knowledge_dir = settings.knowledge_dir
    summary = _empty_summary()
    if not knowledge_dir.exists():
        summary["missing_files"] += 1
        return summary

    store = RawStore(settings)
    if not dry_run:
        await store.init_db()

    files = sorted(knowledge_dir.rglob("*.md"))
    for path in files:
        try:
            classified = classify_legacy_file(path, knowledge_dir)
            if not classified:
                continue
            source_kind = classified["source_kind"]
            if source_kind == "skip_chunk":
                summary["skipped_chunks"] += 1
                continue
            if source_kind not in summary:
                continue
            summary[source_kind] += 1
            if dry_run:
                continue
            markdown = path.read_text(encoding="utf-8")
            await store.add_source(
                source_kind=source_kind,
                origin=classified["origin"],
                title=classified["title"],
                markdown=markdown,
                metadata=classified["metadata"],
            )
        except FileNotFoundError:
            summary["missing_files"] += 1
        except Exception as exc:
            summary["errors"].append(f"{path}: {exc}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate legacy knowledge files into raw store.")
    parser.add_argument("--apply", action="store_true", help="Apply migration. Default is dry-run.")
    args = parser.parse_args()
    settings = Settings()
    settings.ensure_dirs()
    summary = asyncio.run(migrate_raw(settings, dry_run=not args.apply))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
