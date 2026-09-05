from __future__ import annotations

import base64
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATHS = [
    ROOT / "contracts/acquisition/fetch_request_v0.schema.json",
    ROOT / "contracts/acquisition/bounded_fetch_result_v0.schema.json",
    ROOT / "contracts/acquisition/fetch_policy_v0.schema.json",
    ROOT / "contracts/source/source_contract_v0.schema.json",
]
POLICY_PATH = ROOT / "policies/fetch/structured_public_v0.json"
REGISTRY_PATH = ROOT / "sources/registry/registry_v0.json"
SOURCE_PATHS = [ROOT / "sources/registry/cisa.kev.v0.json", ROOT / "sources/registry/pypi.updates.v0.json"]
REQUEST_EXAMPLE = ROOT / "contracts/acquisition/examples/pypi_fetch_request_v0.json"
RESULT_EXAMPLE = ROOT / "contracts/acquisition/examples/pypi_fetch_success_v0.json"
SOURCE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
ALLOWED_REQUEST_HEADERS = {"Accept", "If-Modified-Since", "If-None-Match", "User-Agent"}
ALLOWED_RESPONSE_HEADERS = {"Cache-Control", "Content-Encoding", "Content-Length", "Content-Type", "Date", "ETag", "Last-Modified", "Retry-After", "X-Cache", "X-Cache-Hits"}
SUSPICIOUS_SECRET_KEYS = {"password", "passwd", "api_key", "apikey", "access_token", "refresh_token", "secret", "secret_key", "private_key"}
FORBIDDEN_DB_KEYS = {"database_url", "db_url", "db_host", "dsn", "postgres_dsn"}
EXPECTED_ENDPOINTS = {
    "pypi.updates": "https://pypi.org/rss/updates.xml",
    "cisa.kev": "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
}
REQUIRED_BLOCK_CLASSES = {"LOOPBACK", "PRIVATE", "LINK_LOCAL", "MULTICAST", "UNSPECIFIED", "CLOUD_METADATA", "IPV4_MAPPED_PRIVATE"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path}: top-level JSON must be object")
    return value


