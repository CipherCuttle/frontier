# ruff: noqa: E402
"""WP12b (G11): the full experiment lifecycle proof on live PostgreSQL.

One complete chain against a FRESH database (no SQLite substitution, no
cross-test pollution — the scratch database is created, used and destroyed by
this test):

1. fresh database -> ``alembic upgrade head`` -> readiness contract assertion
   (``EXPECTED_DATABASE_REVISION`` matches the migration head);
2. canonical source evidence acquired through the REAL acquisition boundary
   (registry contracts + fetch policy + static bounded fetcher) for three
   registry sources: ``pypi.updates`` (qualifying SOFTWARE_PACKAGES anchor),
   ``cisa.kev`` (qualifying SECURITY_VULNERABILITIES anchor) and
   ``hn.frontpage`` (never a domain anchor);
3. the orchestrator runs one DEV PEF_V0 boundary on that evidence (baseline
   snapshot and paired shadow run are built and published by the production
   paths);
4. the candidate PEF artifact is re-derived and published (determinism proof:
   identical inputs re-run against the same persisted control reproduce the
   run's candidate artifact id byte-identically);
5. the paired snapshot is reconstructed from the DB (WP4 loader) and evaluated
   by the persisted evaluator; the evaluation receipt is persisted;
6. the read plane is exercised through the real ASGI/HTTP app (public +
   experimental GET endpoints);
7. determinism: re-running the orchestrator cycle is an idempotent
   ALREADY_COMPLETE with the identical run id, and a second evaluation is the
   identical receipt;
8. the scenario asserts NO confirmatory evidence exists (DEV-only: zero
   CONFIRMATORY runs, a confirmatory cycle on a fresh boundary fails closed at
   the binding gates before any freeze receipt exists, and the persisted
   evaluation is a DEV evaluation that never carries a verdict);
9. backup (``pg_dump``) -> destroy (DROP DATABASE) -> recreate+migrate ->
   restore (data-only) -> readiness -> replay (positive gauntlet control):
   every scientific digest re-derives byte-identically from the restored
   database, including the evaluation receipt.

Requires ``FRONTIER_E2E_DATABASE_URL`` (a PostgreSQL server URL on which this
test may CREATE/DROP scratch databases) and ``docker`` for the version-matched
``pg_dump``/``pg_restore`` client (SKIP pattern like every other PG test).
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import replace as dataclass_replace
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path
from typing import LiteralString, Protocol, cast
from urllib.parse import urlsplit

import pytest

psycopg = pytest.importorskip("psycopg")

from fastapi.testclient import TestClient
from httpx import Response
from psycopg import Connection, sql

from frontier.adapters.acquisition.config import (
    SourceRegistry,
    load_fetch_policy,
    load_source_registry,
)
from frontier.adapters.api.public_read import create_public_read_app
from frontier.adapters.postgres import PostgresEvidenceStore
from frontier.adapters.postgres.advanced_intelligence import (
    PostgresCandidateFreezeRepository,
    PostgresEvaluationRepository,
    PostgresPefArtifactRepository,
)
from frontier.adapters.postgres.evaluation_store import PostgresEvaluationArtifactStore
from frontier.adapters.postgres.experiment_attempts import (
    PostgresExperimentAttemptRepository,
    PostgresShadowRunPersister,
)
from frontier.adapters.postgres.experimental_read import PostgresExperimentalReadRepository
from frontier.adapters.postgres.frozen_registry_intelligence import (
    PostgresFrozenRegistryBaselineIntelligenceRepository,
)
from frontier.adapters.postgres.intelligence import PostgresBaselineIntelligenceRepository
from frontier.adapters.postgres.public_read import PostgresPublicReadRepository
from frontier.adapters.postgres.readiness import (
    EXPECTED_DATABASE_REVISION,
    verify_database_readiness,
)
from frontier.application.acquisition import AcquisitionResult, AcquisitionService
from frontier.application.advanced_intelligence import run_pef_v0_ranking, run_shadow_experiment
from frontier.application.evaluation import evaluate_shadow_experiment_from_persisted
from frontier.application.evaluation_loaders import PersistedRunRef, load_paired_snapshot
from frontier.application.experiment_orchestration import (
    ExperimentCycleAction,
    ExperimentOrchestrator,
    ShadowExperimentRunner,
)
from frontier.application.experimental_read import ExperimentalReadService
from frontier.application.intelligence import run_baseline_intelligence
from frontier.application.public_read import PublicReadService
from frontier.contracts.fetch import BoundedFetchResult, FetchOutcome, FetchRequest
from frontier.domain.advanced_intelligence import ShadowExperimentRun
from frontier.domain.candidate_freeze import (
    CandidateFreezeReceipt,
    FreezeInputs,
    build_candidate_freeze_receipt,
)
from frontier.domain.canonical_json import canonical_json_bytes
from frontier.domain.collection import CollectionRunStatus
from frontier.domain.digests import Digest, sha256_digest
from frontier.domain.evaluation import (
    DOMAIN_SECURITY_VULNERABILITIES,
    DOMAIN_SOFTWARE_PACKAGES,
    DOMAIN_UNQUALIFIED,
    classify_anchor_domain,
)
from frontier.domain.grouping import GroupingRelationInput
from frontier.domain.intelligence import (
    BaselineHealthInput,
    BaselineObservationInput,
    BaselineSnapshot,
)
from frontier.domain.receipt import ProjectionReceipt

ROOT = Path(__file__).resolve().parents[2]

ADMIN_URL = os.getenv("FRONTIER_E2E_DATABASE_URL")
POSTGRES_IMAGE = os.getenv("FRONTIER_E2E_POSTGRES_IMAGE", "postgres:18")
pytestmark = [
    pytest.mark.skipif(not ADMIN_URL, reason="FRONTIER_E2E_DATABASE_URL not set"),
    pytest.mark.skipif(shutil.which("docker") is None, reason="docker not available"),
]

DATABASE_NAME = "frontier_e2e_" + uuid.uuid4().hex[:10]

# The DEV boundary sits ~30 minutes in the future relative to module import so
# that observations (observed_at = clock_timestamp() at insert) and health rows
# are always inside the snapshot horizon, while the boundary itself stays an
# exact 300 s-aligned UTC instant (preregistration cadence).
_BASE = (int(datetime.now(tz=UTC).timestamp()) // 300) * 300
BOUNDARY = datetime.fromtimestamp(_BASE + 300 * 6, tz=UTC)
INGEST_AT = datetime.fromtimestamp(_BASE - 300, tz=UTC)
EVALUATION_HORIZON = BOUNDARY + timedelta(hours=1)

REGISTRY_VERSION = Digest(
    cast(
        str,
        json.loads((ROOT / "sources" / "registry" / "registry_v0.json").read_text())[
            "source_registry_version"
        ],
    )
)

SOURCE_IDS = ("pypi.updates", "cisa.kev", "hn.frontpage")

# The candidate freeze receipt binds the REAL preregistration document
# (file digest + configuration digest recomputed from the document) plus the
# integrated source registry digest the whole chain uses. The operator-side
# values (commit/tree/lock) are pinned constants so the receipt identity is
# deterministic within a test session.
_PREREG_PATH = ROOT / "experiments" / "advanced_intelligence" / "pef_v0" / "preregistration.json"
_PREREG_DOCUMENT = cast("dict[str, object]", json.loads(_PREREG_PATH.read_text(encoding="utf-8")))
_PREREG_CONFIG = cast(
    "dict[str, object]",
    cast("dict[str, object]", _PREREG_DOCUMENT["candidate"])["configuration"],
)
FROZEN_AT = datetime.fromtimestamp(_BASE - 300, tz=UTC)
FREEZE = build_candidate_freeze_receipt(
    FreezeInputs(
        preregistration_digest=sha256_digest(_PREREG_PATH.read_bytes()),
        preregistration_config_digest=sha256_digest(canonical_json_bytes(_PREREG_CONFIG)),
        implementation_commit="e" * 64,
        implementation_tree_digest="f" * 64,
        dependency_lock_digest=Digest("sha256:" + "3" * 64),
        source_registry_digest=REGISTRY_VERSION,
        registry_entry_digests=(),
    ),
    frozen_at=FROZEN_AT,
)
assert FREEZE.status.value == "FROZEN"


def _rfc822_text(moment: datetime) -> str:
    return format_datetime(moment).replace("+0000", " GMT")


def _iso_date(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d")


_PUB = datetime.fromtimestamp(_BASE - 300 * 2, tz=UTC)
_PUB_RFC822 = _rfc822_text(_PUB).encode()
_PUB_ISO_DATE = _iso_date(_PUB).encode()

PYPI_BODY = (
    b'<?xml version="1.0" encoding="utf-8"?>'
    b'<rss version="2.0"><channel><title>PyPI recent updates</title>'
    b"<item><title>e2elifecyclealpha 1.0.0</title>"
    b"<link>https://pypi.org/project/e2elifecyclealpha/1.0.0/</link>"
    b"<description>Frontier E2E alpha probe</description>"
    b"<pubDate>" + _PUB_RFC822 + b"</pubDate></item>"
    b"<item><title>e2elifecyclebeta 0.3.1</title>"
    b"<link>https://pypi.org/project/e2elifecyclebeta/0.3.1/</link>"
    b"<description>E2E beta probe</description>"
    b"<pubDate>" + _PUB_RFC822 + b"</pubDate></item>"
    b"</channel></rss>"
)

CISA_BODY = json.dumps(
    {
        "count": 2,
        "catalogVersion": "e2e-lifecycle-v0",
        "dateReleased": _PUB_RFC822.decode(),
        "vulnerabilities": [
            {
                "cveID": "CVE-2026-01011",
                "vulnerabilityName": "E2E lifecycle probe vulnerability one",
                "shortDescription": "Deterministic probe description one.",
                "requiredAction": "Apply the probe patch.",
                "vendorProject": "E2E",
                "product": "probe-one",
                "dateAdded": _PUB_ISO_DATE.decode(),
                "dueDate": _PUB_ISO_DATE.decode(),
                "knownRansomwareCampaignUse": "Unknown",
                "notes": "E2E lifecycle probe.",
                "cwes": ["CWE-1234"],
            },
            {
                "cveID": "CVE-2026-01012",
                "vulnerabilityName": "E2E lifecycle probe vulnerability two",
                "shortDescription": "Deterministic probe description two.",
                "requiredAction": "Apply the probe patch.",
                "vendorProject": "E2E",
                "product": "probe-two",
                "dateAdded": _PUB_ISO_DATE.decode(),
                "dueDate": _PUB_ISO_DATE.decode(),
                "knownRansomwareCampaignUse": "Unknown",
                "notes": "E2E lifecycle probe.",
                "cwes": ["CWE-5678"],
            },
        ],
    }
).encode()

HN_BODY = (
    b'<rss version="2.0"><channel><title>Hacker News Frontpage</title>'
    b"<item><title>Frontier E2E attention probe one</title>"
    b"<link>https://example.test/e2e-hn-one</link>"
    b"<comments>https://news.ycombinator.com/item?id=960001</comments></item>"
    b"<item><title>Frontier E2E attention probe two</title>"
    b"<link>https://example.test/e2e-hn-two</link>"
    b"<comments>https://news.ycombinator.com/item?id=960002</comments></item>"
    b"</channel></rss>"
)

BODIES: dict[str, bytes] = {
    "pypi.updates": PYPI_BODY,
    "cisa.kev": CISA_BODY,
    "hn.frontpage": HN_BODY,
}

ConnectionT = Connection[tuple[object, ...]]


@dataclass(frozen=True, slots=True)
class _Identity:
    """Scientific identity captured before the destroy/restore round trip."""

    run_id: str
    run_digest: str
    snapshot_id: str
    baseline_receipt_id: str
    baseline_receipt_output_digest: str
    artifact_id: str
    artifact_output_digest: str
    evaluation_id: str
    evaluation_receipt_digest: str
    row_counts: dict[str, int]


def _sqlalchemy_url(database_url: str) -> str:
    return database_url.replace("postgresql://", "postgresql+psycopg://", 1)


def _database_url(admin_url: str, database: str) -> str:
    return admin_url.rsplit("/", 1)[0] + "/" + database


def _migrate_head(database_url: str) -> None:
    environment = os.environ.copy()
    environment["FRONTIER_DATABASE_URL"] = _sqlalchemy_url(database_url)
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )


def _reset_database(admin_url: str, database: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(database))
        )
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))


def _drop_database(admin_url: str, database: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(database))
        )


def _pg_client_command(
    admin_url: str, executable: str, database: str, *arguments: str, interactive: bool = False
) -> tuple[list[str], dict[str, str]]:
    parsed = urlsplit(admin_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    user = parsed.username or "frontier"
    password = parsed.password or "frontier"
    environment = os.environ.copy()
    environment["PGPASSWORD"] = password
    command = ["docker", "run"]
    if interactive:
        command.append("-i")
    command.extend(
        [
            "--rm",
            "--network",
            "host",
            "-e",
            "PGPASSWORD",
            POSTGRES_IMAGE,
            executable,
            "-h",
            host,
            "-p",
            str(port),
            "-U",
            user,
            "-d",
            database,
            *arguments,
        ]
    )
    return command, environment


def _dump_database(admin_url: str, database: str, dump_path: Path) -> int:
    command, environment = _pg_client_command(
        admin_url, "pg_dump", database, "--format=custom", "--no-owner", "--no-privileges"
    )
    with dump_path.open("wb") as output:
        subprocess.run(command, check=True, env=environment, stdout=output)
    size = dump_path.stat().st_size
    assert size > 0, "backup artifact is empty"
    return size


class _StaticFetcher:
    """One canned bounded fetch per source (the hostile boundary is real).

    The response content type mirrors each registry contract's accepted
    content types so the acquire path validates like a real wire response.
    """

    def __init__(
        self,
        bodies: dict[str, bytes],
        *,
        registry: SourceRegistry,
        retrieved_at: datetime,
    ) -> None:
        self._bodies = bodies
        self._registry = registry
        self._retrieved_at = retrieved_at

    async def fetch(self, request: FetchRequest) -> BoundedFetchResult:
        body = self._bodies[request.source_id]
        accepted = self._registry.require(request.source_id).accepted_content_types
        content_type = accepted[0]
        return BoundedFetchResult(
            request_id=request.request_id,
            outcome=FetchOutcome.SUCCESS,
            retrieved_at=self._retrieved_at,
            original_url=request.url,
            final_url=request.url,
            redirect_chain=(),
            http_status=200,
            content_type=content_type,
            response_headers={"Content-Type": content_type},
            compressed_bytes=len(body),
            expanded_bytes=len(body),
            body_digest=sha256_digest(body),
            body=body,
            failure=None,
        )


def _acquire_sources(database_url: str) -> dict[str, AcquisitionResult]:
    registry = load_source_registry(ROOT)
    policy = load_fetch_policy(ROOT)
    results: dict[str, AcquisitionResult] = {}
    with psycopg.connect(database_url) as connection:
        store = PostgresEvidenceStore(connection)
        service = AcquisitionService(
            registry=registry,
            policy=policy,
            fetcher=_StaticFetcher(BODIES, registry=registry, retrieved_at=INGEST_AT),
            repository=store,
            clock=lambda: INGEST_AT,
            sleep=lambda _seconds: asyncio.sleep(0),
            jitter=lambda: 0.5,
        )
        for source_id in SOURCE_IDS:
            result = asyncio.run(service.acquire(source_id))
            assert result.status is CollectionRunStatus.SUCCESS, result.failure_code
            assert result.inserted >= 2
            results[source_id] = result
    return results


def _bound_runner(freeze: CandidateFreezeReceipt) -> ShadowExperimentRunner:
    """A canonical-context shadow runner that binds the resolved freeze receipt."""

    def runner(
        observations: tuple[BaselineObservationInput, ...],
        *,
        control_snapshot: BaselineSnapshot,
        control_receipt: ProjectionReceipt,
        generated_at: datetime,
        source_registry_version: Digest,
        candidate_freeze_receipt: CandidateFreezeReceipt | None,
    ) -> ShadowExperimentRun:
        return run_shadow_experiment(
            observations,
            control_snapshot=control_snapshot,
            control_receipt=control_receipt,
            generated_at=generated_at,
            source_registry_version=source_registry_version,
            candidate_freeze_receipt=freeze,
        )

    return runner


def _orchestrator(
    connection: ConnectionT, *, run_class: str, worker_id: str
) -> ExperimentOrchestrator:
    baseline_repository = (
        PostgresFrozenRegistryBaselineIntelligenceRepository(connection, load_source_registry(ROOT))
        if run_class == "CONFIRMATORY"
        else PostgresBaselineIntelligenceRepository(connection)
    )
    return ExperimentOrchestrator(
        attempts=PostgresExperimentAttemptRepository(connection),
        baseline_repository=baseline_repository,
        persistence=PostgresShadowRunPersister(connection),
        source_registry_version=REGISTRY_VERSION,
        run_class=run_class,
        canonical_context=True,
        worker_id=worker_id,
        lease_seconds=1.0,
        clock=lambda: BOUNDARY,
    )


def _bound_orchestrator(connection: ConnectionT, *, worker_id: str) -> ExperimentOrchestrator:
    return ExperimentOrchestrator(
        attempts=PostgresExperimentAttemptRepository(connection),
        baseline_repository=PostgresBaselineIntelligenceRepository(connection),
        persistence=PostgresShadowRunPersister(connection),
        source_registry_version=REGISTRY_VERSION,
        freeze_binding=None,
        shadow_runner=_bound_runner(FREEZE),
        run_class="DEV",
        canonical_context=True,
        worker_id=worker_id,
        lease_seconds=1.0,
        clock=lambda: BOUNDARY,
    )


def _scalar(connection: ConnectionT, query: LiteralString, *params: object) -> int:
    with connection.cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
    assert row is not None
    return int(cast(int, row[0]))


def _control_inputs(
    baseline: PostgresBaselineIntelligenceRepository,
) -> tuple[
    tuple[BaselineObservationInput, ...],
    tuple[GroupingRelationInput, ...],
    tuple[str, ...],
    tuple[BaselineHealthInput, ...],
]:
    """One deterministic fetch of the eligible universe (R1/R6 ordering)."""
    observations = tuple(
        sorted(
            baseline.list_baseline_observations_as_of(BOUNDARY),
            key=lambda item: item.observation_id,
        )
    )
    relations = tuple(baseline.list_grouping_relations_as_of(BOUNDARY))
    enabled = tuple(baseline.list_enabled_source_ids())
    health = tuple(baseline.list_latest_health_as_of(BOUNDARY))
    return observations, relations, enabled, health


def _run_dev_chain(connection: ConnectionT) -> tuple[str, _Identity]:
    """Orchestrator DEV cycle -> artifact publication -> evaluation -> identity."""
    baseline = PostgresBaselineIntelligenceRepository(connection)
    # The candidate freeze receipt is recorded through the canonical freeze
    # workflow first; the DEV cycle then binds it (durable stamp is authority
    # data, never confirmatory promotion).
    PostgresCandidateFreezeRepository(connection, persistence_authorized=True).record_receipt(
        FREEZE
    )
    orchestrator = _bound_orchestrator(connection, worker_id="worker.e2e.dev")
    first = orchestrator.run_cycle(now=BOUNDARY)
    assert first.action is ExperimentCycleAction.RAN, first.detail
    assert first.run_id is not None
    run_id = first.run_id

    # Determinism/idempotency: the boundary is DONE; a re-run never re-executes
    # and never creates a second run row.
    second = orchestrator.run_cycle(now=BOUNDARY)
    assert second.action is ExperimentCycleAction.ALREADY_COMPLETE
    # Content-derived identity: still exactly one retained run row.
    assert (
        _scalar(
            connection,
            "SELECT count(*) FROM shadow_experiment_runs WHERE run_id = %s",
            run_id,
        )
        == 1
    )

    # The candidate artifact is re-derived deterministically from the SAME
    # persisted universe (one fetch, pinned generated_at) and published.
    observations, relations, enabled, health = _control_inputs(baseline)
    control = run_baseline_intelligence(
        baseline,
        as_of=BOUNDARY,
        generated_at=BOUNDARY,
        source_registry_version=REGISTRY_VERSION,
        observations=observations,
        relations=relations,
        enabled_source_ids=enabled,
        health=health,
    )
    candidate = run_pef_v0_ranking(
        observations,
        control_snapshot=control.snapshot,
        control_receipt=control.receipt,
        generated_at=BOUNDARY,
        source_registry_version=REGISTRY_VERSION,
    )
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT candidate_artifact_id, candidate_output_digest, run_digest
            FROM shadow_experiment_runs WHERE run_id = %s
            """,
            (run_id,),
        )
        row = cur.fetchone()
    assert row is not None
    artifact_id = cast(str, row[0])
    candidate_output_digest = cast(str, row[1])
    run_digest = cast(str, row[2])
    assert str(candidate.artifact.artifact_id) == artifact_id
    assert str(candidate.artifact.output_digest) == candidate_output_digest
    PostgresPefArtifactRepository(connection).publish_complete_artifact(
        candidate.artifact, candidate.receipt
    )

    # Reconstruct the paired snapshot from the DB (WP4 loader) and evaluate.
    store = PostgresEvaluationArtifactStore(connection)
    loaded = load_paired_snapshot(store, run_id, as_of=BOUNDARY)
    assert loaded.run_class == "DEV"
    receipt = evaluate_shadow_experiment_from_persisted(
        store=store,
        runs=(PersistedRunRef(run_id, BOUNDARY),),
        opportunity_groups=(),
        evaluation_horizon=EVALUATION_HORIZON,
        generated_at=EVALUATION_HORIZON,
        receipt_repository=PostgresEvaluationRepository(connection),
    )
    replayed = evaluate_shadow_experiment_from_persisted(
        store=store,
        runs=(PersistedRunRef(run_id, BOUNDARY),),
        opportunity_groups=(),
        evaluation_horizon=EVALUATION_HORIZON,
        generated_at=EVALUATION_HORIZON,
        receipt_repository=PostgresEvaluationRepository(connection),
    )
    assert replayed.evaluation_id == receipt.evaluation_id

    identity = _Identity(
        run_id=run_id,
        run_digest=run_digest,
        snapshot_id=control.snapshot.snapshot_id,
        baseline_receipt_id=control.receipt.receipt_id,
        baseline_receipt_output_digest=str(control.receipt.output_digest),
        artifact_id=str(candidate.artifact.artifact_id),
        artifact_output_digest=str(candidate.artifact.output_digest),
        evaluation_id=receipt.evaluation_id,
        evaluation_receipt_digest=str(receipt.receipt_digest),
        row_counts={},
    )
    return run_id, identity


