from __future__ import annotations

import json
from pathlib import Path

CORPUS = Path("fixtures/acquisition/corpus_v0.json")
TRANSPORT = Path("fixtures/acquisition/transport_security_v0.json")
ALLOWED_OUTCOMES = {
    "ACCEPT",
    "REJECT",
    "DEGRADE",
    "QUARANTINE",
    "RETRY_LATER",
    "FAIL_CLOSED",
}
REQUIRED_SOURCES = {"pypi.updates", "cisa.kev", "fixture.http", "hn", "gdelt.doc"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def by_id(cases: list[dict[str, object]], case_id: str) -> dict[str, object]:
    matches = [case for case in cases if case.get("id") == case_id]
    require(len(matches) == 1, f"expected exactly one {case_id}")
    return matches[0]


def validate_case_shape(cases: list[dict[str, object]], *, minimum: int) -> None:
    require(len(cases) >= minimum, f"fixture pack unexpectedly shrank below {minimum} cases")
    ids: list[str] = []
    for index, case in enumerate(cases):
        case_id = case.get("id")
        outcome = case.get("expected")
        assertions = case.get("assertions")
        require(isinstance(case_id, str) and case_id, f"case {index} missing id")
        require(outcome in ALLOWED_OUTCOMES, f"{case_id} has invalid outcome {outcome!r}")
        require(isinstance(assertions, dict) and assertions, f"{case_id} must have non-empty assertions")
        ids.append(case_id)
    require(len(ids) == len(set(ids)), "fixture case ids must be unique within pack")


def validate_acquisition_corpus() -> list[dict[str, object]]:
    document = json.loads(CORPUS.read_text(encoding="utf-8"))
    require(
        document.get("schema_version") == "frontier-hostile-acquisition-corpus-v0",
        "unexpected acquisition corpus schema_version",
    )
    authority = document.get("authority")
    require(isinstance(authority, dict), "authority must be an object")
    require(
        authority.get("runtime_implementation_authorized") is False,
        "fixture preflight must not authorize runtime implementation",
    )

    raw_cases = document.get("cases")
    require(isinstance(raw_cases, list), "cases must be a list")
    cases = [case for case in raw_cases if isinstance(case, dict)]
    require(len(cases) == len(raw_cases), "all acquisition cases must be objects")
    validate_case_shape(cases, minimum=18)

    sources = {case.get("source_id") for case in cases if isinstance(case.get("source_id"), str)}
    require(REQUIRED_SOURCES <= sources, f"missing source lanes: {sorted(REQUIRED_SOURCES - sources)}")

    xxe = by_id(cases, "PYPI-004")
    require(xxe.get("expected") == "REJECT", "XXE fixture must remain REJECT")
    require("<!ENTITY" in str(xxe.get("payload")), "XXE fixture lost entity payload")
    xxe_assertions = xxe["assertions"]
    require(isinstance(xxe_assertions, dict), "XXE assertions must be an object")
    require(xxe_assertions.get("external_entity_resolutions") == 0, "XXE fixture must permit zero entity resolution")
    require(xxe_assertions.get("network_side_effects") == 0, "XXE fixture must permit zero network side effects")

    redirect = by_id(cases, "HTTP-001")
    redirect_assertions = redirect["assertions"]
    require(isinstance(redirect_assertions, dict), "redirect assertions must be an object")
    require(redirect.get("expected") == "REJECT", "private-IP redirect must remain REJECT")
    require(redirect_assertions.get("forbidden_connections") == 0, "private-IP redirect must never connect")

    window_gap = by_id(cases, "PYPI-005")
    window_assertions = window_gap["assertions"]
    require(isinstance(window_assertions, dict), "window assertions must be an object")
    require(window_gap.get("expected") == "DEGRADE", "finite feed-window gap must degrade completeness")
    require(window_assertions.get("transport_health") == "OK", "finite feed-window fixture must prove transport can stay healthy")
    require(window_assertions.get("completeness_health") == "DEGRADED", "finite feed-window fixture must degrade completeness")

    backfill = by_id(cases, "CISA-005")
    backfill_assertions = backfill["assertions"]
    require(isinstance(backfill_assertions, dict), "backfill assertions must be an object")
    require(backfill_assertions.get("live_alert_eligible") is False, "backfill must not become a live alert solely because it was ingested now")

    hn = by_id(cases, "HN-001")
    hn_assertions = hn["assertions"]
    require(isinstance(hn_assertions, dict), "HN assertions must be an object")
    require(hn_assertions.get("attention_observations") == 2, "HN duplicate-root fixture must preserve two attention observations")
    require(hn_assertions.get("external_factual_roots_max") == 1, "HN duplicate-root fixture must not manufacture corroboration")

    gdelt = by_id(cases, "GDELT-001")
    gdelt_assertions = gdelt["assertions"]
    require(isinstance(gdelt_assertions, dict), "GDELT assertions must be an object")
    require(gdelt_assertions.get("discovery_rows") == 6, "GDELT syndication fixture must preserve discovery propagation")
    require(gdelt_assertions.get("independent_factual_roots_max") == 1, "GDELT syndication fixture must not manufacture six roots")

    malformed_time = by_id(cases, "GDELT-002")
    malformed_assertions = malformed_time["assertions"]
    require(isinstance(malformed_assertions, dict), "malformed-time assertions must be an object")
    require(malformed_assertions.get("default_malformed_time_to_now") is False, "malformed source times must never silently become now")

    return cases


def validate_transport_pack() -> list[dict[str, object]]:
    document = json.loads(TRANSPORT.read_text(encoding="utf-8"))
    require(
        document.get("schema_version") == "frontier-transport-security-fixtures-v0",
        "unexpected transport fixture schema_version",
    )
    authority = document.get("authority")
    require(isinstance(authority, dict), "transport authority must be an object")
    require(
        authority.get("runtime_implementation_authorized") is False,
        "transport fixture preflight must not authorize runtime implementation",
    )

    raw_cases = document.get("cases")
    require(isinstance(raw_cases, list), "transport cases must be a list")
    cases = [case for case in raw_cases if isinstance(case, dict)]
    require(len(cases) == len(raw_cases), "all transport cases must be objects")
    validate_case_shape(cases, minimum=18)

    rebinding = by_id(cases, "TS-001")
    rebinding_assertions = rebinding["assertions"]
    require(isinstance(rebinding_assertions, dict), "rebinding assertions must be an object")
    require(rebinding.get("expected") == "REJECT", "DNS rebinding must remain REJECT")
    require(rebinding_assertions.get("connect_target_revalidated") is True, "DNS rebinding must revalidate the actual connect target")
    require(rebinding_assertions.get("forbidden_connections") == 0, "DNS rebinding must never reach private target")

    for case_id in ("TS-002", "TS-003", "TS-004", "TS-005"):
        case = by_id(cases, case_id)
        assertions = case["assertions"]
        require(isinstance(assertions, dict), f"{case_id} assertions must be an object")
        require(case.get("expected") == "REJECT", f"{case_id} must remain REJECT")
        require(assertions.get("forbidden_connections") == 0, f"{case_id} must never connect")

    credentials = by_id(cases, "TS-008")
    credentials_assertions = credentials["assertions"]
    require(isinstance(credentials_assertions, dict), "credential assertions must be an object")
    require(credentials_assertions.get("forward_authorization_cross_origin") is False, "cross-origin redirect must not forward Authorization")
    require(credentials_assertions.get("secret_leaks") == 0, "redirect fixture must leak zero secrets")

    bomb = by_id(cases, "TS-009")
    bomb_assertions = bomb["assertions"]
    require(isinstance(bomb_assertions, dict), "bomb assertions must be an object")
    require(bomb.get("expected") == "REJECT", "expansion bomb must remain REJECT")
    require(bomb_assertions.get("expanded_limit_enforced") is True, "expanded-byte limit must be enforced")
    require(bomb_assertions.get("full_body_buffered") is False, "expansion bomb must not require full buffering")

    length_lie = by_id(cases, "TS-010")
    length_assertions = length_lie["assertions"]
    require(isinstance(length_assertions, dict), "content-length assertions must be an object")
    require(length_assertions.get("stream_limit_enforced_independent_of_header") is True, "stream limits must not trust Content-Length")

    mime = by_id(cases, "TS-011")
    mime_assertions = mime["assertions"]
    require(isinstance(mime_assertions, dict), "MIME assertions must be an object")
    require(mime_assertions.get("transport_health") == "OK", "MIME lie must prove transport can be healthy")
    require(mime_assertions.get("schema_health") == "DEGRADED", "MIME lie must degrade schema health")

    slow = by_id(cases, "TS-012")
    slow_assertions = slow["assertions"]
    require(isinstance(slow_assertions, dict), "slow-body assertions must be an object")
    require(slow_assertions.get("deadline_enforced") is True, "slow body must enforce deadline")
    require(slow_assertions.get("partial_body_not_canonical") is True, "partial timed-out body must not become canonical")

    retry = by_id(cases, "TS-014")
    retry_assertions = retry["assertions"]
    require(isinstance(retry_assertions, dict), "retry assertions must be an object")
    require(retry_assertions.get("retry_after_respected") is True, "429 Retry-After must be respected")
    require(retry_assertions.get("immediate_retry") is False, "429 must not trigger immediate retry")

    absurd_retry = by_id(cases, "TS-015")
    absurd_assertions = absurd_retry["assertions"]
    require(isinstance(absurd_assertions, dict), "absurd-retry assertions must be an object")
    require(absurd_assertions.get("provider_delay_not_trusted_unbounded") is True, "Retry-After must not grant unbounded scheduling authority")
    require(absurd_assertions.get("retry_budget_bounded") is True, "retry budget must remain bounded")

    missing_cache = by_id(cases, "TS-016")
    missing_cache_assertions = missing_cache["assertions"]
    require(isinstance(missing_cache_assertions, dict), "304 assertions must be an object")
    require(missing_cache.get("expected") == "FAIL_CLOSED", "304 without cached entity must fail closed")
    require(missing_cache_assertions.get("invent_content_from_304") is False, "304 must never manufacture missing content")

    stale_validator = by_id(cases, "TS-017")
    stale_assertions = stale_validator["assertions"]
    require(isinstance(stale_assertions, dict), "validator assertions must be an object")
    require(stale_assertions.get("validator_inconsistency_detected") is True, "same validator with changed bytes must be visible")

    recovery = by_id(cases, "TS-018")
    recovery_assertions = recovery["assertions"]
    require(isinstance(recovery_assertions, dict), "recovery assertions must be an object")
    require(recovery_assertions.get("recovered_after_gap") is True, "recovery backlog must carry gap context")
    require(recovery_assertions.get("delivery_burst_is_not_world_burst") is True, "delivery burst must not equal world-event burst")
    require(recovery_assertions.get("live_breakout_due_only_to_recovery") is False, "recovery alone must not manufacture a live breakout")

    return cases


def main() -> None:
    acquisition_cases = validate_acquisition_corpus()
    transport_cases = validate_transport_pack()
    all_ids = [str(case["id"]) for case in acquisition_cases + transport_cases]
    require(len(all_ids) == len(set(all_ids)), "fixture case ids must be unique across all packs")
    print(
        "validated "
        f"{len(acquisition_cases)} hostile acquisition fixtures + "
        f"{len(transport_cases)} transport/security fixtures"
    )


if __name__ == "__main__":
    main()
