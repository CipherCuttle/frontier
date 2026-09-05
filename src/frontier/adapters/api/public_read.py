from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from frontier.application.public_read import PublicReadService
from frontier.domain.public_read import (
    PUBLIC_READ_API_VERSION,
    PUBLIC_READ_DEFAULT_LIMIT,
    PUBLIC_READ_MAX_LIMIT,
    PUBLIC_READ_RESPONSE_SCHEMA,
    EpisodeNotFoundError,
    NoCompleteSnapshotError,
    ObservationNotFoundError,
    PublicReadFailure,
    PublicViewKind,
    PublicViewPage,
    SnapshotIntegrityError,
    SnapshotNotFoundError,
)

SnapshotQuery = Annotated[str | None, Query()]
LimitQuery = Annotated[int, Query(ge=1, le=PUBLIC_READ_MAX_LIMIT)]
OffsetQuery = Annotated[int, Query(ge=0)]


class SnapshotBindingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: str
    receipt_id: str
    receipt_schema_version: str
    projection_name: str
    projection_version: str
    schema_version: str
    algorithm_version: str
    ranking_policy_version: str
    configuration_digest: str
    source_registry_version: str
    as_of: str
    input_digest: str
    output_digest: str


class EpisodeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int
    episode_id: str
    observation_ids: list[str]
    first_observed_at: str
    last_observed_at: str
    age_seconds: int
    evidence_count_total: int
    prospective_evidence_count: int
    backfill_evidence_count: int
    recovered_backlog_evidence_count: int
    mentions_1h: int
    mentions_6h: int
    mentions_24h: int
    previous_6h: int
    preprevious_6h: int
    velocity_6h_delta: int
    acceleration_6h: int
    source_ids: list[str]
    source_count: int
    signal_roles: list[str]
    source_role_diversity: int
    evidence_root_diversity: None = None
    confirmation: str


class ViewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = PUBLIC_READ_RESPONSE_SCHEMA
    snapshot: SnapshotBindingResponse
    generated_at: str
    transport_state: str
    freshness_state: str
    coverage_state: str
    schema_state: str
    view: PublicViewKind
    view_policy_version: str
    semantic_scope: str
    total: int
    limit: int
    offset: int
    items: list[EpisodeResponse]


class CollectionOccurrenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    reason: str
    trigger_id: str | None
    recovered_after_gap: bool
    occurrence_status: str
    started_at: str
    completed_at: str | None


class ObservationRelationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relation_id: str
    relation_type: str
    from_observation_id: str
    target_observation_id: str | None
    target_external_ref: str | None
    authority: str
    algorithm_version: str | None
    confidence: str | None
    evidence: dict[str, Any]


class ObservationEvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation_id: str
    schema_version: str
    canonicalization_version: str
    source_id: str
    source_item_key: str
    kind: str
    payload: dict[str, Any]
    source_published_at: str | None
    effective_at: str | None
    observed_at: str
    retrieved_at: str
    content_digest: str
    fetch_digest: str
    collection_occurrences: list[CollectionOccurrenceResponse]
    relations: list[ObservationRelationResponse]


class EpisodeEvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = PUBLIC_READ_RESPONSE_SCHEMA
    snapshot: SnapshotBindingResponse
    generated_at: str
    episode: EpisodeResponse
    observations: list[ObservationEvidenceResponse]


class ObservationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = PUBLIC_READ_RESPONSE_SCHEMA
    snapshot: SnapshotBindingResponse
    generated_at: str
    observation: ObservationEvidenceResponse


class SourceHealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    as_of: str
    transport: str
    freshness: str
    completeness: str
    schema_health: str = Field(alias="schema")
    details: dict[str, Any]


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = PUBLIC_READ_RESPONSE_SCHEMA
    snapshot: SnapshotBindingResponse
    generated_at: str
    transport_state: str
    freshness_state: str
    coverage_state: str
    schema_state: str
    sources: list[SourceHealthResponse]


class MetaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_version: str
    response_schema_family: str
    intelligence_authority: str
    mutation_authority: bool
    openapi_typescript_authority: str


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: str
    detail: str


def _failure_status(exc: PublicReadFailure) -> int:
    if isinstance(exc, (SnapshotNotFoundError, EpisodeNotFoundError, ObservationNotFoundError)):
        return 404
    if isinstance(exc, (NoCompleteSnapshotError, SnapshotIntegrityError)):
        return 503
    return 500


