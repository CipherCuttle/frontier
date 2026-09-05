from __future__ import annotations

import json
from datetime import UTC, datetime

from frontier.adapters.acquisition.normalizers import (
    normalize_arxiv_cs_ai,
    normalize_github_ml_repos,
)
from frontier.domain.digests import sha256_digest
from frontier.domain.health import HealthValue
from frontier.domain.observation import ArtifactPayload, DocumentPayload

NOW = datetime(2026, 9, 5, 20, 30, tzinfo=UTC)


def test_arxiv_recent_submission_is_primary_metadata_without_abstract_copy() -> None:
    body = b"""<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/2609.01234v1</id>
        <updated>2026-09-05T19:45:00Z</updated>
        <published>2026-09-05T19:45:00Z</published>
        <title>  Frontier agent systems  </title>
        <summary>This abstract is intentionally not retained in V0.</summary>
        <author><name>Alice Example</name></author>
        <author><name>Bob Example</name></author>
        <category term="cs.AI"/>
        <category term="cs.LG"/>
        <link rel="alternate" href="https://arxiv.org/abs/2609.01234v1"/>
      </entry>
    </feed>"""
    batch = normalize_arxiv_cs_ai(body, retrieved_at=NOW, fetch_digest=sha256_digest(body))

    assert batch.schema_health is HealthValue.OK
    candidate = batch.candidates[0]
    assert candidate.source_id == "arxiv.cs-ai"
    assert candidate.source_item_key == "http://arxiv.org/abs/2609.01234v1"
    assert candidate.source_published_at == datetime(2026, 9, 5, 19, 45, tzinfo=UTC)
    assert isinstance(candidate.payload, DocumentPayload)
    assert candidate.payload.canonical_url == "https://arxiv.org/abs/2609.01234v1"
    assert candidate.payload.excerpt is None
    assert candidate.payload.source_metadata["authors"] == ["Alice Example", "Bob Example"]
    assert candidate.payload.source_metadata["categories"] == ["cs.AI", "cs.LG"]


def github_repo(*, pushed_at: str, stars: int) -> dict[str, object]:
    return {
        "id": 123456,
        "node_id": "R_kgDOexample",
        "full_name": "frontier-labs/agent-stack",
        "html_url": "https://github.com/frontier-labs/agent-stack",
        "created_at": "2026-09-01T10:00:00Z",
        "updated_at": pushed_at,
        "pushed_at": pushed_at,
        "default_branch": "main",
        "language": "Python",
        "topics": ["agents", "machine-learning"],
        "archived": False,
        "fork": False,
        "stargazers_count": stars,
        "forks_count": stars // 2,
        "watchers_count": stars,
        "open_issues_count": stars,
    }


def test_github_popularity_counters_do_not_manufacture_activity_observations() -> None:
    first_body = json.dumps(
        {
            "total_count": 1,
            "incomplete_results": False,
            "items": [github_repo(pushed_at="2026-09-05T20:00:00Z", stars=10)],
        }
    ).encode()
    second_body = json.dumps(
        {
            "total_count": 1,
            "incomplete_results": False,
            "items": [github_repo(pushed_at="2026-09-05T20:00:00Z", stars=10000)],
        }
    ).encode()

    first = normalize_github_ml_repos(
        first_body, retrieved_at=NOW, fetch_digest=sha256_digest(first_body)
    ).candidates[0]
    second = normalize_github_ml_repos(
        second_body, retrieved_at=NOW, fetch_digest=sha256_digest(second_body)
    ).candidates[0]

    assert first.observation_id == second.observation_id
    assert isinstance(first.payload, ArtifactPayload)
    assert "stargazers_count" not in first.payload.source_metadata
    assert "forks_count" not in first.payload.source_metadata
    assert "watchers_count" not in first.payload.source_metadata


def test_github_new_push_is_new_behavioral_observation() -> None:
    first_body = json.dumps(
        {
            "total_count": 1,
            "incomplete_results": False,
            "items": [github_repo(pushed_at="2026-09-05T20:00:00Z", stars=10)],
        }
    ).encode()
    second_body = json.dumps(
        {
            "total_count": 1,
            "incomplete_results": False,
            "items": [github_repo(pushed_at="2026-09-05T20:05:00Z", stars=10)],
        }
    ).encode()

    first = normalize_github_ml_repos(
        first_body, retrieved_at=NOW, fetch_digest=sha256_digest(first_body)
    ).candidates[0]
    second = normalize_github_ml_repos(
        second_body, retrieved_at=NOW, fetch_digest=sha256_digest(second_body)
    ).candidates[0]

    assert first.observation_id != second.observation_id
    assert second.source_published_at == datetime(2026, 9, 5, 20, 5, tzinfo=UTC)


def test_github_search_incomplete_flag_degrades_coverage_not_schema() -> None:
    body = json.dumps(
        {
            "total_count": 1000,
            "incomplete_results": True,
            "items": [github_repo(pushed_at="2026-09-05T20:00:00Z", stars=10)],
        }
    ).encode()

    batch = normalize_github_ml_repos(body, retrieved_at=NOW, fetch_digest=sha256_digest(body))

    assert batch.schema_health is HealthValue.OK
    assert batch.completeness_health is HealthValue.DEGRADED
    assert batch.details["search_incomplete"] is True
