# karverktyg — Scoutnet kårverktyg

Internal tool for a Swedish scoutkår (default: **Scoutkåren Finn**, Lund). It
reads member data from Scoutnet, surfaces what leaders need to act on each term,
and — in later phases — writes back a small number of carefully controlled
changes.

**Phase 1 is read-only; Phase 2 (this branch) adds a controlled write path** for
applying an uppflyttning — dry-run by default, one member per request, snapshot +
journal + reconcile, fully undoable (§6, §8 of `CLAUDE.md`). It is only active in
`read_write` mode. One prerequisite remains before a real bulk run: verifying
`troop_id` against the write endpoint on a single placeholder record (see
`docs/runbook.md`). Python library + Flask HTTP service + static frontend,
deployable to Kubernetes.

---

## Glossary (Scoutnet vocabulary)

Scoutnet uses English names for Swedish concepts. Code uses the API's vocabulary.

| Swedish | Scoutnet / API | Notes |
|---|---|---|
| kår | `group` | The whole local organisation |
| avdelning | `troop` — `unit`, `unit_type`, `troop_id` | The section a scout belongs to |
| patrull | `patrol` — `patrol_id` | |
| gren | *(not exposed)* | Scoutnet does not publish which gren an avdelning belongs to |
| arrangemang | `project` | Also how Scoutnet models meeting attendance |
| termin | `term` — `term_id`, `term_label` | Use Scoutnet's own term values |
| medlemsnummer | `member_no` | The stable unique identifier. Everything keys on this |

## What you can do in Phase 1 (read-only)

- **Överblick** — active member count, avdelningar, term.
- **Medlemsavgifter** — unpaid dues per avdelning (validated against the *previous*
  term; the current term is not yet invoiced, so that view is empty until it is).
- **Väntelista** — waiting list / awaiting approval, plus **copy-paste
  membership-request email drafts** (scouts → guardians, Ledare → the person;
  editable templates). Nothing is sent — you copy the text into your own mail.
- **Uppflyttning** — the computed master set (who moves where at the summer
  shift), and a downloadable **Excel changelist** for manual entry in Scoutnet.
- **Utför** *(Phase 2, `read_write` only)* — apply the reviewed uppflyttning:
  dry-run drift report, confirm-to-execute, live progress, and undo. See
  `docs/runbook.md`.
- **Anmärkningar** — data-quality and membership-roll findings (advisory only).
- **Funktioner** — capabilities of this deployment (endpoints, keys present, mode).

Not possible with the documented API (out of scope): attendance tracking, and
creating next year's arrangemang. See `docs/phase-0-findings.md` and `CLAUDE.md` §5.

## Quick start

Requires Python 3.14 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

**Fixture mode** runs the whole app with **no credentials and no database** (an
in-memory SQLite is created), against the committed scrubbed fixture:

```bash
uv run karverktyg serve --mode fixture --port 8000
# open http://localhost:8000
```

**Tests** (offline, no network):

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

**Docker / local Postgres:**

```bash
docker compose up --build   # app in fixture mode + a Postgres alongside
```

## Configuration

All configuration is environment-driven (`pydantic-settings`), prefix `SCOUTNET_`.
See `.env.example`. Kår/bracket configuration is a JSON document
(`config/karverktyg.default.json`, a marked placeholder) mountable as a ConfigMap.

| Variable | Purpose |
|---|---|
| `SCOUTNET_MODE` | `fixture` \| `read_only` (default) \| `read_write` (Phase 2 write path) |
| `SCOUTNET_ENTITY_ID` | HTTP Basic username — the internal entity id (1025 for Finn) |
| `SCOUTNET_MEMBERLIST_KEY` | per-endpoint key for `/group/memberlist` |
| `SCOUTNET_ORGANISATION_GROUP_KEY` | per-endpoint key for `/organisation/group` |
| `SCOUTNET_UPDATE_MEMBERSHIP_KEY` | per-endpoint write key (required for `read_write`) |
| `SCOUTNET_WRITE_ALLOWLIST` | JSON list of member numbers writes may touch (empty = none) |
| `SCOUTNET_SNAPSHOT_DIR` | mounted-volume path for pre-run snapshot files (`read_write`) |
| `SCOUTNET_CHUNK_SIZE` / `SCOUTNET_CHUNK_DELAY_S` | write chunk size (**default 1**) and delay |
| `SCOUTNET_SNAPSHOT_RETENTION_DAYS` | snapshot retention window (default 30; gates undo) |
| `SCOUTNET_DATABASE_URL` | Postgres DSN (fixture mode uses in-memory SQLite) |
| `SCOUTNET_COHORT_YEAR` | uppflyttning year N; leave unset to derive from the live term (guarded) |
| `SCOUTNET_KAR_NAME` | kår display name (default Scoutkåren Finn) |

