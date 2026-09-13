from __future__ import annotations

import re
from datetime import datetime
from typing import cast

import psycopg

from frontier.application.value_observatory_internal_boundary import (
    ExactNaiveBenchmarkBoundary,
    ExactPefV1BenchmarkBoundary,
)
from frontier.domain.advanced_intelligence import (
    PEF_ALGORITHM_VERSION,
    PEF_AUTHORITY_STATE,
    PEF_RANKING_POLICY_VERSION,
    PEF_RECEIPT_SCHEMA_VERSION,
    PEF_SCHEMA_VERSION,
    SHADOW_SCHEMA_VERSION,
    PefArtifactStatus,
    PefEpisodeRanking,
    ShadowRunStatus,
)
from frontier.domain.canonical_json import canonical_json_bytes
from frontier.domain.digests import Digest, sha256_digest, sha256_hex
from frontier.domain.health import HealthValue
from frontier.domain.intelligence import (
    BASELINE_ALGORITHM_VERSION,
    BASELINE_CONFIGURATION_DIGEST,
    BASELINE_PROJECTION_NAME,
    BASELINE_PROJECTION_VERSION,
    BASELINE_RANKING_POLICY_VERSION,
    BASELINE_RECEIPT_SCHEMA_VERSION,
    BASELINE_SCHEMA_VERSION,
    BaselineEpisode,
    BaselineSnapshot,
)
from frontier.domain.pef_v1 import (
    PEF_V1_CANDIDATE_ID,
    PEF_V1_CONFIGURATION_DIGEST,
    PEF_V1_EXPERIMENT_ID,
    PEF_V1_PROJECTION_NAME,
    PEF_V1_PROJECTION_VERSION,
    PefV1Artifact,
)
from frontier.domain.receipt import ProjectionReceipt, ProjectionStatus

ConnectionT = psycopg.Connection[tuple[object, ...]]
CursorT = psycopg.Cursor[tuple[object, ...]]
_RUN_CLASS_CONFIRMATORY = "CONFIRMATORY"
_FREEZE_RECEIPT_ID_RE = re.compile(r"^freezereceipt_[0-9a-f]{64}$")


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("benchmark knowledge horizon must be timezone-aware")


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} canonical JSON is not an object")
    return cast(dict[str, object], value)


def _objects(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise RuntimeError(f"{label} is not a list")
    return cast(list[object], value)


def _string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise RuntimeError(f"{label} is not a string")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeError(f"{label} is not an integer")
    return value


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise RuntimeError(f"{label} is not a boolean")
    return value


def _optional_integer(value: object, label: str) -> int | None:
    return None if value is None else _integer(value, label)


def _optional_string(value: object, label: str) -> str | None:
    return None if value is None else _string(value, label)


def _strings(value: object, label: str) -> tuple[str, ...]:
    values = _objects(value, label)
    if not all(isinstance(item, str) for item in values):
        raise RuntimeError(f"{label} is not a string list")
    return tuple(cast(str, item) for item in values)


def _timestamp(value: object, label: str) -> datetime:
    text = _string(value, label)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RuntimeError(f"{label} is not timezone-aware")
    return parsed


def _optional_timestamp(value: object, label: str) -> datetime | None:
    return None if value is None else _timestamp(value, label)


def _db_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, datetime):
        raise RuntimeError(f"{label} database value is not a timestamp")
    if value.tzinfo is None or value.utcoffset() is None:
        raise RuntimeError(f"{label} database timestamp is not timezone-aware")
    return value


def _receipt_from_row(
    row: tuple[object, ...], *, offset: int, expected_receipt_id: str
) -> ProjectionReceipt:
    try:
        receipt = ProjectionReceipt(
            receipt_schema_version=_string(row[offset], "receipt schema version"),
            projection_name=_string(row[offset + 1], "receipt projection name"),
            projection_version=_string(row[offset + 2], "receipt projection version"),
            schema_version=_string(row[offset + 3], "receipt schema"),
            algorithm_version=cast(str | None, row[offset + 4]),
            ranking_policy_version=cast(str | None, row[offset + 5]),
            configuration_digest=Digest(_string(row[offset + 6], "receipt configuration digest")),
            source_registry_version=Digest(
                _string(row[offset + 7], "receipt source registry version")
            ),
            as_of=_db_timestamp(row[offset + 8], "receipt as_of"),
            generated_at=_db_timestamp(row[offset + 9], "receipt generated_at"),
            input_digest=Digest(_string(row[offset + 10], "receipt input digest")),
            output_digest=Digest(_string(row[offset + 11], "receipt output digest")),
            status=ProjectionStatus(_string(row[offset + 12], "receipt status")),
        )
    except (TypeError, ValueError) as error:
        raise RuntimeError("persisted projection receipt is invalid") from error
    if receipt.receipt_id != expected_receipt_id:
        raise RuntimeError("persisted projection receipt id does not bind its canonical identity")
    return receipt


