from __future__ import annotations

from datetime import datetime
from typing import cast

import psycopg
from psycopg.pq import TransactionStatus

from frontier.application.freeze_publication import require_confirmatory_boundary
from frontier.domain.advanced_intelligence import (
    PEF_ALGORITHM_VERSION,
    PefArtifactStatus,
    PefEpisodeRanking,
    ShadowControlArmRanking,
    ShadowExperimentRun,
    ShadowRunStatus,
)
from frontier.domain.canonical_json import canonical_json_bytes, canonical_timestamp
from frontier.domain.digests import Digest, sha256_digest
from frontier.domain.health import HealthValue
from frontier.domain.pef_v1 import (
    PEF_V1_CANDIDATE_ID,
    PEF_V1_CONFIGURATION_DIGEST,
    PEF_V1_EXPERIMENT_ID,
    PEF_V1_PROJECTION_VERSION,
    PefV1Artifact,
)
from frontier.domain.receipt import ProjectionReceipt, ProjectionStatus
from frontier.domain.zero_day import (
    ZERO_DAY_RUN_CLASS,
    ZeroDayPefPersistenceBinding,
    ZeroDaySeal,
    build_zero_day_seal,
    require_zero_day_boundary,
)

from .intelligence import PostgresBaselineIntelligenceRepository

ConnectionT = psycopg.Connection[tuple[object, ...]]
CursorT = psycopg.Cursor[tuple[object, ...]]


