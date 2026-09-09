from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import cast

import psycopg
from psycopg.types.json import Jsonb

from frontier.application.freeze_publication import CandidateFreezePublication
from frontier.application.freeze_publication_v1 import derive_github_main_freeze_publication_v1
from frontier.domain.candidate_freeze import FREEZE_SCHEMA_VERSION, FreezeStatus
from frontier.domain.candidate_freeze_v1 import (
    FREEZE_V1_PREREGISTRATION_PATH,
    CandidateFreezeReceiptV1,
)
from frontier.domain.canonical_json import canonical_json_bytes
from frontier.domain.digests import Digest, sha256_digest
from frontier.domain.pef_v1 import (
    PEF_V1_CANDIDATE_ID,
    PEF_V1_CONFIGURATION_DIGEST,
    PEF_V1_EXPERIMENT_ID,
)
from frontier.domain.advanced_intelligence import PEF_ALGORITHM_VERSION


class PostgresCandidateFreezeV1Repository:
    """Append-only persistence for PEF_V1 candidate freeze receipts."""

    def __init__(
        self,
        connection: psycopg.Connection[tuple[object, ...]],
        *,
        persistence_authorized: bool = False,
    ) -> None:
        self._connection = connection
        self._persistence_authorized = persistence_authorized

    def record_receipt(self, receipt: CandidateFreezeReceiptV1) -> None:
        if not self._persistence_authorized:
            raise PermissionError("PEF_V1 candidate freeze persistence is not authorized")
        if receipt.candidate_id != PEF_V1_CANDIDATE_ID:
            raise ValueError("PEF_V1 candidate freeze candidate id mismatch")
        if receipt.experiment_id != PEF_V1_EXPERIMENT_ID:
            raise ValueError("PEF_V1 candidate freeze experiment id mismatch")
        if receipt.algorithm_version != PEF_ALGORITHM_VERSION:
            raise ValueError("PEF_V1 candidate freeze algorithm version mismatch")
        if receipt.configuration_digest != PEF_V1_CONFIGURATION_DIGEST:
            raise ValueError("PEF_V1 candidate freeze configuration digest mismatch")
        if receipt.preregistration_path != FREEZE_V1_PREREGISTRATION_PATH:
            raise ValueError("PEF_V1 candidate freeze preregistration path mismatch")
        if receipt.schema_version != FREEZE_SCHEMA_VERSION:
            raise ValueError("PEF_V1 candidate freeze schema version mismatch")
        if receipt.status is FreezeStatus.DRIFTED and not receipt.drift_reasons:
            raise ValueError("DRIFTED PEF_V1 freeze receipt requires explicit drift reasons")
        if receipt.status is FreezeStatus.FROZEN and receipt.drift_reasons:
            raise ValueError("FROZEN PEF_V1 freeze receipt cannot carry drift reasons")
        if receipt.receipt_digest != sha256_digest(canonical_json_bytes(receipt.to_canonical())):
            raise ValueError("PEF_V1 freeze receipt digest does not bind its canonical payload")

        entry_values: list[dict[str, str]] | None = None
        if receipt.registry_entry_digests is not None:
            entry_values = [
                {"digest": str(entry.digest), "path": entry.path}
                for entry in receipt.registry_entry_digests
            ]
        with self._connection.transaction(), self._connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO candidate_freeze_receipts (
                    receipt_id, schema_version, candidate_id, experiment_id,
                    algorithm_version, configuration_digest, status,
                    preregistration_path, preregistration_digest,
                    preregistration_config_digest, implementation_commit,
                    implementation_tree_digest, dependency_lock_digest,
                    source_registry_digest, registry_entry_digests,
                    drift_reasons, receipt_digest, frozen_at, verified_at,
                    original_receipt_digest, receipt_json
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (receipt_id) DO NOTHING
                RETURNING receipt_id
                """,
                (
                    receipt.receipt_id,
                    receipt.schema_version,
                    receipt.candidate_id,
                    receipt.experiment_id,
                    receipt.algorithm_version,
                    str(receipt.configuration_digest),
                    receipt.status.value,
                    receipt.preregistration_path,
                    str(receipt.preregistration_digest),
                    (
                        None
                        if receipt.preregistration_config_digest is None
                        else str(receipt.preregistration_config_digest)
                    ),
                    receipt.implementation_commit,
                    receipt.implementation_tree_digest,
                    (
                        None
                        if receipt.dependency_lock_digest is None
                        else str(receipt.dependency_lock_digest)
                    ),
                    (
                        None
                        if receipt.source_registry_digest is None
                        else str(receipt.source_registry_digest)
                    ),
                    None if entry_values is None else Jsonb(entry_values),
                    Jsonb(list(receipt.drift_reasons)),
                    str(receipt.receipt_digest),
                    receipt.frozen_at,
                    receipt.verified_at,
                    (
                        None
                        if receipt.original_receipt_digest is None
                        else str(receipt.original_receipt_digest)
                    ),
                    Jsonb(receipt.to_canonical()),
                ),
            )
            inserted = cur.fetchone()
            if inserted is None:
                cur.execute(
                    "SELECT receipt_digest, status FROM candidate_freeze_receipts "
                    "WHERE receipt_id = %s",
                    (receipt.receipt_id,),
                )
                existing = cur.fetchone()
                if existing is None:
                    raise RuntimeError("PEF_V1 freeze receipt conflict without existing row")
                if (
                    cast(str, existing[0]) != str(receipt.receipt_digest)
                    or cast(str, existing[1]) != receipt.status.value
                ):
                    raise RuntimeError("PEF_V1 freeze receipt identity conflict")

    def get_receipt_json(self, receipt_id: str) -> dict[str, object] | None:
        with self._connection.cursor() as cur:
            cur.execute(
                "SELECT receipt_json FROM candidate_freeze_receipts WHERE receipt_id = %s",
                (receipt_id,),
            )
            row = cur.fetchone()
        return None if row is None else cast(dict[str, object], row[0])

    def get_durable_freeze_at(self, receipt_id: str) -> datetime | None:
        with self._connection.cursor() as cur:
            cur.execute(
                "SELECT durable_freeze_at FROM candidate_freeze_receipts WHERE receipt_id = %s",
                (receipt_id,),
            )
            row = cur.fetchone()
        return None if row is None else cast(datetime | None, row[0])


class PostgresCandidateFreezePublicationV1Repository:
    """Persist only GitHub-main-verified PEF_V1 freeze publication evidence."""

    def __init__(
        self,
        connection: psycopg.Connection[tuple[object, ...]],
        *,
        persistence_authorized: bool = False,
    ) -> None:
        self._connection = connection
        self._persistence_authorized = persistence_authorized

    def record_publication(self, publication: CandidateFreezePublication) -> None:
        del publication
        raise PermissionError(
            "raw PEF_V1 candidate freeze publication persistence is forbidden; "
            "use record_verified_publication"
        )

    def record_verified_publication(
        self,
        receipt: CandidateFreezeReceiptV1,
        *,
        root: Path,
        receipt_path: Path | None = None,
    ) -> CandidateFreezePublication:
        if not self._persistence_authorized:
            raise PermissionError("PEF_V1 candidate freeze publication persistence is not authorized")
        publication = derive_github_main_freeze_publication_v1(
            root, receipt, receipt_path=receipt_path
        )
        with self._connection.transaction(), self._connection.cursor() as cur:
            cur.execute(
                """INSERT INTO candidate_freeze_publications (
                    receipt_id, schema_version, freeze_receipt_digest, implementation_commit,
                    implementation_tree_digest, publication_commit, publication_committer_at,
                    publication_digest, publication_json
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (receipt_id) DO NOTHING RETURNING receipt_id""",
                (
                    publication.freeze_receipt_id,
                    publication.schema_version,
                    str(publication.freeze_receipt_digest),
                    publication.implementation_commit,
                    publication.implementation_tree_digest,
                    publication.publication_commit,
                    publication.publication_committer_at,
                    str(publication.publication_digest),
                    Jsonb(publication.to_canonical()),
                ),
            )
            inserted = cur.fetchone()
            if inserted is None:
                cur.execute(
                    "SELECT publication_digest FROM candidate_freeze_publications "
                    "WHERE receipt_id=%s",
                    (publication.freeze_receipt_id,),
                )
                row = cur.fetchone()
                if row is None or cast(str, row[0]) != str(publication.publication_digest):
                    raise RuntimeError("PEF_V1 freeze publication identity conflict")
        return publication

    def get_publication(self, receipt_id: str) -> CandidateFreezePublication | None:
        with self._connection.cursor() as cur:
            cur.execute(
                """SELECT freeze_receipt_digest, implementation_commit, implementation_tree_digest,
                       publication_commit, publication_committer_at, publication_digest,
                       publication_json
                       FROM candidate_freeze_publications WHERE receipt_id=%s""",
                (receipt_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        publication = CandidateFreezePublication(
            freeze_receipt_id=receipt_id,
            freeze_receipt_digest=Digest(cast(str, row[0])),
            implementation_commit=cast(str, row[1]),
            implementation_tree_digest=cast(str, row[2]),
            publication_commit=cast(str, row[3]),
            publication_committer_at=cast(datetime, row[4]),
        )
        if str(publication.publication_digest) != cast(str, row[5]):
            raise RuntimeError("PEF_V1 freeze publication row does not bind its stored digest")
        if publication.to_canonical() != cast(dict[str, object], row[6]):
            raise RuntimeError("PEF_V1 freeze publication row does not bind its canonical payload")
        return publication


__all__ = [
    "PostgresCandidateFreezePublicationV1Repository",
    "PostgresCandidateFreezeV1Repository",
]
