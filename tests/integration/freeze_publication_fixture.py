"""Test-only synthetic freeze-publication persistence helper.

This module is outside ``src/frontier`` and is not packaged with the product.
Production publication persistence must pass GitHub-main verification.
"""

from __future__ import annotations

from typing import cast

from psycopg import Connection
from psycopg.types.json import Jsonb

from frontier.application.freeze_publication import CandidateFreezePublication


def record_fixture_publication(
    connection: Connection[tuple[object, ...]], publication: CandidateFreezePublication
) -> None:
    with connection.transaction(), connection.cursor() as cur:
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
                "SELECT publication_digest FROM candidate_freeze_publications WHERE receipt_id=%s",
                (publication.freeze_receipt_id,),
            )
            row = cur.fetchone()
            if row is None or cast(str, row[0]) != str(publication.publication_digest):
                raise RuntimeError("fixture freeze publication identity conflict")
