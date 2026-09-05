from __future__ import annotations

import json
from pathlib import Path

CORPUS = Path("fixtures/acquisition/corpus_v0.json")
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


def main() -> None:
    document = json.loads(CORPUS.read_text(encoding="utf-8"))
    require(
        document.get("schema_version") == "frontier-hostile-acquisition-corpus-v0",
        "unexpected corpus schema_version",
    )
    authority = document.get("authority")
    require(isinstance(authority, dict), "authority must be an object")
    require(authority.get("runtime_implementation_authorized") is False, "fixture preflight must not authorize runtime implementation")

    cases = document.get("cases")
    require(isinstance(cases, list), "cases must be a list")
    require(len(cases) >= 18, "hostile corpus unexpectedly shrank below 18 cases")

    ids: list[str] = []
    sources: set[str] = set()
    for index, case in enumerate(cases):
        require(isinstance(case, dict), f"case {index} must be an object")
        case_id = case.get("id")
        source_id = case.get("source_id")
        outcome = case.get("expected")
        assertions = case.get("assertions")
        require(isinstance(case_id, str) and case_id, f"case {index} missing id")
        require(isinstance(source_id, str) and source_id, f"{case_id} missing source_id")
        require(outcome in ALLOWED_OUTCOMES, f"{case_id} has invalid outcome {outcome!r}")
        require(isinstance(assertions, dict) and assertions, f"{case_id} must have non-empty assertions")
        ids.append(case_id)
        sources.add(source_id)

    require(len(ids) == len(set(ids)), "fixture case ids must be unique")
    require(REQUIRED_SOURCES <= sources, f"missing source lanes: {sorted(REQUIRED_SOURCES - sources)}")

    xxe = by_id(cases, "PYPI-004")
    require(xxe.get("expected") == "REJECT", "XXE fixture must remain REJECT")
    require("<!ENTITY" in str(xxe.get("payload")), "XXE fixture lost entity payload")
    xxe_assertions = xxe["assertions"]
    require(xxe_assertions.get("external_entity_resolutions") == 0, "XXE fixture must permit zero entity resolution")
    require(xxe_assertions.get("network_side_effects") == 0, "XXE fixture must permit zero network side effects")

    redirect = by_id(cases, "HTTP-001")
    require(redirect.get("expected") == "REJECT", "private-IP redirect must remain REJECT")
    require(redirect["assertions"].get("forbidden_connections") == 0, "private-IP redirect must never connect")

    window_gap = by_id(cases, "PYPI-005")
    require(window_gap.get("expected") == "DEGRADE", "finite feed-window gap must degrade completeness")
    require(window_gap["assertions"].get("transport_health") == "OK", "finite feed-window fixture must prove transport can stay healthy")
    require(window_gap["assertions"].get("completeness_health") == "DEGRADED", "finite feed-window fixture must degrade completeness")

    backfill = by_id(cases, "CISA-005")
    require(backfill["assertions"].get("live_alert_eligible") is False, "backfill must not become a live alert solely because it was ingested now")

    hn = by_id(cases, "HN-001")
    require(hn["assertions"].get("attention_observations") == 2, "HN duplicate-root fixture must preserve two attention observations")
    require(hn["assertions"].get("external_factual_roots_max") == 1, "HN duplicate-root fixture must not manufacture corroboration")

    gdelt = by_id(cases, "GDELT-001")
    require(gdelt["assertions"].get("discovery_rows") == 6, "GDELT syndication fixture must preserve discovery propagation")
    require(gdelt["assertions"].get("independent_factual_roots_max") == 1, "GDELT syndication fixture must not manufacture six roots")

    malformed_time = by_id(cases, "GDELT-002")
    require(malformed_time["assertions"].get("default_malformed_time_to_now") is False, "malformed source times must never silently become now")

    print(f"validated {len(cases)} hostile acquisition fixtures across {len(sources)} source lanes")


if __name__ == "__main__":
    main()
