import sys
import tempfile
from pathlib import Path

# Ensure tradingagents package is on sys.path for imports
_agents_dir = Path(__file__).resolve().parent.parent.parent / "src" / "agents"
if str(_agents_dir) not in sys.path:
    sys.path.insert(0, str(_agents_dir))

import pytest
from src.agents.tradingagents.agents.utils.memory import TradingMemoryLog


def test_store_decision_writes_front_matter_format():
    with tempfile.TemporaryDirectory() as tmp:
        log = TradingMemoryLog({"memory_log_path": str(Path(tmp) / "test.md")})
        log.store_decision(
            ticker="603738",
            trade_date="2026-05-28",
            final_trade_decision="Rating: **Buy**\nReason: strong fundamentals",
            price_at_decision=42.0,
            confidence=0.75,
        )
        raw = log._log_path.read_text(encoding="utf-8")
        assert "---" in raw
        assert 'ticker: "603738"' in raw
        assert 'date: "2026-05-28"' in raw
        assert "price_at_decision: 42.0" in raw
        assert 'signal: "Buy"' in raw
        assert "confidence: 0.75" in raw
        assert "## 决策" in raw


def test_load_entries_parses_front_matter():
    with tempfile.TemporaryDirectory() as tmp:
        log = TradingMemoryLog({"memory_log_path": str(Path(tmp) / "test.md")})
        log.store_decision(
            ticker="603738",
            trade_date="2026-05-28",
            final_trade_decision="Rating: **Buy**\nReason: strong",
            price_at_decision=42.0,
            confidence=0.75,
        )
        entries = log.load_entries()
        assert len(entries) == 1
        e = entries[0]
        assert e["ticker"] == "603738"
        assert e["date"] == "2026-05-28"
        assert e["price_at_decision"] == 42.0
        assert e["signal"] == "Buy"
        assert e["confidence"] == 0.75
        assert e["decision"] == "Rating: **Buy**\nReason: strong"
        assert e["pending"] is True
        assert e["rating"] == "Buy"


def test_get_past_context_formats_front_matter_entries():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.md"
        # Write a resolved front-matter entry directly
        resolved_entry = (
            '---\nticker: "603738"\ndate: "2026-05-28"\n'
            'price_at_decision: 42.0\nsignal: "Buy"\n---\n\n'
            '## 决策\n\nRating: **Buy**\n\n'
            '## 反思\n\nGood call.\n\n'
            '<!-- ENTRY_END -->\n\n'
        )
        path.write_text(resolved_entry, encoding="utf-8")
        log = TradingMemoryLog({"memory_log_path": str(path)})
        ctx = log.get_past_context("603738", n_same=5, n_cross=3)
        assert "603738" in ctx
        assert "Buy" in ctx
        assert "42.0" in ctx


def test_legacy_entries_still_parse_correctly():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "legacy.md"
        legacy_text = (
            '[2026-05-20 | 000001 | Hold | pending]\n\n'
            'DECISION:\nRating: **Hold**\nReason: neutral outlook\n\n'
            '<!-- ENTRY_END -->\n\n'
            '[2026-05-21 | 000001 | Buy | +5.2% | +3.1% | 5d]\n\n'
            'DECISION:\nRating: **Buy**\nReason: breakout\n\n'
            'REFLECTION:\nGood entry, held for gains.\n\n'
            '<!-- ENTRY_END -->'
        )
        path.write_text(legacy_text, encoding="utf-8")
        log = TradingMemoryLog({"memory_log_path": str(path)})
        entries = log.load_entries()
        assert len(entries) == 2

        e1 = entries[0]
        assert e1["date"] == "2026-05-20"
        assert e1["ticker"] == "000001"
        assert e1["rating"] == "Hold"
        assert e1["signal"] == "Hold"
        assert e1["pending"] is True
        assert "neutral outlook" in e1["decision"]

        e2 = entries[1]
        assert e2["date"] == "2026-05-21"
        assert e2["pending"] is False
        assert e2["raw"] == "+5.2%"
        assert e2["alpha"] == "+3.1%"
        assert e2["holding"] == "5d"
        assert "Good entry" in e2["reflection"]


def test_mixed_legacy_and_new_format():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "mixed.md"
        mixed_text = (
            '[2026-05-20 | 000001 | Hold | pending]\n\n'
            'DECISION:\nRating: **Hold**\n\n'
            '<!-- ENTRY_END -->\n\n'
            '---\nticker: "603738"\ndate: "2026-05-28"\n'
            'price_at_decision: 42.0\nsignal: "Buy"\n---\n\n'
            '## 决策\n\nRating: **Buy**\n\n'
            '<!-- ENTRY_END -->'
        )
        path.write_text(mixed_text, encoding="utf-8")
        log = TradingMemoryLog({"memory_log_path": str(path)})
        entries = log.load_entries()
        assert len(entries) == 2
        assert entries[0]["ticker"] == "000001"
        assert entries[0]["price_at_decision"] is None
        assert entries[1]["ticker"] == "603738"
        assert entries[1]["price_at_decision"] == 42.0


