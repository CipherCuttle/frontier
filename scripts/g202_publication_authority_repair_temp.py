from __future__ import annotations

from pathlib import Path

ROOT = Path('.')


def replace_once(path: str, old: str, new: str) -> None:
    p = ROOT / path
    text = p.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{path}: expected one replacement, found {count}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')


# 1. Make publication evidence self-describing and add a strict GitHub main verifier.
path = 'src/frontier/application/freeze_publication.py'
replace_once(
    path,
    'FREEZE_PUBLICATION_SCHEMA_VERSION = "candidate-freeze-publication-v0"\nRANKING_WINDOW_SECONDS = 2_419_200\n',
    'FREEZE_PUBLICATION_SCHEMA_VERSION = "candidate-freeze-publication-v0"\n'
    'RANKING_WINDOW_SECONDS = 2_419_200\n'
    'GITHUB_PUBLICATION_REPOSITORY = "CipherCuttle/frontier"\n'
    'GITHUB_PUBLICATION_REF = "refs/heads/main"\n',
)
replace_once(
    path,
    '    publication_commit: str\n    publication_committer_at: datetime\n    schema_version: str = FREEZE_PUBLICATION_SCHEMA_VERSION\n',
    '    publication_commit: str\n    publication_committer_at: datetime\n'
    '    publication_repository: str = GITHUB_PUBLICATION_REPOSITORY\n'
    '    publication_ref: str = GITHUB_PUBLICATION_REF\n'
    '    schema_version: str = FREEZE_PUBLICATION_SCHEMA_VERSION\n',
)
replace_once(
    path,
    '        if self.schema_version != FREEZE_PUBLICATION_SCHEMA_VERSION:\n'
    '            raise ValueError("freeze publication schema mismatch")\n',
    '        if self.publication_repository != GITHUB_PUBLICATION_REPOSITORY:\n'
    '            raise ValueError("freeze publication repository mismatch")\n'
    '        if self.publication_ref != GITHUB_PUBLICATION_REF:\n'
    '            raise ValueError("freeze publication ref mismatch")\n'
    '        if self.schema_version != FREEZE_PUBLICATION_SCHEMA_VERSION:\n'
    '            raise ValueError("freeze publication schema mismatch")\n',
)
replace_once(
    path,
    '            "publication_commit": self.publication_commit,\n'
    '            "publication_committer_at": canonical_timestamp(self.publication_committer_at),\n'
    '            "schema_version": self.schema_version,\n',
    '            "publication_commit": self.publication_commit,\n'
    '            "publication_committer_at": canonical_timestamp(self.publication_committer_at),\n'
    '            "publication_ref": self.publication_ref,\n'
    '            "publication_repository": self.publication_repository,\n'
    '            "schema_version": self.schema_version,\n',
)
replace_once(
    path,
    'def _matching_receipt_path(root: Path, receipt: CandidateFreezeReceipt) -> Path:\n',
    'def _github_repository_from_remote(remote_url: str) -> str | None:\n'
    '    value = remote_url.strip()\n'
    '    prefixes = (\n'
    '        "https://github.com/",\n'
    '        "ssh://git@github.com/",\n'
    '        "git@github.com:",\n'
    '    )\n'
    '    for prefix in prefixes:\n'
    '        if value.startswith(prefix):\n'
    '            repository = value[len(prefix) :]\n'
    '            if repository.endswith(".git"):\n'
    '                repository = repository[:-4]\n'
    '            return repository.strip("/")\n'
    '    return None\n\n\n'
    'def require_github_main_publication(\n'
    '    root: Path, publication: CandidateFreezePublication\n'
    ') -> None:\n'
    '    """Prove that the locally derived publication commit is GitHub ``main``.\n\n'
    '    ``derive_freeze_publication`` proves the local immutable Git shape. This\n'
    '    second gate resolves ``origin/refs/heads/main`` from GitHub itself and\n'
    '    requires that remote commit to be exactly the derived publication commit.\n'
    '    """\n'
    '    remote_url = _git_text(root, ["remote", "get-url", "origin"])\n'
    '    repository = _github_repository_from_remote(remote_url)\n'
    '    if repository is None or repository.lower() != GITHUB_PUBLICATION_REPOSITORY.lower():\n'
    '        raise RuntimeError("candidate freeze publication origin is not canonical GitHub repository")\n'
    '    remote = _git_text(\n'
    '        root, ["ls-remote", "--exit-code", "origin", GITHUB_PUBLICATION_REF]\n'
    '    )\n'
    '    lines = [line for line in remote.splitlines() if line.strip()]\n'
    '    if len(lines) != 1:\n'
    '        raise RuntimeError("GitHub main publication ref did not resolve uniquely")\n'
    '    fields = lines[0].split()\n'
    '    if len(fields) != 2 or fields[1] != GITHUB_PUBLICATION_REF:\n'
    '        raise RuntimeError("GitHub main publication ref response is malformed")\n'
    '    if fields[0] != publication.publication_commit:\n'
    '        raise RuntimeError("derived publication commit is not current GitHub main")\n\n\n'
    'def _matching_receipt_path(root: Path, receipt: CandidateFreezeReceipt) -> Path:\n',
)
replace_once(
    path,
    '\n\n__all__ = [\n',
    '\n\ndef derive_github_main_freeze_publication(\n'
    '    root: Path, receipt: CandidateFreezeReceipt, *, receipt_path: Path | None = None\n'
    ') -> CandidateFreezePublication:\n'
    '    publication = derive_freeze_publication(root, receipt, receipt_path=receipt_path)\n'
    '    require_github_main_publication(root, publication)\n'
    '    return publication\n\n\n'
    '__all__ = [\n',
)
replace_once(
    path,
    '    "FREEZE_PUBLICATION_SCHEMA_VERSION",\n'
    '    "RANKING_WINDOW_SECONDS",\n',
    '    "FREEZE_PUBLICATION_SCHEMA_VERSION",\n'
    '    "GITHUB_PUBLICATION_REF",\n'
    '    "GITHUB_PUBLICATION_REPOSITORY",\n'
    '    "RANKING_WINDOW_SECONDS",\n',
)
replace_once(
    path,
    '    "derive_freeze_publication",\n'
    '    "first_confirmatory_boundary",\n'
    '    "require_confirmatory_boundary",\n',
    '    "derive_freeze_publication",\n'
    '    "derive_github_main_freeze_publication",\n'
    '    "first_confirmatory_boundary",\n'
    '    "require_confirmatory_boundary",\n'
    '    "require_github_main_publication",\n',
)

