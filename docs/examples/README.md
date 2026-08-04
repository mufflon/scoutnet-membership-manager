# Config examples

A kår's config is a single JSON file (see `../karverktyg.schema.json` for the full
schema). It lists only your **avdelningar** — each with a `bracket`, an optional
meeting `weekday` (0 = Monday … 6 = Sunday), and an optional explicit move
`target`. Everything else — which age bracket a member is in, troop ids, the kår's
group id — is read live from the member data, and the national åldersgrupp ladder
(Spårare … Rover) is built into the code.

To use one, copy it to `karverktyg.json` (gitignored) and point the app at it with
`SCOUTNET_CONFIG_PATH`, or build your own with `python3 scripts/make_config.py`.
With **no config at all** the tool still runs: avdelningar are inferred from the
data and moves fall back to the universal rule (select a target per person when
there is more than one candidate).

## The examples

- **`finn.json.example`** — Scoutkåren Finn as shipped: three Spårare and three
  Upptäckare avdelningar on Monday/Tuesday/Wednesday, one Äventyrare avdelning, and
  three Utmanare avdelningar built fresh each year. The weekdays drive the
  Spårare → Upptäckare move (Monday Spårare → the Monday Upptäckare).
- **`minimal.json.example`** — one avdelning per bracket. Because each next bracket
  has exactly one avdelning, every move auto-resolves with no weekday needed.
- **`finn-persistent.json.example`** — Finn with a single **standing** Utmanare
  avdelning (`Finnfararna`) that scouts move *into* each year, shown two ways: the
  sole-candidate rule would route to it automatically, and here Vikingarna also
  names it explicitly via `target`.

## What the demo data shows

Run the app in fixture mode (`karverktyg serve --mode fixture`) and it loads
`../../fixtures/memberlist.demo.json` — a **completely fabricated** memberlist
(built by `scripts/make_fixture.py`; no real person appears anywhere). Looking at
it you'll see ~180 invented members spread across the Finn avdelningar: scouts
whose ages fit each åldersgrupp plus an "oldest cohort" a year over (the ones the
Uppflyttning blade proposes to move), a Ledare avdelning with a handful of leaders,
a full förtroende register (ordförande, kassör, committee roles, an ombud), a few
patrol-leader youths, and deliberate edge cases — a scout with no avdelning and a
minor sitting in Ledare — so the Anmärkningar and Uppflyttning blades have
something to act on. Names, personnummer, addresses and phone numbers are all fake;
the per-avdelning head-counts are invented, not any real kår's.
