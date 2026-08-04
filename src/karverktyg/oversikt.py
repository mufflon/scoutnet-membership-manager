"""
Översikt — the aggregate overview blade (§20).

Read-only, aggregate-only (no names, no member numbers): composition by
åldersgrupp, the two leader figures and per-avdelning scouts-per-leader, the
next-year projection derived from §17's transition rules, and the KPIs. Every
movement figure is **derived** from the master set (``compute_master_set``) and
the bracket rules (``eligible_bracket``) — this module never re-implements §17's
brackets, it reads the same computation the Uppflyttning blade uses.

Existence of an avdelning comes from **config** (the registry), membership counts
from the **memberlist**; a configured avdelning with no members appears as a row
with ``-`` in every derived column, never omitted (§20). ``-`` is a literal
placeholder for "not applicable", distinct from a real ``0``.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from karverktyg.collation import sort_key
from karverktyg.config.models import Bracket, BracketRule, KarConfig
from karverktyg.membership.eligibility import BRACKET_LABEL_SV, eligible_bracket
from karverktyg.roster import TroopIndex, build_troop_index
from karverktyg.scoutnet.models import Member, MemberList, PaymentBucket
from karverktyg.uppflyttning.engine import compute_master_set
from karverktyg.uppflyttning.models import ElectedTarget, MasterSet, MoveStatus

DASH = "-"  # literal "not applicable" placeholder (§20); never 0, never blank

# Åldersgrupp display order, youngest first, Ledare/Annat last (§20).
_GROUP_ORDER = [
    Bracket.SPARARE,
    Bracket.UPPTACKARE,
    Bracket.AVENTYRARE,
    Bracket.UTMANARE,
    Bracket.ROVER,
    Bracket.ANNAT,
]
_MOVING_STATUSES = {MoveStatus.READY, MoveStatus.PENDING_TARGET}


# --- Composition ----------------------------------------------------------


@dataclass
class AvdRow:
    """One avdelning in the composition table."""

    name: str
    bracket: Bracket | None
    weekday: int | None
    troop_id: int | None
    member_count: int
    configured: bool
    discovered: bool

    @property
    def is_empty(self) -> bool:
        """No live members — every derived column renders as ``-`` (§20)."""
        return self.member_count == 0


def _avd_bracket(name: str, config: KarConfig, members: list[Member]) -> Bracket | None:
    a = config.avdelning(name)
    if a is not None:
        return a.bracket
    # Discovered but not configured: infer the bracket from a live member.
    for m in members:
        if m.unit == name and m.bracket is not None:
            return m.bracket
    return None


def _build_rows(memberlist: MemberList, config: KarConfig, index: TroopIndex) -> list[AvdRow]:
    """The flat AvdRow list — config registry ∪ live-discovered — sorted for display."""
    live_counts: Counter[str] = Counter(m.unit for m in memberlist.members if m.unit)
    names = {a.name for a in config.avdelningar} | set(live_counts)
    rows = [
        AvdRow(
            name=name,
            bracket=_avd_bracket(name, config, memberlist.members),
            weekday=(a.weekday if (a := config.avdelning(name)) else None),
            troop_id=index.name_to_id.get(name),
            member_count=live_counts.get(name, 0),
            configured=a is not None,
            discovered=name in live_counts,
        )
        for name in names
    ]
    return sorted(
        rows,
        key=lambda r: (
            _GROUP_ORDER.index(r.bracket) if r.bracket in _GROUP_ORDER else 99,
            r.weekday if r.weekday is not None else 99,
            sort_key(r.name),
        ),
    )


def composition(rows: list[AvdRow], no_unit: int) -> dict:
    """Group the avdelning rows by åldersgrupp with subtotals and a kår total (§20)."""
    groups = []
    kar_total = 0
    for bracket in _GROUP_ORDER:
        grp_rows = sorted(
            (r for r in rows if r.bracket is bracket),
            key=lambda r: (r.weekday if r.weekday is not None else 99, sort_key(r.name)),
        )
        if not grp_rows:
            continue
        subtotal = sum(r.member_count for r in grp_rows)
        kar_total += subtotal
        groups.append(
            {
                "bracket": str(bracket),
                "label": BRACKET_LABEL_SV.get(bracket, str(bracket)),
                "subtotal": subtotal,
                "avdelningar": [_avd_dict(r) for r in grp_rows],
            }
        )
    # Avdelningar discovered live with an unknown bracket, plus the no-unit bucket.
    unknown = sorted((r for r in rows if r.bracket is None), key=lambda r: sort_key(r.name))
    return {
        "groups": groups,
        "unknown_bracket": [_avd_dict(r) for r in unknown],
        "no_unit_count": no_unit,
        "kar_total": kar_total + no_unit,
    }


def _avd_dict(r: AvdRow) -> dict:
    return {
        "name": r.name,
        "bracket": str(r.bracket) if r.bracket else DASH,
        "weekday": r.weekday if r.weekday is not None else DASH,
        "members": DASH if r.is_empty else r.member_count,
        "configured": r.configured,
        "discovered": r.discovered,
        # Flag a discovered avdelning with no config: its meeting weekday is unknown.
        "flag": None if r.configured else "saknas i config (veckodag okänd)",
    }


# --- Leaders --------------------------------------------------------------


def leaders(memberlist: MemberList, config: KarConfig) -> dict:
    """
    The two leader figures (§20) plus the per-avdelning troop-scoped leader
    breakdown that feeds the scouts-per-leader KPI.
    """
    eighteen_plus = set(config.eighteen_plus_avdelningar())
    ledare_members = sum(1 for m in memberlist.members if m.unit in eighteen_plus)
    # Role-holders are deduplicated by member (a third hold roles in two
    # avdelningar; summing per-avdelning would overstate people) (§20).
    role_holders = sum(1 for m in memberlist.members if m.is_leader)

    # Per troop_id: adult/youth leaders, classified by the leader's OWN placement.
    per_troop: dict[int, dict[str, int]] = {}
    for m in memberlist.members:
        own_adult = m.unit in eighteen_plus
        troops_led = {r.scope_id for r in m.roles if r.scope == "troop" and r.is_leader}
        for tid in troops_led:
            slot = per_troop.setdefault(tid, {"adult": 0, "youth": 0})
            slot["adult" if own_adult else "youth"] += 1
    return {
        "ledare_members": ledare_members,
        "ledare_members_label": "Medlemmar i avdelningen Ledare (vuxna på rullorna)",
        "role_holders": role_holders,
        "role_holders_label": "Innehavare av ledarroll (troop/group, ej patrull) – unika personer",
        "union_note": "Vid uppflyttning undantas unionen av båda (§17): "
        "över-undantag är säkert, under-undantag flyttar en ledare.",
        "per_troop": per_troop,
    }


# --- Scouts per leader (KPI) ----------------------------------------------


def scouts_per_leader(
    composition_rows: list[AvdRow], per_troop: dict[int, dict[str, int]]
) -> list[dict]:
    """
    Scouts-per-leader per avdelning (§20). Scouts come from ``unit`` counts,
    leaders from troop-scoped leader roles (not Ledare membership). Where either
    side is zero the ratio is ``-`` (a new avdelning is "not applicable yet").
    """
    out: list[dict] = []
    for r in composition_rows:
        if r.bracket in (None, Bracket.ANNAT):
            continue  # ratio is a scout-avdelning KPI; Ledare/Annat is not one
        led = per_troop.get(r.troop_id, {}) if r.troop_id is not None else {}
        adult, youth = led.get("adult", 0), led.get("youth", 0)
        total_leaders = adult + youth
        scouts = r.member_count
        threshold = None  # national ratio guidance is no longer configured (§13)
        if scouts == 0 or total_leaders == 0:
            ratio, per_one, over = DASH, DASH, False
        else:
            per_one = round(scouts / total_leaders, 1)
            ratio = f"{per_one:g}:1"
            over = threshold is not None and per_one > threshold
        out.append(
            {
                "avdelning": r.name,
                "bracket": str(r.bracket),
                "scouts": DASH if scouts == 0 else scouts,
                "leaders": DASH if total_leaders == 0 else total_leaders,
                "adult_leaders": DASH if total_leaders == 0 else adult,
                "youth_leaders": DASH if total_leaders == 0 else youth,
                "ratio": ratio,
                "per_one_leader": per_one,
                "threshold": threshold if threshold is not None else DASH,
                "over_threshold": over,
            }
        )
    return out


def _rule(config: KarConfig, bracket: Bracket | None) -> BracketRule | None:
    if bracket is None:
        return None
    try:
        return config.rule(bracket)
    except KeyError:
        return None


# --- Projection -----------------------------------------------------------


def projection(
    config: KarConfig,
    master: MasterSet,
    composition_rows: list[AvdRow],
) -> dict:
    """Next-year projection derived from §17's rules via the master set (§20)."""
    moving = [e for e in master.entries if e.status in _MOVING_STATUSES]
    outgoing: Counter[str] = Counter(e.source_avdelning for e in moving if e.source_avdelning)
    incoming: Counter[str] = Counter(e.target_avdelning for e in moving if e.target_avdelning)
    pending_new = [e for e in moving if e.status is MoveStatus.PENDING_TARGET]

    rows: list[dict] = [_projection_row(r, outgoing, incoming) for r in composition_rows]
    # The new Utmanare avdelning may not exist yet: a pending row (§20).
    if pending_new:
        rows.append(
            {
                "avdelning": "(ny Utmanare-avdelning)",
                "bracket": str(Bracket.UTMANARE),
                "current": DASH,
                "outgoing": DASH,
                "incoming": len(pending_new),
                "next": len(pending_new),
                "basis": "pending",
                "note": "Ny avdelning väljs vid målval; finns kanske inte ännu",
                "over_threshold": False,
            }
        )

    transitions = _transition_lines(moving, config)
    return {
        "cohort_year": master.cohort_year,
        "rows": rows,
        "transitions": transitions,
        "utmanare_static_note": "Utmanare-avdelningar projiceras statiskt – "
        "ingen flyttas ut per regel (§17); spridning vid nedläggning är individuell.",
    }