# 2. Put Git verification below the publication persistence boundary. Raw writes fail closed;
#    tests have an explicitly named fixture-only seam.
adapter = '''from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import cast

import psycopg
from psycopg.types.json import Jsonb

from frontier.application.freeze_publication import (
    CandidateFreezePublication,
    derive_github_main_freeze_publication,
)
from frontier.domain.candidate_freeze import CandidateFreezeReceipt
from frontier.domain.digests import Digest


class PostgresCandidateFreezePublicationRepository:
    def __init__(
        self,
        connection: psycopg.Connection[tuple[object, ...]],
        *,
        persistence_authorized: bool = False,
    ) -> None:
        self._connection = connection
        self._persistence_authorized = persistence_authorized

    def record_publication(self, publication: CandidateFreezePublication) -> None:
        del publication
        raise PermissionError(
            "raw candidate freeze publication persistence is forbidden; "
            "use record_verified_publication or the explicit fixture seam"
        )

    def record_verified_publication(
        self,
        receipt: CandidateFreezeReceipt,
        *,
        root: Path,
        receipt_path: Path | None = None,
    ) -> CandidateFreezePublication:
        if not self._persistence_authorized:
            raise PermissionError("candidate freeze publication persistence is not authorized")
        publication = derive_github_main_freeze_publication(
            root, receipt, receipt_path=receipt_path
        )
        self._record(publication)
        return publication

    def record_fixture_publication(self, publication: CandidateFreezePublication) -> None:
        """Explicit test/fixture seam; never use for operator publication."""
        if not self._persistence_authorized:
            raise PermissionError("candidate freeze publication persistence is not authorized")
        self._record(publication)

    def _record(self, publication: CandidateFreezePublication) -> None:
        with self._connection.transaction(), self._connection.cursor() as cur:
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
                    "SELECT publication_digest FROM candidate_freeze_publications "
                    "WHERE receipt_id=%s",
                    (publication.freeze_receipt_id,),
                )
                row = cur.fetchone()
                if row is None or cast(str, row[0]) != str(publication.publication_digest):
                    raise RuntimeError("freeze publication identity conflict")

    def get_publication(self, receipt_id: str) -> CandidateFreezePublication | None:
        with self._connection.cursor() as cur:
            cur.execute(
                """SELECT freeze_receipt_digest, implementation_commit, implementation_tree_digest,
                       publication_commit, publication_committer_at, publication_digest,
                       publication_json
                       FROM candidate_freeze_publications WHERE receipt_id=%s""",
                (receipt_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        publication = CandidateFreezePublication(
            freeze_receipt_id=receipt_id,
            freeze_receipt_digest=Digest(cast(str, row[0])),
            implementation_commit=cast(str, row[1]),
            implementation_tree_digest=cast(str, row[2]),
            publication_commit=cast(str, row[3]),
            publication_committer_at=cast(datetime, row[4]),
        )
        if str(publication.publication_digest) != cast(str, row[5]):
            raise RuntimeError("freeze publication row does not bind its stored digest")
        if publication.to_canonical() != cast(dict[str, object], row[6]):
            raise RuntimeError("freeze publication row does not bind its canonical payload")
        return publication


__all__ = ["PostgresCandidateFreezePublicationRepository"]
'''
(ROOT / 'src/frontier/adapters/postgres/freeze_publication.py').write_text(adapter, encoding='utf-8')

