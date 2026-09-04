# FRONTIER Planning Authority Index

Status: CANDIDATE_AUTHORITY

This directory records the planning authority frozen before product implementation.

Order of authority:
1. `CONSTITUTION.md`
2. `P01_REALITY_MAP.md`
3. `P02_OPERATOR_MODEL.md`
4. `P03_QUALITY_ATTRIBUTES.md`
5. `P04_P05_ARCHITECTURE.md`
6. `P06_THREAT_MODEL.md`
7. `P07_GOLDEN_SCENARIOS.md`
8. `P08_DATA_CONTRACT.md`
9. ADRs under `docs/adr/`
10. `SOURCE_POLICY.md`, `DONOR_LEDGER.md`, `DEBT_REGISTER.md`

Implementation governance: IMPLEMENT -> TEST -> ONE independent hostile review -> repair Critical/High -> ONE targeted re-review only if Critical/High fixes were required -> COMMIT/CLOSE -> MOVE FORWARD.

No production runtime implementation is authorized by PR-00 itself.