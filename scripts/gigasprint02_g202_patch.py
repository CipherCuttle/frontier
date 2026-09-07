from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ".github/workflows/gigasprint02-g202.yml"
PAYLOAD_COMMIT = "529ef98fc6cbfeb50ee69ec0716b7920f58422da"


def replace_once(path: str, old: str, new: str) -> None:
    file = ROOT / path
    text = file.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one replacement target, found {count}")
    file.write_text(text.replace(old, new), encoding="utf-8")


def regex_replace_once(path: str, pattern: str, new: str) -> None:
    file = ROOT / path
    text = file.read_text(encoding="utf-8")
    replaced, count = re.subn(pattern, new, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise RuntimeError(f"{path}: expected one regex replacement target, found {count}")
    file.write_text(replaced, encoding="utf-8")


def apply_original_payload() -> None:
    source = subprocess.run(
        ["git", "show", f"{PAYLOAD_COMMIT}:{WORKFLOW}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    marker = "          python - <<'PY'\n"
    start = source.index(marker) + len(marker)
    end_marker = "\n          PY\n      - name: Verify G2-02"
    end = source.index(end_marker, start)
    raw_lines = source[start:end].splitlines()
    normalized: list[str] = []
    inside_payload_string = False
    for line in raw_lines:
        stripped = line.lstrip()
        closing = inside_payload_string and stripped.startswith("''')")
        if (not inside_payload_string or closing) and line.startswith("          "):
            line = line[10:]
        normalized.append(line)
        if line.count("'''") % 2 == 1:
            inside_payload_string = not inside_payload_string
    payload = "\n".join(normalized) + "\n"
    compile(payload, "<g2-02-payload>", "exec")
    exec(payload, {"__name__": "__main__"})


def normalize_generated_source() -> None:
    source = ROOT / "src/frontier/application/freeze_publication.py"
    source.write_bytes(source.read_bytes().replace(b"\x00", b"\\0"))

    test = ROOT / "tests/unit/test_freeze_publication.py"
    lines = test.read_text(encoding="utf-8").splitlines()
    repaired: list[str] = []
    skip = False
    for index, line in enumerate(lines):
        if skip:
            skip = False
            continue
        if 'path.write_text(canonical_json_text(receipt.to_canonical())+"' in line:
            repaired.append(
                '    path.write_text(canonical_json_text(receipt.to_canonical())+"\\n")'
            )
            if index + 1 < len(lines) and lines[index + 1].strip() == '")':
                skip = True
        elif line.strip() == "import json":
            continue
        else:
            repaired.append(line)
    test.write_text("\n".join(repaired) + "\n", encoding="utf-8")

    pg_test = ROOT / "tests/integration/test_freeze_publication_postgres.py"
    text = pg_test.read_text(encoding="utf-8")
    if not text.startswith("# ruff: noqa: E402\n"):
        pg_test.write_text("# ruff: noqa: E402\n" + text, encoding="utf-8")

    replace_once(
        "migrations/versions/0013_freeze_publication_authority.py",
        'revision = "0013_freeze_publication_authority"',
        'revision = "0013_freeze_publication"',
    )
    replace_once(
        "src/frontier/adapters/postgres/readiness.py",
        'EXPECTED_DATABASE_REVISION = "0013_freeze_publication_authority"',
        'EXPECTED_DATABASE_REVISION = "0013_freeze_publication"',
    )
    replace_once(
        "tests/integration/test_experiment_lifecycle_postgres.py",
        'assert readiness.migration_revision == "0013_freeze_publication_authority"',
        'assert readiness.migration_revision == "0013_freeze_publication"',
    )


def format_base() -> None:
    files = [
        "src/frontier/application/freeze_publication.py",
        "src/frontier/adapters/postgres/freeze_publication.py",
        "migrations/versions/0013_freeze_publication_authority.py",
        "tests/unit/test_freeze_publication.py",
        "tests/integration/test_freeze_publication_postgres.py",
        "src/frontier/application/candidate_freeze.py",
        "src/frontier/application/drift_sentry.py",
        "src/frontier/application/experiment_orchestration.py",
        "src/frontier/adapters/postgres/experiment_attempts.py",
        "src/frontier/adapters/postgres/readiness.py",
        "tests/unit/test_experiment_orchestration.py",
        "tests/unit/test_drift_sentry.py",
        "tests/integration/test_experiment_lifecycle_postgres.py",
    ]
    subprocess.run(["uv", "run", "ruff", "format", *files], cwd=ROOT, check=True)

    replace_once(
        "src/frontier/adapters/postgres/freeze_publication.py",
        '                    "SELECT publication_digest FROM candidate_freeze_publications WHERE receipt_id=%s",\n',
        '                    "SELECT publication_digest FROM candidate_freeze_publications "\n'
        '                    "WHERE receipt_id=%s",\n',
    )
    subprocess.run(
        [
            "uv",
            "run",
            "ruff",
            "check",
            "--fix",
            "src/frontier/application/freeze_publication.py",
            "src/frontier/adapters/postgres/freeze_publication.py",
            "tests/unit/test_freeze_publication.py",
            "tests/integration/test_freeze_publication_postgres.py",
        ],
        cwd=ROOT,
        check=True,
    )


def repair_semantics() -> None:
    regex_replace_once(
        "tests/unit/test_experiment_orchestration.py",
        r'publication_committer_at=\(\s*None\s+if binding == "NOT_DURABLE"\s+else BOUNDARY - timedelta\(seconds=301\)\s*\),',
        'publication_committer_at=(\n'
        '                    None\n'
        '                    if binding == "NOT_DURABLE"\n'
        '                    else (\n'
        '                        BOUNDARY - timedelta(seconds=300)\n'
        '                        if binding == "LATER"\n'
        '                        else BOUNDARY - timedelta(seconds=301)\n'
        '                    )\n'
        '                ),',
    )

    replace_once(
        "src/frontier/adapters/postgres/experiment_attempts.py",
        '                SELECT r.status, r.drift_reasons, r.preregistration_digest,\n'
        '                       preregistration_config_digest, implementation_commit,\n'
        '                       implementation_tree_digest, dependency_lock_digest,\n'
        '                       source_registry_digest, registry_entry_digests,\n'
        '                       receipt_digest, frozen_at, verified_at,\n',
        '                SELECT r.status, r.drift_reasons, r.preregistration_digest,\n'
        '                       r.preregistration_config_digest, r.implementation_commit,\n'
        '                       r.implementation_tree_digest, r.dependency_lock_digest,\n'
        '                       r.source_registry_digest, r.registry_entry_digests,\n'
        '                       r.receipt_digest, r.frozen_at, r.verified_at,\n',
    )

    replace_once(
        "src/frontier/application/drift_sentry.py",
        '    def _try_collect(\n'
        '        self, receipt: CandidateFreezeReceipt | None = None\n'
        '    ) -> FreezeInputs | None:\n'
        '        try:\n'
        '            if receipt is None or receipt.implementation_commit is None:\n'
        '                return collect_freeze_inputs(self._root)\n'
        '            head = subprocess.run(\n'
        '                ["git", "rev-parse", "HEAD"],\n'
        '                cwd=self._root,\n'
        '                capture_output=True,\n'
        '                text=True,\n'
        '                check=True,\n'
        '                timeout=30,\n'
        '            ).stdout.strip()\n'
        '            if head == receipt.implementation_commit:\n'
        '                return collect_freeze_inputs(self._root)\n'
        '            derive_freeze_publication(self._root, receipt)\n'
        '            return collect_freeze_inputs(\n'
        '                self._root, implementation_ref=receipt.implementation_commit\n'
        '            )\n'
        '        except (OSError, subprocess.SubprocessError, RuntimeError, ValueError):\n'
        '            return None\n',
        '    def _try_collect(\n'
        '        self, receipt: CandidateFreezeReceipt | None = None\n'
        '    ) -> FreezeInputs | None:\n'
        '        try:\n'
        '            if receipt is None or receipt.implementation_commit is None:\n'
        '                return collect_freeze_inputs(self._root)\n'
        '            head = subprocess.run(\n'
        '                ["git", "rev-parse", "HEAD"],\n'
        '                cwd=self._root,\n'
        '                capture_output=True,\n'
        '                text=True,\n'
        '                check=True,\n'
        '                timeout=30,\n'
        '            ).stdout.strip()\n'
        '            if head == receipt.implementation_commit:\n'
        '                return collect_freeze_inputs(self._root)\n'
        '            try:\n'
        '                subprocess.run(\n'
        '                    [\n'
        '                        "git",\n'
        '                        "cat-file",\n'
        '                        "-e",\n'
        '                        f"{receipt.implementation_commit}^{{commit}}",\n'
        '                    ],\n'
        '                    cwd=self._root,\n'
        '                    capture_output=True,\n'
        '                    check=True,\n'
        '                    timeout=30,\n'
        '                )\n'
        '            except subprocess.CalledProcessError:\n'
        '                return collect_freeze_inputs(self._root)\n'
        '            try:\n'
        '                derive_freeze_publication(self._root, receipt)\n'
        '            except (RuntimeError, ValueError):\n'
        '                return collect_freeze_inputs(self._root)\n'
        '            return collect_freeze_inputs(\n'
        '                self._root, implementation_ref=receipt.implementation_commit\n'
        '            )\n'
        '        except (OSError, subprocess.SubprocessError):\n'
        '            return None\n',
    )

    subprocess.run(
        [
            "uv",
            "run",
            "ruff",
            "format",
            "src/frontier/application/drift_sentry.py",
            "src/frontier/adapters/postgres/experiment_attempts.py",
            "tests/unit/test_experiment_orchestration.py",
            "src/frontier/adapters/postgres/freeze_publication.py",
        ],
        cwd=ROOT,
        check=True,
    )


def main() -> None:
    apply_original_payload()
    normalize_generated_source()
    format_base()
    repair_semantics()


if __name__ == "__main__":
    main()
