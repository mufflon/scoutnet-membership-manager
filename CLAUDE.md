# Scoutnet kårverktyg — repo instructions

Standing instructions for any agent working in this repo. Read this before
touching anything. If a request conflicts with **Hard rules**, stop and ask
rather than proceeding.

---

## 1. What this is

An internal tool for a Swedish scoutkår (default: Scoutkåren Finn, Lund) that
reads member data from Scoutnet, surfaces what leaders need to act on each
term, and — in later phases — writes a small number of carefully controlled
changes back.

Shipped as a Python library plus a Flask HTTP service and a static frontend,
deployed to Kubernetes.

## 2. Language and terminology

Code, comments, commits, docstrings and documentation in **English**.
User-facing UI strings in **Swedish**, kept in a single translation module.

Locale is **sv_SE**, timezone **Europe/Stockholm**. All name lists and any
other user-visible sorting use Swedish collation — å, ä and ö sort after z,
not as variants of a and o. Sort in Postgres with an explicit `sv-SE-x-icu`
collation, or in Python via `PyICU`; never rely on default byte ordering.

Scoutnet uses English names for Swedish concepts. Use the API's vocabulary in
code and never invent a synonym:

| Swedish | Scoutnet / API | Notes |
|---|---|---|
| kår | `group` | The whole local organisation |
| avdelning | `troop` — `unit`, `unit_type`, `troop_id` | The section a scout belongs to |
| patrull | `patrol` — `patrol_id` | |
| gren | *(not exposed)* | Scoutnet does not publish which gren an avdelning belongs to |
| arrangemang | `project` | Also how Scoutnet models meeting attendance |
| termin | `term` — `term_id`, `term_label` | Use Scoutnet's own term values |
| medlemsnummer | `member_no` | The stable unique identifier. Key everything on this |

Reproduce this table in the README and in the app's glossary.

## 3. Tech stack

Versions verified on PyPI 2026-08-02. **Re-verify before pinning**; do not
silently use something older if newer exists.

- Python 3.14 (3.14.6); fall back to 3.13 only if a dependency blocks
- `uv` for dependencies and virtualenvs
- Flask 3.1.3, gunicorn 26.0.0
- httpx 0.28.1, tenacity 9.1.4
- pydantic 2.13.4, pydantic-settings 2.14.2 — all config through settings objects
- SQLAlchemy 2.0.51, alembic 1.18.5, psycopg 3.3.4
- google-api-python-client 2.198.0, google-auth 2.56.2
- phonenumbers 9.0.36, email-validator 2.3.0
- openpyxl 3.1.5 (Excel export), WeasyPrint 69.0 + Jinja2 3.1.6 (PDF export)
- pytest 9.1.1, ruff 0.16.1 (lint + format, strict; repo must stay clean)

Frontend is plain static HTML/JS/CSS, no build step unless one becomes
necessary. It talks **only** to the Flask API — never to Scoutnet, Postgres or
Google.

## 4. The Scoutnet API

### Getting the definition

Source of truth: <https://github.com/Scouterna/scoutnet-api>, OpenAPI 3.1 at
`packages/scoutnet-openapi/schema/scoutnet.yaml`. Version at time of writing:
**0.4.1**, matching the `@scouterna/scoutnet-openapi` npm package.

It ships as **multiple files with relative `$ref`s**. Bundle it:

```bash
npx @redocly/cli bundle schema/scoutnet.yaml -o bundled.yaml
```

**Do not generate a client from it.** Generation fails on known defects, and
our surface is small enough to hand-write. Known bugs in 0.4.1, all worth
reporting upstream:

- `group_troop.meeting_info`, `group_section.address_ids`,
  `project_stats.questions` declare `type: {}`, which is invalid
- `project_member.primary_membership_info` is `type: array` but carries
  `properties`, dropping the whole model
- `region.yaml` has a `conties` typo, described as country instead of county
- Key generation is undocumented

Vendor the bundled spec into `vendor/openapi/` with a sidecar JSON recording
upstream version, git commit hash and retrieval date. The capabilities page
displays all three.

### Authentication

