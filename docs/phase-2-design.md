# Phase 2 design — writes

**Status: proposed, for review. No application code exists yet.** Per
`HANDOVER.md` §5, this document is agreed before any Phase 2 code is written.

Authority order (`HANDOVER.md` §2): running code + live API > `CLAUDE.md` >
status docs. Section references below are to `CLAUDE.md` unless noted.

---

## 0. Scope of the first slice

**First slice: applying an uppflyttning** (`HANDOVER.md` §5). It is the most
finished feature — it already produces a reviewed, target-elected, override-aware
`MasterSet` (`src/karverktyg/uppflyttning/`) and a working reconciler
(`src/karverktyg/export/reconcile.py`).

**Explicitly deferred, not in this slice:**

- The **applicant-approval workflow**. It reads `awaiting_approval`, which
  reliably read-times-out for this kår (§4). Blocked until the timeout is
  characterised (`HANDOVER.md` §3). Do not build write paths on it.
- **Raising chunk size above 1.** A later, evidence-driven decision (§8).
- **Auto-send email.** Phase 1 is drafts only (§10); unchanged here.

Everything below is designed so the applicant workflow and decommissioning runs
reuse the same executor unchanged — they are different *intent producers* feeding
one execution engine.

---

## 1. Non-negotiable safety invariants (restated from `HANDOVER.md` §4)

Repeated here because these are the constraints that "went missing last time"
(`HANDOVER.md` §2). Treat any later disappearance of one as a merge error.

1. **Chunk size defaults to 1.** One member per request needs no atomicity
   guarantee. Nothing in code, docs or UI may assert or assume a multi-member
   chunk is all-or-nothing. *(Already corrected in `settings.py`; was `25`.)*
2. **Member allowlist during testing.** Config-supplied member numbers writes may
   touch; the executor refuses anything else, with a test asserting the refusal.
3. **Never fabricate an identifier for a negative test against production.**
   Malform the payload's *shape* instead, and only against the mock (hard rule 6).
4. `cancelled` stays unreachable (hard rule 3). Dry-run is the default (hard
   rule 4). No concurrent writes (hard rule 5). Snapshot before every bulk run,
   reconcile after, undo while the snapshot is retained. No personal data in
   Postgres (§9). No keys in the repo (hard rule 1).

---

## 2. Mode gate and the write client

The gate is enforced **at client construction** (§6), extending the existing
`build_client` in `src/karverktyg/scoutnet/client.py`:

- Add a `ReadWriteClient` subclassing `ReadOnlyClient` (inheriting the read
  surface + cache) and adding exactly one write method,
  `update_membership(payload: dict) -> dict`.
- `build_client` returns it **only** for `Mode.READ_WRITE`, and only after
  `require_live_credentials()` confirms an `update_membership_key` and
  `entity_id` are present. Today `build_client` raises `NotImplementedError` for
  `read_write`; that line is replaced.
- `FixtureClient` and `ReadOnlyClient` **keep zero write methods.** The existing
  `test_no_write_methods_on_read_clients` stays green unchanged — that is the
  point of the split.
- `ReadWriteClient` is displayed prominently in the UI whenever active (§6),
  surfaced via the capabilities payload (`read_write_active`, already present).

New setting: `update_membership_key: SecretStr | None` (§4 — per-endpoint key),
added to `require_live_credentials()` for `read_write`, and to
`endpoint_key_fingerprints()` for the capabilities page (§12).

`update_membership` posts to `/organisation/update/membership` with HTTP Basic,
same auth pattern as `_get`. It does **not** inherit the read retry policy: a
write is never auto-retried (§8). Any non-200 raises `ScoutnetError` carrying
status, body and any per-member error strings.

---

## 3. Status → write vocabulary

The write endpoint expects `status: "confirmed" | "waiting" | "cancelled"`; the
memberlist returns numeric `status.raw_value` (`Member.status_code`), observed
only as `"2"` = Aktiv (§4). The full mapping is one-third known.