def _baseline_episode(raw: object) -> BaselineEpisode:
    item = _mapping(raw, "baseline episode")
    if item.get("evidence_root_diversity") is not None:
        raise RuntimeError("baseline episode evidence_root_diversity must remain unavailable")
    return BaselineEpisode(
        rank=_integer(item.get("rank"), "baseline episode rank"),
        episode_id=_string(item.get("episode_id"), "baseline episode id"),
        observation_ids=_strings(item.get("observation_ids"), "baseline observation ids"),
        first_observed_at=_timestamp(item.get("first_observed_at"), "baseline first_observed_at"),
        last_observed_at=_timestamp(item.get("last_observed_at"), "baseline last_observed_at"),
        age_seconds=_integer(item.get("age_seconds"), "baseline age_seconds"),
        evidence_count_total=_integer(
            item.get("evidence_count_total"), "baseline evidence_count_total"
        ),
        prospective_evidence_count=_integer(
            item.get("prospective_evidence_count"), "baseline prospective_evidence_count"
        ),
        backfill_evidence_count=_integer(
            item.get("backfill_evidence_count"), "baseline backfill_evidence_count"
        ),
        recovered_backlog_evidence_count=_integer(
            item.get("recovered_backlog_evidence_count"),
            "baseline recovered_backlog_evidence_count",
        ),
        mentions_1h=_integer(item.get("mentions_1h"), "baseline mentions_1h"),
        mentions_6h=_integer(item.get("mentions_6h"), "baseline mentions_6h"),
        mentions_24h=_integer(item.get("mentions_24h"), "baseline mentions_24h"),
        previous_6h=_integer(item.get("previous_6h"), "baseline previous_6h"),
        preprevious_6h=_integer(item.get("preprevious_6h"), "baseline preprevious_6h"),
        velocity_6h_delta=_integer(item.get("velocity_6h_delta"), "baseline velocity_6h_delta"),
        acceleration_6h=_integer(item.get("acceleration_6h"), "baseline acceleration_6h"),
        source_ids=_strings(item.get("source_ids"), "baseline source ids"),
        source_count=_integer(item.get("source_count"), "baseline source count"),
        signal_roles=_strings(item.get("signal_roles"), "baseline signal roles"),
        source_role_diversity=_integer(
            item.get("source_role_diversity"), "baseline source role diversity"
        ),
        evidence_root_diversity=None,
        confirmation=_string(item.get("confirmation"), "baseline confirmation"),
    )


def _baseline_snapshot(raw: object) -> BaselineSnapshot:
    document = _mapping(raw, "baseline snapshot")
    episodes = _objects(document.get("episodes"), "baseline snapshot episodes")
    try:
        snapshot = BaselineSnapshot(
            as_of=_timestamp(document.get("as_of"), "baseline snapshot as_of"),
            transport_state=HealthValue(
                _string(document.get("transport_state"), "baseline transport state")
            ),
            freshness_state=HealthValue(
                _string(document.get("freshness_state"), "baseline freshness state")
            ),
            coverage_state=HealthValue(
                _string(document.get("coverage_state"), "baseline coverage state")
            ),
            schema_state=HealthValue(
                _string(document.get("schema_state"), "baseline schema state")
            ),
            episodes=tuple(_baseline_episode(item) for item in episodes),
            schema_version=_string(document.get("schema_version"), "baseline schema version"),
            projection_version=_string(
                document.get("projection_version"), "baseline projection version"
            ),
            algorithm_version=_string(
                document.get("algorithm_version"), "baseline algorithm version"
            ),
            ranking_policy_version=_string(
                document.get("ranking_policy_version"), "baseline ranking policy version"
            ),
        )
    except ValueError as error:
        raise RuntimeError("persisted baseline snapshot is invalid") from error
    if snapshot.to_canonical() != document:
        raise RuntimeError("persisted baseline snapshot canonical payload drifted")
    return snapshot


