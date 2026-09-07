from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str, *, count: int = 1) -> None:
    file = ROOT / path
    text = file.read_text(encoding="utf-8")
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{path}: expected {count} replacement target(s), found {found}")
    file.write_text(text.replace(old, new), encoding="utf-8")


def patch_evaluation_loaders() -> None:
    path = "src/frontier/application/evaluation_loaders.py"
    replace_once(
        path,
        '''@dataclass(frozen=True, slots=True)
class PersistedFeatureVectorRow:
''',
        '''@dataclass(frozen=True, slots=True)
class PersistedFreezePublicationRow:
    receipt_id: str
    schema_version: str
    freeze_receipt_digest: str
    implementation_commit: str
    implementation_tree_digest: str
    publication_commit: str
    publication_committer_at: datetime
    publication_digest: str


@dataclass(frozen=True, slots=True)
class PersistedFeatureVectorRow:
''',
    )
    replace_once(
        path,
        '''    def fetch_freeze_receipt_row(self, receipt_id: str) -> PersistedFreezeReceiptRow | None: ...
    def fetch_feature_batch_rows(self, batch_id: str) -> tuple[PersistedFeatureVectorRow, ...]: ...
''',
        '''    def fetch_freeze_receipt_row(self, receipt_id: str) -> PersistedFreezeReceiptRow | None: ...
    def fetch_freeze_publication_row(
        self, receipt_id: str
    ) -> PersistedFreezePublicationRow | None: ...
    def fetch_feature_batch_rows(self, batch_id: str) -> tuple[PersistedFeatureVectorRow, ...]: ...
''',
    )
    replace_once(
        path,
        '''    "PersistedFeatureVectorRow",
    "PersistedFreezeReceiptRow",
''',
        '''    "PersistedFeatureVectorRow",
    "PersistedFreezePublicationRow",
    "PersistedFreezeReceiptRow",
''',
    )


def patch_postgres_store() -> None:
    path = "src/frontier/adapters/postgres/evaluation_store.py"
    replace_once(
        path,
        '''    PersistedFeatureVectorRow,
    PersistedFreezeReceiptRow,
''',
        '''    PersistedFeatureVectorRow,
    PersistedFreezePublicationRow,
    PersistedFreezeReceiptRow,
''',
    )
    marker = '''    def fetch_feature_batch_rows(self, batch_id: str) -> tuple[PersistedFeatureVectorRow, ...]:
'''
    file = ROOT / path
    text = file.read_text(encoding="utf-8")
    if text.count(marker) != 1:
        raise RuntimeError(f"{path}: feature batch insertion marker missing")
    method = '''    def fetch_freeze_publication_row(
        self, receipt_id: str
    ) -> PersistedFreezePublicationRow | None:
        with self._connection.cursor() as cur:
            cur.execute(
                """
                SELECT receipt_id, schema_version, freeze_receipt_digest,
                       implementation_commit, implementation_tree_digest,
                       publication_commit, publication_committer_at, publication_digest
                FROM candidate_freeze_publications
                WHERE receipt_id = %s
                """,
                (receipt_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return PersistedFreezePublicationRow(
            receipt_id=cast(str, row[0]),
            schema_version=cast(str, row[1]),
            freeze_receipt_digest=cast(str, row[2]),
            implementation_commit=cast(str, row[3]),
            implementation_tree_digest=cast(str, row[4]),
            publication_commit=cast(str, row[5]),
            publication_committer_at=cast(datetime, row[6]),
            publication_digest=cast(str, row[7]),
        )

'''
    file.write_text(text.replace(marker, method + marker), encoding="utf-8")


