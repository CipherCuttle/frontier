from __future__ import annotations

import json
from datetime import UTC, datetime

from frontier.adapters.acquisition.normalizers import (
    normalize_gdelt_frontier,
    normalize_hf_models,
    normalize_hn_frontpage,
)
from frontier.domain.digests import sha256_digest
from frontier.domain.health import HealthValue
from frontier.domain.observation import ArtifactPayload, DocumentPayload, ObservationKind

NOW = datetime(2026, 9, 5, 2, 30, tzinfo=UTC)


def test_hn_frontpage_preserves_attention_item_identity_and_external_target() -> None:
    body = b"""<rss version="2.0"><channel><item>
      <title>Interesting release</title>
      <link>https://example.com/release</link>
      <comments>https://news.ycombinator.com/item?id=12345</comments>
      <pubDate>Sat, 05 Sep 2026 02:28:00 GMT</pubDate>
    </item></channel></rss>"""
    batch = normalize_hn_frontpage(body, retrieved_at=NOW, fetch_digest=sha256_digest(body))

    assert batch.schema_health is HealthValue.OK
    candidate = batch.candidates[0]
    assert candidate.source_id == "hn.frontpage"
    assert candidate.source_item_key == "hn:12345"
    assert candidate.kind is ObservationKind.DOCUMENT
    assert isinstance(candidate.payload, DocumentPayload)
    assert candidate.payload.canonical_url == "https://example.com/release"
    assert "frontpage_rank" not in candidate.payload.source_metadata
    assert candidate.source_published_at == datetime(2026, 9, 5, 2, 28, tzinfo=UTC)


def test_hn_same_external_url_remains_two_attention_observations() -> None:
    body = b"""<rss version="2.0"><channel>
    <item><title>First submission</title><link>https://example.com/release</link>
      <comments>https://news.ycombinator.com/item?id=100</comments></item>
    <item><title>Second submission</title><link>https://example.com/release</link>
      <comments>https://news.ycombinator.com/item?id=200</comments></item>
    </channel></rss>"""
    batch = normalize_hn_frontpage(body, retrieved_at=NOW, fetch_digest=sha256_digest(body))

    assert [candidate.source_item_key for candidate in batch.candidates] == ["hn:100", "hn:200"]
    assert all(
        isinstance(candidate.payload, DocumentPayload)
        and candidate.payload.canonical_url == "https://example.com/release"
        for candidate in batch.candidates
    )


def test_hn_frontpage_reordering_does_not_manufacture_new_attention_evidence() -> None:
    target = """<item><title>Stable submission</title><link>https://example.com/stable</link>
      <comments>https://news.ycombinator.com/item?id=777</comments>
      <pubDate>Sat, 05 Sep 2026 02:20:00 GMT</pubDate></item>"""
    other = """<item><title>Other submission</title><link>https://example.com/other</link>
      <comments>https://news.ycombinator.com/item?id=778</comments>
      <pubDate>Sat, 05 Sep 2026 02:21:00 GMT</pubDate></item>"""
    first_body = f'<rss version="2.0"><channel>{target}{other}</channel></rss>'.encode()
    second_body = f'<rss version="2.0"><channel>{other}{target}</channel></rss>'.encode()

    first = normalize_hn_frontpage(
        first_body,
        retrieved_at=NOW,
        fetch_digest=sha256_digest(first_body),
    )
    second = normalize_hn_frontpage(
        second_body,
        retrieved_at=NOW,
        fetch_digest=sha256_digest(second_body),
    )

    first_target = next(item for item in first.candidates if item.source_item_key == "hn:777")
    second_target = next(item for item in second.candidates if item.source_item_key == "hn:777")
    assert first_target.observation_id == second_target.observation_id


def gdelt_article(index: int, *, seen: str = "20260905T022800Z") -> dict[str, str]:
    return {
        "url": f"https://publisher{index}.example/story",
        "title": f"Story {index}",
        "seendate": seen,
        "domain": f"publisher{index}.example",
        "language": "English",
        "sourcecountry": "United States",
    }


def test_gdelt_discovery_does_not_invent_publisher_publication_time() -> None:
    body = json.dumps({"articles": [gdelt_article(1)]}).encode()
    batch = normalize_gdelt_frontier(body, retrieved_at=NOW, fetch_digest=sha256_digest(body))

    assert batch.schema_health is HealthValue.OK
    assert batch.completeness_health is HealthValue.OK
    candidate = batch.candidates[0]
    assert candidate.source_id == "gdelt.frontier"
    assert candidate.source_item_key == "https://publisher1.example/story"
    assert candidate.source_published_at is None
    assert isinstance(candidate.payload, DocumentPayload)
    assert candidate.payload.source_metadata["discovery_surface"] == "GDELT_DOC_ARTLIST"
    assert candidate.payload.source_metadata["gdelt_seen_at"] == "2026-09-05T02:28:00.000000Z"