def _pef_episode(raw: object) -> PefEpisodeRanking:
    item = _mapping(raw, "PEF_V1 episode")
    return PefEpisodeRanking(
        rank=_integer(item.get("rank"), "PEF_V1 episode rank"),
        episode_id=_string(item.get("episode_id"), "PEF_V1 episode id"),
        observation_ids=_strings(item.get("observation_ids"), "PEF_V1 observation ids"),
        has_any_prospective_evidence=_boolean(
            item.get("has_any_prospective_evidence"), "PEF_V1 prospective evidence flag"
        ),
        has_prospective_primary_emission=_boolean(
            item.get("has_prospective_primary_emission"), "PEF_V1 primary emission flag"
        ),
        prospective_last_observed_at=_optional_timestamp(
            item.get("prospective_last_observed_at"), "PEF_V1 prospective last observed at"
        ),
        prospective_age_seconds=_optional_integer(
            item.get("prospective_age_seconds"), "PEF_V1 prospective age seconds"
        ),
        prospective_source_role_diversity=_integer(
            item.get("prospective_source_role_diversity"),
            "PEF_V1 prospective source role diversity",
        ),
        prospective_evidence_count=_integer(
            item.get("prospective_evidence_count"), "PEF_V1 prospective evidence count"
        ),
        mentions_1h=_integer(item.get("mentions_1h"), "PEF_V1 mentions_1h"),
        mentions_6h=_integer(item.get("mentions_6h"), "PEF_V1 mentions_6h"),
        mentions_24h=_integer(item.get("mentions_24h"), "PEF_V1 mentions_24h"),
        velocity_6h_delta=_integer(item.get("velocity_6h_delta"), "PEF_V1 velocity_6h_delta"),
        acceleration_6h=_integer(item.get("acceleration_6h"), "PEF_V1 acceleration_6h"),
    )


def _pef_v1_artifact(raw: object, *, generated_at: datetime) -> PefV1Artifact:
    document = _mapping(raw, "PEF_V1 artifact")
    episodes = _objects(document.get("episodes"), "PEF_V1 artifact episodes")
    try:
        artifact = PefV1Artifact(
            as_of=_timestamp(document.get("as_of"), "PEF_V1 artifact as_of"),
            control_snapshot_id=_string(
                document.get("control_snapshot_id"), "PEF_V1 control snapshot id"
            ),
            control_receipt_id=_string(
                document.get("control_receipt_id"), "PEF_V1 control receipt id"
            ),
            source_registry_version=Digest(
                _string(document.get("source_registry_version"), "PEF_V1 source registry")
            ),
            generated_at=generated_at,
            status=PefArtifactStatus(_string(document.get("status"), "PEF_V1 artifact status")),
            failure_reason=_optional_string(
                document.get("failure_reason"), "PEF_V1 failure reason"
            ),
            episodes=tuple(_pef_episode(item) for item in episodes),
            experiment_id=_string(document.get("experiment_id"), "PEF_V1 experiment id"),
            candidate_id=_string(document.get("candidate_id"), "PEF_V1 candidate id"),
            schema_version=_string(document.get("schema_version"), "PEF_V1 schema version"),
            algorithm_version=_string(
                document.get("algorithm_version"), "PEF_V1 algorithm version"
            ),
            ranking_policy_version=_string(
                document.get("ranking_policy_version"), "PEF_V1 ranking policy version"
            ),
            configuration_digest=Digest(
                _string(document.get("configuration_digest"), "PEF_V1 configuration digest")
            ),
            authority_state=_string(document.get("authority_state"), "PEF_V1 authority state"),
            grouping_receipt_id=_string(
                document.get("grouping_receipt_id"), "PEF_V1 grouping receipt id"
            ),
        )
    except (TypeError, ValueError) as error:
        raise RuntimeError("persisted PEF_V1 artifact is invalid") from error
    if artifact.to_canonical() != document:
        raise RuntimeError("persisted PEF_V1 artifact canonical payload drifted")
    return artifact


