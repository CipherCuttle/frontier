from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from frontier.application.value_observatory_executor_readiness import (
    BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS,
)
from frontier.application.value_observatory_ordinary_snapshot_evidence import (
    BENCHMARK_ORDINARY_SNAPSHOT_ARTIFACT_REPOSITORY,
    OrdinarySnapshotEvidenceBlockerCode,
    OrdinarySnapshotEvidenceBundle,
    OrdinarySnapshotEvidenceVerdict,
    OrdinarySnapshotPayloadClaim,
    OrdinarySnapshotReceiptClaim,
    OrdinarySnapshotSourceClaim,
    assess_ordinary_snapshot_evidence_v0,
    ordinary_snapshot_payload_digest_v0,
)
from frontier.domain.digests import Digest

_HORIZON = datetime(2026, 9, 15, 0, 0, tzinfo=UTC)


def _digest(character: str) -> Digest:
    return Digest("sha256:" + character * 64)


def _source(source_id: str) -> OrdinarySnapshotSourceClaim:
    return OrdinarySnapshotSourceClaim(
        source_id=source_id,
        knowledge_horizon=_HORIZON,
        retrieval_completed_at=_HORIZON - timedelta(seconds=20),
        source_contract_digest=_digest("1"),
        request_identity_digest=_digest("2"),
        raw_payload_digest=_digest("3"),
        normalized_collection_digest=_digest("4"),
    )


def _payload() -> OrdinarySnapshotPayloadClaim:
    return OrdinarySnapshotPayloadClaim(
        snapshot_id="ordinary-snapshot-20260915T000000Z",
        knowledge_horizon=_HORIZON,
        benchmark_protocol_digest=_digest("7"),
        source_registry_version=_digest("8"),
        sources=tuple(
            _source(source_id) for source_id in sorted(BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS)
        ),
    )


def _receipt(payload: OrdinarySnapshotPayloadClaim) -> OrdinarySnapshotReceiptClaim:
    return OrdinarySnapshotReceiptClaim(
        repository_full_name=BENCHMARK_ORDINARY_SNAPSHOT_ARTIFACT_REPOSITORY,
        artifact_id=101,
        artifact_digest=_digest("5"),
        artifact_created_at=_HORIZON - timedelta(seconds=10),
        workflow_run_id=202,
        workflow_head_sha="a" * 40,
        snapshot_payload_digest=ordinary_snapshot_payload_digest_v0(payload),
        attestation_ref="sigstore:example-bundle",
        attestation_digest=_digest("6"),
    )


def _bundle() -> OrdinarySnapshotEvidenceBundle:
    payload = _payload()
    return OrdinarySnapshotEvidenceBundle(payload=payload, receipt=_receipt(payload))


def _with_payload(
    bundle: OrdinarySnapshotEvidenceBundle,
    payload: OrdinarySnapshotPayloadClaim,
) -> OrdinarySnapshotEvidenceBundle:
    receipt = replace(
        bundle.receipt,
        snapshot_payload_digest=ordinary_snapshot_payload_digest_v0(payload),
    )
    return OrdinarySnapshotEvidenceBundle(payload=payload, receipt=receipt)


def test_complete_claim_remains_pending_external_authority() -> None:
    assessment = assess_ordinary_snapshot_evidence_v0(_bundle())

    assert assessment.verdict is OrdinarySnapshotEvidenceVerdict.EVIDENCE_COMPLETE_PENDING_AUTHORITY
    assert assessment.source_ids == tuple(sorted(BENCHMARK_CAPTURE_V0_ORDINARY_SOURCE_IDS))
    assert assessment.blockers == ()


def test_payload_digest_is_canonical_across_source_tuple_order() -> None:
    payload = _payload()
    reordered = replace(payload, sources=tuple(reversed(payload.sources)))

    assert ordinary_snapshot_payload_digest_v0(payload) == ordinary_snapshot_payload_digest_v0(
        reordered
    )


def test_receipt_must_bind_exact_canonical_payload_digest() -> None:
    bundle = _bundle()
    changed_receipt = replace(bundle.receipt, snapshot_payload_digest=_digest("9"))

    with pytest.raises(ValueError, match="receipt payload digest mismatch"):
        assess_ordinary_snapshot_evidence_v0(replace(bundle, receipt=changed_receipt))


