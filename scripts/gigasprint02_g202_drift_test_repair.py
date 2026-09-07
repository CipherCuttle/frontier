from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST = ROOT / "tests/integration/test_drift_sentry_postgres.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one replacement target, found {count}")
    return text.replace(old, new)


def main() -> None:
    text = TEST.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "from frontier.adapters.postgres.experiment_attempts import (\n"
        "    PostgresExperimentAttemptRepository,\n"
        "    PostgresFreezeBindingResolver,\n"
        "    PostgresShadowRunPersister,\n"
        ")\n",
        "from frontier.adapters.postgres.experiment_attempts import (\n"
        "    PostgresExperimentAttemptRepository,\n"
        "    PostgresFreezeBindingResolver,\n"
        "    PostgresShadowRunPersister,\n"
        ")\n"
        "from frontier.adapters.postgres.freeze_publication import (\n"
        "    PostgresCandidateFreezePublicationRepository,\n"
        ")\n",
        "postgres publication repository import",
    )
    text = replace_once(
        text,
        "from frontier.application.drift_sentry import DriftSentry\n",
        "from frontier.application.drift_sentry import DriftSentry\n"
        "from frontier.application.freeze_publication import (\n"
        "    CandidateFreezePublication,\n"
        "    first_confirmatory_boundary,\n"
        ")\n",
        "publication domain import",
    )
    old = '''    receipt = _stored_frozen_receipt()
    boundary = _future_boundary()
    with psycopg.connect(DB_URL) as conn:
        PostgresCandidateFreezeRepository(conn, persistence_authorized=True).record_receipt(receipt)
        resolver = PostgresFreezeBindingResolver(conn)
        binding = resolver.latest_binding()
        assert binding is not None
        assert binding.durable_freeze_at is not None
        orchestrator = ExperimentOrchestrator(
'''
    new = '''    receipt = _stored_frozen_receipt()
    assert receipt.implementation_commit is not None
    assert receipt.implementation_tree_digest is not None
    with psycopg.connect(DB_URL) as conn:
        PostgresCandidateFreezeRepository(conn, persistence_authorized=True).record_receipt(receipt)
        resolver = PostgresFreezeBindingResolver(conn)
        binding = resolver.latest_binding()
        assert binding is not None
        assert binding.durable_freeze_at is not None
        publication_at = binding.durable_freeze_at + timedelta(seconds=1)
        PostgresCandidateFreezePublicationRepository(
            conn, persistence_authorized=True
        ).record_publication(
            CandidateFreezePublication(
                freeze_receipt_id=receipt.receipt_id,
                freeze_receipt_digest=receipt.receipt_digest,
                implementation_commit=receipt.implementation_commit,
                implementation_tree_digest=receipt.implementation_tree_digest,
                publication_commit="c" * 64,
                publication_committer_at=publication_at,
            )
        )
        binding = resolver.latest_binding()
        assert binding is not None
        assert binding.publication_committer_at == publication_at
        boundary = first_confirmatory_boundary(publication_at)
        orchestrator = ExperimentOrchestrator(
'''
    text = replace_once(text, old, new, "drift integration setup")
    TEST.write_text(text, encoding="utf-8")
    subprocess.run(
        ["uv", "run", "ruff", "format", str(TEST.relative_to(ROOT))],
        cwd=ROOT,
        check=True,
    )


if __name__ == "__main__":
    main()
