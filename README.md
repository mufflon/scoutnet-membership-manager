# karverktyg — a Scoutnet kårverktyg

An internal tool for a Swedish scoutkår (default demo: **Scoutkåren Finn**, Lund).
It reads member data from Scoutnet, surfaces what leaders need to act on each term
— composition, unpaid dues, waiting list, förtroendeuppdrag, data-quality findings
— and can apply the yearly **uppflyttning** (moving each cohort up an åldersgrupp)
through a carefully controlled write path.

It is a Python library + a Flask HTTP service + a small static frontend,
deployable to Kubernetes. Everything is aggregate/operational — it never stores
personal data (see `CLAUDE.md` §9).

## Credits — the Scoutnet API

This tool talks to the Scoutnet HTTP API, documented by **Scouterna's official
OpenAPI specification**. We vendor a read-only copy (never auto-updated; a daily
spec-drift job flags upstream changes) under `vendor/openapi/`:

- **Source:** <https://github.com/Scouterna/scoutnet-api>
- **Version:** 0.4.1 — npm `@scouterna/scoutnet-openapi@0.4.1`, retrieved 2026-08-03
  (see `vendor/openapi/meta.json` for the exact commit and integrity hash)

Huge thanks to the Scoutnet developers at Scouterna: this tool only exists because
they publish an open, documented API. If you build on this, please keep the
attribution and go say hello to that project.

## Try it in 60 seconds (no API key)

