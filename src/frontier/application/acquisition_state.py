from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from frontier.domain.digests import Digest


@dataclass(frozen=True, slots=True)
class SourceFetchState:
    source_id: str
    etag: str | None
    last_modified: str | None
    last_body_digest: Digest | None
    last_success_at: datetime | None
    consecutive_failures: int
    next_retry_at: datetime | None
