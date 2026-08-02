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
memberlist returns numeric codes. The mapping is on the Phase 2 critical path
and is currently only one-third known — the `waiting` and `awaiting_approval`
captures are needed to complete it.

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

## 5. Feasibility — read before proposing features

**Feasible now, read-only:**
- Unpaid dues per avdelning (field semantics must be confirmed against real data)
- Applications awaiting approval, and the waiting list
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
memberlist call; no project key is needed. The remaining risk is that
`unit.raw_value` is not the same id the write endpoint expects — low, but
unverified. **Confirm it against the write endpoint before any bulk write**,
alongside the atomicity check that §8 already mandates. Record the verified
mapping in the repo.

**Not feasible with the documented API:**
- Cross-checking members against reported activities
- "Who has missed recent meetings / is becoming less active"
- Per-avdelning activity statistics
- Creating next year's activities from Excel — no create-arrangemang endpoint exists
- Listing configured meetings

Scoutnet models attendance as *arrangemang*, one per meeting, each behind its
own project-scoped key. For Finn that is roughly 15 meetings × 13 scout
avdelningar ≈ **195 arrangemang per term**, each needing a key provisioned by
hand by an administrator. And there is no create-arrangemang endpoint at all,
so programmatic creation is impossible rather than merely unverified.

**Decision (2026-08-02): attendance is out of scope.** Do not build or key
weekly arrangemang. However, do not *foreclose* a single manually-keyed
arrangemang later — treat a project key as an optional per-deployment
capability in §12 and §13 so one camp check-in could be added without rework.
Build nothing project-scoped now. State the limitation plainly in the README.

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

**Status: substantially complete as of 2026-08-02.** Findings are folded into
§4, §5 and §11 above; the active-members capture, troop_id resolution and the
arrangemang spike are all done and decided.

Still outstanding. **Both are Phase 1 inputs, not Phase 2** — take them in one
sitting near the start of Phase 1:

- **Capture the `waiting` and `awaiting_approval` variants.** They back the
  read-only waiting-list and applicant views in Phase 1, and they are also the
  only way to observe non-active `status.raw_value` codes, which the Phase 2
  write mapping needs.
- **Re-capture after Höst 2026 is invoiced.** Invoicing is at least a month
  away, so **this cannot happen before the summer shift and must not block
  anything.** Decouple it:
  - The unpaid-dues feature works *today* against `prev_term` (Vår 2026),
    which is invoiced and carries real statuses. Build and validate the
    three-bucket logic against that.
  - `current_term` is `not_invoiced` for everyone, so `current_term_due_date`
    and `kid` parsing is unexercised and new payment codes are likely to appear
    once invoices exist.
  - Ship the payment views marked as validated against Vår 2026 only, and
    revisit after invoicing. The uppflyttning path does not depend on payment
    data at all, so nothing on the critical path waits for this.

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

**Recipients.** Scoutnet splits guardian contacts into dad and mum fields, and
coverage is uneven. **Email both**: send to `contact_email_dad` and
`contact_email_mum` where present, deduplicating case-insensitively in case the
family shares an address. Fall back to the member's own `contact_email` when
neither guardian address exists. If no address at all can be resolved, do not
fail silently — surface the member in the UI as unsendable so a human can act.
Show the resolved recipient list before sending, and record only the count and
timestamp in the message log, never the addresses.

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
- **Age brackets and uppflyttning flows are configuration, not code.** The full
  specification is §17. The active configuration must be viewable in the app.
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
- And for the observed API quirks specifically: `roles` parsed correctly when
  it arrives as `[]` rather than a dict, no `extra_info_` key surviving the
  client boundary, `not_invoiced` excluded from the unpaid list, an
  unrecognised payment code routed to the review bucket rather than either
  pile, and `prev_term_due_date` retaining both dates when a reminder shifted it

Additionally, before Phase 2 is considered complete, a **runbook** exists: how
to obtain a key, how to run a bulk operation, what to do when one fails
halfway, how to undo a run, and how to restore from a snapshot. Written for
whichever of the other two leaders would have to run it if the author were
unavailable — this is annual software and nobody will remember the details
eleven months later.

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
**83 members** in a full uppflyttning — four chunks at the default size of 25.
Use this as an order-of-magnitude check: a computed master set of 8 or 300 means
something is wrong.

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

The tool cannot create avdelningar. So the operator creates it in Scoutnet,
records its `cohort_year`, and refreshes; until then the transition shows as
pending with an explanation rather than silently producing an empty move set.

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
operator supplies its troop_id manually in config. When an elected target cannot
be resolved, say exactly this rather than failing obscurely.

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
projection, and identify which avdelning is oldest and therefore closest to
decommissioning. It must **never** be used to generate a finding or to move
anyone after the avdelning is formed. A member whose birth year differs from
their avdelning's cohort is expected, not an anomaly.

**4. `never_auto` — Utmanare and Rover**

No age-based moves, ever. An Utmanare sitting in an avdelning whose founding
cohort does not match their birth year is **not** a finding — do not interfere.

Utmanare only move when an avdelning is **decommissioned**, which is entirely
operator-initiated. Because the core is one specific year, the tool can *show*
which avdelning is oldest and therefore nearest retirement — but showing is the
limit. It never proposes a decommissioning and never initiates one. The operator
says "move everyone in avdelning X to Y" and the tool executes it as a normal
run: dry-run, snapshot, chunked, reconciled, undoable. Typical targets are
Ledare, since the members are 18+, or a Rover avdelning; the operator chooses,
there is no default.

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

Cross-check against the `current_term` label: `"Höst YYYY"` means N = YYYY,
`"Vår YYYY"` means N = YYYY − 1, since the cohort year is the year of the
autumn term. If the configured N and the derived N disagree, **refuse to compute
a master set** and say which two values conflict. This is a cheap guard against
the single most damaging silent error in the whole tool.

### Off-cohort members

A member whose birth year does not match any cohort of their current bracket —
say a 2014-born still in Spårare — is **flagged for review and excluded from the
automatic move set**. Never moved two brackets automatically.

These require manual intervention. List them prominently, and require the
operator to explicitly acknowledge the list before proceeding, so they cannot be
scrolled past. In Phase 2 that gate sits before a run can be confirmed; **in
Phase 1, where there is no run, it gates the changelist export** — and the
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
excluded from all age-based moves. Take the union of both signals per §11. A
scout who also holds an assistant-leader role elsewhere is flagged for review
rather than auto-moved.

### Yearly maintenance

Bracket birth years shift by one each year with N, so they must be **derived
from N**, not hardcoded as literal years in config. The table above is
illustrative for N = 2026; the config expresses ages, and the engine resolves
birth years. Adding a new Utmanare avdelning each year is the operator's job,
and the app should say so at the point the transition needs it.
