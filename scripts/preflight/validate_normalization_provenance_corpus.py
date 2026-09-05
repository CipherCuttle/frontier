from __future__ import annotations

import json
from pathlib import Path

CORPUS = Path("fixtures/acquisition/normalization_provenance_v0.json")
ALLOWED_OUTCOMES = {"ACCEPT", "REJECT", "DEGRADE", "QUARANTINE", "RETRY_LATER", "FAIL_CLOSED"}
REQUIRED_CATEGORIES = {
    "url_alias",
    "url_syntax",
    "source_impersonation",
    "mirror",
    "syndication",
    "provenance_ambiguity",
    "content_revision",
    "correction_chain",
    "retraction_chain",
    "timestamp_conflict",
    "same_url_changed_bytes",
    "discovery_lineage",
    "ambiguous_ancestry",
    "entity_confusable",
    "unicode_normalization",
    "over_normalization",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def by_id(cases: list[dict[str, object]], case_id: str) -> dict[str, object]:
    matches = [case for case in cases if case.get("id") == case_id]
    require(len(matches) == 1, f"expected exactly one {case_id}")
    return matches[0]


def assertions(case: dict[str, object]) -> dict[str, object]:
    value = case.get("assertions")
    require(isinstance(value, dict), f"{case.get('id')} assertions must be an object")
    return value


def main() -> None:
    document = json.loads(CORPUS.read_text(encoding="utf-8"))
    require(
        document.get("schema_version") == "frontier-normalization-provenance-corpus-v0",
        "unexpected normalization/provenance corpus schema_version",
    )
    authority = document.get("authority")
    require(isinstance(authority, dict), "authority must be an object")
    require(
        authority.get("runtime_implementation_authorized") is False,
        "normalization preflight must not authorize runtime implementation",
    )

    cases = document.get("cases")
    require(isinstance(cases, list), "cases must be a list")
    require(len(cases) >= 20, "normalization/provenance corpus unexpectedly shrank below 20 cases")

    ids: list[str] = []
    categories: set[str] = set()
    for index, case in enumerate(cases):
        require(isinstance(case, dict), f"case {index} must be an object")
        case_id = case.get("id")
        category = case.get("category")
        outcome = case.get("expected")
        require(isinstance(case_id, str) and case_id, f"case {index} missing id")
        require(isinstance(category, str) and category, f"{case_id} missing category")
        require(outcome in ALLOWED_OUTCOMES, f"{case_id} has invalid outcome {outcome!r}")
        require(bool(assertions(case)), f"{case_id} must have non-empty assertions")
        ids.append(case_id)
        categories.add(category)

    require(len(ids) == len(set(ids)), "normalization/provenance fixture ids must be unique")
    require(
        REQUIRED_CATEGORIES <= categories,
        f"missing normalization/provenance categories: {sorted(REQUIRED_CATEGORIES - categories)}",
    )

    tracking = assertions(by_id(cases, "NORM-001"))
    require(tracking.get("canonical_url_count") == 1, "tracking aliases should collapse only under source policy")
    require(tracking.get("normalization_requires_source_policy") is True, "tracking stripping must remain policy-bound")

    semantic_query = assertions(by_id(cases, "NORM-002"))
    require(semantic_query.get("canonical_url_count") == 2, "semantic query parameters must not be over-normalized")

    source_confusable = assertions(by_id(cases, "NORM-006"))
    require(source_confusable.get("same_source_identity") is False, "visual confusable must not inherit source identity")
    require(source_confusable.get("authority_must_not_inherit_from_visual_similarity") is True, "confusable source authority invariant lost")

    mirror = assertions(by_id(cases, "NORM-008"))
    require(mirror.get("identical_content_does_not_prove_common_origin") is True, "digest equality must not prove provenance")

    syndication = assertions(by_id(cases, "NORM-009"))
    require(syndication.get("independent_factual_roots_max") == 1, "syndication must not manufacture factual roots")

    unknown_origin = assertions(by_id(cases, "NORM-010"))
    require(unknown_origin.get("provenance_status") == "UNKNOWN", "same-content ambiguous provenance must stay UNKNOWN")
    require(unknown_origin.get("earliest_observed_must_not_be_promoted_to_proven_root") is True, "earliest observed is not proven root")

    revision = assertions(by_id(cases, "NORM-011"))
    require(revision.get("observation_count") == 2, "changed canonical content must create a second observation")
    require(revision.get("first_observation_mutated") is False, "revisions must not mutate prior observations")

    correction = assertions(by_id(cases, "NORM-012"))
    require(correction.get("current_assertion_tip") == "C", "correction-chain tip invariant changed")
    require(correction.get("historical_observations_retained") == 3, "correction history must remain append-only")

    retraction = assertions(by_id(cases, "NORM-013"))
    require(retraction.get("physical_delete_allowed") is False, "retraction must not delete canonical history")
    require(retraction.get("trend_attention_may_remain_nonzero") is True, "retraction must remain orthogonal to trend attention")

    timestamp = assertions(by_id(cases, "NORM-014"))
    require(timestamp.get("source_timestamp_does_not_reorder_FRONTIER_knowledge") is True, "source timestamp must not rewrite knowledge order")

    same_url = assertions(by_id(cases, "NORM-015"))
    require(same_url.get("observation_count") == 2, "same URL with changed bytes must permit two observations")
    require(same_url.get("provenance_relation_without_explicit_source_signal") == "UNKNOWN", "same URL revisions must not invent provenance relation")

    discovery = assertions(by_id(cases, "NORM-016"))
    require(discovery.get("discovery_source_not_promoted_to_primary") is True, "discovery surface must not become primary authority")

    ancestry = assertions(by_id(cases, "NORM-017"))
    require(ancestry.get("proven_root_id") is None, "ambiguous ancestry must not invent a proven root")
    require(ancestry.get("similarity_alone_cannot_create_explicit_provenance") is True, "similarity cannot create explicit provenance")

    entity_confusable = assertions(by_id(cases, "NORM-018"))
    require(entity_confusable.get("automatic_entity_merge") is False, "Unicode confusables must not auto-merge entities")

    unicode_case = assertions(by_id(cases, "NORM-019"))
    require(unicode_case.get("canonical_text_form") == "NFC", "canonical text normalization must remain NFC")
    require(unicode_case.get("canonical_serialization_equal") is True, "canonically equivalent Unicode must serialize equally")

    over_normalization = assertions(by_id(cases, "NORM-020"))
    require(over_normalization.get("automatic_entity_merge") is False, "fuzzy similarity must not auto-merge entities")
    require(over_normalization.get("fuzzy_similarity_must_not_rewrite_canonical_identity") is True, "fuzzy similarity must remain derived evidence")

    print(f"validated {len(cases)} normalization/provenance fixtures across {len(categories)} categories")


if __name__ == "__main__":
    main()
