from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "scripts/gigasprint02_g203_patch.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one target, found {count}")
    return text.replace(old, new)


def main() -> None:
    text = PATCH.read_text(encoding="utf-8")

    old_durable = """    replace_once(
        path,
        '''        durable_freeze_at=durable_freeze_at,
''',
        '''        durable_freeze_at=authority.durable_freeze_at,
''',
        count=1,
    )
"""
    new_durable = """    replace_once(
        path,
        '''        generated_at=generated_at,
        durable_freeze_at=durable_freeze_at,
        rank_cutoff_k=rank_cutoff_k,
''',
        '''        generated_at=generated_at,
        durable_freeze_at=authority.durable_freeze_at,
        rank_cutoff_k=rank_cutoff_k,
''',
    )
"""
    text = replace_once(
        text,
        old_durable,
        new_durable,
        "persisted evaluator durable authority target",
    )

    anchor = """    replace_once(path, old_sig, new_sig)
    old_body = '''"""
    injection = """    replace_once(path, old_sig, new_sig)
    replace_once(
        path,
        '''from frontier.domain.drift_sentry import DriftStatus
''',
        '''from frontier.domain.digests import Digest
from frontier.domain.drift_sentry import DriftStatus
''',
    )
    old_body = '''"""
    text = replace_once(text, anchor, injection, "Digest import patch insertion")

    PATCH.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
