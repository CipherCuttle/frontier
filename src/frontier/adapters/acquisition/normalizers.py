from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import unquote, urlsplit

from frontier.domain.canonical_json import CanonicalValue, canonical_json_bytes
from frontier.domain.digests import Digest, sha256_hex
from frontier.domain.health import HealthValue
from frontier.domain.observation import (
    ArtifactPayload,
    DocumentPayload,
    ObservationCandidate,
    ObservationKind,
)

_CVE_RE = re.compile(r"^CVE-\d{4}-\d{4,}$")
_CISA_CATALOG_URL = "https://www.cisa.gov/known-exploited-vulnerabilities-catalog"


class NormalizationError(ValueError):
    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


@dataclass(frozen=True, slots=True)
class NormalizedBatch:
    candidates: tuple[ObservationCandidate, ...]
    records_received: int
    records_rejected: int
    schema_health: HealthValue
    details: dict[str, CanonicalValue]


def _text(element: ET.Element, name: str) -> str | None:
    child = element.find(name)
    if child is None or child.text is None:
        return None
    value = child.text.strip()
    return value or None


def _truncate_utf8(value: str | None, maximum: int) -> str | None:
    if value is None:
        return None
    encoded = value.encode("utf-8")
    if len(encoded) <= maximum:
        return value
    return encoded[:maximum].decode("utf-8", errors="ignore")


def _rss_release_identity(link: str | None, title: str) -> tuple[str, str | None, str]:
    if link:
        parsed = urlsplit(link)
        parts = [unquote(part) for part in parsed.path.split("/") if part]
        if len(parts) >= 3 and parts[0].lower() == "project":
            return parts[1], parts[2], link
        return title, None, link
    key = "rss_" + sha256_hex(canonical_json_bytes({"title": title}))
    return title, None, key