_COUNT_QUERIES: dict[str, LiteralString] = {
    "sources": "SELECT count(*) FROM sources",
    "observations": "SELECT count(*) FROM observations",
    "collection_runs": "SELECT count(*) FROM collection_runs",
    "source_health_observations": "SELECT count(*) FROM source_health_observations",
    "baseline_intelligence_snapshots": "SELECT count(*) FROM baseline_intelligence_snapshots",
    "pef_ranking_artifacts": "SELECT count(*) FROM pef_ranking_artifacts",
    "shadow_experiment_runs": "SELECT count(*) FROM shadow_experiment_runs",
    "evaluation_receipts": "SELECT count(*) FROM evaluation_receipts",
    "projection_receipts": "SELECT count(*) FROM projection_receipts",
}


def _capture_row_counts(connection: ConnectionT) -> dict[str, int]:
    return {table: _scalar(connection, query) for table, query in _COUNT_QUERIES.items()}


def _read_plane_surfaces(database_url: str, run_id: str) -> None:
    """Exercise the real ASGI read plane (public + experimental GET only)."""
    repository = PostgresPublicReadRepository.connect(database_url)
    experimental = PostgresExperimentalReadRepository.connect(database_url)
    try:
        app = create_public_read_app(
            PublicReadService(repository),
            experimental_service=ExperimentalReadService(experimental),
        )
        client = cast(_GetClient, TestClient(app))
        assert client.get("/v0/meta").status_code == 200
        assert client.get("/v0/radar").status_code == 200
        assert client.get("/v0/health").status_code == 200
        status = client.get("/v0/experimental/status")
        assert status.status_code == 200
        assert "EXPERIMENTAL_SHADOW" in status.text
        runs = client.get("/v0/experimental/shadow-runs")
        assert runs.status_code == 200
        latest_run = runs.json()["latest"]
        assert latest_run is not None and latest_run["run_id"] == run_id
        detail = client.get(f"/v0/experimental/runs/{run_id}")
        assert detail.status_code == 200
        body = detail.json()
        assert body["availability"] == "AVAILABLE"
        assert body["run"] is not None
        assert body["run"]["run_id"] == run_id
        assert body["run"]["run_class"] == "DEV"
        artifacts = client.get("/v0/experimental/pef-artifacts")
        assert artifacts.status_code == 200
        assert artifacts.json()["latest"] is not None
        evaluations = client.get("/v0/experimental/evaluation-receipts")
        assert evaluations.status_code == 200
        assert evaluations.json()["latest"] is not None
        history = client.get("/v0/experimental/history")
        assert history.status_code == 200
        assert any(entry["run_id"] == run_id for entry in history.json()["runs"])
    finally:
        experimental.close()
        repository.close()


