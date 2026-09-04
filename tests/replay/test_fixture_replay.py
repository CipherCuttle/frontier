from pathlib import Path

from frontier.adapters.fixture.normalizer import load_fixture_candidate
from frontier.domain.canonical_json import canonical_json_text
from frontier.domain.observation import Observation

FIXTURE = Path("fixtures/sources/hostile_document_v1")


def test_fixture_replay_is_byte_identical() -> None:
    candidate, observed_at = load_fixture_candidate(FIXTURE)
    observation = Observation(candidate=candidate, observed_at=observed_at)
    actual = canonical_json_text(observation.to_canonical()) + "\n"
    expected = (FIXTURE / "expected_observation.json").read_text(encoding="utf-8")
    assert actual == expected
    assert canonical_json_text(observation.to_canonical()) + "\n" == actual