HTTP Basic. Username is the body's **internal entity ID**, password is the API
key.

- **Keys are per endpoint, not per user.** Each endpoint on each body has its
  own key, valid nowhere else. Permanent until regenerated.
- **The entity ID may not equal the visible kår number.** Find it in the
  group's home page URL or the example endpoint URLs on the Webbkoppling page.

Keys are generated under **Din kår → Webbkoppling**, which must be enabled
first. **The available endpoint list is set by a system administrator and
varies** — what the spec documents is not necessarily what a kår is offered.
Confirm on the Webbkoppling page before relying on an endpoint.

Servers: `https://scoutnet.se/api` (production),
`https://s1.test.custard.no/api` (test; credentials are not self-service).

### Endpoint surface

**Group-scoped:** `GET /group/memberlist`, `GET /organisation/group`,
`POST /organisation/register/member`, `POST /organisation/update/membership`

**Project-scoped, one key per arrangemang:** `GET /project/get/participants`,
`GET /project/get/groups`, `GET /project/get/questions`, `POST /project/checkin`

**Unavailable:** `GET /body_key_list`, restricted to internally developed systems.

### Documented failure modes

The spec defines only **200, 400 and 401**. There is no 429, no 5xx, no
pagination and no documented size or rate limit anywhere. Treat all limits as
**unknown rather than absent** — see §8.

### `GET /group/memberlist`

Optional params, value `1`: `waiting`, `awaiting_approval`. Each returns those
members **instead of** active ones, so they are separate calls.

```
{
  "data":   { "<member_no>": { "<field>": { "value": ..., "raw_value": "..." } } },
  "labels": { "<field>": "<Swedish column label>" }
}
```

Every field is wrapped in `{value, raw_value}`. Documented fields:

`member_no`, `first_name`, `last_name`, `ssno`, `date_of_birth`, `status`,
`created_at`, `confirmed_at`, `group`, `unit`, `unit_type`, `sex`, `address_1`,
`postcode`, `town`, `country`, `email`, `prev_term`, `current_term`,
`current_term_due_date`, `kid`, `roles`, `waiting_since`, `awaiting_approval`

**Additional fields are permitted and expected.** Guardian/anhörig contacts are
undocumented but appear in practice; other Scouterna projects reference
`contact_telephone_home` and note Scoutnet has both "Telefon hem" and
"Hemtelefon". Never drop unknown fields — carry them in a passthrough mapping.

`unit` is the avdelning **name**; there is no documented `troop_id`.

### `GET /organisation/group`

Aggregate only: `membercount`, `rolecount`, `waitingcount`, and `stats` with
`active`, `active_paid`, `active_paid_previous` (each carrying `term_id` /
`term_label`), `below_26`, `active_troops`, `generated`. Breakdown is by age
group and sex, **not** by avdelning.

`term_id` / `term_label` are the canonical term identity across the app. Fall
back to a local calendar rule only if live data proves unusable.

### `POST /organisation/update/membership`

```
{ "<member_no>": { "status": "confirmed|waiting|cancelled",
                   "troop_id": <int>, "patrol_id": <int> } }
```

Batch, keyed by member number. `status` is **required on every entry**.
Documented as atomic: any error rejects the entire request. On 400 the response
is keyed by member number with per-member error strings.

## 5. Feasibility — read before proposing features

**Feasible now, read-only:**
- Unpaid dues per avdelning (field semantics must be confirmed against real data)
- Applications awaiting approval, and the waiting list
- Uppflyttning candidates (age from `date_of_birth`, brackets from config)
- Next-year membership projection
- Membership-roll findings and data quality checks (§11)
- Leader identification and exclusion from moves (depends on `roles`)
- Cross-check of computed paid totals against `/organisation/group`

**Feasible but blocked on troop_id resolution:**
- Accepting an applicant and allocating an avdelning
- Executing an uppflyttning

The write endpoint needs an integer `troop_id`; the memberlist returns only the
avdelning **name**. Troop IDs are map keys on the group model's `troops`
object, reachable only via project-scoped `/project/get/groups`. Resolve via an
undocumented field in the real response, a config mapping read off Scoutnet
admin URLs, or one project key. **No write code until this is resolved and
documented.**