def _projection_row(r: AvdRow, outgoing: Counter[str], incoming: Counter[str]) -> dict:
    out = outgoing.get(r.name, 0)
    inc = incoming.get(r.name, 0)
    threshold = None  # national size guidance is no longer configured (§13)

    if r.is_empty:
        return _row(r.name, r.bracket, DASH, DASH, DASH, DASH, "empty", "", over=False)
    if r.bracket is Bracket.SPARARE:
        # Inflow is recruitment (§20) — not predicted. Show the known net only.
        nxt = r.member_count - out
        return _row(
            r.name,
            r.bracket,
            r.member_count,
            out,
            DASH,
            nxt,
            "recruitment",
            "Inflöde = rekrytering (ej prognostiserat); nästa år är ett golv",
            over=threshold is not None and nxt > threshold,
        )
    if r.bracket in (Bracket.UTMANARE, Bracket.ROVER, Bracket.ANNAT):
        # Static by rule: no age-based movement out (§17/§20).
        return _row(r.name, r.bracket, r.member_count, 0, inc, r.member_count + inc, "static", "")
    nxt = r.member_count - out + inc
    return _row(
        r.name,
        r.bracket,
        r.member_count,
        out,
        inc,
        nxt,
        "derived",
        "",
        over=threshold is not None and nxt > threshold,
    )


