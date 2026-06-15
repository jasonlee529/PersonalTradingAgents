import hashlib
import json
import re
from datetime import datetime

from src.config import Settings
from src.knowledge.wiki_models import (
    WikiClaim,
    WikiPagePatch,
    WikiPageUpsert,
    WikiUpdatePlan,
    validate_wiki_update_plan,
)
from src.knowledge.wiki_renderers import (
    render_analysis_run_digest_page,
    render_daily_direction_template,
    render_source_digest_page,
    render_stock_analysis_runs_template,
    render_stock_profile_template,
    render_stock_timeline_template,
    render_trade_month_template,
)


def _stable_hash(value: str, length: int = 16) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


_SOURCE_CONFIDENCE_BY_KIND = {
    "announcement": 0.9,
    "daily_trade_log": 0.8,
    "research_report": 0.7,
    "manual_source": 0.6,
    "daily_direction": 0.6,
    "news_article": 0.5,
    "stock_analysis": 0.4,
}


def _default_source_confidence(source_kind: str) -> float:
    return _SOURCE_CONFIDENCE_BY_KIND.get(source_kind, 0.5)


def _default_claim_confidence(
    claim: WikiClaim,
    source_kind_by_id: dict[str, str] | None = None,
) -> float:
    kinds = [
        source_kind_by_id[sid]
        for sid in claim.source_ids
        if source_kind_by_id and sid in source_kind_by_id
    ]
    if not kinds:
        return 0.5
    return round(sum(_default_source_confidence(kind) for kind in kinds) / len(kinds), 2)


# ---------------------------------------------------------------------------
# Deterministic planner (fallback / test mode)
# ---------------------------------------------------------------------------

