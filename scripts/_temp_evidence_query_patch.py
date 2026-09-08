from pathlib import Path


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"expected exactly one anchor, found {text.count(old)}: {old[:80]!r}")
    return text.replace(old, new, 1)


# DOMAIN
path = Path("src/frontier/domain/public_read.py")
text = path.read_text()
text = replace_once(
    text,
    "PUBLIC_READ_DEFAULT_LIMIT = 50\nPUBLIC_READ_MAX_LIMIT = 100\n",
    "PUBLIC_READ_DEFAULT_LIMIT = 50\n"
    "PUBLIC_READ_MAX_LIMIT = 100\n"
    'EVIDENCE_QUERY_POLICY_VERSION = "evidence-query-lexical-filter-v0"\n'
    'EVIDENCE_QUERY_SEMANTIC_SCOPE = "BASELINE_SUBSTRATE_QUERY"\n'
    "EVIDENCE_QUERY_MAX_CODEPOINTS = 256\n"
    "EVIDENCE_QUERY_MAX_TOKENS = 12\n",
)
text = replace_once(
    text,
    'class ObservationNotFoundError(PublicReadFailure):\n    code = "OBSERVATION_NOT_FOUND"\n\n\nclass PublicViewKind(StrEnum):\n',
    'class ObservationNotFoundError(PublicReadFailure):\n    code = "OBSERVATION_NOT_FOUND"\n\n\n'
    'class EvidenceQueryInvalidError(PublicReadFailure):\n    code = "INVALID_QUERY"\n\n\n'
    'class PublicViewKind(StrEnum):\n',
)
text = replace_once(
    text,
    "@dataclass(frozen=True, slots=True)\n"
    "class PublicHealthRead:\n"
    "    snapshot: SnapshotBinding\n"
    "    generated_at: str\n"
    "    transport_state: str\n"
    "    freshness_state: str\n"
    "    coverage_state: str\n"
    "    schema_state: str\n"
    "    sources: tuple[SourceHealthRead, ...]\n\n\n"
    "def _episode_int",
    "@dataclass(frozen=True, slots=True)\n"
    "class PublicHealthRead:\n"
    "    snapshot: SnapshotBinding\n"
    "    generated_at: str\n"
    "    transport_state: str\n"
    "    freshness_state: str\n"
    "    coverage_state: str\n"
    "    schema_state: str\n"
    "    sources: tuple[SourceHealthRead, ...]\n\n\n"
    "@dataclass(frozen=True, slots=True)\n"
    "class EvidenceQueryItem:\n"
    "    episode: dict[str, CanonicalValue]\n"
    "    matched_observation_ids: tuple[str, ...]\n\n\n"
    "@dataclass(frozen=True, slots=True)\n"
    "class EvidenceQueryPage:\n"
    "    snapshot: SnapshotBinding\n"
    "    generated_at: str\n"
    "    transport_state: str\n"
    "    freshness_state: str\n"
    "    coverage_state: str\n"
    "    schema_state: str\n"
    "    query_policy_version: str\n"
    "    semantic_scope: str\n"
    "    query: str\n"
    "    normalized_tokens: tuple[str, ...]\n"
    "    total: int\n"
    "    limit: int\n"
    "    offset: int\n"
    "    items: tuple[EvidenceQueryItem, ...]\n\n\n"
    "def _episode_int",
)
if "def normalize_evidence_query(" in text:
    raise RuntimeError("evidence query domain code already exists")