def _require_naive_integrity(
    row: tuple[object, ...],
    *,
    knowledge_horizon: datetime,
    snapshot: BaselineSnapshot,
    receipt: ProjectionReceipt,
) -> None:
    snapshot_id = _string(row[0], "baseline snapshot id")
    raw_snapshot = _mapping(row[8], "baseline snapshot")
    raw_snapshot_id = "snapshot_" + sha256_hex(canonical_json_bytes(raw_snapshot))
    if snapshot_id != raw_snapshot_id or snapshot.snapshot_id != snapshot_id:
        raise RuntimeError("baseline snapshot id does not bind persisted canonical payload")
    if (
        snapshot.as_of != knowledge_horizon
        or _db_timestamp(row[5], "baseline as_of") != knowledge_horizon
    ):
        raise RuntimeError("baseline snapshot row does not bind the exact requested horizon")
    if (
        snapshot.projection_version != _string(row[1], "baseline projection version")
        or snapshot.schema_version != _string(row[2], "baseline schema version")
        or snapshot.algorithm_version != _string(row[3], "baseline algorithm version")
        or snapshot.ranking_policy_version != _string(row[4], "baseline ranking policy version")
    ):
        raise RuntimeError("baseline snapshot row identity does not match canonical payload")
    snapshot_digest = sha256_digest(canonical_json_bytes(snapshot.to_canonical()))
    if (
        snapshot_digest != Digest(_string(row[6], "baseline output digest"))
        or receipt.output_digest != snapshot_digest
    ):
        raise RuntimeError("baseline snapshot/receipt output binding is invalid")
    if receipt.as_of != knowledge_horizon or receipt.status is not ProjectionStatus.COMPLETE:
        raise RuntimeError("baseline receipt is not COMPLETE at the exact requested horizon")
    if (
        receipt.receipt_schema_version != BASELINE_RECEIPT_SCHEMA_VERSION
        or receipt.projection_name != BASELINE_PROJECTION_NAME
        or receipt.projection_version != BASELINE_PROJECTION_VERSION
        or receipt.schema_version != BASELINE_SCHEMA_VERSION
        or receipt.algorithm_version != BASELINE_ALGORITHM_VERSION
        or receipt.ranking_policy_version != BASELINE_RANKING_POLICY_VERSION
        or receipt.configuration_digest != BASELINE_CONFIGURATION_DIGEST
    ):
        raise RuntimeError("baseline receipt frozen identity mismatch")


