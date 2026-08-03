# Scoutnet kårverktyg — project specification

Standing instructions and reference for anyone, human or agent, working on this
repo. **Read the preamble before §1.** If a request conflicts with §6 *Hard
rules*, stop and ask rather than proceeding.

This document is the merge of the former `CLAUDE.md` and `HANDOVER.md`. The
Phase 0/1/2 scaffolding has been removed — those phases are complete and were
only meaningful during initial development. Forward-looking work lives in §7
*Roadmap*.

---

## Authority order

1. **The running code and the live Scoutnet API.** Observed behaviour beats
   written intent, always.
2. **This document.** Binding on anything not yet built.
3. Anything else.

If the code and this document disagree, the code is the fact. Say so, and fix
whichever is wrong on purpose rather than silently following one.

**Known failure mode.** During one revision cycle three write-safety decisions
were silently reverted, because the editing session worked from a stale copy.
When revising this file, diff against the current version rather than
re-authoring sections from memory, and treat a disappearing safety constraint as
a merge error rather than a judgement call.

## Current state (2026-08-03)

Built, tested and deployed on local k3s. `uv run pytest` passes offline
(170 tests); ruff clean.

**Read-only surface — complete.** Blades: Översikt, Medlemsavgifter,
Förtroendeuppdrag, Väntelista, Anmärkningar, Uppflyttning, Mallar, API-koll,
Funktioner, plus the Excel changelist export and post-hoc reconciliation. Exports:
förtroendeuppdrag (Excel + A4 PDF), unpaid dues (Excel), Översikt (Excel + A4 PDF,
aggregate-only). PDF rendering is the optional `[pdf]` extra (WeasyPrint), installed
in the deployed image; where it is absent the PDF endpoints return a clear 503
rather than failing.

**Uppflyttning write path — complete.** `read_write` mode gate, serial
one-member-at-a-time executor (dry-run default, pre-flight drift check, journal,
resume), pre-run snapshots, reconciliation, and undo — plus the *Utför
uppflyttning* and *Verifiera skrivning* blades and a `verify-write` CLI.
Exercised end to end against a schema-derived mock, and single-member against
live Scoutnet.

**`troop_id` is verified (2026-08-03).** `unit.raw_value` is the id
`POST /organisation/update/membership` accepts — confirmed by moving one member
Ledare (`10172`) → Hajarna (`10155`) through the tool and undoing it, each step
checked by hand in the Scoutnet UI. This was the last assumption that could
block a real bulk run.

**Not built:** the applicant-approval write workflow, and auto-send email. See §7.
(Phase A — förtroendeuppdrag §18, unpaid-dues export §19, Översikt §20 — is done.)

**Meaningful changes this session (2026-08-03).** Where the implementation now
leads the older §18–§20 prose, the code is the fact (Authority order):

- **Förtroendeuppdrag** splits into three sections — **Kårstyrelse**, **Övriga
  förtroendeuppdrag**, **Ombud och representanter** (one-day delegates last). The
  board/other/delegate classification is **hard-coded by `role_key`** in
  `karverktyg.fortroende` (uniform for this kår; Utmanarscoutrepresentant is a
  board seat, `district_voter` a delegate); config no longer carries the ordering.
- **Unpaid-dues export is a single flat sheet** (operator preference for an expert
  tool), not §19's one-sheet-per-avdelning + cover + review-sheet split.
- **Översikt blade is trimmed**: the per-avdelning leader count and
  scouts-per-leader ratio are merged into the composition table; the Nyckeltal/KPI
  block, the adult/youth leader split, per-åldersgrupp thresholds and the
  current-vs-projected chart were removed from the *blade* (the Excel/PDF export
  still carries the fuller set). The "aggregate-only, may circulate freely" framing
  was removed — operators use their own judgement.
- **Performance (§4 read client).** `organisation/group` (~30 s) and
  `awaiting_approval` (30 s read-timeout) are slow for Finn, so blades render from
  the fast reads and pull the slow cross-checks in **asynchronously**
  (`?aggregate=1` / `?rolecount=1`); `organisation/group` is cached and a
  timed-out variant is negative-cached; gunicorn runs **gthread** workers
  (I/O-bound); the frontend aborts stale reads on navigation. No blade fetches
  everything synchronously any more.
- **`Avdelning.troop_id` removed from config** (config = existence, live = ids,
  operator = election; §17/§20 amended). Manual 5-digit **avdelnings-id** entry
  for the Äventyrare→Utmanare election is implemented with the §17 guards
  (group-id rejected, five-digit shape, unknown-needs-ack). "troop_id" is shown to
  operators as **"avdelnings-id"**.
- **Tooling.** ruff `target-version = py313` (keeps `except (A, B):` canonical and
  the code runnable on the 3.13 fallback); `docker-compose.yml` removed; gunicorn
  worker model and k8s resource requests/limits raised.

## Open actions

**Key handling.**

- [ ] **Keys must not be readable by a coding agent.** `.gitignore` protects git;
      it does nothing about an agent with filesystem access to the deployment
      config. Move the config outside the repo tree, or create the Kubernetes
      Secret out of band so no plaintext key file exists at all. Hard rule 7 is a
      policy; this is the structural version of it.

**Resilience — before any extended absence.**

- [ ] **Get the work off one machine.** Everything lives on a local `phase-2`
      branch with no remote configured and nothing pushed. Merge to `main`,
      configure a private remote, push. Until then the bus factor and the disk
      factor are both one, and neither of the other two leaders can run
      anything.

**Discovery — cheap, and one may unlock a feature.**

- [ ] **Probe the three undocumented endpoints**, one read each, own key each:
      `/organisation/project`, `/group/customlists`, `/group/resources`. None
      appears in the OpenAPI document, so the drift-check cannot see them.
      Capture discipline applies: raw response to a gitignored directory, key
      names and counts only in anything shared. `/organisation/project` may
      invalidate the attendance conclusion in §5.
- [ ] **Characterise the `awaiting_approval` read timeout** — intermittent,
      size-related, or permanent? This gates the applicant workflow (§7).

**Seasonal.**

- [ ] **Re-capture after Höst 2026 is invoiced.** Payment logic is validated
      against Vår 2026 only; `current_term_due_date` and `kid` parsing is
      unexercised and new payment-status codes are likely to appear. Until then
      an unrecognised code must land in the review bucket, never in settled or
      outstanding.

## Deployment and version control

Local k3s, namespace `karverktyg`, built by `scripts/k8s-up.sh` from a config
file of API keys. Mode and the write allowlist are deployment config only, never
entered in the UI (hard rule 7). During write testing the allowlist is bounded to
a single record and the snapshot volume is PVC-backed.

All write work is on the local branch `phase-2`, branched from the read-only tip
that `main` points at. Nothing is pushed; there is no remote. See *Open actions*.

## Reference documents

- `docs/runbook.md` — how to run, resume, undo and restore. Written for whichever
  leader has to do it if the author is unavailable. This is annual software.

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
| åldersgrupp (colloquially *gren*) | `unit_type` | Spårare, Upptäckare, Äventyrare, Utmanare, Rover, Annat. Scoutnet's own term is åldersgrupp; it does not expose a separate gren field, but `unit_type` is the same concept |
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

**What Finn actually has access to**, read off the Webbkoppling page 2026-08-03.
This is the authoritative list; the OpenAPI document is neither a subset nor a
superset of it:

| Endpoint | In OpenAPI 0.4.1? | Status |
|---|---|---|
| `GET /group/memberlist` | yes | in use |
| `GET /organisation/group` | yes | in use |
| `POST /organisation/update/membership` | yes | **in use** — the write path |
| `POST /organisation/register/member` | yes | available, not used |
| `GET /group/resources` | **no** | undocumented, unexplored |
| `GET /group/customlists` | **no** | undocumented, unexplored |
| `GET /organisation/project` | **no** | undocumented, unexplored |

**Not available to Finn:** `GET /body_key_list` (restricted to internally
developed systems, as expected) and the entire project-scoped family the spec
documents — `/project/get/participants`, `/project/get/groups`,
`/project/get/questions`, `/project/checkin`.

Two consequences.

**The write endpoints are confirmed available.** The open question of whether
this kår is even offered `update/membership` is closed, and the endpoint is in
production use.

**The vendored spec is incomplete, and the drift-check cannot detect that.**
Three live endpoints appear nowhere in the OpenAPI document, so upstream being
"in sync" says nothing about them. The Webbkoppling page — not the spec — is the
source of truth for what exists. Re-read it when anything surprising happens.

### The three undocumented endpoints

Unexplored as of 2026-08-03. Each needs its own key. **Probe all three with a
single read before scoping any further work**, following the capture discipline: raw response to a gitignored directory, key names and counts only in
anything committed or reported.

- **`/organisation/project`** — the important one. §5 concludes attendance is
  infeasible partly because "there is no group-level list of a kår's projects".
  A group-scoped project endpoint is precisely that, so **that premise may be
  wrong.** Treat the attendance conclusion as provisional until this is read.
  Note that even a list of arrangemang does not by itself give attendance:
  `/project/get/participants` is *not* available to Finn, so reading who attended
  may still be blocked — but the blocker would be a different and more precise
  one than the key-count argument currently given.
- **`/group/customlists`** — driven by e-postlistor defined in Scoutnet, where
  the columns are chosen in the UI. Potentially a narrower, faster data source
  than the 49-field memberlist, which would suit the minimal-personal-data
  posture. Also worth testing as a workaround for the `awaiting_approval`
  timeout.
- **`/group/resources`** — purpose unknown; possibly kår resources such as
  facilities or equipment. Speculation until read.

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

