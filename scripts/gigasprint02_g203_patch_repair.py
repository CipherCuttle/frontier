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

    old_durable = "    replace_once(\n        path,\n        '''        durable_freeze_at=durable_freeze_at,\\n''',\n        '''        durable_freeze_at=authority.durable_freeze_at,\\n''',\n        count=1,\n    )\n"
    new_durable = "    replace_once(\n        path,\n        '''        generated_at=generated_at,\\n        durable_freeze_at=durable_freeze_at,\\n        rank_cutoff_k=rank_cutoff_k,\\n''',\n        '''        generated_at=generated_at,\\n        durable_freeze_at=authority.durable_freeze_at,\\n        rank_cutoff_k=rank_cutoff_k,\\n''',\n    )\n"
    text = replace_once(
        text,
        old_durable,
        new_durable,
        "persisted evaluator durable authority target",
    )

    anchor = "    replace_once(path, old_sig, new_sig)\n    old_body = '''\n"
    injection = "    replace_once(path, old_sig, new_sig)\n    replace_once(\n        path,\n        '''from frontier.domain.drift_sentry import DriftStatus\\n''',\n        '''from frontier.domain.digests import Digest\\nfrom frontier.domain.drift_sentry import DriftStatus\\n''',\n    )\n    old_body = '''\n"
    text = replace_once(text, anchor, injection, "Digest import patch insertion")

    PATCH.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
