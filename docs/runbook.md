# Runbook — writing changes back to Scoutnet

For the leader who has to run this if the author is unavailable. This is annual
software: you will not remember the details eleven months later, so follow the
steps rather than reconstructing them.

Everything here concerns the **write path** — moving scouts between avdelningar in
Scoutnet. Reading, the changelist export and reconciliation all work without any
of this, and are always available as the manual alternative.

Section references like §8 point at `CLAUDE.md`.

---

## 0. The one-line mental model

A run is: **allowlist → snapshot → journal → one member at a time → reconcile.**

Dry-run is the default and changes nothing. Every run can be undone while its
snapshot is retained. If anything looks wrong, stop — nothing is lost by stopping.

---

## 1. One-time setup

1. **Get the write key.** In Scoutnet: **Din kår → Webbkoppling → generate a key
   for `organisation/update/membership`**. It is a *separate* key from the read
   keys — every endpoint has its own. Never commit it, never paste it anywhere,
   never read it into an AI session.
2. **Check the keys work.** **API-koll** probes each configured key with a real
   read and shows green when all are healthy. If a key has been regenerated in
   Scoutnet since the deployment was last configured, this is where you find out —
   an old key stops working the moment it is replaced.
3. **Configure the deployment** — see section 2.

## 2. Configuration for a write deployment

Secret for the keys, ConfigMap for the rest:

| Variable | Value |
|---|---|
| `SCOUTNET_MODE` | `read_write` (set deliberately; the UI shows a banner while active) |
| `SCOUTNET_UPDATE_MEMBERSHIP_KEY` | the write key from step 1.1 |
| `SCOUTNET_WRITE_ALLOWLIST` | JSON list of member numbers writes may touch. Keep it **as small as the job allows**. Empty means nothing can be written. |
| `SCOUTNET_SNAPSHOT_DIR` | a mounted volume path for snapshot files (required) |
| `SCOUTNET_CHUNK_SIZE` | leave at **1**. Do not raise without evidence (§8). |
| `SCOUTNET_CHUNK_DELAY_S` | `1.0` is fine |
| `SCOUTNET_SNAPSHOT_RETENTION_DAYS` | `30` default; undo is available while a run's snapshot is retained |

If a required key is missing, the app **fails loudly at startup**. That is
intended — a silent half-configured write deployment would be worse.

Keys and the allowlist are deployment config only. They are never entered in the
UI (hard rule 7).

## 3. Smoke test before the annual run

Do this **every year, before moving eighty-odd children**, not just the first
time. It takes two minutes and it confirms nothing has shifted upstream since you
last ran it.

`unit.raw_value` is the id `update/membership` accepts — verified on 2026-08-03 by
moving one member Ledare (`10172`) → Hajarna (`10155`) through the tool and undoing
it, each step checked by hand in the Scoutnet UI. That is a fact about Scoutnet
today, not a guarantee about Scoutnet next August.

Use the **placeholder mail account** — not a real scout, and not your own leader
account, since that is the one your access depends on. Put its `member_no` on the
allowlist, note its current avdelning, then:

```bash
scoutnet-membership-manager verify-write --member <placeholder_no> --to <target_troop_id>
scoutnet-membership-manager verify-write --member <placeholder_no> --to <target_troop_id> --execute --idempotency
```

The first command is a dry run and writes nothing. Check in the Scoutnet UI that
the placeholder actually landed in the target avdelning, then undo with the printed
command:

```bash
scoutnet-membership-manager verify-write --undo-run <run_id> --execute
```

`--idempotency` re-applies the same move once and confirms Scoutnet treats it as a
no-op. The crash-resume path in section 5 relies on that being true.

**Verify the patrull write before the first real uppflyttning.** Only `troop_id`
is live-proven (2026-08-03); `patrol_id` is documented but has never round-tripped
against live Scoutnet, and an uppflyttning now sets it automatically. Prove it once
the same way, by adding `--patrol <target_patrol_id>` to the move, then confirm by
hand that the placeholder landed in that patrull, and undo:

