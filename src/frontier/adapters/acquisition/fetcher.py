from __future__ import annotations

import asyncio
import http.client
import ipaddress
import socket
import ssl
import time
import zlib
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Protocol
from urllib.parse import urljoin, urlsplit

from frontier.contracts.fetch import (
    BoundedFetchResult,
    FetchFailure,
    FetchOutcome,
    FetchRequest,
    RedirectHop,
)
from frontier.domain.digests import sha256_digest

from .config import FetchPolicy

_RESPONSE_HEADER_CANONICAL = {
    "cache-control": "Cache-Control",
    "content-encoding": "Content-Encoding",
    "content-length": "Content-Length",
    "content-type": "Content-Type",
    "date": "Date",
    "etag": "ETag",
    "last-modified": "Last-Modified",
    "retry-after": "Retry-After",
    "x-cache": "X-Cache",
    "x-cache-hits": "X-Cache-Hits",
}
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_METADATA_ADDRESSES = frozenset({"169.254.169.254", "fd00:ec2::254"})


@dataclass(frozen=True, slots=True)
class ResolvedTarget:
    url: str
    host: str
    port: int
    address: str
    request_target: str


class WireResponse(Protocol):
    status: int

    def headers(self) -> Sequence[tuple[str, str]]: ...
    def read(self, size: int) -> bytes: ...
    def set_timeout(self, seconds: float) -> None: ...
    def close(self) -> None: ...


class Exchange(Protocol):
    def open(
        self,
        target: ResolvedTarget,
        headers: dict[str, str],
        connect_timeout_seconds: float,
    ) -> WireResponse: ...


Resolver = Callable[[str, int], tuple[str, ...]]


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(
        self,
        host: str,
        port: int,
        address: str,
        *,
        timeout: float,
        context: ssl.SSLContext,
    ) -> None:
        super().__init__(host=host, port=port, timeout=timeout, context=context)
        self._frontier_address = address

    def connect(self) -> None:
        raw = socket.create_connection(
            (self._frontier_address, self.port), self.timeout, self.source_address
        )
        if self._tunnel_host:
            self.sock = raw
            self._tunnel()
            raw = self.sock
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


class _HttpClientWireResponse:
    def __init__(
        self, connection: _PinnedHTTPSConnection, response: http.client.HTTPResponse
    ) -> None:
        self._connection = connection
        self._response = response
        self.status = response.status

    def headers(self) -> Sequence[tuple[str, str]]:
        return tuple((name, value) for name, value in self._response.getheaders())

    def read(self, size: int) -> bytes:
        return self._response.read(size)

    def set_timeout(self, seconds: float) -> None:
        if self._connection.sock is not None:
            self._connection.sock.settimeout(seconds)

    def close(self) -> None:
        self._response.close()
        self._connection.close()


class PinnedHttpsExchange:
    def __init__(self, context: ssl.SSLContext | None = None) -> None:
        self._context = context or ssl.create_default_context()

    def open(
        self,
        target: ResolvedTarget,
        headers: dict[str, str],
        connect_timeout_seconds: float,
    ) -> WireResponse:
        connection = _PinnedHTTPSConnection(
            target.host,
            target.port,
            target.address,
            timeout=connect_timeout_seconds,
            context=self._context,
        )
        connection.request("GET", target.request_target, headers=headers)
        response = connection.getresponse()
        return _HttpClientWireResponse(connection, response)


def _default_resolver(host: str, port: int) -> tuple[str, ...]:
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        addresses = {
            sockaddr[0]
            for family, _socktype, _proto, _canonname, sockaddr in socket.getaddrinfo(
                host,
                port,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
                proto=socket.IPPROTO_TCP,
            )
            if family in (socket.AF_INET, socket.AF_INET6)
        }
        if not addresses:
            raise OSError("DNS returned no usable addresses") from None
        return tuple(sorted(addresses))
    return (str(literal),)


