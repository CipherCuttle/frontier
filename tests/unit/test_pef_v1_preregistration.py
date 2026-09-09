from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from frontier.domain.canonical_json import canonical_json_bytes


PEF_V0_PATH = Path("experiments/advanced_intelligence/pef_v0/preregistration.json")
PEF_V1_PATH = Path("experiments/advanced_intelligence/pef_v1/preregistration.json")
PEF_V0_BLOB = "0ce6320854634b8cd7228361b127e26f9dd0600c"
PEF_V1_CONFIGURATION_DIGEST = (
    "sha256:db2305ee0d89ee56b4c0a2837fd7034dad899ec5fc41acc710358b434a52fd67"
)

EXPECTED_OVERRIDE_POINTERS = (
    "/experiment_id",
    "/candidate/candidate_id",
    "/candidate/configuration/grouping_contract",
    "/candidate/configuration_digest",
    "/evaluation/multiplicity/family_id",
)


def _git_blob_sha(path: Path) -> str:
    payload = path.read_bytes()
    framed = b"blob " + str(len(payload)).encode("ascii") + b"\0" + payload
    return hashlib.sha1(framed).hexdigest()  # noqa: S324 - Git object identity is SHA-1 by contract.


def _apply_json_pointer(document: dict[str, Any], pointer: str, value: Any) -> None:
    assert pointer.startswith("/")
    parts = [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]
    current: Any = document
    for part in parts[:-1]:
        assert isinstance(current, dict)
        current = current[part]
    assert isinstance(current, dict)
    current[parts[-1]] = value


def test_pef_v1_is_exact_successor_delta_over_immutable_pef_v0() -> None:
    predecessor = json.loads(PEF_V0_PATH.read_text(encoding="utf-8"))
    successor = json.loads(PEF_V1_PATH.read_text(encoding="utf-8"))

    assert _git_blob_sha(PEF_V0_PATH) == PEF_V0_BLOB
    assert successor["predecessor"] == {
        "experiment_id": "advanced-ranking-pef-v0",
        "preregistration_path": str(PEF_V0_PATH),
        "preregistration_blob_sha": PEF_V0_BLOB,
        "canonical_parent_commit": "8ff19dbf5b27c639b9d7df28d844672b25016196",
        "inheritance_semantics": (
            "DEEP_COPY_PREDECESSOR_THEN_APPLY_ONLY_FROZEN_JSON_POINTER_OVERRIDES"
        ),
    }

    overrides = successor["frozen_overrides"]
    assert tuple(item["json_pointer"] for item in overrides) == EXPECTED_OVERRIDE_POINTERS

    expanded = copy.deepcopy(predecessor)
    for override in overrides:
        _apply_json_pointer(expanded, override["json_pointer"], override["value"])

    assert expanded["experiment_id"] == "advanced-ranking-pef-v1"
    assert expanded["candidate"]["candidate_id"] == "prospective-primary-emission-freshness-v1"

    # Ranking hypothesis and evaluation semantics remain exactly PEF_V0 except for the
    # separately named multiplicity family required by the successor experiment identity.
    assert (
        expanded["candidate"]["algorithm_version"] == predecessor["candidate"]["algorithm_version"]
    )
    assert expanded["feature_contract"] == predecessor["feature_contract"]
    assert expanded["control"] == predecessor["control"]

    expected_evaluation = copy.deepcopy(predecessor["evaluation"])
    expected_evaluation["multiplicity"]["family_id"] = (
        "advanced-ranking-v1-pef-single-candidate-family"
    )
    assert expanded["evaluation"] == expected_evaluation

    candidate_configuration = expanded["candidate"]["configuration"]
    assert (
        candidate_configuration["algorithm_version"]
        == (predecessor["candidate"]["configuration"]["algorithm_version"])
    )
    assert (
        candidate_configuration["ranking_order"]
        == (predecessor["candidate"]["configuration"]["ranking_order"])
    )
    assert (
        candidate_configuration["feature_definitions"]
        == (predecessor["candidate"]["configuration"]["feature_definitions"])
    )
    assert candidate_configuration["grouping_contract"] == (
        "candidate and control use the exact grouping-scalable-v1 projection at each as_of; "
        "candidate never regroups observations; grouping identity is bound by this successor "
        "preregistration"
    )
    computed_configuration_digest = (
        "sha256:" + hashlib.sha256(canonical_json_bytes(candidate_configuration)).hexdigest()
    )
    assert computed_configuration_digest == PEF_V1_CONFIGURATION_DIGEST
    assert expanded["candidate"]["configuration_digest"] == PEF_V1_CONFIGURATION_DIGEST


def test_pef_v1_binds_exact_canonical_grouping_v1_and_isolates_pef_v0_evidence() -> None:
    successor = json.loads(PEF_V1_PATH.read_text(encoding="utf-8"))

    assert successor["grouping_binding"] == {
        "canonical_publication_commit": "8ff19dbf5b27c639b9d7df28d844672b25016196",
        "canonical_publication_tree": "47793421f47dbb00f5028867a84a4ed0e0f86939",
        "source_path": "src/frontier/domain/grouping_v1.py",
        "source_blob": "5c3b7d57e5bf6ef8d6fb9d0c2dd4fa79bbd52252",
        "projection_name": "episode-grouping",
        "projection_version": "grouping-scalable-v1",
        "schema_version": "grouping-projection-v1",
        "algorithm_version": "guarded-hybrid-group-complete-blocking-v1",
        "configuration_digest": (
            "sha256:57dce4c0ca86ce6fbf3c2dbabf6fd1413f0fef254a4873622dd59e3573177ab2"
        ),
        "pair_semantics_version": ("guarded-hybrid-v0@db206cda7eed92b62c706a10089c2571b4381d66"),
        "pair_oracle_blob": "943affde20b08f500f8dba2716ffedfc428f58e1",
        "omitted_pair_semantics": "OMITTED_PAIRS_HAVE_NO_NEGATIVE_OR_INDEPENDENCE_MEANING",
    }

    assert successor["evidence_isolation"] == {
        "predecessor_status": "ABORTED_BY_OPERATIONAL_SCALABILITY_FAILURE",
        "predecessor_abort_record_path": "docs/PEF_V0_CONFIRMATORY_ABORT_2026-09-08.md",
        "retained_predecessor_confirmatory_boundaries": 11,
        "pool_predecessor_evidence": "FORBIDDEN",
        "backfill_missed_predecessor_boundaries": "FORBIDDEN",
        "shift_or_extend_predecessor_window": "FORBIDDEN",
        "successor_confirmatory_window": (
            "FRESH_ONLY_AFTER_SUCCESSOR_DURABLE_CANDIDATE_FREEZE_PUBLICATION"
        ),
    }

    assert successor["scientific_change_scope"] == {
        "ranking_algorithm_changed": False,
        "candidate_feature_definitions_changed": False,
        "ranking_order_changed": False,
        "global_k_changed": False,
        "outcome_label_changed": False,
        "domain_mapping_changed": False,
        "precision_rule_changed": False,
        "lead_time_rule_changed": False,
        "sample_adequacy_changed": False,
        "source_registry_changed": False,
        "grouping_input_authority_changed": True,
        "change_summary": (
            "PEF_V1 repeats the PEF_V0 ranking hypothesis on the canonical scalable grouping V1 "
            "universe; the predecessor confirmatory run is retained as aborted incident evidence only."
        ),
    }

    assert successor["implementation_authorized_by_this_preregistration_pr"] is False
    assert successor["candidate_freeze_authorized_by_this_preregistration_pr"] is False
    assert successor["confirmatory_execution_authorized_by_this_preregistration_pr"] is False
