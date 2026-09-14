from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import cast

from frontier.adapters.acquisition.config import load_fetch_policy
from frontier.adapters.acquisition.fetcher import SecureHttpFetcher
from frontier.adapters.acquisition.frozen_config import load_source_registry_from_git_ref
from frontier.adapters.acquisition.json_values import parse_typed_json
from frontier.application.value_observatory_ordinary_snapshot_evidence import (
    OrdinarySnapshotEvidenceBundle,
    OrdinarySnapshotPayloadClaim,
    OrdinarySnapshotReceiptClaim,
    OrdinarySnapshotSourceClaim,
    assess_ordinary_snapshot_evidence_v0,
    ordinary_snapshot_payload_digest_v0,
)
from frontier.application.value_observatory_ordinary_snapshot_probe import (
    ordinary_snapshot_probe_artifact_v0,
    ordinary_snapshot_probe_report_v0,
    run_ordinary_snapshot_probe_v0,
)
from frontier.domain.canonical_json import CanonicalValue, canonical_json_bytes
from frontier.domain.digests import Digest, sha256_digest

_BENCHMARK_PROTOCOL_PATH = Path("experiments/value_observatory_v0/benchmark_capture_v0.json")


def _utc_datetime(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    offset = parsed.utcoffset()
    if parsed.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise ValueError("timestamp must be timezone-aware UTC")
    return parsed


def _head_sha(root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        check=True,
        text=True,
        timeout=30,
    )
    value = result.stdout.strip()
    if len(value) != 40:
        raise ValueError("could not resolve exact checkout Git SHA")
    return value


def _protocol_digest(root: Path) -> Digest:
    raw = parse_typed_json((root / _BENCHMARK_PROTOCOL_PATH).read_text(encoding="utf-8"))
    return sha256_digest(canonical_json_bytes(raw))


def _write_canonical(path: Path, value: CanonicalValue) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value) + b"\n")


def _as_mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, object], value)


def _as_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return cast(list[object], value)


