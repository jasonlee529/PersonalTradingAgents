from __future__ import annotations

from pydantic import BaseModel, Field


DOC_TYPE_RAW_SOURCE = "raw_source"
DOC_TYPE_WIKI_PAGE = "wiki_page"

ENTITY_TYPE_STOCK = "stock"
ENTITY_TYPE_TOPIC = "topic"
ENTITY_TYPE_SOURCE_KIND = "source_kind"
ENTITY_TYPE_CLAIM_TYPE = "claim_type"
ENTITY_TYPE_DATE = "date"
ENTITY_TYPE_UNKNOWN = "unknown"

BUILD_MODE_DRY_RUN = "dry_run"
BUILD_MODE_APPLY = "apply"
BUILD_MODE_REBUILD = "rebuild"

BUILD_STATUS_COMPLETED = "completed"
BUILD_STATUS_FAILED = "failed"


class DerivedDocument(BaseModel):
    doc_id: str
    doc_type: str
    source_id: str = ""
    page_id: str = ""
    title: str = ""
    path: str
    content_sha256: str
    metadata: dict = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class DerivedChunk(BaseModel):
    chunk_id: str
    doc_id: str
    doc_type: str
    ordinal: int
    heading_path: str = ""
    text: str
    text_sha256: str = ""
    token_estimate: int = 0
    metadata: dict = Field(default_factory=dict)
    created_at: str = ""


class DerivedEntity(BaseModel):
    entity_id: str
    entity_type: str
    name: str
    canonical_key: str = ""
    metadata: dict = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class DerivedEntityMention(BaseModel):
    entity_id: str
    doc_id: str
    chunk_id: str = ""
    mention_text: str
    mention_type: str = ""
    metadata: dict = Field(default_factory=dict)
    created_at: str = ""


class DerivedClaimRef(BaseModel):
    claim_id: str
    doc_id: str
    chunk_id: str = ""
    source_id: str = ""
    page_id: str = ""
    claim_type: str = ""
    status: str = ""
    metadata: dict = Field(default_factory=dict)
    created_at: str = ""


class DerivedLink(BaseModel):
    from_type: str
    from_id: str
    to_type: str
    to_id: str
    link_type: str
    metadata: dict = Field(default_factory=dict)
    created_at: str = ""


class DerivedBuildResult(BaseModel):
    run_id: str
    mode: str
    status: str
    documents_seen: int = 0
    documents_indexed: int = 0
    chunks_indexed: int = 0
    entities_indexed: int = 0
    error: str = ""
    started_at: str = ""
    completed_at: str = ""
