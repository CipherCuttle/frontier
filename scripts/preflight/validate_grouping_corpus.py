from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

CORPUS = Path("fixtures/grouping/corpus_v0.json")
LABELS = {"GROUP", "NO_GROUP", "AMBIGUOUS"}
REQUIRED_CATEGORIES = {
    "hn_attention_duplicate",
    "shared_catalog_false_merge",
    "same_url_revision",
    "same_url_reuse_far",
    "equal_content_mirror",
    "exact_title_cross_source",
    "punctuation_sensitive_alias",
    "weak_paraphrase",
    "pypi_version_split",
    "hf_version_split",
    "generic_title_collision",
    "unicode_nfc",
    "unicode_confusable",
    "timestamp_conflict",
    "same_source_distinct_items",
    "near_high_overlap",
    "far_same_title",
    "attention_to_shared_catalog",
    "same_external_root_discovery",
    "similar_title_non_equivalence",
    "same_item_changed_content",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def parse_time(value: object, *, case_id: str, side: str) -> datetime:
    require(
        isinstance(value, str) and value.endswith("Z"),
        f"{case_id} {side} observed_at must be UTC Z",
    )
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    require(parsed.utcoffset() is not None, f"{case_id} {side} observed_at must be aware")
    return parsed


def validate_input(value: object, *, case_id: str, side: str) -> None:
    require(isinstance(value, dict), f"{case_id} {side} must be an object")
    for field in ("source_id", "source_item_key"):
        require(
            isinstance(value.get(field), str) and bool(value.get(field)),
            f"{case_id} {side} missing {field}",
        )
    kind = value.get("kind", "DOCUMENT")
    require(kind in {"DOCUMENT", "ARTIFACT", "METRIC"}, f"{case_id} {side} invalid kind")
    parse_time(value.get("observed_at"), case_id=case_id, side=side)
    roles = value.get("signal_roles", [])
    require(
        isinstance(roles, list) and all(isinstance(role, str) and role for role in roles),
        f"{case_id} {side} signal_roles must be strings",
    )
    if kind == "ARTIFACT":
        require(
            isinstance(value.get("artifact_name"), str) and bool(value.get("artifact_name")),
            f"{case_id} {side} artifact requires artifact_name",
        )
        require(
            isinstance(value.get("artifact_version"), str) and bool(value.get("artifact_version")),
            f"{case_id} {side} artifact requires artifact_version",
        )


def by_id(cases: list[dict[str, object]], case_id: str) -> dict[str, object]:
    matches = [case for case in cases if case.get("id") == case_id]
    require(len(matches) == 1, f"expected exactly one {case_id}")
    return matches[0]


def main() -> None:
    document = json.loads(CORPUS.read_text(encoding="utf-8"))
    require(
        document.get("schema_version") == "frontier-grouping-corpus-v0",
        "unexpected grouping corpus schema_version",
    )
    authority = document.get("authority")
    require(isinstance(authority, dict), "grouping authority must be an object")
    require(
        authority.get("runtime_selection_authorized") is False,
        "frozen corpus must not pre-authorize a runtime algorithm",
    )
    require(authority.get("minimum_pair_precision") == "1.000000", "V0 precision gate changed")
    require(authority.get("minimum_group_recall") == "0.800000", "V0 recall gate changed")
    require(
        authority.get("candidate_families")
        == [
            "canonical-url-v0",
            "exact-text-v0",
            "normalized-title-v0",
            "token-jaccard-v0",
            "simhash-v0",
            "minhash-v0",
            "tfidf-v0",
            "guarded-hybrid-v0",
        ],
        "candidate family authority changed",
    )

    cases_value = document.get("cases")
    require(isinstance(cases_value, list), "grouping cases must be a list")
    require(len(cases_value) >= 20, "grouping corpus unexpectedly shrank below 20 cases")

    ids: list[str] = []
    categories: set[str] = set()
    cases: list[dict[str, object]] = []
    for index, raw_case in enumerate(cases_value):
        require(isinstance(raw_case, dict), f"case {index} must be an object")
        case = raw_case
        case_id = case.get("id")
        category = case.get("category")
        expected = case.get("expected")
        require(isinstance(case_id, str) and case_id, f"case {index} missing id")
        require(isinstance(category, str) and category, f"{case_id} missing category")
        require(expected in LABELS, f"{case_id} has invalid expected label {expected!r}")
        require(
            isinstance(case.get("rationale"), str) and bool(case.get("rationale")),
            f"{case_id} missing rationale",
        )
        validate_input(case.get("left"), case_id=case_id, side="left")
        validate_input(case.get("right"), case_id=case_id, side="right")
        ids.append(case_id)
        categories.add(category)
        cases.append(case)

    require(len(ids) == len(set(ids)), "grouping fixture ids must be unique")
    require(
        REQUIRED_CATEGORIES <= categories,
        f"missing grouping categories: {sorted(REQUIRED_CATEGORIES - categories)}",
    )
    require(by_id(cases, "GRP-001").get("expected") == "GROUP", "HN duplicate authority changed")
    require(
        by_id(cases, "GRP-002").get("expected") == "NO_GROUP",
        "shared catalog false-merge guard changed",
    )
    require(
        by_id(cases, "GRP-007").get("expected") == "AMBIGUOUS",
        "punctuation-sensitive alias must remain reversible",
    )
    require(
        by_id(cases, "GRP-018").get("expected") == "AMBIGUOUS",
        "attention-to-shared-catalog case must not force a merge",
    )
    print(f"validated {len(cases)} frozen grouping pair cases across {len(categories)} categories")


if __name__ == "__main__":
    main()