Documented fields:

`member_no`, `first_name`, `last_name`, `ssno`, `date_of_birth`, `status`,
`created_at`, `confirmed_at`, `group`, `unit`, `unit_type`, `sex`, `address_1`,
`postcode`, `town`, `country`, `email`, `prev_term`, `current_term`,
`current_term_due_date`, `kid`, `roles`, `waiting_since`, `awaiting_approval`

Many more undocumented fields appear in practice — 49 in the 2026-08-02 capture.
Never drop unknown fields; carry them in a passthrough mapping.

Everything below this line is **observed** from that capture rather than
inferred from the spec. It supersedes anything the OpenAPI document implies.

#### value vs raw_value

Fields are wrapped as `{value}` or `{value, raw_value}`. `raw_value` appears on
the **coded** fields — `status`, `group`, `unit`, `unit_type`, `unit_role`,
`group_role`, `patrol`, `sex`, `current_term`, `prev_term` — and is absent
elsewhere. **Always key logic on `raw_value` and other machine tokens.** The
`value` and `labels` strings are Swedish display text and may change.

#### Terms and payment

The layout is counter-intuitive and easy to get wrong:

- **The term name is in the `label`, not the value.** `current_term` has label
  `"Höst 2026"`, `prev_term` has label `"Vår 2026"`.
- **The field value is the payment status for that term**, as `raw_value`.

Observed codes: `paid`, `paid_partial_credit`, `not_invoiced`,
`unpaid_overdue_reminded`. The enum is **certainly larger** — the existence of
`unpaid_overdue_reminded` implies at least one earlier un-reminded state that
simply wasn't present at capture time.

Classify into three buckets, never two:

| Bucket | Codes | Meaning |
|---|---|---|
| Not billed | `not_invoiced` | No invoice exists. **Excluded entirely — not a finding.** |
| Outstanding | `unpaid_overdue_reminded`, `paid_partial_credit`, … | Needs attention |
| Settled | `paid` | Done |

`paid_partial_credit` means **the member paid an incorrect amount**. It is not
settled and must appear in the outstanding list, distinguished from a plain
non-payment since the remedy differs.

Use an **explicit allowlist** per bucket. Any unrecognised code goes to a
visible "unknown payment status — needs review" bucket, never silently into
settled or outstanding. Treating a new code as settled loses the kår money;
treating it as outstanding chases families who have paid.

`current_term_due_date` and `kid` were empty for everyone at capture because
Höst 2026 had not been invoiced. They are not unused fields. `prev_term_due_date`
can render as `"2026-04-30 (2026-02-28)"` — the current due date with the
original in parentheses after a reminder shifted it. Parse deliberately and
**retain both dates**; it is not a plain date field.

The memberlist gives payment-status-per-term but no `term_id`. For canonical
term identity use `/organisation/group`.

#### unit, unit_type and troop_id

- `unit.value` is the avdelning name; **`unit.raw_value` is the numeric
  troop_id** (5 digits). 14 distinct avdelningar including `Ledare`.
- The same id space appears again as the keys of `roles.value.troop`, agreeing
  field-for-field. Two independent corroborations in one response.
- `unit_type` codes: `Spårarscouter` 2, `Upptäckarscouter` 3,
  `Äventyrarscouter` 4, `Utmanarscouter` 5, `Roverscouter` 6, `Annat` 7. The
  `Ledare` avdelning carries `Annat`.
- Members with no `unit` exist in live data.

#### roles

`roles.value` is `[]` for plain members and an **object** for role-holders —
a PHP empty-associative-array quirk. **Code must accept both `list` and `dict`**
or it will silently identify zero leaders. Add a test for the empty case.

```
roles.value = {
  "troop": { "<troop_id>": { "<role_id>": {role_id, role_key, role_name} } },
  "group": { "<group_id>": { "<role_id>": {role_id, role_key, role_name} } }
}
```

Match on **`role_key`** — `leader`, `other_leader`, `assistant_leader`,
`member_registrar`, … — never `role_name`.

`group_role` and `unit_role` are derived flat views: comma-joined role names in
`value`, comma-joined role ids in `raw_value`. `roles` is the source of truth;
treat those two as convenience columns only.

#### Guardian and contact fields

Scoutnet uses a **dad/mum split**:

- `contact_fathers_name`, `contact_mothers_name`
- `contact_email_dad`, `contact_email_mum`
- `contact_mobile_dad`, `contact_mobile_mum`
- `contact_telephone_dad`, `contact_telephone_mum`

Member's own: `contact_mobile_phone`, `contact_home_phone` (**not**
`contact_telephone_home`), `contact_work_phone`, `contact_email`,
`contact_alt_email`, `contact_scouterna-email`.

Coverage is uneven between mum and dad fields. That is data-quality territory
(§11), not an error.

#### status

Observed only as `Aktiv`, `raw_value` `"2"`. Note the **vocabulary mismatch**:
the write endpoint expects the strings `confirmed|waiting|cancelled`, while the
memberlist returns numeric codes. Only `{"2": "confirmed"}` is known, which is
sufficient for uppflyttning (every mover is active) but **not** for approving an
applicant, whose current status is by definition not active. Completing the map
requires the `waiting` and `awaiting_approval` captures. An unmapped status must
raise, never default to `confirmed`.

#### extra_info_* — do not read

`extra_info_*` are the kår's own custom questions and may contain dietary,
medical or consent answers, i.e. **special-category personal data under GDPR
Article 9**, which is a different legal regime from the rest of the register.

They are **not relevant to any use case here**. Exclude them from the model
entirely: not parsed, not stored, not displayed, not exported. Drop them at the
client boundary so they cannot leak into a snapshot or an export by accident,
and add a test asserting no `extra_info_` key survives.

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

### Read client behaviour

How the read client calls the API, learned from live use (§6 modes still apply):

- **Retry only connection failures.** A read timeout means Scoutnet accepted the
  request but is slow to answer — retrying only multiplies the wait. Retry
  `ConnectError` / `ConnectTimeout` a few times with a short fixed wait; let read
  timeouts fail fast.
- **Short in-process memberlist cache (~90 s).** The active / waiting /
  awaiting_approval lists are cached per variant so navigating between blades
  does not re-fetch a multi-second list each time. This is read-only data that
  changes slowly; the operator reloads for fresh data.
- **Per-variant fail-soft.** `waiting` and `awaiting_approval` are separate calls
  and one can stall while the other is fine (observed: `awaiting_approval`
  reliably read-times-out for this kår while `waiting` returns quickly). A
  variant that errors or times out must degrade to an inline "unavailable"
  notice and load **independently** — it must never block or 500 the whole blade.
- **Consequence for Phase B (§7).** The applicant approval workflow reads *from*
  `awaiting_approval`, so on current evidence it cannot be built on a variant
  that reliably times out. Establish whether the timeout is intermittent, a
  payload-size problem, or permanent **before** scoping that slice. Uppflyttning
  is unaffected: it reads the active variant, and every mover is active, so the
  status echoed back is `confirmed`.

## 5. Feasibility — read before proposing features

**Feasible now, read-only:**
- Unpaid dues per avdelning (field semantics must be confirmed against real data)
- Applications awaiting approval, and the waiting list
- Membership-request email drafts (recipients + text) for the waiting list /
  awaiting approval — copy-paste, no sending (§10)
- Uppflyttning candidates (age from `date_of_birth`, brackets from config)
- Next-year membership projection
- Membership-roll findings and data quality checks (§11)
- Leader identification and exclusion from moves (depends on `roles`)
- Cross-check of computed paid totals against `/organisation/group`

**Feasible, pending one empirical check:**
- Accepting an applicant and allocating an avdelning
- Executing an uppflyttning

troop_id is **resolved**: `unit.raw_value` carries it, corroborated by the keys
of `roles.value.troop`. Build the avdelning-name → troop_id map from a single
memberlist call; no project key is needed. The remaining risk was that
`unit.raw_value` might not be the same id the write endpoint expects.

**Verified 2026-08-03 (stage 2 complete).** `unit.raw_value` *is* the id
`POST /organisation/update/membership` accepts: member 3020341 was moved from
Ledare (`10172`) to Hajarna (`10155`) through the tool and then undone, each step
confirmed by hand in the Scoutnet UI. This was the only assumption that could
block a real run, and it no longer can.

**Not feasible — but this conclusion is now provisional:**
- Cross-checking members against reported activities
- "Who has missed recent meetings / is becoming less active"
- Per-avdelning activity statistics
- Creating next year's activities from Excel — no create-arrangemang endpoint
  appears in the OpenAPI document
- Listing configured meetings

The reasoning was: Scoutnet models attendance as *arrangemang*, one per meeting,
each behind its own project-scoped key — roughly 15 meetings × 13 scout
avdelningar ≈ **195 arrangemang per term** for Finn, each key provisioned by hand
— and there is no group-level list of a kår's projects.

**That last premise may be wrong.** `/organisation/project` is available to Finn
and is not in the OpenAPI document at all (§4). A group-scoped project endpoint
is exactly the thing whose absence the argument rests on. Read it before
treating any of the above as settled.

Two things do not change either way. `/project/get/participants` is **not**
available to Finn, so reading who actually attended may still be blocked. And
nothing in the documented or observed surface creates arrangemang, so the Excel
import still has no destination.

**Standing decision (2026-08-02, unchanged): attendance is out of scope for now.**
Do not build or key weekly arrangemang, and build nothing project-scoped yet.
Keep a project key as an optional per-deployment capability in §12 and §13 so a
single camp check-in could be added without rework. State the limitation plainly
in the README — and state it as "not available to us today", not as "impossible",
until `/organisation/project` has actually been read.

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
   synthetic. Snapshots (§8) hold no personal data either — only `member_no`
   and placement — so there is no longer any sanctioned personal-data exception;
   snapshot files still live on a mounted volume, never in git or an image.