text = text.rstrip() + '''


def normalize_evidence_query(query: str) -> tuple[str, ...]:
    trimmed = query.strip()
    if not trimmed or len(trimmed) > EVIDENCE_QUERY_MAX_CODEPOINTS:
        raise EvidenceQueryInvalidError("query length is outside the frozen bounds")
    tokens: list[str] = []
    seen: set[str] = set()
    for raw_token in trimmed.split():
        token = raw_token.casefold()
        if token not in seen:
            seen.add(token)
            tokens.append(token)
    if not tokens or len(tokens) > EVIDENCE_QUERY_MAX_TOKENS:
        raise EvidenceQueryInvalidError("query token count is outside the frozen bounds")
    return tuple(tokens)


def _append_payload_string_leaves(value: CanonicalValue, result: list[str]) -> None:
    if isinstance(value, str):
        result.append(value)
    elif isinstance(value, list):
        for item in value:
            _append_payload_string_leaves(item, result)
    elif isinstance(value, dict):
        for item in value.values():
            _append_payload_string_leaves(item, result)


def _observation_token_hits(
    observation: ObservationEvidenceRead,
    normalized_tokens: tuple[str, ...],
) -> frozenset[str]:
    searchable = [observation.source_item_key, observation.kind]
    _append_payload_string_leaves(observation.payload, searchable)
    folded = tuple(value.casefold() for value in searchable)
    return frozenset(
        token for token in normalized_tokens if any(token in value for value in folded)
    )


def evidence_query_snapshot_observation_ids(
    snapshot: ResolvedPublicSnapshot,
) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for episode in _ordered_episodes(snapshot.episodes):
        for observation_id in episode_observation_ids(episode):
            if observation_id not in seen:
                seen.add(observation_id)
                result.append(observation_id)
    return tuple(result)


def select_evidence_query(
    snapshot: ResolvedPublicSnapshot,
    observations_by_id: dict[str, ObservationEvidenceRead],
    *,
    query: str,
    normalized_tokens: tuple[str, ...],
    limit: int = PUBLIC_READ_DEFAULT_LIMIT,
    offset: int = 0,
) -> EvidenceQueryPage:
    expected_tokens = normalize_evidence_query(query)
    if normalized_tokens != expected_tokens:
        raise EvidenceQueryInvalidError("normalized query tokens do not match query")
    if limit < 1 or limit > PUBLIC_READ_MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {PUBLIC_READ_MAX_LIMIT}")
    if offset < 0:
        raise ValueError("offset must be non-negative")

    expected_observation_ids = evidence_query_snapshot_observation_ids(snapshot)
    if set(observations_by_id) != set(expected_observation_ids):
        raise SnapshotIntegrityError(
            "query evidence does not exactly match snapshot observation membership"
        )

    matches: list[EvidenceQueryItem] = []
    for episode in _ordered_episodes(snapshot.episodes):
        member_ids = episode_observation_ids(episode)
        covered_tokens: set[str] = set()
        matched_ids: list[str] = []
        for observation_id in member_ids:
            observation = observations_by_id[observation_id]
            hits = _observation_token_hits(observation, normalized_tokens)
            if hits:
                matched_ids.append(observation_id)
                covered_tokens.update(hits)
        if all(token in covered_tokens for token in normalized_tokens):
            matches.append(
                EvidenceQueryItem(
                    episode=episode,
                    matched_observation_ids=tuple(matched_ids),
                )
            )

    return EvidenceQueryPage(
        snapshot=snapshot.binding,
        generated_at=snapshot.generated_at,
        transport_state=snapshot.transport_state,
        freshness_state=snapshot.freshness_state,
        coverage_state=snapshot.coverage_state,
        schema_state=snapshot.schema_state,
        query_policy_version=EVIDENCE_QUERY_POLICY_VERSION,
        semantic_scope=EVIDENCE_QUERY_SEMANTIC_SCOPE,
        query=query,
        normalized_tokens=normalized_tokens,
        total=len(matches),
        limit=limit,
        offset=offset,
        items=tuple(matches[offset : offset + limit]),
    )
''' + "\n"
path.write_text(text)


