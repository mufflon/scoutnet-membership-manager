#!/usr/bin/env python3
"""
Interactive kår-config builder (CLAUDE.md §13).

Walks you through the few things that differ between scoutkårer — the kår's name
and group id, and the list of avdelningar with their åldersgrupp and meeting day —
and writes a config JSON you can point the app at (SCOUTNET_CONFIG_PATH / the
``config_path`` setting). The standard Scouterna åldersgrupp-ladder (Spårare …
Rover) is built in; you normally only add avdelningar.

It deliberately does NOT write config/karverktyg.default.json: that placeholder is
on its way out, and each kår should generate its own config with this tool.

Run it from the repo root so it can validate the result against the real config
model:

    python3 scripts/make_config.py            # asks where to save
    python3 scripts/make_config.py -o config/minkår.json

Keep this script in step with the config model: when
``karverktyg/config/models.py`` gains or drops a configurable field, update the
questions here too (CLAUDE.md §13).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# The standard Scouterna åldersgrupp-ladder. transition drives uppflyttning (§17);
# these values match karverktyg's TransitionKind. Ages are cohort-age (N − birth
# year). A kår rarely changes this — only the avdelningar below vary.
BRACKETS = [
    {
        "bracket": "sparare",
        "age_min": 8,
        "age_max": 9,
        "transition": "same_weekday",
        "structural_checks": True,
        "scouts_per_leader_max": 6,
        "projected_size_max": 28,
    },
    {
        "bracket": "upptackare",
        "age_min": 10,
        "age_max": 11,
        "transition": "merge",
        "structural_checks": True,
        "scouts_per_leader_max": 8,
        "projected_size_max": 30,
    },
    {
        "bracket": "aventyrare",
        "age_min": 12,
        "age_max": 14,
        "transition": "new_cohort_avdelning",
        "structural_checks": True,
        "scouts_per_leader_max": 10,
        "projected_size_max": 75,
    },
    {
        "bracket": "utmanare",
        "age_min": 15,
        "age_max": 18,
        "transition": "never_auto",
        "structural_checks": False,
        "scouts_per_leader_max": 12,
        "projected_size_max": None,
    },
    {
        "bracket": "rover",
        "age_min": None,
        "age_max": None,
        "transition": "never_auto",
        "structural_checks": False,
    },
    {
        "bracket": "annat",
        "age_min": None,
        "age_max": None,
        "transition": "none",
        "structural_checks": False,
    },
]
BRACKET_NAMES = [b["bracket"] for b in BRACKETS]
# Brackets whose avdelningar meet on a fixed weekday used for uppflyttning routing.
_WEEKDAY_BRACKETS = {"sparare", "upptackare", "aventyrare"}
_WEEKDAYS = ["måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"]


def ask(prompt: str, *, default: str | None = None, required: bool = False) -> str:
    """Prompt until a value is given (or a default accepted)."""
    suffix = f" [{default}]" if default is not None else ""
    while True:
        answer = input(f"{prompt}{suffix}: ").strip()
        if answer:
            return answer
        if default is not None:
            return default
        if not required:
            return ""
        print("  – obligatoriskt, ange ett värde.")


def ask_int(prompt: str, *, lo: int, hi: int, allow_blank: bool = False) -> int | None:
    while True:
        raw = input(f"{prompt}: ").strip()
        if not raw and allow_blank:
            return None
        try:
            n = int(raw)
        except ValueError:
            print("  – ange ett heltal.")
            continue
        if lo <= n <= hi:
            return n
        print(f"  – ange ett tal mellan {lo} och {hi}.")


def ask_yes_no(prompt: str, *, default: bool = False) -> bool:
    d = "J/n" if default else "j/N"
    while True:
        raw = input(f"{prompt} [{d}]: ").strip().lower()
        if not raw:
            return default
        if raw in ("j", "ja", "y", "yes"):
            return True
        if raw in ("n", "nej", "no"):
            return False


def ask_choice(prompt: str, choices: list[str]) -> str:
    print(prompt)
    for i, c in enumerate(choices, start=1):
        print(f"  {i}. {c}")
    while True:
        raw = input("  val (nummer): ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(choices):
            return choices[int(raw) - 1]
        print(f"  – ange 1–{len(choices)}.")


def collect_avdelning() -> dict:
    a: dict[str, object] = {"name": ask("  Avdelningens namn", required=True)}
    bracket = ask_choice("  Åldersgrupp:", BRACKET_NAMES)
    a["bracket"] = bracket
    if bracket in _WEEKDAY_BRACKETS:
        # Required for Spårare (same_weekday routing); recommended for the others.
        req = bracket == "sparare"
        wd = ask_int(
            "  Veckodag (0=måndag … 6=söndag)" + ("" if req else ", blank om okänd"),
            lo=0,
            hi=6,
            allow_blank=not req,
        )
        if wd is not None:
            a["weekday"] = wd
            print(f"    → {_WEEKDAYS[wd]}")
    if bracket == "utmanare":
        cy = ask_int(
            "  Årskull (år laget bildades), blank om okänt", lo=1900, hi=2100, allow_blank=True
        )
        if cy is not None:
            a["cohort_year"] = cy
    if bracket == "annat" and ask_yes_no("  Vuxen-/ledaravdelning (18+)?", default=True):
        a["is_18plus"] = True
    return a


def build_config() -> dict:
    print("=== Kårkonfiguration för Scoutnet-medlemshantering ===\n")
    name = ask("Kårens namn", required=True)
    group_id = ask("Kårens group_id (kårens id i Scoutnet, 4 siffror)", required=True)
    cohort_year_n = ask_int(
        "Uppflyttningsår N (blank = härled från terminen)", lo=1900, hi=2100, allow_blank=True
    )

    print("\nLägg till avdelningar (en i taget).")
    avdelningar: list[dict] = []
    while True:
        avdelningar.append(collect_avdelning())
        print(f"  ✓ {len(avdelningar)} avdelning(ar) hittills.")
        if not ask_yes_no("Lägg till en till?", default=True):
            break

    return {
        "name": name,
        "group_id": group_id,
        "cohort_year_n": cohort_year_n,
        "placeholder": False,
        "brackets": BRACKETS,
        "avdelningar": avdelningar,
        "role_label_overrides": {},
        "expected_fortroende": [],
    }


def validate(cfg: dict) -> str | None:
    """Validate against the real config model if it is importable; else skip."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
        from karverktyg.config.models import KarConfig
    except Exception:  # noqa: BLE001 - validation is a bonus, never a hard dependency
        return "kunde inte importera konfigurationsmodellen (kör från repo-roten för validering)"
    try:
        KarConfig.model_validate(cfg)
    except Exception as e:  # noqa: BLE001 - surface the model's message verbatim
        return str(e)
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description="Bygg en kårkonfiguration interaktivt.")
    ap.add_argument("-o", "--output", type=Path, help="var configen sparas (annars frågar den)")
    args = ap.parse_args()

    cfg = build_config()

    problem = validate(cfg)
    if problem and "kunde inte importera" not in problem:
        print(f"\n⚠ Konfigurationen är ogiltig: {problem}", file=sys.stderr)
        if not ask_yes_no("Spara ändå?", default=False):
            print("Avbröt – inget sparat.")
            sys.exit(1)
    elif problem:
        print(f"\n(Hoppar över validering: {problem})")
    else:
        print("\n✓ Konfigurationen validerar mot modellen.")

    out = args.output or Path(ask("\nSpara till", default="config/minkår.json"))
    if out.name == "karverktyg.default.json":
        print("Skriv inte över karverktyg.default.json – välj ett annat namn.", file=sys.stderr)
        sys.exit(1)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Sparade {len(cfg['avdelningar'])} avdelningar till {out}")
    print("Peka appen på filen via SCOUTNET_CONFIG_PATH eller config_path-inställningen.")


if __name__ == "__main__":
    main()