3. **`cancelled` is banned from the codebase.** It is a valid enum value that
   would cancel memberships. Unreachable, with a test asserting so.
4. **Dry-run is the default** on every write path. Executing requires explicit
   confirmation.
5. **No concurrent writes.** Chunks are sent one at a time, never in parallel.
6. **Never fabricate an identifier for a negative test against production.**
   Member numbers are Scoutnet-wide, so an invented one probably belongs to a
   real person in some kår — possibly one who later joins Finn. Malform the
   payload's *shape* instead, and only against the mock.
7. **Keys are never pasted or read anywhere outside the deployment.** Not into
   chats, AI sessions, issues, tickets, screenshots or logs. If a key is exposed
   anywhere at all, regenerate it in Scoutnet — keys are permanent until
   regenerated, so an exposed key stays live until someone acts.
8. **Never rename a file to a dot-prefix to hide or soft-delete it.** Delete it.
9. No new dependencies without stating why.

## 7. Roadmap

Phases 0–2 are complete and have been removed from this document. What follows is
the forward plan. Work one phase at a time; each ends somewhere useful on its own.

Every phase inherits §6 *Hard rules* and, where it writes, §8 *Write execution*
unchanged. New write features are **intent producers feeding the existing
executor** — do not build a second execution path.

### Phase A — Förtroendeuppdrag blade (done 2026-08-03)

A listing of every kår-level assignment currently held. Read-only, no new key, no
new endpoint, no capture: the data is already fetched and parsed. Full
specification in §18. Built as three sections (see *Current state*).

Lowest-risk phase available, and a good one to take first because it classifies
nothing — it is pure pass-through, so an unfamiliar role appears by itself rather
than being silently dropped.

### Phase B — Membership applicants and email configuration

Two halves that belong together because the first is useless without the second.

**Applicant intake and approval.** The waiting list and awaiting-approval views
exist read-only. This phase adds the workflow: welcome mail, invitation to try a
few meetings, recording which avdelning they are trying, and finally accepting the
membership request with an avdelning allocation. The accept step is a write,
through the existing executor.

**Email configuration and sending.** Currently drafts only. This phase adds real
sending per §10 — Gmail API, service account with domain-wide delegation, send
scope only, configurable sending mailbox — plus editable templates and the
idempotency log.

**Prerequisite, hard.** The approval workflow reads the `awaiting_approval`
variant, which reliably read-times-out for this kår. Characterise that timeout
before scoping this phase (see *Open actions*). If it proves permanent, this phase
needs a different data source — `/group/customlists` is the candidate worth
testing, since its columns are chosen in the Scoutnet UI and the payload may be
small enough to return.

Also note the status-vocabulary gap: only `{"2": "confirmed"}` is known. Approving
an applicant means writing `confirmed` to a member whose current status is *not*
active, so this phase must complete the mapping from real observed codes — never
by guessing. An unmapped status must raise, not default.

### Phase C — Endpoint discovery, and possibly attendance

Depends entirely on what the three undocumented endpoints turn out to be, so it
cannot be scoped until they are read.

If `/organisation/project` provides a group-scoped list of the kår's arrangemang,
the attendance conclusion in §5 needs revisiting. Note that even then,
`/project/get/participants` is **not** available to this kår, so reading who
attended may remain blocked — and nothing anywhere creates arrangemang, so the
Excel-to-Scoutnet activity import still has no destination.

Treat this as a spike producing written options, not a build.

### Deferred architecture work (scoped 2026-08-03)

Forward work agreed after Phase A, in three workstreams. **A is discussed next; B
and C are parked here.**

**A. Uppflyttning multi-target rework — in progress.** A **second Äventyrare
avdelning** exists for the upcoming scout year (permanent, unlike the yearly-new
Utmanare avdelning), which breaks the "only one avdelning in the bracket →
auto-target" assumption.

**Built this session.** A **transition-group selector**: the operator works one
group at a time — Spårare→Upptäckare (`same_weekday`), Upptäckare→Äventyrare
(`merge`), Äventyrare→Utmanare (`new_cohort_avdelning`), or **Felplacerade**
(`misplaced`). `scope_master_set` narrows the master set by group, and the
selection scopes the **view, the changelist export and the executor run** together
— a run only writes the group being looked at. Off-cohort (wrong-age) members are
their own `misplaced` group now, not mixed into the age transitions. This is the
escape hatch for this year: run the clean Spårare→Upptäckare and Äventyrare→Utmanare
groups, and leave Upptäckare→Äventyrare (ambiguous with two Äventyrare avdelningar)
for later / by hand.

Also built: a **save-selection handoff** — "Spara urval för utförande" on the
Uppflyttning blade commits the chosen group (browser-local); *Utför uppflyttning*
then runs that saved group, auto-shows its dry-run, and is empty (pointing back to
Uppflyttning) when nothing is saved. The **Äventyrare→Utmanare election** shows only
when working that group, and its direct entry takes just the 5-digit avdelnings-id
plus a confirmation — the name is immaterial (a placeholder is stored).

**Follow-up — the target-resolution rule (agreed definition).** Per source, in
order:

1. **A configured flow hint** (e.g. the same-weekday match, Hajarna Mon → the Mon
   Upptäckare) → resolve to that target.
2. **No hint but exactly one possible target** → propose it as the default (still
   overridable per member).
3. **No hint and multiple targets** → **the operator must select per person**, via
   the existing per-member override dropdown.
4. **Exception: Äventyrare→Utmanare** always uses its single cohort-level election
   (it creates one new avdelning for the whole cohort — a cohort decision, not a
   per-person one).

So Spårare→Upptäckare stays automatic (weekday hint); Upptäckare→Äventyrare is
auto-defaulted today (one Vikingarna) and becomes must-select-per-person once the
second Äventyrare avdelning exists. Building it means switching `merge` off the
config `default_target` onto inference (reinstate the reverted `infer_target_name`
in `uppflyttning.engine`) so two Äventyrare correctly read as ambiguous, and
dropping the per-source `default_target`s from config.

- **Even-split projection stats** — where a target is ambiguous across N avdelningar,
  distribute count/N to each for the §20 projection figures only (never for an
  actual move; config will not be kept perfectly current).

**B. Config architecture — maintenance/portability, no deadline.**

- **Single config location.** Remove `config_path` / `config/karverktyg.default.json`
  and fold the (now-slim) kår config into `karverktyg.conf`. Motive: "if we
  configure in multiple places we will forget." Constraint: keys must never be
  committed (hard rule 1), so the single file is the **gitignored `.conf`**, and a
  structured avdelning list must be expressed there (e.g. a JSON-valued env var).
- **Multi-kår generality.** Keep kår structure configurable and generic scouting
  rules (brackets, section classification) as defaults, so another kår extends
  config/lists rather than forking. Only matters if the tool is shared.

**C. Security hardening — only once it could leave one machine.** The frontend and
API are one Flask service, so access to the static site is access to the REST API.
Today it is reachable only via `kubectl port-forward` (ClusterIP, no Ingress, no
CORS). Before sharing: sanitize and validate all API input, and put human auth at
the ingress (§14). The data is GDPR-sensitive.

### Standing operational work, not a phase

- **Key handling.** See *Open actions*.
- **Get the repo onto a remote.** See *Open actions*.
- **Spec drift check** — re-bundles upstream and diffs against the vendored copy.
  Never auto-updates; adopting a new spec version is a reviewed change. Cannot
  see the three undocumented endpoints.
- **Read-only canary** — scheduled, weekly by default. Confirms the API still
  answers and the response still parses. A stale success is itself a failure, so
  the age of the last success is shown on the capabilities page.
  **Extend it to report the distinct set of `raw_value` codes seen on
  `current_term` and `prev_term`.** Invoicing for Höst 2026 lands roughly a month
  out; new payment codes appearing while nobody is watching is exactly the change
  a structural check misses.

### Deliberately out of scope

- **Bulk moves out of an Utmanare avdelning — never build this.** Retiring an
  Utmanare avdelning is not a bulk operation and must not be modelled as one. Where
  each member goes is an individual judgement: some become Rover, some stay in
  utmanarverksamhet past the nominal age, some move to Ledare, some leave. There is
  no rule the tool could apply that would be right often enough to be safe, and a
  "move everyone in X to Y" control invites exactly the wrong action. This is
  deliberately human, case-by-case work in the Scoutnet UI. If someone proposes it
  again, this paragraph is the answer.
- Weekly attendance tracking via arrangemang (§5), pending Phase C
- Creating arrangemang programmatically — no endpoint exists
- Multi-kår tenancy. Branding and kår identity are already configuration, so a
  second kår is a config exercise, not a code one. Nobody has asked.
- Any personal data in Postgres, ever (§9)


## 8. Write execution

### Chunked writes, and why we do not rely on atomicity

The endpoint is batch-capable and **documented** as atomic: any error rejects
the entire request. That claim is attractive — an atomic batch that fails
changes nothing, whereas per-member writes can leave the kår half-moved when a
pod dies mid-run.

**But the claim is unverified, and we have deliberately chosen not to verify
it.** The only way to test it against production is to construct a failing
request, which means fabricating a member number, which means very likely
touching a real person's record in some kår. That is not a trade we make (hard
rule 6). Verifying it would also be the sort of test that is unnecessary if the
design simply does not depend on the answer.

