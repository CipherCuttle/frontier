from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from frontier.domain.canonical_json import CanonicalValue, canonical_json_bytes
from frontier.domain.digests import Digest, sha256_digest
from frontier.domain.source import AcquisitionClass, SignalRole, SourceContract, SourceTransport


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int
    base_delay_ms: int
    max_delay_ms: int
    max_retry_after_seconds: int
    jitter: bool


@dataclass(frozen=True, slots=True)
class FetchPolicy:
    policy_profile: str
    allowed_schemes: tuple[str, ...]
    max_redirects: int
    deadline_ms: int
    connect_timeout_ms: int
    read_idle_timeout_ms: int
    max_response_bytes: int
    max_expanded_bytes: int
    max_header_bytes: int
    blocked_address_classes: tuple[str, ...]
    forward_authorization_cross_origin: bool
    retry: RetryPolicy


@dataclass(frozen=True, slots=True)
class RegisteredSource:
    contract: SourceContract
    endpoint_url: str
    fallback_urls: tuple[str, ...]
    fallback_semantics: str | None
    accepted_content_types: tuple[str, ...]
    policy_profile: str
    authentication: str
    credential_ref: str | None
    poll_interval_seconds: int
    finite_window: bool
    etag_support: str
    last_modified_support: str
    raw_contract: dict[str, CanonicalValue]


@dataclass(frozen=True, slots=True)
class SourceRegistry:
    sources: dict[str, RegisteredSource]
    source_registry_version: Digest

    def require(self, source_id: str) -> RegisteredSource:
        try:
            return self.sources[source_id]
        except KeyError as exc:
            raise ValueError(f"source {source_id!r} is not authorized by registry") from exc


def _load_json(path: Path) -> dict[str, CanonicalValue]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected JSON object")
    return raw


def _expect_mapping(value: CanonicalValue | None, *, name: str) -> dict[str, CanonicalValue]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _expect_list(value: CanonicalValue | None, *, name: str) -> list[CanonicalValue]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return value