# APPLICATION
path = Path("src/frontier/application/public_read.py")
text = path.read_text()
text = replace_once(
    text,
    "from frontier.domain.public_read import (\n    EpisodeEvidenceRead,\n",
    "from frontier.domain.public_read import (\n    EvidenceQueryPage,\n    EpisodeEvidenceRead,\n",
)
text = replace_once(
    text,
    "    SourceHealthRead,\n    episode_observation_ids,\n    find_episode,\n    select_public_view,\n)\n",
    "    SourceHealthRead,\n"
    "    episode_observation_ids,\n"
    "    evidence_query_snapshot_observation_ids,\n"
    "    find_episode,\n"
    "    normalize_evidence_query,\n"
    "    select_evidence_query,\n"
    "    select_public_view,\n"
    ")\n",
)
anchor = "    def get_episode(\n        self, episode_id: str, *, snapshot_id: str | None = None\n    ) -> EpisodeEvidenceRead:\n"
method = '''    def search_evidence(
        self,
        query: str,
        *,
        snapshot_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> EvidenceQueryPage:
        normalized_tokens = normalize_evidence_query(query)
        snapshot = self._repository.resolve_snapshot(snapshot_id)
        expected_ids = evidence_query_snapshot_observation_ids(snapshot)
        as_of = _parse_canonical_timestamp(snapshot.binding.as_of)
        observations = self._repository.list_observations(expected_ids, as_of=as_of)
        by_id = {item.observation_id: item for item in observations}
        if len(by_id) != len(observations):
            raise SnapshotIntegrityError(
                "public evidence repository returned duplicate query observations"
            )
        if set(by_id) != set(expected_ids):
            raise SnapshotIntegrityError(
                "query evidence does not exactly match snapshot observation membership"
            )
        return select_evidence_query(
            snapshot,
            by_id,
            query=query,
            normalized_tokens=normalized_tokens,
            limit=limit,
            offset=offset,
        )

'''
text = replace_once(text, anchor, method + anchor)
path.write_text(text)


