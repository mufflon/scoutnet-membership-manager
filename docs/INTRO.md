# scoutnet-membership-manager in a page

A small internal tool for a Swedish scoutkår. It reads member data from Scoutnet
and helps leaders with the recurring termly work — see the composition, chase
unpaid dues, work the waiting list, keep the förtroende register, spot data
problems — and apply the yearly **uppflyttning** (moving each cohort up an
åldersgrupp) through a careful, undoable write path.

## Try it in one command

```bash
uv sync
uv run scoutnet-membership-manager serve --mode fixture --port 8000    # then open http://localhost:8000
```

Fixture mode needs no API key and no database: it runs against a completely
fabricated demo memberlist (`fixtures/memberlist.demo.json`). There is a
container image too — `docker run -e SCOUTNET_MODE=fixture -p 8000:8000 …` (see
the README).

## The mental model

- **Modes** (`SCOUTNET_MODE`): `fixture` (demo, no creds), `read_only` (live, no
  writes), `read_write` (live, the guarded write path). The mode is enforced when
  the API client is built, not just in the UI.
- **Config is tiny and optional.** The national åldersgrupp ladder (Spårare …
  Rover, with Utmanare 15–19) is in code. A kår's config is one JSON file listing
  only its **avdelningar** — each with an optional meeting `weekday` and an
  optional explicit move `target`. Everything else (which bracket a member is in,
  troop ids, the kår's group id) is read live from the data. With **no config at
  all**, avdelningar are inferred and moves are chosen per person.
- **Uppflyttning routing** is one universal rule per moving cohort: an explicit
  `target` → the same-weekday avdelning in the next bracket → the sole avdelning of
  the next bracket → otherwise the operator picks per person. Making a brand-new
  Utmanare avdelning is a runtime "designate a target" action (the tool moves
  scouts into a group you created in Scoutnet; the API can't create groups).
- **No personal data is ever stored.** Findings, snapshots and journals key on
  `member_no` and placement only; the committed fixture is fabricated.

## Where to look next

- **`README.md`** — setup, modes, deploy, the config reference.
- **`CLAUDE.md`** — the authoritative spec (numbered sections referenced from the
  code as `§N`). Start here to understand *why* the code is shaped as it is.
- **`docs/examples/`** — example kår configs and a description of the demo data.
- **`docs/runbook.md`** — the annual write/uppflyttning runbook.
