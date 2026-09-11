from __future__ import annotations

import json
from dataclasses import replace

from frontier.application.ports.fetcher import FetcherPort
from frontier.contracts.fetch import BoundedFetchResult, FetchOutcome, FetchRequest

HF_FROZEN_URL = (
    "https://huggingface.co/api/models?sort=lastModified&direction=-1&limit=100&"
    "expand=author,createdAt,lastModified,pipeline_tag,sha,tags"
)
HF_LIVE_URL = (
    "https://huggingface.co/api/models?sort=lastModified&direction=-1&limit=100&"
    "expand=author&expand=createdAt&expand=lastModified&expand=pipeline_tag&"
    "expand=sha&expand=tags"
)
CISA_MIRROR_URL = (
    "https://raw.githubusercontent.com/cisagov/kev-data/develop/"
    "known_exploited_vulnerabilities.json"
)


class LiveSourceCompatibilityFetcher:
    """Apply narrow wire repairs only to the production live-acquisition path.

    PEF_V1 froze the source-registry digest, so the registry files cannot change
    during the confirmatory window. These repairs preserve the frozen logical
    source contracts while adapting two observed upstream wire quirks:

    * Hugging Face expects repeated ``expand=`` query parameters rather than the
      comma-packed list encoded in the frozen V0 URL.
    * CISA's declared same-authority GitHub mirror serves its JSON document as
      ``text/plain``. We classify that exact mirror response as JSON only after
      proving the response body is a JSON object. The raw Content-Type response
      header remains untouched for auditability.

    No other source, URL, MIME type, or non-success response is modified.
    """

    def __init__(self, inner: FetcherPort) -> None:
        self._inner = inner

    async def fetch(self, request: FetchRequest) -> BoundedFetchResult:
        wire_request = live_wire_request(request)
        result = await self._inner.fetch(wire_request)
        return live_wire_result(wire_request, result)


def live_wire_request(request: FetchRequest) -> FetchRequest:
    if request.source_id == "hf.models" and request.url == HF_FROZEN_URL:
        return replace(request, url=HF_LIVE_URL)
    return request


def live_wire_result(
    request: FetchRequest,
    result: BoundedFetchResult,
) -> BoundedFetchResult:
    if not (
        request.source_id == "cisa.kev"
        and request.url == CISA_MIRROR_URL
        and result.outcome is FetchOutcome.SUCCESS
        and result.http_status == 200
        and (result.content_type or "").lower() == "text/plain"
        and _is_json_object(result.body)
    ):
        return result
    return replace(result, content_type="application/json")


def _is_json_object(body: bytes | None) -> bool:
    if body is None:
        return False
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(value, dict)


__all__ = [
    "CISA_MIRROR_URL",
    "HF_FROZEN_URL",
    "HF_LIVE_URL",
    "LiveSourceCompatibilityFetcher",
    "live_wire_request",
    "live_wire_result",
]