**Not feasible with the documented API:**
- Cross-checking members against reported activities
- "Who has missed recent meetings / is becoming less active"
- Per-avdelning activity statistics
- Creating next year's activities from Excel — no create-arrangemang endpoint exists
- Listing configured meetings

Scoutnet models attendance as *arrangemang*, one per meeting, repeated weekly
until end of term, behind project-scoped keys. Anything attendance-dependent is
out of scope pending the Phase 0 spike.

## 6. Operating modes and hard rules

### Operating modes

A single deployment-level setting, `SCOUTNET_MODE`, decides what this instance
can do. It is enforced **at client construction**, not at each call site — in
the wrong mode the write methods do not exist on the object, so a bug cannot
reach them.

| Mode | Reads | Writes | Data source |
|---|---|---|---|
| `fixture` | yes | no | Committed fixtures and the mock server. No network. |
| `read_only` | yes | **no** | Live Scoutnet |
| `read_write` | yes | yes | Live Scoutnet |

`read_only` is the default. `read_write` must be set deliberately and is
displayed prominently in the UI whenever active.

`fixture` mode exists so the full Flask app can be run and demonstrated with no
credentials at all — useful for frontend work, for the other two leaders to try
it, and for CI. It must be indistinguishable from `read_only` to the frontend,
which never learns which mode is in effect beyond what the capabilities page
reports.

A test asserts that write methods are absent in `fixture` and `read_only`.

### Hard rules

1. **No API keys in the repo, ever** — not in code, tests, fixtures, manifests
   or image layers. Environment variables only. Fail loudly at startup when a
   key is missing.
2. **No real member data in the repo or git history.** Fixtures scrubbed or
   synthetic. The one sanctioned exception is snapshots (§8), which live on a
   mounted volume and never in git or an image.
3. **`cancelled` is banned from the codebase.** It is a valid enum value that
   would cancel memberships. Unreachable, with a test asserting so.
4. **Dry-run is the default** on every write path. Executing requires explicit
   confirmation.
5. **No concurrent writes.** Chunks are sent one at a time, never in parallel.
6. **Never rename a file to a dot-prefix to hide or soft-delete it.** Delete it.
7. No new dependencies without stating why.

## 7. Phasing

Strictly in order.

### Phase 0 — spikes, before any application code

Findings and two throwaway scripts. No implementation.

- **Fixture capture.** One live memberlist call, raw JSON to a gitignored
  directory, printing **only key names and counts, never values**. The operator
  runs it. Then a scrubber producing a committable fixture. Everything
  downstream develops against the fixture; the test suite never touches the
  network.

  Determine: what `current_term`, `prev_term` and `current_term_due_date`
  contain and how paid differs from unpaid; guardian field names; `unit_type`
  and `roles` values; whether any troop ID appears; **whether a member can
  appear more than once, or hold more than one avdelning membership** — leaders
  routinely belong to several, so confirm how the response represents that.
- **troop_id resolution.** Options with a recommendation.
- **Arrangemang / attendance spike.** How many keys would a term of weekly
  meetings need? Is programmatic creation possible at all? Written options and
  a recommendation. No code.

### Phase 1 — read-only

Library, Flask API, frontend, Docker, Kubernetes scaffolding, all read-only
views. No write code in the repo at this stage.

Phase 1 must end somewhere useful on its own, not merely at "we can see the
problem but cannot act on it". Two deliverables make that true:

**Changelist export.** The computed uppflyttning master set, after review and
per-member overrides, exported as an **Excel workbook** (openpyxl) for manual
execution in the Scoutnet UI. This is a permanent first-class output, not a
stopgap for the first year — once writes exist, "export the changelist" and
"execute the changelist" are two buttons over the same reviewed set, never two
code paths.

Design it for the person doing the data entry:

- One sheet per target avdelning, ordered so the operator works through one
  destination at a time without jumping around the UI. Swedish collation
  within each sheet.
- `member_no` in the first column — it is the search key in Scoutnet — with
  name alongside for confirmation, then source and target avdelning.