class DeterministicWikiPlanner:
    """Deterministic planner for wiki ingest. Does not use LLM."""

    async def plan_source_ingest(
        self,
        *,
        source: dict,
        related_pages: list[dict],
        schema_text: str,
    ) -> WikiUpdatePlan:
        source_id = source.get("source_id", "")
        source_kind = source.get("source_kind", "")
        symbol = source.get("symbol", "")
        trade_date = source.get("trade_date", "")
        title = source.get("title", "")

        pages_to_create: list[WikiPageUpsert] = []
        page_patches: list[WikiPagePatch] = []
        claims: list[WikiClaim] = []
        warnings: list[str] = []

        # 1. Source digest page
        digest_slug = f"sources/{source_kind}/{_stable_hash(source_id, 8)}"
        digest_page_id = f"source_digest:{_stable_hash(source_id, 8)}"
        digest_md = render_source_digest_page(
            source, summary=f"{title} ({source_kind})", claims=[]
        )
        pages_to_create.append(WikiPageUpsert(
            page_id=digest_page_id,
            page_type="source_digest",
            title=title,
            slug=digest_slug,
            markdown=digest_md,
            metadata={
                "source_ids": [source_id],
                "source_id": source_id,
                "source_kind": source_kind,
                "symbol": symbol,
                "trade_date": trade_date,
                "tags": [f"source/{source_kind}"] + ([f"stock/{symbol}"] if symbol else []),
            },
        ))

        # 2. Symbol-related pages
        if symbol:
            stock_page_id = f"stock:{symbol}"
            stock_slug = f"stocks/{symbol}"
            timeline_page_id = f"stock:{symbol}:timeline"
            timeline_slug = f"stocks/{symbol}_timeline"

            existing_ids = {p.get("page_id") for p in related_pages}

            if stock_page_id not in existing_ids:
                pages_to_create.append(WikiPageUpsert(
                    page_id=stock_page_id,
                    page_type="stock_profile",
                    title=f"{symbol} 股票档案",
                    slug=stock_slug,
                    markdown=render_stock_profile_template(symbol),
                    metadata={
                        "symbol": symbol,
                        "tags": [f"stock/{symbol}"],
                    },
                ))

            if timeline_page_id not in existing_ids:
                pages_to_create.append(WikiPageUpsert(
                    page_id=timeline_page_id,
                    page_type="stock_timeline",
                    title=f"{symbol} 时间线",
                    slug=timeline_slug,
                    markdown=render_stock_timeline_template(symbol),
                    metadata={
                        "symbol": symbol,
                        "tags": [f"stock/{symbol}"],
                    },
                ))

            # Patch recent_updates
            update_entry = f"- {_now_iso()[:10]} {source_kind}: {title}"
            page_patches.append(WikiPagePatch(
                page_id=stock_page_id,
                section_id="recent_updates",
                markdown=update_entry,
                mode="prepend",
            ))

            # Patch timeline
            timeline_entry = f"- {_now_iso()[:10]} {source_kind}: {title}\n  - 来源：[[{digest_slug}|{title}]]"
            page_patches.append(WikiPagePatch(
                page_id=timeline_page_id,
                section_id="timeline",
                markdown=timeline_entry,
                mode="append",
            ))

        # 3. daily_direction
        if source_kind == "daily_direction" and trade_date:
            daily_page_id = f"daily_direction:{trade_date}"
            daily_slug = f"daily/directions/{trade_date}"
            existing_ids = {p.get("page_id") for p in related_pages}
            if daily_page_id not in existing_ids:
                pages_to_create.append(WikiPageUpsert(
                    page_id=daily_page_id,
                    page_type="daily_direction",
                    title=f"{trade_date} 今日方向",
                    slug=daily_slug,
                    markdown=render_daily_direction_template(trade_date),
                    metadata={
                        "trade_date": trade_date,
                        "tags": ["daily_direction"],
                    },
                ))
            run_entry = f"- {_now_iso()[:10]} {title}"
            page_patches.append(WikiPagePatch(
                page_id=daily_page_id,
                section_id="runs",
                markdown=run_entry,
                mode="append",
            ))

        # 4. daily_trade_log
        if source_kind == "daily_trade_log" and trade_date:
            month = trade_date[:7]
            month_page_id = f"trade_month:{month}"
            month_slug = f"daily/trade_logs/{month}"
            existing_ids = {p.get("page_id") for p in related_pages}
            if month_page_id not in existing_ids:
                pages_to_create.append(WikiPageUpsert(
                    page_id=month_page_id,
                    page_type="trade_month",
                    title=f"{month} 交易记录",
                    slug=month_slug,
                    markdown=render_trade_month_template(month),
                    metadata={
                        "trade_date": trade_date,
                        "tags": ["trade_log"],
                    },
                ))
            entry = f"- {trade_date} {title}"
            page_patches.append(WikiPagePatch(
                page_id=month_page_id,
                section_id="entries",
                markdown=entry,
                mode="append",
            ))

        # 5. Claims
        claim_statement = f"{title} ({source_kind})"
        source_confidence = _default_source_confidence(source_kind)
        claims.append(WikiClaim(
            claim_id=f"claim:{_stable_hash(source_id + claim_statement, 16)}",
            subject_type="stock" if symbol else "general",
            subject_id=symbol or "general",
            claim_type="fact" if source_kind in ("announcement", "daily_trade_log") else "decision",
            statement=claim_statement,
            confidence=source_confidence,
            source_ids=[source_id],
            page_ids=[digest_page_id],
        ))

        log_entry = f"## [{_now_iso()}] ingest | {source_id} | {title}\n\n- status: planned\n- pages: {len(pages_to_create)}\n- claims: {len(claims)}"

        return WikiUpdatePlan(
            source_ids=[source_id],
            title=f"Ingest {source_kind}: {title}",
            summary=f"Deterministic plan for {source_id}",
            pages_to_create=pages_to_create,
            page_patches=page_patches,
            claims=claims,
            contradictions=[],
            log_entry=log_entry,
            warnings=warnings,
        )

    async def plan_analysis_run_ingest(
        self,
        *,
        sources: list[dict],
        related_pages: list[dict],
        schema_text: str,
    ) -> WikiUpdatePlan:
        if not sources:
            return WikiUpdatePlan(
                source_ids=[],
                title="Empty analysis run",
                summary="No sources provided",
                log_entry="",
            )

        first = sources[0]
        symbol = first.get("symbol", "")
        trade_date = first.get("trade_date", "")
        run_id = first.get("metadata", {}).get("run_id", "")
        source_ids = [s.get("source_id", "") for s in sources]

        # Sort by analysis_node order
        node_order = {
            "market_report": 1,
            "sentiment_report": 2,
            "news_report": 3,
            "fundamentals_report": 4,
            "catalyst_report": 5,
            "flow_risk_report": 6,
            "data_quality_summary": 8,
            "bull_bear_debate": 10,
            "trader_investment_plan": 20,
            "risk_debate": 30,
            "final_trade_decision": 31,
            "full_report": 99,
        }
        sorted_sources = sorted(
            sources,
            key=lambda s: node_order.get(s.get("metadata", {}).get("analysis_node", ""), 100),
        )

        pages_to_create: list[WikiPageUpsert] = []
        page_patches: list[WikiPagePatch] = []
        claims: list[WikiClaim] = []

        # Analysis run digest
        digest_slug = f"sources/stock_analysis/{symbol}_{trade_date}_{_stable_hash(run_id, 8)}"
        digest_page_id = f"analysis_run:{symbol}:{trade_date}:{_stable_hash(run_id, 8)}"
        digest_md = render_analysis_run_digest_page(
            sorted_sources,
            summary=f"{symbol} {trade_date} 分析 run",
            claims=[],
        )
        pages_to_create.append(WikiPageUpsert(
            page_id=digest_page_id,
            page_type="analysis_run_digest",
            title=f"{symbol} {trade_date} 分析 Run",
            slug=digest_slug,
            markdown=digest_md,
            metadata={
                "source_ids": source_ids,
                "symbol": symbol,
                "trade_date": trade_date,
                "run_id": run_id,
                "tags": ["analysis_run", f"stock/{symbol}"],
            },
        ))

        # Stock pages
        if symbol:
            stock_page_id = f"stock:{symbol}"
            stock_slug = f"stocks/{symbol}"
            timeline_page_id = f"stock:{symbol}:timeline"
            timeline_slug = f"stocks/{symbol}_timeline"
            runs_page_id = f"stock:{symbol}:analysis_runs"
            runs_slug = f"stocks/{symbol}_analysis_runs"

            existing_ids = {p.get("page_id") for p in related_pages}

            if stock_page_id not in existing_ids:
                pages_to_create.append(WikiPageUpsert(
                    page_id=stock_page_id,
                    page_type="stock_profile",
                    title=f"{symbol} 股票档案",
                    slug=stock_slug,
                    markdown=render_stock_profile_template(symbol),
                    metadata={"symbol": symbol, "tags": [f"stock/{symbol}"]},
                ))
            if timeline_page_id not in existing_ids:
                pages_to_create.append(WikiPageUpsert(
                    page_id=timeline_page_id,
                    page_type="stock_timeline",
                    title=f"{symbol} 时间线",
                    slug=timeline_slug,
                    markdown=render_stock_timeline_template(symbol),
                    metadata={"symbol": symbol, "tags": [f"stock/{symbol}"]},
                ))
            if runs_page_id not in existing_ids:
                pages_to_create.append(WikiPageUpsert(
                    page_id=runs_page_id,
                    page_type="stock_analysis_runs",
                    title=f"{symbol} 分析 Run 列表",
                    slug=runs_slug,
                    markdown=render_stock_analysis_runs_template(symbol),
                    metadata={"symbol": symbol, "tags": [f"stock/{symbol}"]},
                ))

            update_entry = f"- {_now_iso()[:10]} analysis_run: {symbol} {trade_date} 分析"
            page_patches.append(WikiPagePatch(
                page_id=stock_page_id,
                section_id="recent_updates",
                markdown=update_entry,
                mode="prepend",
            ))

            timeline_entry = f"- {_now_iso()[:10]} analysis_run: {symbol} {trade_date}\n  - 来源：[[{digest_slug}|{symbol} {trade_date} 分析 Run]]"
            page_patches.append(WikiPagePatch(
                page_id=timeline_page_id,
                section_id="timeline",
                markdown=timeline_entry,
                mode="append",
            ))

            # Add to analysis_runs table
            run_row = f"| {trade_date} | - | - | - | - | [[{digest_slug}|详情]] |"
            page_patches.append(WikiPagePatch(
                page_id=runs_page_id,
                section_id="analysis_runs",
                markdown=run_row,
                mode="append",
            ))

        # Claims
        for src in sorted_sources:
            sid = src.get("source_id", "")
            source_kind = src.get("source_kind", "stock_analysis")
            stmt = f"{src.get('title', '')} (stock_analysis)"
            claims.append(WikiClaim(
                claim_id=f"claim:{_stable_hash(sid + stmt, 16)}",
                subject_type="stock",
                subject_id=symbol,
                claim_type="decision",
                statement=stmt,
                confidence=_default_source_confidence(source_kind),
                source_ids=[sid],
                page_ids=[digest_page_id],
            ))

        log_entry = f"## [{_now_iso()}] ingest analysis_run | {run_id} | {symbol} {trade_date}\n\n- status: planned\n- sources: {len(source_ids)}\n- pages: {len(pages_to_create)}\n- claims: {len(claims)}"

        return WikiUpdatePlan(
            source_ids=source_ids,
            title=f"Analysis run {symbol} {trade_date}",
            summary=f"Deterministic plan for run {run_id}",
            pages_to_create=pages_to_create,
            page_patches=page_patches,
            claims=claims,
            contradictions=[],
            log_entry=log_entry,
            warnings=[],
        )

    async def plan_batch_ingest(
        self,
        *,
        sources: list[dict],
        related_pages: list[dict],
        schema_text: str,
    ) -> WikiUpdatePlan:
        plans: list[WikiUpdatePlan] = []
        for source in sources:
            plans.append(await self.plan_source_ingest(
                source=source,
                related_pages=related_pages,
                schema_text=schema_text,
            ))

        source_ids: list[str] = []
        pages_by_id: dict[str, WikiPageUpsert] = {}
        page_patches: list[WikiPagePatch] = []
        claims: list[WikiClaim] = []
        warnings: list[str] = []
        log_entries: list[str] = []

        for plan in plans:
            source_ids.extend(plan.source_ids)
            for page in plan.pages_to_create:
                pages_by_id.setdefault(page.page_id, page)
            page_patches.extend(plan.page_patches)
            claims.extend(plan.claims)
            warnings.extend(plan.warnings)
            if plan.log_entry:
                log_entries.append(plan.log_entry)

        return WikiUpdatePlan(
            source_ids=list(dict.fromkeys(source_ids)),
            title=f"Batch ingest {len(source_ids)} sources",
            summary=f"Deterministic batch plan for {len(source_ids)} raw sources",
            pages_to_create=list(pages_by_id.values()),
            page_patches=page_patches,
            claims=claims,
            contradictions=[],
            log_entry="\n\n".join(log_entries),
            warnings=warnings,
        )