```bash
scoutnet-membership-manager verify-write --member <placeholder_no> --to <target_troop_id> --patrol <target_patrol_id>
scoutnet-membership-manager verify-write --member <placeholder_no> --to <target_troop_id> --patrol <target_patrol_id> --execute
```

The same tests are available in the UI under **Verifiera skrivning** (read_write
only): it shows the allowlist, lets you dry-run then execute a single-member move
(with an optional patrull), and offers undo.

## 4. Running an uppflyttning

Review first, on the **Uppflyttning** blade: elect the Äventyrare→Utmanare target,
set any per-member overrides ("stay a year", a different target), and look at
anyone marked **utanför årskull** (off-cohort). Pick an övergång at the top and the
blade is scoped to it; **Exportera berörda scouter** then hands you an Excel contact
roster for exactly that selection — medlemsnummer, current avdelning, name, and
member + guardian phone/email — for warning families ahead of the shift. It is
computed live and ignores your saved overrides, so it always reflects who is
currently affected, not a decision you might still change. Then go to the **Utför**
blade:

1. **Förhandsgranska (torrkörning).** Sends nothing. Shows, per member: *kommer
   att flyttas*, *redan på plats* (skipped, no-op), or *avviker* (skipped — someone
   changed them in Scoutnet since you reviewed). Read this carefully; it is the
   last cheap opportunity to notice a problem.
2. If there are **off-cohort** members, tick the acknowledgement box. You cannot
   execute until you confirm you reviewed them.
3. **Utför (skriv till Scoutnet).** Confirm the dialog. Controls lock, a snapshot
   is taken, and members are written **one at a time**. Progress updates live; you
   can close the tab, and the run continues on the server.
4. When it says **Klar**, the moves are done.

Order-of-magnitude sanity check: a full Finn uppflyttning is roughly **83 members**
— about 28 Spårare, 32 Upptäckare, 23 Äventyrare. A computed set of 8 or 300 means
something is wrong. Stop and investigate before executing.

If you would rather not write at all, the **changelist Excel export** produces the
same set for manual entry in Scoutnet, and the reconciliation afterwards will tell
you whether every move landed.

## 5. When a run fails halfway

The run **stops on the first error** and does not continue or retry. You will see
the HTTP status, the member numbers involved, the intended change, any per-member
error text, and the response body.

- Read the error. **401** means the key or entity id is wrong — likely a rotation
  that did not reach the config. **400** usually names the offending member. A
  timeout or connection error means Scoutnet was unreachable.
- Fix the cause if there is one.
- Then choose on the run's status card:
  - **Återuppta (resume)** — continues from where it stopped. Completed members
    are skipped, and re-applying an applied move is a no-op, so resuming is safe.
  - or leave it and **undo** (section 6) to roll back the part that applied.
- After resume completes, reconciliation confirms every intended member reached
  its target, or lists the ones that did not.

A partially applied run is **accepted, not a disaster.** The journal records
exactly where it stopped and reconciliation catches the remainder.

## 6. Undoing a run

From the run's status card, **Ångra körningen (förhandsgranska)** shows the inverse
set — every member this run moved, put back where they were *before* it. Then
**Utför ångra** executes the reversal as a normal run, with its own snapshot,
journal and reconciliation.

- Undo reverses only members **this run** moved, back to their **observed prior**
  avdelning. It never touches anyone else.
- If a member has since been moved elsewhere by hand in Scoutnet, the pre-flight
  check marks them *avviker* and **excludes** them. Undo will not overwrite
  someone's later edit. The preview shows exactly who is excluded and why.
- Undo is available **only while the run's snapshot is retained.** Once the
  snapshot is purged — by age or manual delete — the UI says undo is unavailable.
  It says so up front, not at the moment you try.

## 7. Where everything lives