def test_gdelt_malformed_seen_time_degrades_schema_without_rewriting_knowledge_time() -> None:
    body = json.dumps({"articles": [gdelt_article(1, seen="not-a-time")]}).encode()
    batch = normalize_gdelt_frontier(body, retrieved_at=NOW, fetch_digest=sha256_digest(body))

    assert batch.schema_health is HealthValue.DEGRADED
    assert batch.candidates[0].source_published_at is None
    assert batch.details["malformed_seen_times"] == 1


def test_gdelt_hard_result_cap_degrades_completeness_not_schema() -> None:
    body = json.dumps({"articles": [gdelt_article(index) for index in range(250)]}).encode()
    batch = normalize_gdelt_frontier(body, retrieved_at=NOW, fetch_digest=sha256_digest(body))

    assert batch.records_received == 250
    assert batch.records_rejected == 0
    assert batch.schema_health is HealthValue.OK
    assert batch.completeness_health is HealthValue.DEGRADED
    assert batch.details["window_saturated"] is True


def hf_model(*, tags: list[str], downloads: int = 1, likes: int = 1) -> dict[str, object]:
    return {
        "id": "frontier-labs/model-x",
        "author": "frontier-labs",
        "sha": "abcdef1234567890",
        "createdAt": "2026-09-05T01:00:00Z",
        "lastModified": "2026-09-05T02:20:00.000+00:00",
        "pipeline_tag": "text-generation",
        "tags": tags,
        "downloads": downloads,
        "likes": likes,
        "trendingScore": downloads + likes,
    }


def test_hf_model_normalizes_stable_repository_emission() -> None:
    body = json.dumps([hf_model(tags=["transformers", "text-generation"])]).encode()
    batch = normalize_hf_models(body, retrieved_at=NOW, fetch_digest=sha256_digest(body))

    assert batch.schema_health is HealthValue.OK
    candidate = batch.candidates[0]
    assert candidate.source_id == "hf.models"
    assert candidate.source_item_key == "frontier-labs/model-x"
    assert candidate.kind is ObservationKind.ARTIFACT
    assert isinstance(candidate.payload, ArtifactPayload)
    assert candidate.payload.version == "abcdef1234567890"
    assert candidate.payload.source_metadata["tags"] == ["text-generation", "transformers"]
    assert candidate.payload.source_metadata["last_modified"] == "2026-09-05T02:20:00.000000Z"
    assert candidate.source_published_at == datetime(2026, 9, 5, 2, 20, tzinfo=UTC)


def test_hf_volatile_counters_and_tag_order_do_not_manufacture_observation_identity() -> None:
    first_body = json.dumps(
        [hf_model(tags=["transformers", "text-generation"], downloads=10, likes=2)]
    ).encode()
    second_body = json.dumps(
        [hf_model(tags=["text-generation", "transformers"], downloads=10000, likes=900)]
    ).encode()

    first = normalize_hf_models(
        first_body,
        retrieved_at=NOW,
        fetch_digest=sha256_digest(first_body),
    ).candidates[0]
    second = normalize_hf_models(
        second_body,
        retrieved_at=NOW,
        fetch_digest=sha256_digest(second_body),
    ).candidates[0]

    assert first.observation_id == second.observation_id
    assert isinstance(first.payload, ArtifactPayload)
    assert "downloads" not in first.payload.source_metadata
    assert "likes" not in first.payload.source_metadata
    assert "trendingScore" not in first.payload.source_metadata


def test_hf_tag_canonicalization_is_order_invariant_before_retention_cap() -> None:
    tags = [f"tag-{index:02d}" for index in range(40)]
    first_body = json.dumps([hf_model(tags=tags)]).encode()
    second_body = json.dumps([hf_model(tags=list(reversed(tags)))]).encode()

    first = normalize_hf_models(
        first_body,
        retrieved_at=NOW,
        fetch_digest=sha256_digest(first_body),
    ).candidates[0]
    second = normalize_hf_models(
        second_body,
        retrieved_at=NOW,
        fetch_digest=sha256_digest(second_body),
    ).candidates[0]

    assert first.observation_id == second.observation_id
    assert isinstance(first.payload, ArtifactPayload)
    assert first.payload.source_metadata["tags"] == sorted(tags)[:32]


def test_hf_hard_result_cap_degrades_completeness() -> None:
    records: list[dict[str, object]] = []
    for index in range(100):
        model = hf_model(tags=["transformers"])
        model["id"] = f"frontier-labs/model-{index}"
        model["sha"] = f"sha-{index}"
        records.append(model)
    body = json.dumps(records).encode()
    batch = normalize_hf_models(body, retrieved_at=NOW, fetch_digest=sha256_digest(body))

    assert batch.records_received == 100
    assert batch.schema_health is HealthValue.OK
    assert batch.completeness_health is HealthValue.DEGRADED