So the design does not depend on it:

- **Chunk size is configurable, and the default is 1.** One member per request
  needs no atomicity guarantee at all. Nothing in the code, the docs or the UI
  may assert or assume that a multi-member chunk is all-or-nothing.
- Chunks are sent **one at a time, serially**, with a configurable minimum delay
  between them. At chunk size 1 a full uppflyttning is roughly 83 requests —
  under two minutes at a one-second delay. The conservative default is close to
  free.
- At chunk size 1 a crash can leave a run partially applied. That is **accepted**:
  the journal records exactly where it stopped and reconciliation catches the
  remainder.
- **Raising chunk size is a deliberate later decision**, taken only once the
  endpoint's real partial-failure behaviour is understood from ordinary
  operation — a chunk that errors during normal use will eventually tell us what
  it did. Record what was observed here before changing the default.
- No documented limit on batch size or request rate exists. Treat this as
  unknown. Small chunks are also how we stay clear of undiscovered limits.
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

Before the first request of any bulk run, capture the current placement of
**every** active member — movers and non-movers alike — to a file on a mounted
volume. This is the recovery/undo "before" board: if a run touches someone it
should not, the snapshot lets you detect and reverse it. The intended change
(the "delta") lives in the write journal, not here.

**A snapshot holds no personal data.** The tool can only ever write `status`,
`troop_id` and `patrol_id` (§4), so those three fields plus `member_no` are the
entire restorable state — names, personnummer, dates of birth and addresses are
never at risk and are never written to a snapshot. Leadership (which troops or
the group a member holds a leader-scoped role in) is recorded too, as a
belt-and-suspenders audit record — the tool never moves leaders, but if anything
goes awry we still know who led what. This supersedes an earlier design in which
snapshots held the full memberlist including personnummer.

**Be explicit about what this narrows.** The earlier full-memberlist snapshot was
a general recovery artifact for the register; a placement snapshot is not. It
protects against **this tool's** mistakes — the three fields the tool can write —
and against nothing else. If the register is damaged by a hand edit, a Scoutnet
fault, or anyone else's integration, the snapshot cannot help, because it never
recorded the fields involved.

That is the right trade: the alternative was holding personnummer for 371 people
on a volume for thirty days in order to guard against damage this tool cannot
cause and is not responsible for. But it is a **different guarantee** than the
one originally specified, and both this document and the runbook must say so
rather than leaving a reader to assume "snapshot" means "backup".

- **A file, not the database, and deliberately so.** The snapshot is an
  out-of-band reference file so it survives a database migration or rebuild —
  the exact situation in which you might need to read an old state. It is
  self-describing (embeds run, timestamp, member count) and readable on its own.
  The DB `snapshot` row is only an index for the UI.
- Volume only for the file; never in git, never in an image. The index row in
  Postgres carries no personal data (only `member_no` and placement, like every
  other table).
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

   The malformed-payload test lives **here and only here** — a non-numeric member
   key, or an out-of-enum `status`. Against the mock it exercises our own error
   handling, failed-chunk display and resume path. It tells us nothing about
   Scoutnet's behaviour, and neither the code nor the docs may imply it does.

2. **A single member against the real API**, agreed in advance.

   Two subjects are available: a **placeholder account used for receiving mail**
   (a non-person, and the correct first choice — a mistake there damages nothing),
   and **the operator's own record** as a second. Prefer the placeholder for
   everything that can be done there.

   Note that the operator's record carries leader roles and the administrative
   access this tool depends on. Testing writes against the account you rely on
   for access is worth avoiding wherever the placeholder will do.

   **Enforce a member allowlist — on the stage-2 verify path only.** A
   config-supplied list of member numbers that the *single-member verify* writes may
   touch; the executor refuses any member not on it for `kind="stage2_verify"`
   (dry-run and execute), and a test asserts the refusal. This bounds the blast
   radius of a stage-2 test write to designated records. Store member numbers in
   config, never names in the repo.

   **It does not gate a production uppflyttning (amended).** Per-member allowlisting
   a real bulk move is redundant and self-referencing — the list would just be the
   300+ computed movers, and the operator will never maintain such a list. Instead:
   the operator is authorised by `read_write` mode + config (no random user reaches
   this), and the *change* is authorised by their deliberate **save** in the
   Uppflyttning blade plus the dry-run review, the confirmation, and snapshot/undo
   (§8 stage 3). The earlier design that allowlisted every write is superseded.

   Three checks, on the placeholder wherever possible:

   - **troop_id** — confirm `unit.raw_value` is the id the write endpoint
     accepts. This is the last outstanding assumption from §5 and the only one
     that can block a real run.
   - **Round trip** — move A → B, reconcile, undo, reconcile again. Exercises
     write, reconciliation and undo end to end on a record nobody depends on.
   - **Idempotency** — repeat the same write and confirm it is a no-op. The
     resume-after-crash design assumes this, so it needs confirming rather than
     asserting.

   **Atomicity is not tested here.** See above: chunk size defaults to 1 so
   nothing depends on the answer.

   Verify each result by hand in the Scoutnet UI, not only through the tool.

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

### Deploy bootstrap

An idempotent bootstrap runs on every deploy and brings the database to the
current schema, reusing it when possible: empty → migrate; alembic-managed →
upgrade; unmanaged but schema-compatible → adopt in place; incompatible and not
migratable → preserve the meaningful data (email templates, finding acks,
message log), rebuild the schema, and drop everything else.

**Uppflyttning working state is never preserved across a migration or rebuild.**
The per-cohort-year decisions and target elections (`uppflyttning_entry`,
`cohort_target`) are scratch data, and a version bump may itself be prompted by
an incompatibility — so they are cleared whenever migrations are actually
applied. A redeploy that applies no migration leaves them untouched, so
in-progress decisions survive ordinary restarts.

## 10. Email

Gmail API, service account with domain-wide delegation, scope
`https://www.googleapis.com/auth/gmail.send` only. Sending mailbox is a config
value and must be inside the Workspace domain. No SMTP.

Two `MailSender` implementations: Gmail, and a recording fake used in
development and tests. Nothing in the test suite can send real mail. Sending is
idempotent — check the message log before, write to it after.

**Drafts vs sending — today it is drafts only.** The current path generates email
*drafts* (recipients, subject, body) for the operator to copy into their own
mail client. The tool sends nothing during the scout-year startup. The Gmail
auto-send above is built but deferred to a later, separately-tested rollout; it
is never the startup path, and it will be reviewed and improved before use.

**Templates.** Stored in the **database** and editable in-app. Shipped defaults
are the fallback and serve as worked examples; the resolver returns the DB row
if present, else the default, so drafts work with no seeding. Jinja variables at
minimum include `first_name`, `kar`, `birth_year`, `pronoun`,
`bracket_label` and `avdelningar_sentence`.

**Membership-request drafts.** For waiting / awaiting-approval applicants,
generate one draft per applicant:

- **Recipients.** Scouts → guardians; **Ledare applicants → the person
  directly, never their parents.** Guardian resolution: `contact_email_dad` and
  `contact_email_mum` where present, deduplicated case-insensitively for a shared
  family address, falling back to the member's own `contact_email`. Ledare
  resolution: the member's own address only. If nothing resolves, do not fail
  silently — surface the member as unsendable.
- **Separate templates** for scouts and for Ledare.
- **Content.** First-name substitution at minimum; the scout template states the
  applicant's birth year, the bracket their age makes them eligible for, and that
  bracket's avdelningar with their weekdays, then asks for a weekday preference.
  Pronoun from the `sex` field — han/hon, and **hen** when unknown.

When (later) auto-send is used, show the resolved recipient list before sending
and record only the count and timestamp in the message log, never the addresses.

## 11. Findings (data quality and enforcement)

One model covering two categories, both **advisory only**. The tool never
changes a member to resolve a finding.

**Data quality** — probable formatting problems, computed with `phonenumbers`
(region SE) and `email-validator` with deliverability checks **off**, since
per-member DNS lookups would be slow and unreliable. Postcode and address
heuristics tuned against real data once the capture exists.

**Membership roll enforcement:**

- **Anyone set as a leader in the Ledare avdelning — treat as a security
  finding, highest severity.** Leaders can edit the details of everyone they
  lead. A leader role scoped to the Ledare avdelning therefore confers edit
  rights over every adult in the kår, including the kårordförande. Adults are
  *members* of Ledare; nobody is ever a *leader* of it. Flag prominently and
  distinctly from ordinary data-quality noise.
- Anyone 18 or over holding a scout membership in an avdelning, except
  avdelningar configured as 18+. Note that adults being members of Ledare is
  normal and must not be flagged — the check applies to scout avdelningar.
- **Scouts belonging to more than one avdelning.** Computed from `unit` plus
  the `roles.value.troop` keys. `unit` is single-valued, so a second avdelning
  only shows up through a role — meaning a plain scout enrolled twice with no
  role would be invisible. Per the operator that does not occur in practice;
  the real case is a scout who also holds an assistant-leader role elsewhere,
  which is a role and therefore visible. Flag for review, never auto-move.
- **Members with no avdelning at all.** Present in live data. Manual resolution.
- **An avdelning with scouts but no recorded leader.** Either a real staffing gap
  or a missing role assignment; both need a human. **Only fires when the avdelning
  has at least one member** — a newly created, entirely empty avdelning is not a
  finding, it is just new.
- **A very young scout set as a leader** — anyone in a scout bracket (Äventyrare
  or younger) holding a leader-class role. Very young scouts should not be
  leaders, so this is surfaced as an error in the findings blade
  (`young_leader`). Distinct from the Ledare-avdelning security finding above.