# 3. Make the DB trigger bind the JSON evidence to the canonical GitHub main declaration.
path = 'migrations/versions/0013_freeze_publication_authority.py'
replace_once(
    path,
    "      IF NEW.freeze_receipt_digest <> r.receipt_digest OR NEW.implementation_commit <> r.implementation_commit OR NEW.implementation_tree_digest <> r.implementation_tree_digest THEN\n"
    "        RAISE EXCEPTION 'freeze publication identity does not match receipt';\n"
    "      END IF;\n",
    "      IF NEW.freeze_receipt_digest <> r.receipt_digest OR NEW.implementation_commit <> r.implementation_commit OR NEW.implementation_tree_digest <> r.implementation_tree_digest THEN\n"
    "        RAISE EXCEPTION 'freeze publication identity does not match receipt';\n"
    "      END IF;\n"
    "      IF NEW.publication_json->>'schema_version' IS DISTINCT FROM NEW.schema_version\n"
    "         OR NEW.publication_json->>'freeze_receipt_id' IS DISTINCT FROM NEW.receipt_id\n"
    "         OR NEW.publication_json->>'freeze_receipt_digest' IS DISTINCT FROM NEW.freeze_receipt_digest\n"
    "         OR NEW.publication_json->>'implementation_commit' IS DISTINCT FROM NEW.implementation_commit\n"
    "         OR NEW.publication_json->>'implementation_tree_digest' IS DISTINCT FROM NEW.implementation_tree_digest\n"
    "         OR NEW.publication_json->>'publication_commit' IS DISTINCT FROM NEW.publication_commit\n"
    "         OR (NEW.publication_json->>'publication_committer_at')::timestamptz IS DISTINCT FROM NEW.publication_committer_at\n"
    "         OR NEW.publication_json->>'publication_repository' IS DISTINCT FROM 'CipherCuttle/frontier'\n"
    "         OR NEW.publication_json->>'publication_ref' IS DISTINCT FROM 'refs/heads/main' THEN\n"
    "        RAISE EXCEPTION 'freeze publication canonical evidence is not bound to GitHub main';\n"
    "      END IF;\n",
)

