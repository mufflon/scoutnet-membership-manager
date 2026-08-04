"""
Förtroendeuppdrag as an Excel workbook (§18, §19).

An ``Info`` cover sheet (kår, term, generation timestamp, the rolecount
cross-check) followed by the assignment register in its computed §18 order —
Styrelse first, unfamiliar roles last. Streamed to the browser, never written to
disk server-side (§9).
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.worksheet.worksheet import Worksheet

from scoutnet_membership_manager.fortroende import SECTION_LABEL_SV, FortroendeResult

_BOLD = Font(bold=True)


def _write_cover(
    ws: Worksheet,
    result: FortroendeResult,
    kar_name: str,
    term_label: str | None,
    generated_at: datetime,
    rolecount: int | None,
) -> None:
    ws.title = "Info"
    match = rolecount is not None and result.total_roles_parsed == rolecount
    rows: list[tuple[str, object]] = [
        ("Kår", kar_name),
        ("Termin", term_label or ""),
        ("Genererad", generated_at.isoformat(timespec="seconds")),
        ("", ""),
        ("Förtroendeuppdrag (kårnivå)", result.group_count),
        ("Roller tolkade (alla nivåer)", result.total_roles_parsed),
        ("Scoutnet rolecount", rolecount if rolecount is not None else "ej tillgänglig"),
        ("Stämmer", "ja" if match else ("nej" if rolecount is not None else "-")),
    ]
    for r, (label, value) in enumerate(rows, start=1):
        ws.cell(row=r, column=1, value=label).font = _BOLD
        ws.cell(row=r, column=2, value=value)
    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 24


def _write_register(ws: Worksheet, result: FortroendeResult) -> None:
    headers = ["Sektion", "Roll", "Namn", "Medlemsnummer", "Rollnyckel"]
    for c, h in enumerate(headers, start=1):
        ws.cell(row=1, column=c, value=h).font = _BOLD
    ws.freeze_panes = "A2"
    # Keep the computed §18 order (board, other, delegate); do not re-sort here.
    for r, a in enumerate(result.assignments, start=2):
        ws.cell(row=r, column=1, value=SECTION_LABEL_SV.get(a.section, a.section))
        ws.cell(row=r, column=2, value=a.label)
        ws.cell(row=r, column=3, value=a.member_name)
        ws.cell(row=r, column=4, value=a.member_no)
        ws.cell(row=r, column=5, value=a.role_key)
    for col, width in (("A", 26), ("B", 30), ("C", 28), ("D", 16), ("E", 22)):
        ws.column_dimensions[col].width = width


def build_fortroende_xlsx(
    result: FortroendeResult,
    *,
    kar_name: str,
    term_label: str | None,
    generated_at: datetime,
    rolecount: int | None = None,
) -> bytes:
    """Build the förtroendeuppdrag workbook (§18)."""
    wb = Workbook()
    _write_cover(wb.active, result, kar_name, term_label, generated_at, rolecount)
    _write_register(wb.create_sheet(title="Förtroendeuppdrag"), result)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
