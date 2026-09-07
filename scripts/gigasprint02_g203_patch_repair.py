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
    text = replace_once(
        text,
        '''    replace_once(
        path,
        '''        durable_freeze_at=durable_freeze_at,\n''',
        '''        durable_freeze_at=authority.durable_freeze_at,\n''',
        count=1,
    )
''',
        '''    replace_once(
        path,
        '''        generated_at=generated_at,\n        durable_freeze_at=durable_freeze_at,\n        rank_cutoff_k=rank_cutoff_k,\n''',
        '''        generated_at=generated_at,\n        durable_freeze_at=authority.durable_freeze_at,\n        rank_cutoff_k=rank_cutoff_k,\n''',
    )
''',
        "persisted evaluator durable authority target",
    )
    anchor = '''    replace_once(path, old_sig, new_sig)
    old_body = '''
'''
    injection = '''    replace_once(path, old_sig, new_sig)
    replace_once(
        path,
        '''from frontier.domain.drift_sentry import DriftStatus\n''',
        '''from frontier.domain.digests import Digest\nfrom frontier.domain.drift_sentry import DriftStatus\n''',
    )
    old_body = '''
'''
    text = replace_once(text, anchor, injection, "Digest import patch insertion")
    PATCH.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
