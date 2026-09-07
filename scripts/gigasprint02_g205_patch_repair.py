from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "scripts/gigasprint02_g205_patch.py"


def main() -> None:
    text = PATCH.read_text(encoding="utf-8")
    old = '''    if text.count(start_marker) != 1:
        raise RuntimeError(f"{path}: expected one start marker")
    start = text.index(start_marker)
'''
    new = '''    count = text.count(start_marker)
    if count == 1:
        start = text.index(start_marker)
    elif count == 2 and start_marker.startswith("        freeze_receipt:"):
        start = text.rindex(start_marker)
    else:
        raise RuntimeError(f"{path}: expected one start marker, found {count}")
'''
    if text.count(old) != 1:
        raise RuntimeError("G2-05 replace_between helper target missing")
    PATCH.write_text(text.replace(old, new), encoding="utf-8")


if __name__ == "__main__":
    main()