**Scope: the structural checks above apply to Spårare, Upptäckare and
Äventyrare only.** Utmanare and Rover are exempt from both the age check and
the multi-avdelning check. Their composition is deliberately variable once
formed — members move between avdelningar and new members are recruited
directly — and they are never auto-moved, so a finding there prompts no action
and is pure noise. An Utmanare assisting in a younger avdelning is normal at
this kår, not an anomaly.

Data-quality checks (email, phone, address formatting) still apply to everyone.
Those are about the accuracy of the record, not the shape of the membership.

Note that role-holders and Ledare members are different populations that
overlap only partially — an adult can sit in Ledare with no recorded role, and
a role-holder can sit in a scout avdelning. For move-exclusion take the
**union** of both signals; over-excluding is safe, under-excluding moves a
leader.

**Patrol-scoped roles are not leadership — classify by scope, not key.**
Patrulledare and Vice patrulledare are patrol-level *youth* roles held inside an
avdelning's patrull. In the API they reuse the `leader` / `vice_leader` role
keys, but their `scope` is `patrol` (real adult leaders are scoped `troop` or
`group`). A `patrol`-scoped role therefore never counts as a leader — not for
the union above, and not for the `young_leader` check. A Patrulledare is an
ordinary scout who moves up with their cohort like anyone else. (In the
2026 data this was ~25 scouts wrongly held back before the scope rule.)

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

The key fingerprint names its method — `sha256[:8]` of the key's UTF-8 bytes —
so an operator can reproduce it against a candidate key without the tool ever
revealing the key.

Permissions are **per deployment**, not per user.

**API-koll (endpoint self-test).** A dedicated blade probes each configured
endpoint key with a *real* read and tabulates the result per endpoint: OK / FEL
/ Avstängd (blank key = deliberately off) / Fixtur. It is green when every
configured key answers. A misconfigured key must be impossible to miss — it
raises a site-wide, clickable banner shown on **every** blade that links here,
plus a per-failure info box carrying the exact error. In fixture mode every
check is green, but the blade says loudly that it is serving committed sample
data, not testing live keys.

## 13. Configuration

All configuration through pydantic-settings, environment-driven, Kubernetes
Secrets for keys and a ConfigMap for the rest. Notable knobs: chunk size, delay
between chunks, snapshot retention window, allowed avdelningar, kår identity.

- **Kår identity and branding** configurable, defaulting to Scoutkåren Finn.
  Vendor Finn's logo and colours into the repo from scoutkarenfinn.se — never
  fetch at build or run time. Keep them in a swappable directory.
- **Age brackets and uppflyttning flows are configuration, not code.** The full
  specification is §17. The active configuration must be viewable in the app.
- **Leaders are never auto-shifted (no automatic leader moves)** — being set as a
  leader in an avdelning keeps the member there. This excludes leader-class roles
  only: a scout who holds a plain *non-leader* function elsewhere still shifts
  with their cohort (flagged with a note for review). Adults (18+) and members of
  an 18+ avdelning are likewise excluded. A young scout who is a leader is not
  shifted **and** is raised as an error in §11.
- Per-member decisions, the target election and "keep in place" are all scoped to
  the cohort year and never carry forward: next year is computed fresh and a
  "keep" carries an expiry year, so shifting scouts off leaves no state behind
  for the future (§9 purge). A reset clears the whole year's working state.

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

## 16. Definition of done

- `uv run pytest` passes with no network access
- ruff clean, lint and format
- No secrets and no real member data in git history
- README covers key generation, glossary, configuration and current-phase limits
- Tests exist for: rejection of `cancelled`, absence of write methods in
  `fixture` and `read_only` modes, absence of personal-data columns,
  no-parallel-writes, resume after crash, snapshot written before first request,
  reconciliation reporting, undo excluding externally-changed members, ack
  invalidation when a value changes, and mail senders being inert under test
- And for the observed API quirks specifically: `roles` parsed correctly when
  it arrives as `[]` rather than a dict, no `extra_info_` key surviving the
  client boundary, `not_invoiced` excluded from the unpaid list, an
  unrecognised payment code routed to the review bucket rather than either
  pile, and `prev_term_due_date` retaining both dates when a reminder shifted it

A **runbook** is maintained at `docs/runbook.md`: how to obtain a key, how to run
a bulk operation, what to do when one fails halfway, how to undo a run, and how to
restore from a snapshot. Written for whichever of the other two leaders would have
to run it if the author were unavailable — this is annual software and nobody will
remember the details eleven months later. **Any phase that adds a write path must
update it.**

## 17. Age brackets and uppflyttning

All of this is **configuration**, not code. The engine understands the four
transition kinds below and reads everything else from config; the app displays
the active configuration.

### Cohort and age

**Key on birth year, never on school year.** Åk was considered and rejected —
it requires assumptions about school start dates that can drift, while birth
year is directly derivable from `date_of_birth` and cannot.

- Cohort year **N** = the calendar year of the autumn term.
- Age for bracket purposes = **N − birth year**. Not the member's actual age on
  a given date; the whole cohort shifts together at the summer transition.

### Brackets, for N = 2026

| Bracket | `unit_type` | Age | Birth years | Avdelningar |
|---|---|---|---|---|
| Spårare | 2 | 8–9 | 2017, 2018 | Hajarna (Mon), Späckhuggarna (Tue), Rockorna (Wed) |
| Upptäckare | 3 | 10–11 | 2015, 2016 | Kämparna (Mon), Spejarna (Tue), Utforskarna (Wed) |
| Äventyrare | 4 | 12–14 | 2012–2014 | Vikingarna (Thu) |
| Utmanare | 5 | ~15–17, varies | | three, roughly one per cohort |
| Rover | 6 | up to 26 | | several, small |

Weekday is not available from the API. It lives in config, per avdelning,
alongside the troop_id.

### The avdelning roster

Fourteen avdelningar as of 2026-08-02. Member counts sum to 369; the capture
found 371 active members of whom 2 have no `unit`, which reconciles exactly and
independently confirms that `unit` is single-valued with no double counting.

| Avdelning | `unit_type` | Age range in Scoutnet | Weekday | Members |
|---|---|---|---|---|
| Hajarna | Spårare (2) | 8–9 | Mon | 20 |
| Späckhuggarna | Spårare (2) | 8–9 | Tue | 16 |
| Rockorna | Spårare (2) | 8–9 | Wed | 21 |
| Kämparna | Upptäckare (3) | 10–11 | Mon | 24 |
| Spejarna | Upptäckare (3) | 10–11 | Tue | 26 |
| Utforskarna | Upptäckare (3) | 10–11 | Wed | 14 |
| Vikingarna | Äventyrare (4) | 12–14 | Thu | 69 |
| Finndus | Utmanare (5) | 15–18 | | 17 |
| Finnemang | Utmanare (5) | 15–18 | | 13 |
| Fniss | Utmanare (5) | 14–18 | | 17 |
| Finness | Rover (6) | none set | | 3 |
| Finnurligt | Rover (6) | none set | | 5 |
| Parafinn | Rover (6) | none set | | 4 |
| Ledare | Annat (7) | 18– | | 120 |

Counts are indicative, recorded for sanity-checking, and will drift. troop_ids
come from `unit.raw_value` at runtime, not from this table.

**Avdelningsledare names are deliberately omitted.** They are personal data and
the tool has no use for them; leadership is read from `roles` at runtime.

Note that the three Utmanare age ranges overlap completely and Fniss starts at
14 rather than 15, so **cohort cannot be inferred from an Utmanare avdelning's
configured range**. Each carries a `cohort_year` in our config instead, recorded
when the avdelning is created — the three existing ones need theirs filled in.

**`Ledare` is the only avdelning configured 18+**, and is the sole entry in the
18+ list for the §11 age finding.

### Expected transition volumes

Roughly 28 Spårare, 32 Upptäckare and 23 Äventyrare move each summer, so about
**83 members** in a full uppflyttning — roughly 83 requests at the default chunk
size of 1 (§8). Use this as an order-of-magnitude check: a computed master set of
8 or 300 means something is wrong.

### The four transition kinds

**1. `same_weekday` — Spårare → Upptäckare**

Only the **oldest Spårare cohort** moves. Target is the Upptäckare avdelning
meeting on the same weekday: Hajarna → Kämparna, Späckhuggarna → Spejarna,
Rockorna → Utforskarna. Younger Spårare stay put.

**2. `merge` — Upptäckare → Äventyrare**

Only the **oldest Upptäckare cohort** moves, from all three avdelningar into
Vikingarna. Younger Upptäckare stay put. This is the one place three
avdelningar collapse into one.

**3. `new_cohort_avdelning` — Äventyrare → Utmanare**

The oldest Äventyrare cohort leaves Vikingarna for a **new Utmanare avdelning
created for that cohort**. Creation is age-based: one new avdelning per cohort
year, formed around the group leaving Vikingarna.

Each Utmanare avdelning therefore carries a **`cohort_year` in our config**,
recorded when it is created. The target for cohort N is the Utmanare avdelning
whose `cohort_year` is N — determined, not chosen freshly each run.

Scoutnet's own age range for these avdelningar is a generic 15–18 and does not
encode the cohort, which is why `cohort_year` lives in our config rather than
being read from the API.

The tool cannot create avdelningar. So the operator creates it in Scoutnet, then
selects it here. Two ways to select, because a brand-new avdelning has no members
and is therefore invisible to the memberlist (§20):

1. **A dropdown** of every avdelning the tool knows — those discovered from
   `unit.raw_value` plus any registered in config.