# API
path = Path("src/frontier/adapters/api/public_read.py")
text = path.read_text()
text = replace_once(
    text,
    "from frontier.domain.public_read import (\n    PUBLIC_READ_API_VERSION,\n",
    "from frontier.domain.public_read import (\n    EVIDENCE_QUERY_MAX_CODEPOINTS,\n    PUBLIC_READ_API_VERSION,\n",
)
text = replace_once(
    text,
    "    EpisodeNotFoundError,\n    NoCompleteSnapshotError,\n",
    "    EpisodeNotFoundError,\n    EvidenceQueryInvalidError,\n    EvidenceQueryPage,\n    NoCompleteSnapshotError,\n",
)
text = replace_once(
    text,
    "OffsetQuery = Annotated[int, Query(ge=0)]\n",
    "OffsetQuery = Annotated[int, Query(ge=0)]\n"
    "EvidenceSearchQuery = Annotated[\n"
    "    str, Query(min_length=1, max_length=EVIDENCE_QUERY_MAX_CODEPOINTS)\n"
    "]\n",
)
models = '''class EvidenceQueryItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episode: EpisodeResponse
    matched_observation_ids: list[str]


class EvidenceQueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = PUBLIC_READ_RESPONSE_SCHEMA
    snapshot: SnapshotBindingResponse
    generated_at: str
    transport_state: str
    freshness_state: str
    coverage_state: str
    schema_state: str
    query_policy_version: str
    semantic_scope: str
    query: str
    normalized_tokens: list[str]
    total: int
    limit: int
    offset: int
    items: list[EvidenceQueryItemResponse]


'''
text = replace_once(text, "class CollectionOccurrenceResponse(BaseModel):\n", models + "class CollectionOccurrenceResponse(BaseModel):\n")
text = replace_once(
    text,
    "def _failure_status(exc: PublicReadFailure) -> int:\n"
    "    if isinstance(exc, (SnapshotNotFoundError, EpisodeNotFoundError, ObservationNotFoundError)):\n"
    "        return 404\n",
    "def _failure_status(exc: PublicReadFailure) -> int:\n"
    "    if isinstance(exc, EvidenceQueryInvalidError):\n"
    "        return 400\n"
    "    if isinstance(exc, (SnapshotNotFoundError, EpisodeNotFoundError, ObservationNotFoundError)):\n"
    "        return 404\n",
)
text = replace_once(
    text,
    "def _failure_detail(exc: PublicReadFailure) -> str:\n    if isinstance(exc, NoCompleteSnapshotError):\n",
    "def _failure_detail(exc: PublicReadFailure) -> str:\n"
    "    if isinstance(exc, EvidenceQueryInvalidError):\n"
    '        return "The evidence query is invalid."\n'
    "    if isinstance(exc, NoCompleteSnapshotError):\n",
)
text = replace_once(
    text,
    "def create_public_read_app(\n",
    "def _evidence_query_response(page: EvidenceQueryPage) -> EvidenceQueryResponse:\n"
    "    return EvidenceQueryResponse.model_validate(asdict(page))\n\n\n"
    "def create_public_read_app(\n",
)
endpoint = '''    def search_evidence(
        q: EvidenceSearchQuery,
        snapshot_id: SnapshotQuery = None,
        limit: LimitQuery = PUBLIC_READ_DEFAULT_LIMIT,
        offset: OffsetQuery = 0,
    ) -> EvidenceQueryResponse:
        page = service.search_evidence(q, snapshot_id=snapshot_id, limit=limit, offset=offset)
        return _evidence_query_response(page)

'''
text = replace_once(
    text,
    "    def episode(episode_id: str, snapshot_id: SnapshotQuery = None) -> EpisodeEvidenceResponse:\n",
    endpoint + "    def episode(episode_id: str, snapshot_id: SnapshotQuery = None) -> EpisodeEvidenceResponse:\n",
)
route = '''    app.add_api_route(
        "/v0/search",
        search_evidence,
        methods=["GET"],
        response_model=EvidenceQueryResponse,
        operation_id="searchEvidence",
    )
'''
text = replace_once(
    text,
    "    app.add_api_route(\n        \"/v0/episodes/{episode_id}\",\n",
    route + "    app.add_api_route(\n        \"/v0/episodes/{episode_id}\",\n",
)
path.write_text(text)


# DOMAIN/APPLICATION TESTS
path = Path("tests/unit/test_public_read.py")
text = path.read_text()
text = replace_once(
    text,
    "    ObservationEvidenceRead,\n    PublicViewKind,\n",
    "    EvidenceQueryInvalidError,\n    ObservationEvidenceRead,\n    PublicViewKind,\n",
)
text = replace_once(
    text,
    "    SourceHealthRead,\n    select_public_view,\n)\n",
    "    SourceHealthRead,\n    normalize_evidence_query,\n    select_public_view,\n)\n",
)
if "class _QueryRepository:" in text:
    raise RuntimeError("query tests already exist")
