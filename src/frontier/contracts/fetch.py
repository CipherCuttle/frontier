from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from urllib.parse import urlsplit

from frontier.domain.digests import Digest

FETCH_REQUEST_SCHEMA_VERSION = "fetch-request-v0"
FETCH_RESULT_SCHEMA_VERSION = "bounded-fetch-result-v0"
_SOURCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
_FAILURE_CODE_RE = re.compile(r"^[A-Z0-9_]{1,64}$")
_ALLOWED_REQUEST_HEADERS = frozenset({"Accept", "If-Modified-Since", "If-None-Match", "User-Agent"})
_ALLOWED_RESPONSE_HEADERS = frozenset(
    {
        "Cache-Control",
        "Content-Encoding",
        "Content-Length",
        "Content-Type",
        "Date",
        "ETag",
        "Last-Modified",
        "Retry-After",
        "X-Cache",
        "X-Cache-Hits",
    }
)


class FetchOutcome(StrEnum):
    SUCCESS = "SUCCESS"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class RedirectHop:
    status: int
    url: str

    def __post_init__(self) -> None:
        if not 300 <= self.status <= 399:
            raise ValueError("redirect status must be 3xx")
        if len(self.url) > 2048:
            raise ValueError("redirect URL exceeds 2048 characters")


@dataclass(frozen=True, slots=True)
class FetchFailure:
    code: str
    safe_message: str
    retryable: bool
    retry_after_seconds: int | None = None

    def __post_init__(self) -> None:
        if not _FAILURE_CODE_RE.fullmatch(self.code):
            raise ValueError("invalid fetch failure code")
        if len(self.safe_message) > 512:
            raise ValueError("safe_message exceeds 512 characters")
        if self.retry_after_seconds is not None and not 0 <= self.retry_after_seconds <= 3600:
            raise ValueError("retry_after_seconds must be 0..3600")


@dataclass(frozen=True, slots=True)
class FetchRequest:
    request_id: str
    source_id: str
    url: str
    policy_profile: str
    credential_ref: str | None
    accepted_content_types: tuple[str, ...]
    deadline_ms: int
    max_response_bytes: int
    max_redirects: int
    request_headers: dict[str, str] = field(default_factory=dict)
    method: str = "GET"
    schema_version: str = FETCH_REQUEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != FETCH_REQUEST_SCHEMA_VERSION:
            raise ValueError("unsupported FetchRequest schema_version")
        if not self.request_id or len(self.request_id) > 128:
            raise ValueError("request_id must be 1..128 characters")
        if not _SOURCE_ID_RE.fullmatch(self.source_id):
            raise ValueError("invalid source_id")
        parsed = urlsplit(self.url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("FetchRequest URL must be credential-free HTTPS")
        if len(self.url) > 2048:
            raise ValueError("FetchRequest URL exceeds 2048 characters")
        if self.method != "GET":
            raise ValueError("FetchRequest V0 only permits GET")
        if not self.policy_profile or len(self.policy_profile) > 64:
            raise ValueError("invalid policy_profile")
        if self.credential_ref is not None and len(self.credential_ref) > 256:
            raise ValueError("credential_ref exceeds 256 characters")
        accepted = tuple(dict.fromkeys(self.accepted_content_types))
        if not 1 <= len(accepted) <= 16:
            raise ValueError("accepted_content_types must contain 1..16 unique values")
        if any(not value or len(value) > 128 for value in accepted):
            raise ValueError("invalid accepted content type")
        object.__setattr__(self, "accepted_content_types", accepted)
        if not 1000 <= self.deadline_ms <= 60000:
            raise ValueError("deadline_ms must be 1000..60000")
        if not 1024 <= self.max_response_bytes <= 16 * 1024 * 1024:
            raise ValueError("max_response_bytes outside V0 bounds")
        if not 0 <= self.max_redirects <= 5:
            raise ValueError("max_redirects must be 0..5")
        headers = dict(self.request_headers)
        if len(headers) > 16 or not set(headers) <= _ALLOWED_REQUEST_HEADERS:
            raise ValueError("request header outside V0 allowlist")
        if any(len(value) > 2048 for value in headers.values()):
            raise ValueError("request header value exceeds 2048 characters")
        object.__setattr__(self, "request_headers", headers)


@dataclass(frozen=True, slots=True)
class BoundedFetchResult:
    request_id: str
    outcome: FetchOutcome
    retrieved_at: datetime
    original_url: str
    final_url: str | None
    redirect_chain: tuple[RedirectHop, ...]
    http_status: int | None
    content_type: str | None
    response_headers: dict[str, str]
    compressed_bytes: int | None
    expanded_bytes: int | None
    body_digest: Digest | None
    body: bytes | None
    failure: FetchFailure | None
    schema_version: str = FETCH_RESULT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != FETCH_RESULT_SCHEMA_VERSION:
            raise ValueError("unsupported BoundedFetchResult schema_version")
        if not self.request_id or len(self.request_id) > 128:
            raise ValueError("request_id must be 1..128 characters")
        if self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() is None:
            raise ValueError("fetcher retrieved_at must be timezone-aware")
        if len(self.original_url) > 2048:
            raise ValueError("original_url exceeds 2048 characters")
        if self.final_url is not None and len(self.final_url) > 2048:
            raise ValueError("final_url exceeds 2048 characters")
        if len(self.redirect_chain) > 5:
            raise ValueError("redirect chain exceeds V0 bound")
        if self.http_status is not None and not 100 <= self.http_status <= 599:
            raise ValueError("http_status outside HTTP range")
        if self.content_type is not None and len(self.content_type) > 256:
            raise ValueError("content_type exceeds 256 characters")
        headers = dict(self.response_headers)
        if len(headers) > 32 or not set(headers) <= _ALLOWED_RESPONSE_HEADERS:
            raise ValueError("response header outside V0 allowlist")
        if any(len(value) > 4096 for value in headers.values()):
            raise ValueError("response header value exceeds 4096 characters")
        object.__setattr__(self, "response_headers", headers)
        for value in (self.compressed_bytes, self.expanded_bytes):
            if value is not None and not 0 <= value <= 16 * 1024 * 1024:
                raise ValueError("fetch byte telemetry outside V0 bounds")
        if self.outcome is FetchOutcome.SUCCESS:
            if self.body is None or self.failure is not None:
                raise ValueError("SUCCESS requires body bytes and no failure")
        elif self.failure is None:
            raise ValueError("REJECTED/FAILED result requires failure")