Age brackets and uppflyttning flows are **configuration, not code** (`CLAUDE.md`
§13, §17). The shipped config is a clearly-marked placeholder.

## Obtaining an API key

Keys are **per endpoint, per body** (not per user), permanent until regenerated.

1. In Scoutnet, enable **Din kår → Webbkoppling**.
2. Generate a key for **each** endpoint you need (`group/memberlist`,
   `organisation/group`). The available endpoints are set by a system
   administrator and vary — confirm on the Webbkoppling page.
3. The Basic-auth username is the **internal entity id** shown as "Kår-ID för
   webbtjänster" (1025 for Finn) — not necessarily the visible kår number.
4. Put keys in the environment / a Kubernetes Secret. **Never commit a key.**

## Modes (§6)

| Mode | Reads | Writes | Data source |
|---|---|---|---|
| `fixture` | yes | no | Committed fixtures. No network, no credentials. |
| `read_only` | yes | **no** | Live Scoutnet |
| `read_write` | yes | yes | Live Scoutnet — the write path (Phase 2) |

Enforced at client construction: `fixture`/`read_only` clients have **no** write
method at all; the single `update_membership` method exists only on the
`read_write` client, which `build_client` returns only when the write key is set.
`read_write` must be set deliberately and shows a banner in the UI while active.

## Deployment

- `Dockerfile` (multi-stage, non-root, gunicorn), `k8s/` manifests (deployment
  with liveness `/healthz` + readiness `/readyz`; readiness checks Postgres only,
  never Scoutnet), `k8s/cronjobs.yaml` (read-only canary + spec-drift).
- Human authentication is expected at the ingress (`k8s/ingress.example.yaml`).
- Image distribution is unsolved (§14) — build reproducibly with `docker buildx`
  and choose a registry at deploy time.

## Layout

```
src/karverktyg/
  settings.py            app settings (pydantic-settings)
  collation.py i18n.py   Swedish collation (§2) and UI strings
  config/                bracket + avdelning config models and loader (§17)
  scoutnet/              API client (fixture + read-only) and parser (§4)
  roster.py              troop-id index (from unit.raw_value)
  findings/              data-quality + membership-roll findings (§11)
  uppflyttning/          cohort-year guard + master-set engine (§17)
  export/                Excel changelist + reconciliation (§7)
  write/                 Phase 2 write path: executor, snapshots, undo (§8)
  membership/            membership-request email drafts + templates (§10)
  mail/                  MailSender interface, recording fake, Gmail (§10)
  db/                    SQLAlchemy models (no personal-data columns, §9)
  web/                   Flask app, read-only API, capabilities, static frontend
  jobs/                  read-only canary + spec-drift (§14)
scripts/                 Phase-0 throwaway spikes (capture + scrubber)
config/ fixtures/ migrations/ k8s/ vendor/ branding/ docs/
```

## Status / limits

Phase 2 write path (uppflyttning apply) is built and tested — dry-run, execute,
resume, undo, snapshots — and exercised end to end against a schema-derived mock.
**One prerequisite before a real bulk run:** verify `troop_id` against the live
`update/membership` endpoint on a single placeholder record (`docs/runbook.md`,
§1). The applicant-approval write workflow is **not** built — it depends on the
`awaiting_approval` variant, which currently read-times-out for this kår.

Other standing limits: the Äventyrare→Utmanare step stays *pending* until the
operator fills in `cohort_year` for the target Utmanare avdelning. Payment views
are validated against the previous (invoiced) term only until Höst is invoiced.
PDF report rendering (§7) is templated via WeasyPrint but not yet wired end-to-end.
