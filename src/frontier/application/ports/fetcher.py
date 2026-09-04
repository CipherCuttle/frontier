from __future__ import annotations

from typing import Protocol

from frontier.contracts.fetch import BoundedFetchResult, FetchRequest


class FetcherPort(Protocol):
    async def fetch(self, request: FetchRequest) -> BoundedFetchResult: ...