# 4. Runtime authority consumers must validate publication digest + canonical payload before using its clock.
path = 'src/frontier/adapters/postgres/experiment_attempts.py'
replace_once(
    path,
    'from frontier.application.freeze_publication import require_confirmatory_boundary\n',
    'from frontier.application.freeze_publication import (\n'
    '    CandidateFreezePublication,\n'
    '    require_confirmatory_boundary,\n'
    ')\n',
)
old_claim = '''            cur.execute(
                """
                SELECT r.status, r.durable_freeze_at, p.publication_committer_at
                FROM candidate_freeze_receipts r
                LEFT JOIN candidate_freeze_publications p ON p.receipt_id = r.receipt_id
                WHERE r.receipt_id = %s AND r.experiment_id = %s
                """,
                (expected_receipt_id, PEF_EXPERIMENT_ID),
            )
            authority = cur.fetchone()
            if authority is None:
                return skip("bound candidate freeze receipt is not present in canonical DB")
            if FreezeStatus(cast(str, authority[0])) is not FreezeStatus.FROZEN:
                return skip("bound candidate freeze receipt is not FROZEN")
            durable_freeze_at = cast(datetime | None, authority[1])
            if durable_freeze_at is None:
                return skip("bound freeze receipt has durable_freeze_at NULL (not durable)")
            publication_committer_at = cast(datetime | None, authority[2])
            if publication_committer_at is None:
                return skip("bound freeze receipt has no verified Git publication")
            if publication_committer_at < durable_freeze_at:
                return skip("Git publication precedes canonical DB durability")
'''
new_claim = '''            cur.execute(
                """
                SELECT r.status, r.durable_freeze_at, r.receipt_digest,
                       r.implementation_commit, r.implementation_tree_digest,
                       p.freeze_receipt_digest, p.implementation_commit,
                       p.implementation_tree_digest, p.publication_commit,
                       p.publication_committer_at, p.publication_digest,
                       p.publication_json
                FROM candidate_freeze_receipts r
                LEFT JOIN candidate_freeze_publications p ON p.receipt_id = r.receipt_id
                WHERE r.receipt_id = %s AND r.experiment_id = %s
                """,
                (expected_receipt_id, PEF_EXPERIMENT_ID),
            )
            authority = cur.fetchone()
            if authority is None:
                return skip("bound candidate freeze receipt is not present in canonical DB")
            if FreezeStatus(cast(str, authority[0])) is not FreezeStatus.FROZEN:
                return skip("bound candidate freeze receipt is not FROZEN")
            durable_freeze_at = cast(datetime | None, authority[1])
            if durable_freeze_at is None:
                return skip("bound freeze receipt has durable_freeze_at NULL (not durable)")
            if authority[9] is None:
                return skip("bound freeze receipt has no verified Git publication")
            try:
                publication = CandidateFreezePublication(
                    freeze_receipt_id=expected_receipt_id,
                    freeze_receipt_digest=Digest(cast(str, authority[5])),
                    implementation_commit=cast(str, authority[6]),
                    implementation_tree_digest=cast(str, authority[7]),
                    publication_commit=cast(str, authority[8]),
                    publication_committer_at=cast(datetime, authority[9]),
                )
            except (TypeError, ValueError):
                return skip("bound Git publication identity is invalid")
            if (
                str(publication.freeze_receipt_digest) != cast(str, authority[2])
                or publication.implementation_commit != cast(str, authority[3])
                or publication.implementation_tree_digest != cast(str, authority[4])
            ):
                return skip("bound Git publication identity does not match freeze receipt")
            if str(publication.publication_digest) != cast(str, authority[10]):
                return skip("bound Git publication digest mismatch")
            if publication.to_canonical() != cast(dict[str, object], authority[11]):
                return skip("bound Git publication canonical payload mismatch")
            publication_committer_at = publication.publication_committer_at
            if publication_committer_at < durable_freeze_at:
                return skip("Git publication precedes canonical DB durability")
'''
replace_once(path, old_claim, new_claim)
replace_once(
    path,
    '''                       r.receipt_digest, r.frozen_at, r.verified_at,
                       r.original_receipt_digest, r.durable_freeze_at,
                       p.publication_commit, p.publication_committer_at
''',
    '''                       r.receipt_digest, r.frozen_at, r.verified_at,
                       r.original_receipt_digest, r.durable_freeze_at,
                       p.freeze_receipt_digest, p.implementation_commit,
                       p.implementation_tree_digest, p.publication_commit,
                       p.publication_committer_at, p.publication_digest,
                       p.publication_json
''',
)
replace_once(
    path,
    '''        return FreezeBinding(
            receipt=receipt,
            durable_freeze_at=None if row[13] is None else cast(datetime, row[13]),
            publication_commit=None if row[14] is None else cast(str, row[14]),
            publication_committer_at=None if row[15] is None else cast(datetime, row[15]),
        )
''',
    '''        publication_commit: str | None = None
        publication_committer_at: datetime | None = None
        if row[18] is not None:
            try:
                publication = CandidateFreezePublication(
                    freeze_receipt_id=receipt.receipt_id,
                    freeze_receipt_digest=Digest(cast(str, row[14])),
                    implementation_commit=cast(str, row[15]),
                    implementation_tree_digest=cast(str, row[16]),
                    publication_commit=cast(str, row[17]),
                    publication_committer_at=cast(datetime, row[18]),
                )
            except (TypeError, ValueError) as error:
                raise RuntimeError("freeze publication row is invalid") from error
            if publication.freeze_receipt_digest != receipt.receipt_digest:
                raise RuntimeError("freeze publication row does not bind freeze receipt digest")
            if publication.implementation_commit != receipt.implementation_commit:
                raise RuntimeError("freeze publication row does not bind implementation commit")
            if publication.implementation_tree_digest != receipt.implementation_tree_digest:
                raise RuntimeError("freeze publication row does not bind implementation tree")
            if str(publication.publication_digest) != cast(str, row[19]):
                raise RuntimeError("freeze publication row does not bind its stored digest")
            if publication.to_canonical() != cast(dict[str, object], row[20]):
                raise RuntimeError("freeze publication row does not bind its canonical payload")
            publication_commit = publication.publication_commit
            publication_committer_at = publication.publication_committer_at
        return FreezeBinding(
            receipt=receipt,
            durable_freeze_at=None if row[13] is None else cast(datetime, row[13]),
            publication_commit=publication_commit,
            publication_committer_at=publication_committer_at,
        )
''',
)