2. **Direct entry of a `troop_id`**, for the case the dropdown cannot cover: an
   avdelning created minutes ago with nobody in it.

**Direct entry is an explicit, deliberate relaxation of §8's rule that `troop_id`
may only come from the resolved name → id map.** It is allowed only here, only for
this election, and only with these guards:

- **The group id is rejected outright.** `1025` is the kår, not a troop, and sits
  beside troop ids in `roles.value` where it is easy to confuse. Never accepted,
  with a test asserting it.
- **Shape check.** Observed troop ids are five digits; the group id is four.
  Reject anything outside the expected range and say why.
- **Show what the tool knows before accepting.** For an id absent from the map,
  state that plainly — *"unknown avdelning, not in config, no members"* — and
  require an explicit acknowledgement. Do not present an unknown id as if it were
  verified.
- **Do not write it to config.** The value matters for a few minutes once a year.
  In deployment config it would sit stale, pointing at last year's avdelning, and
  offer itself as a plausible default at the next election — a silent wrong-cohort
  failure. Persist it as **run metadata keyed to the cohort year** instead, so the
  record reads *this cohort went to that troop_id*, never *the target is that
  troop_id*. This is the mirror of hard rule 7: put each value where its lifetime
  says it belongs. A key lives as long as the deployment; a target avdelning lives
  as long as one election.
- **Never allow manual entry anywhere else** — not for the source avdelning, not
  for per-member overrides. This is one hole, in one place, for one reason.

Accept explicitly that this path is thinner than the map-derived one. Nothing
validates a hand-typed id against prior data, so the only defences are the checks
at entry plus the recovery path: the dry run displays the target id before anything
is written, the operator can open that id in Scoutnet to confirm it is the
avdelning they meant, and reconciliation plus undo cover a mistake afterwards.
Until a target is selected the transition shows as pending with an explanation,
rather than silently producing an empty move set.

**This option exists only because there is no API route to an empty avdelning.**
The endpoints available to this kår expose troop ids only through members, so an
avdelning with nobody in it cannot be discovered
(`/organisation/group` returns `active_troops` as a bare count; `/group/resources`
is the facilities directory; `/project/get/groups`, which does carry troop objects,
is not available to us).

**If that ever changes — a new endpoint, an endpoint enabled for this kår, or a
troop id appearing in the memberlist for member-less avdelningar — remove manual
entry and read the avdelning from Scoutnet instead.** It is a workaround kept for
want of an alternative, not a feature to preserve. The spec-drift check (§7) is the
mechanism most likely to notice, so treat any new group-scoped endpoint touching
avdelning structure as a prompt to revisit this section.

**The target is elected once, for the whole cohort.** The operator creates the
new Utmanare avdelning in Scoutnet and elects it as the target; that election
is a **single choice covering the entire moving cohort — the oldest Äventyrare
birth year only, not all of Vikingarna** — and never a per-member decision.
Roughly 23 of Vikingarna's 69 members; the other two cohorts stay put. The
default offered is the avdelning whose `cohort_year` is N.

**The target may already have members.** By migration time it might hold
leaders assigned to it, or scouts transferred manually in advance. Never
require or assume an empty target:

- Do not warn or block on a non-empty target.
- Show its current membership before the run, so the operator can confirm they
  elected the right avdelning.
- Reconciliation compares against **intent**, never against "the target should
  contain exactly the moved cohort". Pre-existing members are not drift.
- Undo reverses only the members this run moved. It must never remove someone
  who was already there.
- A scout transferred manually beforehand is no longer in Vikingarna and so
  drops out of the Äventyrare set naturally. No special handling, but do not
  let them appear twice.

**A genuinely empty target is invisible to the tool.** The avdelning-name →
troop_id map is derived from `unit.raw_value` across the memberlist, so an
avdelning with no members appears nowhere in the response and cannot be
discovered. Either it holds at least one member — in practice a leader — or the
operator supplies its troop_id at the target election (direct entry, stored as run
metadata keyed to the cohort year — never in config; §20). When an elected target
cannot be resolved, say exactly this rather than failing obscurely.

Per-member overrides still layer on top for individual exceptions, per below.
Keep the two levels distinct in the UI and in the config: cohort-level target
election first, individual exceptions second.

The transition stays pending until the new avdelning exists and has been
elected. There is no path that moves the cohort into an existing Utmanare
avdelning — a new one is created each year, outside the tool.

**`cohort_year` describes the core, not the boundary.** An Utmanare avdelning
is built around one specific birth year, and that stays true — but the edges
drift, because members move between Utmanare avdelningar and new members are
recruited directly into them.

So `cohort_year` may be used to **describe, order and project**: label an
avdelning in the UI, sort the three by age, feed the next-year membership
projection, and order the three by age. It must **never** be used to generate a
finding, to move anyone after the avdelning is formed, or to suggest that an
avdelning should be retired. A member whose birth year differs from
their avdelning's cohort is expected, not an anomaly.

**4. `never_auto` — Utmanare and Rover**

No age-based moves, ever. An Utmanare sitting in an avdelning whose founding
cohort does not match their birth year is **not** a finding — do not interfere.

**The tool never moves an Utmanare, for any reason.** When an avdelning is
eventually retired, its members disperse individually — some to Rover, some
continuing with utmanarverksamhet past the nominal age, some to Ledare, some
leaving. That is a human decision per person, taken in the Scoutnet UI. No bulk
move-out control exists and none is to be built (§7, *Deliberately out of scope*).

The tool may still *show* which avdelning is oldest, as ordering information. It
draws no conclusion from it.

### Utmanare and Rover are age-exempt

Neither is age-checked, in moves or in findings. An Utmanare who turns 18 is
**not** flagged — their avdelningar are configured up to 18 anyway, and the
bracket is operator-managed by design. A Rover over 26 is not flagged either. A
Rover membership held alongside another avdelning is **not** flagged by the
multi-avdelning check in §11; it harms nobody and would generate constant noise.

The §11 age finding therefore applies only to Spårare, Upptäckare and
Äventyrare avdelningar, with Ledare as the configured 18+ exception.

### Where cohort year N comes from

**Config, with the live term as a cross-check.** Do not derive N from the live
response alone — a mid-cycle capture could silently shift every cohort by a
year, which would produce a plausible-looking and completely wrong master set.

Cross-check against the `current_term` label. N is the year of the autumn term
the scouts are moved **into**, and the uppflyttning is always computed before
the summer camp, so **both `"Höst YYYY"` and `"Vår YYYY"` give N = YYYY**:

- In spring (`"Vår YYYY"`) you are planning the coming summer's move into Höst
  YYYY. The members are still placed for the *prior* scout year — that is
  expected, and the engine handles it by moving whoever has aged one step past
  their bracket, not by trusting the nominal age band.
- In late summer / early autumn (`"Höst YYYY"`, before the move is entered in
  Scoutnet) you are completing that same move.

Deriving N as `YYYY − 1` in spring — naming the *current* scout year instead of
the autumn the move feeds — is wrong: every mover then looks correctly placed
and the master set comes out empty. This bit us against real spring data.

If the configured N and the derived N disagree, **refuse to compute a master
set** and say which two values conflict. This is a cheap guard against the
single most damaging silent error in the whole tool.

### Off-cohort members

A member whose birth year does not match any cohort of their current bracket —
say a 2014-born still in Spårare — is **flagged for review and excluded from the
automatic move set**. Never moved two brackets automatically.

These require manual intervention. List them prominently, and require the
operator to explicitly acknowledge the list before proceeding, so they cannot be
scrolled past. The gate sits before a run can be confirmed, and equally **before
the changelist export** when the manual route is used — and the
acknowledgement, with its timestamp and the count acknowledged, is stamped on
the workbook's cover sheet. Excludes Utmanare and Rover per above.

### Per-member overrides

The computed master set is editable per member, either to a different target
avdelning than the default, or to stay an extra year.

**"Stay an extra year" carries an expiry cohort year, never a boolean.** Store
it as *keep in the current avdelning through cohort year N*. A boolean would
lapse into a double move the following summer, when the rule sees someone two
years over. The override expires by itself, and the app shows when it does.

Overrides survive recomputation of the master set — recomputing must not
silently discard operator decisions. Show which entries carry an override and
who set it.

### Leaders

Members holding a leader-class role, and members of the Ledare avdelning, are
excluded from all age-based moves. Take the union of both signals per §11 —
including its scope rule: patrol-scoped roles (Patrulledare / Vice patrulledare)
are youth roles, not leadership, and move with their cohort. A scout who also
holds an assistant-leader role elsewhere is flagged for review rather than
auto-moved.

### Yearly maintenance

Bracket birth years shift by one each year with N, so they must be **derived
from N**, not hardcoded as literal years in config. The table above is
illustrative for N = 2026; the config expresses ages, and the engine resolves
birth years. Adding a new Utmanare avdelning each year is the operator's job,
and the app should say so at the point the transition needs it.

## 18. Förtroendeuppdrag (Phase A specification)

Lists every kår-level assignment currently held, from the **`group` scope** of
`roles.value`. Only Finn roles are in scope: district and national assignments do
not appear in the memberlist and are explicitly not covered.

`troop`-scoped entries are avdelning leadership and belong to the uppflyttning and
findings logic, not here. `patrol`-scoped entries are youth roles (§4) and are
excluded entirely.

Needs no new key, endpoint or capture.

### Presentation

One **solid flat list**, one row per assignment: role, person, member number. A
person holding several assignments appears once per assignment — this is a register
of posts, not of people.

Ordering:

1. **Styrelse first**, in constitutional order — ordförande, vice ordförande,
   kassör, sekreterare, ledamöter, suppleanter.
