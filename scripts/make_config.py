#!/usr/bin/env python3
"""
Interactive kår-config builder (CLAUDE.md §13).

The config is only a kår's **avdelningar** — each with an optional meeting weekday
and an optional explicit move target. Brackets are national and live in code; the
kår's group id and every avdelning's troop_id are read live from the data. The
result is a single JSON that the app reads via ``SCOUTNET_CONFIG_PATH`` (default
``scoutnet-membership-manager.json``, which is gitignored). Running it with **no config at all**
also works — avdelningar are inferred and moves fall back to the universal rule.

Run from the repo root so the result can be validated against the real model:

    python3 scripts/make_config.py            # asks where to save
    python3 scripts/make_config.py -o scoutnet-membership-manager.json

Keep this in step with the config model: when ``scoutnet_membership_manager/config/models.py`` gains
or drops a configurable field, update the questions here too (CLAUDE.md §13).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BRACKET_NAMES = ["sparare", "upptackare", "aventyrare", "utmanare", "rover", "annat"]
# Brackets whose avdelningar meet on a weekday used for same-weekday routing (§17).
_WEEKDAY_BRACKETS = {"sparare", "upptackare", "aventyrare"}
_WEEKDAYS = ["måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"]


def ask(prompt: str, *, default: str | None = None, required: bool = False) -> str:
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
        wd = ask_int(
            "  Veckodag (0=måndag … 6=söndag), blank om okänd", lo=0, hi=6, allow_blank=True
        )
        if wd is not None:
            a["weekday"] = wd
            print(f"    → {_WEEKDAYS[wd]}")
    target = ask("  Fast måldelning vid uppflyttning (namn), blank för automatik")
    if target:
        a["target"] = target
    return a


def build_config() -> dict:
    print("=== Kårkonfiguration för Scoutnet-medlemshantering ===\n")
    name = ask("Kårens namn", required=True)
    print("\nLägg till avdelningar (en i taget).")
    avdelningar: list[dict] = []
    while True:
        avdelningar.append(collect_avdelning())
        print(f"  ✓ {len(avdelningar)} avdelning(ar) hittills.")
        if not ask_yes_no("Lägg till en till?", default=True):
            break
    return {
        "$schema": "docs/scoutnet-membership-manager.schema.json",
        "version": 1,
        "name": name,
        "avdelningar": avdelningar,
    }


def validate(cfg: dict) -> str | None:
    """Validate against the real config model if importable; else skip."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
        from scoutnet_membership_manager.config.loader import migrate
        from scoutnet_membership_manager.config.models import KarConfig
    except Exception:  # noqa: BLE001 - validation is a bonus, never a hard dependency
        return "kunde inte importera konfigurationsmodellen (kör från repo-roten för validering)"
    try:
        KarConfig.model_validate(migrate(cfg))
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

    out = args.output or Path(ask("\nSpara till", default="scoutnet-membership-manager.json"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Sparade {len(cfg['avdelningar'])} avdelningar till {out}")
    print(
        "Peka appen på filen via SCOUTNET_CONFIG_PATH (standard: scoutnet-membership-manager.json)."
    )


if __name__ == "__main__":
    main()
