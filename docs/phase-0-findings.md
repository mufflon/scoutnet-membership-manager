# Phase 0 findings

**Source:** one live `GET /group/memberlist` (active variant), captured 2026-08-02
for Scoutkåren Finn (group/entity `1025`). **371 active members, 49 data fields.**
All statements below are derived from the *scrubbed* fixture
(`fixtures/memberlist.scrubbed.json`). No personal data appears in this document;
counts are aggregates.

Machine tokens (`raw_value`, `role_key`, numeric ids) are what code should key
on — the human `value`/`label` strings are Swedish and may change.

---

## Part A — memberlist field semantics

### Response shape

- `data` is an object keyed by `member_no` (a **string**). A member appears
  **exactly once** — a dict cannot hold duplicate keys, so there is no
  duplicate-row case to handle. `labels` maps each field to its Swedish column
  name.
- Every field is wrapped as `{value}` or `{value, raw_value}`. `raw_value` is
  present on the *coded* fields — `status, group, unit, unit_type, unit_role,
  group_role, patrol, sex, current_term, prev_term`, and some `extra_info_*` —
  and absent elsewhere. Carry unknown fields through untouched (§4).

### Terms and payment — the important one (§7)

The design here is non-obvious and easy to get wrong:

- **The term NAME lives in the `label`, not the value.** `current_term` →
  label `"Höst 2026"`; `prev_term` → label `"Vår 2026"`.
- **The field VALUE is the payment status for that term:**
  - `current_term.raw_value`: all `not_invoiced` (Höst 2026 not yet billed).
    `current_term_due_date` is therefore empty for everyone — no due date exists
    until an invoice is issued.
  - `prev_term.raw_value` (Vår 2026): `paid` 343, `unpaid_overdue_reminded` 24,
    `not_invoiced` 3, `paid_partial_credit` 1.
  - `prev_term_due_date` (368/371) is a date; some render as
    `"2026-04-30 (2026-02-28)"` — current due date with the original in
    parentheses after a reminder shifted it.
- **Unpaid-dues logic (§5)** = `{current,prev}_term.raw_value` **not in**
  `{paid, paid_partial_credit}`. Key on `raw_value`, not the Swedish `value`.
- **Canonical term identity:** the memberlist gives payment-status-per-term, *not*
  a `term_id`. For `term_id`/`term_label` use `/organisation/group` (§4) and join
  on the label if needed.

### unit / unit_type

- `unit.value` = avdelning **name**; `unit.raw_value` = a stable **numeric ID**
  (5 digits). 14 distinct avdelningar including a `Ledare` avdelning. **2 members
  have no `unit`** — the §11 "no avdelning" case, present in live data.
- `unit_type` (6 values, with codes): `Spårarscouter`(2), `Upptäckarscouter`(3),
  `Äventyrarscouter`(4), `Utmanarscouter`(5), `Roverscouter`(6), `Annat`(7).
  The `Ledare` avdelning carries `unit_type = Annat`. These are the standard
  Scouterna age sections and will anchor the (still-unspecified) uppflyttning
  brackets — no brackets are invented here.

### roles — leadership, fully decoded

- `roles.value` is `[]` for **276** plain members and an **object** for **95**
  role-holders. The empty case is a PHP `[]`-for-empty-assoc-array quirk; **code
  must accept both `list` and `dict`** or it will silently miss every leader.
- Structure:
  ```
  roles.value = {
    "troop": { "<troop_id>": { "<role_id>": {role_id, role_key, role_name} } },
    "group": { "1025":       { "<role_id>": {role_id, role_key, role_name} } }
  }
  ```
- The `troop` keys are **the same numeric troop_ids as `unit.raw_value`**; the
  `group` key is `1025` (the kår). Confirmed across the set (e.g. Vikingarna
  `10164`, Rockorna `16926` appear identically in both places).
