from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str, label: str) -> None:
    file = ROOT / path
    text = file.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one target, found {count}")
    file.write_text(text.replace(old, new), encoding="utf-8")


def patch_evaluator_error_contract() -> None:
    replace_once(
        "src/frontier/application/evaluation.py",
        """    run_rows = tuple(store.fetch_run_row(ref.run_id) for ref in runs)
    if any(row is None for row in run_rows):
        missing = next(ref.run_id for ref, row in zip(runs, run_rows, strict=True) if row is None)
        raise ValueError(f"missing shadow experiment run row for {missing}")
    persisted_classes = {row.run_class for row in run_rows if row is not None}
    if len(persisted_classes) != 1:
        from frontier.application.evaluation_loaders import PersistedEvaluationError

        raise PersistedEvaluationError(
            "persisted evaluation cannot mix DEV and CONFIRMATORY run classes"
        )
""",
        """    from frontier.application.evaluation_loaders import PersistedEvaluationError

    run_rows = tuple(store.fetch_run_row(ref.run_id) for ref in runs)
    if any(row is None for row in run_rows):
        missing = next(ref.run_id for ref, row in zip(runs, run_rows, strict=True) if row is None)
        raise PersistedEvaluationError(f"missing shadow experiment run row for {missing}")
    persisted_classes = {row.run_class for row in run_rows if row is not None}
    if len(persisted_classes) != 1:
        raise PersistedEvaluationError(
            "persisted evaluation cannot mix DEV and CONFIRMATORY run classes"
        )
""",
        "persisted missing-row error contract",
    )


def patch_unit_mixed_freeze_expectation() -> None:
    replace_once(
        "tests/unit/test_evaluation_loaders.py",
        """        # Through the persisted evaluator this surfaces as an INVALID_DRIFT
        # receipt when the sample is adequate; with an empty opportunity set
        # the epistemic gate stays explicit and confirmatory_evidence is False.
        receipt = _evaluate(
            store,
            run_one,
            extra=(run_two,),
            confirmatory=True,
            durable_freeze_at=DURABLE_AT,
        )
        assert receipt.confirmatory_evidence is False
""",
        """        # Persisted authority fails closed before statistical evaluation:
        # a mixed-freeze window cannot manufacture any evaluation receipt.
        with pytest.raises(PersistedEvaluationError, match="different candidate freeze receipts"):
            _evaluate(
                store,
                run_one,
                extra=(run_two,),
                confirmatory=True,
                durable_freeze_at=DURABLE_AT,
            )
""",
        "mixed-freeze unit expectation",
    )


def patch_replay_publication_order() -> None:
    path = ROOT / "tests/replay/test_experiment_gauntlet.py"
    text = path.read_text(encoding="utf-8")

    start = text.index(
        "    def test_g10_c13_as_of_before_durable_freeze_is_ineligible(self) -> None:\n"
    )
    end = text.index(
        "    def test_g10_c15_post_durable_as_of_without_durability_is_ineligible(self) -> None:\n",
        start,
    )
    replacement = """    def test_g10_c13_as_of_before_durable_freeze_is_ineligible(self) -> None:
        freeze = _freeze()
        publication_at = DURABLE_AT + timedelta(seconds=1)
        decision = evaluate_confirmatory_gates(
            FreezeBinding(
                freeze,
                durable_freeze_at=DURABLE_AT,
                publication_commit="c" * 64,
                publication_committer_at=publication_at,
            ),
            as_of=FROZEN_AT,
            canonical_context=True,
        )
        assert decision.allowed is False
        assert "outside the fixed preregistered ranking window" in decision.reason

    def test_g10_c14_as_of_equal_to_durable_freeze_is_ineligible(self) -> None:
        freeze = _freeze()
        aligned_durable = FROZEN_AT + timedelta(seconds=300)
        decision = evaluate_confirmatory_gates(
            FreezeBinding(
                freeze,
                durable_freeze_at=aligned_durable,
                publication_commit="c" * 64,
                publication_committer_at=aligned_durable,
            ),
            as_of=aligned_durable,
            canonical_context=True,
        )
        assert decision.allowed is False
        assert "outside the fixed preregistered ranking window" in decision.reason

"""
    text = text[:start] + replacement + text[end:]

    start = text.index(
        "    def test_g10_c17_pre_durability_confirmatory_run_gate_rejects(self) -> None:\n"
    )
    end = text.index(
        "    def test_g10_c18_wrong_freeze_candidate_id_mismatches(self) -> None:\n",
        start,
    )
    replacement = """    def test_g10_c17_pre_durability_confirmatory_run_gate_rejects(self) -> None:
        freeze = _freeze()
        # Before durability: no canonical persistence evidence at all.
        early = evaluate_confirmatory_gates(
            FreezeBinding(freeze, durable_freeze_at=None),
            as_of=AS_OF,
            canonical_context=True,
        )
        assert early.allowed is False
        assert "durable_freeze_at NULL" in early.reason
        # Later durability/publication can never retroactively authorize an
        # earlier boundary: the Git-publication window starts strictly later.
        earlier_boundary = FROZEN_AT + timedelta(seconds=300)
        late_authority = earlier_boundary + timedelta(seconds=300)
        late_stamped = evaluate_confirmatory_gates(
            FreezeBinding(
                freeze,
                durable_freeze_at=late_authority,
                publication_commit="c" * 64,
                publication_committer_at=late_authority,
            ),
            as_of=earlier_boundary,
            canonical_context=True,
        )
        assert late_stamped.allowed is False
        assert "outside the fixed preregistered ranking window" in late_stamped.reason

"""
    text = text[:start] + replacement + text[end:]
    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_evaluator_error_contract()
    patch_unit_mixed_freeze_expectation()
    patch_replay_publication_order()


if __name__ == "__main__":
    main()