def patch_evaluation() -> None:
    path = "src/frontier/application/evaluation.py"
    replace_once(
        path,
        '''from frontier.application.drift_sentry import DriftChecker
''',
        '''from frontier.application.drift_sentry import DriftChecker
from frontier.application.freeze_publication import (
    CandidateFreezePublication,
    first_confirmatory_boundary,
    require_confirmatory_boundary,
)
''',
    )
    replace_once(
        path,
        '''def evaluate_shadow_experiment_from_persisted(
''',
        '''@dataclass(frozen=True, slots=True)
class _PersistedEvaluationAuthority:
    confirmatory: bool
    durable_freeze_at: datetime | None
    window_start: datetime | None


def _resolve_persisted_evaluation_authority(
    store: EvaluationArtifactStore,
    loaded: Sequence[object],
    *,
    requested_confirmatory: bool,
    canonical_context: bool | None,
    durable_freeze_at_assertion: datetime | None,
    window_start_assertion: datetime | None,
) -> _PersistedEvaluationAuthority:
    from frontier.application.evaluation_loaders import (
        CONFIRMATORY_RUN_CLASS,
        DEV_RUN_CLASS,
        LoadedPairedSnapshot,
        PersistedEvaluationError,
    )

    snapshots = tuple(item for item in loaded if isinstance(item, LoadedPairedSnapshot))
    if len(snapshots) != len(loaded):
        raise TypeError("persisted evaluation authority requires loaded paired snapshots")
    run_classes = {item.run_class for item in snapshots}
    if len(run_classes) != 1:
        raise PersistedEvaluationError(
            "persisted evaluation cannot mix DEV and CONFIRMATORY run classes"
        )
    run_class = next(iter(run_classes))
    if run_class not in (DEV_RUN_CLASS, CONFIRMATORY_RUN_CLASS):
        raise PersistedEvaluationError(f"unknown persisted run class {run_class!r}")
    actual_confirmatory = run_class == CONFIRMATORY_RUN_CLASS
    if requested_confirmatory and not actual_confirmatory:
        raise PersistedEvaluationError(
            "caller cannot escalate a persisted DEV run to CONFIRMATORY evaluation"
        )
    if not actual_confirmatory:
        if durable_freeze_at_assertion is not None or window_start_assertion is not None:
            raise PersistedEvaluationError(
                "DEV persisted evaluation cannot accept confirmatory authority timestamps"
            )
        return _PersistedEvaluationAuthority(False, None, None)

    if canonical_context is False:
        raise ValueError("confirmatory persisted evaluation was explicitly denied canonical DB context")
    receipt_ids = {item.freeze_receipt.receipt_id for item in snapshots}
    if len(receipt_ids) != 1:
        raise PersistedEvaluationError(
            "confirmatory persisted evaluation runs bind different candidate freeze receipts"
        )
    receipt_id = next(iter(receipt_ids))
    freeze_receipt = snapshots[0].freeze_receipt
    freeze_row = store.fetch_freeze_receipt_row(receipt_id)
    if freeze_row is None or freeze_row.receipt_id != receipt_id:
        raise PersistedEvaluationError("confirmatory freeze durability row is unresolvable")
    if freeze_row.durable_freeze_at is None:
        raise PersistedEvaluationError("confirmatory freeze has no canonical DB durability")
    publication_row = store.fetch_freeze_publication_row(receipt_id)
    if publication_row is None:
        raise PersistedEvaluationError("confirmatory freeze has no persisted Git publication authority")
    try:
        publication = CandidateFreezePublication(
            freeze_receipt_id=publication_row.receipt_id,
            freeze_receipt_digest=Digest(publication_row.freeze_receipt_digest),
            implementation_commit=publication_row.implementation_commit,
            implementation_tree_digest=publication_row.implementation_tree_digest,
            publication_commit=publication_row.publication_commit,
            publication_committer_at=publication_row.publication_committer_at,
            schema_version=publication_row.schema_version,
        )
    except ValueError as error:
        raise PersistedEvaluationError(f"persisted Git publication authority is invalid: {error}") from error
    if str(publication.publication_digest) != publication_row.publication_digest:
        raise PersistedEvaluationError("persisted Git publication digest does not bind its payload")
    if publication.freeze_receipt_id != freeze_receipt.receipt_id:
        raise PersistedEvaluationError("Git publication binds a different freeze receipt id")
    if publication.freeze_receipt_digest != freeze_receipt.receipt_digest:
        raise PersistedEvaluationError("Git publication binds a different freeze receipt digest")
    if freeze_receipt.implementation_commit is None or freeze_receipt.implementation_tree_digest is None:
        raise PersistedEvaluationError("confirmatory freeze is missing implementation identity")
    if publication.implementation_commit != freeze_receipt.implementation_commit:
        raise PersistedEvaluationError("Git publication binds a different implementation commit")
    if publication.implementation_tree_digest != freeze_receipt.implementation_tree_digest:
        raise PersistedEvaluationError("Git publication binds a different implementation tree")
    if publication.publication_committer_at < freeze_row.durable_freeze_at:
        raise PersistedEvaluationError("Git publication timestamp precedes canonical DB durability")
    window_start = first_confirmatory_boundary(publication.publication_committer_at)
    for item in snapshots:
        try:
            require_confirmatory_boundary(
                as_of=item.run.as_of,
                publication_committer_at=publication.publication_committer_at,
            )
        except ValueError as error:
            raise PersistedEvaluationError(
                f"persisted CONFIRMATORY run is outside Git-publication authority: {error}"
            ) from error
    if (
        durable_freeze_at_assertion is not None
        and durable_freeze_at_assertion != freeze_row.durable_freeze_at
    ):
        raise PersistedEvaluationError(
            "caller durable_freeze_at assertion disagrees with persisted authority"
        )
    if window_start_assertion is not None and window_start_assertion != window_start:
        raise PersistedEvaluationError(
            "caller window_start assertion disagrees with persisted Git publication authority"
        )
    return _PersistedEvaluationAuthority(True, freeze_row.durable_freeze_at, window_start)


def evaluate_shadow_experiment_from_persisted(
''',
    )
    old_sig = '''    confirmatory: bool = False,
    canonical_context: bool = False,
    durable_freeze_at: datetime | None = None,
'''
    new_sig = '''    confirmatory: bool = False,
    canonical_context: bool | None = None,
    durable_freeze_at: datetime | None = None,
'''
    replace_once(path, old_sig, new_sig)
    old_body = '''    if not runs:
        raise ValueError("persisted evaluation requires at least one persisted run")
    if confirmatory and not canonical_context:
        raise ValueError("confirmatory persisted evaluation requires the canonical DB context")
    if len({ref.run_id for ref in runs}) != len(runs):
        raise ValueError("duplicate persisted run ids in evaluation request")

    loaded = tuple(
        load_paired_snapshot(
            store,
            ref.run_id,
            as_of=ref.as_of,
            confirmatory=confirmatory,
            window_start=window_start,
            feature_batch_id=feature_batch_id,
        )
        for ref in runs
    )
    ordered = tuple(sorted(loaded, key=lambda item: item.snapshot.run.as_of))
'''
    new_body = '''    if not runs:
        raise ValueError("persisted evaluation requires at least one persisted run")
    if len({ref.run_id for ref in runs}) != len(runs):
        raise ValueError("duplicate persisted run ids in evaluation request")

    run_rows = tuple(store.fetch_run_row(ref.run_id) for ref in runs)
    if any(row is None for row in run_rows):
        missing = next(ref.run_id for ref, row in zip(runs, run_rows, strict=True) if row is None)
        raise ValueError(f"missing shadow experiment run row for {missing}")
    persisted_classes = {row.run_class for row in run_rows if row is not None}
    if len(persisted_classes) != 1:
        from frontier.application.evaluation_loaders import PersistedEvaluationError

        raise PersistedEvaluationError(
            "persisted evaluation cannot mix DEV and CONFIRMATORY run classes"
        )
    persisted_confirmatory = next(iter(persisted_classes)) == "CONFIRMATORY"
    loaded = tuple(
        load_paired_snapshot(
            store,
            ref.run_id,
            as_of=ref.as_of,
            confirmatory=persisted_confirmatory,
            feature_batch_id=feature_batch_id,
        )
        for ref in runs
    )
    ordered = tuple(sorted(loaded, key=lambda item: item.snapshot.run.as_of))
    authority = _resolve_persisted_evaluation_authority(
        store,
        ordered,
        requested_confirmatory=confirmatory,
        canonical_context=canonical_context,
        durable_freeze_at_assertion=durable_freeze_at,
        window_start_assertion=window_start,
    )
'''
    replace_once(path, old_body, new_body)
    replace_once(
        path,
        '''    if confirmatory and drift_sentry is not None:
''',
        '''    if authority.confirmatory and drift_sentry is not None:
''',
    )
    replace_once(
        path,
        '''        durable_freeze_at=durable_freeze_at,
''',
        '''        durable_freeze_at=authority.durable_freeze_at,
''',
        count=1,
    )


