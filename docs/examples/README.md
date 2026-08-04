# Config examples

## The config file (`karverktyg.json`)

All non-secret configuration is one committed file at the repo root,
`karverktyg.json` (the API keys live in `apikeys.conf`). Its shape:

```jsonc
{
  "schema_version": 1,          // config-file format version (verifiable vs the schema)
  "mode": "read_only",          // fixture | read_only | read_write
  "cohort_year": 2026,          // uppflyttning year N (omit to derive from the live term)
  "entity_id": "1025",          // the kår's id / API username (not a secret)
  "kar": {                      // the kår itself — see the examples below
    "name": "Scoutkåren Finn",
    "avdelningar": [
      { "name": "Hajarna", "bracket": "sparare", "weekday": 0, "target": "Kämparna" }
    ]
  }
}
```

Environment variables (`SCOUTNET_*`) override any field, so k8s / `docker run` can
set them. Each **avdelning** takes a `bracket`
(sparare/upptackare/aventyrare/utmanare/rover/annat), an optional meeting `weekday`
(0 = Monday … 6 = Sunday, drives the same-weekday move), and an optional explicit
move `target`. Everything else — which bracket a member is in, troop ids, the kår's
group id — is read live from the member data; the national åldersgrupp ladder is in
code. The `.json.example` files below are just the **`kar` block** (validated by
`../karverktyg.schema.json`). With **no config at all** the tool still runs:
avdelningar are inferred from the data and moves fall back to selecting a target per
person when there is more than one candidate.

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
