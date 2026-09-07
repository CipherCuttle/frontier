from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tests/replay/test_experiment_gauntlet.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one target, found {count}")
    return text.replace(old, new)


def main() -> None:
    text = PATH.read_text(encoding="utf-8")

    text = replace_once(
        text,
        """from frontier.application.evaluation_loaders import (
    CONFIRMATORY_RUN_CLASS,
    PersistedArtifactRow,
""",
        """from frontier.application.evaluation_loaders import (
    CONFIRMATORY_RUN_CLASS,
    DEV_RUN_CLASS,
    PersistedArtifactRow,
""",
        "DEV run-class import",
    )
    text = replace_once(
        text,
        """    PersistedFeatureVectorRow,
    PersistedFreezeReceiptRow,
""",
        """    PersistedFeatureVectorRow,
    PersistedFreezePublicationRow,
    PersistedFreezeReceiptRow,
""",
        "publication-row import",
    )
    text = replace_once(
        text,
        """from frontier.application.experiment_orchestration import (
""",
        """from frontier.application.freeze_publication import (
    CandidateFreezePublication,
    first_confirmatory_boundary,
)
from frontier.application.experiment_orchestration import (
""",
        "freeze-publication import",
    )
    text = replace_once(
        text,
        """        self.freeze_receipts: dict[str, PersistedFreezeReceiptRow] = {}
        self.feature_rows: dict[str, tuple[PersistedFeatureVectorRow, ...]] = {}
""",
        """        self.freeze_receipts: dict[str, PersistedFreezeReceiptRow] = {}
        self.freeze_publications: dict[str, PersistedFreezePublicationRow] = {}
        self.feature_rows: dict[str, tuple[PersistedFeatureVectorRow, ...]] = {}
""",
        "FakeStore publication storage",
    )
    text = replace_once(
        text,
        """    def fetch_feature_batch_rows(self, batch_id: str) -> tuple[PersistedFeatureVectorRow, ...]:
""",
        """    def fetch_freeze_publication_row(
        self, receipt_id: str
    ) -> PersistedFreezePublicationRow | None:
        return self.freeze_publications.get(receipt_id)

    def fetch_feature_batch_rows(self, batch_id: str) -> tuple[PersistedFeatureVectorRow, ...]:
""",
        "FakeStore publication reader",
    )

    marker = "def _default_store() -> tuple[FakeStore, _Paired, CandidateFreezeReceipt]:\n"
    if text.count(marker) != 1:
        raise RuntimeError("default-store marker is not unique")
    helper = """def _seed_publication(
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


"""
    text = text.replace(marker, helper + marker)

    text = replace_once(
        text,
        """    _seed(store, paired)
    _seed_freeze(store, freeze)
    return store, paired, freeze
""",
        """    _seed(store, paired, run_class=DEV_RUN_CLASS)
    _seed_freeze(store, freeze)
    return store, paired, freeze
""",
        "default replay store is DEV",
    )

    old_c08_start = text.index(
        "    def test_g10_c08_registry_mismatch_invalidates_confirmatory_evaluation(self) -> None:\n"
    )
    old_c08_end = text.index(
        "\n\n# ---------------------------------------------------------------------------\n# Mid-window deletion",
        old_c08_start,
    )
    new_c08 = """    def test_g10_c08_registry_mismatch_invalidates_confirmatory_evaluation(self) -> None:
        \"\"\"Case 8 INVALID_DRIFT path: registry drift invalidates real persisted authority.\"\"\"
        freeze = _freeze()
        publication_at = FROZEN_AT + timedelta(seconds=121)
        as_of = first_confirmatory_boundary(publication_at)
        paired = _paired(as_of, freeze_id=freeze.receipt_id)
        store = FakeStore()
        _seed(store, paired, run_class=CONFIRMATORY_RUN_CLASS)
        _seed_freeze(store, freeze)
        _seed_publication(store, freeze, publication_at=publication_at)
        sentry = _RegistryMismatchSentry(expected=Digest("sha256:" + "e" * 64))
        horizon = paired.run.as_of + timedelta(hours=1)
        receipt = evaluate_shadow_experiment_from_persisted(
            store=store,
            runs=(PersistedRunRef(paired.run.run_id, paired.run.as_of),),
            opportunity_groups=(),
            evaluation_horizon=horizon,
            generated_at=horizon,
            confirmatory=False,
            durable_freeze_at=DURABLE_AT,
            drift_sentry=cast("DriftChecker", sentry),
        )
        assert receipt.status is EvaluationStatus.INVALID_DRIFT
"""
    text = text[:old_c08_start] + new_c08 + text[old_c08_end:]

    text = replace_once(
        text,
        """        _seed(store, mid)
        # Positive control first: both boundaries evaluate together.
""",
        """        _seed(store, mid, run_class=DEV_RUN_CLASS)
        # Positive control first: both boundaries evaluate together.
""",
        "mid-window DEV class",
    )

    old_c19 = """        receipt = _evaluate_persisted(
            store,
            run_one,
            extra=(run_two,),
            confirmatory=True,
            durable_freeze_at=DURABLE_AT,
            repo=RecordingRepo(),
        )
        assert receipt.confirmatory_evidence is False
        assert receipt.status is not EvaluationStatus.COMPLETE
"""
    new_c19 = """        with pytest.raises(PersistedEvaluationError, match="different candidate freeze receipts"):
            _evaluate_persisted(
                store,
                run_one,
                extra=(run_two,),
                confirmatory=True,
                durable_freeze_at=DURABLE_AT,
                repo=RecordingRepo(),
            )
"""
    text = replace_once(text, old_c19, new_c19, "cross-freeze persisted evaluation")

    PATH.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