def patch_unit_tests() -> None:
    path = "tests/unit/test_evaluation_loaders.py"
    replace_once(
        path,
        '''    PersistedFeatureVectorRow,
    PersistedFreezeReceiptRow,
''',
        '''    PersistedFeatureVectorRow,
    PersistedFreezePublicationRow,
    PersistedFreezeReceiptRow,
''',
    )
    replace_once(
        path,
        '''from frontier.application.opportunity_outcome import RANKING_WINDOW_SECONDS
''',
        '''from frontier.application.freeze_publication import (
    CandidateFreezePublication,
    first_confirmatory_boundary,
)
from frontier.application.opportunity_outcome import RANKING_WINDOW_SECONDS
''',
    )
    replace_once(
        path,
        '''        self.freeze_receipts: dict[str, PersistedFreezeReceiptRow] = {}
        self.feature_rows: dict[str, tuple[PersistedFeatureVectorRow, ...]] = {}
''',
        '''        self.freeze_receipts: dict[str, PersistedFreezeReceiptRow] = {}
        self.freeze_publications: dict[str, PersistedFreezePublicationRow] = {}
        self.feature_rows: dict[str, tuple[PersistedFeatureVectorRow, ...]] = {}
''',
    )
    replace_once(
        path,
        '''    def fetch_feature_batch_rows(self, batch_id: str) -> tuple[PersistedFeatureVectorRow, ...]:
''',
        '''    def fetch_freeze_publication_row(
        self, receipt_id: str
    ) -> PersistedFreezePublicationRow | None:
        return self.freeze_publications.get(receipt_id)

    def fetch_feature_batch_rows(self, batch_id: str) -> tuple[PersistedFeatureVectorRow, ...]:
''',
    )
    marker = '''def _default_store() -> tuple[FakeStore, _Paired, CandidateFreezeReceipt]:
'''
    file = ROOT / path
    text = file.read_text(encoding="utf-8")
    if text.count(marker) != 1:
        raise RuntimeError(f"{path}: default store marker missing")
    helper = '''def _seed_publication(
    store: FakeStore,
    freeze: CandidateFreezeReceipt,
    *,
    publication_at: datetime,
) -> CandidateFreezePublication:
    assert freeze.implementation_commit is not None
    assert freeze.implementation_tree_digest is not None
    publication = CandidateFreezePublication(
        freeze_receipt_id=freeze.receipt_id,
        freeze_receipt_digest=freeze.receipt_digest,
        implementation_commit=freeze.implementation_commit,
        implementation_tree_digest=freeze.implementation_tree_digest,
        publication_commit="c" * 64,
        publication_committer_at=publication_at,
    )
    store.freeze_publications[freeze.receipt_id] = PersistedFreezePublicationRow(
        receipt_id=publication.freeze_receipt_id,
        schema_version=publication.schema_version,
        freeze_receipt_digest=str(publication.freeze_receipt_digest),
        implementation_commit=publication.implementation_commit,
        implementation_tree_digest=publication.implementation_tree_digest,
        publication_commit=publication.publication_commit,
        publication_committer_at=publication.publication_committer_at,
        publication_digest=str(publication.publication_digest),
    )
    return publication


'''
    file.write_text(text.replace(marker, helper + marker), encoding="utf-8")
    replace_once(
        path,
        '''    _seed(store, paired)
    _seed_freeze(store, freeze)
    return store, paired, freeze
''',
        '''    _seed(store, paired, run_class=DEV_RUN_CLASS)
    _seed_freeze(store, freeze)
    return store, paired, freeze
''',
        count=1,
    )
    replace_once(
        path,
        '''        assert loaded.run_class == CONFIRMATORY_RUN_CLASS
''',
        '''        assert loaded.run_class == DEV_RUN_CLASS
''',
    )
    replace_once(
        path,
        '''        _seed(store, paired)
        _seed_freeze(store, freeze)
        return store, paired
''',
        '''        _seed(store, paired, run_class=CONFIRMATORY_RUN_CLASS)
        _seed_freeze(store, freeze)
        publication_at = FROZEN_AT + timedelta(seconds=121)
        _seed_publication(store, freeze, publication_at=publication_at)
        return store, paired
''',
        count=1,
    )
    # Replace stale caller-authority tests with persisted-publication authority tests.
    start = file.read_text(encoding="utf-8").index(
        "    def test_a_confirmatory_evaluation_requires_canonical_context(self) -> None:\n"
    )
    end = file.read_text(encoding="utf-8").index(
        "    def test_b_run_bound_to_another_freeze_invalidates_to_drift(self) -> None:\n", start
    )
    current = file.read_text(encoding="utf-8")
    replacement = '''    def test_a_caller_true_cannot_escalate_dev_to_confirmatory(self) -> None:
        store, paired, _ = _default_store()
        with pytest.raises(PersistedEvaluationError, match="cannot escalate"):
            _evaluate(store, paired, confirmatory=True)

    def test_a_persisted_confirmatory_cannot_be_downgraded_by_caller_false(self) -> None:
        publication_at = FROZEN_AT + timedelta(seconds=121)
        as_of = first_confirmatory_boundary(publication_at)
        store, paired = self._confirmatory_store(as_of=as_of)
        receipt = _evaluate(store, paired, confirmatory=False)
        assert receipt.status is not EvaluationStatus.INVALID_DRIFT

    def test_a_missing_publication_fails_closed_even_when_caller_false(self) -> None:
        freeze = _freeze()
        paired = _paired(AS_OF, freeze_id=freeze.receipt_id)
        store = FakeStore()
        _seed(store, paired, run_class=CONFIRMATORY_RUN_CLASS)
        _seed_freeze(store, freeze)
        with pytest.raises(PersistedEvaluationError, match="no persisted Git publication"):
            _evaluate(store, paired, confirmatory=False)

    def test_a_explicit_canonical_context_denial_is_restrictive_only(self) -> None:
        publication_at = FROZEN_AT + timedelta(seconds=121)
        as_of = first_confirmatory_boundary(publication_at)
        store, paired = self._confirmatory_store(as_of=as_of)
        with pytest.raises(ValueError, match="explicitly denied"):
            evaluate_shadow_experiment_from_persisted(
                store=store,
                runs=(PersistedRunRef(paired.run.run_id, paired.run.as_of),),
                opportunity_groups=(),
                evaluation_horizon=paired.run.as_of + timedelta(hours=1),
                generated_at=paired.run.as_of + timedelta(hours=1),
                canonical_context=False,
            )

'''
    file.write_text(current[:start] + replacement + current[end:], encoding="utf-8")
    # Old B-F tests exercise the legacy durability helper directly; keep B, but replace C-F
    # with exact persisted publication assertions to match the frozen scientific clock.
    text = file.read_text(encoding="utf-8")
    start = text.index("    def test_c_as_of_before_durable_freeze_is_ineligible(self) -> None:\n")
    end = text.index("\n\n# ---------------------------------------------------------------------------\n# Persisted evaluator wiring", start)
    replacement = '''    def test_c_publication_window_is_authoritative(self) -> None:
        publication_at = FROZEN_AT + timedelta(seconds=121)
        as_of = first_confirmatory_boundary(publication_at)
        store, paired = self._confirmatory_store(as_of=as_of)
        receipt = _evaluate(store, paired, confirmatory=False)
        assert receipt.status is not EvaluationStatus.INVALID_DRIFT

    def test_d_caller_timestamp_assertions_must_equal_persisted_authority(self) -> None:
        publication_at = FROZEN_AT + timedelta(seconds=121)
        as_of = first_confirmatory_boundary(publication_at)
        store, paired = self._confirmatory_store(as_of=as_of)
        with pytest.raises(PersistedEvaluationError, match="durable_freeze_at assertion"):
            _evaluate(
                store,
                paired,
                confirmatory=False,
                durable_freeze_at=DURABLE_AT + timedelta(seconds=1),
            )

    def test_e_outside_publication_window_fails_closed(self) -> None:
        publication_at = FROZEN_AT + timedelta(seconds=121)
        start = first_confirmatory_boundary(publication_at)
        store, paired = self._confirmatory_store(
            as_of=start + timedelta(seconds=RANKING_WINDOW_SECONDS)
        )
        with pytest.raises(PersistedEvaluationError, match="outside Git-publication authority"):
            _evaluate(store, paired, confirmatory=False)

    def test_f_mixed_dev_and_confirmatory_runs_fail_closed(self) -> None:
        freeze = _freeze()
        publication_at = FROZEN_AT + timedelta(seconds=121)
        start = first_confirmatory_boundary(publication_at)
        confirmatory_run = _paired(start, freeze_id=freeze.receipt_id)
        dev_run = _paired(start + timedelta(seconds=300), freeze_id=freeze.receipt_id)
        store = FakeStore()
        _seed(store, confirmatory_run, run_class=CONFIRMATORY_RUN_CLASS)
        _seed(store, dev_run, run_class=DEV_RUN_CLASS)
        _seed_freeze(store, freeze)
        _seed_publication(store, freeze, publication_at=publication_at)
        with pytest.raises(PersistedEvaluationError, match="mix DEV and CONFIRMATORY"):
            _evaluate(store, confirmatory_run, extra=(dev_run,))
'''
    file.write_text(text[:start] + replacement + text[end:], encoding="utf-8")
    # _evaluate no longer grants canonical context; explicit caller true remains an assertion only.
    replace_once(
        path,
        '''        canonical_context=confirmatory,
''',
        '''        canonical_context=True if confirmatory else None,
''',
    )