# ---------------------------------------------------------------------------
# LLM-driven planner
# ---------------------------------------------------------------------------

_WIKI_UPDATE_PLAN_SCHEMA_TEXT = """
{
  "source_ids": ["..."],
  "title": "...",
  "summary": "...",
  "pages_to_create": [
    {
      "page_id": "...",
      "page_type": "...",
      "title": "...",
      "slug": "...",
      "markdown": "...",
      "metadata": {}
    }
  ],
  "page_patches": [
    {
      "page_id": "...",
      "section_id": "...",
      "markdown": "...",
      "mode": "replace"
    }
  ],
  "claims": [
    {
      "claim_id": "...",
      "subject_type": "...",
      "subject_id": "...",
      "claim_type": "...",
      "statement": "...",
      "confidence": 0.6,
      "source_ids": ["..."]
    }
  ],
  "contradictions": [],
  "log_entry": "...",
  "warnings": []
}
""".strip()


_HARD_CONSTRAINTS = """
## Hard Constraints

1. You can ONLY use information from the provided raw sources and related pages.
2. Do NOT fabricate facts, data, sources, company names, announcements, or research opinions.
3. Every factual claim MUST reference at least one source_id from the input raw sources.
4. If evidence is insufficient, write it to open_questions (as a claim with claim_type="question"), NOT as a conclusion.
5. Do NOT copy large sections of raw text; write summaries and citations only.
6. User actual trades are facts, NOT equivalent to correct decisions.
7. AI analysis is opinion, NOT equivalent to facts.
8. Announcements have higher priority than news and AI analysis.
9. Research reports are external opinions; label institution and publish time.
10. Do NOT output raw filesystem absolute paths.
11. Every claim MUST include confidence from 0.0 to 1.0 based on source credibility.
""".strip()


