from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from frontier.adapters.acquisition.normalizers import (
    NormalizationError,
    normalize_cisa_kev,
    normalize_pypi_updates,
)
from frontier.domain.digests import sha256_digest
from frontier.domain.health import HealthValue
from frontier.domain.observation import ArtifactPayload, DocumentPayload, ObservationKind

NOW = datetime(2026, 9, 5, 1, 0, tzinfo=UTC)


def test_pypi_rss_normalizes_release_identity_without_guessing_from_title() -> None:
    body = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel><item>
      <title>frontier-demo 1.2.3</title>
      <link>https://pypi.org/project/frontier-demo/1.2.3/</link>
      <description>release notes</description>
      <pubDate>Sat, 05 Sep 2026 00:59:00 GMT</pubDate>
    </item></channel></rss>"""
    batch = normalize_pypi_updates(body, retrieved_at=NOW, fetch_digest=sha256_digest(body))

    assert batch.records_received == 1
    assert batch.records_rejected == 0
    assert batch.schema_health is HealthValue.OK
    candidate = batch.candidates[0]
    assert candidate.kind is ObservationKind.ARTIFACT
    assert candidate.source_item_key == "https://pypi.org/project/frontier-demo/1.2.3/"
    assert isinstance(candidate.payload, ArtifactPayload)
    assert candidate.payload.name == "frontier-demo"
    assert candidate.payload.version == "1.2.3"
    assert candidate.source_published_at == datetime(2026, 9, 5, 0, 59, tzinfo=UTC)


def test_pypi_rejects_dtd_and_entity_declarations_before_xml_parse() -> None:
    body = b'<!DOCTYPE rss [<!ENTITY xxe SYSTEM "http://127.0.0.1/secret">]><rss>&xxe;</rss>'
    with pytest.raises(NormalizationError, match="forbidden") as error:
        normalize_pypi_updates(body, retrieved_at=NOW, fetch_digest=sha256_digest(body))
    assert error.value.code == "XML_DTD_FORBIDDEN"


def test_pypi_malformed_source_time_never_defaults_to_now() -> None:
    body = b"""<rss version="2.0"><channel><item>
      <title>broken-time</title>
      <link>https://pypi.org/project/broken-time/1.0/</link>
      <pubDate>definitely-not-a-time</pubDate>
    </item></channel></rss>"""
    batch = normalize_pypi_updates(body, retrieved_at=NOW, fetch_digest=sha256_digest(body))
    assert batch.schema_health is HealthValue.DEGRADED
    assert batch.candidates[0].source_published_at is None
    assert batch.details["malformed_source_times"] == 1


def cisa_catalog(catalog_version: str) -> dict[str, object]:
    return {
        "title": "CISA Known Exploited Vulnerabilities Catalog",
        "catalogVersion": catalog_version,
        "count": 1,
        "vulnerabilities": [
            {
                "cveID": "CVE-2026-12345",
                "vendorProject": "Example",
                "product": "Widget",
                "vulnerabilityName": "Example Widget RCE",
                "dateAdded": "2026-09-05",
                "shortDescription": "Remote code execution.",
                "requiredAction": "Apply mitigations.",
                "dueDate": "2026-09-20",
                "knownRansomwareCampaignUse": "Unknown",
                "notes": "https://example.invalid/advisory",
                "cwes": ["CWE-78"],
            }
        ],
    }


def test_cisa_catalog_creates_one_canonical_document_per_cve() -> None:
    raw = cisa_catalog("2026.09.05")
    body = json.dumps(raw).encode()
    batch = normalize_cisa_kev(body, retrieved_at=NOW, fetch_digest=sha256_digest(body))

    assert batch.records_received == 1
    assert batch.records_rejected == 0
    candidate = batch.candidates[0]
    assert candidate.kind is ObservationKind.DOCUMENT
    assert candidate.source_item_key == "CVE-2026-12345"
    assert candidate.source_published_at is None
    assert candidate.effective_at is None
    assert isinstance(candidate.payload, DocumentPayload)
    assert candidate.payload.source_metadata["date_added"] == "2026-09-05"
    assert "catalog_version" not in candidate.payload.source_metadata
    assert batch.details["catalog_version"] == "2026.09.05"
    assert "Apply mitigations" in (candidate.payload.excerpt or "")


def test_cisa_catalog_version_change_does_not_manufacture_new_cve_observation() -> None:
    first_body = json.dumps(cisa_catalog("2026.09.05")).encode()
    second_body = json.dumps(cisa_catalog("2026.09.06")).encode()

    first = normalize_cisa_kev(
        first_body,
        retrieved_at=NOW,
        fetch_digest=sha256_digest(first_body),
    ).candidates[0]
    second = normalize_cisa_kev(
        second_body,
        retrieved_at=NOW,
        fetch_digest=sha256_digest(second_body),
    ).candidates[0]

    assert first.observation_id == second.observation_id
