from __future__ import annotations

from datetime import datetime
from typing import cast

import psycopg
from psycopg.types.json import Jsonb

from frontier.application.freeze_publication import (
    CandidateFreezePublication,
    require_confirmatory_boundary,
)
from frontier.application.pef_v1_confirmatory import (
    PefV1ConfirmatoryEvidence,
    PefV1FreezeBinding,
)
from frontier.domain.advanced_intelligence import (
    PEF_ALGORITHM_VERSION,
    PEF_AUTHORITY_STATE,
    PEF_RANKING_POLICY_VERSION,
    PEF_SCHEMA_VERSION,
    SHADOW_SCHEMA_VERSION,
)
from frontier.domain.candidate_freeze import FreezeStatus, RegistryEntryDigest
from frontier.domain.candidate_freeze_v1 import CandidateFreezeReceiptV1
from frontier.domain.canonical_json import canonical_json_bytes
from frontier.domain.digests import Digest, sha256_digest
from frontier.domain.grouping_v1 import (
    GROUPING_V1_ALGORITHM_VERSION,
    GROUPING_V1_CONFIGURATION_DIGEST,
    GROUPING_V1_PROJECTION_NAME,
    GROUPING_V1_PROJECTION_VERSION,
    GROUPING_V1_SCHEMA_VERSION,
)
from frontier.domain.intelligence import (
    BASELINE_ALGORITHM_VERSION,
    BASELINE_PROJECTION_NAME,
    BASELINE_PROJECTION_VERSION,
    BASELINE_RANKING_POLICY_VERSION,
    BASELINE_SCHEMA_VERSION,
)
from frontier.domain.pef_v1 import (
    PEF_V1_CANDIDATE_ID,
    PEF_V1_CONFIGURATION_DIGEST,
    PEF_V1_CONTROL_CONFIGURATION_DIGEST,
    PEF_V1_EXPERIMENT_ID,
    PEF_V1_PROJECTION_NAME,
    PEF_V1_PROJECTION_VERSION,
)
from frontier.domain.receipt import ProjectionReceipt, ProjectionStatus

RUN_CLASS_CONFIRMATORY = "CONFIRMATORY"