def _row(
    name: str,
    bracket: Bracket | None,
    current: object,
    out: object,
    inc: object,
    nxt: object,
    basis: str,
    note: str,
    *,
    over: bool = False,
) -> dict:
    return {
        "avdelning": name,
        "bracket": str(bracket) if bracket else DASH,
        "current": current,
        "outgoing": out,
        "incoming": inc,
        "next": nxt,
        "basis": basis,  # derived / static / recruitment / pending / empty (§20 qualifier)
        "note": note,
        "over_threshold": over,
    }


def _transition_lines(moving: list, config: KarConfig) -> list[dict]:
    """How many move from each åldersgrupp to the next — stated explicitly (§20)."""
    by_source_bracket: Counter[Bracket] = Counter()
    for e in moving:
        a = config.avdelning(e.source_avdelning) if e.source_avdelning else None
        if a is not None:
            by_source_bracket[a.bracket] += 1
    steps = [
        (Bracket.SPARARE, Bracket.UPPTACKARE),
        (Bracket.UPPTACKARE, Bracket.AVENTYRARE),
        (Bracket.AVENTYRARE, Bracket.UTMANARE),
    ]
    return [
        {
            "from": BRACKET_LABEL_SV.get(src, str(src)),
            "to": BRACKET_LABEL_SV.get(dst, str(dst)),
            "count": by_source_bracket.get(src, 0),
        }
        for src, dst in steps
    ]


