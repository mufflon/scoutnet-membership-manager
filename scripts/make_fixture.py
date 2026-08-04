#!/usr/bin/env python3
"""
Fabricate a complete demo memberlist fixture — no capture, no API key.

Generates an entirely synthetic memberlist in the Scoutnet capture shape, so the
tool can run in fixture mode (and be shared) with zero real data provenance. There
is no scrubbing step because there is no real data to begin with: every member,
name, age and head-count is invented here.

Members are placed in the avdelningar of a config (default: the bundled config),
with ages that fit each åldersgrupp, a handful of leaders in the Ledare avdelning,
and a few deliberate edge cases (a scout with no avdelning, a minor sitting in
Ledare, an off-cohort scout) so the findings and uppflyttning blades have
something to show.

Deterministic (seeded). Reuses the scrubber's fakers so values look right; needs
only the stdlib plus the project's config model (run from the repo root).

Usage:
    python3 scripts/make_fixture.py [--config config/....json] [-o OUT.json] [--seed N]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from random import Random

import scrub_capture as sc  # sibling spike: name/ssno/phone/email fakers

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from karverktyg.config.models import Bracket, KarConfig, unit_type_code  # noqa: E402

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "docs" / "examples" / "finn.json.example"
DEMO_GROUP_ID = "1025"  # the kår's group id, carried on group-scoped förtroende roles
REF_YEAR = 2026  # ages are as-of this cohort year
# Rough per-bracket avdelning sizes (min, max) for a believable demo kår.
SIZE = {
    Bracket.SPARARE: (10, 22),
    Bracket.UPPTACKARE: (10, 24),
    Bracket.AVENTYRARE: (14, 34),
    Bracket.UTMANARE: (5, 14),
    Bracket.ROVER: (2, 6),
    Bracket.ANNAT: (14, 26),
}


def _dob(age: int, rng: Random) -> str:
    return date(REF_YEAR - age, rng.randint(1, 12), rng.randint(1, 28)).isoformat()


def _member(
    no: str,
    unit: str | None,
    troop_id: int | None,
    code: int | None,
    age: int,
    rng: Random,
    *,
    roles: object = None,
    paid: bool = True,
) -> dict:
    female = rng.random() < 0.5
    dob = _dob(age, rng)
    dob_iso = date.fromisoformat(dob)
    rec: dict[str, object] = {
        "member_no": {"value": no},
        "first_name": {"value": rng.choice(sc.FIRST_NAMES)},
        "last_name": {"value": rng.choice(sc.LAST_NAMES)},
        "ssno": {"value": sc.fake_ssno("000000-0000", dob_iso, rng, female)},
        "date_of_birth": {"value": dob},
        "status": {"raw_value": "2", "value": "Aktiv"},
        "sex": {"raw_value": "2" if female else "1", "value": "Kvinna" if female else "Man"},
        "address_1": {"value": f"{rng.choice(sc.STREETS)} {rng.randint(1, 89)}"},
        "postcode": {"value": sc.fake_postcode("000 00", rng)},
        "town": {"value": rng.choice(sc.TOWNS)},
        "country": {"value": "Sverige"},
        "email": {"value": sc.fake_email(rng, no, "medlem")},
        "contact_mobile_phone": {"value": f"070{rng.randint(1000000, 9999999)}"},  # valid SE mobile
        "roles": roles if roles is not None else {"value": []},
        # The current (autumn) term is not yet invoiced for anyone — current_payment()
        # reads NOT_BILLED across the kår, as in a real mid-season capture.
        "current_term": {"raw_value": "not_invoiced", "value": "Ej fakturerad"},
    }
    if unit is not None:
        rec["unit"] = {"raw_value": str(troop_id), "value": unit}
        rec["unit_type"] = {"raw_value": str(code), "value": unit}
        # The previous term is billed; most paid, some still outstanding (the dues chase).
        rec["prev_term"] = {
            "raw_value": "paid" if paid else "unpaid_overdue_reminded",
            "value": "Betald" if paid else "Obetald (påmind)",
        }
        rec["prev_term_due_date"] = {"value": "2026-02-28"}
    return rec


def _group_roles(group_id: str, specs: list[tuple[int, str, str]]) -> dict:
    by_role = {str(rid): {"role_id": rid, "role_key": rk, "role_name": rn} for rid, rk, rn in specs}
    return {"value": {"group": {str(group_id): by_role}}}


def _patrol_role(patrol_id: int) -> dict:
    return {
        "value": {
            "patrol": {
                str(patrol_id): {
                    "2": {"role_id": 2, "role_key": "leader", "role_name": "Patrulledare"}
                }
            }
        }
    }


# The förtroende register (§18): one group-scoped role each. role_key matches the
# classifier — "leader" is the (constitutional) kårordförande and sorts first;
# board seats, then committee/other (an unfamiliar key passes through, sorted
# last), then the ombud delegate.
FORTROENDE = [
    (1, "leader", "Kårordförande"),
    (2, "vice_leader", "Vice ordförande"),
    (3, "treasurer", "Kassör"),
    (4, "secretary", "Sekreterare"),
    (5, "board_member", "Ledamot"),
    (6, "scout_challenge_rep", "Utmanarscoutrepresentant"),
    (24, "material_responsible", "Materielansvarig"),
    (25, "key_responsible", "Nyckelansvarig"),
    (121, "nomination_committee", "Valberedning"),
    (130, "district_voter", "Ombud distriktsstämma"),
]


def _leader_roles(troop_id: int) -> dict:
    return {
        "value": {
            "troop": {
                str(troop_id): {
                    "3": {"role_id": 3, "role_key": "other_leader", "role_name": "Ledare"}
                }
            }
        }
    }


def fabricate(config: KarConfig, seed: int = 20260804) -> dict:
    rng = Random(f"fixture::{seed}")
    troop = {
        a.name: 20001 + i for i, a in enumerate(sorted(config.avdelningar, key=lambda a: a.name))
    }
    scout_avd = [
        a for a in config.avdelningar if a.bracket in SIZE and a.bracket is not Bracket.ANNAT
    ]
    ledare = next((a for a in config.avdelningar if a.bracket is Bracket.ANNAT), None)

    data: dict[str, dict] = {}
    no = 100000

    def age_for(b: Bracket) -> int:
        rule = config.rule(b)
        if rule.age_min is not None and rule.age_max is not None:
            return rng.randint(rule.age_min, rule.age_max)
        return rng.randint(19, 25)  # rover / annat: young adults

    # Scout members per avdelning. ~1 in 4 is the "oldest cohort" — one year over
    # the bracket, so they form the moving cohort the uppflyttning blade acts on.
    for a in scout_avd:
        lo, hi = SIZE[a.bracket]
        rule = config.rule(a.bracket)
        for _ in range(rng.randint(lo, hi)):
            no += 1
            mover = rule.age_max is not None and rng.random() < 0.25
            age = rule.age_max + 1 if mover else age_for(a.bracket)
            data[str(no)] = _member(
                str(no),
                a.name,
                troop[a.name],
                unit_type_code(a.bracket),
                age,
                rng,
                paid=rng.random() < 0.85,
            )

    # Ledare avdelning: adults, some of them leaders of a scout avdelning.
    if ledare is not None:
        lo, hi = SIZE[Bracket.ANNAT]
        for _ in range(rng.randint(lo, hi)):
            no += 1
            roles = None
            if scout_avd and rng.random() < 0.6:
                roles = _leader_roles(troop[rng.choice(scout_avd).name])
            data[str(no)] = _member(
                str(no),
                ledare.name,
                troop[ledare.name],
                unit_type_code(Bracket.ANNAT),
                rng.randint(25, 60),
                rng,
                roles=roles,
            )
        # Edge case: one minor sitting in Ledare (underage_in_ledare finding).
        no += 1
        data[str(no)] = _member(
            str(no), ledare.name, troop[ledare.name], unit_type_code(Bracket.ANNAT), 15, rng
        )
        # The förtroende register (§18): a board/committee/ombud member for each
        # group-scoped role, so the Förtroendeuppdrag blade has a full roster.
        for role_id, role_key, role_name in FORTROENDE:
            no += 1
            data[str(no)] = _member(
                str(no),
                ledare.name,
                troop[ledare.name],
                unit_type_code(Bracket.ANNAT),
                rng.randint(30, 60),
                rng,
                roles=_group_roles(DEMO_GROUP_ID, [(role_id, role_key, role_name)]),
            )

    # A few patrol-scoped youth roles (Patrulledare) — never counted as leaders (§11).
    if scout_avd:
        a = scout_avd[0]
        for p in range(3):
            no += 1
            m = _member(
                str(no),
                a.name,
                troop[a.name],
                unit_type_code(a.bracket),
                age_for(a.bracket),
                rng,
                roles=_patrol_role(500 + p),
            )
            m["patrol"] = {"raw_value": str(500 + p), "value": f"Patrull {p + 1}"}
            data[str(no)] = m

    # Edge cases: two members with no avdelning at all (no_avdelning finding).
    for _ in range(2):
        no += 1
        data[str(no)] = _member(str(no), None, None, None, rng.randint(8, 12), rng)

    # Edge case: an off-cohort scout (age well outside the bracket window).
    if scout_avd:
        a = scout_avd[0]
        no += 1
        data[str(no)] = _member(str(no), a.name, troop[a.name], unit_type_code(a.bracket), 16, rng)

    # A few free-text extra_info answers, so the parser's extra_info path is exercised.
    for key in list(data)[:5]:
        data[key]["extra_info_90"] = {"value": "Ja", "raw_value": "1"}

    # Scoutnet carries the two term *names* as the current_term / prev_term labels
    # (the parser reads them from here); the rest are ordinary column labels.
    labels = {
        "member_no": "Medlemsnr.",
        "first_name": "Förnamn",
        "last_name": "Efternamn",
        "ssno": "Personnummer",
        "date_of_birth": "Födelsedatum",
        "status": "Status",
        "sex": "Kön",
        "unit": "Avdelning",
        "unit_type": "Enhetstyp",
        "roles": "Roller",
        "address_1": "Adress",
        "postcode": "Postnummer",
        "town": "Ort",
        "country": "Land",
        "email": "E-post",
        "contact_mobile_phone": "Mobil",
        "patrol": "Patrull",
        "extra_info_90": "Övrig info",
        "current_term": "Höst 2026",
        "prev_term": "Vår 2026",
    }
    return {"data": data, "labels": labels}


def main() -> None:
    ap = argparse.ArgumentParser(description="Fabricera en helt påhittad demo-fixture.")
    ap.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG, help="kårkonfig för avdelningarna"
    )
    ap.add_argument("-o", "--output", type=Path, default=Path("fixtures/memberlist.demo.json"))
    ap.add_argument("--seed", type=int, default=20260804)
    args = ap.parse_args()

    config = KarConfig.model_validate(json.loads(args.config.read_bytes()))
    out = fabricate(config, seed=args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Fabricated {len(out['data'])} members -> {args.output} (no capture, no API key)")


if __name__ == "__main__":
    main()
