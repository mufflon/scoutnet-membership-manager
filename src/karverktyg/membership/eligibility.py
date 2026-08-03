"""Eligibility helpers for membership-request text (§10)."""

from __future__ import annotations

from karverktyg.config.models import Bracket, KarConfig

WEEKDAY_SV = ["måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"]

BRACKET_LABEL_SV = {
    Bracket.SPARARE: "Spårare",
    Bracket.UPPTACKARE: "Upptäckare",
    Bracket.AVENTYRARE: "Äventyrare",
    Bracket.UTMANARE: "Utmanare",
    Bracket.ROVER: "Rover",
    Bracket.ANNAT: "Ledare",
}

# Order age brackets low to high; skip Annat (not age-based).
_LADDER = [Bracket.SPARARE, Bracket.UPPTACKARE, Bracket.AVENTYRARE,
           Bracket.UTMANARE, Bracket.ROVER]


def bracket_label(bracket: Bracket | None) -> str | None:
    return BRACKET_LABEL_SV.get(bracket) if bracket else None


def pronoun_sv(sex_code: str | None) -> str:
    """han / hon from the Scoutnet sex code; hen when unknown (neutral default)."""
    s = str(sex_code) if sex_code is not None else ""
    if s == "1":
        return "han"
    if s == "2":
        return "hon"
    return "hen"


def eligible_bracket(birth_year: int | None, cohort_year_n: int | None,
                     config: KarConfig) -> Bracket | None:
    """The bracket whose age window the applicant's age falls in (§17 age model)."""
    if birth_year is None or cohort_year_n is None:
        return None
    age = cohort_year_n - birth_year
    for b in _LADDER:
        try:
            rule = config.rule(b)
        except KeyError:
            continue
        if (rule.age_min is not None and rule.age_max is not None
                and rule.age_min <= age <= rule.age_max):
            return b
    return None


def bracket_avdelningar(bracket: Bracket, config: KarConfig) -> list[dict]:
    """Avdelningar in a bracket with their weekday, ordered by weekday."""
    out = []
    for a in config.avdelningar_in(bracket):
        weekday = WEEKDAY_SV[a.weekday] if a.weekday is not None else None
        out.append({"name": a.name, "weekday": weekday})
    out.sort(key=lambda d: (d["weekday"] is None, d.get("weekday") or ""))
    return out


def avdelningar_sentence(bracket: Bracket, config: KarConfig) -> str:
    """e.g. 'Spårare består av tre avdelningar som träffas på måndagar (Hajarna),
    tisdagar (Späckhuggarna) och onsdagar (Rockorna).'"""
    avd = bracket_avdelningar(bracket, config)
    if not avd:
        return ""
    parts = [f"{a['weekday']}ar ({a['name']})" if a["weekday"] else a["name"] for a in avd]
    joined = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " och " + parts[-1]
    label = bracket_label(bracket)
    n_words = {1: "en", 2: "två", 3: "tre", 4: "fyra", 5: "fem"}.get(len(avd), str(len(avd)))
    avd_word = "avdelning" if len(avd) == 1 else "avdelningar"
    return f"{label} består av {n_words} {avd_word} som träffas på {joined}."