# 5. Add the only production publication writer to the operator CLI.
path = 'src/frontier/cli/main.py'
replace_once(
    path,
    'FREEZE_PERSIST_AUTHORIZED_ENV = "FRONTIER_FREEZE_PERSIST_AUTHORIZED"\n',
    'FREEZE_PERSIST_AUTHORIZED_ENV = "FRONTIER_FREEZE_PERSIST_AUTHORIZED"\n'
    'FREEZE_PUBLICATION_PERSIST_AUTHORIZED_ENV = (\n'
    '    "FRONTIER_FREEZE_PUBLICATION_PERSIST_AUTHORIZED"\n'
    ')\n',
)
replace_once(
    path,
    '\n\ndef _freeze_components_payload(inputs: FreezeInputs) -> dict[str, object]:\n',
    '\n\ndef _freeze_publication_persist_refusal_payload() -> dict[str, str]:\n'
    '    return {\n'
    '        "error": "FREEZE_PUBLICATION_PERSIST_UNAUTHORIZED",\n'
    '        "message": (\n'
    '            "Refusing to persist Git publication authority unless the final "\n'
    '            "candidate-freeze receipt has been merged to GitHub main and "\n'
    '            f"{FREEZE_PUBLICATION_PERSIST_AUTHORIZED_ENV}=1 is set explicitly."\n'
    '        ),\n'
    '    }\n\n\n'
    'def _freeze_components_payload(inputs: FreezeInputs) -> dict[str, object]:\n',
)
insert_publish = '''

def freeze_publish(root: Path, *, receipt_id: str, database_url: str) -> int:
    """Verify GitHub main publication authority, then persist that exact evidence."""
    if os.getenv(FREEZE_PUBLICATION_PERSIST_AUTHORIZED_ENV) != "1":
        print(
            json.dumps(_freeze_publication_persist_refusal_payload(), sort_keys=True),
            file=sys.stderr,
        )
        return 2
    try:
        receipt = _load_freeze_receipt(None, receipt_id, database_url)
    except ValueError as error:
        print(
            json.dumps({"error": "FREEZE_RECEIPT_UNLOADABLE", "detail": str(error)}),
            file=sys.stderr,
        )
        return 2
    if receipt is None:
        print(
            json.dumps({"error": "FREEZE_RECEIPT_NOT_FOUND", "receipt_id": receipt_id}),
            file=sys.stderr,
        )
        return 2

    import psycopg

    from frontier.adapters.postgres.freeze_publication import (
        PostgresCandidateFreezePublicationRepository,
    )
    from frontier.adapters.postgres.readiness import verify_database_readiness

    try:
        with psycopg.connect(database_url) as conn:
            verify_database_readiness(conn)
            publication = PostgresCandidateFreezePublicationRepository(
                conn, persistence_authorized=True
            ).record_verified_publication(receipt, root=root)
    except (RuntimeError, ValueError) as error:
        print(
            json.dumps(
                {"error": "FREEZE_PUBLICATION_VERIFICATION_FAILED", "detail": str(error)},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            {
                "publication": publication.to_canonical(),
                "publication_digest": str(publication.publication_digest),
                "receipt_id": receipt_id,
            },
            sort_keys=True,
        )
    )
    return 0
'''
replace_once(path, '\n\ndef freeze_verify(\n', insert_publish + '\n\ndef freeze_verify(\n')
replace_once(
    path,
    '''    if args.freeze_command == "verify":
        url = _freeze_database_url(args.database_url, parser) if args.receipt_id else None
        return freeze_verify(
            args.root,
            receipt_file=args.receipt_file,
            receipt_id=args.receipt_id,
            database_url=url,
        )
    return freeze_durability(
        args.receipt_id, database_url=_freeze_database_url(args.database_url, parser)
    )
''',
    '''    if args.freeze_command == "verify":
        url = _freeze_database_url(args.database_url, parser) if args.receipt_id else None
        return freeze_verify(
            args.root,
            receipt_file=args.receipt_file,
            receipt_id=args.receipt_id,
            database_url=url,
        )
    if args.freeze_command == "publish":
        return freeze_publish(
            args.root,
            receipt_id=args.receipt_id,
            database_url=_freeze_database_url(args.database_url, parser),
        )
    return freeze_durability(
        args.receipt_id, database_url=_freeze_database_url(args.database_url, parser)
    )
''',
)
replace_once(
    path,
    '''    freeze_durability_parser = freeze_sub.add_parser(
        "durability", help="report durable_freeze_at for a stored receipt id"
    )
''',
    '''    freeze_publish_parser = freeze_sub.add_parser(
        "publish", help="verify and persist the exact GitHub main freeze publication"
    )
    freeze_publish_parser.add_argument("--root", type=Path, default=Path("."))
    freeze_publish_parser.add_argument("--receipt-id", required=True)
    freeze_publish_parser.add_argument("--database-url")

    freeze_durability_parser = freeze_sub.add_parser(
        "durability", help="report durable_freeze_at for a stored receipt id"
    )
''',
)

