from __future__ import annotations

import gzip
from collections.abc import Sequence

import pytest

from frontier.adapters.acquisition.config import FetchPolicy, RetryPolicy
from frontier.adapters.acquisition.fetcher import ResolvedTarget, SecureHttpFetcher, resolve_target
from frontier.contracts.fetch import FetchOutcome, FetchRequest


class FakeResponse:
    def __init__(
        self,
        status: int,
        headers: Sequence[tuple[str, str]],
        body: bytes = b"",
    ) -> None:
        self.status = status
        self._headers = tuple(headers)
        self._body = body
        self._offset = 0
        self.read_calls = 0
        self.closed = False

    def headers(self) -> Sequence[tuple[str, str]]:
        return self._headers

    def read(self, size: int) -> bytes:
        self.read_calls += 1
        chunk = self._body[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk

    def set_timeout(self, seconds: float) -> None:
        assert seconds > 0

    def close(self) -> None:
        self.closed = True


class ScriptedExchange:
    def __init__(self, *responses: FakeResponse) -> None:
        self._responses = list(responses)
        self.opened: list[ResolvedTarget] = []

    def open(
        self,
        target: ResolvedTarget,
        headers: dict[str, str],
        connect_timeout_seconds: float,
    ) -> FakeResponse:
        assert headers["Accept-Encoding"] == "identity, gzip, deflate"
        assert connect_timeout_seconds > 0
        self.opened.append(target)
        if not self._responses:
            raise AssertionError("unexpected network exchange")
        return self._responses.pop(0)


def policy(*, max_expanded_bytes: int = 4096) -> FetchPolicy:
    return FetchPolicy(
        policy_profile="structured-public-v0",
        allowed_schemes=("https",),
        max_redirects=3,
        deadline_ms=15000,
        connect_timeout_ms=5000,
        read_idle_timeout_ms=5000,
        max_response_bytes=1024,
        max_expanded_bytes=max_expanded_bytes,
        max_header_bytes=65536,
        blocked_address_classes=(
            "CLOUD_METADATA",
            "IPV4_MAPPED_PRIVATE",
            "LINK_LOCAL",
            "LOOPBACK",
            "MULTICAST",
            "PRIVATE",
            "UNSPECIFIED",
        ),
        forward_authorization_cross_origin=False,
        retry=RetryPolicy(
            max_attempts=3,
            base_delay_ms=1000,
            max_delay_ms=30000,
            max_retry_after_seconds=3600,
            jitter=True,
        ),
    )


def request(url: str = "https://public.example/feed") -> FetchRequest:
    return FetchRequest(
        request_id="run:1",
        source_id="fixture.http",
        url=url,
        policy_profile="structured-public-v0",
        credential_ref=None,
        accepted_content_types=("application/json",),
        deadline_ms=15000,
        max_response_bytes=1024,
        max_redirects=3,
        request_headers={"Accept": "application/json", "User-Agent": "FRONTIER/test"},
    )


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "::1",
        "::ffff:10.0.0.1",
    ],
)
def test_resolver_rejects_forbidden_address_classes_before_connect(address: str) -> None:
    with pytest.raises(ValueError, match="forbidden"):
        resolve_target(
            "https://blocked.example/path",
            lambda _host, _port: (address,),
            frozenset(policy().blocked_address_classes),
        )


def test_redirect_target_is_revalidated_before_second_connection() -> None:
    redirect = FakeResponse(302, (("Location", "https://private.example/secret"),))
    exchange = ScriptedExchange(redirect)

    def resolver(host: str, _port: int) -> tuple[str, ...]:
        return ("8.8.8.8",) if host == "public.example" else ("10.0.0.5",)

    result = SecureHttpFetcher(policy(), resolver=resolver, exchange=exchange).fetch_sync(request())

    assert result.outcome is FetchOutcome.REJECTED
    assert result.failure is not None
    assert result.failure.code == "TARGET_REJECTED"
    assert [target.host for target in exchange.opened] == ["public.example"]


def test_stream_limit_does_not_trust_content_length_header() -> None:
    response = FakeResponse(
        200,
        (("Content-Type", "application/json"), ("Content-Length", "1")),
        b"x" * 1500,
    )
    exchange = ScriptedExchange(response)
    fetcher = SecureHttpFetcher(
        policy(), resolver=lambda _host, _port: ("8.8.8.8",), exchange=exchange
    )

    result = fetcher.fetch_sync(request())

    assert result.outcome is FetchOutcome.REJECTED
    assert result.failure is not None
    assert result.failure.code == "BODY_REJECTED"
    assert response.read_calls >= 1