_PAGE_ID_RULES = """
## Page ID Rules

Use these exact page_id patterns. Do not invent alternate separators such as hyphens.

- stock_profile: `stock:{symbol}`. Example: `stock:603738`
- stock_timeline: `stock:{symbol}:timeline`. Example: `stock:603738:timeline`
- stock_analysis_runs: `stock:{symbol}:analysis_runs`. Example: `stock:603738:analysis_runs`
- source_digest: `source_digest:{stable_id}`
- analysis_run_digest: `analysis_run:{symbol}:{trade_date}:{stable_id}`
- daily_direction: `daily_direction:{YYYY-MM-DD}`
- trade_month: `trade_month:{YYYY-MM}`
- topic: `topic:{slug}`
- contradictions: `claims:contradictions`
- open_questions: `claims:open_questions`

If you patch a page, the page_patches.page_id must exactly match the page_id of the related page
or the page_id used in pages_to_create.
""".strip()


class LLMWikiPlanner:
    """LLM-driven planner that generates WikiUpdatePlan from raw sources."""

    def __init__(
        self,
        settings: Settings,
        wiki_store=None,
        invoke_fn=None,
    ):
        self.settings = settings
        self.wiki_store = wiki_store
        self._invoke_fn = invoke_fn

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def plan_source_ingest(
        self,
        *,
        source: dict,
        related_pages: list[dict],
        schema_text: str,
        recent_log: str = "",
    ) -> WikiUpdatePlan:
        prompt = self._build_source_prompt(source, related_pages, schema_text, recent_log)
        valid_source_ids = {source.get("source_id", "")}
        source_kind_by_id = {
            source.get("source_id", ""): source.get("source_kind", ""),
        }
        return await self._call_llm(prompt, valid_source_ids, source_kind_by_id)

    async def plan_analysis_run_ingest(
        self,
        *,
        sources: list[dict],
        related_pages: list[dict],
        schema_text: str,
        recent_log: str = "",
    ) -> WikiUpdatePlan:
        prompt = self._build_analysis_run_prompt(sources, related_pages, schema_text, recent_log)
        valid_source_ids = {s.get("source_id", "") for s in sources}
        source_kind_by_id = {
            s.get("source_id", ""): s.get("source_kind", "")
            for s in sources
        }
        return await self._call_llm(prompt, valid_source_ids, source_kind_by_id)

    async def plan_batch_ingest(
        self,
        *,
        sources: list[dict],
        related_pages: list[dict],
        schema_text: str,
        recent_log: str = "",
    ) -> WikiUpdatePlan:
        prompt = self._build_batch_prompt(sources, related_pages, schema_text, recent_log)
        valid_source_ids = {s.get("source_id", "") for s in sources}
        source_kind_by_id = {
            s.get("source_id", ""): s.get("source_kind", "")
            for s in sources
        }
        return await self._call_llm(prompt, valid_source_ids, source_kind_by_id)

    # ------------------------------------------------------------------
    # LLM invocation
    # ------------------------------------------------------------------

    async def _call_llm(
        self,
        prompt: str,
        valid_source_ids: set[str],
        source_kind_by_id: dict[str, str] | None = None,
    ) -> WikiUpdatePlan:
        raw_output = await self._invoke_llm(prompt)
        plan = await self._parse_and_validate(raw_output, valid_source_ids, source_kind_by_id)
        return plan

    async def _invoke_llm(self, prompt: str) -> str:
        """Call LLM and return raw text output."""
        if self._invoke_fn is not None:
            return await self._invoke_fn(prompt)

        # Real LLM call via project factory
        from src.agents.tradingagents.llm_clients.factory import create_llm_client
        from src.agents.tradingagents.llm_clients.provider_catalog import (
            get_api_key_field,
        )

        provider = _get_wiki_provider(self.settings)
        key_field = get_api_key_field(provider)
        api_key = getattr(self.settings, key_field, "") if key_field else ""
        if not api_key:
            raise ValueError(
                f"No API key for LLM provider '{provider}'. "
                f"Please configure the corresponding API key."
            )

        client = create_llm_client(
            provider=provider,
            model=self.settings.get_llm_model(provider, "quick"),
            api_key=api_key,
            timeout=self.settings.llm_timeout,
        )
        llm = client.get_llm()

        from langchain_core.messages import HumanMessage, SystemMessage

        messages = [
            SystemMessage(
                content="You are a precise wiki maintainer assistant. "
                "You output strictly valid JSON matching the requested schema. "
                "No prose outside the JSON."
            ),
            HumanMessage(content=prompt),
        ]
        response = llm.invoke(messages)
        return str(response.content)

    # ------------------------------------------------------------------
    # Parse / repair / validate
    # ------------------------------------------------------------------

    async def _parse_and_validate(
        self,
        raw_output: str,
        valid_source_ids: set[str],
        source_kind_by_id: dict[str, str] | None = None,
    ) -> WikiUpdatePlan:
        # 1. Try extract JSON
        data = self._extract_json(raw_output)

        # 2. Try repair once if extraction failed
        if data is None:
            data = await self._repair_json(raw_output)

        if data is None:
            raise ValueError(
                f"LLM output could not be parsed as JSON after repair. "
                f"Output preview: {raw_output[:500]}"
            )

        # 3. Pydantic validation
        try:
            plan = WikiUpdatePlan.model_validate(data)
        except Exception as exc:
            raise ValueError(f"LLM output failed Pydantic validation: {exc}") from exc

        self._normalize_plan_page_ids(plan)
        self._apply_default_claim_confidence(plan, source_kind_by_id)

        # 4. Custom validation
        errors = self._validate_plan(plan, valid_source_ids)
        if errors:
            raise ValueError("; ".join(errors))

        return plan

    def _apply_default_claim_confidence(
        self,
        plan: WikiUpdatePlan,
        source_kind_by_id: dict[str, str] | None = None,
    ) -> None:
        for claim in [*plan.claims, *plan.contradictions]:
            if claim.confidence <= 0:
                claim.confidence = _default_claim_confidence(claim, source_kind_by_id)
            else:
                claim.confidence = max(0.0, min(float(claim.confidence), 1.0))

    def _normalize_plan_page_ids(self, plan: WikiUpdatePlan) -> None:
        """Normalize common LLM-generated stock page_id variants before validation."""
        replacements: dict[str, str] = {}

        for page in plan.pages_to_create:
            normalized = self._normalized_stock_page_id(page)
            if normalized and normalized != page.page_id:
                replacements[page.page_id] = normalized
                page.page_id = normalized

        if not replacements:
            return

        for patch in plan.page_patches:
            patch.page_id = replacements.get(patch.page_id, patch.page_id)

        for claim in [*plan.claims, *plan.contradictions]:
            claim.page_ids = [
                replacements.get(page_id, page_id)
                for page_id in claim.page_ids
            ]

    @staticmethod
    def _normalized_stock_page_id(page: WikiPageUpsert) -> str | None:
        page_type = page.page_type
        if page_type not in {"stock_profile", "stock_timeline", "stock_analysis_runs"}:
            return None
        if page.page_id.startswith("stock:"):
            return None

        symbol = str(page.metadata.get("symbol") or "").strip()
        if not symbol:
            symbol = LLMWikiPlanner._infer_symbol_from_stock_page_id(page.page_id, page_type)
            if symbol:
                page.metadata["symbol"] = symbol

        if not symbol:
            return None

        if page_type == "stock_profile":
            return f"stock:{symbol}"
        if page_type == "stock_timeline":
            return f"stock:{symbol}:timeline"
        return f"stock:{symbol}:analysis_runs"

    @staticmethod
    def _infer_symbol_from_stock_page_id(page_id: str, page_type: str) -> str:
        suffixes_by_type = {
            "stock_profile": [
                "-stock-profile",
                "_stock_profile",
                "-profile",
                "_profile",
            ],
            "stock_timeline": [
                "-stock-timeline",
                "_stock_timeline",
                "-timeline",
                "_timeline",
            ],
            "stock_analysis_runs": [
                "-stock-analysis-runs",
                "_stock_analysis_runs",
                "-analysis-runs",
                "_analysis_runs",
            ],
        }

        for suffix in suffixes_by_type.get(page_type, []):
            if page_id.endswith(suffix):
                symbol = page_id[: -len(suffix)].strip()
                if re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z._-]*", symbol):
                    return symbol
        return ""

    def _extract_json(self, text: str) -> dict | None:
        """Try to extract a JSON object from LLM output."""
        # Direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Markdown code block
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # First { to last }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass

        return None

    async def _repair_json(self, raw_output: str) -> dict | None:
        """One-shot repair: ask LLM to fix broken JSON."""
        repair_prompt = (
            "The previous response was not valid JSON. "
            "Please fix it and return ONLY valid JSON, no other text.\n\n"
            f"Previous response:\n{raw_output}\n\n"
            "Return valid JSON only:"
        )
        try:
            repaired = await self._invoke_llm(repair_prompt)
        except Exception:
            return None
        return self._extract_json(repaired)

    def _validate_plan(self, plan: WikiUpdatePlan, valid_source_ids: set[str]) -> list[str]:
        """Return list of validation error messages (empty if valid)."""
        return validate_wiki_update_plan(plan, valid_source_ids=valid_source_ids)

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    def _build_source_prompt(
        self,
        source: dict,
        related_pages: list[dict],
        schema_text: str,
        recent_log: str,
    ) -> str:
        source_id = source.get("source_id", "")
        source_kind = source.get("source_kind", "")
        symbol = source.get("symbol", "")
        trade_date = source.get("trade_date", "")
        title = source.get("title", "")
        markdown = source.get("markdown", "")

        related_text = self._format_related_pages(related_pages)
        log_text = recent_log if recent_log else "(No recent log entries provided)"

        prompt = f"""You are a wiki maintainer assistant. Based on the provided raw source and related wiki pages, generate a WikiUpdatePlan in strict JSON format.

## Wiki Maintainer Schema

{schema_text}

## Raw Source

- source_id: `{source_id}`
- source_kind: `{source_kind}`
- symbol: `{symbol}`
- trade_date: `{trade_date}`
- title: {title}

```markdown
{markdown}
```

## Related Wiki Pages

{related_text}

## Recent Log Summary

{log_text}

{_HARD_CONSTRAINTS}

{_PAGE_ID_RULES}

## Output Format

Return ONLY valid JSON matching this WikiUpdatePlan schema:

{_WIKI_UPDATE_PLAN_SCHEMA_TEXT}

Do NOT include any text outside the JSON. Ensure all source_ids in the output exist in the input raw source.
"""
        return prompt

    def _build_analysis_run_prompt(
        self,
        sources: list[dict],
        related_pages: list[dict],
        schema_text: str,
        recent_log: str,
    ) -> str:
        sources_text = "\n\n".join(
            self._format_single_source(s) for s in sources
        )
        related_text = self._format_related_pages(related_pages)
        log_text = recent_log if recent_log else "(No recent log entries provided)"

        first = sources[0] if sources else {}
        symbol = first.get("symbol", "")
        trade_date = first.get("trade_date", "")

        prompt = f"""You are a wiki maintainer assistant. Based on the provided analysis run sources and related wiki pages, generate a WikiUpdatePlan in strict JSON format.

## Wiki Maintainer Schema

{schema_text}

## Analysis Run Sources

Symbol: {symbol}
Trade Date: {trade_date}
Sources ({len(sources)}):

{sources_text}

## Related Wiki Pages

{related_text}

## Recent Log Summary

{log_text}

{_HARD_CONSTRAINTS}

{_PAGE_ID_RULES}

## Output Format

Return ONLY valid JSON matching this WikiUpdatePlan schema:

{_WIKI_UPDATE_PLAN_SCHEMA_TEXT}

Do NOT include any text outside the JSON. Ensure all source_ids in the output exist in the input raw sources.
"""
        return prompt

    def _build_batch_prompt(
        self,
        sources: list[dict],
        related_pages: list[dict],
        schema_text: str,
        recent_log: str,
    ) -> str:
        sources_text = "\n\n".join(
            self._format_single_source(s) for s in sources
        )
        related_text = self._format_related_pages(related_pages)
        log_text = recent_log if recent_log else "(No recent log entries provided)"

        prompt = f"""You are a wiki maintainer assistant. Based on the provided batch of raw sources and related wiki pages, generate ONE WikiUpdatePlan in strict JSON format.

## Wiki Maintainer Schema

{schema_text}

## Raw Source Batch

Sources ({len(sources)}):

{sources_text}

## Related Wiki Pages

{related_text}

## Recent Log Summary

{log_text}

{_HARD_CONSTRAINTS}

{_PAGE_ID_RULES}

## Batch Rules

1. Return one consolidated plan for all provided raw sources.
2. Do not create duplicate pages with the same page_id.
3. Prefer one patch per target section that summarizes the whole batch when multiple sources touch the same page.
4. Include every input source_id in source_ids unless the source has no usable content; explain skipped sources in warnings.

## Output Format

Return ONLY valid JSON matching this WikiUpdatePlan schema:

{_WIKI_UPDATE_PLAN_SCHEMA_TEXT}

Do NOT include any text outside the JSON. Ensure all source_ids in the output exist in the input raw sources.
"""
        return prompt

    @staticmethod
    def _format_single_source(source: dict) -> str:
        lines = [
            f"- source_id: `{source.get('source_id', '')}`",
            f"  source_kind: `{source.get('source_kind', '')}`",
            f"  title: {source.get('title', '')}",
            f"  symbol: `{source.get('symbol', '')}`",
            f"  trade_date: `{source.get('trade_date', '')}`",
        ]
        md = source.get("markdown", "")
        if md:
            lines.append(f"  markdown:\n```markdown\n{md}\n```")
        return "\n".join(lines)

    @staticmethod
    def _format_related_pages(pages: list[dict]) -> str:
        if not pages:
            return "(No related pages)"
        lines = []
        for p in pages:
            page_id = p.get("page_id", "")
            page_type = p.get("page_type", "")
            title = p.get("title", "")
            content = p.get("content", "")
            lines.append(f"### {title} ({page_id}, type={page_type})")
            if content:
                lines.append(f"```markdown\n{content[:2000]}\n```")
            else:
                lines.append("(Content not available)")
            lines.append("")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Planner factory