def test_gate_rejects_missing_extra_and_duplicate_source_claims() -> None:
    bundle = _bundle()

    with pytest.raises(ValueError, match="source set mismatch"):
        assess_ordinary_snapshot_evidence_v0(
            replace(bundle, payload=replace(bundle.payload, sources=bundle.payload.sources[:-1]))
        )

    extra = replace(bundle.payload.sources[0], source_id="not.frozen")
    with pytest.raises(ValueError, match="source set mismatch"):
        assess_ordinary_snapshot_evidence_v0(
            replace(
                bundle,
                payload=replace(bundle.payload, sources=(*bundle.payload.sources, extra)),
            )
        )

    with pytest.raises(ValueError, match="duplicate"):
        assess_ordinary_snapshot_evidence_v0(
            replace(
                bundle,
                payload=replace(
                    bundle.payload,
                    sources=(*bundle.payload.sources, bundle.payload.sources[0]),
                ),
            )
        )


def test_gate_rejects_mixed_knowledge_horizons() -> None:
    bundle = _bundle()
    changed = replace(
        bundle.payload.sources[0],
        knowledge_horizon=_HORIZON + timedelta(hours=6),
    )
    payload = replace(bundle.payload, sources=(changed, *bundle.payload.sources[1:]))

    with pytest.raises(ValueError, match="knowledge_horizon mismatch"):
        assess_ordinary_snapshot_evidence_v0(replace(bundle, payload=payload))


def test_artifact_created_after_horizon_blocks_evidence() -> None:
    bundle = _bundle()
    receipt = replace(bundle.receipt, artifact_created_at=_HORIZON + timedelta(seconds=1))

    assessment = assess_ordinary_snapshot_evidence_v0(replace(bundle, receipt=receipt))

    assert assessment.verdict is OrdinarySnapshotEvidenceVerdict.BLOCKED
    assert tuple(blocker.code for blocker in assessment.blockers) == (
        OrdinarySnapshotEvidenceBlockerCode.ARTIFACT_CREATED_AFTER_HORIZON,
    )


def test_post_horizon_source_retrieval_blocks_evidence() -> None:
    bundle = _bundle()
    changed = replace(
        bundle.payload.sources[0],
        retrieval_completed_at=_HORIZON + timedelta(seconds=1),
    )
    payload = replace(bundle.payload, sources=(changed, *bundle.payload.sources[1:]))
    changed_bundle = _with_payload(bundle, payload)
    receipt = replace(
        changed_bundle.receipt,
        artifact_created_at=_HORIZON + timedelta(seconds=2),
    )

    assessment = assess_ordinary_snapshot_evidence_v0(
        replace(changed_bundle, receipt=receipt)
    )

    blocker_codes = {blocker.code for blocker in assessment.blockers}
    assert OrdinarySnapshotEvidenceBlockerCode.ARTIFACT_CREATED_AFTER_HORIZON in blocker_codes
    assert OrdinarySnapshotEvidenceBlockerCode.SOURCE_RETRIEVAL_AFTER_HORIZON in blocker_codes


def test_source_claim_cannot_postdate_claimed_artifact_creation() -> None:
    bundle = _bundle()
    changed = replace(
        bundle.payload.sources[0],
        retrieval_completed_at=_HORIZON - timedelta(seconds=5),
    )
    payload = replace(bundle.payload, sources=(changed, *bundle.payload.sources[1:]))

    assessment = assess_ordinary_snapshot_evidence_v0(_with_payload(bundle, payload))

    assert assessment.verdict is OrdinarySnapshotEvidenceVerdict.BLOCKED
    assert any(
        blocker.code is OrdinarySnapshotEvidenceBlockerCode.SOURCE_RETRIEVAL_AFTER_ARTIFACT
        for blocker in assessment.blockers
    )


def test_raw_response_body_retention_is_forbidden() -> None:
    with pytest.raises(ValueError, match="raw response-body retention"):
        replace(_source("hn.frontpage"), raw_body_retained=True)


def test_external_receipt_identity_is_structurally_bounded() -> None:
    receipt = _receipt(_payload())

    with pytest.raises(ValueError, match="repository mismatch"):
        replace(receipt, repository_full_name="somewhere/else")

    with pytest.raises(ValueError, match="40-hex"):
        replace(receipt, workflow_head_sha="not-a-sha")

    with pytest.raises(ValueError, match="attestation_ref"):
        replace(receipt, attestation_ref="")