- A "done" column and freeze panes, because a hundred manual edits happens
  across more than one sitting and the operator needs to record where they
  stopped.
- A cover sheet with generation timestamp, term, total counts per avdelning,
  and the configuration version the set was computed from.

**Post-hoc reconciliation.** After manual execution, re-fetch the memberlist
and diff it against the changelist: how many applied, which members were not
found, which ended up somewhere other than intended. Pure read, available
immediately, and it catches exactly the transcription errors manual entry
produces. The same reconciliation code is reused by Phase 2.

### Reports

All reports export to **PDF**, rendered from Jinja2 templates via WeasyPrint so
the print output and the on-screen view share one source.

- **A4**, never US Letter.
- **One avdelning per page**, with a hard page break between them, so a subset
  can be selected and printed later.
- Page header carrying kår, avdelning, term and generation timestamp; page
  numbers as "x of y".
- Swedish collation for every name list.
- Print stylesheet only — no separate report-rendering path to drift out of
  sync with the screen.

Excel export is offered alongside PDF wherever the content is genuinely
tabular and someone might want to sort or filter it.

### Phase 2 — writes

Only after Phase 1 runs and Phase 0's blockers are closed.

## 8. Write execution (Phase 2)

### Chunked atomic batches

The endpoint is atomic and batch-capable, and we use it that way. Serial
per-member writes would be the design that leaves the kår half-moved when a pod
dies mid-run; an atomic batch that fails changes nothing.

- **Chunk size is configurable**, default small (start at 25). Chunks are sent
  **one at a time, serially**, with a configurable minimum delay between them.
- No documented limit on batch size or request rate exists. Treat this as
  unknown. Small chunks are how we stay clear of undiscovered limits.
- **Verify atomicity empirically before trusting it.** Send a two-member chunk
  where one entry is deliberately invalid, then confirm the valid one did *not*
  apply. If Scoutnet does not honour its own atomicity claim, fall back to
  one member per request and record that finding here.
- **Re-read before write.** `status` is mandatory, so fetch current status
  immediately beforehand and echo it back unchanged. Only `troop_id` changes
  during an uppflyttning.

### Error handling

Any non-200 — 400, 401, 5xx, timeout, connection error, malformed body — marks
that chunk **failed** and stops the run. Do not retry automatically; do not
continue to the next chunk.

Surface to the user, on screen, everything needed to understand it: HTTP status,
the member numbers in the chunk, the intended change per member, any per-member
error strings from a 400 body, the response body, and elapsed time. Log the
same, with credentials redacted. The user then chooses to resume from the
failed chunk or abort.

### Snapshots

Before the first request of any bulk run, fetch and write a **full memberlist
snapshot** to a mounted volume. This is the recovery path if a run damages the
register.

Snapshots contain complete personal data including personal numbers. They are
the one place that rule is relaxed, so:

- Volume only. Never in git, never in an image, never in Postgres.
- **Retention is time-based, not count-based.** Keep everything younger than a
  configurable window (default 30 days), and always keep at least the most
  recent regardless of age. Keeping "only the latest" is wrong — it destroys
  the ability to unwind an earlier run once a later one happens.
- Automatic purge on schedule, plus a manual delete in the UI.
- Listed in the app with timestamp, size and the run that produced it.

### Reconciliation

After a run completes, re-fetch the memberlist and compare against intent.
Report either "all changes applied successfully" or an itemised list of every
member whose actual state does not match what was intended.

### Undo a run

Every completed or partially completed run can be reversed. The prior-state
snapshot plus the journal contain everything needed to compute the inverse
operation set, so generate it rather than asking the operator to reconstruct
anything.

- Offered from the run's detail view for as long as its snapshot is retained.
  Once the snapshot is purged, undo is no longer available and the UI says so
  explicitly rather than failing later.
- An undo **is itself a run**: same chunking, same dry-run-first, same
  confirmation, same journal, same snapshot taken beforehand, same
  reconciliation afterwards. It is not a privileged path.
- Compute the inverse from *observed* prior state in the snapshot, never from
  the intended change. If a member's current state already differs from what
  the run set, flag it and exclude it from the undo rather than overwriting
  someone else's later edit.
