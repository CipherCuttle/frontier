from __future__ import annotations

import subprocess
import sys

COMMANDS = [
    ["ruff", "format", "--check", "--exclude", "scripts/preflight", "."],
    ["ruff", "check", "."],
    ["pyright"],
    [sys.executable, "scripts/check_architecture_boundaries.py"],
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