**For the uppflyttning slice we need only `confirmed`.** Every mover is active,
so the re-read status is `"2"` and echoes back as `confirmed` (§8 "re-read before
write"; `HANDOVER.md` §5). Implementation:

- A single map `{"2": "confirmed"}`, with any other observed code raising rather
  than guessing — an unmapped status must never silently become `confirmed`.
- `"cancelled"` is **never** an output of this map and never a literal in the
  codebase (hard rule 3); a test asserts the string is unreachable.
- `waiting` / `cancelled` mappings are completed later, gated on the
  `waiting` / `awaiting_approval` captures (§7 Phase 0 leftovers) — not this slice.

**Re-read before write** (§8): immediately before building a chunk's payload,
fetch the member's *current* status live and echo it back unchanged; only
`troop_id` changes. `status` is required on every entry (§4).

---

## 4. Data model (Postgres, §9)

Three new tables. **All keyed on `member_no`; no names, addresses, personnummer,
email or phone** — a test already fails if a personal-data column appears in a
migration (§9), and it must keep passing.

### `write_run`
| column | type | notes |
|---|---|---|
| `id` | str (uuid) | run id |
| `kind` | str | `uppflyttning` \| `undo` \| `decommission` … |
| `cohort_year` | int? | for uppflyttning runs |
| `parent_run_id` | str? | set when `kind = undo` |
| `mode` | str | `dry_run` \| `execute` — a dry run is a first-class run |
| `state` | str | `pending` → `running` → `done` \| `failed` \| `aborted` |
| `snapshot_id` | str? | the pre-run snapshot (§ below) |
| `created_at` / `finished_at` | datetime | |

### `write_journal`
One row per intended per-member operation, written **before the first request**
(§8 "journal first").
| column | type | notes |
|---|---|---|
| `id` | int pk | |
| `run_id` | str fk | |
| `chunk_id` | int | monotonic within a run |
| `member_no` | str | |
| `intended_status` | str | `confirmed` for this slice |
| `intended_troop_id` | int | the only field that changes |
| `source_troop_id` | int? | observed prior state, for undo + display |
| `state` | str | `pending` → `in_flight` → `done` \| `failed` |
| `attempts` | int | |
| `error` | text? | per-member error string / HTTP body on failure |

### `snapshot` (metadata only)
The snapshot **file** lives on a mounted volume, never in Postgres/git/image (§8).
This table records its existence for listing and undo.
| column | type | notes |
|---|---|---|
| `id` | str | |
| `run_id` | str? | the run it was taken for |
| `path` | str | volume path |
| `size_bytes` | int | |
| `taken_at` | datetime | drives time-based retention (§8) |

### Bootstrap interaction (§9) — **important**
`db/bootstrap.py` clears `_UPPFLYTTNING_TABLES` (`uppflyttning_entry`,
`cohort_target`) on any migration because they are per-year scratch. **The write
tables are NOT scratch** — an in-flight run's journal must survive an ordinary
restart for resume-after-crash to work (§8). Therefore:

- `write_run` / `write_journal` / `snapshot` go into `_MEANINGFUL` (preserved
  across a rebuild), **not** into `_UPPFLYTTNING_TABLES`.
- Retention is by explicit, tested cleanup (§9), not by the migration wipe:
  a completed run's journal is deleted after a short window; snapshots purge on
  the time-based schedule (§8).

New alembic migration `0003_write_tables.py`, `down_revision = "0002"`, mirroring
the `0002` pattern.

---

## 5. The executor

`src/karverktyg/write/executor.py` (new package). Pure orchestration over the
`ReadWriteClient`; no Flask, no personal data retained beyond the live re-read.

### Lifecycle
1. **Allowlist check.** Refuse immediately if any `member_no` in the intent is
   not on the configured allowlist (§8, invariant 2). Test asserts refusal.
2. **One fresh live read**, reused for the next two steps (no double fetch).
3. **Snapshot.** From that read, capture every active member's placement +
   leadership to the volume *before the first request* (§8, `write_snapshot`; no
   personal data). A run cannot proceed if the snapshot write fails.
4. **Pre-flight drift check.** Diff the approved plan against that same live
   read and categorise each intended move:
   - **will_apply** — member still in the expected source avdelning, still active;
   - **already_applied** — already at the target (a no-op; the idempotency the
     resume path relies on);
   - **drifted** — somewhere *unexpected*, now a leader, status changed, or gone.

   Drift must be **acknowledged and the drifted members excluded** before
   execution, so a scout hand-moved in Scoutnet since the changelist was reviewed
   is surfaced up front rather than written over. Same diff shape as the post-run
   reconciler, run *before* instead of after.
5. **Journal.** Persist the full intended operation set (`state = pending`) before
   any request (§8 "journal first"). `source_troop_id` comes from the observed
   snapshot read, so undo reverses to what *was*, not to what the plan assumed.
6. **Chunk loop**, serial, one chunk at a time (hard rule 5), `chunk_delay_s`
   between chunks (default 1.0s), `chunk_size` default 1:
   - **re-read status** for the chunk's members immediately before writing and
     echo it back unchanged — only `troop_id` moves (§8); `state = in_flight`;
   - `POST`; on 200 mark `done`; on **any** non-200 / timeout / connection error /
     malformed body mark the chunk `failed`, set run `state = failed`, and
     **stop** — no auto-retry, no next chunk (§8 error handling).
7. **Reconcile** on completion (§ below).

### Dry-run (default, hard rule 4)
`mode = dry_run` runs the allowlist check, the live read and the pre-flight drift
check, then builds the exact per-chunk payloads it *would* `POST` — its output is
the drift report plus those payloads. It performs **no side effects**: no
snapshot file, no journal rows, no send. Snapshot and journal are execute-only
bookkeeping and don't affect *what* would be sent, so the preview stays faithful
while sharing the payload-building path with execute. Executing is a separate,
explicit confirmation; the actual Scoutnet write is the one guarded operation,
never a second implementation.

### Resume (§8)
After a crash the operator sees where the run stopped (journal state) and chooses
resume or abort. Resume continues from the first non-`done` chunk. **Re-applying
an already-applied change is a no-op** — this assumption is stated in the code and
verified in testing stage 2 (idempotency check). Progress is **server-side
state** polled by the frontend; closing the tab does not affect a run (§8).

---

## 6. Snapshots, reconciliation, undo

### Snapshots (§8) — implemented in step 4
- **Placement + leadership of every active member; no personal data.** Per
  member (`member_no`): `unit`/`troop_id`, `status`, `patrol_id`, and `leader_of`
  (troop-/group-scoped leader roles — patrol-scoped youth roles excluded). Those
  three writable fields are the whole restorable state; names, personnummer, DOB
  and addresses are never at risk, so they are never stored. Leadership is a
  belt-and-suspenders audit record. *(Supersedes the earlier "full memberlist
  incl. personnummer" design — §8/§9/Hard-rule-2 updated to match.)*
- **A self-describing file on the volume, not the DB** — so it survives a
  migration/rebuild, the exact case where you'd read an old state. The DB
  `snapshot` row (path/size/timestamp/run) is only the UI index. Written before
  the first request of any bulk run; a run cannot proceed if the write fails.
- Retention **time-based** (default 30 days), always keep at least the most
  recent regardless of age. Automatic purge on schedule + manual delete in UI.
- Listed with timestamp, size and originating run.
- API: `write_snapshot`, `list_snapshots`, `purge_snapshots`, `delete_snapshot`
  in `karverktyg.write.snapshot`.

### Reconciliation (§8, reuse existing)
After a run, re-fetch the memberlist and `reconcile(master, memberlist_after)`
(already compares against *intent*, not "target contains exactly the cohort" —
pre-existing target members are not drift, §17). Report all-applied or an
itemised list of members whose actual state differs from intent. Same code Phase 1
already ships.

### Undo (§8)
- An undo **is itself a run**: same allowlist, dry-run-first, chunking, journal,
  snapshot-before, reconcile-after. Not a privileged path.
- Inverse computed from **observed prior state** in the snapshot
  (`source_troop_id`), never from the intended change.
- If a member's current state already differs from what the run set, **flag and
  exclude** from the undo rather than overwriting someone's later edit. Show the
  full inverse set, including exclusions and why, before executing.
- Offered from the run detail view **only while the snapshot is retained**; once
  purged the UI says undo is unavailable rather than failing later.

---

## 7. Config knobs (§13)

Added to `Settings` (env-driven, pydantic-settings):

- `chunk_size: int = 1` ✅ *(already fixed)*
- `chunk_delay_s: float = 1.0` ✅
- `snapshot_retention_days: int = 30` ✅
- `snapshot_dir: Path` — mounted-volume path, required in `read_write`.
- `write_allowlist: list[str] = []` — member numbers writes may touch during
  testing (§8). Numbers only, never names (hard rule 6 / §8).
- `update_membership_key: SecretStr | None` — per-endpoint write key (§4).

k8s: write key via Secret, the rest via ConfigMap; a mounted PVC for
`snapshot_dir`; `SCOUTNET_MODE=read_write` set deliberately and visibly.

---

## 8. Testing progression (§8, operator approves each step)

**Stage 1 — mock Scoutnet server**, generated from the bundled schema, replaying
captured read data and validating request bodies. Exercise the full run here:
dry-run, execute, crash + resume, failed-chunk display, undo round trip.
- The **malformed-payload test lives here and only here** — a non-numeric member
  key or out-of-enum `status`, malforming *shape* only (invariant 3). It tests our
  error handling, not Scoutnet's behaviour; neither code nor docs may imply
  otherwise.
- Atomicity is **not** tested (chunk size 1; nothing depends on it, §8).

**Stage 2 — single member against the real API**, agreed in advance, allowlist
enforced (blast radius = 2 records). Prefer the **placeholder mail account**; the
operator's own record is the second choice (it carries the leader roles this tool
depends on). Three checks:
- **troop_id** — confirm `unit.raw_value` is the id `update/membership` accepts.
  The last outstanding assumption that can block a real run (§5, `HANDOVER.md` §3).
- **Round trip** — move A→B, reconcile, undo, reconcile again.
- **Idempotency** — repeat the same write, confirm no-op (resume depends on it).

Verify each by hand in the Scoutnet UI, not only through the tool.

**Stage 3 — a reviewed list**, displayed in full and approved before execution.

---

## 9. Tests this slice must add (§16 DoD)

New, on top of the existing suite (must stay green, offline):

- Write methods **absent** on `FixtureClient`/`ReadOnlyClient`, **present** only
  on `ReadWriteClient` (extend `test_client_modes.py`).
- `read_write` refused without `update_membership_key`; allowed with it.
- Allowlist refusal for an off-list `member_no`.
- No concurrent writes (chunks strictly serial).
- Snapshot written before the first request (assert ordering).
- Resume after crash re-applies from the failed chunk; already-done is a no-op.
- Reconciliation reporting (reuse existing).
- Undo excludes an externally-changed member.
- `cancelled` unreachable — string absent from the write path.
- No personal-data column in the `0003` migration (existing heuristic test).

---

## 10. Open items owned by the operator (not code, `HANDOVER.md` §3)

None block this slice, but flagging for tracking:

- **Rotate the exposed `group/memberlist` key.** Do first, unrelated to phase.
- Probe the three undocumented endpoints; characterise the `awaiting_approval`
  timeout. These gate the **applicant** workflow, not uppflyttning-apply.

---

## 11. Proposed build order

1. Branch `phase-2` off `phase-1`. ✅
2. Settings + `ReadWriteClient` + mode gate + capabilities wiring + tests. ✅
3. `0003` migration + ORM models + bootstrap `_MEANINGFUL` wiring + tests. ✅
4. Snapshot writer + retention + tests. ✅
5. Executor, split into two reviewable commits:
   - **5a** ✅ — executor core: allowlist → live read → {snapshot + pre-flight
     drift} → journal → serial chunk loop (dry-run default, per-chunk status
     re-read) → status→`confirmed` mapping → resume. Tested against a fake
     in-process `ReadWriteClient` double. No network.
   - **5b** ✅ — the stage-1 **mock Scoutnet server** whose request contract is
     read from the vendored spec (via `pyyaml`, dev-only), driven through
     `httpx.MockTransport`: full-run integration over the real `ReadWriteClient`
     incl. crash/resume/failure paths and the shape-only malformed-payload test.
     Fresh-read wiring (client `fresh=` cache bypass) landed here, closing the
     5a reconcile/re-read caveat.
6. Undo + reconcile wiring + tests. ✅ — undo is a run (`kind="undo"`,
   `parent_run_id`); inverse from the journal's observed `source_troop_id`; the
   drift check excludes externally-changed members; gated on snapshot retention.
7. Flask write endpoints + server-side progress + frontend blade:
   - **7a** ✅ — `writes_bp`: dry-run (sync) + execute/resume/undo as background
     runs via a `RunManager` (single-active-run guard, local + DB), server-side
     status polling, snapshot list/delete, off-cohort ack gate, allowlist
     pre-check, all gated to `read_write`. Tests inject a read+write fixture
     double (no network). Client `transport` seam + `create_app(client=...)`.
   - **7b** ✅ — the "Utför" frontend blade: gated in non-write modes; dry-run
     drift report; off-cohort ack gate; confirm-to-execute that **locks the
     blade's controls** (a second click can't fire another request — the backend
     already refuses concurrent runs with 409, this is UX); server-side progress
     polling; run-status card with resume-on-failure and undo (preview →
     execute → poll); run history + snapshot list/delete; prominent `read_write`
     banner. Verified end-to-end in a browser against a read_write fixture double.
8. Runbook (§16) before the slice is called done.

Stage 2 (real single-member) happens only after 1–7 are green and the operator
approves — and after the key rotation.