def _require_pef_run_integrity(row: tuple[object, ...], *, knowledge_horizon: datetime) -> None:
    run_id = _string(row[0], "PEF_V1 run id")
    if _string(row[1], "PEF_V1 run class") != _RUN_CLASS_CONFIRMATORY:
        raise RuntimeError("exact PEF_V1 boundary is not a confirmatory frozen run")
    run_json = _mapping(row[13], "PEF_V1 shadow run")
    expected_run_digest = sha256_digest(canonical_json_bytes(run_json))
    if _string(row[12], "PEF_V1 run digest") != str(expected_run_digest):
        raise RuntimeError("PEF_V1 shadow run digest does not bind canonical payload")
    if run_id != "shadowrun_" + sha256_hex(canonical_json_bytes(run_json)):
        raise RuntimeError("PEF_V1 shadow run id does not bind canonical payload")

    row_status = _string(row[2], "PEF_V1 run status")
    row_candidate_id = _string(row[3], "PEF_V1 run candidate id")
    row_schema = _string(row[4], "PEF_V1 run schema")
    row_algorithm = _string(row[5], "PEF_V1 run algorithm")
    row_configuration = _string(row[6], "PEF_V1 run configuration")
    row_authority = _string(row[7], "PEF_V1 run authority")
    row_control_snapshot = _string(row[8], "PEF_V1 run control snapshot id")
    row_control_receipt = _string(row[9], "PEF_V1 run control receipt id")
    row_artifact = _string(row[10], "PEF_V1 run candidate artifact id")
    row_output_digest = _string(row[11], "PEF_V1 run candidate output digest")

    if _string(run_json.get("experiment_id"), "PEF_V1 run experiment id") != PEF_V1_EXPERIMENT_ID:
        raise RuntimeError("PEF_V1 shadow run experiment identity mismatch")
    if _timestamp(run_json.get("as_of"), "PEF_V1 run as_of") != knowledge_horizon:
        raise RuntimeError("PEF_V1 shadow run does not bind the exact requested horizon")
    if _timestamp(run_json.get("generated_at"), "PEF_V1 run generated_at") != knowledge_horizon:
        raise RuntimeError("PEF_V1 confirmatory run generated_at must equal its exact horizon")
    if row_candidate_id != PEF_V1_CANDIDATE_ID:
        raise RuntimeError("PEF_V1 shadow run candidate identity mismatch")
    if row_schema != SHADOW_SCHEMA_VERSION:
        raise RuntimeError("PEF_V1 shadow run schema identity mismatch")
    if row_algorithm != PEF_ALGORITHM_VERSION:
        raise RuntimeError("PEF_V1 shadow run algorithm identity mismatch")
    if Digest(row_configuration) != PEF_V1_CONFIGURATION_DIGEST:
        raise RuntimeError("PEF_V1 shadow run configuration identity mismatch")
    if row_authority != PEF_AUTHORITY_STATE:
        raise RuntimeError("PEF_V1 shadow run authority-state mismatch")

    json_bindings = (
        (_string(run_json.get("status"), "PEF_V1 run JSON status"), row_status),
        (_string(run_json.get("candidate_id"), "PEF_V1 run JSON candidate id"), row_candidate_id),
        (_string(run_json.get("schema_version"), "PEF_V1 run JSON schema"), row_schema),
        (_string(run_json.get("algorithm_version"), "PEF_V1 run JSON algorithm"), row_algorithm),
        (
            _string(run_json.get("configuration_digest"), "PEF_V1 run JSON configuration"),
            row_configuration,
        ),
        (_string(run_json.get("authority_state"), "PEF_V1 run JSON authority"), row_authority),
        (
            _string(run_json.get("control_snapshot_id"), "PEF_V1 run JSON control snapshot"),
            row_control_snapshot,
        ),
        (
            _string(run_json.get("control_receipt_id"), "PEF_V1 run JSON control receipt"),
            row_control_receipt,
        ),
        (
            _string(run_json.get("candidate_artifact_id"), "PEF_V1 run JSON artifact id"),
            row_artifact,
        ),
        (
            _string(
                run_json.get("candidate_output_digest"), "PEF_V1 run JSON output digest"
            ),
            row_output_digest,
        ),
    )
    if any(canonical_value != row_value for canonical_value, row_value in json_bindings):
        raise RuntimeError("PEF_V1 shadow run row does not bind canonical run payload")

    freeze_id = run_json.get("candidate_freeze_receipt_id")
    if not isinstance(freeze_id, str) or not _FREEZE_RECEIPT_ID_RE.fullmatch(freeze_id):
        raise RuntimeError("PEF_V1 shadow run is not bound to canonical frozen candidate authority")


