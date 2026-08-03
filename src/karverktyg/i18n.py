"""
User-facing Swedish strings (CLAUDE.md §2).

Code is English; every user-visible string lives here in one module. UI code
calls ``t("key")``. Locale is sv_SE. Keeping them together makes the surface
auditable and a future language switch mechanical.
"""

from __future__ import annotations

# Keyed by a stable English identifier -> Swedish display text.
STRINGS: dict[str, str] = {
    # Navigation / pages
    "app.title": "Kårverktyg",
    "nav.overview": "Översikt",
    "nav.dues": "Medlemsavgifter",
    "nav.waiting": "Väntelista",
    "nav.uppflyttning": "Uppflyttning",
    "nav.findings": "Anmärkningar",
    "nav.capabilities": "Funktioner",
    # Payment buckets (§4)
    "payment.outstanding": "Utestående",
    "payment.settled": "Betald",
    "payment.not_billed": "Ej fakturerad",
    "payment.unknown": "Okänd betalstatus – behöver granskas",
    # Findings (§11)
    "finding.security_ledare_leader": "Ledare i avdelningen Ledare (säkerhetsrisk)",
    "finding.adult_in_scout_unit": "Myndig i scoutavdelning",
    "finding.multi_avdelning": "Medlem i flera avdelningar",
    "finding.young_leader": "Ung scout satt som ledare",
    "finding.no_avdelning": "Saknar avdelning",
    "finding.bad_phone": "Telefonnummer ser felaktigt ut",
    "finding.bad_email": "E-postadress ser felaktig ut",
    "finding.severity.security": "Säkerhet",
    "finding.severity.warning": "Varning",
    "finding.severity.info": "Information",
    # Uppflyttning (§17)
    "uppflyttning.pending_target": "Väntar på att måldelning skapas",
    "uppflyttning.off_cohort": "Utanför årskull – kräver manuell hantering",
    "uppflyttning.ack_required": "Bekräfta listan innan export",
    # Capabilities (§12)
    "cap.endpoint_configured": "Konfigurerad",
    "cap.endpoint_missing": "Nyckel saknas",
    "cap.action_disabled": "Inaktiverad – nyckel saknas",
    # Generic
    "common.done": "Klar",
    "common.member_no": "Medlemsnummer",
    "common.name": "Namn",
    "common.avdelning": "Avdelning",
    "common.source": "Från",
    "common.target": "Till",
}


def t(key: str) -> str:
    """
    Translate a key to its Swedish string. Unknown keys return the key in
    brackets so a missing translation is visible, never silent.
    """
    return STRINGS.get(key, f"[{key}]")
