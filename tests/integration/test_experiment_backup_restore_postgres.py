"""WP10 (G9): the backup/restore proof covers the experimental tables.

Runs the destructive scratch-database recovery drill (``scripts/ops/
verify_backup_restore.py``) against a real PostgreSQL when an explicit
scratch server is provided via ``FRONTIER_RECOVERY_DATABASE_URL`` and docker
is available (SKIP pattern, like the other PostgreSQL integration tests).
The drill seeds every experimental scientific table (migrations 0003-0012),
dumps the full schema+data, rebuilds the target schema with
``alembic upgrade head``, replays the dump and re-derives every scientific
identity; the assertions below prove the required coverage:
all experiment tables present in the dump, digests match post-restore,
a DEV run stays DEV, ``durable_freeze_at`` is preserved byte-identically,
and the fold-projection of the opportunity transitions is identical.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "verify_backup_restore.py"

EXPERIMENT_TABLES = frozenset(
    {
        "baseline_intelligence_snapshots",
        "pef_ranking_artifacts",
        "shadow_experiment_runs",
        "candidate_freeze_receipts",
        "evaluation_receipts",
        "feature_vectors",
        "experimental_analysis_artifacts",
        "opportunity_anchors",
        "outcome_resolutions",
        "opportunity_transitions",
        "experiment_run_attempts",
        "worker_heartbeats",
        "opportunity_memberships",
    }
)

SCRATCH_URL = os.getenv("FRONTIER_RECOVERY_DATABASE_URL")
pytestmark = [
    pytest.mark.skipif(not SCRATCH_URL, reason="FRONTIER_RECOVERY_DATABASE_URL not set"),
    pytest.mark.skipif(shutil.which("docker") is None, reason="docker not available"),
]


def _run_drill() -> dict[str, object]:
    """Run the full drill and return its JSON report (exit non-zero -> fail)."""
    environment = os.environ.copy()
    environment["FRONTIER_RECOVERY_DRILL_ALLOW"] = "1"
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        pytest.fail(f"recovery drill failed: {completed.stderr[-4000:]}")
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_backup_restore_proof_covers_experimental_scientific_tables() -> None:
    report = _run_drill()
    # Digests match post-restore: the drill re-derives every scientific
    # identity and exits non-zero on ANY mismatch, so a passing exit plus the
    # explicit flag is the digest-match assertion.
    assert report["restore_verified"] is True
    assert report["experiment_tables_present_in_dump"] is True
    assert report["migration_revision"] == "0012_opportunity_memberships"
    # All experiment tables are present in the dump and carry restored rows.
    tables = cast("dict[str, int]", report["experiment_tables"])
    assert set(tables) == set(EXPERIMENT_TABLES)
    for table in EXPERIMENT_TABLES:
        assert tables[table] >= 1, f"{table} has no restored rows"
    # A pre-restore DEV run stays DEV; timestamps are restored values.
    assert report["dev_run_class_after_restore"] == "DEV"
    assert report["conf_run_class_after_restore"] == "CONFIRMATORY"
    assert report["durable_freeze_at_preserved"] is True
    # Fold-projection of the opportunity transitions is identical.
    assert report["opportunity_fold_after_restore"] == "RESOLVED"