def _require_pef_artifact_integrity(
    row: tuple[object, ...],
    *,
    knowledge_horizon: datetime,
    artifact: PefV1Artifact,
    receipt: ProjectionReceipt,
) -> None:
    artifact_id = _string(row[14], "PEF_V1 artifact id")
    raw_artifact = _mapping(row[28], "PEF_V1 artifact")
    if artifact_id != "artifact_" + sha256_hex(canonical_json_bytes(raw_artifact)):
        raise RuntimeError("PEF_V1 artifact id does not bind canonical payload")
    if artifact.artifact_id != artifact_id:
        raise RuntimeError("PEF_V1 typed artifact identity drifted from persisted payload")
    if (
        artifact.as_of != knowledge_horizon
        or _db_timestamp(row[22], "PEF_V1 artifact as_of") != knowledge_horizon
    ):
        raise RuntimeError("PEF_V1 artifact row does not bind the exact requested horizon")
    if (
        _string(row[15], "PEF_V1 projection version") != PEF_V1_PROJECTION_VERSION
        or _string(row[16], "PEF_V1 artifact schema") != PEF_SCHEMA_VERSION
        or _string(row[17], "PEF_V1 artifact algorithm") != PEF_ALGORITHM_VERSION
        or _string(row[18], "PEF_V1 artifact ranking policy") != PEF_RANKING_POLICY_VERSION
        or Digest(_string(row[19], "PEF_V1 artifact configuration")) != PEF_V1_CONFIGURATION_DIGEST
        or _string(row[20], "PEF_V1 artifact authority") != PEF_AUTHORITY_STATE
    ):
        raise RuntimeError("PEF_V1 artifact frozen identity mismatch")
    if (
        artifact.experiment_id != PEF_V1_EXPERIMENT_ID
        or artifact.candidate_id != PEF_V1_CANDIDATE_ID
    ):
        raise RuntimeError("PEF_V1 artifact experiment/candidate identity mismatch")
    if _optional_string(row[27], "PEF_V1 artifact failure reason") != artifact.failure_reason:
        raise RuntimeError("PEF_V1 artifact row failure reason does not bind canonical payload")
    artifact_digest = sha256_digest(canonical_json_bytes(artifact.to_canonical()))
    if (
        artifact_digest != Digest(_string(row[26], "PEF_V1 artifact output digest"))
        or receipt.output_digest != artifact_digest
        or _string(row[11], "PEF_V1 run candidate output digest") != str(artifact_digest)
    ):
        raise RuntimeError("PEF_V1 run/artifact/receipt output binding is invalid")
    if _string(row[10], "PEF_V1 run candidate artifact id") != artifact.artifact_id:
        raise RuntimeError("PEF_V1 shadow run does not bind the persisted artifact")
    if (
        _string(row[8], "PEF_V1 run control snapshot id") != artifact.control_snapshot_id
        or _string(row[9], "PEF_V1 run control receipt id") != artifact.control_receipt_id
        or _string(row[23], "PEF_V1 artifact control snapshot id") != artifact.control_snapshot_id
        or _string(row[24], "PEF_V1 artifact control receipt id") != artifact.control_receipt_id
    ):
        raise RuntimeError("PEF_V1 run/artifact control binding mismatch")
    run_status = ShadowRunStatus(_string(row[2], "PEF_V1 run status"))
    artifact_status = PefArtifactStatus(_string(row[21], "PEF_V1 artifact status"))
    expected_run_status = (
        ShadowRunStatus.RAN if artifact_status is PefArtifactStatus.RAN else ShadowRunStatus.FAILED
    )
    if artifact.status is not artifact_status or run_status is not expected_run_status:
        raise RuntimeError("PEF_V1 run/artifact status binding mismatch")
    if receipt.as_of != knowledge_horizon or receipt.generated_at != artifact.generated_at:
        raise RuntimeError("PEF_V1 receipt timing does not bind the persisted artifact")
    if (
        receipt.receipt_schema_version != PEF_RECEIPT_SCHEMA_VERSION
        or receipt.projection_name != PEF_V1_PROJECTION_NAME
        or receipt.projection_version != PEF_V1_PROJECTION_VERSION
        or receipt.schema_version != PEF_SCHEMA_VERSION
        or receipt.algorithm_version != PEF_ALGORITHM_VERSION
        or receipt.ranking_policy_version != PEF_RANKING_POLICY_VERSION
        or receipt.configuration_digest != PEF_V1_CONFIGURATION_DIGEST
        or receipt.source_registry_version != artifact.source_registry_version
    ):
        raise RuntimeError("PEF_V1 receipt frozen identity mismatch")
    expected_receipt_status = (
        ProjectionStatus.COMPLETE
        if artifact.status is PefArtifactStatus.RAN
        else ProjectionStatus.FAILED
    )
    if receipt.status is not expected_receipt_status:
        raise RuntimeError("PEF_V1 receipt status does not bind artifact status")


