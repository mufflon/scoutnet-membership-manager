#!/usr/bin/env python3
"""Phase 0 scrubber: turn a raw memberlist capture into a committable fixture.

Throwaway spike script (CLAUDE.md §7). Stdlib only. Reads a raw capture written
by capture_memberlist.py, replaces every piece of personal data with realistic
fakes, and writes a fixture that is safe to commit (Hard rule #2).

Design:
  * Every field has an EXPLICIT policy below. A field with no policy is a hard
    error — we never pass an unclassified field through, because it might be PII.
  * Structural / categorical fields (status, unit, unit_type, roles, terms, ...)
    keep their REAL values: they are not personal data and the findings and the
    troop_id analysis need them.
  * Personal fields are faked format-preservingly: the fake has the same shape
    (length, separators, valid Luhn for personnummer) as the original, so value
    shapes survive. date_of_birth keeps its real YEAR (age cohort matters for
    uppflyttning) but a faked month/day; ssno is kept consistent with it.
  * member_no is remapped to a synthetic number of the SAME digit length.
  * Free text we cannot vet (note, extra_info_* answers) is redacted; coded
    raw_value answers are kept.
  * Deterministic: the same capture yields a byte-identical fixture (idempotent).
  * After building, a PII scan walks every preserved/redacted field. If a
    personnummer, email or phone pattern survives where it should not, the run
    ABORTS rather than committing a leak.

Stdout is counts and field names only — never a value.

Usage:
    python3 scripts/scrub_capture.py [CAPTURE_PATH] [-o OUTPUT_PATH] [--scramble]

With no CAPTURE_PATH it uses the newest captures/*.raw.json. Output defaults to
fixtures/memberlist.scrubbed.json. ``--scramble`` additionally obscures each
avdelning's head-count (see scramble_composition.py) — use it for a fixture that
will be published, so the committed data reveals no real per-avdelning composition.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from random import Random

ROOT = Path(__file__).resolve().parent.parent
CAPTURES_DIR = ROOT / "captures"
DEFAULT_OUTPUT = ROOT / "fixtures" / "memberlist.scrubbed.json"

# --- Field policies -------------------------------------------------------
# PRESERVE      keep real value+raw_value (structural / categorical, not PII)
# NAME          fake given/sur/guardian name
# SSNO          fake Swedish personnummer, valid Luhn, consistent with DOB
# DOB           fake date, real year, faked month/day, original format
# STREET        fake street line (also c/o lines, which carry a person name)
# POSTCODE      fake postcode, same shape
# TOWN          fake town
# EMAIL         fake email
# PHONE         fake phone, same shape
# REDACT        replace value with a placeholder; keep raw_value if present
# AVATAR        replace url with a placeholder
# MEMBER_NO     remap to a synthetic number of the same length
POLICY = {
    "member_no": "MEMBER_NO",
    "first_name": "NAME",
    "last_name": "NAME",
    "nickname": "NAME",
    "contact_fathers_name": "NAME",
    "contact_mothers_name": "NAME",
    "ssno": "SSNO",
    "date_of_birth": "DOB",
    "address_1": "STREET",
    "address_2": "STREET",
    "address_3": "STREET",
    "address_co": "NAME",
    "postcode": "POSTCODE",
    "town": "TOWN",
    "email": "EMAIL",
    "contact_email": "EMAIL",
    "contact_alt_email": "EMAIL",
    "contact_scouterna-email": "EMAIL",
    "contact_email_dad": "EMAIL",
    "contact_email_mum": "EMAIL",
    "contact_home_phone": "PHONE",
    "contact_work_phone": "PHONE",
    "contact_mobile_phone": "PHONE",
    "contact_mobile_dad": "PHONE",
    "contact_mobile_mum": "PHONE",
    "contact_telephone_dad": "PHONE",
    "contact_telephone_mum": "PHONE",
    "note": "REDACT",
    "extra_info_83": "REDACT",
    "extra_info_90": "REDACT",
    "extra_info_91": "REDACT",
    "extra_info_92": "REDACT",
    "avatar_url": "AVATAR",
    "avatar_updated": "PRESERVE",
    # Structural / categorical — real values kept:
    "status": "PRESERVE",
    "group": "PRESERVE",
    "group_role": "PRESERVE",
    "unit": "PRESERVE",
    "unit_type": "PRESERVE",
    "unit_role": "PRESERVE",
    "patrol": "PRESERVE",
    "roles": "PRESERVE",
    "sex": "PRESERVE",
    "current_term": "PRESERVE",
    "prev_term": "PRESERVE",
    "prev_term_due_date": "PRESERVE",
    "current_term_due_date": "PRESERVE",
    "created_at": "PRESERVE",
    "confirmed_at": "PRESERVE",
    "country": "PRESERVE",
    "contact_leader_interest": "PRESERVE",
}

# Fields whose faked value legitimately looks like PII — exempt from the scan.
FAKED_POLICIES = {"NAME", "SSNO", "DOB", "STREET", "POSTCODE", "TOWN", "EMAIL", "PHONE"}

FIRST_NAMES = [
    "Alva",
    "Björn",
    "Cornelia",
    "David",
    "Ebba",
    "Filip",
    "Greta",
    "Hugo",
    "Iris",
    "Jonas",
    "Klara",
    "Love",
    "Maja",
    "Noel",
    "Olga",
    "Pelle",
    "Ronja",
    "Sixten",
    "Tuva",
    "Uno",
    "Vera",
    "William",
]
LAST_NAMES = [
    "Andersson",
    "Bergström",
    "Cederqvist",
    "Dahl",
    "Ekström",
    "Forsberg",
    "Gustafsson",
    "Holmberg",
    "Isaksson",
    "Johansson",
    "Karlsson",
    "Lindqvist",
    "Möller",
    "Nyström",
    "Öberg",
    "Persson",
]
TOWNS = ["Lund", "Dalby", "Södra Sandby", "Genarp", "Veberöd", "Staffanstorp"]
STREETS = ["Exempelgatan", "Provvägen", "Testallén", "Fiktivgränd", "Scoutstigen"]


class ScrubError(Exception):
    pass


# --- Faking helpers -------------------------------------------------------


def luhn_check_digit(digits: str) -> str:
    total = 0
    for i, ch in enumerate(digits):
        n = int(ch) * (2 if i % 2 == 0 else 1)
        total += n if n < 10 else n - 9
    return str((10 - total % 10) % 10)


def parse_date(value: str) -> tuple[date, str]:
    """Return (parsed_date, strftime_format) or raise. Format is preserved."""
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            from datetime import datetime

            return datetime.strptime(value, fmt).date(), fmt
        except ValueError:
            continue
    raise ScrubError(f"unrecognised date format (len {len(value)})")


def fake_dob(value: str, rng: Random) -> str:
    real, fmt = parse_date(value)
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)
    return date(real.year, month, day).strftime(fmt)


def fake_ssno(value: str, dob_iso: date, rng: Random, female: bool | None) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) not in (10, 12):
        raise ScrubError(f"unrecognised ssno shape ({len(digits)} digits)")
    sep = "-" if "-" in value else ("+" if "+" in value else "")
    yymmdd = dob_iso.strftime("%y%m%d")
    # Third birth digit parity encodes sex; align when we can tell.
    parities = [0, 2, 4, 6, 8] if female else [1, 3, 5, 7, 9]
    if female is None:
        parities = list(range(10))
    birth = f"{rng.randint(0, 9)}{rng.randint(0, 9)}{rng.choice(parities)}"
    core = yymmdd + birth
    full10 = core + luhn_check_digit(core)
    body, tail = full10[:-4], full10[-4:]
    if len(digits) == 12:
        body = dob_iso.strftime("%Y%m%d") + full10[6:-4]
    return f"{body}{sep}{tail}"


def fake_phone(value: str, rng: Random) -> str:
    """Keep every non-digit and the first digit; randomise the rest."""
    out, seen = [], False
    for ch in value:
        if ch.isdigit():
            if not seen:
                out.append(ch)
                seen = True
            else:
                out.append(str(rng.randint(0, 9)))
        else:
            out.append(ch)
    return "".join(out)


def fake_postcode(value: str, rng: Random) -> str:
    return re.sub(r"\d", lambda _: str(rng.randint(0, 9)), value)


def fake_email(rng: Random, new_member_no: str, tag: str) -> str:
    return f"{tag}{new_member_no}@example.org"


def is_female(member: dict) -> bool | None:
    raw = member.get("sex") or {}
    token = f"{raw.get('value', '')}{raw.get('raw_value', '')}".lower()
    if any(t in token for t in ("kvinn", "flick", "female", "girl")) or token in ("2", "k", "f"):
        return True
    if any(t in token for t in ("man", "pojk", "male", "boy")) or token in ("1", "m"):
        return False
    return None


# --- Core scrub -----------------------------------------------------------


def scrub_field(field: str, wrapper: dict, ctx: dict) -> dict:
    policy = POLICY.get(field)
    if policy is None:
        raise ScrubError(f"no policy for field {field!r}")
    if not isinstance(wrapper, dict):
        raise ScrubError(f"field {field!r} is {type(wrapper).__name__}, expected object")

    rng: Random = ctx["rng"]
    out = dict(wrapper)  # preserve exactly the same wrapper keys

    if policy == "PRESERVE":
        return out
    if policy == "AVATAR":
        if "value" in out:
            out["value"] = "https://example.org/avatar/placeholder.png"
        return out
    if policy == "REDACT":
        if "value" in out:
            out["value"] = "[redacted]"
        return out  # raw_value (option code), if present, is kept
    if policy == "MEMBER_NO":
        out["value"] = ctx["new_member_no"]
        return out

    # Remaining policies replace a scalar value (and raw_value if present).
    if policy == "NAME":
        given = field in ("first_name", "nickname")
        fake = rng.choice(FIRST_NAMES) if given else rng.choice(LAST_NAMES)
        if field in ("contact_fathers_name", "contact_mothers_name", "address_co"):
            fake = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
    elif policy == "STREET":
        fake = f"{rng.choice(STREETS)} {rng.randint(1, 89)}"
    elif policy == "TOWN":
        fake = rng.choice(TOWNS)
    elif policy == "POSTCODE":
        fake = fake_postcode(str(out.get("value", "")), rng)
    elif policy == "EMAIL":
        tag = {"contact_email_dad": "far", "contact_email_mum": "mor"}.get(field, "medlem")
        fake = fake_email(rng, ctx["new_member_no"], tag)
    elif policy == "PHONE":
        fake = fake_phone(str(out.get("value", "")), rng)
    elif policy == "DOB":
        fake = fake_dob(str(out.get("value", "")), rng)
        ctx["dob"], _ = parse_date(fake)
    elif policy == "SSNO":
        dob = ctx.get("dob")
        if dob is None:  # order-independent: derive from real dob if seen later
            dob = date(2010, 1, 1)
        fake = fake_ssno(str(out.get("value", "")), dob, rng, ctx["female"])
    else:  # pragma: no cover
        raise ScrubError(f"unhandled policy {policy}")

    for k in ("value", "raw_value"):
        if k in out:
            out[k] = fake
    return out


def build_member_no_map(keys: list[str]) -> dict[str, str]:
    """Synthetic member numbers, same digit length, deterministic, unique."""
    per_len: Counter[int] = Counter()
    mapping: dict[str, str] = {}
    for key in sorted(keys):
        L = len(key)
        base = 10 ** (L - 1) if L > 1 else 0
        mapping[key] = str(base + per_len[L])
        per_len[L] += 1
    return mapping


def scrub(capture: dict) -> dict:
    data = capture.get("data")
    labels = capture.get("labels")
    if not isinstance(data, dict):
        raise ScrubError("'data' is missing or not an object")

    unknown = {f for m in data.values() if isinstance(m, dict) for f in m} - set(POLICY)
    if unknown:
        raise ScrubError(
            "unclassified field(s) — refusing to guess, add a policy: " + ", ".join(sorted(unknown))
        )

    no_map = build_member_no_map(list(data))
    out_data: dict[str, dict] = {}
    for i, (old_no, member) in enumerate(sorted(data.items())):
        rng = Random(f"scoutnet-fixture::{i}")
        ctx = {
            "rng": rng,
            "new_member_no": no_map[old_no],
            "female": is_female(member),
            "dob": None,
        }
        # DOB before SSNO so the personnummer stays consistent with it.
        order = sorted(member, key=lambda f: POLICY.get(f) != "DOB")
        scrubbed = {f: scrub_field(f, member[f], ctx) for f in order}
        # restore original field order
        scrubbed = {f: scrubbed[f] for f in member}
        out_data[no_map[old_no]] = scrubbed

    out = {"data": out_data}
    if labels is not None:
        out["labels"] = labels  # column labels are not personal data
    return out


# --- Verification ---------------------------------------------------------

PII_PATTERNS = {
    "personnummer": re.compile(r"(?<!\d)(?:19|20)?\d{6}[-+]?\d{4}(?!\d)"),
    "email": re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+"),
    "mobile": re.compile(r"(?:\+46|0)\s?7\d[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}"),
}

# Per-field exemptions from a SPECIFIC pattern, with a reason. Only for fields
# whose classification is confirmed correct and that structurally collide with a
# heuristic. Not blanket trust — every other pattern still applies to the field.
SCAN_EXEMPT = {
    # avatar_updated is a 10-digit Unix timestamp, which matches the "any 10
    # digits" personnummer heuristic. It is a modification time, not a person.
    "avatar_updated": {"personnummer"},
}


def verify_no_pii(out: dict) -> None:
    """Scan preserved/redacted fields for surviving PII. Faked fields are
    exempt (their fakes legitimately look like PII). Reports field + pattern,
    never a value."""
    hits: Counter[str] = Counter()

    def walk(node: object, field: str):
        exempt = SCAN_EXEMPT.get(field, ())
        if isinstance(node, str):
            for name, pat in PII_PATTERNS.items():
                if name in exempt:
                    continue
                if pat.search(node):
                    hits[f"{field}:{name}"] += 1
        elif isinstance(node, dict):
            for v in node.values():
                walk(v, field)
        elif isinstance(node, list):
            for v in node:
                walk(v, field)

    for member in out["data"].values():
        for field, wrapper in member.items():
            if POLICY.get(field) in FAKED_POLICIES:
                continue
            walk(wrapper, field)

    if hits:
        detail = ", ".join(f"{k} (×{n})" for k, n in hits.most_common())
        raise ScrubError(
            "PII-shaped values survived in fields that should have none — "
            "a field is misclassified. Aborting rather than committing a leak: " + detail
        )


# --- CLI ------------------------------------------------------------------


def newest_capture() -> Path:
    caps = sorted(CAPTURES_DIR.glob("*.raw.json"))
    if not caps:
        raise ScrubError(f"no *.raw.json in {CAPTURES_DIR}. Run the capture first.")
    return caps[-1]


def main() -> None:
    ap = argparse.ArgumentParser(description="Scrub a memberlist capture into a fixture.")
    ap.add_argument("capture", nargs="?", type=Path, help="capture .raw.json (default: newest)")
    ap.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument(
        "--scramble",
        action="store_true",
        help="also obscure per-avdelning composition (delete + duplicate) so the "
        "committed fixture does not reveal the real head-count of any avdelning",
    )
    args = ap.parse_args()

    try:
        src = args.capture or newest_capture()
        capture = json.loads(Path(src).read_bytes())
        out = scrub(capture)
        verify_no_pii(out)
        if args.scramble:
            import scramble_composition  # sibling spike; keeps this import optional

            out = scramble_composition.scramble(out)
            verify_no_pii(out)  # the scramble only touches already-safe data
    except ScrubError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(out, ensure_ascii=False, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )

    policy_counts: Counter[str] = Counter(POLICY[f] for m in out["data"].values() for f in m)
    print(f"Scrubbed {src.name} -> {args.output}")
    print(f"Members: {len(out['data'])}" + (" (composition scrambled)" if args.scramble else ""))
    print("PII scan: clean (no personnummer/email/phone in preserved fields)")
    print("Field policy application counts (field-instances):")
    for policy, n in sorted(policy_counts.items()):
        print(f"  {policy:<10} {n}")


if __name__ == "__main__":
    main()