Fixture mode runs the whole app against a **completely fabricated** demo
memberlist — no credentials, no database, no network. Requires Python 3.14 and
[uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run karverktyg serve --mode fixture --port 8000
# open http://localhost:8000
```

The demo data in `fixtures/memberlist.demo.json` is invented from scratch by
`scripts/make_fixture.py` — no real member ever appears in this repo.

Run the tests (offline, no network):

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

## Setting it up for your kår

Three things to prepare: a **config** (which avdelningar you have), your **API
keys**, and where you **deploy**.

### 1. Make your config

Age brackets and avdelningar are configuration, not code. Build yours interactively
— it validates as it goes and writes a JSON file:

```bash
python3 scripts/make_config.py            # asks where to save
```

Point the app at it with `SCOUTNET_CONFIG_PATH=config/yourkår.json`. The bundled
`config/karverktyg.default.json` is the demo kår and the default if you set nothing.

### 2. Get your API keys

Keys are **per endpoint, per body** (not per user), permanent until regenerated.

1. In Scoutnet, enable **Din kår → Webbkoppling**.
2. Generate a key for each endpoint you need (`group/memberlist`,
   `organisation/group`, and `update/membership` if you will write).
3. The Basic-auth username is the **internal entity id** ("Kår-ID för webbtjänster")
   — not necessarily the visible kår number.
4. Put the keys in `karverktyg.conf` (copy `karverktyg.conf.example`). **Never
   commit it** — `*.conf` is gitignored; only `*.conf.example` is tracked.

### 3. Deploy

The tool runs on Kubernetes (developed against a local k3s / Rancher Desktop).
`scripts/k8s-up.sh` reads your `karverktyg.conf`, builds the image, and rolls out:

```bash
./scripts/k8s-up.sh                       # uses ./karverktyg.conf
kubectl -n karverktyg port-forward svc/karverktyg 8000:80   # then open :8000
```

The service is a ClusterIP — put human authentication at the ingress
(`k8s/ingress.example.yaml`). `scripts/k8s-down.sh` tears it back down.

## Modes

Set with `SCOUTNET_MODE` (or `--mode`). The mode is enforced at client
construction, not just in the UI.

| Mode | Reads | Writes | Data source |
|---|---|---|---|
| `fixture` | yes | no | Committed demo fixture. No network, no credentials. |
| `read_only` (default) | yes | **no** | Live Scoutnet |
| `read_write` | yes | yes | Live Scoutnet — the controlled write path |

`fixture` and `read_only` clients have **no** write method at all; the single
`update_membership` method exists only on the `read_write` client, returned only
when a write key is set. `read_write` must be chosen deliberately and shows a
banner in the UI while active. The write path (uppflyttning apply) is dry-run by
default, one member per request, with snapshot + journal + reconcile, and is fully
undoable (`CLAUDE.md` §6, §8; `docs/runbook.md`).

## What you can do

- **Översikt** — active member count, composition per åldersgrupp (with leaders and
  scouts-per-leader), and next-year projection. Aggregate-only Excel/PDF export.
- **Medlemsavgifter** — unpaid dues for the invoiced term, per avdelning, as a
  single-sheet export. (The current term is empty until it is invoiced.)
- **Väntelista** — waiting list / awaiting approval, plus copy-paste
  membership-request email drafts. Nothing is sent — you copy the text yourself.
- **Förtroendeuppdrag** — the register of group-scoped roles, split into styrelse,
  övriga uppdrag, and ombud.
- **Anmärkningar** — data-quality and membership-roll findings (advisory only),
  including scouts with no avdelning and minors sitting in the Ledare avdelning.
- **Uppflyttning** — the computed master set (who moves where at the summer shift),
  one övergång at a time, with per-member routing and a downloadable Excel
  changelist.
- **Utför uppflyttning** *(`read_write` only)* — apply the reviewed övergång:
  dry-run drift report, confirm-to-execute, live progress, and undo.
- **API-koll / Verifiera skrivning** — per-key live probes and manual write
  verification.

Out of scope with the documented API: attendance tracking, and creating next
year's arrangemang (see `docs/phase-0-findings.md`).

## Configuration reference

All settings are environment-driven (`pydantic-settings`), prefix `SCOUTNET_`
(see `.env.example`); `scripts/k8s-up.sh` maps `karverktyg.conf` onto them.

| Variable | Purpose |
|---|---|
| `SCOUTNET_MODE` | `fixture` \| `read_only` (default) \| `read_write` |
| `SCOUTNET_CONFIG_PATH` | path to your kår config JSON (default: the bundled demo) |
| `SCOUTNET_ENTITY_ID` | HTTP Basic username — the internal entity id |
| `SCOUTNET_MEMBERLIST_KEY` | per-endpoint key for `/group/memberlist` |
| `SCOUTNET_ORGANISATION_GROUP_KEY` | per-endpoint key for `/organisation/group` |
| `SCOUTNET_UPDATE_MEMBERSHIP_KEY` | per-endpoint write key (required for `read_write`) |
| `SCOUTNET_WRITE_ALLOWLIST` | member numbers the write-verify test may touch |
| `SCOUTNET_SNAPSHOT_DIR` | mounted-volume path for pre-run snapshots (`read_write`) |
| `SCOUTNET_CHUNK_SIZE` / `SCOUTNET_CHUNK_DELAY_S` | write chunk size (**default 1**) and delay |
| `SCOUTNET_SNAPSHOT_RETENTION_DAYS` | snapshot retention window (default 30; gates undo) |
| `SCOUTNET_DATABASE_URL` | Postgres DSN (fixture mode uses in-memory SQLite) |
| `SCOUTNET_COHORT_YEAR` | uppflyttning year N; unset = derive from the live term (guarded) |
| `SCOUTNET_KAR_NAME` | kår display name |

## Generating test data

- **`scripts/make_fixture.py`** — fabricate a complete demo memberlist from
  nothing (no capture, no key). This is what ships in `fixtures/`.
- **`scripts/make_config.py`** — build a kår config interactively.
- **`scripts/capture_memberlist.py`** + **`scripts/scrub_capture.py --scramble`** —
  for a kår that wants realistic test data from their *own* live capture: capture,
  then fake every personal field and obscure the per-avdelning head-counts (via
  `scripts/scramble_composition.py`) before anything is written to disk you commit.

## Layout

```
src/karverktyg/
  settings.py            app settings (pydantic-settings)
  collation.py i18n.py   Swedish collation and UI strings
  config/                bracket + avdelning config models and loader
  scoutnet/              API client (fixture + read-only + write) and parser
  roster.py              troop-id index (from unit.raw_value)
  findings/              data-quality + membership-roll findings
  uppflyttning/          cohort-year guard + master-set engine
  fortroende.py          förtroendeuppdrag register
  oversikt.py export/    composition/projection + Excel/PDF exports
  write/                 write path: executor, snapshots, undo
  membership/ mail/      membership-request drafts + mail interface
  db/                    SQLAlchemy models (no personal-data columns)
  web/                   Flask app, JSON API, static frontend
  jobs/                  read-only canary + spec-drift
scripts/                 config/fixture generators + capture/scrub spikes
config/ fixtures/ migrations/ k8s/ vendor/ docs/
```

## Standing limits

- Before a real bulk uppflyttning write, verify `troop_id` against the live
  `update/membership` endpoint on a single placeholder record (`docs/runbook.md`).
- The Äventyrare→Utmanare övergång stays *pending* until the operator supplies the
  new Utmanare avdelning's id.
- The applicant-approval write workflow is not built — it depends on the
  `awaiting_approval` variant, which currently read-times-out for this kår.
- PDF export needs the `[pdf]` extra (WeasyPrint + native pango/cairo); the
  deployed container installs it.

## License

MIT — see [`LICENSE`](LICENSE). Use it, fork it, adapt it for your kår.
