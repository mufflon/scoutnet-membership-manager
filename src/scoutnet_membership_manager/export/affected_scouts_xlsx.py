"""
Berörda scouter — the affected scouts of the current uppflyttning selection as a
single flat Excel sheet (§7 / §17).

A lightweight contact roster, distinct from the changelist: while the changelist
is the deliberate hand-off for data entry (one sheet per *target* avdelning), this
is "who is in the group I am looking at right now, and how do I reach them and
their guardians". It lists members by their **current** avdelning (source), so the
operator can click between transitions and pull the contact details for whoever is
affected. It is not gated on the off-cohort acknowledgement and does not depend on
any stored decision — it is a pure view of the live selection (§9: contains names,
streamed to the browser, never written to disk server-side).

Contact details only: member and guardian telephone/email. No postal address,
no personnummer — those are deliberately out of scope.

**Guardian columns are neutral "Anhörig 1 / Anhörig 2", not mor/far.** Scoutnet's
memberlist API keys the two guardian slots as mum/dad, but its own ``labels`` map
them to the gender-neutral *Anhörig 1* (the ``_mum`` fields) and *Anhörig 2* (the
``_dad`` fields) — verified against live data (§4) — and the gendered keys do not
reliably describe the person (a single guardian, a grandparent, two dads). So we
carry the values under the neutral labels, and we **left-pack**: the present
guardians fill Anhörig 1 then 2 in that order, so a sole guardian always lands in
the first column even when only the Anhörig 2 (``_dad``) fields are set.
"""

from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font

from scoutnet_membership_manager.collation import sort_key
from scoutnet_membership_manager.patrol_roles import patrol_role_holders
from scoutnet_membership_manager.scoutnet.models import Member, MemberList
from scoutnet_membership_manager.uppflyttning.models import MasterSet

_BOLD = Font(bold=True)
_LINK = Font(color="0563C1", underline="single")
_NO_AVDELNING = "(ingen avdelning)"

# Second sheet: patrol-scoped roles held by anyone in the selection, to be ended by
# hand in Scoutnet (there is no engagement-write endpoint, §4). A follow-up worklist
# after an uppflyttning, where a mover can keep a Patrulledare role in their old
# patrull. Each row links straight to the member's Scoutnet profile.
_ROLE_HEADERS = ["Namn", "Avdelning", "Patrull", "Uppdrag", "Scoutnet-länk"]
_ROLE_WIDTHS = [26, 20, 20, 18, 48]

_HEADERS = [
    "Medlemsnummer",
    "Avdelning",  # current — where they are now
    "Namn",
    "Medlemmens e-post",
    "Medlemmens mobil",
    "Anhörig 1 – namn",
    "Anhörig 1 – e-post",
    "Anhörig 1 – telefon",
    "Anhörig 2 – namn",
    "Anhörig 2 – e-post",
    "Anhörig 2 – telefon",
]

_WIDTHS = [16, 20, 26, 26, 16, 22, 26, 18, 22, 26, 18]

# The two guardian slots as Scoutnet's API keys them (§4): (name, email, phone).
# Order is mum (= Anhörig 1), then dad (= Anhörig 2), per the API's own labels —
# but only present guardians are kept, and they are left-packed into Anhörig 1/2,
# so a sole guardian always fills the first column.
_GUARDIAN_SLOTS = (
    ("contact_mothers_name", "contact_email_mum", ("contact_mobile_mum", "contact_telephone_mum")),
    ("contact_fathers_name", "contact_email_dad", ("contact_mobile_dad", "contact_telephone_dad")),
)


def _guardians(m: Member) -> list[tuple[str, str, str]]:
    """Present guardians as (name, email, phone), mum-then-dad, gaps dropped."""
    out: list[tuple[str, str, str]] = []
    for name_f, email_f, phone_fs in _GUARDIAN_SLOTS:
        name = m.guardian_names.get(name_f, "")
        email = m.emails.get(email_f, "")
        phone = next((m.phones.get(f, "") for f in phone_fs if m.phones.get(f)), "")
        if name or email or phone:  # any contact detail => the slot is real
            out.append((name, email, phone))
    return out


def _row(m: Member) -> list[object]:
    # Empty contact cells are expected and are themselves a data-quality signal
    # (§11) — left blank, not "-".
    g = _guardians(m)
    g1 = g[0] if len(g) > 0 else ("", "", "")
    g2 = g[1] if len(g) > 1 else ("", "", "")
    return [
        m.member_no,
        m.unit or _NO_AVDELNING,
        m.full_name,
        m.emails.get("contact_email", ""),
        m.phones.get("contact_mobile_phone", ""),
        *g1,
        *g2,
    ]


def build_affected_scouts_xlsx(master: MasterSet, memberlist: MemberList) -> bytes:
    """
    Build the affected-scouts contact roster for ``master`` (already scoped to the
    selected group), joining each move entry back to the live member for contacts.
    A single flat sheet, sorted by current avdelning then surname (Swedish
    collation), so the operator can sort and filter it themselves (§19).
    """
    by_no = memberlist.by_member_no()
    members = [m for e in master.entries if (m := by_no.get(e.member_no)) is not None]
    members.sort(
        key=lambda m: (
            m.unit is None,  # no-avdelning members last
            sort_key(m.unit or ""),
            sort_key(m.last_name),
            sort_key(m.first_name),
        )
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "Berörda scouter"
    for c, h in enumerate(_HEADERS, start=1):
        ws.cell(row=1, column=c, value=h).font = _BOLD
    ws.freeze_panes = "A2"
    for r, m in enumerate(members, start=2):
        for c, value in enumerate(_row(m), start=1):
            ws.cell(row=r, column=c, value=value)
    for col, width in enumerate(_WIDTHS, start=1):
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = width

    _add_patrol_roles_sheet(wb, master, memberlist)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _add_patrol_roles_sheet(wb: Workbook, master: MasterSet, memberlist: MemberList) -> None:
    """
    A "Patrulledare att avsluta" sheet: everyone in the selection who holds a
    patrol-scoped role (Patrulledare / Vice patrulledare), with a clickable link to
    their Scoutnet profile so the operator can open each and set a slutdatum by hand.
    Always added, even when empty, so the export documents that the check was made.
    """
    holders = patrol_role_holders(memberlist, {e.member_no for e in master.entries})
    ws = wb.create_sheet("Patrulledare att avsluta")
    for c, h in enumerate(_ROLE_HEADERS, start=1):
        ws.cell(row=1, column=c, value=h).font = _BOLD
    ws.freeze_panes = "A2"
    for r, h in enumerate(holders, start=2):
        ws.cell(row=r, column=1, value=h.name)
        ws.cell(row=r, column=2, value=h.avdelning or _NO_AVDELNING)
        ws.cell(row=r, column=3, value=h.patrol or "")
        ws.cell(row=r, column=4, value=h.role_name)
        link = ws.cell(row=r, column=5, value=h.url)
        link.hyperlink = h.url
        link.font = _LINK
    for col, width in enumerate(_ROLE_WIDTHS, start=1):
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = width
