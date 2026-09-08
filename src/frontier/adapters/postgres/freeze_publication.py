from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import cast

import psycopg
from psycopg.types.json import Jsonb

from frontier.application.freeze_publication import (
    CandidateFreezePublication,
    derive_github_main_freeze_publication,
)
from frontier.domain.candidate_freeze import CandidateFreezeReceipt
from frontier.domain.digests import Digest


class PostgresCandidateFreezePublicationRepository:
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
            "raw candidate freeze publication persistence is forbidden; "
            "use record_verified_publication"
        )

    def record_verified_publication(
        self,
        receipt: CandidateFreezeReceipt,
        *,
        root: Path,
        receipt_path: Path | None = None,
    ) -> CandidateFreezePublication:
        if not self._persistence_authorized:
            raise PermissionError("candidate freeze publication persistence is not authorized")
        publication = derive_github_main_freeze_publication(
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
                    raise RuntimeError("freeze publication identity conflict")
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
            raise RuntimeError("freeze publication row does not bind its stored digest")
        if publication.to_canonical() != cast(dict[str, object], row[6]):
            raise RuntimeError("freeze publication row does not bind its canonical payload")
        return publication


__all__ = ["PostgresCandidateFreezePublicationRepository"]
