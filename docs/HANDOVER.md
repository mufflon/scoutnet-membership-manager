# Handover — Scoutnet kårverktyg

**Updated 2026-08-03.** Read this first, then `CLAUDE.md` (the standing spec),
then `docs/phase-2-design.md` and `docs/runbook.md`.

(The earlier handover lived outside the repo and was lost; this one is
version-controlled with the code and reflects the current state.)

## 1. Where the project is

**Phase 1 (read-only) and the Phase 2 uppflyttning write path are both built,
tested and deployed** on local k3s. `uv run pytest` passes offline (130 tests),
ruff clean.

The write path (apply an uppflyttning) is complete: `read_write` mode gate, the
serial one-member-at-a-time executor (dry-run default, pre-flight drift check,
journal, resume), pre-run snapshots (no personal data), reconcile, and undo —
plus the **Utför uppflyttning** and **Verifiera skrivning** blades and a
`verify-write` CLI. Exercised end-to-end against a schema-derived mock and, for
the single-member path, against live Scoutnet.

**Stage 2 is verified (2026-08-03).** `unit.raw_value` is the id
`update/membership` accepts — confirmed by moving member 3020341 Ledare (10172)
→ Hajarna (10155) through the tool and undoing it, checked by hand in the
Scoutnet UI. This was the last assumption that could block a real bulk run.

## 2. Which document wins

1. The running code and the live Scoutnet API — observed behaviour beats intent.
2. `CLAUDE.md` — the standing spec.
3. This file / `docs/phase-2-design.md` — current state and the write design.

## 3. Open actions

- [ ] **Rotate all three API keys.** `group/memberlist`, `organisation/group`
      and `organisation/update/membership` were all exposed during development
      (read into an AI session on 2026-08-03). Deferred by the operator to end of
      week once development is done — they stay live until regenerated on the
      Webbkoppling page. Update `karverktyg.conf` and confirm API-koll goes green.
- [ ] **Applicant-approval write workflow — not built.** It depends on the
      `awaiting_approval` variant, which reliably read-times-out for this kår.
      Establish whether that timeout is intermittent, size-related or permanent
      before scoping it. Uppflyttning is unaffected.
- [ ] **Probe the three undocumented endpoints** (`/organisation/project`,
      `/group/customlists`, `/group/resources`) — none is in the OpenAPI doc, so
      the drift-check can't see them. Follow capture discipline (raw to a
      gitignored dir; key names and counts only in anything shared).

## 4. Current deployment

Local k3s, namespace `karverktyg`, built by `scripts/k8s-up.sh` from
`karverktyg.conf`. Presently **`read_write`**, with the write allowlist bounded
to the single record `3020341` and a PVC-backed snapshot volume. Swap
`SCOUTNET_MODE` / `SCOUTNET_WRITE_ALLOWLIST` in `karverktyg.conf` and redeploy to
change this. Keys and the allowlist are deployment config only — never entered
in the UI (hard rule 7).

## 5. Version control

All Phase 2 work is on the local branch **`phase-2`** (branched from the Phase 1
tip that `main` points at). **Nothing is pushed and `phase-2` is not merged to
`main`** — there is no remote configured yet.

## 6. Non-negotiable safety invariants (still binding)

Chunk size defaults to **1**; write allowlist bounds the blast radius during
testing; `cancelled` is unreachable; dry-run is the default; no concurrent runs;
a snapshot is taken before every bulk run; reconcile after; undo available while
the snapshot is retained; no personal data in Postgres; no keys in the repo.
Full detail in `CLAUDE.md` §6 and §8.