- `role_key` is the stable token to match on — `leader`, `other_leader`,
  `assistant_leader`, `member_registrar`, `material_responsible`,
  `nomination_committee`, … — never `role_name`.
- `group_role` and `unit_role` are **derived flat views** of `roles`: the `value`
  is a comma-joined list of role names, the `raw_value` a comma-joined list of
  role ids (e.g. `"1243,24"`). Treat `roles` as the source of truth and these as
  convenience columns.
- **Leader identification (§5/§11):** a member holds a `troop`-scope role with a
  leader-class `role_key`, and/or their `unit == "Ledare"` (120 members sit in the
  Ledare avdelning). This is the set excluded from age-based moves.

### Guardian / contact fields (§7)

Scoutnet uses a **dad/mum split**, not the `contact_telephone_home` §4 guessed at:

- Names: `contact_fathers_name`, `contact_mothers_name`
- Email: `contact_email_dad`, `contact_email_mum`
- Mobile: `contact_mobile_dad`, `contact_mobile_mum`
- Landline: `contact_telephone_dad`, `contact_telephone_mum`
- Member's own: `contact_mobile_phone`, **`contact_home_phone`** (note: *not*
  `contact_telephone_home`), `contact_work_phone`, `contact_email`,
  `contact_alt_email`, `contact_scouterna-email`

Coverage is uneven (mothers' contacts more populated than fathers'); this is
data-quality territory (§11), not an error.

### Multi-membership (§7, explicit ask)

- One entry per member (dict key) — never appears twice.
- `unit` is **single-valued** → one *primary* avdelning.
- Involvement in **several** avdelningar shows up in `roles.troop` as multiple
  `troop_id` keys (30 of the 95 role-holders carry two scope-entries).
- **Practical scope of the §11 check (resolved with the operator):** `roles` only
  captures *functional/leadership* memberships, so a plain scout enrolled in two
  avdelningar with *no* role would be invisible here. But that is not a realistic
  case — per the operator, a scout being an ordinary scout in two avdelningar
  effectively does not happen; the real multi-avdelning case is a scout who is also
  a leader (e.g. *assisterande ledare*) in another avdelning. That is a **role**,
  so it **is** visible via `roles.troop`. Net: the §11 "member in >1 avdelning"
  finding is computable from `unit` + `roles.troop` keys and reliably catches the
  cases that actually occur; the endpoint's blindness to plain dual membership does
  not bite. Leaders are excluded from moves as usual, so an assistant-leader-
  elsewhere is flagged for review, not auto-moved.

### Other fields

- `status`: all `Aktiv` (`raw_value` numeric `"2"`). **Vocabulary mismatch to
  handle:** the write endpoint (`/organisation/update/membership`) expects string
  `status` values `confirmed|waiting|cancelled`, not the memberlist's numeric
  codes. Map deliberately in Phase 2.
- `sex`: `Man`(1) / `Kvinna`(2) / `Okänt`(0).
- `group.raw_value = 1025` — the kår/entity id, matching the auth entity id.
- `patrol.raw_value` = numeric `patrol_id` (39 distinct, present 232/371).
- `extra_info_83/90/91/92` = the kår's own custom questions. **Redacted** in the
  fixture (could be dietary/medical/consent); coded `raw_value` answers kept where
  present. `contact_leader_interest` = a flag, value `"Ja"` (31 members).
- **Label-only, no data this call:** `current_term_due_date`, `kid`, `section`,
  `address_3`. Sparse: `address_2`, `address_co`, `nickname`.

---

## Part B — troop_id resolution proposal

**Need:** `/organisation/update/membership` requires an integer `troop_id`; §4/§5
assumed the memberlist exposes only the avdelning *name*, so `troop_id` would need
a project-scoped key.

**Finding:** that assumption is out of date. The memberlist already carries the
numeric troop_id, corroborated **twice** in the same response:

1. `unit.raw_value` — the member's primary avdelning id.
2. `roles.value.troop.<troop_id>` — the same id space, agreeing field-for-field.

A stable **name → troop_id map for all 14 avdelningar** is derivable from a single
memberlist call, no extra key required.

| Option | Cost | Risk |
|---|---|---|
| **1 (recommended)** — use `unit.raw_value` as `troop_id`; build the name→id map from the memberlist; **empirically verify one id against the write endpoint** before any Phase 2 write | zero extra keys, no project scope | that `unit.raw_value` ≠ the update endpoint's `troop_id`. Low — `roles.troop` uses the same ids — but §8 mandates an empirical atomicity/write check anyway, so this rides along for free |
| 2 — config map of avdelning name → troop_id read off Scoutnet admin URLs | manual, drifts | redundant now; keep only as a cross-check / fallback |
| 3 — one project key + `/project/get/groups` to read the group model's `troops` | needs an arrangemang key | heaviest; only if Option 1 fails verification |

**Adopted: Option 1** (operator, 2026-08-02), gated by the §8 empirical write
check. Record the verified mapping in the repo. **No write code until that check
passes** (§5, §8).

---

## Part C — arrangemang / attendance spike (analysis only, no code)

**Question:** can the tool track meeting attendance, and can meetings be created
programmatically?

**Findings** (spec §4/§5 + this capture):

- Scoutnet models attendance as *arrangemang* = `project`, **one project per
  meeting**, each behind its **own** project-scoped key ("one key per
  arrangemang", §4). Keys are per-endpoint, permanent until regenerated, and the
  available endpoint list is set by a system administrator.
- **Key math.** A term runs ~14–18 weekly meetings. Finn has ~13 scout avdelningar
  (excluding Ledare). One arrangemang per meeting ⇒ **~15 × 13 ≈ ~195 arrangemang
  per term**, each needing its own project key — ≈ 195 keys/term, ≈ 390/year, every
  one provisioned by an admin by hand. Even a *single* avdelning is ~15 keys/term.
  Operationally infeasible to key.
- **No create endpoint.** The documented surface is `GET /project/get/{participants,
  groups,questions}` and `POST /project/checkin` — **there is no
  create-arrangemang endpoint.** Programmatic creation of next year's meetings is
  impossible with the documented API. Confirmed, not merely unverified.
- Reading attendance needs the specific per-meeting project key; there is no
  group-level list of a kår's projects and no bulk read.

| Option | What it buys | Cost |
|---|---|---|
| A — declare attendance **out of scope**, per §5 | keeps the tool honest; no dead project-scoped code | none |
| **B (kept open)** — support a **single, manually-keyed** arrangemang (e.g. one camp) for check-in, opt-in, only if a concrete need appears | one bounded feature, one key | build only when needed; not now |
| C — track attendance **outside** Scoutnet in our own store | full control | large build, duplicates Scoutnet, out of Phase 0/1 scope |

**Decision (operator, 2026-08-02): A as the default scope, but keep the B door
open.** Bulk/weekly attendance stays out of scope — we do **not** build or key ~195
arrangemang per term. But the design should not *foreclose* a single,
manually-keyed arrangemang check-in: treat a project key as an optional,
per-deployment capability (§12 capabilities page, §13 config) so one can be added
later without rework. Build nothing project-scoped now. Keep the value in the
feasible read-only set (unpaid dues, waiting list, uppflyttning candidates,
data-quality findings) plus the Phase 1 changelist export and reconciliation, and
state the blocker plainly in the README limits.

---

## Open decisions for the operator

1. **troop_id:** adopt Option 1 (`unit.raw_value`), with the empirical
   write-endpoint check deferred to the Phase 2 gate?
2. **Arrangemang:** confirm Option A (out of scope), or keep the single-arrangemang
   check-in door (Option B) open in the design?
3. **Multi-membership:** add "can a plain scout hold two avdelningar?" to the list
   of things to confirm against the register?
