from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(".")

# Production adapter: verified GitHub-main publication is the only write path.
adapter = ROOT / "src/frontier/adapters/postgres/freeze_publication.py"
text = adapter.read_text(encoding="utf-8")
text = text.replace(
    '            "use record_verified_publication or the explicit fixture seam"\n',
    '            "use record_verified_publication"\n',
    1,
)
old = '''        publication = derive_github_main_freeze_publication(\n            root, receipt, receipt_path=receipt_path\n        )\n        self._record(publication)\n        return publication\n\n    def record_fixture_publication(self, publication: CandidateFreezePublication) -> None:\n        """Explicit test/fixture seam; never use for operator publication."""\n        if not self._persistence_authorized:\n            raise PermissionError("candidate freeze publication persistence is not authorized")\n        self._record(publication)\n\n    def _record(self, publication: CandidateFreezePublication) -> None:\n        with self._connection.transaction(), self._connection.cursor() as cur:\n'''
new = '''        publication = derive_github_main_freeze_publication(\n            root, receipt, receipt_path=receipt_path\n        )\n        with self._connection.transaction(), self._connection.cursor() as cur:\n'''
if text.count(old) != 1:
    raise SystemExit("production fixture seam block not found exactly once")
text = text.replace(old, new, 1)
marker = '''                if row is None or cast(str, row[0]) != str(publication.publication_digest):\n                    raise RuntimeError("freeze publication identity conflict")\n\n    def get_publication'''
replacement = '''                if row is None or cast(str, row[0]) != str(publication.publication_digest):\n                    raise RuntimeError("freeze publication identity conflict")\n        return publication\n\n    def get_publication'''
if text.count(marker) != 1:
    raise SystemExit("verified publication return insertion point not found")
adapter.write_text(text.replace(marker, replacement, 1), encoding="utf-8")

# Test-only namespace. Hatch wheel packages src/frontier only.
(ROOT / "tests/__init__.py").write_text("", encoding="utf-8")
(ROOT / "tests/integration/__init__.py").write_text("", encoding="utf-8")
helper = ROOT / "tests/integration/freeze_publication_fixture.py"
helper.write_text(
    '''"""Test-only synthetic freeze-publication persistence helper.

This module is outside ``src/frontier`` and is not packaged with the product.
Production publication persistence must pass GitHub-main verification.
"""

from __future__ import annotations

from typing import cast

from psycopg import Connection
from psycopg.types.json import Jsonb

from frontier.application.freeze_publication import CandidateFreezePublication


def record_fixture_publication(
    connection: Connection[tuple[object, ...]], publication: CandidateFreezePublication
) -> None:
    with connection.transaction(), connection.cursor() as cur:
        cur.execute(
            """INSERT INTO candidate_freeze_publications (
                receipt_id, schema_version, freeze_receipt_digest, implementation_commit,
                implementation_tree_digest, publication_commit, publication_committer_at,
                publication_digest, publication_json
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (receipt_id) DO NOTHING RETURNING receipt_id""",
            (
                publication.freeze_receipt_id,
                publication.schema_version,
                str(publication.freeze_receipt_digest),
                publication.implementation_commit,
                publication.implementation_tree_digest,
                publication.publication_commit,
                publication.publication_committer_at,
                str(publication.publication_digest),
                Jsonb(publication.to_canonical()),
            ),
        )
        inserted = cur.fetchone()
        if inserted is None:
            cur.execute(
                "SELECT publication_digest FROM candidate_freeze_publications WHERE receipt_id=%s",
                (publication.freeze_receipt_id,),
            )
            row = cur.fetchone()
            if row is None or cast(str, row[0]) != str(publication.publication_digest):
                raise RuntimeError("fixture freeze publication identity conflict")
''',
    encoding="utf-8",
)

import_line = (
    "from tests.integration.freeze_publication_fixture import record_fixture_publication\n\n"
)
inline_ctor = re.compile(
    r"PostgresCandidateFreezePublicationRepository\(\s*conn,\s*"
    r"persistence_authorized=True\s*\)\.record_fixture_publication\("
)
variable_call = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\.record_fixture_publication\(")

special = ROOT / "tests/integration/test_freeze_publication_postgres.py"
consumers: list[str] = []
for path in sorted((ROOT / "tests/integration").glob("test_*.py")):
    if path == special:
        continue
    source = path.read_text(encoding="utf-8")
    if ".record_fixture_publication(" not in source:
        continue
    original_count = source.count(".record_fixture_publication(")
    source = inline_ctor.sub("record_fixture_publication(conn, ", source)
    source = variable_call.sub("record_fixture_publication(conn, ", source)
    if ".record_fixture_publication(" in source:
        raise SystemExit(f"{path}: unhandled fixture publication call shape")
    if source.count("record_fixture_publication(conn, ") != original_count:
        raise SystemExit(f"{path}: fixture publication rewrite count mismatch")
    anchor = source.find("from frontier.")
    if anchor < 0:
        raise SystemExit(f"{path}: no frontier import anchor")
    source = source[:anchor] + import_line + source[anchor:]
    path.write_text(source, encoding="utf-8")
    consumers.append(path.as_posix())

source = special.read_text(encoding="utf-8")
old_special = '''        repo = PostgresCandidateFreezePublicationRepository(conn)\n        with pytest.raises(PermissionError):\n            repo.record_fixture_publication(publication)\n        authorized_repo = PostgresCandidateFreezePublicationRepository(\n            conn, persistence_authorized=True\n        )\n        with pytest.raises(PermissionError):\n            authorized_repo.record_publication(publication)\n        authorized_repo.record_fixture_publication(publication)\n'''
new_special = '''        repo = PostgresCandidateFreezePublicationRepository(conn)\n        with pytest.raises(PermissionError):\n            repo.record_publication(publication)\n        authorized_repo = PostgresCandidateFreezePublicationRepository(\n            conn, persistence_authorized=True\n        )\n        with pytest.raises(PermissionError):\n            authorized_repo.record_publication(publication)\n        record_fixture_publication(conn, publication)\n'''
if source.count(old_special) != 1:
    raise SystemExit("special publication repository fixture block not found")
source = source.replace(old_special, new_special, 1)
anchor = source.find("from frontier.")
if anchor < 0:
    raise SystemExit("special test has no frontier import anchor")
source = source[:anchor] + import_line + source[anchor:]
special.write_text(source, encoding="utf-8")
consumers.append(special.as_posix())

if len(consumers) != 5:
    raise SystemExit(f"expected five fixture consumers, found {consumers}")
print("fixture consumers:", *consumers, sep="\n")