def _failure_detail(exc: PublicReadFailure) -> str:
    if isinstance(exc, NoCompleteSnapshotError):
        return "No publishable COMPLETE baseline snapshot is available."
    if isinstance(exc, SnapshotNotFoundError):
        return "The requested snapshot is not publishable or does not exist."
    if isinstance(exc, SnapshotIntegrityError):
        return "The selected snapshot failed integrity validation."
    if isinstance(exc, EpisodeNotFoundError):
        return "The requested episode is not present in the selected snapshot."
    if isinstance(exc, ObservationNotFoundError):
        return "The requested observation is unavailable at the selected snapshot horizon."
    return "The public read request failed."


def _view_response(page: PublicViewPage) -> ViewResponse:
    return ViewResponse.model_validate(
        {
            "snapshot": asdict(page.snapshot),
            "generated_at": page.generated_at,
            "transport_state": page.transport_state,
            "freshness_state": page.freshness_state,
            "coverage_state": page.coverage_state,
            "schema_state": page.schema_state,
            "view": page.view,
            "view_policy_version": page.view_policy_version,
            "semantic_scope": page.semantic_scope,
            "total": page.total,
            "limit": page.limit,
            "offset": page.offset,
            "items": list(page.items),
        }
    )


def create_public_read_app(service: PublicReadService) -> FastAPI:
    app = FastAPI(
        title="FRONTIER Public Read API",
        version=PUBLIC_READ_API_VERSION,
        docs_url=None,
        redoc_url=None,
        openapi_url="/openapi.json",
    )

    @app.exception_handler(PublicReadFailure)
    async def public_read_failure_handler(
        _request: Request, exc: PublicReadFailure
    ) -> JSONResponse:
        return JSONResponse(
            status_code=_failure_status(exc),
            content={"error": exc.code, "detail": _failure_detail(exc)},
        )

    @app.get("/v0/meta", response_model=MetaResponse, operation_id="getPublicReadMeta")
    def meta() -> MetaResponse:
        return MetaResponse(
            api_version=PUBLIC_READ_API_VERSION,
            response_schema_family=PUBLIC_READ_RESPONSE_SCHEMA,
            intelligence_authority="baseline-intelligence-v0",
            mutation_authority=False,
            openapi_typescript_authority="ADR-0008",
        )

    def view_endpoint(
        view: PublicViewKind,
        snapshot_id: str | None,
        limit: int,
        offset: int,
    ) -> ViewResponse:
        page = service.get_view(
            view,
            snapshot_id=snapshot_id,
            limit=limit,
            offset=offset,
        )
        return _view_response(page)

    @app.get("/v0/radar", response_model=ViewResponse, operation_id="getRadar")
    def radar(
        snapshot_id: SnapshotQuery = None,
        limit: LimitQuery = PUBLIC_READ_DEFAULT_LIMIT,
        offset: OffsetQuery = 0,
    ) -> ViewResponse:
        return view_endpoint(PublicViewKind.RADAR, snapshot_id, limit, offset)

    @app.get("/v0/now", response_model=ViewResponse, operation_id="getNow")
    def now(
        snapshot_id: SnapshotQuery = None,
        limit: LimitQuery = PUBLIC_READ_DEFAULT_LIMIT,
        offset: OffsetQuery = 0,
    ) -> ViewResponse:
        return view_endpoint(PublicViewKind.NOW, snapshot_id, limit, offset)

    @app.get("/v0/trending", response_model=ViewResponse, operation_id="getTrending")
    def trending(
        snapshot_id: SnapshotQuery = None,
        limit: LimitQuery = PUBLIC_READ_DEFAULT_LIMIT,
        offset: OffsetQuery = 0,
    ) -> ViewResponse:
        return view_endpoint(PublicViewKind.TRENDING, snapshot_id, limit, offset)

    @app.get(
        "/v0/episodes/{episode_id}",
        response_model=EpisodeEvidenceResponse,
        operation_id="getEpisode",
    )
    def episode(episode_id: str, snapshot_id: SnapshotQuery = None) -> EpisodeEvidenceResponse:
        value = service.get_episode(episode_id, snapshot_id=snapshot_id)
        return EpisodeEvidenceResponse.model_validate(asdict(value))

    @app.get(
        "/v0/observations/{observation_id}",
        response_model=ObservationResponse,
        operation_id="getObservation",
    )
    def observation(
        observation_id: str,
        snapshot_id: SnapshotQuery = None,
    ) -> ObservationResponse:
        value = service.get_observation(observation_id, snapshot_id=snapshot_id)
        return ObservationResponse.model_validate(asdict(value))

    @app.get("/v0/health", response_model=HealthResponse, operation_id="getHealth")
    def health(snapshot_id: SnapshotQuery = None) -> HealthResponse:
        value = service.get_health(snapshot_id=snapshot_id)
        return HealthResponse.model_validate(asdict(value))

    return app