# --- KPIs and reconciliation ----------------------------------------------


def _num(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def kpis(
    memberlist: MemberList,
    config: KarConfig,
    composition_rows: list[AvdRow],
    projection_rows: list[dict],
    applicants: dict[str, MemberList | None],
    n: int,
    org_group: dict,
) -> dict:
    """The small, actionable KPIs (§20)."""
    stats = org_group.get("stats") or {}

    # Size spread within each scout åldersgrupp.
    spread: list[dict] = []
    for bracket in (Bracket.SPARARE, Bracket.UPPTACKARE, Bracket.AVENTYRARE):
        sizes = [
            r.member_count for r in composition_rows if r.bracket is bracket and not r.is_empty
        ]
        if len(sizes) >= 2:  # noqa: PLR2004 - a spread needs at least two avdelningar
            spread.append(
                {
                    "bracket": BRACKET_LABEL_SV.get(bracket, str(bracket)),
                    "min": min(sizes),
                    "max": max(sizes),
                    "spread": max(sizes) - min(sizes),
                }
            )

    over_projected = [
        {"avdelning": pr["avdelning"], "next": pr["next"]}
        for pr in projection_rows
        if pr.get("over_threshold")
    ]

    # Waiting-list depth, total and per bracket.
    depth_total, per_bracket, missing = 0, Counter(), []
    for variant in ("waiting", "awaiting_approval"):
        ml = applicants.get(variant)
        if ml is None:
            missing.append(variant)
            continue
        depth_total += len(ml)
        for m in ml.members:
            b = eligible_bracket(m.birth_year, n, config)
            if b is not None:
                per_bracket[b] += 1

    # Share paid for the invoiced (prev) term, cross-checked against the org
    # figure for that same term — active_paid_previous, falling back to active_paid.
    paid = sum(1 for m in memberlist.members if m.prev_payment() is PaymentBucket.SETTLED)
    total = len(memberlist) or 1
    paid_stat = stats.get("active_paid_previous") or stats.get("active_paid") or {}
    active_paid = _num(paid_stat.get("value"))
    below_26 = _num((stats.get("below_26") or {}).get("value"))
    membercount = _num(org_group.get("membercount")) or len(memberlist)

    return {
        "size_spread": spread,
        "projected_over_threshold": over_projected,
        "waiting_depth": {
            "total": depth_total,
            "per_bracket": [
                {"bracket": BRACKET_LABEL_SV.get(b, str(b)), "count": per_bracket[b]}
                for b in _GROUP_ORDER
                if per_bracket.get(b)
            ],
            "provisional": bool(missing),
            "missing_variants": missing,
        },
        "share_paid": {
            "computed_paid": paid,
            "of": len(memberlist),
            "percent": round(100 * paid / total, 1),
            "org_active_paid": active_paid if active_paid is not None else DASH,
            "cross_check_ok": active_paid is None or active_paid == paid,
        },
        "share_under_26": (
            {"percent": round(100 * below_26 / (membercount or 1), 1), "count": below_26}
            if below_26 is not None
            else {"percent": DASH, "count": DASH, "note": "below_26 ej tillgängligt"}
        ),
        "retention": {
            "available": False,
            "note": "Retention/avhopp kräver historik som verktyget medvetet inte lagrar (§9). "
            "Använd Scoutnets egna rapporter.",
        },
    }


def reconciliation(memberlist: MemberList, composition: dict, org_group: dict) -> dict:
    """Independent totals against /organisation/group; say when they disagree (§20)."""
    distinct_troops = sum(len(g["avdelningar"]) for g in composition["groups"]) + len(
        composition["unknown_bracket"]
    )
    org_membercount = _num(org_group.get("membercount"))
    org_troops = _num(org_group.get("active_troops"))
    org_waiting = _num(org_group.get("waitingcount"))
    return {
        "membercount": {
            "computed": len(memberlist),
            "org": org_membercount if org_membercount is not None else DASH,
            "agree": org_membercount is None or org_membercount == len(memberlist),
        },
        "active_troops": {
            "computed": distinct_troops,
            "org": org_troops if org_troops is not None else DASH,
            "agree": org_troops is None or org_troops == distinct_troops,
        },
        "waitingcount": {
            "org": org_waiting if org_waiting is not None else DASH,
        },
    }


# --- Top-level assembly ---------------------------------------------------


@dataclass
class OversiktInputs:
    """Everything the overview needs, fetched by the caller (fail-soft)."""

    memberlist: MemberList
    config: KarConfig
    org_group: dict = field(default_factory=dict)
    applicants: dict[str, MemberList | None] = field(default_factory=dict)
    cohort_year_n: int | None = None
    elected_target: ElectedTarget | None = None


def build_oversikt(inp: OversiktInputs) -> dict:
    """Assemble the full §20 overview payload."""
    index = build_troop_index(inp.memberlist, inp.config)
    # The flat AvdRow list (config registry ∪ live), built once and reused.
    rows = _build_rows(inp.memberlist, inp.config, index)
    no_unit = sum(1 for m in inp.memberlist.members if not m.unit)
    comp = composition(rows, no_unit)
    ldr = leaders(inp.memberlist, inp.config)
    master = compute_master_set(
        inp.memberlist,
        inp.config,
        inp.cohort_year_n,
        inp.memberlist.current_term_label,
        index=index,
        elected_target=inp.elected_target,
    )
    proj = projection(inp.config, master, rows)
    spl = scouts_per_leader(rows, ldr["per_troop"])
    kpi = kpis(
        inp.memberlist,
        inp.config,
        rows,
        proj["rows"],
        inp.applicants,
        master.cohort_year,
        inp.org_group,
    )
    recon = reconciliation(inp.memberlist, comp, inp.org_group)
    shift_applied = not [e for e in master.entries if e.status in _MOVING_STATUSES]
    return {
        "kar": inp.config.name,
        "current_term": inp.memberlist.current_term_label,
        "prev_term": inp.memberlist.prev_term_label,
        "cohort_year": master.cohort_year,
        "shift_applied": shift_applied,
        "projection_targets": master.cohort_year + 1 if shift_applied else master.cohort_year,
        "composition": comp,
        "leaders": {k: v for k, v in ldr.items() if k != "per_troop"},
        "scouts_per_leader": spl,
        "projection": proj,
        "kpis": kpi,
        "reconciliation": recon,
    }