def test_batch_update_preserves_front_matter():
    with tempfile.TemporaryDirectory() as tmp:
        log = TradingMemoryLog({"memory_log_path": str(Path(tmp) / "test.md")})
        log.store_decision(
            ticker="603738",
            trade_date="2026-05-28",
            final_trade_decision="Rating: **Buy**\nReason: strong",
            price_at_decision=42.0,
            confidence=0.75,
        )
        log.batch_update_with_outcomes([{
            "ticker": "603738",
            "trade_date": "2026-05-28",
            "raw_return": 0.052,
            "alpha_return": 0.031,
            "holding_days": 5,
            "reflection": "Good call, price moved up as expected.",
        }])
        entries = log.load_entries()
        assert len(entries) == 1
        e = entries[0]
        assert e["ticker"] == "603738"
        assert e["price_at_decision"] == 42.0
        assert e["confidence"] == 0.75
        assert e["pending"] is False
        assert "Good call" in e["reflection"]

        # Verify raw text still has front-matter
        raw = log._log_path.read_text(encoding="utf-8")
        assert 'ticker: "603738"' in raw
        assert "price_at_decision: 42.0" in raw
        assert "## 反思" in raw


def test_update_with_outcome_preserves_front_matter():
    with tempfile.TemporaryDirectory() as tmp:
        log = TradingMemoryLog({"memory_log_path": str(Path(tmp) / "test.md")})
        log.store_decision(
            ticker="603738",
            trade_date="2026-05-28",
            final_trade_decision="Rating: **Buy**",
            price_at_decision=42.0,
        )
        log.update_with_outcome(
            ticker="603738",
            trade_date="2026-05-28",
            raw_return=0.052,
            alpha_return=0.031,
            holding_days=5,
            reflection="Worked out well.",
        )
        raw = log._log_path.read_text(encoding="utf-8")
        assert 'ticker: "603738"' in raw
        assert "price_at_decision: 42.0" in raw
        assert "## 反思" in raw
        assert "Worked out well" in raw


def test_store_decision_is_idempotent_for_front_matter():
    with tempfile.TemporaryDirectory() as tmp:
        log = TradingMemoryLog({"memory_log_path": str(Path(tmp) / "test.md")})
        for _ in range(3):
            log.store_decision(
                ticker="603738",
                trade_date="2026-05-28",
                final_trade_decision="Rating: **Buy**",
                price_at_decision=42.0,
            )
        entries = log.load_entries()
        assert len(entries) == 1


def test_get_recent_decisions_returns_decision_records():
    with tempfile.TemporaryDirectory() as tmp:
        log = TradingMemoryLog({"memory_log_path": str(Path(tmp) / "test.md")})
        log.store_decision(
            ticker="603738",
            trade_date="2026-05-28",
            final_trade_decision="Rating: **Buy**\nReason: strong",
            price_at_decision=42.0,
            confidence=0.75,
        )
        # Resolve the entry so it appears in recent_decisions
        log.update_with_outcome(
            ticker="603738",
            trade_date="2026-05-28",
            raw_return=0.05,
            alpha_return=0.03,
            holding_days=5,
            reflection="Good.",
        )
        records = log.get_recent_decisions("603738", limit=3)
        assert len(records) == 1
        r = records[0]
        assert r.ticker == "603738"
        assert r.date == "2026-05-28"
        assert r.price_at_decision == 42.0
        assert r.signal == "Buy"
        assert r.confidence == 0.75


def test_get_recent_decisions_with_delta():
    with tempfile.TemporaryDirectory() as tmp:
        log = TradingMemoryLog({"memory_log_path": str(Path(tmp) / "test.md")})
        log.store_decision(
            ticker="603738", trade_date="2026-05-20",
            final_trade_decision="Rating: **Buy**", price_at_decision=40.0,
        )
        log.update_with_outcome(
            ticker="603738", trade_date="2026-05-20",
            raw_return=0.05, alpha_return=0.03, holding_days=5, reflection="OK.",
        )
        log.store_decision(
            ticker="603738", trade_date="2026-05-28",
            final_trade_decision="Rating: **Hold**", price_at_decision=42.0,
        )
        log.update_with_outcome(
            ticker="603738", trade_date="2026-05-28",
            raw_return=0.02, alpha_return=0.01, holding_days=5, reflection="Hold.",
        )

        # Verify delta computation on records directly
        records = log.get_recent_decisions("603738", limit=3)
        assert len(records) == 2
        current_price = 45.0
        current_signal = "Buy"
        for r in records:
            if r.price_at_decision is not None:
                r.price_delta_pct = (current_price - r.price_at_decision) / r.price_at_decision
            r.signal_changed = r.signal != current_signal

        assert records[0].price_delta_pct == (45.0 - 42.0) / 42.0
        assert records[0].signal_changed is True  # Hold != Buy
        assert records[1].price_delta_pct == (45.0 - 40.0) / 40.0
        assert records[1].signal_changed is False  # Buy == Buy