- Show the operator the full inverse set before executing, including anything
  excluded and why.

### Progress and resumption

- **Journal first.** Persist the full intended operation set before the first
  request. Chunks move pending → in_flight → done | failed.
- Progress is **server-side state**, polled by the frontend. Closing the tab
  must not affect a run.
- After a crash and restart the operator sees where it stopped and chooses to
  resume from the interrupted chunk or abort. Resuming is safe because
  re-applying an already-applied change is a no-op — state that assumption in
  the code, and verify it in testing stage 2.

### Testing progression for writes

In this order, operator approving each step:

1. **Mock Scoutnet server**, generated from the bundled schema rather than
   hand-written, replaying realistic captured read data and validating request
   bodies. Exercise the full run here including crash, resume and failure paths.
2. **One hardcoded member**, agreed in advance, against the real API. Verify by
   hand in the Scoutnet UI. Also verify idempotency by repeating it, and verify
   atomicity with the deliberately-invalid pair described above.
3. **A reviewed list**, displayed in full and approved before execution.

## 9. State (Postgres)

Store the **minimum** to make workflows resumable, and nothing Scoutnet already
holds. Names, addresses, personal numbers, emails and phone numbers are never
written to the database — they are fetched live and joined at render time. A
test fails if a personal-data column appears in a migration; treat it as a
cheap heuristic, not a guarantee.

- Uppflyttning master set: `member_no`, source and target avdelning, per-member
  override, approval state
- Applicant workflow: `member_no`, workflow state, avdelning being tried
- Message log for idempotency: `member_no`, message type, sent timestamp
- Write journal: run ID, chunk ID, `member_no`, intended change, status, attempts
- Finding acknowledgements: see §11

Generated Excel and PDF exports contain names and other personal data. They are
streamed to the browser on request and **never written to disk server-side,
never cached, never stored in Postgres**. Once downloaded they are the
operator's responsibility.

**Purge aggressively.** Once an outcome exists in Scoutnet the local rows lose
their reason to exist: an enrolled member's applicant state and message log are
deleted; a completed run's journal is deleted after a short retention window.
An explicit, tested cleanup step in the workflow — not a background sweep that
might not run.

## 10. Email

Gmail API, service account with domain-wide delegation, scope
`https://www.googleapis.com/auth/gmail.send` only. Sending mailbox is a config
value and must be inside the Workspace domain. No SMTP.

Two `MailSender` implementations: Gmail, and a recording fake used in
development and tests. Nothing in the test suite can send real mail. Templates
are editable configuration. Sending is idempotent — check the message log
before, write to it after.

## 11. Findings (data quality and enforcement)

One model covering two categories, both **advisory only**. The tool never
changes a member to resolve a finding.

**Data quality** — probable formatting problems, computed with `phonenumbers`
(region SE) and `email-validator` with deliverability checks **off**, since
per-member DNS lookups would be slow and unreliable. Postcode and address
heuristics tuned against real data once the capture exists.

**Membership roll enforcement:**
- Anyone 18 or over holding a scout membership in an avdelning, except in
  avdelningar configured as 18+
- Anyone set as a leader in the Ledare avdelning
- **Scouts belonging to more than one avdelning.** Leaders routinely do and are
  excluded; for scouts it is rare and worth flagging.
- **Members with no avdelning at all.** These need manual resolution.

Findings are computed live on every page load and never stored.

**Acknowledgement is the only persisted state, and it is keyed to the value,
not the member.** Store `member_no`, finding type, and a hash of the normalised
offending value. If the value later changes to a different problematic one, the
hash changes and the finding resurfaces — an ack must never permanently blind
the tool to a field. A hash is not personal data, so this stays inside §9.

## 12. Capabilities page

What **this deployment** can do:

- Each configured endpoint, whether a key is present, and a truncated hash of
  the key — never the key
- Which UI actions are consequently enabled; actions without a key render
  **disabled with an explanation**, not hidden
- Vendored OpenAPI version, upstream git hash, retrieval date
- Application version and build number

