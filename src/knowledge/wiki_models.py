from typing import Literal

from pydantic import BaseModel, Field


WIKI_PAGE_TYPES = {
    "home",
    "log",
    "source_digest",
    "analysis_run_digest",
    "stock_profile",
    "stock_timeline",
    "stock_analysis_runs",
    "topic",
    "daily_direction",
    "trade_month",
    "portfolio_overview",
    "trade_review",
    "contradictions",
    "open_questions",
    "saved_query",
}

WIKI_SOURCE_STATUSES = {
    "pending",
    "queued",
    "planning",
    "applying",
    "processed",
    "needs_reprocess",
    "failed",
    "ignored",
}

WIKI_RUNNING_SOURCE_STATUSES = {
    "queued",
    "planning",
    "applying",
}

WIKI_INGEST_STATUSES = {
    "queued",
    "pending",
    "planning",
    "applying",
    "completed",
    "failed",
    "cancelled",
}


class WikiPageUpsert(BaseModel):
    page_id: str
    page_type: str
    title: str
    slug: str
    markdown: str
    metadata: dict = Field(default_factory=dict)


class WikiPagePatch(BaseModel):
    page_id: str
    section_id: str
    markdown: str
    mode: Literal["replace", "append", "prepend"] = "replace"


class WikiClaim(BaseModel):
    claim_id: str = ""
    subject_type: str
    subject_id: str
    claim_type: str
    statement: str
    polarity: str = ""
    status: str = "active"
    confidence: float = 0.0
    source_ids: list[str] = Field(default_factory=list)
    page_ids: list[str] = Field(default_factory=list)
    contradicts: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class WikiUpdatePlan(BaseModel):
    source_ids: list[str]
    title: str
    summary: str
    pages_to_create: list[WikiPageUpsert] = Field(default_factory=list)
    page_patches: list[WikiPagePatch] = Field(default_factory=list)
    claims: list[WikiClaim] = Field(default_factory=list)
    contradictions: list[WikiClaim] = Field(default_factory=list)
    log_entry: str
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Plan validation
# ---------------------------------------------------------------------------

_PAGE_ID_PREFIXES: dict[str, str] = {
    "home": "home:",
    "stock_profile": "stock:",
    "stock_timeline": "stock:",
    "stock_analysis_runs": "stock:",
    "topic": "topic:",
    "daily_direction": "daily_direction:",
    "trade_month": "trade_month:",
    "portfolio_overview": "portfolio:",
    "trade_review": "portfolio:",
    "source_digest": "source_digest:",
    "analysis_run_digest": "analysis_run:",
    "contradictions": "claims:",
    "open_questions": "claims:",
    "saved_query": "query:",
}

_SECTION_ALLOWLIST: dict[str, set[str]] = {
    "stock_profile": {"summary", "position", "thesis", "catalysts", "risks", "evidence", "recent_updates", "links"},
    "stock_timeline": {"timeline"},
    "stock_analysis_runs": {"analysis_runs"},
    "topic": {"definition", "current_view", "related_stocks", "catalysts", "risks", "evidence"},
    "daily_direction": {"latest", "runs", "portfolio_relation", "validation"},
    "trade_month": {"summary", "entries", "ai_vs_actual", "review"},
    "portfolio_overview": {"summary", "position", "thesis", "catalysts", "risks", "evidence", "recent_updates", "links"},
    "trade_review": {"summary", "entries", "review"},
}

_PLACEHOLDER_PATTERNS = ["TODO", "待补", "待完善"]

# Regex for absolute paths (Windows C:\... and Unix /home/... /Users/... etc.)
import re as _re
_ABS_PATH_PATTERN = _re.compile(r"(^|[\s\"'])(([A-Za-z]:[\\/])|(/(home|Users|var|etc|opt|tmp|root|usr|bin|lib|lib64)(/|$)))")


def validate_wiki_update_plan(
    plan: WikiUpdatePlan,
    valid_source_ids: set[str] | None = None,
) -> list[str]:
    """Return a list of validation error messages (empty if valid)."""
    errors: list[str] = []

    # 1. Page types must be valid
    for page in plan.pages_to_create:
        if page.page_type not in WIKI_PAGE_TYPES:
            errors.append(f"Invalid page_type: {page.page_type}")

    # 2. page_id / page_type compatibility
    for page in plan.pages_to_create:
        expected_prefix = _PAGE_ID_PREFIXES.get(page.page_type)
        if expected_prefix and not page.page_id.startswith(expected_prefix):
            errors.append(
                f"page_id '{page.page_id}' does not match expected prefix '{expected_prefix}' for page_type '{page.page_type}'"
            )

    # 3. section_id allowlist
    # Build a map of page_id -> page_type from pages_to_create
    page_type_map = {p.page_id: p.page_type for p in plan.pages_to_create}
    for patch in plan.page_patches:
        pt = page_type_map.get(patch.page_id)
        if pt and pt in _SECTION_ALLOWLIST:
            allowed = _SECTION_ALLOWLIST[pt]
            if patch.section_id not in allowed:
                errors.append(
                    f"Invalid section_id '{patch.section_id}' for page_type '{pt}'. Allowed: {sorted(allowed)}"
                )

    # 4. No absolute paths in markdown or metadata values
    for page in plan.pages_to_create:
        if _ABS_PATH_PATTERN.search(page.markdown):
            errors.append(f"Absolute path detected in markdown for page {page.page_id}")
        for k, v in page.metadata.items():
            if isinstance(v, str) and _ABS_PATH_PATTERN.search(v):
                errors.append(f"Absolute path detected in metadata.{k} for page {page.page_id}")

    # 5. No placeholder conclusions (unless open_questions or question claim)
    for page in plan.pages_to_create:
        if page.page_type == "open_questions":
            continue
        for ph in _PLACEHOLDER_PATTERNS:
            if ph in page.markdown:
                errors.append(f"Placeholder '{ph}' found in markdown for page {page.page_id}")
        for k, v in page.metadata.items():
            if isinstance(v, str):
                for ph in _PLACEHOLDER_PATTERNS:
                    if ph in v:
                        errors.append(f"Placeholder '{ph}' found in metadata.{k} for page {page.page_id}")

    for claim in plan.claims:
        if claim.claim_type == "question":
            continue
        for ph in _PLACEHOLDER_PATTERNS:
            if ph in claim.statement:
                errors.append(f"Placeholder '{ph}' found in claim statement: {claim.statement[:60]}")

    for claim in plan.contradictions:
        for ph in _PLACEHOLDER_PATTERNS:
            if ph in claim.statement:
                errors.append(f"Placeholder '{ph}' found in contradiction statement: {claim.statement[:60]}")

    # 6. source_ids validity
    if valid_source_ids is not None:
        for sid in plan.source_ids:
            if sid not in valid_source_ids:
                errors.append(f"Plan references unknown source_id: {sid}")

    # 7. Claims must have source_ids and they must be valid
    for claim in plan.claims:
        if not claim.source_ids:
            errors.append(f"Claim missing source_ids: {claim.statement[:80]}")
        if valid_source_ids is not None:
            for csid in claim.source_ids:
                if csid not in valid_source_ids:
                    errors.append(f"Claim references unknown source_id: {csid}")

    for claim in plan.contradictions:
        if not claim.source_ids:
            errors.append(f"Contradiction missing source_ids: {claim.statement[:80]}")
        if valid_source_ids is not None:
            for csid in claim.source_ids:
                if csid not in valid_source_ids:
                    errors.append(f"Contradiction references unknown source_id: {csid}")

    return errors