class _GetClient(Protocol):
    def get(self, url: str, *, params: Mapping[str, str] | None = None) -> Response: ...


def test_g11_full_experiment_lifecycle_on_live_postgres(tmp_path: Path) -> None:
    assert ADMIN_URL is not None
    database = DATABASE_NAME
    database_url = _database_url(ADMIN_URL, database)
    try:
        # --- fresh database + migrations + readiness contract ---------------
        _reset_database(ADMIN_URL, database)
        _migrate_head(database_url)
        with psycopg.connect(database_url, autocommit=True) as connection:
            readiness = verify_database_readiness(connection)
            assert readiness.migration_revision == EXPECTED_DATABASE_REVISION
            assert readiness.migration_revision == "0013_freeze_publication"

        # --- canonical acquisition through the hostile boundary -------------
        acquired = _acquire_sources(database_url)
        assert set(acquired) == set(SOURCE_IDS)
        # Qualifying domain anchors resolve per the frozen V0 taxonomy and the
        # attention source never assigns a domain.
        assert classify_anchor_domain(("pypi.updates",)) == DOMAIN_SOFTWARE_PACKAGES
        assert classify_anchor_domain(("cisa.kev",)) == DOMAIN_SECURITY_VULNERABILITIES
        assert classify_anchor_domain(("hn.frontpage",)) == DOMAIN_UNQUALIFIED

        with psycopg.connect(database_url, autocommit=True) as connection:
            # DEV-only proof (part 1): with NO bound candidate freeze receipt,
            # the confirmatory path fails closed at the binding gates and no
            # confirmatory run can be manufactured.
            confirmatory = _orchestrator(
                connection, run_class="CONFIRMATORY", worker_id="worker.e2e-conf"
            )
            denied = confirmatory.run_cycle(now=BOUNDARY + timedelta(seconds=300))
            assert denied.action is ExperimentCycleAction.SKIPPED_CONFIRMATORY_GATES
            assert "no candidate freeze receipt is bound" in (denied.detail or "")
            assert (
                _scalar(
                    connection,
                    "SELECT count(*) FROM shadow_experiment_runs WHERE as_of = %s",
                    BOUNDARY + timedelta(seconds=300),
                )
                == 0
            )

            # DEV chain: freeze receipt recorded, DEV cycle bound to it.
            run_id, identity = _run_dev_chain(connection)

            identity = dataclass_replace(identity, row_counts=_capture_row_counts(connection))
            # DEV-only scenario: zero confirmatory runs exist at any point.
            assert (
                _scalar(
                    connection,
                    "SELECT count(*) FROM shadow_experiment_runs WHERE run_class = 'CONFIRMATORY'",
                )
                == 0
            )

        assert run_id is not None
        _read_plane_surfaces(database_url, run_id)

        # --- backup -> destroy -> restore -> replay --------------------------
        dump_path = tmp_path / f"{database}.dump"
        _dump_database(ADMIN_URL, database, dump_path)
        _drop_database(ADMIN_URL, database)
        with psycopg.connect(ADMIN_URL, autocommit=True) as connection:
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        _migrate_head(database_url)
        with (
            psycopg.connect(database_url, autocommit=True) as connection,
            connection.cursor() as cur,
        ):
            # Make room for the dumped alembic_version row.
            cur.execute("DELETE FROM alembic_version")
        command, environment = _pg_client_command(
            ADMIN_URL,
            "pg_restore",
            database,
            "--exit-on-error",
            "--data-only",
            "--disable-triggers",
            "--no-owner",
            "--no-privileges",
            interactive=True,
        )
        with dump_path.open("rb") as backup:
            subprocess.run(command, check=True, env=environment, stdin=backup)

        with psycopg.connect(database_url, autocommit=True) as connection:
            # Readiness still holds on the restored database.
            verify_database_readiness(connection)
            # Row identity survived the destroy/restore round trip.
            assert _capture_row_counts(connection) == identity.row_counts
            # Positive gauntlet control: the restored artifacts replay.
            baseline = PostgresBaselineIntelligenceRepository(connection)
            observations, relations, enabled, health = _control_inputs(baseline)
            control = run_baseline_intelligence(
                baseline,
                as_of=BOUNDARY,
                generated_at=BOUNDARY,
                source_registry_version=REGISTRY_VERSION,
                observations=observations,
                relations=relations,
                enabled_source_ids=enabled,
                health=health,
            )
            assert control.snapshot.snapshot_id == identity.snapshot_id
            assert control.receipt.receipt_id == identity.baseline_receipt_id
            assert str(control.receipt.output_digest) == identity.baseline_receipt_output_digest
            candidate = run_pef_v0_ranking(
                observations,
                control_snapshot=control.snapshot,
                control_receipt=control.receipt,
                generated_at=BOUNDARY,
                source_registry_version=REGISTRY_VERSION,
            )
            assert str(candidate.artifact.artifact_id) == identity.artifact_id
            assert str(candidate.artifact.output_digest) == identity.artifact_output_digest
            # Idempotent re-publication of the identical restored identities.
            PostgresPefArtifactRepository(connection).publish_complete_artifact(
                candidate.artifact, candidate.receipt
            )
            store = PostgresEvaluationArtifactStore(connection)
            loaded = load_paired_snapshot(store, identity.run_id, as_of=BOUNDARY)
            assert str(loaded.run.run_digest) == identity.run_digest
            receipt = evaluate_shadow_experiment_from_persisted(
                store=store,
                runs=(PersistedRunRef(identity.run_id, BOUNDARY),),
                opportunity_groups=(),
                evaluation_horizon=EVALUATION_HORIZON,
                generated_at=EVALUATION_HORIZON,
                receipt_repository=PostgresEvaluationRepository(connection),
            )
            assert receipt.evaluation_id == identity.evaluation_id
            assert str(receipt.receipt_digest) == identity.evaluation_receipt_digest
            # A restored DEV run stays DEV and no confirmatory row exists.
            assert (
                _scalar(
                    connection,
                    "SELECT count(*) FROM shadow_experiment_runs WHERE run_id = %s "
                    "AND run_class = 'DEV'",
                    identity.run_id,
                )
                == 1
            )
            assert (
                _scalar(
                    connection,
                    "SELECT count(*) FROM shadow_experiment_runs WHERE run_class = 'CONFIRMATORY'",
                )
                == 0
            )

        _read_plane_surfaces(database_url, identity.run_id)
    finally:
        _drop_database(ADMIN_URL, database)