def _expect_str(value: CanonicalValue | None, *, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _expect_int(value: CanonicalValue | None, *, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    return value


def _str_tuple(value: CanonicalValue | None, *, name: str) -> tuple[str, ...]:
    items = _expect_list(value, name=name)
    if not all(isinstance(item, str) and item for item in items):
        raise ValueError(f"{name} must contain only non-empty strings")
    return tuple(item for item in items if isinstance(item, str))


def load_fetch_policy(root: Path) -> FetchPolicy:
    raw = _load_json(root / "policies/fetch/structured_public_v0.json")
    if raw.get("schema_version") != "fetch-policy-v0":
        raise ValueError("unsupported fetch policy schema")
    retry_raw = _expect_mapping(raw.get("retry"), name="retry")
    policy = FetchPolicy(
        policy_profile=_expect_str(raw.get("policy_profile"), name="policy_profile"),
        allowed_schemes=_str_tuple(raw.get("allowed_schemes"), name="allowed_schemes"),
        max_redirects=_expect_int(raw.get("max_redirects"), name="max_redirects"),
        deadline_ms=_expect_int(raw.get("deadline_ms"), name="deadline_ms"),
        connect_timeout_ms=_expect_int(raw.get("connect_timeout_ms"), name="connect_timeout_ms"),
        read_idle_timeout_ms=_expect_int(
            raw.get("read_idle_timeout_ms"), name="read_idle_timeout_ms"
        ),
        max_response_bytes=_expect_int(raw.get("max_response_bytes"), name="max_response_bytes"),
        max_expanded_bytes=_expect_int(raw.get("max_expanded_bytes"), name="max_expanded_bytes"),
        max_header_bytes=_expect_int(raw.get("max_header_bytes"), name="max_header_bytes"),
        blocked_address_classes=_str_tuple(
            raw.get("blocked_address_classes"), name="blocked_address_classes"
        ),
        forward_authorization_cross_origin=raw.get("forward_authorization_cross_origin") is True,
        retry=RetryPolicy(
            max_attempts=_expect_int(retry_raw.get("max_attempts"), name="retry.max_attempts"),
            base_delay_ms=_expect_int(retry_raw.get("base_delay_ms"), name="retry.base_delay_ms"),
            max_delay_ms=_expect_int(retry_raw.get("max_delay_ms"), name="retry.max_delay_ms"),
            max_retry_after_seconds=_expect_int(
                retry_raw.get("max_retry_after_seconds"), name="retry.max_retry_after_seconds"
            ),
            jitter=retry_raw.get("jitter") is True,
        ),
    )
    if policy.allowed_schemes != ("https",):
        raise ValueError("structured-public-v0 must remain HTTPS-only")
    if policy.forward_authorization_cross_origin:
        raise ValueError("cross-origin authorization forwarding is forbidden")
    return policy


def _registered_source(raw: dict[str, CanonicalValue]) -> RegisteredSource:
    source_id = _expect_str(raw.get("source_id"), name="source_id")
    if raw.get("schema_version") != "source-contract-v0":
        raise ValueError(f"{source_id}: unsupported source contract schema")
    if raw.get("enabled") is not True:
        raise ValueError(f"{source_id}: disabled source cannot be acquired")
    endpoint = _expect_mapping(raw.get("endpoint"), name=f"{source_id}.endpoint")
    policy = _expect_mapping(raw.get("policy"), name=f"{source_id}.policy")
    capability = _expect_mapping(raw.get("capability"), name=f"{source_id}.capability")
    cadence = _expect_mapping(raw.get("expected_cadence"), name=f"{source_id}.expected_cadence")
    roles = tuple(
        SignalRole(value)
        for value in _str_tuple(raw.get("signal_roles"), name=f"{source_id}.signal_roles")
    )
    contract = SourceContract(
        source_id=source_id,
        display_name=_expect_str(raw.get("display_name"), name=f"{source_id}.display_name"),
        acquisition_class=AcquisitionClass(
            _expect_str(raw.get("acquisition_class"), name=f"{source_id}.acquisition_class")
        ),
        signal_roles=roles,
        transport=SourceTransport(_expect_str(raw.get("transport"), name=f"{source_id}.transport")),
        enabled=True,
    )
    if endpoint.get("method") != "GET" or endpoint.get("authentication") != "NONE":
        raise ValueError(f"{source_id}: V0 only authorizes unauthenticated GET")
    if endpoint.get("credential_ref") is not None:
        raise ValueError(f"{source_id}: credential_ref must be null for authentication=NONE")
    if policy.get("access_state") != "ALLOWED" or policy.get("browser_authorized") is not False:
        raise ValueError(f"{source_id}: source policy does not authorize structured acquisition")
    if policy.get("raw_artifact_retention") != "NONE":
        raise ValueError(f"{source_id}: raw response retention is not authorized")
    fallback_urls = endpoint.get("fallback_urls")
    if fallback_urls is None:
        fallbacks: tuple[str, ...] = ()
    else:
        fallbacks = _str_tuple(fallback_urls, name=f"{source_id}.endpoint.fallback_urls")
    fallback_semantics = endpoint.get("fallback_semantics")
    if fallback_semantics is not None and not isinstance(fallback_semantics, str):
        raise ValueError(f"{source_id}: fallback_semantics must be string/null")
    return RegisteredSource(
        contract=contract,
        endpoint_url=_expect_str(endpoint.get("url"), name=f"{source_id}.endpoint.url"),
        fallback_urls=fallbacks,
        fallback_semantics=fallback_semantics,
        accepted_content_types=_str_tuple(
            endpoint.get("accepted_content_types"), name=f"{source_id}.accepted_content_types"
        ),
        policy_profile=_expect_str(
            endpoint.get("policy_profile"), name=f"{source_id}.policy_profile"
        ),
        authentication="NONE",
        credential_ref=None,
        poll_interval_seconds=_expect_int(
            cadence.get("poll_interval_seconds"), name=f"{source_id}.poll_interval_seconds"
        ),
        finite_window=capability.get("finite_window") is True,
        etag_support=str(capability.get("etag_support", "UNKNOWN")),
        last_modified_support=str(capability.get("last_modified_support", "UNKNOWN")),
        raw_contract=raw,
    )


def load_source_registry(root: Path) -> SourceRegistry:
    registry_raw = _load_json(root / "sources/registry/registry_v0.json")
    if registry_raw.get("schema_version") != "source-registry-v0":
        raise ValueError("unsupported source registry schema")
    paths = _str_tuple(registry_raw.get("source_contract_paths"), name="source_contract_paths")
    expected_ids = _str_tuple(registry_raw.get("required_source_ids"), name="required_source_ids")
    raw_sources = [_load_json(root / path) for path in paths]
    sources = [_registered_source(raw) for raw in raw_sources]
    source_ids = tuple(sorted(source.contract.source_id for source in sources))
    if source_ids != tuple(sorted(expected_ids)) or len(source_ids) != len(expected_ids):
        raise ValueError("source registry required_source_ids drifted from source contracts")
    digest = sha256_digest(
        canonical_json_bytes(sorted(raw_sources, key=lambda item: str(item["source_id"])))
    )
    expected_digest = registry_raw.get("source_registry_version")
    if not isinstance(expected_digest, str) or str(digest) != expected_digest:
        raise ValueError("source registry digest mismatch")
    return SourceRegistry(
        sources={source.contract.source_id: source for source in sources},
        source_registry_version=digest,
    )