def _blocked_address_class(address: str) -> str | None:
    ip = ipaddress.ip_address(address)
    if str(ip) in _METADATA_ADDRESSES:
        return "CLOUD_METADATA"
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        mapped = ip.ipv4_mapped
        if (
            mapped.is_private
            or mapped.is_loopback
            or mapped.is_link_local
            or mapped.is_multicast
            or mapped.is_unspecified
        ):
            return "IPV4_MAPPED_PRIVATE"
    if ip.is_loopback:
        return "LOOPBACK"
    if ip.is_link_local:
        return "LINK_LOCAL"
    if ip.is_private:
        return "PRIVATE"
    if ip.is_multicast:
        return "MULTICAST"
    if ip.is_unspecified:
        return "UNSPECIFIED"
    if not ip.is_global:
        return "PRIVATE"
    return None


def resolve_target(url: str, resolver: Resolver, blocked_classes: frozenset[str]) -> ResolvedTarget:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("URL must be credential-free HTTPS")
    port = parsed.port or 443
    addresses = resolver(parsed.hostname, port)
    if not addresses:
        raise ValueError("target resolved to no addresses")
    normalized: list[str] = []
    for address in addresses:
        blocked = _blocked_address_class(address)
        if blocked is not None and blocked in blocked_classes:
            raise ValueError(f"target address class forbidden: {blocked}")
        normalized.append(str(ipaddress.ip_address(address)))
    request_target = parsed.path or "/"
    if parsed.query:
        request_target += "?" + parsed.query
    return ResolvedTarget(
        url=url,
        host=parsed.hostname,
        port=port,
        address=sorted(normalized)[0],
        request_target=request_target,
    )


def _sanitize_headers(
    raw_headers: Sequence[tuple[str, str]], max_header_bytes: int
) -> dict[str, str]:
    total = 0
    result: dict[str, str] = {}
    for raw_name, raw_value in raw_headers:
        total += len(raw_name.encode("utf-8")) + len(raw_value.encode("utf-8")) + 4
        if total > max_header_bytes:
            raise ValueError("response headers exceed policy bound")
        canonical = _RESPONSE_HEADER_CANONICAL.get(raw_name.lower())
        if canonical is not None:
            value = raw_value.strip()
            previous = result.get(canonical)
            result[canonical] = value if previous is None else previous + ", " + value
    return result


def _content_type(headers: dict[str, str]) -> str | None:
    value = headers.get("Content-Type")
    if value is None:
        return None
    return value.split(";", 1)[0].strip().lower()


def _retry_after(headers: dict[str, str], maximum: int) -> int | None:
    value = headers.get("Retry-After")
    if value is None:
        return None
    try:
        seconds = int(value)
    except ValueError:
        try:
            when = parsedate_to_datetime(value)
            if when.tzinfo is None:
                when = when.replace(tzinfo=UTC)
            seconds = max(0, int((when - datetime.now(UTC)).total_seconds()))
        except TypeError, ValueError, OverflowError:
            return None
    return min(maximum, max(0, seconds))


def _decoder(content_encoding: str | None) -> zlib.decompressobj | None:
    if content_encoding is None or content_encoding.lower() in ("", "identity"):
        return None
    normalized = content_encoding.lower().strip()
    if normalized == "gzip":
        return zlib.decompressobj(16 + zlib.MAX_WBITS)
    if normalized == "deflate":
        return zlib.decompressobj()
    raise ValueError(f"unsupported content encoding: {normalized}")


