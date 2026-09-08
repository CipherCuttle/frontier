from __future__ import annotations

import argparse
import json
import resource
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from frontier.domain.digests import Digest
from frontier.domain.grouping import GroupingInput
from frontier.domain.grouping_v1 import (
    build_compact_grouping_projection,
    build_compact_grouping_receipt,
)

AS_OF: Final = datetime(2026, 9, 8, 20, tzinfo=UTC)
SOURCE_REGISTRY_DIGEST: Final = Digest(
    "sha256:0e3dcd047379e500900194ed2ff47aa980a4a61172c33a7fb7b9e2f5930b696e"
)


@dataclass(frozen=True, slots=True)
class Case:
    count: int
    peak_rss_mib_max: float
    wall_seconds_max: float
    shape: str


CASES: Final[dict[str, Case]] = {
    "incident-2425": Case(2425, 512, 30, "sparse"),
    "sparse-10000": Case(10_000, 768, 60, "sparse"),
    "sparse-25000": Case(25_000, 1024, 180, "sparse"),
    "mixed-150000": Case(150_000, 1536, 300, "mixed"),
    "dense-5000": Case(5000, 1024, 180, "dense"),
}


def _observation(
    index: int,
    *,
    title: str,
    canonical_url: str,
    signal_roles: tuple[str, ...] = (),
) -> GroupingInput:
    return GroupingInput(
        observation_id=f"obs_{index:064x}",
        source_id="benchmark.synthetic",
        source_item_key=f"item-{index}",
        kind="DOCUMENT",
        observed_at=AS_OF - timedelta(minutes=index % 120),
        canonical_url=canonical_url,
        title=title,
        text=None,
        signal_roles=signal_roles,
    )


def _sparse(count: int) -> tuple[GroupingInput, ...]:
    return tuple(
        _observation(
            index,
            title=f"frontier synthetic release unique{index}",
            canonical_url=f"https://benchmark.invalid/sparse/{index}",
        )
        for index in range(count)
    )


def _mixed(count: int) -> tuple[GroupingInput, ...]:
    collision_count = min(2000, count // 20)
    sparse_count = count - collision_count
    values = list(_sparse(sparse_count))
    base = sparse_count

    attention_count = collision_count // 2
    for offset in range(attention_count):
        bucket = offset // 50
        index = base + offset
        values.append(
            _observation(
                index,
                title=f"attention target bucket {bucket} item {offset}",
                canonical_url=f"https://benchmark.invalid/attention/{bucket}",
                signal_roles=("ATTENTION",),
            )
        )

    title_count = collision_count - attention_count
    for offset in range(title_count):
        bucket = offset // 50
        index = base + attention_count + offset
        values.append(
            _observation(
                index,
                title=f"deterministic exact title collision bucket {bucket}",
                canonical_url=f"https://benchmark.invalid/title/{index}",
            )
        )
    return tuple(values)


def _dense(count: int) -> tuple[GroupingInput, ...]:
    return tuple(
        _observation(
            index,
            title=f"dense attention target unique{index}",
            canonical_url="https://benchmark.invalid/dense/shared",
            signal_roles=("ATTENTION",),
        )
        for index in range(count)
    )


def _inputs(case: Case) -> tuple[GroupingInput, ...]:
    if case.shape == "sparse":
        return _sparse(case.count)
    if case.shape == "mixed":
        return _mixed(case.count)
    if case.shape == "dense":
        return _dense(case.count)
    raise ValueError(f"unknown benchmark shape: {case.shape}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("case", choices=tuple(CASES))
    args = parser.parse_args()
    case = CASES[args.case]

    inputs = _inputs(case)
    started = time.perf_counter()
    projection = build_compact_grouping_projection(inputs, as_of=AS_OF)
    receipt = build_compact_grouping_receipt(
        projection,
        inputs=inputs,
        relations=(),
        generated_at=AS_OF + timedelta(minutes=1),
        source_registry_version=SOURCE_REGISTRY_DIGEST,
    )
    wall_seconds = time.perf_counter() - started
    peak_rss_mib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024

    result = {
        "algorithm_version": projection.algorithm_version,
        "candidate_pair_count": projection.candidate_pair_count,
        "case": args.case,
        "eligible_observation_count": projection.eligible_observation_count,
        "group_count": len(projection.groups),
        "group_pair_count": projection.group_pair_count,
        "input_digest": str(receipt.input_digest),
        "output_digest": str(receipt.output_digest),
        "peak_rss_mib": round(peak_rss_mib, 3),
        "peak_rss_mib_max": case.peak_rss_mib_max,
        "receipt_id": receipt.receipt_id,
        "ungrouped_count": len(projection.ungrouped_observation_ids),
        "wall_seconds": round(wall_seconds, 3),
        "wall_seconds_max": case.wall_seconds_max,
    }
    print(json.dumps(result, sort_keys=True))

    failures: list[str] = []
    if peak_rss_mib > case.peak_rss_mib_max:
        failures.append(
            f"peak RSS {peak_rss_mib:.3f} MiB exceeds {case.peak_rss_mib_max:.3f} MiB"
        )
    if wall_seconds > case.wall_seconds_max:
        failures.append(f"wall {wall_seconds:.3f}s exceeds {case.wall_seconds_max:.3f}s")
    if projection.eligible_observation_count != case.count:
        failures.append("eligible observation count does not match generated benchmark count")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