def _as_str(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _as_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    return value


def _digest(value: object, label: str) -> Digest:
    text = _as_str(value, label)
    if not text.startswith("sha256:"):
        text = "sha256:" + text
    return Digest(text)


def _payload_from_artifact(raw: dict[str, object]) -> OrdinarySnapshotPayloadClaim:
    if raw.get("schema_version") != "frontier-ordinary-snapshot-probe-artifact-v0":
        raise ValueError("unsupported ordinary snapshot probe artifact schema")
    claim = _as_mapping(raw.get("payload_claim"), "payload_claim")
    collections = _as_list(raw.get("normalized_collections"), "normalized_collections")
    collections_by_source: dict[str, dict[str, object]] = {}
    for value in collections:
        collection = _as_mapping(value, "normalized_collection")
        source_id = _as_str(collection.get("source_id"), "normalized_collection.source_id")
        if source_id in collections_by_source:
            raise ValueError("duplicate normalized collection source")
        collections_by_source[source_id] = collection

    source_claims: list[OrdinarySnapshotSourceClaim] = []
    for value in _as_list(claim.get("sources"), "payload_claim.sources"):
        source = _as_mapping(value, "payload_claim.source")
        source_id = _as_str(source.get("source_id"), "payload_claim.source_id")
        collection = collections_by_source.get(source_id)
        if collection is None:
            raise ValueError(f"missing normalized collection for {source_id}")
        expected_collection_digest = _digest(
            source.get("normalized_collection_digest"),
            "payload_claim.normalized_collection_digest",
        )
        actual_collection_digest = sha256_digest(
            canonical_json_bytes(cast(CanonicalValue, collection))
        )
        if actual_collection_digest != expected_collection_digest:
            raise ValueError(f"normalized collection digest mismatch for {source_id}")
        raw_body_retained = source.get("raw_body_retained")
        if raw_body_retained is not False:
            raise ValueError("ordinary snapshot probe artifact claims raw body retention")
        source_claims.append(
            OrdinarySnapshotSourceClaim(
                source_id=source_id,
                knowledge_horizon=_utc_datetime(
                    _as_str(source.get("knowledge_horizon"), "source.knowledge_horizon")
                ),
                retrieval_completed_at=_utc_datetime(
                    _as_str(source.get("retrieval_completed_at"), "source.retrieval_completed_at")
                ),
                source_contract_digest=_digest(
                    source.get("source_contract_digest"), "source.source_contract_digest"
                ),
                request_identity_digest=_digest(
                    source.get("request_identity_digest"), "source.request_identity_digest"
                ),
                raw_payload_digest=_digest(
                    source.get("raw_payload_digest"), "source.raw_payload_digest"
                ),
                normalized_collection_digest=expected_collection_digest,
                raw_body_retained=False,
            )
        )

    if set(collections_by_source) != {source.source_id for source in source_claims}:
        raise ValueError("normalized collection set differs from payload claim source set")
    payload = OrdinarySnapshotPayloadClaim(
        snapshot_id=_as_str(claim.get("snapshot_id"), "payload_claim.snapshot_id"),
        knowledge_horizon=_utc_datetime(
            _as_str(claim.get("knowledge_horizon"), "payload_claim.knowledge_horizon")
        ),
        benchmark_protocol_digest=_digest(
            claim.get("benchmark_protocol_digest"), "payload_claim.benchmark_protocol_digest"
        ),
        source_registry_version=_digest(
            claim.get("source_registry_version"), "payload_claim.source_registry_version"
        ),
        sources=tuple(source_claims),
    )
    stored_digest = _digest(raw.get("snapshot_payload_digest"), "snapshot_payload_digest")
    if ordinary_snapshot_payload_digest_v0(payload) != stored_digest:
        raise ValueError("snapshot payload digest mismatch")
    return payload


def _produce(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    authority_ref = _head_sha(root)
    registry = load_source_registry_from_git_ref(root, authority_ref)
    policy = load_fetch_policy(root)
    result = asyncio.run(
        run_ordinary_snapshot_probe_v0(
            registry=registry,
            policy=policy,
            fetcher=SecureHttpFetcher(policy),
            snapshot_id=args.snapshot_id,
            authority_ref=authority_ref,
            knowledge_horizon=_utc_datetime(args.knowledge_horizon),
            benchmark_protocol_digest=_protocol_digest(root),
        )
    )
    output = Path(args.output_dir)
    _write_canonical(output / "probe_report_v0.json", ordinary_snapshot_probe_report_v0(result))
    if result.payload is None:
        return 2
    _write_canonical(
        output / "ordinary_snapshot_payload_v0.json",
        ordinary_snapshot_probe_artifact_v0(result),
    )
    return 0


def _receipt(args: argparse.Namespace) -> int:
    raw_artifact = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    payload = _payload_from_artifact(_as_mapping(raw_artifact, "snapshot artifact"))
    metadata = _as_mapping(
        json.loads(Path(args.artifact_metadata).read_text(encoding="utf-8")),
        "artifact metadata",
    )
    workflow = _as_mapping(metadata.get("workflow_run"), "artifact metadata.workflow_run")
    artifact_digest = _digest(metadata.get("digest"), "artifact metadata.digest")
    expected_artifact_digest = _digest(args.expected_artifact_digest, "expected artifact digest")
    if artifact_digest != expected_artifact_digest:
        raise ValueError("GitHub artifact REST digest differs from upload action digest")

    receipt = OrdinarySnapshotReceiptClaim(
        repository_full_name=args.repository,
        artifact_id=_as_int(metadata.get("id"), "artifact metadata.id"),
        artifact_digest=artifact_digest,
        artifact_created_at=_utc_datetime(
            _as_str(metadata.get("created_at"), "artifact metadata.created_at")
        ),
        workflow_run_id=_as_int(workflow.get("id"), "artifact metadata.workflow_run.id"),
        workflow_head_sha=_as_str(
            workflow.get("head_sha"), "artifact metadata.workflow_run.head_sha"
        ),
        snapshot_payload_digest=ordinary_snapshot_payload_digest_v0(payload),
        attestation_ref=args.attestation_ref,
        attestation_digest=sha256_digest(Path(args.attestation_bundle).read_bytes()),
    )
    assessment = assess_ordinary_snapshot_evidence_v0(
        OrdinarySnapshotEvidenceBundle(payload=payload, receipt=receipt)
    )
    output: dict[str, CanonicalValue] = {
        "assessment": {
            "blockers": [
                {
                    "code": blocker.code.value,
                    "detail": blocker.detail,
                    "source_id": blocker.source_id,
                }
                for blocker in assessment.blockers
            ],
            "source_ids": list(assessment.source_ids),
            "verdict": assessment.verdict.value,
        },
        "receipt": {
            "artifact_created_at": receipt.artifact_created_at.isoformat().replace("+00:00", "Z"),
            "artifact_digest": receipt.artifact_digest.value,
            "artifact_id": receipt.artifact_id,
            "attestation_digest": receipt.attestation_digest.value,
            "attestation_ref": receipt.attestation_ref,
            "repository_full_name": receipt.repository_full_name,
            "snapshot_payload_digest": receipt.snapshot_payload_digest.value,
            "workflow_head_sha": receipt.workflow_head_sha,
            "workflow_run_id": receipt.workflow_run_id,
        },
        "schema_version": "frontier-ordinary-snapshot-probe-receipt-v0",
    }
    _write_canonical(Path(args.output), output)
    print(assessment.verdict.value)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    produce = subparsers.add_parser("produce")
    produce.add_argument("--knowledge-horizon", required=True)
    produce.add_argument("--snapshot-id", required=True)
    produce.add_argument("--output-dir", required=True)
    produce.add_argument("--root", default=".")
    produce.set_defaults(handler=_produce)

    receipt = subparsers.add_parser("receipt")
    receipt.add_argument("--payload", required=True)
    receipt.add_argument("--artifact-metadata", required=True)
    receipt.add_argument("--expected-artifact-digest", required=True)
    receipt.add_argument("--attestation-ref", required=True)
    receipt.add_argument("--attestation-bundle", required=True)
    receipt.add_argument("--repository", required=True)
    receipt.add_argument("--output", required=True)
    receipt.set_defaults(handler=_receipt)
    return parser


def main() -> int:
    args = _parser().parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
