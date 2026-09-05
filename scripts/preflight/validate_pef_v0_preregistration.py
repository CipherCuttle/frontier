from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from frontier.domain.canonical_json import canonical_json_bytes
from frontier.domain.digests import sha256_digest

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "experiments" / "advanced_intelligence" / "pef_v0" / "preregistration.json"
AUTHORITY_COMMIT = "1d38caf9a74ef278a6c4418bf6298aec6bb50c66"
CONFIG_DIGEST = "sha256:4b1f7987e83933cd0586e33aebf514e8adffa7f03e576bce308152ed2eaf90e2"
RANKING_ORDER = [
    "has_prospective_primary_emission_desc",
    "has_any_prospective_evidence_desc",
    "prospective_age_seconds_asc_null_last",
    "velocity_6h_delta_desc",
    "mentions_1h_desc",
    "mentions_6h_desc",
    "acceleration_6h_desc",
    "mentions_24h_desc",
    "prospective_source_role_diversity_desc",
    "prospective_evidence_count_desc",
    "episode_id_asc",
]
REQUIRED_SOURCES = [
    "cisa.kev",
    "gdelt.frontier",
    "hf.models",
    "hn.frontpage",
    "pypi.updates",
]
DOMAIN_ANCHORS = {
    "AI_MODELS": "hf.models",
    "SECURITY_VULNERABILITIES": "cisa.kev",
    "SOFTWARE_PACKAGES": "pypi.updates",
}


def fail(message: str) -> int:
    print(f"pef-v0-preregistration: FAIL: {message}")
    return 1