# 6. Every synthetic publication in tests must use the explicitly named fixture seam.
for p in (ROOT / 'tests').rglob('*.py'):
    text = p.read_text(encoding='utf-8')
    if '.record_publication(' in text:
        p.write_text(text.replace('.record_publication(', '.record_fixture_publication('), encoding='utf-8')

# Raw publication must remain forbidden even with the lower-level capability.
path = 'tests/integration/test_freeze_publication_postgres.py'
replace_once(
    path,
    '''        PostgresCandidateFreezePublicationRepository(
            conn, persistence_authorized=True
        ).record_fixture_publication(publication)
        loaded = repo.get_publication(receipt.receipt_id)
''',
    '''        authorized_repo = PostgresCandidateFreezePublicationRepository(
            conn, persistence_authorized=True
        )
        with pytest.raises(PermissionError):
            authorized_repo.record_publication(publication)
        authorized_repo.record_fixture_publication(publication)
        loaded = repo.get_publication(receipt.receipt_id)
''',
)

# 7. Unit proof that strict publication checks canonical GitHub origin + remote main SHA.
path = 'tests/unit/test_freeze_publication.py'
replace_once(path, 'import subprocess\n', 'import subprocess\n\nimport pytest\n\nimport frontier.application.freeze_publication as freeze_publication_module\n')
replace_once(
    path,
    '''from frontier.application.freeze_publication import (
    confirmatory_window_end,
    derive_freeze_publication,
    first_confirmatory_boundary,
    require_confirmatory_boundary,
)
''',
    '''from frontier.application.freeze_publication import (
    CandidateFreezePublication,
    confirmatory_window_end,
    derive_freeze_publication,
    first_confirmatory_boundary,
    require_confirmatory_boundary,
    require_github_main_publication,
)
''',
)
append = '''

def test_github_main_publication_requires_canonical_remote_and_exact_remote_head(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    publication = CandidateFreezePublication(
        freeze_receipt_id="freezereceipt_" + "a" * 64,
        freeze_receipt_digest=Digest("sha256:" + "b" * 64),
        implementation_commit="c" * 40,
        implementation_tree_digest="d" * 40,
        publication_commit="e" * 40,
        publication_committer_at=PUB,
    )
    responses = {
        ("remote", "get-url", "origin"): "https://github.com/CipherCuttle/frontier.git",
        (
            "ls-remote",
            "--exit-code",
            "origin",
            "refs/heads/main",
        ): f"{publication.publication_commit}\\trefs/heads/main",
    }

    def git_text(root: Path, args: list[str]) -> str:
        assert root == tmp_path
        return responses[tuple(args)]

    monkeypatch.setattr(freeze_publication_module, "_git_text", git_text)
    require_github_main_publication(tmp_path, publication)

    responses[("ls-remote", "--exit-code", "origin", "refs/heads/main")] = (
        "f" * 40 + "\\trefs/heads/main"
    )
    with pytest.raises(RuntimeError, match="not current GitHub main"):
        require_github_main_publication(tmp_path, publication)

    responses[("remote", "get-url", "origin")] = "https://github.com/attacker/fork.git"
    with pytest.raises(RuntimeError, match="not canonical GitHub repository"):
        require_github_main_publication(tmp_path, publication)
'''
(ROOT / path).write_text((ROOT / path).read_text(encoding='utf-8') + append, encoding='utf-8')

