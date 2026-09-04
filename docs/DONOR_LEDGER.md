# FRONTIER Donor Ledger

Donor systems are never runtime authorities. Reuse classification: CONCEPT, BEHAVIOR, IMPLEMENTATION, FIXTURE, REJECT.

| Donor | Candidate reuse | Class | FRONTIER rule |
|---|---|---|---|
| `CipherCuttle/daemonlink` | deterministic stable IDs/hashes | BEHAVIOR | re-specify + test under FRONTIER authority |
| `CipherCuttle/daemonlink` | canonical URL handling | BEHAVIOR | bounded donor behavior only |
| `CipherCuttle/daemonlink` | RSS/feed parsing fixtures | FIXTURE/BEHAVIOR | copy only with provenance and tests |
| `CipherCuttle/daemonlink` | source adapter abstraction | CONCEPT | redesign to FRONTIER source contract |
| `CipherCuttle/daemonlink` | WTP/pain/alive/signal-strength ontology | REJECT | never propagate |
| `CipherCuttle/daemonlink` | SRCNOW channel quotas/allowlists | REJECT | hidden legacy product policy |
| `CipherCuttle/Srcnow` | FLASH/CONFIRMED/RETRACTED history | CONCEPT | only historical inspiration; current assertion model differs |
| `CipherCuttle/Srcnow` | personalization affecting truth rank | REJECT | canonical rank remains shared/public |
| `CipherCuttle/Synworks---Nullstate` | Prove It / falsification doctrine | CONCEPT | evidence-first dossier design |
| `CipherCuttle/Smokestack` | point-in-time/replay/prospective discipline | CONCEPT/BEHAVIOR | carry into evaluation and receipts |

Any actual implementation/code/fixture reuse must add exact donor repo, commit, path, reuse class, reason, and FRONTIER replacement tests before merge.