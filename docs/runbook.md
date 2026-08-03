# Runbook — Phase 2 writes (uppflyttning)

For the leader who has to run this if the author is unavailable. Annual software:
you will not remember the details eleven months later, so follow the steps.

Everything here is about the **write path** (moving scouts between avdelningar in
Scoutnet). Reading, changelist export and reconciliation work without any of this.

---

## 0. The one-line mental model

A run is: **allowlist → snapshot → journal → one member at a time → reconcile.**
Dry-run is the default and changes nothing. Every run can be undone while its
snapshot is retained. If anything looks wrong, stop — nothing is lost.

---

## 1. Before the first real run (once)

1. **Rotate the exposed memberlist key** if not already done (it was pasted into
   an AI chat during development). Regenerate on the Webbkoppling page and update
   the deployment config; confirm **API-koll** goes green.
2. **Get the write key.** In Scoutnet: **Din kår → Webbkoppling → generate a key
   for `organisation/update/membership`**. It is a *separate* key from the read
   keys. Never commit or paste it anywhere.
3. **Verify `troop_id` against the write endpoint (stage 2).** This is the last
   unproven assumption: we believe `unit.raw_value` is the id `update/membership`
   accepts, but that is a read surface. Before any bulk run, do a single move on
   the **placeholder mail account** (not a real scout, not your own leader
   account), then check it by hand in the Scoutnet UI. Only proceed once this is
   confirmed. Record the verified mapping.

## 2. Configuration for a write deployment

Set these (Secret for the key, ConfigMap for the rest):

| Variable | Value |
|---|---|
| `SCOUTNET_MODE` | `read_write` (set deliberately; the UI shows a banner while active) |
| `SCOUTNET_UPDATE_MEMBERSHIP_KEY` | the write key from step 1.2 |
| `SCOUTNET_WRITE_ALLOWLIST` | JSON list of member numbers writes may touch. **During testing keep this tiny** (the placeholder account, maybe your own). Empty = nothing may be written. |
| `SCOUTNET_SNAPSHOT_DIR` | a mounted volume path for snapshot files (required) |
| `SCOUTNET_CHUNK_SIZE` | leave at **1**. Do not raise without evidence (§8). |
| `SCOUTNET_CHUNK_DELAY_S` | `1.0` is fine |
| `SCOUTNET_SNAPSHOT_RETENTION_DAYS` | `30` default; undo is available while a run's snapshot is retained |

If a required key is missing the app **fails loudly at startup** — that is intended.

## 3. Running an uppflyttning

Do the review first, on the **Uppflyttning** blade: elect the Äventyrare→Utmanare
target, set any per-member overrides ("stay a year", different target), and note
anyone **utanför årskull** (off-cohort). Then go to the **Utför** blade:

1. **Förhandsgranska (torrkörning).** This sends nothing. It shows, per member:
   *kommer att flyttas*, *redan på plats* (skipped, no-op), or *avviker* (skipped
   — someone changed them in Scoutnet since you reviewed). Read this carefully.
2. If there are **off-cohort** members, tick the acknowledgement box — you cannot
   execute until you have confirmed you reviewed them.
3. **Utför (skriv till Scoutnet).** Confirm the dialog. The controls lock, a
   snapshot is taken, and members are written **one at a time**. Progress updates
   live; you can close the tab — the run continues on the server.
4. When it says **Klar**, the moves are done. The changelist Excel export remains
   available as the manual alternative and produces the same set.

Order-of-magnitude sanity check: a full Finn uppflyttning is roughly **83 members**
(~28 Spårare, ~32 Upptäckare, ~23 Äventyrare). A computed set of 8 or 300 means
something is wrong — stop and investigate before executing.

## 4. When a run fails halfway

The run **stops on the first error** and does not continue or retry. You will see
the HTTP status, the member numbers in the failed chunk, the intended change, any
per-member error text, and the response body.

- Read the error. A 401 means the key/entity-id is wrong. A 400 usually names the
  offending member. A timeout/connection error means Scoutnet was unreachable.
- Fix the cause if there is one (e.g. key, connectivity).
- Then choose on the run's status card:
  - **Återuppta (resume)** — continues from the failed chunk. Chunks already done
    are skipped; re-applying an applied move is a no-op, so resume is safe.
  - or leave it and **undo** (section 5) to roll back the part that applied.
- After resume completes, the reconciliation confirms every intended member
  reached its target, or lists the ones that did not.

A partially-applied run is **accepted, not a disaster**: the journal records
exactly where it stopped, and reconciliation catches the remainder.

## 5. Undoing a run

From the run's status card, **Ångra körningen (förhandsgranska)** shows the inverse
set — every member this run moved, put back to where they were *before* it. Then
**Utför ångra** executes the reversal as a normal run (its own snapshot, journal,
reconcile).

- Undo only reverses members **this run** moved, back to their **observed prior**
  avdelning. It never touches anyone else.
- If a member has since been moved elsewhere (by hand in Scoutnet), the pre-flight
  check marks them *avviker* and **excludes** them — undo will not overwrite a
  later edit. The preview shows exactly who is excluded and why.
- Undo is available **only while the run's snapshot is retained**. Once the
  snapshot is purged (age, or manual delete), the UI says undo is unavailable.

## 6. Restoring from a snapshot (last resort)

Snapshots are **placement reference files** on the mounted volume (`SNAPSHOT_DIR`),
one per run, taken before the first write. They contain **no personal data** —
only, per `member_no`: their avdelning (`troop_id`), `status`, `patrol_id`, and
which troops/group they lead. They survive a database migration on purpose.

You normally never touch these — **undo (section 5) is the supported path**. Use
the file directly only if the database/journal is gone and undo is unavailable:

1. Find the snapshot file for the run in `SNAPSHOT_DIR` (listed in the Utför blade
   with timestamp and size). It is plain JSON, keyed by `member_no`.
2. It tells you each member's avdelning *before* the run. Compare against the live
   memberlist to see what changed.
3. Re-key the affected members back to their prior `troop_id` **by hand in the
   Scoutnet UI**, or via a fresh, allowlisted run once the tool is healthy.

The snapshot cannot restore names/personnummer/addresses — the tool never changes
those, so they were never at risk and Scoutnet still holds them.

## 7. Hard safety rules (do not work around these)

- **Chunk size is 1.** One member per request; no run assumes a multi-member
  request is all-or-nothing. Raising it is a deliberate, evidence-based decision.
- **Allowlist bounds the blast radius** during testing — a member not on it is
  refused before anything happens.
- **`cancelled` is unreachable.** The tool only ever writes `confirmed` for
  uppflyttning; it cannot cancel a membership.
- **One run at a time.** A second run while one is active is refused.
- **If a key is exposed anywhere** (chat, screenshot, ticket), regenerate it in
  Scoutnet immediately — keys are permanent until regenerated — and record it.