def canonical_json(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        raise SystemExit("canonical registry input must not contain binary float")
    if isinstance(value, str):
        return json.dumps(unicodedata.normalize("NFC", value), ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ",".join(canonical_json(item) for item in value) + "]"
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for raw_key, child in value.items():
            require(isinstance(raw_key, str), "canonical object key must be string")
            key = unicodedata.normalize("NFC", raw_key)
            require(key not in normalized, f"duplicate key after NFC normalization: {key!r}")
            normalized[key] = child
        return "{" + ",".join(canonical_json(key) + ":" + canonical_json(normalized[key]) for key in sorted(normalized)) + "}"
    raise SystemExit(f"unsupported canonical value type: {type(value).__name__}")


def scan_for_secrets_and_db(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = key.lower()
            require(lowered not in SUSPICIOUS_SECRET_KEYS, f"{path}.{key}: plaintext-secret-shaped key forbidden")
            require(lowered not in FORBIDDEN_DB_KEYS, f"{path}.{key}: DB coordinate forbidden in fetch/source contract")
            if lowered == "credential_ref":
                require(child is None or isinstance(child, str), f"{path}.{key}: credential_ref must be string/null")
            scan_for_secrets_and_db(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_for_secrets_and_db(child, f"{path}[{index}]")
    elif isinstance(value, str):
        lowered = value.lower()
        require("postgres://" not in lowered and "postgresql://" not in lowered, f"{path}: DB DSN forbidden")
        require("-----begin private key-----" not in lowered, f"{path}: private key material forbidden")


def validate_schemas() -> None:
    for path in SCHEMA_PATHS:
        schema = load(path)
        require(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", f"{path}: wrong JSON Schema draft")
        require(schema.get("type") == "object", f"{path}: schema must define object")
        require(schema.get("additionalProperties") is False, f"{path}: top-level additionalProperties must fail closed")
        required = schema.get("required")
        require(isinstance(required, list) and required, f"{path}: required list missing")
    request_schema = load(ROOT / "contracts/acquisition/fetch_request_v0.schema.json")
    request_header_names = request_schema["properties"]["request_headers"]["propertyNames"].get("enum")
    require(set(request_header_names or []) == ALLOWED_REQUEST_HEADERS, "FetchRequest schema header allowlist drifted")
    result_schema = load(ROOT / "contracts/acquisition/bounded_fetch_result_v0.schema.json")
    response_header_names = result_schema["properties"]["response_headers"]["propertyNames"].get("enum")
    require(set(response_header_names or []) == ALLOWED_RESPONSE_HEADERS, "BoundedFetchResult schema header allowlist drifted")
    source_schema = load(ROOT / "contracts/source/source_contract_v0.schema.json")
    endpoint_schema = source_schema["properties"]["endpoint"]
    require(isinstance(endpoint_schema.get("allOf"), list) and len(endpoint_schema["allOf"]) == 2, "SourceContract auth/credential conditional missing")


def validate_policy() -> dict[str, Any]:
    policy = load(POLICY_PATH)
    require(policy.get("schema_version") == "fetch-policy-v0", "fetch policy schema version mismatch")
    require(policy.get("policy_profile") == "structured-public-v0", "unexpected fetch policy profile")
    require(policy.get("allowed_schemes") == ["https"], "V0 structured fetch must be HTTPS-only")
    require(policy.get("forward_authorization_cross_origin") is False, "cross-origin authorization forwarding must be false")
    blocked = policy.get("blocked_address_classes")
    require(isinstance(blocked, list) and REQUIRED_BLOCK_CLASSES <= set(blocked), "blocked address classes incomplete")
    require(0 <= int(policy["max_redirects"]) <= 5, "redirect bound invalid")
    require(1024 <= int(policy["max_response_bytes"]) <= 16 * 1024 * 1024, "response bound invalid")
    require(int(policy["max_expanded_bytes"]) >= int(policy["max_response_bytes"]), "expanded bound smaller than response bound")
    retry = policy.get("retry")
    require(isinstance(retry, dict), "retry policy missing")
    require(1 <= int(retry["max_attempts"]) <= 5, "retry attempts unbounded")
    require(int(retry["max_retry_after_seconds"]) <= 3600, "Retry-After cap too high")
    require(retry.get("jitter") is True, "retry jitter must be enabled")
    return policy


def validate_source_contract(source: dict[str, Any]) -> None:
    source_id = source.get("source_id")
    require(isinstance(source_id, str) and SOURCE_ID.fullmatch(source_id), f"invalid source_id: {source_id!r}")
    require(source.get("schema_version") == "source-contract-v0", f"{source_id}: wrong schema version")
    require(source.get("enabled") is True, f"{source_id}: preflight source must be enabled candidate")
    require(source.get("acquisition_class") == "A_AUTHORITATIVE_STRUCTURED", f"{source_id}: wrong acquisition class")
    roles = source.get("signal_roles")
    require(isinstance(roles, list) and roles == sorted(set(roles)), f"{source_id}: signal_roles must be sorted/unique")
    endpoint = source.get("endpoint")
    require(isinstance(endpoint, dict), f"{source_id}: endpoint missing")
    require(endpoint.get("url") == EXPECTED_ENDPOINTS[source_id], f"{source_id}: endpoint changed unexpectedly")
    require(endpoint.get("method") == "GET", f"{source_id}: V0 only authorizes GET")
    require(endpoint.get("authentication") == "NONE", f"{source_id}: auth unexpectedly required")
    require(endpoint.get("credential_ref") is None, f"{source_id}: authentication=NONE requires null credential_ref")
    require(endpoint.get("policy_profile") == "structured-public-v0", f"{source_id}: wrong policy profile")
    accepted = endpoint.get("accepted_content_types")
    require(isinstance(accepted, list) and accepted, f"{source_id}: accepted content types missing")
    policy = source.get("policy")
    require(isinstance(policy, dict), f"{source_id}: source policy missing")
    require(policy.get("access_state") == "ALLOWED", f"{source_id}: enabled source access must be ALLOWED")
    require(policy.get("browser_authorized") is False, f"{source_id}: browser use must be disabled")
    require(policy.get("raw_artifact_retention") == "NONE", f"{source_id}: raw artifact retention not authorized")
    refs = policy.get("policy_references")
    require(isinstance(refs, list) and refs, f"{source_id}: policy references required")
    capability = source.get("capability")
    require(isinstance(capability, dict), f"{source_id}: capability missing")
    require(capability.get("primary_evidence_eligible") is True, f"{source_id}: initial source must be primary-evidence eligible")
    if source_id == "pypi.updates":
        require(source.get("transport") == "RSS", "PyPI transport must be RSS")
        require(capability.get("etag_support") == "SUPPORTED", "PyPI official API docs state RSS provides ETag")
        require(capability.get("finite_window") is True, "PyPI latest-updates feed must preserve finite-window risk")
    if source_id == "cisa.kev":
        require(source.get("transport") == "JSON_HTTP", "CISA transport must be JSON_HTTP")
        require(capability.get("finite_window") is False, "CISA KEV is a full catalog, not finite recent window")
        require(endpoint.get("fallback_urls") == ["https://raw.githubusercontent.com/cisagov/kev-data/develop/known_exploited_vulnerabilities.json"], "CISA same-authority fallback missing or changed")
        require(endpoint.get("fallback_semantics") == "SAME_AUTHORITY_MIRROR", "CISA fallback must not become independent corroboration")
        require(capability.get("schema_reference") == "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities_schema.json", "CISA schema reference changed unexpectedly")


def validate_registry(sources: list[dict[str, Any]]) -> None:
    registry = load(REGISTRY_PATH)
    require(registry.get("schema_version") == "source-registry-v0", "source registry schema mismatch")
    ids = [source["source_id"] for source in sorted(sources, key=lambda item: item["source_id"])]
    require(registry.get("required_source_ids") == ids, "registry source IDs must be sorted and exact")
    paths = registry.get("source_contract_paths")
    require(isinstance(paths, list) and paths == sorted(paths), "registry paths must be sorted")
    require(len(paths) == len(sources), "registry source/path cardinality mismatch")
    version = registry.get("source_registry_version")
    require(isinstance(version, str) and DIGEST.fullmatch(version), "registry digest text malformed")
    digest = "sha256:" + hashlib.sha256(canonical_json(sorted(sources, key=lambda item: item["source_id"])).encode("utf-8")).hexdigest()
    require(version == digest, f"source registry digest mismatch: expected {digest}")


def validate_examples(policy: dict[str, Any], sources: list[dict[str, Any]]) -> None:
    request = load(REQUEST_EXAMPLE)
    result = load(RESULT_EXAMPLE)
    pypi = next(source for source in sources if source["source_id"] == "pypi.updates")
    require(request.get("schema_version") == "fetch-request-v0", "request example schema version mismatch")
    require(request.get("source_id") == "pypi.updates", "request example wrong source")
    require(request.get("url") == pypi["endpoint"]["url"], "request URL must derive from source contract")
    require(request.get("method") == "GET", "request method must be GET")
    require(request.get("credential_ref") is None, "request example must carry no credential")
    require(request.get("deadline_ms") == policy["deadline_ms"], "request deadline must materialize policy bound")
    require(request.get("max_response_bytes") == policy["max_response_bytes"], "request response bound must materialize policy")
    require(request.get("max_redirects") == policy["max_redirects"], "request redirect bound must materialize policy")
    headers = request.get("request_headers")
    require(isinstance(headers, dict), "request headers missing")
    require(set(headers) <= ALLOWED_REQUEST_HEADERS, "request example contains header outside V0 allowlist")
    require("User-Agent" in headers, "PyPI request must identify FRONTIER with User-Agent")
    require(result.get("schema_version") == "bounded-fetch-result-v0", "result example schema version mismatch")
    require(result.get("request_id") == request.get("request_id"), "result/request operational correlation mismatch")
    require(result.get("outcome") == "SUCCESS", "success example must be SUCCESS")
    require(result.get("failure") is None, "success example cannot carry failure")
    response_headers = result.get("response_headers")
    require(isinstance(response_headers, dict), "result response_headers missing")
    require(set(response_headers) <= ALLOWED_RESPONSE_HEADERS, "result contains header outside sanitized V0 allowlist")
    chain = result.get("redirect_chain")
    require(isinstance(chain, list) and len(chain) <= int(request["max_redirects"]), "redirect chain exceeds request bound")
    encoded = result.get("body_base64")
    require(isinstance(encoded, str), "success result must carry body bytes")
    try:
        body = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise SystemExit(f"result body is not strict base64: {exc}") from exc
    digest = "sha256:" + hashlib.sha256(body).hexdigest()
    require(result.get("body_digest") == digest, "fetcher body_digest does not match wire bytes")
    require(result.get("expanded_bytes") == len(body), "expanded byte telemetry mismatch")
    require(len(body) <= int(request["max_response_bytes"]), "example body exceeds request response bound")


def main() -> None:
    validate_schemas()
    policy = validate_policy()
    sources = [load(path) for path in SOURCE_PATHS]
    require([source["source_id"] for source in sources] == ["cisa.kev", "pypi.updates"], "source files/order unexpected")
    for source in sources:
        scan_for_secrets_and_db(source, source["source_id"])
        validate_source_contract(source)
    scan_for_secrets_and_db(policy, "fetch_policy")
    validate_registry(sources)
    validate_examples(policy, sources)
    print("PR-02 executable contract preflight: PASS")
    print(f"sources={','.join(source['source_id'] for source in sources)}")
    print(f"source_registry_version={load(REGISTRY_PATH)['source_registry_version']}")


if __name__ == "__main__":
    main()
