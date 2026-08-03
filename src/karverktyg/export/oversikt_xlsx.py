"""
Översikt as an Excel workbook (§19/§20).

One sheet per table on the blade — composition, leaders + scouts-per-leader,
projection (with the åldersgrupp transitions and the Spårare recruitment target),
and the KPIs — plus a cover sheet carrying the kår, generation timestamp, the
current term label and **the cohort year the projection targets** (without which a
saved workbook is unreadable months later).

This is the one **aggregate-only** export — no names, no member numbers — so it
can circulate freely; the cover says so. Numbers are written as numbers so they
sum and chart; a not-applicable figure is the literal string ``-`` (never 0,
never blank), and the derived/static/unknown qualifier survives as its own
column. Streamed to the browser, never written to disk server-side (§9).
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


def _comp_row(group_label: str, a: dict) -> list[object]:
    return [group_label, a["name"], a["weekday"], a["cohort_year"], a["members"], a["flag"] or ""]


def _write_composition(ws: Worksheet, d: dict) -> None:
    ws.title = "Sammansättning"
    rows: list[list[object]] = []
    for g in d["composition"]["groups"]:
        rows.extend(_comp_row(g["label"], a) for a in g["avdelningar"])
        rows.append([f"  Delsumma {g['label']}", "", "", "", g["subtotal"], ""])
    rows.extend(_comp_row("(okänd åldersgrupp)", a) for a in d["composition"]["unknown_bracket"])
    rows.append(["Utan avdelning", "", "", "", d["composition"]["no_unit_count"], ""])
    rows.append(["Kårtotal", "", "", "", d["composition"]["kar_total"], ""])
    _write_rows(
        ws,
        ["Åldersgrupp", "Avdelning", "Veckodag", "Årskull", "Medlemmar", "Anm."],
        rows,
    )


def _write_leaders(ws: Worksheet, d: dict) -> None:
    ws.title = "Ledare"
    ldr = d["leaders"]
    ws.cell(row=1, column=1, value=ldr["ledare_members_label"]).font = _BOLD
    ws.cell(row=1, column=2, value=ldr["ledare_members"])
    ws.cell(row=2, column=1, value=ldr["role_holders_label"]).font = _BOLD
    ws.cell(row=2, column=2, value=ldr["role_holders"])
    start = 4
    headers = [
        "Avdelning",
        "Scouter",
        "Ledare",
        "Vuxenledare",
        "Ungdomsledare",
        "Kvot",
        "Tröskel",
        "Över tröskel",
    ]
    for c, h in enumerate(headers, start=1):
        ws.cell(row=start, column=c, value=h).font = _BOLD
    for i, s in enumerate(d["scouts_per_leader"], start=start + 1):
        for c, value in enumerate(
            [
                s["avdelning"],
                s["scouts"],
                s["leaders"],
                s["adult_leaders"],
                s["youth_leaders"],
                s["ratio"],
                s["threshold"],
                "ja" if s["over_threshold"] else "nej",
            ],
            start=1,
        ):
            ws.cell(row=i, column=c, value=value)
    ws.column_dimensions["A"].width = 20


def _write_projection(ws: Worksheet, d: dict) -> None:
    ws.title = "Prognos"
    proj = d["projection"]
    rows = [
        [
            r["avdelning"],
            r["bracket"],
            r["current"],
            r["outgoing"],
            r["incoming"],
            r["next"],
            r["basis"],
            r["note"],
        ]
        for r in proj["rows"]
    ]
    _write_rows(
        ws,
        [
            "Avdelning",
            "Åldersgrupp",
            "Nuvarande",
            "Utgående",
            "Inkommande",
            "Nästa år",
            "Grund",
            "Not",
        ],
        rows,
    )
    # Transitions + recruitment below the table.
    start = len(rows) + 3
    ws.cell(row=start, column=1, value="Åldersgruppsövergångar").font = _BOLD
    for i, t in enumerate(proj["transitions"], start=start + 1):
        ws.cell(row=i, column=1, value=f"{t['from']} → {t['to']}")
        ws.cell(row=i, column=2, value=t["count"])
    sp = proj["spararrekrytering"]
    rr = start + len(proj["transitions"]) + 2
    ws.cell(row=rr, column=1, value="Spårarrekrytering").font = _BOLD
    ws.cell(row=rr + 1, column=1, value=sp["sentence"])
    ws.cell(row=rr + 2, column=1, value="X (avgår)")
    ws.cell(row=rr + 2, column=2, value=sp["x_leaving"])
    ws.cell(row=rr + 3, column=1, value="Y (väntande)")
    ws.cell(row=rr + 3, column=2, value=sp["y_pending"])
    ws.cell(row=rr + 4, column=1, value="Z (mål)")
    ws.cell(row=rr + 4, column=2, value=sp["z_target"])
    ws.cell(row=rr + 5, column=1, value="Provisorisk")
    ws.cell(row=rr + 5, column=2, value="ja" if sp["provisional"] else "nej")
    ws.column_dimensions["A"].width = 22


def _write_kpis(ws: Worksheet, d: dict) -> None:
    ws.title = "Nyckeltal"
    k = d["kpis"]
    r = 1

    def line(label: object, value: object) -> None:
        nonlocal r
        ws.cell(row=r, column=1, value=label).font = _BOLD
        ws.cell(row=r, column=2, value=value)
        r += 1

    ws.cell(row=r, column=1, value="Storleksspridning per åldersgrupp").font = _BOLD
    r += 1
    for s in k["size_spread"]:
        ws.cell(row=r, column=1, value=f"  {s['bracket']}")
        ws.cell(row=r, column=2, value=f"{s['min']}–{s['max']} (spridning {s['spread']})")
        r += 1
    r += 1
    line("Andel betald (beräknat)", f"{k['share_paid']['percent']} %")
    line(
        "  varav betalda / totalt", f"{k['share_paid']['computed_paid']} / {k['share_paid']['of']}"
    )
    line("  organisation/group active_paid", k["share_paid"]["org_active_paid"])
    line("  stämmer", "ja" if k["share_paid"]["cross_check_ok"] else "nej")
    line("Andel under 26 år", k["share_under_26"]["percent"])
    line("Väntelistedjup (totalt)", k["waiting_depth"]["total"])
    for b in k["waiting_depth"]["per_bracket"]:
        line(f"  {b['bracket']}", b["count"])
    line("Retention/avhopp", k["retention"]["note"])
    for pr in k["projected_over_threshold"]:
        line(f"⚠ Prognos över tröskel: {pr['avdelning']}", pr["next"])
    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 30


def build_oversikt_xlsx(d: dict, *, kar_name: str, generated_at: datetime) -> bytes:
    """Build the aggregate-only Översikt workbook (§19/§20)."""
    wb = Workbook()
    _write_cover(wb.active, d, kar_name, generated_at)
    _write_composition(wb.create_sheet("Sammansättning"), d)
    _write_leaders(wb.create_sheet("Ledare"), d)
    _write_projection(wb.create_sheet("Prognos"), d)
    _write_kpis(wb.create_sheet("Nyckeltal"), d)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