class SecureHttpFetcher:
    def __init__(
        self,
        policy: FetchPolicy,
        *,
        resolver: Resolver | None = None,
        exchange: Exchange | None = None,
    ) -> None:
        self._policy = policy
        self._resolver = resolver or _default_resolver
        self._exchange = exchange or PinnedHttpsExchange()
        self._blocked_classes = frozenset(policy.blocked_address_classes)

    async def fetch(self, request: FetchRequest) -> BoundedFetchResult:
        return await asyncio.to_thread(self.fetch_sync, request)

    def fetch_sync(self, request: FetchRequest) -> BoundedFetchResult:
        started = time.monotonic()
        current_url = request.url
        redirects: list[RedirectHop] = []
        while True:
            remaining = request.deadline_ms / 1000 - (time.monotonic() - started)
            if remaining <= 0:
                return self._failure(
                    request,
                    current_url,
                    redirects,
                    FetchOutcome.FAILED,
                    "DEADLINE_EXCEEDED",
                    "fetch deadline exceeded",
                    True,
                )
            try:
                target = resolve_target(current_url, self._resolver, self._blocked_classes)
            except (OSError, ValueError) as exc:
                return self._failure(
                    request,
                    current_url,
                    redirects,
                    FetchOutcome.REJECTED,
                    "TARGET_REJECTED",
                    str(exc),
                    False,
                )
            connect_timeout = min(self._policy.connect_timeout_ms / 1000, remaining)
            try:
                response = self._exchange.open(target, self._wire_headers(request), connect_timeout)
            except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
                return self._failure(
                    request,
                    current_url,
                    redirects,
                    FetchOutcome.FAILED,
                    "CONNECT_FAILED",
                    type(exc).__name__,
                    True,
                )
            try:
                try:
                    headers = _sanitize_headers(response.headers(), self._policy.max_header_bytes)
                except ValueError as exc:
                    return self._failure(
                        request,
                        current_url,
                        redirects,
                        FetchOutcome.REJECTED,
                        "HEADERS_REJECTED",
                        str(exc),
                        False,
                    )
                if response.status in _REDIRECT_STATUSES:
                    location = next(
                        (value for name, value in response.headers() if name.lower() == "location"),
                        None,
                    )
                    if not location:
                        return self._failure(
                            request,
                            current_url,
                            redirects,
                            FetchOutcome.FAILED,
                            "REDIRECT_WITHOUT_LOCATION",
                            "redirect response omitted Location",
                            False,
                        )
                    if len(redirects) >= min(request.max_redirects, self._policy.max_redirects):
                        return self._failure(
                            request,
                            current_url,
                            redirects,
                            FetchOutcome.REJECTED,
                            "REDIRECT_LIMIT",
                            "redirect limit exceeded",
                            False,
                        )
                    next_url = urljoin(current_url, location)
                    redirects.append(RedirectHop(status=response.status, url=next_url))
                    current_url = next_url
                    continue
                retry_after = _retry_after(headers, self._policy.retry.max_retry_after_seconds)
                if response.status == 429 or 500 <= response.status <= 599:
                    return self._failure(
                        request,
                        current_url,
                        redirects,
                        FetchOutcome.FAILED,
                        f"HTTP_{response.status}",
                        "upstream returned retryable HTTP status",
                        True,
                        http_status=response.status,
                        response_headers=headers,
                        retry_after_seconds=retry_after,
                    )
                if response.status not in (200, 304):
                    return self._failure(
                        request,
                        current_url,
                        redirects,
                        FetchOutcome.FAILED,
                        f"HTTP_{response.status}",
                        "upstream returned non-success HTTP status",
                        False,
                        http_status=response.status,
                        response_headers=headers,
                    )
                if response.status == 304:
                    return BoundedFetchResult(
                        request_id=request.request_id,
                        outcome=FetchOutcome.SUCCESS,
                        retrieved_at=datetime.now(UTC),
                        original_url=request.url,
                        final_url=current_url,
                        redirect_chain=tuple(redirects),
                        http_status=304,
                        content_type=_content_type(headers),
                        response_headers=headers,
                        compressed_bytes=0,
                        expanded_bytes=0,
                        body_digest=sha256_digest(b""),
                        body=b"",
                        failure=None,
                    )
                return self._read_success(
                    request, current_url, redirects, response, headers, started
                )
            finally:
                response.close()

    def _wire_headers(self, request: FetchRequest) -> dict[str, str]:
        headers = dict(request.request_headers)
        headers["Accept-Encoding"] = "identity, gzip, deflate"
        return headers

    def _read_success(
        self,
        request: FetchRequest,
        current_url: str,
        redirects: list[RedirectHop],
        response: WireResponse,
        headers: dict[str, str],
        started: float,
    ) -> BoundedFetchResult:
        declared = headers.get("Content-Length")
        if declared is not None:
            try:
                declared_bytes = int(declared)
            except ValueError:
                declared_bytes = -1
            if declared_bytes > request.max_response_bytes:
                return self._failure(
                    request,
                    current_url,
                    redirects,
                    FetchOutcome.REJECTED,
                    "RESPONSE_TOO_LARGE",
                    "declared response size exceeds bound",
                    False,
                    http_status=response.status,
                    response_headers=headers,
                )
        try:
            decoder = _decoder(headers.get("Content-Encoding"))
        except ValueError as exc:
            return self._failure(
                request,
                current_url,
                redirects,
                FetchOutcome.REJECTED,
                "CONTENT_ENCODING_REJECTED",
                str(exc),
                False,
                http_status=response.status,
                response_headers=headers,
            )
        compressed = 0
        expanded = 0
        chunks: list[bytes] = []
        try:
            for chunk in self._iter_body(response, request, started):
                compressed += len(chunk)
                if compressed > request.max_response_bytes:
                    raise ValueError("wire response exceeds max_response_bytes")
                output = decoder.decompress(chunk) if decoder is not None else chunk
                expanded += len(output)
                if expanded > self._policy.max_expanded_bytes:
                    raise ValueError("expanded response exceeds max_expanded_bytes")
                if output:
                    chunks.append(output)
            if decoder is not None:
                tail = decoder.flush()
                expanded += len(tail)
                if expanded > self._policy.max_expanded_bytes:
                    raise ValueError("expanded response exceeds max_expanded_bytes")
                if tail:
                    chunks.append(tail)
        except (OSError, TimeoutError) as exc:
            return self._failure(
                request,
                current_url,
                redirects,
                FetchOutcome.FAILED,
                "BODY_READ_FAILED",
                type(exc).__name__,
                True,
                http_status=response.status,
                response_headers=headers,
            )
        except (ValueError, zlib.error) as exc:
            return self._failure(
                request,
                current_url,
                redirects,
                FetchOutcome.REJECTED,
                "BODY_REJECTED",
                str(exc),
                False,
                http_status=response.status,
                response_headers=headers,
            )
        body = b"".join(chunks)
        return BoundedFetchResult(
            request_id=request.request_id,
            outcome=FetchOutcome.SUCCESS,
            retrieved_at=datetime.now(UTC),
            original_url=request.url,
            final_url=current_url,
            redirect_chain=tuple(redirects),
            http_status=response.status,
            content_type=_content_type(headers),
            response_headers=headers,
            compressed_bytes=compressed,
            expanded_bytes=expanded,
            body_digest=sha256_digest(body),
            body=body,
            failure=None,
        )

    def _iter_body(
        self, response: WireResponse, request: FetchRequest, started: float
    ) -> Iterator[bytes]:
        while True:
            remaining = request.deadline_ms / 1000 - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError("fetch deadline exceeded during body read")
            response.set_timeout(min(self._policy.read_idle_timeout_ms / 1000, remaining))
            chunk = response.read(65536)
            if not chunk:
                return
            yield chunk

    def _failure(
        self,
        request: FetchRequest,
        current_url: str,
        redirects: list[RedirectHop],
        outcome: FetchOutcome,
        code: str,
        message: str,
        retryable: bool,
        *,
        http_status: int | None = None,
        response_headers: dict[str, str] | None = None,
        retry_after_seconds: int | None = None,
    ) -> BoundedFetchResult:
        return BoundedFetchResult(
            request_id=request.request_id,
            outcome=outcome,
            retrieved_at=datetime.now(UTC),
            original_url=request.url,
            final_url=current_url,
            redirect_chain=tuple(redirects),
            http_status=http_status,
            content_type=_content_type(response_headers or {}),
            response_headers=response_headers or {},
            compressed_bytes=None,
            expanded_bytes=None,
            body_digest=None,
            body=None,
            failure=FetchFailure(
                code=code,
                safe_message=message[:512],
                retryable=retryable,
                retry_after_seconds=retry_after_seconds,
            ),
        )
