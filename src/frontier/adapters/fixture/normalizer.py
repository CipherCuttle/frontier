from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from frontier.domain.digests import sha256_digest
from frontier.domain.observation import DocumentPayload, ObservationCandidate, ObservationKind


def _dt(text: str | None) -> datetime | None:
    if text is None:
        return None
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def load_fixture_candidate(fixture_dir: Path) -> tuple[ObservationCandidate, datetime]:
    spec = json.loads((fixture_dir / "input.json").read_text(encoding="utf-8"))
    body = (fixture_dir / spec["body_file"]).read_bytes()
    body_text = body.decode("utf-8")
    retrieved_at = _dt(spec["retrieved_at"])
    expected_observed_at = _dt(spec["expected_observed_at"])
    assert retrieved_at is not None and expected_observed_at is not None
    payload = DocumentPayload(
        canonical_url=spec["canonical_url"],
        title=spec["title"],
        excerpt=body_text,
        language=spec.get("language"),
        source_metadata=spec.get("source_metadata", {}),
    )
    candidate = ObservationCandidate(
        source_id=spec["source_id"],
        source_item_key=spec["source_item_key"],
        kind=ObservationKind.DOCUMENT,
        payload=payload,
        retrieved_at=retrieved_at,
        fetch_digest=sha256_digest(body),
        source_published_at=_dt(spec.get("source_published_at")),
        effective_at=_dt(spec.get("effective_at")),
    )
    return candidate, expected_observed_at
