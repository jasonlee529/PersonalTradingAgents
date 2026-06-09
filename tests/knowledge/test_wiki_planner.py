import json
from copy import deepcopy

import pytest

from src.config import Settings
from src.knowledge.wiki_planner import (
    DeterministicWikiPlanner,
    LLMWikiPlanner,
    create_wiki_planner,
)
from src.knowledge.wiki_models import WikiUpdatePlan


SAMPLE_SOURCE = {
    "source_id": "manual_source:test_001",
    "source_kind": "manual_source",
    "symbol": "603738",
    "trade_date": "2026-06-05",
    "title": "泰晶科技调研笔记",
    "markdown": "# 调研笔记\n\n晶振需求旺盛。",
    "metadata": {"manual_subtype": "note"},
}

VALID_PLAN_JSON = {
    "source_ids": ["manual_source:test_001"],
    "title": "Ingest manual_source: 泰晶科技调研笔记",
    "summary": "Test summary",
    "pages_to_create": [
        {
            "page_id": "source_digest:abc123",
            "page_type": "source_digest",
            "title": "泰晶科技调研笔记",
            "slug": "sources/manual_source/abc123",
            "markdown": "# 摘要\n\n调研笔记。",
            "metadata": {"source_id": "manual_source:test_001"},
        }
    ],
    "page_patches": [],
    "claims": [
        {
            "claim_id": "claim:test_001",
            "subject_type": "stock",
            "subject_id": "603738",
            "claim_type": "fact",
            "statement": "晶振需求旺盛",
            "source_ids": ["manual_source:test_001"],
        }
    ],
    "contradictions": [],
    "log_entry": "Test log",
    "warnings": [],
}


class FakeLLM:
    """Fake LLM that returns canned responses for testing."""

    def __init__(self, responses):
        self.responses = responses
        self.call_count = 0
        self.last_prompt = ""

    async def __call__(self, prompt: str) -> str:
        self.last_prompt = prompt
        response = self.responses[self.call_count]
        self.call_count += 1
        return response


@pytest.fixture
def planner_settings():
    return Settings(
        llm_provider="openai",
        openai_api_key="fake-key",
        test_mode=False,
    )


@pytest.mark.asyncio
async def test_llm_planner_valid_json(planner_settings):
    fake = FakeLLM([json.dumps(VALID_PLAN_JSON)])
    planner = LLMWikiPlanner(planner_settings, invoke_fn=fake)

    plan = await planner.plan_source_ingest(
        source=SAMPLE_SOURCE,
        related_pages=[],
        schema_text="schema",
    )

    assert isinstance(plan, WikiUpdatePlan)
    assert plan.source_ids == ["manual_source:test_001"]
    assert len(plan.pages_to_create) == 1
    assert plan.pages_to_create[0].page_type == "source_digest"
    assert len(plan.claims) == 1
    assert plan.claims[0].source_ids == ["manual_source:test_001"]
    assert plan.claims[0].confidence > 0


@pytest.mark.asyncio
async def test_deterministic_planner_sets_claim_confidence():
    planner = DeterministicWikiPlanner()

    plan = await planner.plan_source_ingest(
        source=SAMPLE_SOURCE,
        related_pages=[],
        schema_text="schema",
    )

    assert plan.claims
    assert plan.claims[0].confidence == 0.6


@pytest.mark.asyncio
async def test_llm_planner_defaults_missing_claim_confidence(planner_settings):
    no_confidence_plan = dict(VALID_PLAN_JSON)
    no_confidence_plan["claims"] = [
        {
            "claim_id": "claim:test_no_confidence",
            "subject_type": "stock",
            "subject_id": "603738",
            "claim_type": "fact",
            "statement": "晶振需求旺盛",
            "source_ids": ["manual_source:test_001"],
        }
    ]
    fake = FakeLLM([json.dumps(no_confidence_plan)])
    planner = LLMWikiPlanner(planner_settings, invoke_fn=fake)

    plan = await planner.plan_source_ingest(
        source=SAMPLE_SOURCE,
        related_pages=[],
        schema_text="schema",
    )

    assert plan.claims[0].confidence == 0.6


@pytest.mark.asyncio
async def test_llm_planner_non_json_triggers_repair(planner_settings):
    # First call: non-JSON, second call: valid JSON
    fake = FakeLLM(["Some prose before JSON\n```json\n" + json.dumps(VALID_PLAN_JSON) + "\n```", json.dumps(VALID_PLAN_JSON)])
    planner = LLMWikiPlanner(planner_settings, invoke_fn=fake)

    plan = await planner.plan_source_ingest(
        source=SAMPLE_SOURCE,
        related_pages=[],
        schema_text="schema",
    )

    assert isinstance(plan, WikiUpdatePlan)
    assert fake.call_count == 1  # Extracted from prose, no repair needed


