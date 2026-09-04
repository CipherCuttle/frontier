from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FetchOutcome(StrEnum):
    SUCCESS = "SUCCESS"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class FetchRequest:
    request_id: str
    source_id: str
    url: str
    method: str = "GET"
    max_response_bytes: int = 1_000_000
    max_redirects: int = 5


@dataclass(frozen=True, slots=True)
class BoundedFetchResult:
    request_id: str
    outcome: FetchOutcome
    body: bytes
    final_url: str | None = None
    content_type: str | None = None
    failure_code: str | None = None