def _rss_time(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except TypeError, ValueError, OverflowError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def normalize_pypi_updates(
    body: bytes, *, retrieved_at: datetime, fetch_digest: Digest
) -> NormalizedBatch:
    lowered = body.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise NormalizationError("XML_DTD_FORBIDDEN", "DTD/entity declarations are forbidden")
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise NormalizationError("RSS_PARSE_FAILED", "PyPI RSS is malformed") from exc
    items = root.findall("./channel/item")
    candidates: list[ObservationCandidate] = []
    rejected = 0
    malformed_time = 0
    for item in items:
        title = _text(item, "title")
        link = _text(item, "link")
        description = _text(item, "description")
        pub_date_text = _text(item, "pubDate")
        if title is None:
            rejected += 1
            continue
        published = _rss_time(pub_date_text)
        if pub_date_text is not None and published is None:
            malformed_time += 1
        name, version, item_key = _rss_release_identity(link, title)
        payload = ArtifactPayload(
            artifact_type="python-package-release",
            name=_truncate_utf8(name, 2048) or title,
            version=_truncate_utf8(version, 512),
            canonical_url=_truncate_utf8(link, 4096),
            artifact_digest=None,
            source_metadata={
                "description": _truncate_utf8(description, 8192),
                "feed_title": _truncate_utf8(title, 2048),
                "source_pub_date": _truncate_utf8(pub_date_text, 256),
            },
        )
        candidates.append(
            ObservationCandidate(
                source_id="pypi.updates",
                source_item_key=item_key,
                kind=ObservationKind.ARTIFACT,
                payload=payload,
                retrieved_at=retrieved_at,
                fetch_digest=fetch_digest,
                source_published_at=published,
                effective_at=None,
            )
        )
    schema_health = HealthValue.OK
    if rejected or malformed_time:
        schema_health = HealthValue.DEGRADED
    return NormalizedBatch(
        candidates=tuple(candidates),
        records_received=len(items),
        records_rejected=rejected,
        schema_health=schema_health,
        details={
            "malformed_source_times": malformed_time,
            "parser": "stdlib-elementtree-v0",
        },
    )


def _string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _string_list(value: object, maximum_items: int = 64) -> list[CanonicalValue]:
    if not isinstance(value, list):
        return []
    result: list[CanonicalValue] = []
    for item in value[:maximum_items]:
        text = _string(item)
        if text is not None:
            result.append(_truncate_utf8(text, 512))
    return result


def normalize_cisa_kev(
    body: bytes, *, retrieved_at: datetime, fetch_digest: Digest
) -> NormalizedBatch:
    try:
        raw = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NormalizationError("JSON_PARSE_FAILED", "CISA KEV JSON is malformed") from exc
    if not isinstance(raw, dict):
        raise NormalizationError("CISA_SCHEMA_FAILED", "CISA KEV root must be an object")
    vulnerabilities = raw.get("vulnerabilities")
    if not isinstance(vulnerabilities, list):
        raise NormalizationError("CISA_SCHEMA_FAILED", "CISA KEV vulnerabilities must be a list")
    candidates: list[ObservationCandidate] = []
    rejected = 0
    for entry in vulnerabilities:
        if not isinstance(entry, dict):
            rejected += 1
            continue
        cve = _string(entry.get("cveID"))
        title = _string(entry.get("vulnerabilityName"))
        if cve is None or not _CVE_RE.fullmatch(cve) or title is None:
            rejected += 1
            continue
        short_description = _string(entry.get("shortDescription"))
        required_action = _string(entry.get("requiredAction"))
        excerpt_parts = [part for part in (short_description, required_action) if part]
        excerpt = _truncate_utf8("\n\n".join(excerpt_parts), 8192)
        payload = DocumentPayload(
            canonical_url=_CISA_CATALOG_URL,
            title=_truncate_utf8(title, 2048),
            excerpt=excerpt,
            language="en",
            source_metadata={
                "cve_id": cve,
                "vendor_project": _truncate_utf8(_string(entry.get("vendorProject")), 512),
                "product": _truncate_utf8(_string(entry.get("product")), 512),
                "date_added": _truncate_utf8(_string(entry.get("dateAdded")), 64),
                "due_date": _truncate_utf8(_string(entry.get("dueDate")), 64),
                "known_ransomware_campaign_use": _truncate_utf8(
                    _string(entry.get("knownRansomwareCampaignUse")), 128
                ),
                "notes": _truncate_utf8(_string(entry.get("notes")), 2048),
                "cwes": _string_list(entry.get("cwes")),
                "catalog_version": _truncate_utf8(_string(raw.get("catalogVersion")), 128),
            },
        )
        candidates.append(
            ObservationCandidate(
                source_id="cisa.kev",
                source_item_key=cve,
                kind=ObservationKind.DOCUMENT,
                payload=payload,
                retrieved_at=retrieved_at,
                fetch_digest=fetch_digest,
                source_published_at=None,
                effective_at=None,
            )
        )
    schema_health = HealthValue.OK if rejected == 0 else HealthValue.DEGRADED
    return NormalizedBatch(
        candidates=tuple(candidates),
        records_received=len(vulnerabilities),
        records_rejected=rejected,
        schema_health=schema_health,
        details={
            "catalog_count": raw.get("count") if isinstance(raw.get("count"), int) else None,
            "catalog_version": _string(raw.get("catalogVersion")),
            "parser": "stdlib-json-v0",
        },
    )


def normalize_source(
    source_id: str,
    body: bytes,
    *,
    retrieved_at: datetime,
    fetch_digest: Digest,
) -> NormalizedBatch:
    if source_id == "pypi.updates":
        return normalize_pypi_updates(body, retrieved_at=retrieved_at, fetch_digest=fetch_digest)
    if source_id == "cisa.kev":
        return normalize_cisa_kev(body, retrieved_at=retrieved_at, fetch_digest=fetch_digest)
    raise NormalizationError("SOURCE_NORMALIZER_MISSING", f"no normalizer for {source_id}")
