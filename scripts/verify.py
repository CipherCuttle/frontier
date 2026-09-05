from __future__ import annotations

import subprocess
import sys

COMMANDS = [
    ["ruff", "format", "--check", "--exclude", "scripts/preflight", "."],
    ["ruff", "check", "--exclude", "scripts/preflight", "."],
    ["pyright"],
    [sys.executable, "scripts/check_architecture_boundaries.py"],
    [sys.executable, "scripts/preflight/validate_pr02_contracts.py"],
    [sys.executable, "scripts/preflight/validate_acquisition_corpus.py"],
    [sys.executable, "scripts/preflight/validate_normalization_provenance_corpus.py"],
    [sys.executable, "scripts/preflight/validate_grouping_corpus.py"],
    [sys.executable, "scripts/preflight/validate_grouping_selection.py"],
    [sys.executable, "scripts/preflight/validate_baseline_intelligence_corpus.py"],
    [sys.executable, "scripts/preflight/validate_baseline_intelligence_runtime.py"],
    [sys.executable, "scripts/preflight/validate_public_read_plane_corpus.py"],
    [sys.executable, "scripts/preflight/validate_terminal_corpus.py"],
    [sys.executable, "scripts/generate_public_contracts.py", "--check"],
    ["pytest", "-q"],
]


def main() -> int:
    for command in COMMANDS:
        print("+", " ".join(command), flush=True)
        completed = subprocess.run(command, check=False)
        if completed.returncode:
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