ConnectionT = psycopg.Connection[tuple[object, ...]]
CursorT = psycopg.Cursor[tuple[object, ...]]


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise RuntimeError("PEF_V1 freeze timestamp is not a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RuntimeError("PEF_V1 freeze timestamp is not timezone-aware")
    return parsed


def _optional_timestamp(value: object) -> datetime | None:
    return None if value is None else _timestamp(value)


def _digest(value: object) -> Digest:
    if not isinstance(value, str):
        raise RuntimeError("PEF_V1 freeze digest is not a string")
    return Digest(value)


def _optional_digest(value: object) -> Digest | None:
    return None if value is None else _digest(value)


def _receipt_from_canonical(raw: object) -> CandidateFreezeReceiptV1:
    if not isinstance(raw, dict):
        raise RuntimeError("PEF_V1 freeze receipt JSON is not an object")
    document = cast(dict[str, object], raw)
    raw_reasons_value = document.get("drift_reasons")
    if not isinstance(raw_reasons_value, list):
        raise RuntimeError("PEF_V1 freeze drift reasons are invalid")
    raw_reasons = cast(list[object], raw_reasons_value)
    if not all(isinstance(item, str) for item in raw_reasons):
        raise RuntimeError("PEF_V1 freeze drift reasons are invalid")
    drift_reasons = tuple(cast(str, item) for item in raw_reasons)

    raw_entries_value = document.get("registry_entry_digests")
    entries: tuple[RegistryEntryDigest, ...] | None
    if raw_entries_value is None:
        entries = None
    elif isinstance(raw_entries_value, list):
        raw_entries = cast(list[object], raw_entries_value)
        parsed_entries: list[RegistryEntryDigest] = []
        for raw_entry in raw_entries:
            if not isinstance(raw_entry, dict):
                raise RuntimeError("PEF_V1 registry digest entry is invalid")
            entry = cast(dict[str, object], raw_entry)
            path = entry.get("path")
            if not isinstance(path, str):
                raise RuntimeError("PEF_V1 registry digest path is invalid")
            parsed_entries.append(
                RegistryEntryDigest(path=path, digest=_digest(entry.get("digest")))
            )
        entries = tuple(parsed_entries)
    else:
        raise RuntimeError("PEF_V1 registry digest entries are invalid")

    try:
        status = FreezeStatus(cast(str, document["status"]))
        candidate_id = cast(str, document["candidate_id"])
        experiment_id = cast(str, document["experiment_id"])
        algorithm_version = cast(str, document["algorithm_version"])
        configuration_digest = _digest(document["configuration_digest"])
        preregistration_path = cast(str, document["preregistration_path"])
        schema_version = cast(str, document["schema_version"])
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError("PEF_V1 freeze receipt identity is invalid") from error

    return CandidateFreezeReceiptV1(
        frozen_at=_timestamp(document.get("frozen_at")),
        status=status,
        drift_reasons=drift_reasons,
        preregistration_digest=_digest(document.get("preregistration_digest")),
        preregistration_config_digest=_optional_digest(
            document.get("preregistration_config_digest")
        ),
        implementation_commit=cast(str | None, document.get("implementation_commit")),
        implementation_tree_digest=cast(str | None, document.get("implementation_tree_digest")),
        dependency_lock_digest=_optional_digest(document.get("dependency_lock_digest")),
        source_registry_digest=_optional_digest(document.get("source_registry_digest")),
        registry_entry_digests=entries,
        candidate_id=candidate_id,
        experiment_id=experiment_id,
        algorithm_version=algorithm_version,
        configuration_digest=configuration_digest,
        preregistration_path=preregistration_path,
        schema_version=schema_version,
        verified_at=_optional_timestamp(document.get("verified_at")),
        original_receipt_digest=_optional_digest(document.get("original_receipt_digest")),
    )


def _load_binding(cur: CursorT, receipt_id: str) -> PefV1FreezeBinding | None:
    cur.execute(
        """
        SELECT r.receipt_json, r.receipt_digest, r.durable_freeze_at,
               p.freeze_receipt_digest, p.implementation_commit,
               p.implementation_tree_digest, p.publication_commit,
               p.publication_committer_at, p.publication_digest, p.publication_json
        FROM candidate_freeze_receipts r
        LEFT JOIN candidate_freeze_publications p ON p.receipt_id = r.receipt_id
        WHERE r.receipt_id = %s AND r.experiment_id = %s
        """,
        (receipt_id, PEF_V1_EXPERIMENT_ID),
    )
    row = cur.fetchone()
    if row is None:
        return None
    receipt = _receipt_from_canonical(row[0])
    if receipt.receipt_id != receipt_id:
        raise RuntimeError("PEF_V1 freeze row id does not bind canonical receipt")
    if str(receipt.receipt_digest) != cast(str, row[1]):
        raise RuntimeError("PEF_V1 freeze row digest does not bind canonical receipt")

    publication_commit: str | None = None
    publication_committer_at: datetime | None = None
    publication_digest: Digest | None = None
    if row[7] is not None:
        try:
            publication = CandidateFreezePublication(
                freeze_receipt_id=receipt.receipt_id,
                freeze_receipt_digest=Digest(cast(str, row[3])),
                implementation_commit=cast(str, row[4]),
                implementation_tree_digest=cast(str, row[5]),
                publication_commit=cast(str, row[6]),
                publication_committer_at=cast(datetime, row[7]),
            )
        except (TypeError, ValueError) as error:
            raise RuntimeError("PEF_V1 freeze publication row is invalid") from error
        if publication.freeze_receipt_digest != receipt.receipt_digest:
            raise RuntimeError("PEF_V1 publication does not bind freeze receipt digest")
        if publication.implementation_commit != receipt.implementation_commit:
            raise RuntimeError("PEF_V1 publication does not bind implementation commit")
        if publication.implementation_tree_digest != receipt.implementation_tree_digest:
            raise RuntimeError("PEF_V1 publication does not bind implementation tree")
        publication_digest = Digest(cast(str, row[8]))
        if publication.publication_digest != publication_digest:
            raise RuntimeError("PEF_V1 publication row digest mismatch")
        if publication.to_canonical() != cast(dict[str, object], row[9]):
            raise RuntimeError("PEF_V1 publication row canonical payload mismatch")
        publication_commit = publication.publication_commit
        publication_committer_at = publication.publication_committer_at
    elif any(value is not None for value in row[3:7]) or row[8] is not None or row[9] is not None:
        raise RuntimeError("PEF_V1 freeze publication row is partial")

    return PefV1FreezeBinding(
        receipt=receipt,
        durable_freeze_at=cast(datetime | None, row[2]),
        publication_commit=publication_commit,
        publication_committer_at=publication_committer_at,
        publication_digest=publication_digest,
    )


def _latest_v1_receipt_id(cur: CursorT) -> str | None:
    cur.execute(
        """
        SELECT receipt_id
        FROM candidate_freeze_receipts
        WHERE experiment_id = %s
        ORDER BY frozen_at DESC, receipt_id DESC
        LIMIT 1
        """,
        (PEF_V1_EXPERIMENT_ID,),
    )
    row = cur.fetchone()
    return None if row is None else cast(str, row[0])


class PostgresPefV1FreezeBindingResolver:
    def __init__(self, connection: ConnectionT) -> None:
        self._connection = connection

    def latest_binding(self) -> PefV1FreezeBinding | None:
        with self._connection.cursor() as cur:
            receipt_id = _latest_v1_receipt_id(cur)
            if receipt_id is None:
                return None
            return _load_binding(cur, receipt_id)


def _receipt_values(receipt: ProjectionReceipt) -> tuple[object, ...]:
    return (
        receipt.receipt_id,
        receipt.receipt_schema_version,
        receipt.projection_name,
        receipt.projection_version,
        receipt.schema_version,
        receipt.algorithm_version,
        receipt.ranking_policy_version,
        str(receipt.configuration_digest),
        str(receipt.source_registry_version),
        receipt.as_of,
        receipt.generated_at,
        str(receipt.input_digest),
        str(receipt.output_digest),
        receipt.status.value,
    )


def _persist_receipt(cur: CursorT, receipt: ProjectionReceipt) -> None:
    values = _receipt_values(receipt)
    cur.execute(
        """
        INSERT INTO projection_receipts (
            receipt_id, receipt_schema_version, projection_name,
            projection_version, schema_version, algorithm_version,
            ranking_policy_version, configuration_digest,
            source_registry_version, as_of, generated_at,
            input_digest, output_digest, status
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (receipt_id) DO NOTHING
        RETURNING receipt_id
        """,
        values,
    )
    if cur.fetchone() is not None:
        return
    cur.execute(
        """
        SELECT receipt_id, receipt_schema_version, projection_name,
               projection_version, schema_version, algorithm_version,
               ranking_policy_version, configuration_digest,
               source_registry_version, as_of, generated_at,
               input_digest, output_digest, status
        FROM projection_receipts WHERE receipt_id = %s
        """,
        (receipt.receipt_id,),
    )
    existing = cur.fetchone()
    if existing != values:
        raise RuntimeError("PEF_V1 projection receipt identity conflict")


def _validate_receipt_identities(evidence: PefV1ConfirmatoryEvidence) -> None:
    grouping = evidence.grouping_receipt
    control = evidence.control_receipt
    candidate = evidence.candidate_receipt
    if grouping.status is not ProjectionStatus.COMPLETE:
        raise ValueError("PEF_V1 grouping receipt must be COMPLETE")
    if grouping.projection_name != GROUPING_V1_PROJECTION_NAME:
        raise ValueError("PEF_V1 grouping receipt projection name mismatch")
    if grouping.projection_version != GROUPING_V1_PROJECTION_VERSION:
        raise ValueError("PEF_V1 grouping receipt projection version mismatch")
    if grouping.schema_version != GROUPING_V1_SCHEMA_VERSION:
        raise ValueError("PEF_V1 grouping receipt schema mismatch")
    if grouping.algorithm_version != GROUPING_V1_ALGORITHM_VERSION:
        raise ValueError("PEF_V1 grouping receipt algorithm mismatch")
    if grouping.configuration_digest != GROUPING_V1_CONFIGURATION_DIGEST:
        raise ValueError("PEF_V1 grouping receipt configuration mismatch")

    if control.status is not ProjectionStatus.COMPLETE:
        raise ValueError("PEF_V1 control receipt must be COMPLETE")
    if control.projection_name != BASELINE_PROJECTION_NAME:
        raise ValueError("PEF_V1 control receipt projection name mismatch")
    if control.projection_version != BASELINE_PROJECTION_VERSION:
        raise ValueError("PEF_V1 control receipt projection version mismatch")
    if control.schema_version != BASELINE_SCHEMA_VERSION:
        raise ValueError("PEF_V1 control receipt schema mismatch")
    if control.algorithm_version != BASELINE_ALGORITHM_VERSION:
        raise ValueError("PEF_V1 control receipt algorithm mismatch")
    if control.ranking_policy_version != BASELINE_RANKING_POLICY_VERSION:
        raise ValueError("PEF_V1 control receipt ranking policy mismatch")
    if control.configuration_digest != PEF_V1_CONTROL_CONFIGURATION_DIGEST:
        raise ValueError("PEF_V1 control receipt configuration mismatch")

    if candidate.projection_name != PEF_V1_PROJECTION_NAME:
        raise ValueError("PEF_V1 candidate receipt projection name mismatch")
    if candidate.projection_version != PEF_V1_PROJECTION_VERSION:
        raise ValueError("PEF_V1 candidate receipt projection version mismatch")
    if candidate.schema_version != PEF_SCHEMA_VERSION:
        raise ValueError("PEF_V1 candidate receipt schema mismatch")
    if candidate.algorithm_version != PEF_ALGORITHM_VERSION:
        raise ValueError("PEF_V1 candidate receipt algorithm mismatch")
    if candidate.ranking_policy_version != PEF_RANKING_POLICY_VERSION:
        raise ValueError("PEF_V1 candidate receipt ranking policy mismatch")
    if candidate.configuration_digest != PEF_V1_CONFIGURATION_DIGEST:
        raise ValueError("PEF_V1 candidate receipt configuration mismatch")

    if not (
        grouping.source_registry_version
        == control.source_registry_version
        == candidate.source_registry_version
        == evidence.candidate_artifact.source_registry_version
    ):
        raise ValueError("PEF_V1 confirmatory evidence source registry mismatch")


def _validate_evidence(
    evidence: PefV1ConfirmatoryEvidence,
    *,
    expected_freeze_receipt_id: str,
    binding: PefV1FreezeBinding,
) -> None:
    _validate_receipt_identities(evidence)
    run = evidence.run
    artifact = evidence.candidate_artifact
    candidate_receipt = evidence.candidate_receipt
    if run.experiment_id != PEF_V1_EXPERIMENT_ID:
        raise ValueError("PEF_V1 confirmatory run experiment identity mismatch")
    if run.candidate_id != PEF_V1_CANDIDATE_ID:
        raise ValueError("PEF_V1 confirmatory run candidate identity mismatch")
    if run.configuration_digest != PEF_V1_CONFIGURATION_DIGEST:
        raise ValueError("PEF_V1 confirmatory run configuration identity mismatch")
    if run.schema_version != SHADOW_SCHEMA_VERSION:
        raise ValueError("PEF_V1 confirmatory run schema identity mismatch")
    if run.algorithm_version != PEF_ALGORITHM_VERSION:
        raise ValueError("PEF_V1 confirmatory run algorithm identity mismatch")
    if run.authority_state != PEF_AUTHORITY_STATE:
        raise ValueError("PEF_V1 confirmatory run authority state mismatch")
    if run.candidate_freeze_receipt_id != expected_freeze_receipt_id:
        raise ValueError("PEF_V1 confirmatory run does not bind the expected freeze receipt")
    if expected_freeze_receipt_id != binding.receipt.receipt_id:
        raise ValueError("PEF_V1 expected freeze receipt is not canonical DB authority")
    if binding.receipt.status is not FreezeStatus.FROZEN or binding.durable_freeze_at is None:
        raise ValueError("PEF_V1 canonical freeze is not durable FROZEN authority")
    if binding.publication_committer_at is None or binding.publication_digest is None:
        raise ValueError("PEF_V1 canonical freeze publication is missing")
    if binding.publication_committer_at < binding.durable_freeze_at:
        raise ValueError("PEF_V1 publication precedes durable freeze")
    require_confirmatory_boundary(
        as_of=run.as_of,
        publication_committer_at=binding.publication_committer_at,
    )
    if run.generated_at != run.as_of:
        raise ValueError("PEF_V1 confirmatory generated_at must equal its boundary")
    if run.run_digest != sha256_digest(canonical_json_bytes(run.to_canonical())):
        raise ValueError("PEF_V1 confirmatory run digest does not bind canonical payload")
    if artifact.experiment_id != PEF_V1_EXPERIMENT_ID:
        raise ValueError("PEF_V1 candidate artifact experiment identity mismatch")
    if artifact.candidate_id != PEF_V1_CANDIDATE_ID:
        raise ValueError("PEF_V1 candidate artifact candidate identity mismatch")
    if artifact.configuration_digest != PEF_V1_CONFIGURATION_DIGEST:
        raise ValueError("PEF_V1 candidate artifact configuration identity mismatch")
    if artifact.schema_version != PEF_SCHEMA_VERSION:
        raise ValueError("PEF_V1 candidate artifact schema identity mismatch")
    if artifact.algorithm_version != PEF_ALGORITHM_VERSION:
        raise ValueError("PEF_V1 candidate artifact algorithm identity mismatch")
    if artifact.ranking_policy_version != PEF_RANKING_POLICY_VERSION:
        raise ValueError("PEF_V1 candidate artifact ranking policy mismatch")
    if artifact.authority_state != PEF_AUTHORITY_STATE:
        raise ValueError("PEF_V1 candidate artifact authority state mismatch")
    if artifact.artifact_id != run.candidate_artifact_id:
        raise ValueError("PEF_V1 shadow run does not bind candidate artifact")
    if artifact.output_digest != run.candidate_output_digest:
        raise ValueError("PEF_V1 shadow run does not bind candidate output")
    if candidate_receipt.output_digest != artifact.output_digest:
        raise ValueError("PEF_V1 candidate receipt does not bind candidate artifact")
    if artifact.grouping_receipt_id != evidence.grouping_receipt.receipt_id:
        raise ValueError("PEF_V1 candidate artifact does not bind grouping receipt")
    if run.control_receipt_id != evidence.control_receipt.receipt_id:
        raise ValueError("PEF_V1 shadow run does not bind control receipt")
    if artifact.control_receipt_id != evidence.control_receipt.receipt_id:
        raise ValueError("PEF_V1 candidate artifact does not bind control receipt")
    if run.control_snapshot_id != artifact.control_snapshot_id:
        raise ValueError("PEF_V1 run and candidate artifact control snapshot mismatch")
    if not (
        run.as_of
        == artifact.as_of
        == candidate_receipt.as_of
        == evidence.control_receipt.as_of
        == evidence.grouping_receipt.as_of
    ):
        raise ValueError("PEF_V1 confirmatory evidence boundary mismatch")


class PostgresPefV1ConfirmatoryPersistence:
    """Append PEF_V1 confirmatory evidence only after canonical DB re-verification."""

    def __init__(self, connection: ConnectionT) -> None:
        self._connection = connection

    def latest_run_id_and_class_for_as_of(self, as_of: datetime) -> tuple[str, str, str] | None:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT run_id, run_class, status
                FROM shadow_experiment_runs
                WHERE experiment_id = %s AND as_of = %s
                ORDER BY run_id DESC
                LIMIT 1
                """,
                (PEF_V1_EXPERIMENT_ID, as_of),
            )
            row = cur.fetchone()
        return None if row is None else (cast(str, row[0]), cast(str, row[1]), cast(str, row[2]))

    def persist(
        self,
        evidence: PefV1ConfirmatoryEvidence,
        *,
        expected_freeze_receipt_id: str,
    ) -> str:
        with self._connection.transaction(), self._connection.cursor() as cur:
            # Hold the freeze authority stable for the entire append transaction.
            # INSERTs into candidate_freeze_receipts require ROW EXCLUSIVE and
            # therefore cannot supersede this authority until this transaction commits.
            cur.execute("LOCK TABLE candidate_freeze_receipts IN SHARE MODE")
            latest_receipt_id = _latest_v1_receipt_id(cur)
            if latest_receipt_id != expected_freeze_receipt_id:
                raise RuntimeError("PEF_V1 expected freeze is not latest canonical authority")
            binding = _load_binding(cur, expected_freeze_receipt_id)
            if binding is None:
                raise RuntimeError("PEF_V1 canonical freeze authority is missing")
            _validate_evidence(
                evidence,
                expected_freeze_receipt_id=expected_freeze_receipt_id,
                binding=binding,
            )

            _persist_receipt(cur, evidence.grouping_receipt)
            _persist_receipt(cur, evidence.control_receipt)
            _persist_receipt(cur, evidence.candidate_receipt)

            artifact = evidence.candidate_artifact
            cur.execute(
                """
                INSERT INTO pef_ranking_artifacts (
                    artifact_id, projection_version, schema_version,
                    algorithm_version, ranking_policy_version, configuration_digest,
                    authority_state, status, as_of, control_snapshot_id,
                    control_receipt_id, receipt_id, output_digest, failure_reason,
                    artifact_json
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (artifact_id) DO NOTHING
                RETURNING artifact_id
                """,
                (
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
                    evidence.candidate_receipt.receipt_id,
                    str(evidence.candidate_receipt.output_digest),
                    artifact.failure_reason,
                    Jsonb(artifact.to_canonical()),
                ),
            )
            if cur.fetchone() is None:
                cur.execute(
                    """
                    SELECT projection_version, receipt_id, output_digest, artifact_json
                    FROM pef_ranking_artifacts WHERE artifact_id = %s
                    """,
                    (artifact.artifact_id,),
                )
                row = cur.fetchone()
                if row is None or (
                    cast(str, row[0]) != PEF_V1_PROJECTION_VERSION
                    or cast(str, row[1]) != evidence.candidate_receipt.receipt_id
                    or cast(str, row[2]) != str(evidence.candidate_receipt.output_digest)
                    or cast(dict[str, object], row[3]) != artifact.to_canonical()
                ):
                    raise RuntimeError("PEF_V1 candidate artifact identity conflict")

            run = evidence.run
            cur.execute(
                """
                INSERT INTO shadow_experiment_runs (
                    run_id, experiment_id, candidate_id, schema_version,
                    algorithm_version, configuration_digest, authority_state,
                    status, as_of, control_snapshot_id, control_receipt_id,
                    candidate_artifact_id, candidate_output_digest,
                    coverage_state, episode_universe_digest, run_digest,
                    failure_reason, run_class, run_json
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (run_id) DO NOTHING
                RETURNING run_id
                """,
                (
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
                    RUN_CLASS_CONFIRMATORY,
                    Jsonb(run.to_canonical()),
                ),
            )
            if cur.fetchone() is None:
                cur.execute(
                    """
                    SELECT experiment_id, run_digest, status, run_class, run_json
                    FROM shadow_experiment_runs WHERE run_id = %s
                    """,
                    (run.run_id,),
                )
                row = cur.fetchone()
                if row is None or (
                    cast(str, row[0]) != PEF_V1_EXPERIMENT_ID
                    or cast(str, row[1]) != str(run.run_digest)
                    or cast(str, row[2]) != run.status.value
                    or cast(str, row[3]) != RUN_CLASS_CONFIRMATORY
                    or cast(dict[str, object], row[4]) != run.to_canonical()
                ):
                    raise RuntimeError("PEF_V1 shadow run identity conflict")
        return evidence.run.run_id


__all__ = [
    "PostgresPefV1ConfirmatoryPersistence",
    "PostgresPefV1FreezeBindingResolver",
]