text = text.rstrip() + '''


class _QueryRepository:
    def __init__(self, *, returned_ids: tuple[str, ...] | None = None) -> None:
        self.ids = tuple("obs_" + char * 64 for char in "abcd")
        self.snapshot = _snapshot(
            _episode("episode-a", 1, observation_ids=[self.ids[0]]),
            _episode("episode-b", 2, observation_ids=[self.ids[1], self.ids[2]]),
            _episode("episode-c", 3, observation_ids=[self.ids[3]]),
        )
        self.returned_ids = returned_ids or self.ids

    def resolve_snapshot(self, snapshot_id: str | None = None) -> ResolvedPublicSnapshot:
        return self.snapshot

    def list_observations(
        self, observation_ids: tuple[str, ...], *, as_of: datetime
    ) -> list[ObservationEvidenceRead]:
        assert observation_ids == self.ids
        assert as_of == datetime(2026, 9, 5, 12, tzinfo=UTC)
        return [self._observation(observation_id) for observation_id in self.returned_ids]

    def get_observation(
        self, observation_id: str, *, as_of: datetime
    ) -> ObservationEvidenceRead | None:
        return self._observation(observation_id)

    def list_source_health(self, *, as_of: datetime) -> list[SourceHealthRead]:
        return []

    def _observation(self, observation_id: str) -> ObservationEvidenceRead:
        index = self.ids.index(observation_id) if observation_id in self.ids else -1
        payloads: list[dict[str, CanonicalValue]] = [
            {"title": "Frontier Agent needle", "secretword": "benign", "count": 12345},
            {"left": "alpha needle"},
            {"right": "beta"},
            {"title": "needle needle needle"},
        ]
        source_item_keys = ["item-a", "item-b", "item-c", "special-item-key"]
        kinds = ["DOCUMENT", "DOCUMENT", "DOCUMENT", "SPECIAL_KIND"]
        return ObservationEvidenceRead(
            observation_id=observation_id,
            schema_version="observation-v1",
            canonicalization_version="frontier-canonical-json-v1",
            source_id="fixture.source",
            source_item_key=source_item_keys[index] if index >= 0 else "outside-item",
            kind=kinds[index] if index >= 0 else "DOCUMENT",
            payload=payloads[index] if index >= 0 else {"title": "outside needle"},
            source_published_at=None,
            effective_at=None,
            observed_at="2026-09-05T11:00:00.000000Z",
            retrieved_at="2026-09-05T11:00:00.000000Z",
            content_digest="sha256:" + "7" * 64,
            fetch_digest="sha256:" + "8" * 64,
            collection_occurrences=(),
            relations=(),
        )


def test_evidence_query_normalizes_casefold_and_deduplicates_tokens() -> None:
    assert normalize_evidence_query("  Alpha alpha BETA beta  ") == ("alpha", "beta")
    with pytest.raises(EvidenceQueryInvalidError):
        normalize_evidence_query("   ")
    with pytest.raises(EvidenceQueryInvalidError):
        normalize_evidence_query(" ".join(f"t{index}" for index in range(13)))
    with pytest.raises(EvidenceQueryInvalidError):
        normalize_evidence_query("x" * 257)


def test_evidence_query_matches_only_authorized_string_values_and_and_spans_observations() -> None:
    service = PublicReadService(_QueryRepository())
    page = service.search_evidence("frontier AGENT")
    assert page.normalized_tokens == ("frontier", "agent")
    assert [item.episode["rank"] for item in page.items] == [1]

    cross_observation = service.search_evidence("alpha beta")
    assert [item.episode["rank"] for item in cross_observation.items] == [2]
    assert cross_observation.items[0].matched_observation_ids == tuple(
        "obs_" + char * 64 for char in "bc"
    )

    assert service.search_evidence("secretword").total == 0
    assert service.search_evidence("12345").total == 0
    assert service.search_evidence("fixture.source").total == 0
    assert service.search_evidence("special-item-key").total == 1
    assert service.search_evidence("special_kind").total == 1


def test_evidence_query_preserves_baseline_order_and_filters_before_pagination() -> None:
    service = PublicReadService(_QueryRepository())
    page = service.search_evidence("needle", limit=1, offset=1)
    assert page.total == 3
    assert [item.episode["rank"] for item in page.items] == [2]
    assert page.query_policy_version == "evidence-query-lexical-filter-v0"
    assert page.semantic_scope == "BASELINE_SUBSTRATE_QUERY"


def test_evidence_query_requires_exact_snapshot_observation_membership() -> None:
    expected = tuple("obs_" + char * 64 for char in "abcd")
    with pytest.raises(SnapshotIntegrityError, match="exactly match"):
        PublicReadService(_QueryRepository(returned_ids=expected[:-1])).search_evidence("needle")
    with pytest.raises(SnapshotIntegrityError, match="duplicate"):
        PublicReadService(_QueryRepository(returned_ids=(*expected, expected[0]))).search_evidence(
            "needle"
        )
''' + "\n"
path.write_text(text)