2. **All other engagements** after, grouped by role, roles in configured order,
   any unconfigured role last.
3. Within a role, people sorted by name using Swedish collation (§2).

Ordering comes from a configured list of `role_key` values. **Ordering is config;
membership of the list is not.** A `role_key` absent from the config is still
displayed, sorted last, never dropped. This blade must be pure pass-through:
unlike leader classification it matches on nothing, so an unfamiliar
förtroendeuppdrag appears by itself rather than vanishing.

Match, sort and configure on `role_key`. Never on `role_name`.

Exports: Excel and A4 PDF, per §19's report conventions.

### Role labels

Display `role_name` as Scoutnet returns it. Do not translate, rename or reinterpret
a role — Stugbokare shows as Stugbokare, whatever it is used for locally.

A `role_key` → label override map may exist in config for the case where Scoutnet's
own name is genuinely unhelpful, but it ships **empty** and nothing depends on it.
Renaming a role in the tool but not in Scoutnet means two systems disagreeing about
the same post, which costs more in confusion than it buys in clarity.

Match, sort and configure on `role_key`; display `role_name`. Never the reverse.

If a `role_key` is ever leader-class but used locally for something that is not
leadership, it needs an explicit exclusion from the leader-classification rules —
otherwise its holders are silently dropped from age-based moves.

### Reconciliation

`/organisation/group` returns `rolecount`. Compare it against the number of parsed
assignments and display both. A mismatch means a scope is being missed or the parse
is wrong — the same independent-total check that confirmed 369 + 2 = 371 for the
memberlist.

### Optional: vacancies

If a list of expected förtroendeuppdrag is configured, posts that are expected but
unfilled fall out for free, and are useful ahead of an årsmöte. Strictly opt-in:
with no config, no vacancies are reported, and an unfilled post is never treated as
an error.

## 19. Exports and reports

Restored section. The export and report conventions were lost when the phasing
section was replaced; they were never withdrawn as decisions.

### Report conventions

All reports export to **PDF**, rendered from Jinja2 templates via WeasyPrint so
the print output and the on-screen view share one source.

- **A4**, never US Letter.
- **One avdelning per page**, with a hard page break between them, so a subset can
  be selected and printed later.
- Page header carrying kår, avdelning, term and generation timestamp; page numbers
  as "x of y".
- Swedish collation for every name list.
- Print stylesheet only — no separate report-rendering path to drift out of sync
  with the screen.

Excel is offered alongside PDF wherever the content is genuinely tabular and
someone might want to sort or filter it.

**All exports stream to the browser.** Never written to disk server-side, never
cached, never stored in Postgres (§9). Once downloaded they are the operator's
responsibility.

### Changelist export (uppflyttning)

The computed master set, after review and per-member overrides, exported as an
**Excel workbook** for manual execution in the Scoutnet UI. A permanent
first-class output, not a stopgap: "export the changelist" and "execute the
changelist" are two buttons over the same reviewed set, never two code paths.

Designed for the person doing the data entry:

- One sheet per **target** avdelning, so the operator works through one destination
  at a time without jumping around the UI. Swedish collation within each sheet.
- `member_no` in the first column — it is the search key in Scoutnet — with name
  alongside for confirmation, then source and target avdelning.
- A "done" column and freeze panes: a hundred manual edits happens across more
  than one sitting and the operator needs to record where they stopped.
- A cover sheet with generation timestamp, term, per-avdelning totals, the
  configuration version the set was computed from, and the off-cohort
  acknowledgement (§17) with its timestamp and count.

**Post-hoc reconciliation.** After manual execution, re-fetch the memberlist and
diff it against the changelist: how many applied, which members were not found,
which ended up somewhere other than intended. Pure read, and it catches exactly
the transcription errors manual entry produces. The same reconciliation code
serves the write executor (§8).

### Översikt export

The overview (§20) as an Excel workbook **and an A4 PDF**. Treat the PDF as a
first-class output rather than an afterthought: this is the one artifact in the
tool that is genuinely interesting to people beyond the person who generated it —
board members, avdelningsledare, an årsmöte, a bidrag application — and it is
aggregate-only, so it can be circulated without hesitation.

**Exempt from §19's one-avdelning-per-page rule.** That rule exists for
per-avdelning reports; the Översikt is a summary, and splitting it across fourteen
pages would destroy the comparisons that make it useful. Aim for one or two pages:
composition by åldersgrupp, the leader columns and ratio, the projection with
recruitment targets, and the KPIs. Everything else from §19 still applies — A4,
Swedish collation, page header with kår, term and generation timestamp, page
numbers, and the same Jinja2/WeasyPrint template as the screen view.

One sheet per table on the blade — composition by åldersgrupp, leaders, projection
(including recruitment targets and pending requests), åldersgrupp transitions,
KPIs — plus a cover sheet carrying kår, generation timestamp, the current term
label, and **the cohort year the projection targets**. Without that last one a
saved workbook is unreadable six months later.

**Everything on the blade goes in the workbook**, including the per-avdelning
leader count, the adult/youth leader split, the scouts-per-leader ratio, and the
`-` placeholders where a figure is not applicable. Write `-` as a literal string:
do not substitute 0, and do not leave the cell blank — a blank reads as missing
data rather than as not applicable.

**Configured avdelningar with no members appear as rows**, all-`-`, rather than
being omitted (§20). An avdelning missing entirely from a board paper is worse
than one showing dashes.

Two rules that matter more in a spreadsheet than on screen:

- **The derived / static / unknown labelling must survive the export** (§20). On
  the blade the caveat sits next to the number; in Excel someone will copy a
  column into a board paper. An unqualified projected Spårare figure is exactly how
  a plan gets built on a number the tool never claimed to know. Carry the
  qualifier as its own column, not as a footnote.
- **Numbers as numbers**, not text, so they can be summed and charted by whoever
  receives them.

Unlike the other two exports this one is **aggregate only — no names, no contact
details, no member numbers.** It is therefore the one export that can circulate
freely: board papers, årsmöte handouts, a bidrag application. Say so on the cover
sheet, because the habit built by the other exports is to treat every download as
confidential.

### Unpaid dues export (Medlemsavgifter)

Everyone outstanding for **the current or the previous term**, as an Excel
workbook — a chase list for avdelningsledare.

Membership follows §4's three buckets exactly, and the distinction matters here
more than anywhere else:

- **Included:** anything in the outstanding bucket for either term.
- **Excluded:** `not_invoiced`. No invoice exists, so there is nothing to chase.
  Note that until Höst 2026 is invoiced, `current_term` is `not_invoiced` for
  everyone and this export is driven entirely by `prev_term`.
- **Excluded:** `paid`.
- **Separate sheet, never mixed into the chase list:** any unrecognised payment
  code. Chasing a family whose status the tool does not understand is worse than
  not chasing them. Label the sheet as needing review.

`paid_partial_credit` — paid an incorrect amount — is included but must be
**visibly distinguished** from having paid nothing. The remedy differs: one is a
correction, the other a reminder.

Layout:

- **One sheet per avdelning**, since avdelningsledare chase their own. Plus a
  sheet for members with no avdelning (they exist), and one for Ledare — adults
  owe dues too.
- Cover sheet: generation timestamp, both term labels, per-avdelning outstanding
  counts and totals.
- Sorted by surname within each sheet, Swedish collation.

Columns: `member_no`, name, avdelning, which term(s) are outstanding, the payment
status per term (Swedish label plus the underlying code), due date — carrying
**both** dates when `prev_term_due_date` records a reminder shift (§4) — and `kid`
where present, since it is the payment reference a chase message needs.

Contacts, per §10's dad/mum split: `contact_email_dad`, `contact_email_mum`,
`contact_mobile_dad`, `contact_mobile_mum`, guardian names, and the member's own
`contact_email` and `contact_mobile_phone`. Coverage is uneven; empty cells are
expected and are themselves a data-quality signal (§11). For adult members the
guardian columns will simply be empty — use their own contact details.

**This is the most sensitive artifact the tool produces.** It combines guardians'
contact details for minors with payment delinquency, and unlike other exports its
whole purpose is to be forwarded to other leaders. State that on the cover sheet:
what it contains, that it should not be circulated beyond those who need it, and
that it goes stale — a paid family stays on a downloaded copy forever. Regenerate
rather than reuse.

## 20. Översikt (overview blade)

Read-only, no new key or endpoint. Tables, not charts — see *Presentation* below.

### Current composition

Members per avdelning, **grouped by åldersgrupp** (`unit_type`), with a subtotal
per group and a kår total. Order the groups by age: Spårare, Upptäckare,
Äventyrare, Utmanare, Rover, then Annat/Ledare.

**Empty avdelningar are invisible to the API, so config is the registry.** The
avdelning list cannot come from the memberlist alone: it is derived from
`unit.raw_value`, so an avdelning with no members appears nowhere in the response.
This is not hypothetical — a newly created Utmanare avdelning starts with zero
scouts and zero leaders.

The avdelning config (which already holds weekday and `cohort_year`, §17) is
therefore the **registry of avdelningar that exist** — their names and attributes,
so a brand-new avdelning can be **listed** even with nobody in it. **Config carries
no `troop_id`** (amended: it once carried an optional one for the empty avdelning).
The id's lifetime is one election, not the deployment's, so it belongs where the
operator sets it: a genuinely empty avdelning is **elected as the
Äventyrare→Utmanare target** by direct `troop_id` entry, stored as run metadata
keyed to the cohort year (§17), never in config. A config `troop_id` would go stale
and offer itself as a plausible wrong-cohort default next year.

