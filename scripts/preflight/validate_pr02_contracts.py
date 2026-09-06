from __future__ import annotations

import base64
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATHS = [
    ROOT / "contracts/acquisition/fetch_request_v0.schema.json",
    ROOT / "contracts/acquisition/bounded_fetch_result_v0.schema.json",
    ROOT / "contracts/acquisition/fetch_policy_v0.schema.json",
    ROOT / "contracts/source/source_contract_v0.schema.json",
]
POLICY_PATH = ROOT / "policies/fetch/structured_public_v0.json"
REGISTRY_PATH = ROOT / "sources/registry/registry_v0.json"
REQUEST_EXAMPLE = ROOT / "contracts/acquisition/examples/pypi_fetch_request_v0.json"
RESULT_EXAMPLE = ROOT / "contracts/acquisition/examples/pypi_fetch_success_v0.json"
SOURCE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
ALLOWED_REQUEST_HEADERS = {"Accept", "If-Modified-Since", "If-None-Match", "User-Agent"}
ALLOWED_RESPONSE_HEADERS = {
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
SUSPICIOUS_SECRET_KEYS = {
    "password",
    "passwd",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "secret",
    "secret_key",
    "private_key",
}
FORBIDDEN_DB_KEYS = {"database_url", "db_url", "db_host", "dsn", "postgres_dsn"}
REQUIRED_BLOCK_CLASSES = {
    "LOOPBACK",
    "PRIVATE",
    "LINK_LOCAL",
    "MULTICAST",
    "UNSPECIFIED",
    "CLOUD_METADATA",
    "IPV4_MAPPED_PRIVATE",
}
EXPECTED_SOURCES: dict[str, dict[str, Any]] = {
    "arxiv.cs-ai": {
        "acquisition_class": "A_AUTHORITATIVE_STRUCTURED",
        "roles": ["PRIMARY_EMISSION"],
        "transport": "ATOM",
        "endpoint": (
            "https://export.arxiv.org/api/query?"
            "search_query=cat%3Acs.AI&start=0&max_results=100&"
            "sortBy=submittedDate&sortOrder=descending"
        ),
        "primary": True,
        "finite": True,
    },
    "cisa.kev": {
        "acquisition_class": "A_AUTHORITATIVE_STRUCTURED",
        "roles": ["BEHAVIORAL", "PRIMARY_EMISSION"],
        "transport": "JSON_HTTP",
        "endpoint": (
            "https://www.cisa.gov/sites/default/files/feeds/"
            "known_exploited_vulnerabilities.json"
        ),
        "primary": True,
        "finite": False,
    },
    "gdelt.frontier": {
        "acquisition_class": "B_OPEN_AGGREGATION",
        "roles": ["DISCOVERY"],
        "transport": "JSON_HTTP",
        "endpoint": (
            "https://api.gdeltproject.org/api/v2/doc/doc?"
            "query=(AI%20OR%20%22artificial%20intelligence%22%20OR%20LLM%20OR%20"
            "%22machine%20learning%22%20OR%20cryptocurrency%20OR%20bitcoin%20OR%20"
            "ethereum%20OR%20cybersecurity%20OR%20%22open%20source%22)&mode=artlist&"
            "format=json&timespan=1h&maxrecords=250&sort=datedesc"
        ),
        "primary": False,
        "finite": True,
    },
    "github.ml-repos": {
        "acquisition_class": "A_AUTHORITATIVE_STRUCTURED",
        "roles": ["BEHAVIORAL", "DISCOVERY"],
        "transport": "REST",
        "endpoint": (
            "https://api.github.com/search/repositories?"
            "q=topic%3Amachine-learning+fork%3Afalse+archived%3Afalse&"
            "sort=updated&order=desc&per_page=100"
        ),
        "primary": False,
        "finite": True,
    },
    "hf.models": {
        "acquisition_class": "A_AUTHORITATIVE_STRUCTURED",
        "roles": ["PRIMARY_EMISSION"],
        "transport": "REST",
        "endpoint": (
            "https://huggingface.co/api/models?sort=lastModified&direction=-1&limit=100&"
            "expand=author,createdAt,lastModified,pipeline_tag,sha,tags"
        ),
        "primary": True,
        "finite": True,
    },
    "hn.frontpage": {
        "acquisition_class": "A_AUTHORITATIVE_STRUCTURED",
        "roles": ["ATTENTION"],
        "transport": "RSS",
        "endpoint": "https://news.ycombinator.com/rss",
        "primary": False,
        "finite": True,
    },
    "pypi.updates": {
        "acquisition_class": "A_AUTHORITATIVE_STRUCTURED",
        "roles": ["PRIMARY_EMISSION"],
        "transport": "RSS",
        "endpoint": "https://pypi.org/rss/updates.xml",
        "primary": True,
        "finite": True,
    },
}


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
        return (
            "{"
            + ",".join(
                canonical_json(key) + ":" + canonical_json(normalized[key])
                for key in sorted(normalized)
            )
            + "}"
        )
    raise SystemExit(f"unsupported canonical value type: {type(value).__name__}")


def scan_for_secrets_and_db(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = key.lower()
            require(
                lowered not in SUSPICIOUS_SECRET_KEYS,
                f"{path}.{key}: plaintext-secret-shaped key forbidden",
            )
            require(
                lowered not in FORBIDDEN_DB_KEYS,
                f"{path}.{key}: DB coordinate forbidden in fetch/source contract",
            )
            if lowered == "credential_ref":
                require(
                    child is None or isinstance(child, str),
                    f"{path}.{key}: credential_ref must be string/null",
                )
            scan_for_secrets_and_db(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_for_secrets_and_db(child, f"{path}[{index}]")
    elif isinstance(value, str):
        lowered = value.lower()
        require(
            "postgres://" not in lowered and "postgresql://" not in lowered,
            f"{path}: DB DSN forbidden",
        )
        require(
            "-----begin private key-----" not in lowered,
            f"{path}: private key material forbidden",
        )


def validate_schemas() -> None:
    for path in SCHEMA_PATHS:
        schema = load(path)
        require(
            schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema",
            f"{path}: wrong JSON Schema draft",
        )
        require(schema.get("type") == "object", f"{path}: schema must define object")
        require(
            schema.get("additionalProperties") is False,
            f"{path}: top-level additionalProperties must fail closed",
        )
        required = schema.get("required")
        require(isinstance(required, list) and required, f"{path}: required list missing")
    request_schema = load(ROOT / "contracts/acquisition/fetch_request_v0.schema.json")
    request_header_names = request_schema["properties"]["request_headers"]["propertyNames"].get(
        "enum"
    )
    require(
        set(request_header_names or []) == ALLOWED_REQUEST_HEADERS,
        "FetchRequest schema header allowlist drifted",
    )
    result_schema = load(ROOT / "contracts/acquisition/bounded_fetch_result_v0.schema.json")
    response_header_names = result_schema["properties"]["response_headers"]["propertyNames"].get(
        "enum"
    )
    require(
        set(response_header_names or []) == ALLOWED_RESPONSE_HEADERS,
        "BoundedFetchResult schema header allowlist drifted",
    )
    source_schema = load(ROOT / "contracts/source/source_contract_v0.schema.json")
    endpoint_schema = source_schema["properties"]["endpoint"]
    require(
        isinstance(endpoint_schema.get("allOf"), list)
        and len(endpoint_schema["allOf"]) == 2,
        "SourceContract auth/credential conditional missing",
    )


def validate_policy() -> dict[str, Any]:
    policy = load(POLICY_PATH)
    require(
        policy.get("schema_version") == "fetch-policy-v0",
        "fetch policy schema version mismatch",
    )
    require(
        policy.get("policy_profile") == "structured-public-v0",
        "unexpected fetch policy profile",
    )
    require(policy.get("allowed_schemes") == ["https"], "V0 structured fetch must be HTTPS-only")
    require(
        policy.get("forward_authorization_cross_origin") is False,
        "cross-origin authorization forwarding must be false",
    )
    blocked = policy.get("blocked_address_classes")
    require(
        isinstance(blocked, list) and REQUIRED_BLOCK_CLASSES <= set(blocked),
        "blocked address classes incomplete",
    )
    require(0 <= int(policy["max_redirects"]) <= 5, "redirect bound invalid")
    require(
        1024 <= int(policy["max_response_bytes"]) <= 16 * 1024 * 1024,
        "response bound invalid",
    )
    require(
        int(policy["max_expanded_bytes"]) >= int(policy["max_response_bytes"]),
        "expanded bound smaller than response bound",
    )
    retry = policy.get("retry")
    require(isinstance(retry, dict), "retry policy missing")
    require(1 <= int(retry["max_attempts"]) <= 5, "retry attempts unbounded")
    require(int(retry["max_retry_after_seconds"]) <= 3600, "Retry-After cap too high")
    require(retry.get("jitter") is True, "retry jitter must be enabled")
    return policy


def validate_source_contract(source: dict[str, Any]) -> None:
    source_id = source.get("source_id")
    require(
        isinstance(source_id, str) and SOURCE_ID.fullmatch(source_id) is not None,
        f"invalid source_id: {source_id!r}",
    )
    require(source_id in EXPECTED_SOURCES, f"unexpected enabled source: {source_id}")
    expected = EXPECTED_SOURCES[source_id]
    require(
        source.get("schema_version") == "source-contract-v0",
        f"{source_id}: wrong schema version",
    )
    require(source.get("enabled") is True, f"{source_id}: source must be enabled")
    require(
        source.get("acquisition_class") == expected["acquisition_class"],
        f"{source_id}: wrong acquisition class",
    )
    roles = source.get("signal_roles")
    require(
        isinstance(roles, list) and roles == expected["roles"] == sorted(set(roles)),
        f"{source_id}: signal roles drifted",
    )
    require(source.get("transport") == expected["transport"], f"{source_id}: transport drifted")
    endpoint = source.get("endpoint")
    require(isinstance(endpoint, dict), f"{source_id}: endpoint missing")
    require(
        endpoint.get("url") == expected["endpoint"],
        f"{source_id}: endpoint changed unexpectedly",
    )
    require(endpoint.get("method") == "GET", f"{source_id}: V0 only authorizes GET")
    require(endpoint.get("authentication") == "NONE", f"{source_id}: auth unexpectedly required")
    require(
        endpoint.get("credential_ref") is None,
        f"{source_id}: authentication=NONE requires null credential_ref",
    )
    require(
        endpoint.get("policy_profile") == "structured-public-v0",
        f"{source_id}: wrong policy profile",
    )
    accepted = endpoint.get("accepted_content_types")
    require(isinstance(accepted, list) and accepted, f"{source_id}: accepted content types missing")
    cadence = source.get("expected_cadence")
    require(isinstance(cadence, dict), f"{source_id}: expected cadence missing")
    poll_seconds = cadence.get("poll_interval_seconds")
    require(
        isinstance(poll_seconds, int) and 60 <= poll_seconds <= 86400,
        f"{source_id}: poll interval invalid",
    )
    policy = source.get("policy")
    require(isinstance(policy, dict), f"{source_id}: source policy missing")
    require(
        policy.get("access_state") == "ALLOWED",
        f"{source_id}: enabled source access must be ALLOWED",
    )
    require(policy.get("browser_authorized") is False, f"{source_id}: browser use must be disabled")
    require(
        policy.get("raw_artifact_retention") == "NONE",
        f"{source_id}: raw artifact retention not authorized",
    )
    refs = policy.get("policy_references")
    require(isinstance(refs, list) and refs, f"{source_id}: policy references required")
    capability = source.get("capability")
    require(isinstance(capability, dict), f"{source_id}: capability missing")
    require(
        capability.get("primary_evidence_eligible") is expected["primary"],
        f"{source_id}: primary-evidence eligibility drifted",
    )
    require(
        capability.get("finite_window") is expected["finite"],
        f"{source_id}: finite-window classification drifted",
    )

    if source_id == "pypi.updates":
        require(
            capability.get("etag_support") == "SUPPORTED",
            "PyPI official API docs state RSS provides ETag",
        )
    elif source_id == "cisa.kev":
        require(
            endpoint.get("fallback_urls")
            == [
                "https://raw.githubusercontent.com/cisagov/kev-data/develop/"
                "known_exploited_vulnerabilities.json"
            ],
            "CISA same-authority fallback missing or changed",
        )
        require(
            endpoint.get("fallback_semantics") == "SAME_AUTHORITY_MIRROR",
            "CISA fallback must not become independent corroboration",
        )
        require(
            capability.get("schema_reference")
            == "https://www.cisa.gov/sites/default/files/feeds/"
            "known_exploited_vulnerabilities_schema.json",
            "CISA schema reference changed unexpectedly",
        )
    elif source_id == "hn.frontpage":
        require(
            roles == ["ATTENTION"] and capability.get("primary_evidence_eligible") is False,
            "HN must remain attention-only rather than factual authority",
        )
    elif source_id == "gdelt.frontier":
        require(
            roles == ["DISCOVERY"] and capability.get("primary_evidence_eligible") is False,
            "GDELT must remain discovery-only rather than factual authority",
        )
        parsed = urlsplit(str(endpoint["url"]))
        query = parse_qs(parsed.query)
        require(query.get("mode") == ["artlist"], "GDELT must use ArticleList mode")
        require(query.get("format") == ["json"], "GDELT must use JSON output")
        require(query.get("maxrecords") == ["250"], "GDELT window cap drifted")
        require(query.get("sort") == ["datedesc"], "GDELT ordering must be date-descending")
        require(query.get("timespan") == ["1h"], "GDELT discovery window drifted")
    elif source_id == "hf.models":
        url = str(endpoint["url"])
        require("limit=100" in url, "Hugging Face result cap drifted")
        require("sort=lastModified" in url, "Hugging Face ordering drifted")
        require(
            all(token not in url for token in ("downloads", "likes", "trendingScore")),
            "volatile Hugging Face counters must not enter the canonical fetch profile",
        )
        require(
            any("rate-limits" in str(ref) for ref in refs),
            "Hugging Face policy must reference rate-limit documentation",
        )
    elif source_id == "arxiv.cs-ai":
        require(
            roles == ["PRIMARY_EMISSION"] and capability.get("primary_evidence_eligible") is True,
            "arXiv must describe repository emission, not downstream corroboration",
        )
        parsed = urlsplit(str(endpoint["url"]))
        query = parse_qs(parsed.query)
        require(query.get("search_query") == ["cat:cs.AI"], "arXiv category scope drifted")
        require(query.get("start") == ["0"], "arXiv first-page scope drifted")
        require(query.get("max_results") == ["100"], "arXiv result cap drifted")
        require(query.get("sortBy") == ["submittedDate"], "arXiv ordering field drifted")
        require(query.get("sortOrder") == ["descending"], "arXiv ordering direction drifted")
        require(
            int(poll_seconds) >= 300,
            "arXiv polling must remain sparse enough for public API etiquette",
        )
    elif source_id == "github.ml-repos":
        require(
            roles == ["BEHAVIORAL", "DISCOVERY"]
            and capability.get("primary_evidence_eligible") is False,
            "GitHub search must remain behavioral/discovery evidence",
        )
        parsed = urlsplit(str(endpoint["url"]))
        query = parse_qs(parsed.query)
        require(query.get("per_page") == ["100"], "GitHub finite result cap drifted")
        require(query.get("sort") == ["updated"], "GitHub activity ordering drifted")
        require(query.get("order") == ["desc"], "GitHub ordering direction drifted")
        q = query.get("q")
        require(
            q == ["topic:machine-learning fork:false archived:false"],
            "GitHub search scope drifted",
        )
        require(
            int(poll_seconds) >= 600,
            "GitHub unauthenticated search polling must remain conservative",
        )
        require(
            any("rate-limits" in str(ref) for ref in refs),
            "GitHub policy must reference current rate-limit documentation",
        )


def load_registry_sources() -> list[dict[str, Any]]:
    registry = load(REGISTRY_PATH)
    paths = registry.get("source_contract_paths")
    require(isinstance(paths, list) and paths == sorted(paths), "registry paths must be sorted")
    require(all(isinstance(path, str) for path in paths), "registry paths must be strings")
    return [load(ROOT / str(path)) for path in paths]


def validate_registry(sources: list[dict[str, Any]]) -> None:
    registry = load(REGISTRY_PATH)
    require(
        registry.get("schema_version") == "source-registry-v0",
        "source registry schema mismatch",
    )
    ids = [source["source_id"] for source in sorted(sources, key=lambda item: item["source_id"])]
    require(ids == sorted(EXPECTED_SOURCES), "enabled source set drifted")
    require(registry.get("required_source_ids") == ids, "registry source IDs must be sorted and exact")
    paths = registry.get("source_contract_paths")
    require(isinstance(paths, list) and paths == sorted(paths), "registry paths must be sorted")
    require(len(paths) == len(sources), "registry source/path cardinality mismatch")
    version = registry.get("source_registry_version")
    require(isinstance(version, str) and DIGEST.fullmatch(version), "registry digest text malformed")
    digest = "sha256:" + hashlib.sha256(
        canonical_json(sorted(sources, key=lambda item: item["source_id"])).encode("utf-8")
    ).hexdigest()
    require(version == digest, f"source registry digest mismatch: expected {digest}")


def validate_examples(policy: dict[str, Any], sources: list[dict[str, Any]]) -> None:
    request = load(REQUEST_EXAMPLE)
    result = load(RESULT_EXAMPLE)
    pypi = next(source for source in sources if source["source_id"] == "pypi.updates")
    require(
        request.get("schema_version") == "fetch-request-v0",
        "request example schema version mismatch",
    )
    require(request.get("source_id") == "pypi.updates", "request example wrong source")
    require(
        request.get("url") == pypi["endpoint"]["url"],
        "request URL must derive from source contract",
    )
    require(request.get("method") == "GET", "request method must be GET")
    require(request.get("credential_ref") is None, "request example must carry no credential")
    require(
        request.get("deadline_ms") == policy["deadline_ms"],
        "request deadline must materialize policy bound",
    )
    require(
        request.get("max_response_bytes") == policy["max_response_bytes"],
        "request response bound must materialize policy",
    )
    require(
        request.get("max_redirects") == policy["max_redirects"],
        "request redirect bound must materialize policy",
    )
    headers = request.get("request_headers")
    require(isinstance(headers, dict), "request headers missing")
    require(
        set(headers) <= ALLOWED_REQUEST_HEADERS,
        "request example contains header outside V0 allowlist",
    )
    require("User-Agent" in headers, "PyPI request must identify FRONTIER with User-Agent")
    require(
        result.get("schema_version") == "bounded-fetch-result-v0",
        "result example schema version mismatch",
    )
    require(
        result.get("request_id") == request.get("request_id"),
        "result/request operational correlation mismatch",
    )
    require(result.get("outcome") == "SUCCESS", "success example must be SUCCESS")
    require(result.get("failure") is None, "success example cannot carry failure")
    response_headers = result.get("response_headers")
    require(isinstance(response_headers, dict), "result response_headers missing")
    require(
        set(response_headers) <= ALLOWED_RESPONSE_HEADERS,
        "result contains header outside sanitized V0 allowlist",
    )
    chain = result.get("redirect_chain")
    require(
        isinstance(chain, list) and len(chain) <= int(request["max_redirects"]),
        "redirect chain exceeds request bound",
    )
    encoded = result.get("body_base64")
    require(isinstance(encoded, str), "success result must carry body bytes")
    try:
        body = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise SystemExit(f"result body is not strict base64: {exc}") from exc
    digest = "sha256:" + hashlib.sha256(body).hexdigest()
    require(result.get("body_digest") == digest, "fetcher body_digest does not match wire bytes")
    require(result.get("expanded_bytes") == len(body), "expanded byte telemetry mismatch")
    require(
        len(body) <= int(request["max_response_bytes"]),
        "example body exceeds request response bound",
    )


def main() -> None:
    validate_schemas()
    policy = validate_policy()
    sources = load_registry_sources()
    for source in sources:
        scan_for_secrets_and_db(source, str(source.get("source_id")))
        validate_source_contract(source)
    scan_for_secrets_and_db(policy, "fetch_policy")
    validate_registry(sources)
    validate_examples(policy, sources)
    print("executable source/fetch contract preflight: PASS")
    print(f"sources={','.join(source['source_id'] for source in sources)}")
    print(f"source_registry_version={load(REGISTRY_PATH)['source_registry_version']}")


if __name__ == "__main__":
    main()