Permissions are **per deployment**, not per user.

## 13. Configuration

All configuration through pydantic-settings, environment-driven, Kubernetes
Secrets for keys and a ConfigMap for the rest. Notable knobs: chunk size, delay
between chunks, snapshot retention window, allowed avdelningar, kår identity.

- **Kår identity and branding** configurable, defaulting to Scoutkåren Finn.
  Vendor Finn's logo and colours into the repo from scoutkarenfinn.se — never
  fetch at build or run time. Keep them in a swappable directory.
- **Age brackets and uppflyttning flows are configuration, not code.** The kår
  uses school-year cohorts with structurally different transitions
  (same-weekday moves, merges into one avdelning, splits by birth year, and
  brackets that must never be auto-moved). **The concrete rules are not yet
  specified** — design a schema general enough to express those shapes, ship a
  clearly marked placeholder, invent nothing. The active configuration is
  viewable in the app.
- Members holding leader roles are never included in age-based moves.

## 14. Deployment

Single cluster, single deployment, but configuration must vary so different
configs can be tested. No package index and no container registry yet — treat
image distribution as unsolved and keep the build reproducible with
`docker buildx` so a destination can be chosen later.

Frontend and API may share one image or split across two containers in one pod;
pick one, justify briefly, keep it simple.

**Health and readiness probes are required.** Liveness is a cheap local check.
Readiness additionally verifies Postgres connectivity — and must **not** call
Scoutnet, or an upstream outage will cycle pods. Scoutnet reachability belongs
on the capabilities page, not in a probe.

Human authentication is handled at the ingress. The app trusts no
client-supplied identity header unless the ingress is documented as stripping
and setting it.

### Scheduled jobs

Both are read-only and must run in `read_only` mode. Neither ever writes to
Scoutnet.

**Spec drift detection.** A command that fetches the upstream repo, re-bundles
the OpenAPI document and diffs it against the vendored copy in
`vendor/openapi/`. Reports the upstream version, git hash and a summary of what
changed — added or removed paths and fields first, since those are what break
us. Upstream uses release-please, so version bumps are meaningful signals.
Runnable manually and as a CronJob. Never auto-updates the vendored copy;
adopting a new spec version is a reviewed change. Surface the result on the
capabilities page so drift is visible without reading logs.

**Read-only canary.** A CronJob, weekly by default and configurable, that
fetches the memberlist and `/organisation/group` and asserts the basics: the
call succeeds, the response parses, expected fields are present, member count
is within a sane range of last time. This is seasonal software — uppflyttning
runs once a year — and the point is to discover breakage in April rather than
on the day two hundred scouts need moving. Failures alert somewhere the
operator will actually see; a stale success is itself a failure, so record the
last successful run and show its age on the capabilities page.

## 15. .gitignore

```gitignore
# Secrets and credentials
.env
.env.*
!.env.example
*.pem
*.key
service-account*.json
credentials*.json

# Live captures, snapshots, unscrubbed data
captures/
snapshots/
*.raw.json
*.local.json

# Python
__pycache__/
*.py[cod]
.venv/
venv/
*.egg-info/
dist/
build/
.pytest_cache/
.ruff_cache/
.coverage
htmlcov/

# Tooling
node_modules/
bundled.yaml
.DS_Store
```

## 16. Definition of done, per phase

- `uv run pytest` passes with no network access
- ruff clean, lint and format
- No secrets and no real member data in git history
- README covers key generation, glossary, configuration and current-phase limits
- Tests exist for: rejection of `cancelled`, absence of write methods in
  `fixture` and `read_only` modes, absence of personal-data columns,
  no-parallel-writes, resume after crash, snapshot written before first request,
  reconciliation reporting, undo excluding externally-changed members, ack
  invalidation when a value changes, and mail senders being inert under test

Additionally, before Phase 2 is considered complete, a **runbook** exists: how
to obtain a key, how to run a bulk operation, what to do when one fails
halfway, how to undo a run, and how to restore from a snapshot. Written for
whichever of the other two leaders would have to run it if the author were
unavailable — this is annual software and nobody will remember the details
eleven months later.
