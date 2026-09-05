from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from frontier.domain.grouping import EpisodeGroup, GroupingInput, GroupingProjection
from frontier.domain.health import HealthValue
from frontier.domain.intelligence import (
    BaselineHealthInput,
    BaselineObservationInput,
    build_baseline_snapshot,
)

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "fixtures" / "baseline_intelligence" / "corpus_v0.json"


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def observation_id(scenario_id: str, key: str) -> str:
    material = f"{scenario_id}:{key}".encode()
    return "obs_" + hashlib.sha256(material).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"baseline-intelligence-runtime: FAIL: {message}")


def main() -> int:
    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    checked = 0
    for scenario in data["scenarios"]:
        if scenario["category"] == "atomic_publication":
            continue
        scenario_id = scenario["id"]
        as_of = parse_time(scenario["as_of"])
        observations: list[BaselineObservationInput] = []
        members_by_key: dict[str, list[str]] = {}
        for episode in scenario.get("episodes", []):
            member_ids: list[str] = []
            for raw in episode["observations"]:
                obs_id = observation_id(scenario_id, raw["key"])
                observed_at = parse_time(raw["observed_at"])
                observations.append(
                    BaselineObservationInput(
                        grouping=GroupingInput(
                            observation_id=obs_id,
                            source_id=raw["source_id"],
                            source_item_key=raw["key"],
                            kind="DOCUMENT",
                            observed_at=observed_at,
                            canonical_url=f"https://fixture.invalid/{scenario_id}/{raw['key']}",
                            title=f"{episode['episode_key']} canonical fixture title",
                            text=None,
                            signal_roles=tuple(raw["signal_roles"]),
                        ),
                        first_reason=raw["first_reason"],
                        recovered_after_gap=raw["recovered_after_gap"],
                    )
                )
                if observed_at <= as_of:
                    member_ids.append(obs_id)
            if member_ids:
                members_by_key[episode["episode_key"]] = member_ids

        groups: list[EpisodeGroup] = []
        ungrouped: list[str] = []
        for index, member_ids in enumerate(members_by_key.values(), start=1):
            ordered = tuple(sorted(member_ids))
            if len(ordered) == 1:
                ungrouped.append(ordered[0])
            else:
                groups.append(
                    EpisodeGroup(
                        group_id="grp_" + f"{index:064x}",
                        observation_ids=ordered,
                    )
                )
        projection = GroupingProjection(
            as_of=as_of,
            groups=tuple(groups),
            ambiguous_pairs=(),
            ungrouped_observation_ids=tuple(sorted(ungrouped)),
        )

        health = tuple(
            BaselineHealthInput(
                source_id=raw["source_id"],
                as_of=parse_time(raw["as_of"]),
                transport=HealthValue(raw["transport"]),
                freshness=HealthValue(raw["freshness"]),
                completeness=HealthValue(raw["completeness"]),
                schema=HealthValue(raw["schema"]),
            )
            for raw in scenario.get("health", [])
        )
        enabled_sources = scenario.get("enabled_sources")
        if enabled_sources is None:
            enabled_sources = sorted({item.grouping.source_id for item in observations})

        snapshot = build_baseline_snapshot(
            observations,
            grouping_projection=projection,
            enabled_source_ids=enabled_sources,
            health=health,
            as_of=as_of,
        )
        episode_key_by_members = {
            frozenset(member_ids): key for key, member_ids in members_by_key.items()
        }
        actual_by_key = {
            episode_key_by_members[frozenset(item.observation_ids)]: item
            for item in snapshot.episodes
        }
        expected = scenario["expect"]
        expected_ranking = expected.get("ranked_episode_keys")
        if expected_ranking is not None:
            actual_ranking = [
                episode_key_by_members[frozenset(item.observation_ids)]
                for item in snapshot.episodes
            ]
            require(actual_ranking == expected_ranking, f"{scenario_id}: ranking mismatch")

        for key, metrics in expected.items():
            if key in {
                "ranked_episode_keys",
                "tie_break",
                "transport_state",
                "freshness_state",
                "coverage_state",
                "schema_state",
            }:
                continue
            require(key in actual_by_key, f"{scenario_id}: missing episode {key}")
            episode = actual_by_key[key]
            for field, value in metrics.items():
                require(
                    getattr(episode, field) == value,
                    f"{scenario_id}:{key}:{field} expected {value!r} got {getattr(episode, field)!r}",
                )

        for field in ("transport_state", "freshness_state", "coverage_state", "schema_state"):
            if field in expected:
                require(
                    getattr(snapshot, field).value == expected[field],
                    f"{scenario_id}:{field} mismatch",
                )
        if expected.get("tie_break") == "episode_id_ascending":
            ids = [item.episode_id for item in snapshot.episodes]
            require(ids == sorted(ids), f"{scenario_id}: episode-id tie break mismatch")
        checked += 1

    print(f"baseline-intelligence-runtime: PASS {checked} executable frozen scenarios")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
