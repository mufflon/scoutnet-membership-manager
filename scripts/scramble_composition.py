#!/usr/bin/env python3
"""Obscure per-avdelning composition in a scrubbed fixture (privacy; CLAUDE.md §7).

The scrubbed fixture (see scrub_capture.py) is safe on *personal* data, but it
still reveals the real number of scouts and leaders in each avdelning — and for a
fixture we publish, that composition is itself sensitive. This throwaway spike
takes an already-scrubbed fixture and perturbs every avdelning's head-count so the
real numbers can't be read back:

  1. Duplicate + modify: a random subset of members is cloned, each clone a fresh
     fake identity (new member_no, re-faked name/ssno/address/email/phone) in the
     SAME avdelning — produced by re-running the scrubber's own faking, so no new
     PII logic and no real data is ever touched.
  2. Delete: a random subset of the (now larger) set is removed.

Each avdelning draws its own duplicate- and delete-rate, so counts move up and
down by different, unpredictable amounts. The published fixture stays realistic in
shape while no per-avdelning total — and no kår total — matches reality.

Deterministic (fixed seed) so the committed fixture is reproducible. Operates only
on already-scrubbed input, so it cannot leak real personal data; it re-runs the
scrubber's PII scan on the result as a backstop. Stdout is counts only.

Usage:
    python3 scripts/scramble_composition.py IN.json [-o OUT.json] [--seed N]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from random import Random

# Both scripts live in scripts/; reuse the scrubber's faking + PII scan.
import scrub_capture as sc

# Per-avdelning rates are drawn from these ranges. Wide enough that direction and
# magnitude vary per avdelning; the real count is not recoverable from the result.
DUP_RATE = (0.10, 0.40)
DEL_RATE = (0.10, 0.40)


def _avdelning_key(member: dict) -> str:
    unit = member.get("unit") or {}
    return str(unit.get("raw_value") or unit.get("value") or "")


def _clone(member: dict, new_no: str, rng: Random) -> dict:
    """A fresh fake identity in the same avdelning: re-run the scrubber's faking
    with a new member_no. Structural fields (unit, roles, dates) are preserved."""
    ctx = {"rng": rng, "new_member_no": new_no, "female": sc.is_female(member), "dob": None}
    order = sorted(member, key=lambda f: sc.POLICY.get(f) != "DOB")  # DOB before SSNO
    scrubbed = {f: sc.scrub_field(f, member[f], ctx) for f in order}
    return {f: scrubbed[f] for f in member}  # restore original field order


def scramble(fixture: dict, seed: int = 20260804) -> dict:
    data = fixture.get("data")
    if not isinstance(data, dict):
        raise sc.ScrubError("'data' is missing or not an object")

    members = list(data.items())  # (member_no, record)
    next_no = max((int(no) for no, _ in members if no.isdigit()), default=1_000_000) + 1

    # Per-avdelning rates, drawn once and deterministically. Iterate in SORTED
    # order — a set's iteration order varies with PYTHONHASHSEED and would make the
    # output non-reproducible.
    rate_rng = Random(f"rates::{seed}")
    avdelningar = sorted({_avdelning_key(m) for _, m in members})
    dup_rate = {a: rate_rng.uniform(*DUP_RATE) for a in avdelningar}
    del_rate = {a: rate_rng.uniform(*DEL_RATE) for a in avdelningar}

    # Pass 1 — duplicate + modify.
    out: list[tuple[str, dict]] = list(members)
    for i, (_, m) in enumerate(members):
        if Random(f"dup::{seed}::{i}").random() < dup_rate[_avdelning_key(m)]:
            new_no = str(next_no)
            next_no += 1
            out.append((new_no, _clone(m, new_no, Random(f"clone::{seed}::{i}"))))

    # Pass 2 — delete (over originals + clones).
    kept = [
        (no, m)
        for j, (no, m) in enumerate(out)
        if Random(f"del::{seed}::{j}::{no}").random() >= del_rate[_avdelning_key(m)]
    ]

    result: dict[str, object] = {"data": dict(kept)}
    if fixture.get("labels") is not None:
        result["labels"] = fixture["labels"]
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="Scramble per-avdelning composition in a fixture.")
    ap.add_argument("input", type=Path, help="scrubbed fixture .json")
    ap.add_argument("-o", "--output", type=Path, help="output path (default: overwrite input)")
    ap.add_argument("--seed", type=int, default=20260804)
    args = ap.parse_args()

    try:
        fixture = json.loads(args.input.read_bytes())
        before = len(fixture.get("data", {}))
        out = scramble(fixture, seed=args.seed)
        sc.verify_no_pii(out)  # backstop: the result must still carry no real PII
    except sc.ScrubError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    dest = args.output or args.input
    dest.write_text(
        json.dumps(out, ensure_ascii=False, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    after = len(out["data"])
    print(f"Scrambled {args.input.name} -> {dest}")
    print(f"Members: {before} -> {after} (per-avdelning counts perturbed; PII scan clean)")


if __name__ == "__main__":
    main()