# 8. CLI guard must fail before touching an invalid DB/network endpoint.
path = 'tests/unit/test_freeze_cli.py'
replace_once(
    path,
    '''from frontier.cli.main import (
    FREEZE_PERSIST_AUTHORIZED_ENV,
    durability_payload,
    freeze_derive,
    freeze_verify,
)
''',
    '''from frontier.cli.main import (
    FREEZE_PERSIST_AUTHORIZED_ENV,
    FREEZE_PUBLICATION_PERSIST_AUTHORIZED_ENV,
    durability_payload,
    freeze_derive,
    freeze_publish,
    freeze_verify,
)
''',
)
append = '''

def test_publication_persist_guard_refuses_before_db_or_git_access(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(FREEZE_PUBLICATION_PERSIST_AUTHORIZED_ENV, raising=False)
    rc = freeze_publish(
        REPO_ROOT,
        receipt_id="freezereceipt_" + "a" * 64,
        database_url="postgresql://invalid.invalid/db",
    )
    assert rc == 2
    captured = capsys.readouterr()
    refusal = json.loads(captured.err)
    assert refusal["error"] == "FREEZE_PUBLICATION_PERSIST_UNAUTHORIZED"
    assert captured.out == ""


def test_publication_persist_guard_env_is_documented_name() -> None:
    assert (
        FREEZE_PUBLICATION_PERSIST_AUTHORIZED_ENV
        == "FRONTIER_FREEZE_PUBLICATION_PERSIST_AUTHORIZED"
    )
'''
(ROOT / path).write_text((ROOT / path).read_text(encoding='utf-8') + append, encoding='utf-8')

print('G2-02 publication authority repair applied')