def patch_integration_tests() -> None:
    path = "tests/integration/test_evaluation_persisted_postgres.py"
    replace_once(
        path,
        '''from frontier.adapters.postgres.evaluation_store import (
    PostgresEvaluationArtifactStore,
)
''',
        '''from frontier.adapters.postgres.evaluation_store import (
    PostgresEvaluationArtifactStore,
)
from frontier.adapters.postgres.freeze_publication import (
    PostgresCandidateFreezePublicationRepository,
)
''',
    )
    replace_once(
        path,
        '''from frontier.application.evaluation_loaders import (
''',
        '''from frontier.application.freeze_publication import (
    CandidateFreezePublication,
    first_confirmatory_boundary,
)
from frontier.application.evaluation_loaders import (
''',
    )
    marker = '''def test_persisted_run_evaluates_end_to_end_and_appends_receipt(conn: ConnectionT) -> None:
'''
    file = ROOT / path
    text = file.read_text(encoding="utf-8")
    if text.count(marker) != 1:
        raise RuntimeError(f"{path}: integration insertion marker missing")
    helper = '''def _publish_freeze(
    conn: ConnectionT,
    freeze: CandidateFreezeReceipt,
    *,
    publication_offset: timedelta = timedelta(seconds=1),
) -> CandidateFreezePublication:
    row = conn.execute(
        "SELECT durable_freeze_at FROM candidate_freeze_receipts WHERE receipt_id=%s",
        (freeze.receipt_id,),
    ).fetchone()
    assert row is not None and row[0] is not None
    durable = cast(datetime, row[0])
    assert freeze.implementation_commit is not None
    assert freeze.implementation_tree_digest is not None
    publication = CandidateFreezePublication(
        freeze_receipt_id=freeze.receipt_id,
        freeze_receipt_digest=freeze.receipt_digest,
        implementation_commit=freeze.implementation_commit,
        implementation_tree_digest=freeze.implementation_tree_digest,
        publication_commit="c" * 64,
        publication_committer_at=durable + publication_offset,
    )
    PostgresCandidateFreezePublicationRepository(
        conn, persistence_authorized=True
    ).record_publication(publication)
    return publication


def _future_boundary() -> datetime:
    now = datetime.now(UTC) + timedelta(days=1)
    epoch = int(now.timestamp())
    return datetime.fromtimestamp((epoch // 300 + 1) * 300, tz=UTC)


'''
    file.write_text(text.replace(marker, helper + marker), encoding="utf-8")
    # Append D011 live authority tests.
    with file.open("a", encoding="utf-8") as handle:
        handle.write(
            '''\n\ndef test_persisted_confirmatory_infers_authority_when_caller_false(conn: ConnectionT) -> None:
    as_of = _future_boundary()
    _, _, run, freeze = _persisted_paired(conn, as_of=as_of, run_class="CONFIRMATORY")
    publication = _publish_freeze(conn, freeze)
    assert as_of >= first_confirmatory_boundary(publication.publication_committer_at)
    horizon = as_of + timedelta(hours=1)
    receipt = evaluate_shadow_experiment_from_persisted(
        store=PostgresEvaluationArtifactStore(conn),
        runs=(PersistedRunRef(run.run_id, as_of),),
        opportunity_groups=(),
        evaluation_horizon=horizon,
        generated_at=horizon,
        confirmatory=False,
    )
    assert receipt.status is EvaluationStatus.INSUFFICIENT_SAMPLE
    assert receipt.status is not EvaluationStatus.INVALID_DRIFT


def test_persisted_confirmatory_missing_publication_fails_closed(conn: ConnectionT) -> None:
    as_of = _future_boundary() + timedelta(seconds=300)
    _, _, run, _ = _persisted_paired(conn, as_of=as_of, run_class="CONFIRMATORY")
    with pytest.raises(PersistedEvaluationError, match="no persisted Git publication"):
        evaluate_shadow_experiment_from_persisted(
            store=PostgresEvaluationArtifactStore(conn),
            runs=(PersistedRunRef(run.run_id, as_of),),
            opportunity_groups=(),
            evaluation_horizon=as_of + timedelta(hours=1),
            generated_at=as_of + timedelta(hours=1),
            confirmatory=False,
        )


def test_caller_cannot_escalate_dev_or_forge_authority_timestamps(conn: ConnectionT) -> None:
    as_of = _future_boundary() + timedelta(seconds=600)
    _, _, run, _ = _persisted_paired(conn, as_of=as_of, run_class="DEV")
    store = PostgresEvaluationArtifactStore(conn)
    with pytest.raises(PersistedEvaluationError, match="cannot escalate"):
        evaluate_shadow_experiment_from_persisted(
            store=store,
            runs=(PersistedRunRef(run.run_id, as_of),),
            opportunity_groups=(),
            evaluation_horizon=as_of + timedelta(hours=1),
            generated_at=as_of + timedelta(hours=1),
            confirmatory=True,
        )
    with pytest.raises(PersistedEvaluationError, match="cannot accept confirmatory authority timestamps"):
        evaluate_shadow_experiment_from_persisted(
            store=store,
            runs=(PersistedRunRef(run.run_id, as_of),),
            opportunity_groups=(),
            evaluation_horizon=as_of + timedelta(hours=1),
            generated_at=as_of + timedelta(hours=1),
            durable_freeze_at=as_of - timedelta(days=1),
            window_start=as_of,
        )


def test_persisted_confirmatory_rejects_forged_caller_clock_assertion(conn: ConnectionT) -> None:
    as_of = _future_boundary() + timedelta(seconds=900)
    _, _, run, freeze = _persisted_paired(conn, as_of=as_of, run_class="CONFIRMATORY")
    publication = _publish_freeze(conn, freeze)
    start = first_confirmatory_boundary(publication.publication_committer_at)
    with pytest.raises(PersistedEvaluationError, match="window_start assertion"):
        evaluate_shadow_experiment_from_persisted(
            store=PostgresEvaluationArtifactStore(conn),
            runs=(PersistedRunRef(run.run_id, as_of),),
            opportunity_groups=(),
            evaluation_horizon=as_of + timedelta(hours=1),
            generated_at=as_of + timedelta(hours=1),
            window_start=start + timedelta(seconds=300),
        )
'''
        )


def main() -> None:
    patch_evaluation_loaders()
    patch_postgres_store()
    patch_evaluation()
    patch_unit_tests()
    patch_integration_tests()
    files = [
        "src/frontier/application/evaluation_loaders.py",
        "src/frontier/adapters/postgres/evaluation_store.py",
        "src/frontier/application/evaluation.py",
        "tests/unit/test_evaluation_loaders.py",
        "tests/integration/test_evaluation_persisted_postgres.py",
    ]
    subprocess.run(["uv", "run", "ruff", "format", *files], cwd=ROOT, check=True)
    subprocess.run(["uv", "run", "ruff", "check", "--fix", *files], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