@pytest.mark.asyncio
async def test_llm_planner_repair_succeeds(planner_settings):
    # First call: broken JSON, second call: valid JSON (repair)
    fake = FakeLLM(["not json at all", json.dumps(VALID_PLAN_JSON)])
    planner = LLMWikiPlanner(planner_settings, invoke_fn=fake)

    plan = await planner.plan_source_ingest(
        source=SAMPLE_SOURCE,
        related_pages=[],
        schema_text="schema",
    )

    assert isinstance(plan, WikiUpdatePlan)
    assert fake.call_count == 2  # Original + repair


@pytest.mark.asyncio
async def test_llm_planner_repair_fails_raises(planner_settings):
    fake = FakeLLM(["not json", "still not json"])
    planner = LLMWikiPlanner(planner_settings, invoke_fn=fake)

    with pytest.raises(ValueError) as exc_info:
        await planner.plan_source_ingest(
            source=SAMPLE_SOURCE,
            related_pages=[],
            schema_text="schema",
        )

    assert "repair" in str(exc_info.value).lower() or "json" in str(exc_info.value).lower()
    assert fake.call_count == 2


@pytest.mark.asyncio
async def test_llm_planner_claim_missing_source_ids_rejected(planner_settings):
    bad_plan = dict(VALID_PLAN_JSON)
    bad_plan["claims"] = [
        {
            "claim_id": "claim:no_source",
            "subject_type": "stock",
            "subject_id": "603738",
            "claim_type": "fact",
            "statement": "No source claim",
            "source_ids": [],
        }
    ]
    fake = FakeLLM([json.dumps(bad_plan)])
    planner = LLMWikiPlanner(planner_settings, invoke_fn=fake)

    with pytest.raises(ValueError) as exc_info:
        await planner.plan_source_ingest(
            source=SAMPLE_SOURCE,
            related_pages=[],
            schema_text="schema",
        )

    assert "source_id" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_llm_planner_unknown_source_id_rejected(planner_settings):
    bad_plan = dict(VALID_PLAN_JSON)
    bad_plan["claims"] = [
        {
            "claim_id": "claim:bad",
            "subject_type": "stock",
            "subject_id": "603738",
            "claim_type": "fact",
            "statement": "Bad source",
            "source_ids": ["manual_source:does_not_exist"],
        }
    ]
    fake = FakeLLM([json.dumps(bad_plan)])
    planner = LLMWikiPlanner(planner_settings, invoke_fn=fake)

    with pytest.raises(ValueError) as exc_info:
        await planner.plan_source_ingest(
            source=SAMPLE_SOURCE,
            related_pages=[],
            schema_text="schema",
        )

    assert "source_id" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_llm_planner_invalid_page_type_rejected(planner_settings):
    bad_plan = dict(VALID_PLAN_JSON)
    bad_plan["pages_to_create"] = [
        {
            "page_id": "bad:page",
            "page_type": "invalid_type",
            "title": "Bad",
            "slug": "bad",
            "markdown": "# Bad",
            "metadata": {},
        }
    ]
    fake = FakeLLM([json.dumps(bad_plan)])
    planner = LLMWikiPlanner(planner_settings, invoke_fn=fake)

    with pytest.raises(ValueError) as exc_info:
        await planner.plan_source_ingest(
            source=SAMPLE_SOURCE,
            related_pages=[],
            schema_text="schema",
        )

    assert "page_type" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_llm_planner_plan_analysis_run(planner_settings):
    analysis_plan = dict(VALID_PLAN_JSON)
    analysis_plan["source_ids"] = ["stock_analysis:s1", "stock_analysis:s2"]
    analysis_plan["claims"] = [
        {
            "claim_id": "claim:analysis_001",
            "subject_type": "stock",
            "subject_id": "603738",
            "claim_type": "decision",
            "statement": "Analysis decision",
            "source_ids": ["stock_analysis:s1", "stock_analysis:s2"],
        }
    ]
    fake = FakeLLM([json.dumps(analysis_plan)])
    planner = LLMWikiPlanner(planner_settings, invoke_fn=fake)

    sources = [
        {"source_id": "stock_analysis:s1", "source_kind": "stock_analysis", "symbol": "603738", "title": "A"},
        {"source_id": "stock_analysis:s2", "source_kind": "stock_analysis", "symbol": "603738", "title": "B"},
    ]

    plan = await planner.plan_analysis_run_ingest(
        sources=sources,
        related_pages=[],
        schema_text="schema",
    )

    assert isinstance(plan, WikiUpdatePlan)
    assert plan.source_ids == ["stock_analysis:s1", "stock_analysis:s2"]


