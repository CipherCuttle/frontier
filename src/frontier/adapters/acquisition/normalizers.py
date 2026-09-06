from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qs, quote, unquote, urlsplit

from frontier.domain.canonical_json import CanonicalValue, canonical_json_bytes, canonical_timestamp
from frontier.domain.digests import Digest, sha256_hex
from frontier.domain.health import HealthValue
from frontier.domain.observation import (
    ArtifactPayload,
    DocumentPayload,
    ObservationCandidate,
    ObservationKind,
)

from .json_values import JsonValueError, parse_typed_json

_CVE_RE = re.compile(r"^CVE-\d{4}-\d{4,}$")
_CISA_CATALOG_URL = "https://www.cisa.gov/known-exploited-vulnerabilities-catalog"
_GDELT_MAX_RECORDS = 250
_HF_MODEL_LIMIT = 100
_ARXIV_MAX_RECORDS = 100
_GITHUB_REPO_LIMIT = 100
_ATOM_NS = "http://www.w3.org/2005/Atom"


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
    completeness_health: HealthValue = HealthValue.OK


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


def _iso_time(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _gdelt_time(value: str | None) -> datetime | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        parsed = datetime.strptime(stripped, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError:
        return _iso_time(stripped)
    return parsed


def _string(value: CanonicalValue | None) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _string_list(value: CanonicalValue | None, maximum_items: int = 64) -> list[CanonicalValue]:
    if not isinstance(value, list):
        return []
    result: list[CanonicalValue] = []
    for item in value[:maximum_items]:
        text = _string(item)
        if text is not None:
            result.append(_truncate_utf8(text, 512))
    return result


def _sorted_string_list(
    value: CanonicalValue | None, maximum_items: int = 64
) -> list[CanonicalValue]:
    if not isinstance(value, list):
        return []
    strings: set[str] = set()
    for item in value:
        text = _string(item)
        if text is None:
            continue
        truncated = _truncate_utf8(text, 512)
        if truncated is not None:
            strings.add(truncated)
    result: list[CanonicalValue] = []
    result.extend(sorted(strings)[:maximum_items])
    return result


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


def normalize_cisa_kev(
    body: bytes, *, retrieved_at: datetime, fetch_digest: Digest
) -> NormalizedBatch:
    try:
        raw = parse_typed_json(body)
    except JsonValueError as exc:
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
    count_value = raw.get("count")
    return NormalizedBatch(
        candidates=tuple(candidates),
        records_received=len(vulnerabilities),
        records_rejected=rejected,
        schema_health=schema_health,
        details={
            "catalog_count": count_value if isinstance(count_value, int) else None,
            "catalog_version": _string(raw.get("catalogVersion")),
            "parser": "stdlib-json-v0",
        },
    )


def _hn_item_key(link: str | None, comments: str | None, title: str) -> str:
    for candidate in (comments, link):
        if candidate is None:
            continue
        parsed = urlsplit(candidate)
        if parsed.hostname == "news.ycombinator.com" and parsed.path == "/item":
            item_id = parse_qs(parsed.query).get("id")
            if item_id and item_id[0].isdigit():
                return f"hn:{item_id[0]}"
    return "hn:" + sha256_hex(canonical_json_bytes({"link": link, "title": title}))


def normalize_hn_frontpage(
    body: bytes, *, retrieved_at: datetime, fetch_digest: Digest
) -> NormalizedBatch:
    lowered = body.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise NormalizationError("XML_DTD_FORBIDDEN", "DTD/entity declarations are forbidden")
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise NormalizationError("RSS_PARSE_FAILED", "Hacker News RSS is malformed") from exc
    items = root.findall("./channel/item")
    candidates: list[ObservationCandidate] = []
    rejected = 0
    malformed_time = 0
    for item in items:
        title = _text(item, "title")
        link = _text(item, "link")
        comments = _text(item, "comments")
        pub_date_text = _text(item, "pubDate")
        if title is None or (link is None and comments is None):
            rejected += 1
            continue
        published = _rss_time(pub_date_text)
        if pub_date_text is not None and published is None:
            malformed_time += 1
        canonical_url = link or comments
        payload = DocumentPayload(
            canonical_url=_truncate_utf8(canonical_url, 4096),
            title=_truncate_utf8(title, 2048),
            excerpt=None,
            language="en",
            source_metadata={
                "comments_url": _truncate_utf8(comments, 4096),
                "source_pub_date": _truncate_utf8(pub_date_text, 256),
            },
        )
        candidates.append(
            ObservationCandidate(
                source_id="hn.frontpage",
                source_item_key=_hn_item_key(link, comments, title),
                kind=ObservationKind.DOCUMENT,
                payload=payload,
                retrieved_at=retrieved_at,
                fetch_digest=fetch_digest,
                source_published_at=published,
                effective_at=None,
            )
        )
    schema_health = (
        HealthValue.OK if rejected == 0 and malformed_time == 0 else HealthValue.DEGRADED
    )
    return NormalizedBatch(
        candidates=tuple(candidates),
        records_received=len(items),
        records_rejected=rejected,
        schema_health=schema_health,
        details={
            "malformed_source_times": malformed_time,
            "parser": "stdlib-elementtree-v0",
            "surface": "frontpage",
        },
    )


def normalize_gdelt_frontier(
    body: bytes, *, retrieved_at: datetime, fetch_digest: Digest
) -> NormalizedBatch:
    try:
        raw = parse_typed_json(body)
    except JsonValueError as exc:
        raise NormalizationError("JSON_PARSE_FAILED", "GDELT JSON is malformed") from exc
    if not isinstance(raw, dict):
        raise NormalizationError("GDELT_SCHEMA_FAILED", "GDELT root must be an object")
    articles = raw.get("articles")
    if not isinstance(articles, list):
        raise NormalizationError("GDELT_SCHEMA_FAILED", "GDELT articles must be a list")
    candidates: list[ObservationCandidate] = []
    rejected = 0
    malformed_seen = 0
    for entry in articles:
        if not isinstance(entry, dict):
            rejected += 1
            continue
        url = _string(entry.get("url"))
        title = _string(entry.get("title"))
        if url is None or title is None:
            rejected += 1
            continue
        seen_text = _string(entry.get("seendate"))
        seen_at = _gdelt_time(seen_text)
        if seen_text is not None and seen_at is None:
            malformed_seen += 1
        payload = DocumentPayload(
            canonical_url=_truncate_utf8(url, 4096),
            title=_truncate_utf8(title, 2048),
            excerpt=None,
            language=_truncate_utf8(_string(entry.get("language")), 64),
            source_metadata={
                "discovery_surface": "GDELT_DOC_ARTLIST",
                "domain": _truncate_utf8(_string(entry.get("domain")), 512),
                "gdelt_seen_at": (
                    canonical_timestamp(seen_at)
                    if seen_at is not None
                    else _truncate_utf8(seen_text, 128)
                ),
                "social_image": _truncate_utf8(_string(entry.get("socialimage")), 4096),
                "source_country": _truncate_utf8(_string(entry.get("sourcecountry")), 256),
                "url_mobile": _truncate_utf8(_string(entry.get("url_mobile")), 4096),
            },
        )
        candidates.append(
            ObservationCandidate(
                source_id="gdelt.frontier",
                source_item_key=url,
                kind=ObservationKind.DOCUMENT,
                payload=payload,
                retrieved_at=retrieved_at,
                fetch_digest=fetch_digest,
                source_published_at=None,
                effective_at=None,
            )
        )
    saturated = len(articles) >= _GDELT_MAX_RECORDS
    schema_health = (
        HealthValue.OK if rejected == 0 and malformed_seen == 0 else HealthValue.DEGRADED
    )
    return NormalizedBatch(
        candidates=tuple(candidates),
        records_received=len(articles),
        records_rejected=rejected,
        schema_health=schema_health,
        completeness_health=HealthValue.DEGRADED if saturated else HealthValue.OK,
        details={
            "malformed_seen_times": malformed_seen,
            "parser": "stdlib-json-v0",
            "window_saturated": saturated,
        },
    )


def normalize_hf_models(
    body: bytes, *, retrieved_at: datetime, fetch_digest: Digest
) -> NormalizedBatch:
    try:
        raw = parse_typed_json(body)
    except JsonValueError as exc:
        raise NormalizationError("JSON_PARSE_FAILED", "Hugging Face JSON is malformed") from exc
    if not isinstance(raw, list):
        raise NormalizationError("HF_SCHEMA_FAILED", "Hugging Face model list must be an array")
    candidates: list[ObservationCandidate] = []
    rejected = 0
    malformed_time = 0
    for entry in raw:
        if not isinstance(entry, dict):
            rejected += 1
            continue
        model_id = _string(entry.get("id"))
        if model_id is None:
            rejected += 1
            continue
        sha = _string(entry.get("sha"))
        last_modified_text = _string(entry.get("lastModified"))
        created_text = _string(entry.get("createdAt"))
        last_modified = _iso_time(last_modified_text)
        created_at = _iso_time(created_text)
        if last_modified_text is not None and last_modified is None:
            malformed_time += 1
        if created_text is not None and created_at is None:
            malformed_time += 1
        payload = ArtifactPayload(
            artifact_type="huggingface-model-repo",
            name=_truncate_utf8(model_id, 2048) or model_id,
            version=_truncate_utf8(sha, 512),
            canonical_url=_truncate_utf8(
                f"https://huggingface.co/{quote(model_id, safe='/')}", 4096
            ),
            artifact_digest=None,
            source_metadata={
                "author": _truncate_utf8(_string(entry.get("author")), 512),
                "created_at": canonical_timestamp(created_at) if created_at is not None else None,
                "last_modified": (
                    canonical_timestamp(last_modified) if last_modified is not None else None
                ),
                "pipeline_tag": _truncate_utf8(_string(entry.get("pipeline_tag")), 256),
                "tags": _sorted_string_list(entry.get("tags"), maximum_items=32),
            },
        )
        candidates.append(
            ObservationCandidate(
                source_id="hf.models",
                source_item_key=model_id,
                kind=ObservationKind.ARTIFACT,
                payload=payload,
                retrieved_at=retrieved_at,
                fetch_digest=fetch_digest,
                source_published_at=last_modified,
                effective_at=None,
            )
        )
    saturated = len(raw) >= _HF_MODEL_LIMIT
    schema_health = (
        HealthValue.OK if rejected == 0 and malformed_time == 0 else HealthValue.DEGRADED
    )
    return NormalizedBatch(
        candidates=tuple(candidates),
        records_received=len(raw),
        records_rejected=rejected,
        schema_health=schema_health,
        completeness_health=HealthValue.DEGRADED if saturated else HealthValue.OK,
        details={
            "malformed_source_times": malformed_time,
            "parser": "stdlib-json-v0",
            "window_saturated": saturated,
        },
    )


def _atom_text(element: ET.Element, local_name: str) -> str | None:
    child = element.find(f"{{{_ATOM_NS}}}{local_name}")
    if child is None or child.text is None:
        return None
    value = " ".join(child.text.split())
    return value or None


def normalize_arxiv_cs_ai(
    body: bytes, *, retrieved_at: datetime, fetch_digest: Digest
) -> NormalizedBatch:
    lowered = body.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise NormalizationError("XML_DTD_FORBIDDEN", "DTD/entity declarations are forbidden")
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise NormalizationError("ATOM_PARSE_FAILED", "arXiv Atom feed is malformed") from exc
    entries = root.findall(f"{{{_ATOM_NS}}}entry")
    candidates: list[ObservationCandidate] = []
    rejected = 0
    malformed_time = 0
    for entry in entries:
        entry_id = _atom_text(entry, "id")
        title = _atom_text(entry, "title")
        published_text = _atom_text(entry, "published")
        updated_text = _atom_text(entry, "updated")
        if entry_id is None or title is None or len(entry_id.encode("utf-8")) > 4096:
            rejected += 1
            continue
        published = _iso_time(published_text)
        updated = _iso_time(updated_text)
        if published_text is not None and published is None:
            malformed_time += 1
        if updated_text is not None and updated is None:
            malformed_time += 1
        authors: list[str] = []
        for author in entry.findall(f"{{{_ATOM_NS}}}author"):
            name = _atom_text(author, "name")
            if name is not None:
                authors.append(name)
        category_values: list[CanonicalValue] = []
        category_values.extend(
            sorted(
                {
                    term
                    for category in entry.findall(f"{{{_ATOM_NS}}}category")
                    if (term := category.attrib.get("term"))
                }
            )[:32]
        )
        author_values: list[CanonicalValue] = []
        author_values.extend(_truncate_utf8(author, 512) or author for author in authors[:32])
        alternate_url: str | None = None
        for link in entry.findall(f"{{{_ATOM_NS}}}link"):
            if link.attrib.get("rel", "alternate") == "alternate" and link.attrib.get("href"):
                alternate_url = link.attrib["href"]
                break
        canonical_url = alternate_url or entry_id
        payload = DocumentPayload(
            canonical_url=_truncate_utf8(canonical_url, 4096),
            title=_truncate_utf8(title, 2048),
            excerpt=None,
            language=None,
            source_metadata={
                "arxiv_id": _truncate_utf8(entry_id, 512),
                "authors": author_values,
                "categories": category_values,
                "published": (
                    canonical_timestamp(published)
                    if published is not None
                    else _truncate_utf8(published_text, 128)
                ),
                "updated": (
                    canonical_timestamp(updated)
                    if updated is not None
                    else _truncate_utf8(updated_text, 128)
                ),
            },
        )
        candidates.append(
            ObservationCandidate(
                source_id="arxiv.cs-ai",
                source_item_key=entry_id,
                kind=ObservationKind.DOCUMENT,
                payload=payload,
                retrieved_at=retrieved_at,
                fetch_digest=fetch_digest,
                source_published_at=published,
                effective_at=None,
            )
        )
    saturated = len(entries) >= _ARXIV_MAX_RECORDS
    schema_health = (
        HealthValue.OK if rejected == 0 and malformed_time == 0 else HealthValue.DEGRADED
    )
    return NormalizedBatch(
        candidates=tuple(candidates),
        records_received=len(entries),
        records_rejected=rejected,
        schema_health=schema_health,
        completeness_health=HealthValue.DEGRADED if saturated else HealthValue.OK,
        details={
            "malformed_source_times": malformed_time,
            "parser": "stdlib-elementtree-atom-v0",
            "window_saturated": saturated,
        },
    )


def normalize_github_ml_repos(
    body: bytes, *, retrieved_at: datetime, fetch_digest: Digest
) -> NormalizedBatch:
    try:
        raw = parse_typed_json(body)
    except JsonValueError as exc:
        raise NormalizationError(
            "JSON_PARSE_FAILED", "GitHub repository search JSON is malformed"
        ) from exc
    if not isinstance(raw, dict):
        raise NormalizationError("GITHUB_SCHEMA_FAILED", "GitHub search root must be an object")
    items = raw.get("items")
    if not isinstance(items, list):
        raise NormalizationError("GITHUB_SCHEMA_FAILED", "GitHub search items must be a list")
    candidates: list[ObservationCandidate] = []
    rejected = 0
    malformed_time = 0
    for entry in items:
        if not isinstance(entry, dict):
            rejected += 1
            continue
        repo_id = entry.get("id")
        full_name = _string(entry.get("full_name"))
        html_url = _string(entry.get("html_url"))
        if (
            not isinstance(repo_id, int)
            or isinstance(repo_id, bool)
            or full_name is None
            or html_url is None
        ):
            rejected += 1
            continue
        created_text = _string(entry.get("created_at"))
        updated_text = _string(entry.get("updated_at"))
        pushed_text = _string(entry.get("pushed_at"))
        created = _iso_time(created_text)
        updated = _iso_time(updated_text)
        pushed = _iso_time(pushed_text)
        for text, parsed in (
            (created_text, created),
            (updated_text, updated),
            (pushed_text, pushed),
        ):
            if text is not None and parsed is None:
                malformed_time += 1
        event_time = pushed or updated
        payload = ArtifactPayload(
            artifact_type="github-repository",
            name=_truncate_utf8(full_name, 2048) or full_name,
            version=canonical_timestamp(event_time) if event_time is not None else None,
            canonical_url=_truncate_utf8(html_url, 4096),
            artifact_digest=None,
            source_metadata={
                "archived": (
                    entry.get("archived") if isinstance(entry.get("archived"), bool) else None
                ),
                "created_at": canonical_timestamp(created) if created is not None else None,
                "default_branch": _truncate_utf8(_string(entry.get("default_branch")), 512),
                "fork": entry.get("fork") if isinstance(entry.get("fork"), bool) else None,
                "github_repository_id": repo_id,
                "language": _truncate_utf8(_string(entry.get("language")), 256),
                "node_id": _truncate_utf8(_string(entry.get("node_id")), 512),
                "pushed_at": canonical_timestamp(pushed) if pushed is not None else None,
                "topics": _sorted_string_list(entry.get("topics"), maximum_items=32),
                "updated_at": canonical_timestamp(updated) if updated is not None else None,
            },
        )
        candidates.append(
            ObservationCandidate(
                source_id="github.ml-repos",
                source_item_key=f"github-repo:{repo_id}",
                kind=ObservationKind.ARTIFACT,
                payload=payload,
                retrieved_at=retrieved_at,
                fetch_digest=fetch_digest,
                source_published_at=event_time,
                effective_at=None,
            )
        )
    incomplete = raw.get("incomplete_results") is True
    saturated = len(items) >= _GITHUB_REPO_LIMIT
    schema_health = (
        HealthValue.OK if rejected == 0 and malformed_time == 0 else HealthValue.DEGRADED
    )
    return NormalizedBatch(
        candidates=tuple(candidates),
        records_received=len(items),
        records_rejected=rejected,
        schema_health=schema_health,
        completeness_health=HealthValue.DEGRADED if incomplete or saturated else HealthValue.OK,
        details={
            "malformed_source_times": malformed_time,
            "parser": "stdlib-json-v0",
            "search_incomplete": incomplete,
            "total_count": (
                raw.get("total_count") if isinstance(raw.get("total_count"), int) else None
            ),
            "window_saturated": saturated,
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
    if source_id == "hn.frontpage":
        return normalize_hn_frontpage(body, retrieved_at=retrieved_at, fetch_digest=fetch_digest)
    if source_id == "gdelt.frontier":
        return normalize_gdelt_frontier(body, retrieved_at=retrieved_at, fetch_digest=fetch_digest)
    if source_id == "hf.models":
        return normalize_hf_models(body, retrieved_at=retrieved_at, fetch_digest=fetch_digest)
    if source_id == "arxiv.cs-ai":
        return normalize_arxiv_cs_ai(body, retrieved_at=retrieved_at, fetch_digest=fetch_digest)
    if source_id == "github.ml-repos":
        return normalize_github_ml_repos(body, retrieved_at=retrieved_at, fetch_digest=fetch_digest)
    raise NormalizationError("SOURCE_NORMALIZER_MISSING", f"no normalizer for {source_id}")