class PostgresInternalBenchmarkBoundaryResolver:
    """Read exact retained internal benchmark boundaries without fallback."""

    def __init__(self, connection: ConnectionT) -> None:
        self._connection = connection

    def resolve_naive(self, knowledge_horizon: datetime) -> ExactNaiveBenchmarkBoundary | None:
        _require_aware(knowledge_horizon)
        with self._connection.cursor() as cur:
            rows = _select_exact_naive_rows(cur, knowledge_horizon)
        if not rows:
            return None
        if len(rows) != 1:
            raise RuntimeError("ambiguous exact baseline benchmark boundary")
        row = rows[0]
        receipt_id = _string(row[7], "baseline receipt id")
        receipt = _receipt_from_row(row, offset=9, expected_receipt_id=receipt_id)
        snapshot = _baseline_snapshot(row[8])
        _require_naive_integrity(
            row,
            knowledge_horizon=knowledge_horizon,
            snapshot=snapshot,
            receipt=receipt,
        )
        return ExactNaiveBenchmarkBoundary(snapshot=snapshot, receipt=receipt)

    def resolve_pef_v1(self, knowledge_horizon: datetime) -> ExactPefV1BenchmarkBoundary | None:
        _require_aware(knowledge_horizon)
        with self._connection.cursor() as cur:
            rows = _select_exact_pef_v1_rows(cur, knowledge_horizon)
        if not rows:
            return None
        if len(rows) != 1:
            raise RuntimeError("ambiguous exact PEF_V1 benchmark boundary")
        row = rows[0]
        _require_pef_run_integrity(row, knowledge_horizon=knowledge_horizon)
        receipt_id = _string(row[25], "PEF_V1 candidate receipt id")
        receipt = _receipt_from_row(row, offset=29, expected_receipt_id=receipt_id)
        artifact = _pef_v1_artifact(row[28], generated_at=receipt.generated_at)
        _require_pef_artifact_integrity(
            row,
            knowledge_horizon=knowledge_horizon,
            artifact=artifact,
            receipt=receipt,
        )
        return ExactPefV1BenchmarkBoundary(
            run_id=_string(row[0], "PEF_V1 run id"),
            artifact=artifact,
            receipt=receipt,
        )


def _select_exact_naive_rows(cur: CursorT, knowledge_horizon: datetime) -> list[tuple[object, ...]]:
    cur.execute(
        """
        SELECT s.snapshot_id, s.projection_version, s.schema_version,
               s.algorithm_version, s.ranking_policy_version, s.as_of,
               s.output_digest, s.receipt_id, s.snapshot_json,
               r.receipt_schema_version, r.projection_name, r.projection_version,
               r.schema_version, r.algorithm_version, r.ranking_policy_version,
               r.configuration_digest, r.source_registry_version, r.as_of,
               r.generated_at, r.input_digest, r.output_digest, r.status
        FROM baseline_intelligence_snapshots s
        JOIN projection_receipts r ON r.receipt_id = s.receipt_id
        WHERE s.as_of = %s
        ORDER BY s.snapshot_id
        """,
        (knowledge_horizon,),
    )
    return list(cur.fetchall())


def _select_exact_pef_v1_rows(
    cur: CursorT, knowledge_horizon: datetime
) -> list[tuple[object, ...]]:
    cur.execute(
        """
        SELECT run.run_id, run.run_class, run.status, run.candidate_id,
               run.schema_version, run.algorithm_version, run.configuration_digest,
               run.authority_state, run.control_snapshot_id, run.control_receipt_id,
               run.candidate_artifact_id, run.candidate_output_digest,
               run.run_digest, run.run_json,
               artifact.artifact_id, artifact.projection_version,
               artifact.schema_version, artifact.algorithm_version,
               artifact.ranking_policy_version, artifact.configuration_digest,
               artifact.authority_state, artifact.status, artifact.as_of,
               artifact.control_snapshot_id, artifact.control_receipt_id,
               artifact.receipt_id, artifact.output_digest, artifact.failure_reason,
               artifact.artifact_json,
               receipt.receipt_schema_version, receipt.projection_name,
               receipt.projection_version, receipt.schema_version,
               receipt.algorithm_version, receipt.ranking_policy_version,
               receipt.configuration_digest, receipt.source_registry_version,
               receipt.as_of, receipt.generated_at, receipt.input_digest,
               receipt.output_digest, receipt.status
        FROM shadow_experiment_runs run
        JOIN pef_ranking_artifacts artifact
          ON artifact.artifact_id = run.candidate_artifact_id
        JOIN projection_receipts receipt ON receipt.receipt_id = artifact.receipt_id
        WHERE run.experiment_id = %s AND run.as_of = %s
        ORDER BY run.run_id
        """,
        (PEF_V1_EXPERIMENT_ID, knowledge_horizon),
    )
    return list(cur.fetchall())


__all__ = ["PostgresInternalBenchmarkBoundaryResolver"]
