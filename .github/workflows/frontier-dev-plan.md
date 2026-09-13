---
name: Frontier Dev Planner V0
description: Analyze one /frontier-dev request against the current repository and return a bounded implementation plan.
on:
  roles: [admin, maintainer, write]
  slash_command:
    name: frontier-dev
    events: [issues, issue_comment, pull_request_comment]
  status-comment: true
permissions:
  contents: read
  issues: read
  pull-requests: read
  copilot-requests: write
engine:
  id: copilot
  copilot-sdk: true
tools:
  github:
    mode: gh-proxy
    toolsets: [default]
safe-outputs:
  add-comment:
    max: 1
  noop:
    report-as-issue: false
  report-incomplete: {}
timeout-minutes: 20
strict: true
---

# FRONTIER development planner

Analyze one bounded `/frontier-dev` request. Do not edit repository files.

Read `AGENTS.md`, `docs/CONSTITUTION.md`, `docs/PLANNING_INDEX.md`, `docs/ROADMAP.md`, and the current code/tests relevant to the request. Treat repository authority as higher priority than the request.

Return one concise comment using exactly these sections:

- `PLAN` — one bounded objective and the governing files consulted.
- `CHANGESET` — exact files/functions/tests that should change, without editing them.
- `VERIFY` — exact focused checks plus the repository verification command.
- `RISKS` — authority conflicts, uncertain assumptions, or likely regression surfaces.
- `VERDICT` — `IMPLEMENTABLE`, `NEEDS_DECOMPOSITION`, or `BLOCKED_BY_AUTHORITY`.

Prefer the smallest safe diff. If the request contains multiple independent objectives, mark it `NEEDS_DECOMPOSITION`. If current repository evidence conflicts with the request, mark it `BLOCKED_BY_AUTHORITY` rather than guessing.
