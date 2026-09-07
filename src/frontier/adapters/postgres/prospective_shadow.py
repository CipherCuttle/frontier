from __future__ import annotations

from datetime import datetime
from typing import cast

from frontier.adapters.postgres.advanced_intelligence import PostgresShadowRunRepository


class PostgresProspectiveShadowRunRepository(PostgresShadowRunRepository):
    """Shadow-run persistence with fixed-window receipt-bound boundary queries."""

    def has_bound_run_at(self, *, as_of: datetime, candidate_freeze_receipt_id: str) -> bool:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM shadow_experiment_runs
                WHERE as_of = %s
                  AND run_json ->> 'candidate_freeze_receipt_id' = %s
                LIMIT 1
                """,
                (as_of, candidate_freeze_receipt_id),
            )
            return cur.fetchone() is not None

    def bound_run_boundaries(
        self,
        *,
        candidate_freeze_receipt_id: str,
        start: datetime,
        end: datetime,
    ) -> tuple[datetime, ...]:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT as_of
                FROM shadow_experiment_runs
                WHERE as_of >= %s
                  AND as_of < %s
                  AND run_json ->> 'candidate_freeze_receipt_id' = %s
                ORDER BY as_of, run_id
                """,
                (start, end, candidate_freeze_receipt_id),
            )
            return tuple(cast(datetime, row[0]) for row in cur.fetchall())