def require_dict(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return cast(dict[str, Any], value)


def main() -> int:
    try:
        document = require_dict(json.loads(PREREG.read_text(encoding="utf-8")), "document")
        if document.get("schema_version") != "advanced-ranking-preregistration-v0":
            return fail("unexpected schema_version")

        authority = require_dict(document.get("authority"), "authority")
        if authority != {
            "document": "docs/ADVANCED_INTELLIGENCE_EXPERIMENTS.md",
            "authority_commit": AUTHORITY_COMMIT,
        }:
            return fail("authority binding drifted")
        if document.get("experiment_id") != "advanced-ranking-pef-v0":
            return fail("unexpected experiment_id")
        if document.get("implementation_authorized_by_this_preregistration_pr") is not False:
            return fail("preregistration must not authorize implementation")

        candidate = require_dict(document.get("candidate"), "candidate")
        if candidate.get("candidate_id") != "prospective-primary-emission-freshness-v0":
            return fail("unexpected candidate_id")
        if candidate.get("algorithm_version") != "prospective-primary-emission-freshness-lexicographic-v0":
            return fail("unexpected candidate algorithm_version")
        if candidate.get("deterministic") is not True:
            return fail("candidate must remain deterministic")
        if candidate.get("implementation_status") != "NOT_IMPLEMENTED_PREREGISTRATION_ONLY":
            return fail("preregistration implementation status drifted")
        if candidate.get("authority_state_before_promotion") != "EXPERIMENTAL_SHADOW":
            return fail("candidate shadow authority drifted")

        configuration = require_dict(candidate.get("configuration"), "candidate.configuration")
        calculated_digest = str(sha256_digest(canonical_json_bytes(configuration)))
        if calculated_digest != CONFIG_DIGEST or candidate.get("configuration_digest") != CONFIG_DIGEST:
            return fail("candidate configuration digest drifted")
        if configuration.get("ranking_order") != RANKING_ORDER:
            return fail("candidate ranking order drifted")
        if configuration.get("score_semantics") != "NO_SCALAR_SCORE_LEXICOGRAPHIC_RANK_ONLY":
            return fail("candidate score semantics drifted")
        eligibility = require_dict(configuration.get("activity_eligibility"), "activity_eligibility")
        if eligibility != {
            "eligible_reasons": ["ACTIVE_ENRICHMENT", "DISCOVERY", "SCHEDULED"],
            "exclude_backfill": True,
            "exclude_recovered_after_gap": True,
        }:
            return fail("candidate activity eligibility drifted")

        control = require_dict(document.get("control"), "control")
        if control != {
            "projection_name": "baseline-intelligence",
            "projection_version": "baseline-intelligence-v0",
            "algorithm_version": "windowed-episode-metrics-v0",
            "ranking_policy_version": "naive-episode-activity-v0",
        }:
            return fail("control identity drifted")

        evaluation = require_dict(document.get("evaluation"), "evaluation")
        if evaluation.get("global_rank_cutoff_k") != 100:
            return fail("global K drifted")

        schedule = require_dict(evaluation.get("snapshot_schedule"), "snapshot_schedule")
        expected_schedule = {
            "cadence_seconds": 300,
            "alignment": "UTC_UNIX_EPOCH_MULTIPLE_OF_300_SECONDS",
            "start": "first aligned boundary strictly after durable candidate-freeze receipt on main",
            "ranking_window_seconds": 2419200,
            "ranking_window_interval": "[start,start+2419200)",
            "label_maturation_seconds_after_window": 86400,
            "no_early_stopping": True,
            "no_window_extension_for_sample_size": True,
        }
        if schedule != expected_schedule:
            return fail("snapshot schedule drifted")

        paired = require_dict(evaluation.get("paired_snapshot_integrity"), "paired_snapshot_integrity")
        if paired != {
            "candidate_and_control_same_as_of": True,
            "candidate_must_reference_exact_control_snapshot_id_and_receipt_id": True,
            "baseline_complete_boundary_floor_bps": 9500,
            "max_candidate_failed_or_missing_artifacts_when_control_complete": 0,
            "missing_expected_boundaries_cannot_shift_start_or_end": True,
        }:
            return fail("paired snapshot integrity drifted")

        registry = require_dict(evaluation.get("source_registry"), "source_registry")
        if registry.get("required_enabled_source_ids") != REQUIRED_SOURCES:
            return fail("required source set drifted")
        if registry.get("freeze_exact_registry_version_in_candidate_freeze") is not True:
            return fail("source registry must be frozen in candidate freeze")
        if registry.get("registry_change_during_confirmatory_window") != "INVALIDATE_AND_RESTART":
            return fail("source-registry change policy drifted")

        domains = require_dict(evaluation.get("domain_mapping"), "domain_mapping")
        for domain, source_id in DOMAIN_ANCHORS.items():
            mapping = require_dict(domains.get(domain), domain)
            if mapping.get("anchor_source_id") != source_id:
                return fail(f"{domain} anchor source drifted")
        if domains.get("minimum_qualifying_domains") != 2:
            return fail("minimum domain count drifted")
        if domains.get("promotion_rule") != "EVERY_DOMAIN_MEETING_SAMPLE_ADEQUACY_MUST_PASS;_AT_LEAST_TWO_MUST_MEET_SAMPLE_ADEQUACY":
            return fail("domain promotion rule drifted")

        opportunity = require_dict(evaluation.get("opportunity"), "opportunity")
        if opportunity.get("stable_anchor_identity") != "observation_id":
            return fail("opportunity anchor identity drifted")
        if opportunity.get("each_retained_anchor_counts_once") is not True:
            return fail("opportunity unit drifted")

        outcome = require_dict(evaluation.get("outcome_label"), "outcome_label")
        if outcome.get("name") != "FOLLOW_ON_ATTENTION_OR_DISCOVERY_WITHIN_24H":
            return fail("outcome label drifted")
        if outcome.get("model_independent") is not True:
            return fail("outcome must remain model-independent")
        if outcome.get("adjudication") != "AUTOMATED_DETERMINISTIC_NO_HUMAN_ADJUDICATION":
            return fail("outcome adjudication drifted")
        if outcome.get("candidate_or_control_outputs_may_define_label") is not False:
            return fail("model output cannot define outcome")
        if outcome.get("positive_remains_positive_under_degraded_coverage") is not True:
            return fail("observed positive evidence must remain positive")

        precision = require_dict(evaluation.get("precision"), "precision")
        if precision.get("point_floor") != "candidate_precision >= control_precision in every adequately sampled domain":
            return fail("precision point floor drifted")
        if precision.get("newcombe_z") != "1.959963984540054":
            return fail("precision z value drifted")
        if precision.get("noninferiority_margin") != "0.10":
            return fail("precision noninferiority margin drifted")

        lead_time = require_dict(evaluation.get("lead_time"), "lead_time")
        if lead_time.get("domain_floor") != "median lead_time_advantage_seconds > 0":
            return fail("domain lead-time floor drifted")
        if lead_time.get("pooled_floor") != "pooled median lead_time_advantage_seconds > 0":
            return fail("pooled lead-time floor drifted")
        if lead_time.get("no_dropped_misses") is not True:
            return fail("lead-time misses cannot be dropped")

        adequacy = require_dict(evaluation.get("sample_adequacy"), "sample_adequacy")
        if adequacy != {
            "min_resolved_opportunities_per_domain": 30,
            "min_positive_opportunities_per_domain": 10,
            "min_surfaced_resolved_opportunities_per_arm_per_domain": 20,
            "min_resolved_label_fraction_bps_per_domain": 9000,
            "underpowered_domain": "NOT_QUALIFYING; retained and reported; cannot be selected as a promotion domain",
            "fewer_than_two_adequately_sampled_domains": "INCONCLUSIVE_NO_PROMOTION",
        }:
            return fail("sample adequacy contract drifted")

        multiplicity = require_dict(evaluation.get("multiplicity"), "multiplicity")
        if multiplicity.get("policy") != "SINGLE_CONFIRMATORY_CANDIDATE":
            return fail("multiplicity policy drifted")
        if multiplicity.get("interim_outcome_based_early_stop") is not False:
            return fail("interim outcome stopping must remain forbidden")

        freeze = require_dict(document.get("candidate_freeze_requirements"), "candidate_freeze_requirements")
        if freeze != {
            "after_implementation_and_test": True,
            "before_first_confirmatory_boundary": True,
            "bind_reviewed_preregistration_commit": True,
            "bind_exact_implementation_commit_and_tree": True,
            "bind_dependency_lock_digest": True,
            "bind_build_artifact_digest_when_applicable": True,
            "bind_source_registry_version": True,
            "any_bound_identity_change": "NEW_FREEZE_AND_RESTART",
        }:
            return fail("candidate-freeze requirements drifted")
    except (KeyError, TypeError, ValueError) as exc:
        return fail(str(exc))

    print("pef-v0-preregistration: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