# ---------------------------------------------------------------------------

def create_wiki_planner(
    settings: Settings,
    *,
    wiki_store=None,
    invoke_fn=None,
    fallback: bool = False,
) -> DeterministicWikiPlanner | LLMWikiPlanner:
    """Create the appropriate wiki planner based on settings.

    Args:
        settings: Application settings.
        wiki_store: Optional WikiStore for reading related page content.
        invoke_fn: Optional async callable(prompt) -> str for testing.
        fallback: If True, always return DeterministicWikiPlanner.

    Returns:
        DeterministicWikiPlanner in test_mode or when fallback=True.
        LLMWikiPlanner otherwise.

    Raises:
        ValueError: If LLM planner is requested but no API key is configured.
    """
    if settings.test_mode:
        return DeterministicWikiPlanner()

    if fallback:
        planner = DeterministicWikiPlanner()
        planner._planner_type = "deterministic"  # type: ignore[attr-defined]
        return planner

    from src.agents.tradingagents.llm_clients.provider_catalog import get_api_key_field

    provider = _get_wiki_provider(settings)
    key_field = get_api_key_field(provider)
    api_key = getattr(settings, key_field, "") if key_field else ""
    if not api_key:
        raise ValueError(
            f"No API key configured for LLM provider '{provider}'. "
            f"Please set the corresponding API key in your environment or .env file."
        )

    return LLMWikiPlanner(
        settings,
        wiki_store=wiki_store,
        invoke_fn=invoke_fn,
    )


def _get_wiki_provider(settings: Settings) -> str:
    return settings.wiki_llm_provider or "deepseek"
