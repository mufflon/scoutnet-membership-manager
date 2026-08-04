"""
Översikt as an Excel workbook (§19/§20).

Mirrors the trimmed on-screen blade: a cover sheet with the run metadata, one
**composition** sheet (per åldersgrupp, with leaders and scouts-per-leader merged
in), and one **projection** sheet (with the åldersgrupp transitions). No
weekday/årskull/tröskel columns, no separate leaders sheet, no KPI sheet, no
chart, no applicant/recruitment figures — the blade dropped them, so the export
does too.

This is the one **aggregate-only** export — no names, no member numbers — so it
can circulate freely; the cover says so. Numbers are written as numbers so they
sum; a not-applicable figure is the literal string ``-`` (never 0, never blank).
Streamed to the browser, never written to disk server-side (§9).
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.worksheet.worksheet import Worksheet

_BOLD = Font(bold=True)

_AGGREGATE_NOTICE = [
    "Aggregerad – inga namn, inga medlemsnummer, inga kontaktuppgifter.",
]


def _write_rows(
    ws: Worksheet, headers: list[str], rows: list[list[object]], *, freeze: bool = True
) -> None:
    for c, h in enumerate(headers, start=1):
        ws.cell(row=1, column=c, value=h).font = _BOLD
    if freeze:
        ws.freeze_panes = "A2"
    for r, row in enumerate(rows, start=2):
        for c, value in enumerate(row, start=1):
            ws.cell(row=r, column=c, value=value)


def _write_cover(ws: Worksheet, d: dict, kar_name: str, generated_at: datetime) -> None:
    ws.title = "Info"
    r = 1
    for line in _AGGREGATE_NOTICE:
        ws.cell(row=r, column=1, value=line).font = _BOLD if r == 1 else Font()
        r += 1
    r += 1
    recon = d["reconciliation"]
    meta: list[tuple[str, object]] = [
        ("Kår", kar_name),
        ("Genererad", generated_at.isoformat(timespec="seconds")),
        ("Innevarande termin", d.get("current_term") or ""),
        ("Uppflyttningsår (N)", d["cohort_year"]),
        ("Prognosen avser årskull", d["projection_targets"]),
        ("Skiftet för N redan tillämpat", "ja" if d["shift_applied"] else "nej"),
        ("", ""),
        ("Medlemmar (beräknat)", recon["membercount"]["computed"]),
        ("Medlemmar (organisation/group)", recon["membercount"]["org"]),
        ("Avdelningar (beräknat)", recon["active_troops"]["computed"]),
        ("Avdelningar (organisation/group)", recon["active_troops"]["org"]),
    ]
    for label, value in meta:
        ws.cell(row=r, column=1, value=label).font = _BOLD
        ws.cell(row=r, column=2, value=value)
        r += 1
    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 26


def _comp_row(group_label: str, a: dict, spl: dict[str, dict]) -> list[object]:
    s = spl.get(a["name"], {})
    return [
        group_label,
        a["name"],
        a["members"],
        s.get("leaders", "-"),
        s.get("ratio", "-"),
        a["flag"] or "",
    ]


def _write_composition(ws: Worksheet, d: dict) -> None:
    ws.title = "Sammansättning"
    spl = {s["avdelning"]: s for s in d["scouts_per_leader"]}
    rows: list[list[object]] = []
    for g in d["composition"]["groups"]:
        rows.extend(_comp_row(g["label"], a, spl) for a in g["avdelningar"])
        rows.append([f"  Delsumma {g['label']}", "", g["subtotal"], "", "", ""])
    rows.extend(
        _comp_row("(okänd åldersgrupp)", a, spl) for a in d["composition"]["unknown_bracket"]
    )
    rows.append(["Utan avdelning", "", d["composition"]["no_unit_count"], "", "", ""])
    rows.append(["Kårtotal", "", d["composition"]["kar_total"], "", "", ""])
    _write_rows(
        ws,
        ["Åldersgrupp", "Avdelning", "Medlemmar", "Ledare", "Kvot", "Anm."],
        rows,
    )
    # Leaders summary, mirroring the line under the blade's composition.
    ldr = d["leaders"]
    foot = len(rows) + 3
    ws.cell(row=foot, column=1, value=ldr["ledare_members_label"]).font = _BOLD
    ws.cell(row=foot, column=2, value=ldr["ledare_members"])
    ws.cell(row=foot + 1, column=1, value=ldr["role_holders_label"]).font = _BOLD
    ws.cell(row=foot + 1, column=2, value=ldr["role_holders"])
    ws.column_dimensions["A"].width = 22


def _write_projection(ws: Worksheet, d: dict) -> None:
    ws.title = "Prognos"
    proj = d["projection"]
    rows = [
        [r["avdelning"], r["current"], r["outgoing"], r["incoming"], r["next"]]
        for r in proj["rows"]
    ]
    _write_rows(
        ws,
        ["Avdelning", "Nuvarande", "Utgående", "Inkommande", "Nästa år"],
        rows,
    )
    # Åldersgrupp transitions below the table.
    start = len(rows) + 3
    ws.cell(row=start, column=1, value="Åldersgruppsövergångar").font = _BOLD
    for i, t in enumerate(proj["transitions"], start=start + 1):
        ws.cell(row=i, column=1, value=f"{t['from']} → {t['to']}")
        ws.cell(row=i, column=2, value=t["count"])
    ws.column_dimensions["A"].width = 22


def build_oversikt_xlsx(d: dict, *, kar_name: str, generated_at: datetime) -> bytes:
    """Build the aggregate-only Översikt workbook (§19/§20)."""
    wb = Workbook()
    _write_cover(wb.active, d, kar_name, generated_at)
    _write_composition(wb.create_sheet("Sammansättning"), d)
    _write_projection(wb.create_sheet("Prognos"), d)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