def test_create_planner_test_mode_returns_deterministic():
    settings = Settings(test_mode=True)
    planner = create_wiki_planner(settings)
    assert isinstance(planner, DeterministicWikiPlanner)


def test_create_planner_normal_mode_returns_llm():
    settings = Settings(
        llm_provider="openai",
        openai_api_key="fake-key",
        test_mode=False,
    )
    planner = create_wiki_planner(settings)
    assert isinstance(planner, LLMWikiPlanner)


def test_create_planner_no_api_key_raises(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("WIKI_LLM_PROVIDER", raising=False)
    settings = Settings(
        llm_provider="deepseek",
        wiki_llm_provider="",
        deepseek_api_key="",
        test_mode=False,
        _env_file=None,
    )
    with pytest.raises(ValueError) as exc_info:
        create_wiki_planner(settings)
    assert "api key" in str(exc_info.value).lower()


def test_create_planner_fallback_returns_deterministic():
    settings = Settings(
        llm_provider="openai",
        openai_api_key="fake-key",
        test_mode=False,
    )
    planner = create_wiki_planner(settings, fallback=True)
    assert isinstance(planner, DeterministicWikiPlanner)


@pytest.mark.asyncio
async def test_llm_planner_prompt_contains_schema_and_source(planner_settings):
    fake = FakeLLM([json.dumps(VALID_PLAN_JSON)])
    planner = LLMWikiPlanner(planner_settings, invoke_fn=fake)

    await planner.plan_source_ingest(
        source=SAMPLE_SOURCE,
        related_pages=[],
        schema_text="wiki-maintainer schema content",
    )

    prompt = fake.last_prompt
    assert "wiki-maintainer schema content" in prompt
    assert "manual_source:test_001" in prompt
    assert "泰晶科技调研笔记" in prompt
    assert "WikiUpdatePlan" in prompt or "JSON" in prompt
    assert "stock:{symbol}" in prompt
    assert "stock:{symbol}:timeline" in prompt


@pytest.mark.asyncio
async def test_llm_planner_prompt_contains_related_pages(planner_settings):
    fake = FakeLLM([json.dumps(VALID_PLAN_JSON)])
    planner = LLMWikiPlanner(planner_settings, invoke_fn=fake)

    related = [
        {"page_id": "stock:603738", "page_type": "stock_profile", "title": "603738", "slug": "stocks/603738", "content": "# 603738\n\nexisting content"},
    ]

    await planner.plan_source_ingest(
        source=SAMPLE_SOURCE,
        related_pages=related,
        schema_text="schema",
    )

    prompt = fake.last_prompt
    assert "stock:603738" in prompt or "existing content" in prompt


@pytest.mark.asyncio
async def test_llm_planner_invalid_section_id_rejected(planner_settings):
    bad_plan = dict(VALID_PLAN_JSON)
    bad_plan["pages_to_create"] = [
        {
            "page_id": "stock:603738",
            "page_type": "stock_profile",
            "title": "603738",
            "slug": "stocks/603738",
            "markdown": "# 603738\n\n内容",
            "metadata": {"symbol": "603738"},
        }
    ]
    bad_plan["page_patches"] = [
        {
            "page_id": "stock:603738",
            "section_id": "invalid_section",
            "markdown": "补丁",
            "mode": "replace",
        }
    ]
    fake = FakeLLM([json.dumps(bad_plan)])
    planner = LLMWikiPlanner(planner_settings, invoke_fn=fake)

    with pytest.raises(ValueError) as exc_info:
        await planner.plan_source_ingest(
            source=SAMPLE_SOURCE,
            related_pages=[{"page_id": "stock:603738", "page_type": "stock_profile", "title": "603738", "slug": "stocks/603738"}],
            schema_text="schema",
        )

    assert "section_id" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_llm_planner_invalid_page_id_prefix_rejected(planner_settings):
    bad_plan = dict(VALID_PLAN_JSON)
    bad_plan["pages_to_create"] = [
        {
            "page_id": "wrong:prefix",
            "page_type": "stock_profile",
            "title": "Bad",
            "slug": "bad",
            "markdown": "# Bad",
            "metadata": {},
        }
    ]
    fake = FakeLLM([json.dumps(bad_plan)])
    planner = LLMWikiPlanner(planner_settings, invoke_fn=fake)

    with pytest.raises(ValueError) as exc_info:
        await planner.plan_source_ingest(
            source=SAMPLE_SOURCE,
            related_pages=[],
            schema_text="schema",
        )

    assert "page_id" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_llm_planner_normalizes_common_stock_page_id_variants(planner_settings):
    plan_json = deepcopy(VALID_PLAN_JSON)
    plan_json["pages_to_create"] = [
        {
            "page_id": "603738-stock-profile",
            "page_type": "stock_profile",
            "title": "603738",
            "slug": "stocks/603738",
            "markdown": "# 603738\n\n内容",
            "metadata": {},
        },
        {
            "page_id": "603738-timeline",
            "page_type": "stock_timeline",
            "title": "603738 Timeline",
            "slug": "stocks/603738_timeline",
            "markdown": "# Timeline\n\n内容",
            "metadata": {},
        },
    ]
    plan_json["page_patches"] = [
        {
            "page_id": "603738-stock-profile",
            "section_id": "summary",
            "markdown": "补丁",
            "mode": "replace",
        },
        {
            "page_id": "603738-timeline",
            "section_id": "timeline",
            "markdown": "- 2026-06-05: update",
            "mode": "append",
        },
    ]
    plan_json["claims"][0]["page_ids"] = ["603738-stock-profile", "603738-timeline"]

    fake = FakeLLM([json.dumps(plan_json)])
    planner = LLMWikiPlanner(planner_settings, invoke_fn=fake)

    plan = await planner.plan_source_ingest(
        source=SAMPLE_SOURCE,
        related_pages=[],
        schema_text="schema",
    )

    assert [page.page_id for page in plan.pages_to_create] == [
        "stock:603738",
        "stock:603738:timeline",
    ]
    assert [page.metadata["symbol"] for page in plan.pages_to_create] == ["603738", "603738"]
    assert [patch.page_id for patch in plan.page_patches] == [
        "stock:603738",
        "stock:603738:timeline",
    ]
    assert plan.claims[0].page_ids == ["stock:603738", "stock:603738:timeline"]


@pytest.mark.asyncio
async def test_llm_planner_absolute_path_rejected(planner_settings):
    bad_plan = dict(VALID_PLAN_JSON)
    bad_plan["pages_to_create"] = [
        {
            "page_id": "source_digest:abc123",
            "page_type": "source_digest",
            "title": "Bad",
            "slug": "bad",
            "markdown": "# Bad\n\nSee C:\\Users\\secret.md",
            "metadata": {},
        }
    ]
    fake = FakeLLM([json.dumps(bad_plan)])
    planner = LLMWikiPlanner(planner_settings, invoke_fn=fake)

    with pytest.raises(ValueError) as exc_info:
        await planner.plan_source_ingest(
            source=SAMPLE_SOURCE,
            related_pages=[],
            schema_text="schema",
        )

    assert "absolute path" in str(exc_info.value).lower() or "path" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_llm_planner_placeholder_rejected(planner_settings):
    bad_plan = dict(VALID_PLAN_JSON)
    bad_plan["pages_to_create"] = [
        {
            "page_id": "source_digest:abc123",
            "page_type": "source_digest",
            "title": "Bad",
            "slug": "bad",
            "markdown": "# Bad\n\n结论待补",
            "metadata": {},
        }
    ]
    fake = FakeLLM([json.dumps(bad_plan)])
    planner = LLMWikiPlanner(planner_settings, invoke_fn=fake)

    with pytest.raises(ValueError) as exc_info:
        await planner.plan_source_ingest(
            source=SAMPLE_SOURCE,
            related_pages=[],
            schema_text="schema",
        )

    assert "placeholder" in str(exc_info.value).lower() or "待补" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_llm_planner_placeholder_allowed_for_open_questions(planner_settings):
    ok_plan = dict(VALID_PLAN_JSON)
    ok_plan["pages_to_create"] = [
        {
            "page_id": "claims:open_questions",
            "page_type": "open_questions",
            "title": "Open Questions",
            "slug": "claims/open_questions",
            "markdown": "# Open Questions\n\n- TODO: verify revenue growth",
            "metadata": {},
        }
    ]
    ok_plan["claims"] = [
        {
            "claim_id": "claim:q1",
            "subject_type": "stock",
            "subject_id": "603738",
            "claim_type": "question",
            "statement": "TODO: verify revenue growth",
            "source_ids": ["manual_source:test_001"],
        }
    ]
    fake = FakeLLM([json.dumps(ok_plan)])
    planner = LLMWikiPlanner(planner_settings, invoke_fn=fake)

    plan = await planner.plan_source_ingest(
        source=SAMPLE_SOURCE,
        related_pages=[],
        schema_text="schema",
    )

    assert isinstance(plan, WikiUpdatePlan)
    assert plan.pages_to_create[0].page_type == "open_questions"
