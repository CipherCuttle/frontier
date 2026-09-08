# PEF_V0 confirmatory VM operator — temporary external deployment

This directory is an **external deployment wrapper** for the already-frozen PEF_V0 confirmatory experiment. It must not be merged into canonical `main` during the confirmatory window.

## Frozen scientific identity

- canonical publication commit: `db206cda7eed92b62c706a10089c2571b4381d66`
- canonical publication tree: `5134857849b03c0dcff4595c8c9fe1059ffe47a6`
- expected freeze receipt: `freezereceipt_d8ea34d4f5ae84d7eb1de30272395876823c55287b8900af7ba8abadfc5c2346`
- run class: `CONFIRMATORY`
- canonical context: `true`
- promotion authority: **not granted**

The VM application checkout is detached at the exact canonical publication commit. The external operator rechecks commit, tree, parents, freeze binding, durability, publication binding, source-registry drift, database readiness, and canonical context before operation.

## Suggested Hetzner VM

Use a separate x86 Hetzner Cloud VM so Qnty and the developer workstation are unaffected.

- location: NBG1 preferred
- image: Ubuntu 24.04 LTS
- architecture: x86
- size: 2 vCPU / 4 GB RAM / 40 GB NVMe is the starting target; use the cheapest available x86 shared plan meeting or exceeding that
- network: Primary IPv4 enabled for simple SSH/outbound connectivity
- firewall: inbound SSH only from the operator's trusted IP where practical; outbound HTTPS/PostgreSQL/DNS must remain available
- no local database or persistent volume is required; canonical evidence remains in Neon

## Install

Use the `bootstrap.sh` from commit `3f35f8ea97b58b5789b04920eb287cc54bc6f549`.

The bootstrap:

1. installs a pinned `uv` bootstrap and Python 3.14;
2. checks out the canonical application at the exact detached commit;
3. verifies commit/tree/parents and the frozen lock;
4. downloads the operator and systemd unit from immutable ops commit `00249026c569b4ee623552b9a6690a1184fb9307`;
5. prompts securely for the canonical Neon PostgreSQL URL and stores it root-only at `/etc/frontier/frontier_database_url`;
6. runs `frontier doctor` and a read-only confirmatory preflight;
7. starts `frontier-pef-v0-confirmatory.service` only if every preflight gate passes.

No database secret is stored in Git.

## Observe

```bash
sudo systemctl status frontier-pef-v0-confirmatory.service
sudo journalctl -u frontier-pef-v0-confirmatory.service -f
sudo frontier-pef-v0-status
```

A singleton Postgres advisory lock prevents a second live worker cycle. Authority failure or drift exits with a non-restarting fatal status. Ordinary transient process failures are restartable by systemd.

## Scientific constraints

- Do not backfill missed historical boundaries.
- Do not shift the preregistered start/end window.
- Do not update the canonical application checkout during the window.
- Do not merge this temporary ops branch into canonical `main` during the window.
- Do not reinterpret a failed/missing candidate artifact as an empty ranking.
- Do not authorize promotion from this deployment procedure.
