from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST = ROOT / "tests/integration/test_confirmatory_claim_postgres.py"
DRIFT_TEST = ROOT / "tests/integration/test_drift_sentry_postgres.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one target, found {count}")
    return text.replace(old, new)


def main() -> None:
    text = TEST.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "from threading import Barrier\n\nimport pytest\n",
        "from threading import Barrier\nfrom typing import cast\n\nimport pytest\n",
        "cast import",
    )
    text = replace_once(
        text,
        "psycopg = pytest.importorskip(\"psycopg\")\n\n",
        "psycopg = pytest.importorskip(\"psycopg\")\n\nfrom psycopg import Connection\n\n",
        "connection import",
    )
    text = replace_once(
        text,
        "from frontier.application.freeze_publication import (\n",
        "from frontier.application.experiment_orchestration import ConfirmatoryClaimResult\n"
        "from frontier.application.freeze_publication import (\n",
        "claim result import",
    )
    text = replace_once(
        text,
        "from frontier.domain.advanced_intelligence import PEF_EXPERIMENT_ID\n",
        "from frontier.domain.advanced_intelligence import (\n"
        "    PEF_CONFIGURATION_DIGEST,\n"
        "    PEF_EXPERIMENT_ID,\n"
        ")\n",
        "frozen PEF configuration import",
    )
    text = replace_once(
        text,
        "from frontier.domain.candidate_freeze import FreezeInputs, build_candidate_freeze_receipt\n",
        "from frontier.domain.candidate_freeze import (\n"
        "    CandidateFreezeReceipt,\n"
        "    FreezeInputs,\n"
        "    build_candidate_freeze_receipt,\n"
        ")\n",
        "freeze receipt import",
    )
    text = replace_once(
        text,
        "pytestmark = pytest.mark.skipif(not DB_URL, reason=\"FRONTIER_TEST_DATABASE_URL not set\")\n\n",
        "pytestmark = pytest.mark.skipif(not DB_URL, reason=\"FRONTIER_TEST_DATABASE_URL not set\")\n\n"
        "ConnectionT = Connection[tuple[object, ...]]\n\n",
        "connection alias",
    )
    text = replace_once(
        text,
        "def _receipt(seed: str):\n",
        "def _receipt(seed: str) -> CandidateFreezeReceipt:\n",
        "receipt return type",
    )
    text = replace_once(
        text,
        '            preregistration_config_digest=Digest("sha256:" + "a" * 64),\n',
        "            preregistration_config_digest=PEF_CONFIGURATION_DIGEST,\n",
        "frozen preregistration configuration",
    )
    text = replace_once(
        text,
        "def _persist_receipt(conn, seed: str):\n",
        "def _persist_receipt(\n"
        "    conn: ConnectionT, seed: str\n"
        ") -> tuple[CandidateFreezeReceipt, datetime]:\n",
        "persist receipt signature",
    )
    text = replace_once(
        text,
        "    return receipt, row[0]\n",
        "    return receipt, cast(datetime, row[0])\n",
        "durable timestamp cast",
    )
    text = replace_once(
        text,
        "def _persist_authority(conn, seed: str):\n",
        "def _persist_authority(\n"
        "    conn: ConnectionT, seed: str\n"
        ") -> tuple[CandidateFreezeReceipt, datetime]:\n",
        "persist authority signature",
    )
    text = replace_once(
        text,
        "    publication_at = durable + timedelta(seconds=1)\n",
        "    publication_at = durable + timedelta(days=int(seed), seconds=1)\n",
        "authority boundary isolation",
    )
    text = replace_once(
        text,
        "def _pending(repo: PostgresExperimentAttemptRepository, as_of: datetime, attempt_no: int = 1):\n",
        "def _pending(\n"
        "    repo: PostgresExperimentAttemptRepository,\n"
        "    as_of: datetime,\n"
        "    attempt_no: int = 1,\n"
        ") -> ExperimentRunAttempt:\n",
        "pending signature",
    )
    text = replace_once(
        text,
        "def _claim(repo, attempt, receipt_id: str | None, *, owner: str = \"g205-worker\", deny=None):\n",
        "def _claim(\n"
        "    repo: PostgresExperimentAttemptRepository,\n"
        "    attempt: ExperimentRunAttempt,\n"
        "    receipt_id: str | None,\n"
        "    *,\n"
        "    owner: str = \"g205-worker\",\n"
        "    deny: str | None = None,\n"
        ") -> ConfirmatoryClaimResult:\n",
        "claim signature",
    )
    text = replace_once(
        text,
        "        as_of = first_confirmatory_boundary(durable + timedelta(seconds=1))\n",
        "        as_of = first_confirmatory_boundary(durable + timedelta(days=4, seconds=1))\n",
        "missing publication boundary isolation",
    )
    TEST.write_text(text, encoding="utf-8")

    drift = DRIFT_TEST.read_text(encoding="utf-8")
    drift = replace_once(
        drift,
        "        publication_at = binding.durable_freeze_at + timedelta(seconds=1)\n",
        "        publication_at = binding.durable_freeze_at + timedelta(days=30, seconds=1)\n",
        "drift boundary isolation",
    )
    DRIFT_TEST.write_text(drift, encoding="utf-8")


if __name__ == "__main__":
    main()