def _document(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RuntimeError(f"ZERO-DAY persisted {label} is not an object")
    return cast(dict[str, object], value)


def _str(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise RuntimeError(f"ZERO-DAY persisted {label} is not a string")
    return value


def _optional_str(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _str(value, label)


def _int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeError(f"ZERO-DAY persisted {label} is not an integer")
    return value


def _optional_int(value: object, label: str) -> int | None:
    if value is None:
        return None
    return _int(value, label)


def _bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise RuntimeError(f"ZERO-DAY persisted {label} is not a boolean")
    return value


def _timestamp(value: object, label: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise RuntimeError(f"ZERO-DAY persisted {label} timestamp is invalid") from error
    else:
        raise RuntimeError(f"ZERO-DAY persisted {label} is not a timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RuntimeError(f"ZERO-DAY persisted {label} timestamp is not timezone-aware")
    return parsed


def _optional_timestamp(value: object, label: str) -> datetime | None:
    if value is None:
        return None
    return _timestamp(value, label)


def _digest(value: object, label: str) -> Digest:
    try:
        return Digest(_str(value, label))
    except ValueError as error:
        raise RuntimeError(f"ZERO-DAY persisted {label} digest is invalid") from error


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise RuntimeError(f"ZERO-DAY persisted {label} is not an array")
    return tuple(_str(item, label) for item in cast(list[object], value))


def _episode_ranking(raw: object) -> PefEpisodeRanking:
    document = _document(raw, "candidate episode")
    try:
        return PefEpisodeRanking(
            rank=_int(document["rank"], "candidate rank"),
            episode_id=_str(document["episode_id"], "candidate episode id"),
            observation_ids=_string_tuple(document["observation_ids"], "candidate observation ids"),
            has_any_prospective_evidence=_bool(
                document["has_any_prospective_evidence"],
                "candidate prospective-evidence flag",
            ),
            has_prospective_primary_emission=_bool(
                document["has_prospective_primary_emission"],
                "candidate primary-emission flag",
            ),
            prospective_last_observed_at=_optional_timestamp(
                document["prospective_last_observed_at"],
                "candidate prospective last observed at",
            ),
            prospective_age_seconds=_optional_int(
                document["prospective_age_seconds"],
                "candidate prospective age",
            ),
            prospective_source_role_diversity=_int(
                document["prospective_source_role_diversity"],
                "candidate source-role diversity",
            ),
            prospective_evidence_count=_int(
                document["prospective_evidence_count"],
                "candidate prospective evidence count",
            ),
            mentions_1h=_int(document["mentions_1h"], "candidate mentions_1h"),
            mentions_6h=_int(document["mentions_6h"], "candidate mentions_6h"),
            mentions_24h=_int(document["mentions_24h"], "candidate mentions_24h"),
            velocity_6h_delta=_int(document["velocity_6h_delta"], "candidate velocity_6h_delta"),
            acceleration_6h=_int(document["acceleration_6h"], "candidate acceleration_6h"),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError("ZERO-DAY persisted candidate episode is invalid") from error


def _artifact_from_canonical(raw: object, *, generated_at: datetime) -> PefV1Artifact:
    document = _document(raw, "candidate artifact JSON")
    raw_episodes = document.get("episodes")
    if not isinstance(raw_episodes, list):
        raise RuntimeError("ZERO-DAY persisted candidate episodes are not an array")
    try:
        artifact = PefV1Artifact(
            as_of=_timestamp(document["as_of"], "candidate as_of"),
            control_snapshot_id=_str(
                document["control_snapshot_id"], "candidate control snapshot id"
            ),
            control_receipt_id=_str(document["control_receipt_id"], "candidate control receipt id"),
            source_registry_version=_digest(
                document["source_registry_version"], "candidate source registry"
            ),
            generated_at=generated_at,
            status=PefArtifactStatus(_str(document["status"], "candidate status")),
            failure_reason=_optional_str(
                document.get("failure_reason"), "candidate failure reason"
            ),
            episodes=tuple(_episode_ranking(item) for item in cast(list[object], raw_episodes)),
            experiment_id=_str(document["experiment_id"], "candidate experiment id"),
            candidate_id=_str(document["candidate_id"], "candidate id"),
            schema_version=_str(document["schema_version"], "candidate schema version"),
            algorithm_version=_str(document["algorithm_version"], "candidate algorithm version"),
            ranking_policy_version=_str(
                document["ranking_policy_version"], "candidate ranking policy"
            ),
            configuration_digest=_digest(
                document["configuration_digest"], "candidate configuration"
            ),
            authority_state=_str(document["authority_state"], "candidate authority state"),
            grouping_receipt_id=_str(
                document["grouping_receipt_id"], "candidate grouping receipt id"
            ),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError("ZERO-DAY persisted candidate artifact is invalid") from error
    if artifact.to_canonical() != document:
        raise RuntimeError("ZERO-DAY candidate artifact canonical payload mismatch")
    return artifact


def _control_ranking(raw: object) -> ShadowControlArmRanking:
    document = _document(raw, "control ranking")
    try:
        ranking = ShadowControlArmRanking(
            rank=_int(document["rank"], "control rank"),
            episode_id=_str(document["episode_id"], "control episode id"),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError("ZERO-DAY persisted control ranking is invalid") from error
    if ranking.to_canonical() != document:
        raise RuntimeError("ZERO-DAY control ranking canonical payload mismatch")
    return ranking


def _run_from_canonical(raw: object) -> ShadowExperimentRun:
    document = _document(raw, "shadow run JSON")
    raw_ranking = document.get("control_ranking")
    if not isinstance(raw_ranking, list):
        raise RuntimeError("ZERO-DAY persisted control ranking is not an array")
    try:
        run = ShadowExperimentRun(
            as_of=_timestamp(document["as_of"], "run as_of"),
            generated_at=_timestamp(document["generated_at"], "run generated_at"),
            control_snapshot_id=_str(document["control_snapshot_id"], "run control snapshot id"),
            control_receipt_id=_str(document["control_receipt_id"], "run control receipt id"),
            coverage_state=HealthValue(
                _str(document["control_coverage_state"], "run coverage state")
            ),
            freshness_state=HealthValue(
                _str(document["control_freshness_state"], "run freshness state")
            ),
            transport_state=HealthValue(
                _str(document["control_transport_state"], "run transport state")
            ),
            schema_state=HealthValue(_str(document["control_schema_state"], "run schema state")),
            status=ShadowRunStatus(_str(document["status"], "run status")),
            episode_universe_digest=_digest(
                document["episode_universe_digest"], "run episode universe"
            ),
            candidate_artifact_id=_str(
                document["candidate_artifact_id"], "run candidate artifact id"
            ),
            candidate_output_digest=_digest(
                document["candidate_output_digest"], "run candidate output"
            ),
            control_ranking=tuple(
                _control_ranking(item) for item in cast(list[object], raw_ranking)
            ),
            failure_reason=_optional_str(document.get("failure_reason"), "run failure reason"),
            experiment_id=_str(document["experiment_id"], "run experiment id"),
            candidate_id=_str(document["candidate_id"], "run candidate id"),
            schema_version=_str(document["schema_version"], "run schema version"),
            algorithm_version=_str(document["algorithm_version"], "run algorithm version"),
            configuration_digest=_digest(document["configuration_digest"], "run configuration"),
            authority_state=_str(document["authority_state"], "run authority state"),
            candidate_freeze_receipt_id=_optional_str(
                document.get("candidate_freeze_receipt_id"),
                "run candidate freeze receipt id",
            ),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError("ZERO-DAY persisted shadow run is invalid") from error
    if run.to_canonical() != document:
        raise RuntimeError("ZERO-DAY shadow run canonical payload mismatch")
    return run


def _load_candidate_receipt(
    cur: CursorT, receipt_id: str
) -> tuple[ProjectionReceipt, datetime]:
    cur.execute(
        """
        SELECT receipt_id, receipt_schema_version, projection_name,
               projection_version, schema_version, algorithm_version,
               ranking_policy_version, configuration_digest,
               source_registry_version, as_of, generated_at,
               input_digest, output_digest, status, created_at
        FROM projection_receipts
        WHERE receipt_id = %s
        """,
        (receipt_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError("ZERO-DAY candidate projection receipt is missing")
    try:
        receipt = ProjectionReceipt(
            receipt_schema_version=cast(str, row[1]),
            projection_name=cast(str, row[2]),
            projection_version=cast(str, row[3]),
            schema_version=cast(str, row[4]),
            algorithm_version=cast(str | None, row[5]),
            ranking_policy_version=cast(str | None, row[6]),
            configuration_digest=Digest(cast(str, row[7])),
            source_registry_version=Digest(cast(str, row[8])),
            as_of=cast(datetime, row[9]),
            generated_at=cast(datetime, row[10]),
            input_digest=Digest(cast(str, row[11])),
            output_digest=Digest(cast(str, row[12])),
            status=ProjectionStatus(cast(str, row[13])),
        )
    except (TypeError, ValueError) as error:
        raise RuntimeError("ZERO-DAY candidate projection receipt row is invalid") from error
    if cast(str, row[0]) != receipt.receipt_id or receipt.receipt_id != receipt_id:
        raise RuntimeError("ZERO-DAY candidate projection receipt identity mismatch")
    return receipt, cast(datetime, row[14])


def _load_candidate_artifact(
    cur: CursorT,
    artifact_id: str,
) -> tuple[PefV1Artifact, str, datetime, ProjectionReceipt, datetime]:
    cur.execute(
        """
        SELECT artifact_id, projection_version, schema_version, algorithm_version,
               ranking_policy_version, configuration_digest, authority_state,
               status, as_of, control_snapshot_id, control_receipt_id,
               receipt_id, output_digest, failure_reason, artifact_json, created_at
        FROM pef_ranking_artifacts
        WHERE artifact_id = %s
        """,
        (artifact_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError("ZERO-DAY candidate artifact is missing")
    receipt_id = cast(str, row[11])
    receipt, receipt_persisted_at = _load_candidate_receipt(cur, receipt_id)
    artifact = _artifact_from_canonical(row[14], generated_at=receipt.generated_at)
    expected = (
        artifact.artifact_id,
        PEF_V1_PROJECTION_VERSION,
        artifact.schema_version,
        artifact.algorithm_version,
        artifact.ranking_policy_version,
        str(artifact.configuration_digest),
        artifact.authority_state,
        artifact.status.value,
        artifact.as_of,
        artifact.control_snapshot_id,
        artifact.control_receipt_id,
        receipt.receipt_id,
        str(artifact.output_digest),
        artifact.failure_reason,
    )
    if tuple(row[:14]) != expected:
        raise RuntimeError("ZERO-DAY candidate artifact row identity mismatch")
    if artifact_id != artifact.artifact_id:
        raise RuntimeError("ZERO-DAY candidate artifact content id mismatch")
    if receipt.output_digest != artifact.output_digest:
        raise RuntimeError("ZERO-DAY candidate receipt does not bind artifact output")
    return artifact, receipt_id, cast(datetime, row[15]), receipt, receipt_persisted_at


def _load_exact_run(
    cur: CursorT, as_of: datetime
) -> tuple[ShadowExperimentRun, str, datetime] | None:
    cur.execute(
        """
        SELECT run_id, experiment_id, candidate_id, schema_version,
               algorithm_version, configuration_digest, authority_state,
               status, as_of, control_snapshot_id, control_receipt_id,
               candidate_artifact_id, candidate_output_digest, coverage_state,
               episode_universe_digest, run_digest, failure_reason,
               run_class, run_json, created_at
        FROM shadow_experiment_runs
        WHERE experiment_id = %s
          AND candidate_id = %s
          AND as_of = %s
          AND run_class = %s
          AND status = 'RAN'
        ORDER BY run_id
        LIMIT 2
        """,
        (PEF_V1_EXPERIMENT_ID, PEF_V1_CANDIDATE_ID, as_of, ZERO_DAY_RUN_CLASS),
    )
    rows = cur.fetchall()
    if not rows:
        return None
    if len(rows) != 1:
        raise RuntimeError("ZERO-DAY exact boundary has ambiguous PEF_V1 confirmatory runs")
    row = rows[0]
    run = _run_from_canonical(row[18])
    expected = (
        run.run_id,
        run.experiment_id,
        run.candidate_id,
        run.schema_version,
        run.algorithm_version,
        str(run.configuration_digest),
        run.authority_state,
        run.status.value,
        run.as_of,
        run.control_snapshot_id,
        run.control_receipt_id,
        run.candidate_artifact_id,
        str(run.candidate_output_digest),
        run.coverage_state.value,
        str(run.episode_universe_digest),
        str(run.run_digest),
        run.failure_reason,
        ZERO_DAY_RUN_CLASS,
    )
    if tuple(row[:18]) != expected:
        raise RuntimeError("ZERO-DAY shadow run row identity mismatch")
    return run, cast(str, row[17]), cast(datetime, row[19])


def _validate_freeze_authority(cur: CursorT, receipt_id: str, *, as_of: datetime) -> None:
    cur.execute(
        """
        SELECT r.receipt_id, r.schema_version, r.candidate_id, r.experiment_id,
               r.algorithm_version, r.configuration_digest, r.status,
               r.implementation_commit, r.implementation_tree_digest,
               r.receipt_digest, r.frozen_at, r.durable_freeze_at, r.receipt_json,
               p.freeze_receipt_digest, p.implementation_commit,
               p.implementation_tree_digest, p.publication_committer_at,
               p.publication_digest, p.publication_json
        FROM candidate_freeze_receipts r
        LEFT JOIN candidate_freeze_publications p ON p.receipt_id = r.receipt_id
        WHERE r.receipt_id = %s
        """,
        (receipt_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError("ZERO-DAY bound candidate freeze receipt is missing")
    if tuple(row[2:7]) != (
        PEF_V1_CANDIDATE_ID,
        PEF_V1_EXPERIMENT_ID,
        PEF_ALGORITHM_VERSION,
        str(PEF_V1_CONFIGURATION_DIGEST),
        "FROZEN",
    ):
        raise RuntimeError("ZERO-DAY bound candidate freeze identity is invalid")

    receipt_json = _document(row[12], "freeze receipt JSON")
    expected_receipt_digest = sha256_digest(canonical_json_bytes(receipt_json))
    if cast(str, row[9]) != str(expected_receipt_digest):
        raise RuntimeError("ZERO-DAY bound freeze receipt digest mismatch")
    expected_receipt_id = "freezereceipt_" + str(expected_receipt_digest).removeprefix("sha256:")
    if cast(str, row[0]) != expected_receipt_id or receipt_id != expected_receipt_id:
        raise RuntimeError("ZERO-DAY bound freeze receipt content id mismatch")
    if _str(receipt_json.get("schema_version"), "freeze schema version") != cast(str, row[1]):
        raise RuntimeError("ZERO-DAY bound freeze receipt schema mismatch")
    for key, relational in (
        ("candidate_id", row[2]),
        ("experiment_id", row[3]),
        ("algorithm_version", row[4]),
        ("configuration_digest", row[5]),
        ("status", row[6]),
        ("implementation_commit", row[7]),
        ("implementation_tree_digest", row[8]),
    ):
        if receipt_json.get(key) != relational:
            raise RuntimeError("ZERO-DAY bound freeze receipt canonical identity mismatch")
    if receipt_json.get("frozen_at") != canonical_timestamp(cast(datetime, row[10])):
        raise RuntimeError("ZERO-DAY bound freeze receipt frozen_at mismatch")

    durable_freeze_at = cast(datetime | None, row[11])
    if durable_freeze_at is None:
        raise RuntimeError("ZERO-DAY bound candidate freeze is not durable")
    if row[16] is None or row[17] is None or row[18] is None:
        raise RuntimeError("ZERO-DAY bound candidate freeze has no Git publication authority")
    if cast(str, row[13]) != cast(str, row[9]):
        raise RuntimeError("ZERO-DAY freeze publication does not bind receipt digest")
    if cast(str, row[14]) != cast(str, row[7]) or cast(str, row[15]) != cast(str, row[8]):
        raise RuntimeError("ZERO-DAY freeze publication does not bind implementation identity")

    publication_at = cast(datetime, row[16])
    if publication_at < durable_freeze_at or publication_at < cast(datetime, row[10]):
        raise RuntimeError("ZERO-DAY freeze publication predates durable freeze authority")
    publication_json = _document(row[18], "freeze publication JSON")
    expected_publication_digest = sha256_digest(canonical_json_bytes(publication_json))
    if cast(str, row[17]) != str(expected_publication_digest):
        raise RuntimeError("ZERO-DAY freeze publication digest mismatch")
    if publication_json.get("freeze_receipt_id") != receipt_id:
        raise RuntimeError("ZERO-DAY freeze publication receipt id mismatch")
    if publication_json.get("freeze_receipt_digest") != cast(str, row[9]):
        raise RuntimeError("ZERO-DAY freeze publication receipt digest mismatch")
    if publication_json.get("implementation_commit") != row[7]:
        raise RuntimeError("ZERO-DAY freeze publication implementation commit mismatch")
    if publication_json.get("implementation_tree_digest") != row[8]:
        raise RuntimeError("ZERO-DAY freeze publication implementation tree mismatch")
    if publication_json.get("publication_committer_at") != canonical_timestamp(publication_at):
        raise RuntimeError("ZERO-DAY freeze publication timestamp mismatch")
    if publication_json.get("publication_repository") != "CipherCuttle/frontier":
        raise RuntimeError("ZERO-DAY freeze publication repository mismatch")
    if publication_json.get("publication_ref") != "refs/heads/main":
        raise RuntimeError("ZERO-DAY freeze publication ref mismatch")
    require_confirmatory_boundary(as_of=as_of, publication_committer_at=publication_at)


class PostgresZeroDayAdapter:
    """Read one exact persisted PEF_V1 boundary into a ZERO-DAY diagnostic seal.

    The adapter never writes. It reads under one repeatable-read, read-only
    PostgreSQL transaction, validates all persisted identities, reconstructs
    the exact baseline observation input set, and delegates selection to the
    pure ZERO-DAY domain builder. Missing exact RAN boundaries return ``None``;
    inconsistent or ambiguous persisted evidence fails closed.
    """

    def __init__(self, connection: ConnectionT) -> None:
        self._connection = connection
        self._baseline = PostgresBaselineIntelligenceRepository(connection)

    def build_seal_for_boundary(
        self,
        *,
        as_of: datetime,
        sealed_at: datetime,
    ) -> ZeroDaySeal | None:
        require_zero_day_boundary(as_of)
        if self._connection.info.transaction_status is not TransactionStatus.IDLE:
            raise RuntimeError("ZERO-DAY adapter requires an idle PostgreSQL connection")

        with self._connection.transaction(), self._connection.cursor() as cur:
            cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            loaded_run = _load_exact_run(cur, as_of)
            if loaded_run is None:
                return None
            run, run_class, run_persisted_at = loaded_run
            if run.candidate_freeze_receipt_id is None:
                raise RuntimeError("ZERO-DAY persisted PEF_V1 run is freeze-unbound")
            _validate_freeze_authority(
                cur,
                run.candidate_freeze_receipt_id,
                as_of=as_of,
            )
            (
                artifact,
                artifact_receipt_id,
                artifact_persisted_at,
                candidate_receipt,
                candidate_receipt_persisted_at,
            ) = _load_candidate_artifact(cur, run.candidate_artifact_id)
            observations = tuple(
                sorted(
                    self._baseline.list_baseline_observations_as_of(as_of),
                    key=lambda item: item.observation_id,
                )
            )
            persistence = ZeroDayPefPersistenceBinding(
                candidate_receipt=candidate_receipt,
                artifact_receipt_id=artifact_receipt_id,
                artifact_persisted_at=artifact_persisted_at,
                candidate_receipt_persisted_at=candidate_receipt_persisted_at,
                run_persisted_at=run_persisted_at,
            )
            return build_zero_day_seal(
                artifact,
                run,
                observations,
                persistence,
                run_class=run_class,
                sealed_at=sealed_at,
            )


__all__ = ["PostgresZeroDayAdapter"]