Merge rules — the memberlist and the config each own different things:

- **Membership counts always come from the memberlist.** Config never asserts a count.
- **Existence comes from config.** A configured avdelning with no members appears
  as a row with `-` in every derived column, never omitted.
- **Ids always come from the live memberlist** (`unit.raw_value`), never from
  config. Config names an avdelning; the live data gives it an id.
- **Discovered but not configured**: show it, and flag that it is missing from
  config, since its weekday and `cohort_year` are then unknown. Never drop it.
- **No config-vs-live `troop_id` refusal is needed** (amended). This section once
  required refusing on a name→`troop_id` disagreement between config and the
  memberlist. With config no longer carrying an id there is nothing to disagree
  with — the refusal became dead. Its stated rationale ("silently preferring one
  would put moves into the wrong avdelning") did not in fact hold: a target
  resolves by name→live-id, so the disputed config value was the one already
  discarded and could never route a move.

Reconcile against `/organisation/group`: `membercount`, `active_troops` and
`waitingcount` give independent totals. Display both figures where they should
agree, and say plainly when they do not — that mismatch is how the 369 + 2 = 371
check was confirmed in the first place.

### Leaders

**Report two numbers, not one.** The populations differ and a single "leaders"
figure would be ambiguous:

- **Members of the Ledare avdelning** — adults on the roll.
- **Holders of a leader-class role** — `troop`- or `group`-scoped, per §11's
  classification, excluding `patrol` scope.

At the 2026-08-02 capture those were 120 and 95. The gap is real, not an error:
an adult can sit in Ledare with no recorded role, and a role-holder can sit in a
scout avdelning. Label each number with its definition. For move-exclusion the
union is used (§17); say so.

Break the role-holder count down per avdelning, since that feeds the ratio KPI
below.

### Projection for the next scout year

For each avdelning: **next-year count = current − outgoing cohort + incoming
cohort**, applying §17's transition rules. Vikingarna, for example, loses its
oldest Äventyrare year and gains the oldest year from all three Upptäckare
avdelningar.

Every åldersgrupp's movement is **derived** from §17's rules. Nothing here is a
forecast:

| Åldersgrupp | Outgoing | Incoming |
|---|---|---|
| Spårare | oldest cohort → Upptäckare, same weekday | new recruits — see below |
| Upptäckare | oldest cohort → Vikingarna | oldest Spårare, same weekday |
| Äventyrare | oldest cohort → new Utmanare avdelning | oldest Upptäckare, all three |
| Utmanare | none by age (`never_auto`) | oldest Äventyrare, into the new avdelning |
| Rover | none | none |
| Ledare | none by age | none |

**Spårare: state a recruitment target, do not predict an intake.** Spårare is the
entry åldersgrupp, so its inflow is recruitment, and the tool has no business
guessing at it. Instead express the outgoing count as what it actually implies —
**"recruitment target for unchanged membership: N"** for the Spårare
åldersgrupp as a whole, where N is the number leaving for Upptäckare.

That is a derived fact, not a projection, and it is the number a kår can act on.
Do not attempt a per-avdelning or per-weekday target — keep this simple and stable
rather than variable.

**Net the pending requests off the target, and show the whole derivation.**
State it as one sentence with all three numbers visible:

> *Spårare: 28 leave for Upptäckare, 12 requests are already pending — a
> recruitment target of 16 for unchanged membership.*

- **X** — members leaving Spårare for Upptäckare. Derived from §17.
- **Y** — pending membership requests that would fall in Spårare, bucketed by
  `date_of_birth` using §17's bracket rules. Reuse that logic; do not
  reimplement the brackets.
- **Z = X − Y** — the recruitment target.

**Never show Z alone.** All three numbers appear together, so nobody treats the
net figure as an oracle. Someone reading only "16" cannot tell whether that
reflects a small cohort leaving or a healthy pipeline.

Handling and honesty:

- **Z can be zero or negative.** Say so in words — *"no recruitment needed;
  pending requests exceed departures by 4"* — rather than printing a negative
  number.
- **Z assumes every pending request becomes a member.** They will not all
  convert, so Z is a floor. State the assumption once; do not model attrition.
- **A missing variant makes Z wrong in the optimistic direction.** Y comes from
  `waiting` and `awaiting_approval` (§4), and `awaiting_approval` reliably
  read-times-out for this kår. If a variant is unavailable, Y is understated and Z
  is therefore **overstated** — the tool asks you to recruit more than you need.
  Show the variant breakdown and mark Z as provisional whenever a source is
  missing. Do not silently compute Z from a partial Y.
- Requests go stale. `waiting_since` is available, so show the oldest request date
  or the age range next to Y. Twelve requests from last week and twelve from two
  years ago mean different things, and only one of them is a real pipeline.

**Utmanare avdelningar project as static.** Nobody moves out of an Utmanare
avdelning by rule (§17), and the eventual dispersal when one is retired is
individual and unmodellable. Say so rather than leaving a reader to wonder why the
numbers do not move.

Also state explicitly, as its own line per transition: **how many members move
from each åldersgrupp to the next.** That is the number people actually ask for,
and it should not have to be inferred by subtracting two columns.

The new Utmanare avdelning may not exist yet. Show it as a pending row with its
incoming count and a note, not as an error.

### Working in both spring and autumn

The projection target is **the next shift not yet applied**, and the target cohort
year is displayed in the heading so it is never ambiguous.

Because N is the year of the autumn term the scouts move *into* (§17), and is
therefore constant from one August through the following July:

- **In spring** the pending uppflyttning is N itself — the same set the
  Uppflyttning blade is computing. The projection is that set applied.
- **In autumn**, once the move for N has been entered in Scoutnet, everyone shows
  as *redan på plats*. The projection then looks one step further, to **N + 1**,
  using identical arithmetic.

Derive the target by asking whether the shift for N is already applied, and offer
an explicit selector so the operator can look at either. Never infer the target
from the calendar month — the term label is the authority (§17).

### KPIs worth having

Small, actionable, and each one either derived from data already fetched or from
`/organisation/group`:

- **Scouts per leader, per avdelning.** The most useful figure on the blade: 26
  scouts with two leaders is a staffing problem, and nothing else in the tool
  surfaces it. Details matter here, because the two halves come from different
  fields:
  - **Leaders of an avdelning** come from `roles.value.troop[<troop_id>]` with a
    leader-class `role_key`. **Not** from membership of the Ledare avdelning, which
    is not per-avdelning. Patrol-scoped roles are excluded — patrulledare are
    youth (§11).
  - **Scouts in an avdelning** come from `unit.raw_value`. A leader of Hajarna
    typically has `unit` = Ledare, so they are not in Hajarna's member count and
    there is no double counting.
  - Express it as **scouts per leader** (e.g. 13:1) rather than a fraction — it is
    the form people reason in.
  - **Threshold in config, per åldersgrupp**, since younger avdelningar need
    denser staffing. Flag when exceeded; do not hardcode a "safe" ratio.
  - **Print the leader count itself**, as its own column. The ratio alone hides
    whether 13:1 means 26 scouts and 2 leaders or 13 and 1.
  - **Split the leader count into adult and youth leaders, and report both.**
    Utmanare and Äventyrare who hold an assistant-leader role in another avdelning
    are real staffing, and should count toward the ratio — but they are not
    interchangeable with adults, so the two figures appear in separate columns and
    the ratio uses the total. Distinguish by the leader's *own* placement: `unit` =
    Ledare means adult; a scout åldersgrupp means a youth leader. Patrol-scoped
    roles remain excluded either way — patrulledare are a within-avdelning youth
    role, not staffing for the avdelning.
  - **Where either side is zero, print `-`, not a number.** A newly created
    avdelning has no scouts and no leaders, and printing `0:1`, `∞` or `0` invites
    a wrong reading. `-` says "not applicable yet", which is the truth.
  - For a **kår-wide** leader total, deduplicate: about a third of role-holders
    hold roles in two avdelningar, so summing the per-avdelning counts overstates
    the number of people.
  - This KPI is only as sound as the role-scope classification. The patrol-scope
    bug would have inflated every leader count on this blade.
- **Size spread within an åldersgrupp.** Spejarna 26 against Utforskarna 14 on the
  same bracket, different weekdays, is actionable: it tells you where to steer new
  recruits.
- **Projected size crossing a configurable threshold.** This is the actionable
  output of the projection: Vikingarna at 69, gaining ~32 and losing ~23, lands
  near 78 in one avdelning. Flag it, because that is the trigger for standing up a
  second Äventyrare avdelning. Threshold in config, per åldersgrupp.
- **Waiting-list depth**, total and per bracket where derivable. Feeds both
  recruitment and the decision to open a new avdelning.
- **Share paid for the term**, cross-checked against `active_paid` from
  `/organisation/group`.
- **Share under 26**, from `below_26`. Relevant to bidrag eligibility, and the kår
  has no other easy way to see it.

**Not available:** retention and attrition. Computing "how many of last year's
cohort are still members" needs historical membership data, which this tool
deliberately does not keep (§9). Do not approximate it — say it is unavailable and
why. Scoutnet's own reports are the place for that.

### Presentation

Tables. With fourteen avdelningar a chart adds nothing a column of numbers does
not say more precisely, and a plot invites reading trends into a single snapshot.

One exception worth allowing: a plain horizontal bar per avdelning, current versus
projected, side by side. That is a comparison rather than a trend, and it makes an
avdelning about to outgrow itself visible at a glance. No line charts, no
time series — the tool holds no history to plot.

Exports: see §19. Excel workbook for the tables and an A4 PDF for the printable
overview, both aggregate-only.