def test_short_body_rejects_declared_content_length_mismatch() -> None:
    body = b'{"ok":true}'
    response = FakeResponse(
        200,
        (("Content-Type", "application/json"), ("Content-Length", str(len(body) + 1))),
        body,
    )
    fetcher = SecureHttpFetcher(
        policy(),
        resolver=lambda _host, _port: ("8.8.8.8",),
        exchange=ScriptedExchange(response),
    )

    result = fetcher.fetch_sync(request())

    assert result.outcome is FetchOutcome.REJECTED
    assert result.failure is not None
    assert result.failure.code == "BODY_REJECTED"


def test_expanded_body_limit_rejects_compression_bomb() -> None:
    compressed = gzip.compress(b"z" * 4096)
    response = FakeResponse(
        200,
        (("Content-Type", "application/json"), ("Content-Encoding", "gzip")),
        compressed,
    )
    fetcher = SecureHttpFetcher(
        policy(max_expanded_bytes=256),
        resolver=lambda _host, _port: ("8.8.8.8",),
        exchange=ScriptedExchange(response),
    )

    result = fetcher.fetch_sync(request())

    assert result.outcome is FetchOutcome.REJECTED
    assert result.failure is not None
    assert result.failure.code == "BODY_REJECTED"


def test_truncated_gzip_rejected_even_when_payload_fully_decompresses() -> None:
    compressed = gzip.compress(b'{"vulnerabilities":[]}')
    truncated = compressed[:-8]
    response = FakeResponse(
        200,
        (("Content-Type", "application/json"), ("Content-Encoding", "gzip")),
        truncated,
    )
    fetcher = SecureHttpFetcher(
        policy(),
        resolver=lambda _host, _port: ("8.8.8.8",),
        exchange=ScriptedExchange(response),
    )

    result = fetcher.fetch_sync(request())

    assert result.outcome is FetchOutcome.REJECTED
    assert result.failure is not None
    assert result.failure.code == "BODY_REJECTED"


def test_retry_after_is_capped_by_frozen_policy() -> None:
    response = FakeResponse(429, (("Retry-After", "99999"),))
    fetcher = SecureHttpFetcher(
        policy(),
        resolver=lambda _host, _port: ("8.8.8.8",),
        exchange=ScriptedExchange(response),
    )

    result = fetcher.fetch_sync(request())

    assert result.outcome is FetchOutcome.FAILED
    assert result.failure is not None
    assert result.failure.retryable
    assert result.failure.retry_after_seconds == 3600


def test_explicit_403_retry_after_is_rate_limited_not_permission_retry() -> None:
    response = FakeResponse(403, (("Retry-After", "120"),))
    fetcher = SecureHttpFetcher(
        policy(),
        resolver=lambda _host, _port: ("8.8.8.8",),
        exchange=ScriptedExchange(response),
    )

    result = fetcher.fetch_sync(request())

    assert result.outcome is FetchOutcome.FAILED
    assert result.failure is not None
    assert result.failure.code == "HTTP_403_RATE_LIMITED"
    assert result.failure.retryable
    assert result.failure.retry_after_seconds == 120


def test_explicit_403_reset_epoch_is_capped_without_crossing_fetch_header_contract() -> None:
    response = FakeResponse(
        403,
        (
            ("X-RateLimit-Remaining", "0"),
            ("X-RateLimit-Reset", "4102444800"),
        ),
    )
    fetcher = SecureHttpFetcher(
        policy(),
        resolver=lambda _host, _port: ("8.8.8.8",),
        exchange=ScriptedExchange(response),
    )

    result = fetcher.fetch_sync(request())

    assert result.outcome is FetchOutcome.FAILED
    assert result.failure is not None
    assert result.failure.code == "HTTP_403_RATE_LIMITED"
    assert result.failure.retryable
    assert result.failure.retry_after_seconds == 3600
    assert "X-RateLimit-Remaining" not in result.response_headers
    assert "X-RateLimit-Reset" not in result.response_headers


def test_403_without_explicit_rate_limit_evidence_remains_nonretryable() -> None:
    response = FakeResponse(403, ())
    fetcher = SecureHttpFetcher(
        policy(),
        resolver=lambda _host, _port: ("8.8.8.8",),
        exchange=ScriptedExchange(response),
    )

    result = fetcher.fetch_sync(request())

    assert result.outcome is FetchOutcome.FAILED
    assert result.failure is not None
    assert result.failure.code == "HTTP_403"
    assert not result.failure.retryable
    assert result.failure.retry_after_seconds is None


def test_304_crosses_fetch_seam_as_empty_success_for_trusted_cache_decision() -> None:
    response = FakeResponse(304, (("ETag", '"same"'),))
    fetcher = SecureHttpFetcher(
        policy(),
        resolver=lambda _host, _port: ("8.8.8.8",),
        exchange=ScriptedExchange(response),
    )

    result = fetcher.fetch_sync(request())

    assert result.outcome is FetchOutcome.SUCCESS
    assert result.http_status == 304
    assert result.body == b""