If something goes awry, these are the three places that hold the record of what
happened. Find them before you start improvising.

| What | Where | Survives a database loss? |
|---|---|---|
| **Before-state** — every member's placement immediately before a run | JSON files on the mounted volume at `SNAPSHOT_DIR`, one per run, keyed by `member_no` | **Yes.** A file on a PVC, deliberately out of band |
| **Intent and outcome** — what each member was meant to change to, and whether it applied | Postgres: `write_run`, `write_journal`, and a `snapshot` index row | **No** |
| **Current truth** | Live Scoutnet | n/a |

To look at them, from the `scoutnet-membership-manager` namespace:

```bash
# snapshot files
kubectl -n scoutnet-membership-manager exec deploy/scoutnet-membership-manager -- ls -la "$SCOUTNET_SNAPSHOT_DIR"

# the journal
kubectl -n scoutnet-membership-manager exec -it deploy/<postgres> -- psql -U <user> -d <db> \
  -c 'select * from write_run order by id desc limit 10;'
```

Deployment and object names may have moved; check `scripts/k8s-up.sh` and the
config file rather than trusting the exact strings above. The **Utför** blade lists
snapshots with timestamp and size, which is the easier route when the app is up.

Note the asymmetry, because it decides what you can do:

- **Snapshot files survive a database rebuild.** If Postgres is gone you still know
  where everyone was before the run — enough to reconstruct by comparing against
  the live memberlist.
- **The journal does not.** If Postgres is gone you lose what was *intended*, and
  with it the in-app undo. You would be reconstructing from before-state versus
  live-state instead.
- Retention bites: snapshots purge after `SNAPSHOT_RETENTION_DAYS` (30 by default),
  and undo dies with the snapshot. If a run needs preserving beyond that — a
  disputed change, something a board wants to see — **copy the snapshot file off
  the volume**. Nothing does that for you.

## 8. Restoring from a snapshot (last resort)

Snapshots hold **no personal data** — only, per `member_no`: avdelning
(`troop_id`), `status`, `patrol_id`, and which troops or group they lead.

**What a snapshot does and does not protect you from.** It covers the three fields
this tool can write, and nothing else. So it protects against **this tool's**
mistakes — a bad run, a wrong target, a move that should not have happened. It does
**not** protect against arbitrary damage to the register: a mistaken hand edit in
Scoutnet, a Scoutnet fault, or anyone else's integration. Those touch fields the
snapshot never recorded.

This is a deliberate trade — the alternative was keeping personnummer for 371
people on a volume for a month, to guard against damage this tool cannot cause. But
do not read "snapshot" as "backup of the register". It is not one. Scoutnet remains
the system of record.

You normally never touch these files. **Undo (section 6) is the supported path.**
Use a snapshot directly only if the database or journal is gone and undo is
unavailable:

1. Find the run's snapshot file in `SNAPSHOT_DIR` (section 7). Plain JSON, keyed by
   `member_no`.
2. It records each member's avdelning *before* the run. Compare against the live
   memberlist to see what changed.
3. Put the affected members back to their prior `troop_id`, either by hand in the
   Scoutnet UI or through a fresh allowlisted run once the tool is healthy.

## 9. Hard safety rules — do not work around these

- **Chunk size is 1.** One member per request. Nothing assumes a multi-member
  request is all-or-nothing, because that has deliberately never been verified.
  Raising it is an evidence-based decision, not a convenience.
- **The allowlist bounds the blast radius.** A member not on it is refused before
  anything happens.
- **`cancelled` is unreachable.** The tool only ever writes `confirmed`. It cannot
  cancel a membership.
- **One run at a time.** A second run while one is active is refused.
- **Never enter a key in the UI**, and never read one into an AI session or paste
  it into a chat, ticket or screenshot. If a key is exposed anywhere at all,
  regenerate it in Scoutnet immediately — keys are permanent until regenerated —
  and record that you did.
