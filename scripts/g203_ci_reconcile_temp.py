from __future__ import annotations

from pathlib import Path


def replace_exact(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one target, found {count}")
    file.write_text(text.replace(old, new), encoding="utf-8")


replace_exact(
    "tests/integration/test_freeze_workflow_postgres.py",
    '''Sequence proven: derive (dry) -> guard refusal without override -> persist WITH
override (fixture receipt) -> durability stamped -> verify OK -> orchestrator
confirmatory gate passes for as_of > durable_freeze_at; WRONG-freeze verify
prints drift; receipt_created_at != durable_freeze_at (different clocks).''',
    '''Sequence proven: derive (dry) -> guard refusal without override -> persist WITH
override (fixture receipt) -> durability stamped -> verify OK -> Git publication
authority persisted -> orchestrator confirmatory gate passes at the first legal
publication-derived boundary; WRONG-freeze verify prints drift;
receipt_created_at != durable_freeze_at (different clocks).''',
)

replace_exact(
    "tests/integration/test_freeze_workflow_postgres.py",
    '''from frontier.adapters.postgres.advanced_intelligence import (
    PostgresCandidateFreezeRepository,
)
''',
    '''from frontier.adapters.postgres.advanced_intelligence import (
    PostgresCandidateFreezeRepository,
)
from frontier.adapters.postgres.freeze_publication import (
    PostgresCandidateFreezePublicationRepository,
)
''',
)

replace_exact(
    "tests/integration/test_freeze_workflow_postgres.py",
    '''from frontier.application.experiment_orchestration import (
    FreezeBinding,
    evaluate_confirmatory_gates,
)
''',
    '''from frontier.application.experiment_orchestration import (
    FreezeBinding,
    evaluate_confirmatory_gates,
)
from frontier.application.freeze_publication import (
    CandidateFreezePublication,
    first_confirmatory_boundary,
)
''',
)

replace_exact(
    "tests/integration/test_freeze_workflow_postgres.py",
    '''    # 7. Orchestrator confirmatory gates: only as_of > durable_freeze_at passes.
    durable = datetime.fromisoformat(durable_freeze_at)
    allowed = evaluate_confirmatory_gates(
        FreezeBinding(receipt=receipt, durable_freeze_at=durable),
        as_of=durable + timedelta(hours=1),
        canonical_context=True,
    )
    assert allowed.allowed is True

    not_durable = evaluate_confirmatory_gates(
        FreezeBinding(receipt=receipt, durable_freeze_at=None),
        as_of=durable + timedelta(hours=1),
        canonical_context=True,
    )
    assert not_durable.allowed is False
    assert "durable_freeze_at NULL" in not_durable.reason

    early = evaluate_confirmatory_gates(
        FreezeBinding(receipt=receipt, durable_freeze_at=durable),
        as_of=durable,
        canonical_context=True,
    )
    assert early.allowed is False
    assert "not strictly after durable_freeze_at" in early.reason
''',
    '''    # 7. Confirmatory authority requires BOTH canonical DB durability and
    # verified Git publication. The scientific clock is the Git committer time.
    durable = datetime.fromisoformat(durable_freeze_at)
    publication_at = durable + timedelta(seconds=1)
    first_boundary = first_confirmatory_boundary(publication_at)

    unpublished = evaluate_confirmatory_gates(
        FreezeBinding(receipt=receipt, durable_freeze_at=durable),
        as_of=first_boundary,
        canonical_context=True,
    )
    assert unpublished.allowed is False
    assert "no verified Git publication" in unpublished.reason

    assert receipt.implementation_commit is not None
    assert receipt.implementation_tree_digest is not None
    publication = CandidateFreezePublication(
        freeze_receipt_id=receipt.receipt_id,
        freeze_receipt_digest=receipt.receipt_digest,
        implementation_commit=receipt.implementation_commit,
        implementation_tree_digest=receipt.implementation_tree_digest,
        publication_commit="c" * 40,
        publication_committer_at=publication_at,
    )
    with psycopg.connect(DB_URL) as conn:
        publication_repo = PostgresCandidateFreezePublicationRepository(
            conn, persistence_authorized=True
        )
        publication_repo.record_publication(publication)
        assert publication_repo.get_publication(receipt_id) == publication

    published_binding = FreezeBinding(
        receipt=receipt,
        durable_freeze_at=durable,
        publication_commit=publication.publication_commit,
        publication_committer_at=publication.publication_committer_at,
    )
    allowed = evaluate_confirmatory_gates(
        published_binding,
        as_of=first_boundary,
        canonical_context=True,
    )
    assert allowed.allowed is True

    not_durable = evaluate_confirmatory_gates(
        FreezeBinding(
            receipt=receipt,
            durable_freeze_at=None,
            publication_commit=publication.publication_commit,
            publication_committer_at=publication.publication_committer_at,
        ),
        as_of=first_boundary,
        canonical_context=True,
    )
    assert not_durable.allowed is False
    assert "durable_freeze_at NULL" in not_durable.reason

    early = evaluate_confirmatory_gates(
        published_binding,
        as_of=first_boundary - timedelta(seconds=300),
        canonical_context=True,
    )
    assert early.allowed is False
    assert "outside the fixed preregistered ranking window" in early.reason
''',
)

replace_exact(
    "tests/integration/test_postgres_store.py",
    '''                "frontier_append_only_feature_vectors",
                "frontier_append_only_feature_vectors_truncate",
                "frontier_append_only_observations",
''',
    '''                "frontier_append_only_feature_vectors",
                "frontier_append_only_feature_vectors_truncate",
                "frontier_append_only_freeze_publications",
                "frontier_append_only_freeze_publications_truncate",
                "frontier_append_only_observations",
''',
)

replace_exact(
    "tests/unit/test_drift_sentry.py",
    '''    _seed_freeze,  # pyright: ignore[reportPrivateUsage]
)
''',
    '''    _seed_freeze,  # pyright: ignore[reportPrivateUsage]
    _seed_publication,  # pyright: ignore[reportPrivateUsage]
)
''',
)

replace_exact(
    "tests/unit/test_drift_sentry.py",
    '''from frontier.application.experiment_status import build_experiment_status
''',
    '''from frontier.application.experiment_status import build_experiment_status
from frontier.application.freeze_publication import first_confirmatory_boundary
''',
)

replace_exact(
    "tests/unit/test_drift_sentry.py",
    '''def _store_for_live(paired: object, receipt: CandidateFreezeReceipt, durable: datetime):
    store = _store_double()
    _seed(store, paired, run_class="CONFIRMATORY")  # pyright: ignore[reportPrivateUsage, reportArgumentType]
    _seed_freeze(store, receipt, durable=durable)  # pyright: ignore[reportPrivateUsage]
    return store
''',
    '''def _store_for_live(paired: object, receipt: CandidateFreezeReceipt, durable: datetime):
    store = _store_double()
    _seed(store, paired, run_class="CONFIRMATORY")  # pyright: ignore[reportPrivateUsage, reportArgumentType]
    _seed_freeze(store, receipt, durable=durable)  # pyright: ignore[reportPrivateUsage]
    _seed_publication(store, receipt, publication_at=durable)  # pyright: ignore[reportPrivateUsage]
    return store
''',
)

replace_exact(
    "tests/unit/test_drift_sentry.py",
    '''    def test_confirmatory_drift_yields_invalid_drift(self) -> None:
        store, paired, _ = _seeded()
        receipt = _evaluate(
            store=store,
            run_id=paired.run.run_id,
            as_of=paired.run.as_of,
            confirmatory=True,
            durable_freeze_at=DURABLE_AT,
            checker=DriftSentry(REPO_ROOT),
        )
''',
    '''    def test_confirmatory_drift_yields_invalid_drift(self) -> None:
        _, _, freeze = _seeded()
        as_of = first_confirmatory_boundary(DURABLE_AT)
        paired = _paired(as_of, freeze_id=freeze.receipt_id)
        store = _store_double()
        _seed(store, paired, run_class="CONFIRMATORY")  # pyright: ignore[reportPrivateUsage]
        _seed_freeze(store, freeze, durable=DURABLE_AT)  # pyright: ignore[reportPrivateUsage]
        _seed_publication(store, freeze, publication_at=DURABLE_AT)  # pyright: ignore[reportPrivateUsage]
        receipt = _evaluate(
            store=store,
            run_id=paired.run.run_id,
            as_of=as_of,
            confirmatory=True,
            durable_freeze_at=DURABLE_AT,
            checker=DriftSentry(REPO_ROOT),
        )
''',
)

replace_exact(
    "tests/unit/test_drift_sentry.py",
    '''        as_of = durable + timedelta(seconds=300)
''',
    '''        as_of = first_confirmatory_boundary(durable)
''',
)