# API TESTS
path = Path("tests/unit/test_public_read_api.py")
text = path.read_text()
text = replace_once(
    text,
    "    def list_observations(\n"
    "        self, observation_ids: tuple[str, ...], *, as_of: datetime\n"
    "    ) -> list[ObservationEvidenceRead]:\n"
    "        return []\n",
    "    def list_observations(\n"
    "        self, observation_ids: tuple[str, ...], *, as_of: datetime\n"
    "    ) -> list[ObservationEvidenceRead]:\n"
    "        return [\n"
    "            ObservationEvidenceRead(\n"
    "                observation_id=observation_id,\n"
    "                schema_version=\"observation-v1\",\n"
    "                canonicalization_version=\"frontier-canonical-json-v1\",\n"
    "                source_id=\"hn.frontpage\",\n"
    "                source_item_key=\"item-frontier\",\n"
    "                kind=\"DOCUMENT\",\n"
    "                payload={\"title\": \"Frontier Agent\"},\n"
    "                source_published_at=None,\n"
    "                effective_at=None,\n"
    "                observed_at=\"2026-09-05T11:59:00.000000Z\",\n"
    "                retrieved_at=\"2026-09-05T11:59:00.000000Z\",\n"
    "                content_digest=\"sha256:\" + \"7\" * 64,\n"
    "                fetch_digest=\"sha256:\" + \"8\" * 64,\n"
    "                collection_occurrences=(),\n"
    "                relations=(),\n"
    "            )\n"
    "            for observation_id in observation_ids\n"
    "        ]\n",
)
text = replace_once(
    text,
    '        "/v0/trending",\n        "/v0/episodes/{episode_id}",\n',
    '        "/v0/trending",\n        "/v0/search",\n        "/v0/episodes/{episode_id}",\n',
)
if "test_evidence_search_is_snapshot_bound_nonranking_and_auditable" in text:
    raise RuntimeError("query API tests already exist")
text = text.rstrip() + '''


def test_evidence_search_is_snapshot_bound_nonranking_and_auditable() -> None:
    client = cast(
        _GetClient,
        TestClient(create_public_read_app(PublicReadService(_FakeRepository()))),
    )
    response = client.get("/v0/search", params={"q": "frontier AGENT"})
    assert response.status_code == 200
    body = cast(dict[str, Any], response.json())
    assert body["query_policy_version"] == "evidence-query-lexical-filter-v0"
    assert body["semantic_scope"] == "BASELINE_SUBSTRATE_QUERY"
    assert body["normalized_tokens"] == ["frontier", "agent"]
    assert body["total"] == 1
    item = cast(dict[str, Any], cast(list[dict[str, Any]], body["items"])[0])
    episode = cast(dict[str, Any], item["episode"])
    assert episode["rank"] == 1
    assert "score" not in item
    assert item["matched_observation_ids"] == ["obs_" + "b" * 64]


def test_evidence_search_rejects_whitespace_only_query_explicitly() -> None:
    client = cast(
        _GetClient,
        TestClient(create_public_read_app(PublicReadService(_FakeRepository()))),
    )
    response = client.get("/v0/search", params={"q": "   "})
    assert response.status_code == 400
    assert cast(dict[str, Any], response.json()) == {
        "error": "INVALID_QUERY",
        "detail": "The evidence query is invalid.",
    }
''' + "\n"
path.write_text(text)


# CONTRACT GENERATOR AUTHORITY COMMENT
path = Path("scripts/generate_public_contracts.py")
text = path.read_text()
text = replace_once(
    text,
    '        "// Authority: ADR-0008 / PUBLIC_READ_PLANE_V0.",\n',
    '        "// Authority: ADR-0008 / PUBLIC_READ_PLANE_V0 / EVIDENCE_QUERY_V0.",\n',
)
path.write_text(text)
