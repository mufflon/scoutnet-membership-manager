"""Read-only JSON API (Phase 1). No write endpoints exist."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
from flask import Blueprint, Response, current_app, jsonify, request
from flask.typing import ResponseReturnValue

from karverktyg.config.models import Bracket, KarConfig
from karverktyg.db.session import get_session
from karverktyg.export import (
    ChangelistAckRequired,
    PdfUnavailable,
    build_changelist,
    build_dues_xlsx,
    build_fortroende_xlsx,
    build_oversikt_xlsx,
    html_to_pdf,
    render_html,
)
from karverktyg.findings import compute_findings
from karverktyg.fortroende import fortroendeuppdrag, group_by_section, rolecount_reconciliation
from karverktyg.membership import effective_templates, generate_drafts, upsert_template
from karverktyg.membership.templates import templates_by_key
from karverktyg.oversikt import OversiktInputs, build_oversikt
from karverktyg.roster import build_troop_index
from karverktyg.scoutnet.client import ScoutnetError
from karverktyg.scoutnet.models import MemberList
from karverktyg.settings import Settings
from karverktyg.uppflyttning import (
    ElectedTarget,
    MasterSet,
    apply_overrides,
    clear_all_decisions,
    clear_decision,
    clear_elected_target,
    compute_master_set,
    get_decisions,
    get_elected_target,
    set_elected_target,
    upsert_decision,
)
from karverktyg.uppflyttning.cohort import CohortYearConflict, resolve_cohort_year
from karverktyg.uppflyttning.models import MoveEntry
from karverktyg.views import dues_by_avdelning
from karverktyg.web.apicheck import api_check
from karverktyg.web.capabilities import capabilities

api_bp = Blueprint("api", __name__, url_prefix="/api")

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_PDF_MIME = "application/pdf"
_HTTP_PDF_UNAVAILABLE = 503
# Observed troop ids are five digits; the kår group id is four (§17).
_TROOP_ID_MIN = 10000
_TROOP_ID_MAX = 99999
_SEVERITY_ORDER = {"security": 0, "warning": 1, "info": 2}
# A Scoutnet fetch that fails for one variant must not take down the blade.
_FETCH_ERRORS = (ScoutnetError, httpx.HTTPError)


def _settings() -> Settings:
    return current_app.config["SETTINGS"]


def _config() -> KarConfig:
    return current_app.config["KAR_CONFIG"]


def _memberlist(variant: str = "active") -> MemberList:
    return current_app.config["SCOUTNET"].memberlist(variant)


def _config_n() -> int | None:
    s = _settings()
    return s.cohort_year if s.cohort_year is not None else _config().cohort_year_n


def _elected_target(ml: MemberList) -> ElectedTarget | None:
    """The persisted Äventyrare→Utmanare target election for this cohort year."""
    try:
        n = resolve_cohort_year(_config_n(), ml.current_term_label)
    except CohortYearConflict:
        return None  # compute_master_set will raise the 409
    with get_session(current_app.config["SESSIONMAKER"]) as s:
        return get_elected_target(s, n, Bracket.UTMANARE)


def _master_set(ml: MemberList) -> MasterSet:
    """Compute the master set, then layer the operator's stored decisions (§17)."""
    ms = compute_master_set(
        ml, _config(), _config_n(), ml.current_term_label, elected_target=_elected_target(ml)
    )
    index = build_troop_index(ml, _config())
    with get_session(current_app.config["SESSIONMAKER"]) as s:
        decisions = get_decisions(s, ms.cohort_year)
    apply_overrides(ms, decisions, index)
    return ms


def _entry_for(ml: MemberList, member_no: str) -> dict | None:
    """The recomputed, decision-applied row for one member (for in-place UI updates)."""
    for e in _master_set(ml).entries:
        if e.member_no == member_no:
            return _ser_move(e)
    return None


def _ser_move(e: MoveEntry) -> dict:
    return {
        "member_no": e.member_no,
        "name": e.member_name,
        "birth_year": e.birth_year,
        "source": e.source_avdelning,
        "target": e.target_avdelning,
        "target_troop_id": e.target_troop_id,
        "default_target": e.default_target,
        "status": str(e.status),
        "transition": str(e.transition),
        "note": e.note,
        "override": e.is_override,
        "acknowledged": e.acknowledged,
        "stay": e.override_stay_until is not None,
    }


def _oversikt_inputs(*, with_org: bool = False) -> OversiktInputs:
    """
    §20 inputs. The **fast path** (``with_org=False``) reads only the active +
    waiting memberlists (both quick). The aggregate cross-checks that need the
    slow ``organisation/group`` (~30 s for this kår) are fetched only when
    ``with_org=True``, off the blade's critical path. ``awaiting_approval``
    reliably read-times-out here (§4), so it is never fetched for Översikt —
    Y / waiting-depth use ``waiting`` only and are marked provisional (§20).
    Väntelista is where ``awaiting_approval`` is actually viewed.
    """
    ml = _memberlist()
    try:
        waiting = _memberlist("waiting")
    except _FETCH_ERRORS:
        waiting = None
    org: dict = {}
    if with_org:
        try:
            org = current_app.config["SCOUTNET"].organisation_group()
        except _FETCH_ERRORS:
            org = {}
    return OversiktInputs(
        memberlist=ml,
        config=_config(),
        org_group=org,
        applicants={"waiting": waiting, "awaiting_approval": None},
        cohort_year_n=_config_n(),
        elected_target=_elected_target(ml),
    )


def _oversikt_bars(payload: dict) -> list[dict]:
    """Current-vs-projected bar data, the one chart §20 allows (§20 Presentation)."""
    pairs = [
        (r["avdelning"], r["current"], r["next"])
        for r in payload["projection"]["rows"]
        if isinstance(r["current"], int) and isinstance(r["next"], int)
    ]
    top = max((max(c, n) for _, c, n in pairs), default=1) or 1
    return [
        {
            "name": name,
            "current": cur,
            "next": nxt,
            "cur_pct": round(100 * cur / top),
            "next_pct": round(100 * nxt / top),
        }
        for name, cur, nxt in pairs
    ]


@api_bp.get("/overview")
def api_overview() -> ResponseReturnValue:
    """
    The aggregate overview (§20). Fast by default (active + waiting only); pass
    ``?aggregate=1`` to include the slow organisation/group cross-checks, which
    the frontend fetches asynchronously so the blade never blocks on them.
    """
    with_org = request.args.get("aggregate") == "1"
    ml = _memberlist()
    payload = build_oversikt(_oversikt_inputs(with_org=with_org))
    return jsonify(
        member_count=len(ml),
        avdelning_count=len({m.unit for m in ml.members if m.unit}),
        note_current_term="Höst-terminen är ännu inte fakturerad – "
        "betalvyn gäller föregående termin.",
        aggregate=with_org,
        **payload,
    )


@api_bp.get("/oversikt.xlsx")
def api_oversikt_xlsx() -> ResponseReturnValue:
    """Stream the aggregate-only Översikt workbook (§19/§20)."""
    data = build_oversikt_xlsx(
        build_oversikt(_oversikt_inputs(with_org=True)),
        kar_name=_settings().kar_name,
        generated_at=datetime.now(UTC),
    )
    return Response(
        data,
        mimetype=_XLSX_MIME,
        headers={"Content-Disposition": "attachment; filename=oversikt.xlsx"},
    )


@api_bp.get("/oversikt.pdf")
def api_oversikt_pdf() -> ResponseReturnValue:
    """Stream the aggregate-only Översikt A4 PDF (§19/§20); 503 if WeasyPrint absent."""
    payload = build_oversikt(_oversikt_inputs(with_org=True))
    html = render_html(
        "oversikt.html",
        {
            "kar": _settings().kar_name,
            "term": payload.get("current_term"),
            "generated": datetime.now(UTC).isoformat(timespec="seconds"),
            "o": payload,
            "bars": _oversikt_bars(payload),
        },
    )
    try:
        pdf = html_to_pdf(html)
    except PdfUnavailable as e:
        return jsonify(error=str(e)), _HTTP_PDF_UNAVAILABLE
    return Response(
        pdf,
        mimetype=_PDF_MIME,
        headers={"Content-Disposition": "attachment; filename=oversikt.pdf"},
    )


@api_bp.get("/dues")
def api_dues() -> ResponseReturnValue:
    """Per-avdelning payment breakdown for the invoiced term."""
    ml = _memberlist()
    return jsonify(term=ml.prev_term_label, avdelningar=dues_by_avdelning(ml))


@api_bp.get("/dues.xlsx")
def api_dues_xlsx() -> ResponseReturnValue:
    """Stream the unpaid-dues chase list as a single flat sheet (§19)."""
    ml = _memberlist()
    data = build_dues_xlsx(ml)
    return Response(
        data,
        mimetype=_XLSX_MIME,
        headers={"Content-Disposition": "attachment; filename=medlemsavgifter.xlsx"},
    )


@api_bp.get("/waiting")
def api_waiting() -> ResponseReturnValue:
    """Waiting list and awaiting-approval applicants; each variant fails soft."""
    lists: dict[str, list[dict]] = {}
    unavailable: dict[str, str] = {}
    for variant in ("waiting", "awaiting_approval"):
        try:
            ml = _memberlist(variant)
        except _FETCH_ERRORS as e:
            lists[variant] = []
            unavailable[variant] = str(e)
            continue
        lists[variant] = [
            {"member_no": m.member_no, "name": m.full_name, "unit": m.unit} for m in ml.members
        ]
    return jsonify(
        waiting=lists["waiting"],
        awaiting_approval=lists["awaiting_approval"],
        unavailable=unavailable,
    )


@api_bp.get("/findings")
def api_findings() -> ResponseReturnValue:
    """Findings for the register, security findings first (§11)."""
    ml = _memberlist()
    try:
        n = resolve_cohort_year(_config_n(), ml.current_term_label)
    except CohortYearConflict:
        n = None  # age check needs N; skip it rather than fail the whole page
    findings = compute_findings(ml, _config(), n)
    findings.sort(key=lambda f: _SEVERITY_ORDER.get(str(f.severity), 9))
    return jsonify(
        cohort_year=n,
        findings=[
            {
                "type": str(f.type),
                "severity": str(f.severity),
                "member_no": f.member_no,
                "name": f.member_name,
                "avdelning": f.avdelning,
                "detail": f.detail,
            }
            for f in findings
        ],
    )


def _rolecount() -> int | None:
    """
    Scoutnet's rolecount from /organisation/group, for the §18 cross-check.
    Fails soft: a fetch error or an aggregate without rolecount (fixture mode
    synthesises one) yields None, and the reconciliation degrades to
    "not available" rather than taking down the blade.
    """
    try:
        aggregate = current_app.config["SCOUTNET"].organisation_group()
    except _FETCH_ERRORS:
        return None
    rc = aggregate.get("rolecount")
    try:
        return int(rc) if rc is not None else None
    except (TypeError, ValueError):
        return None


@api_bp.get("/fortroende")
def api_fortroende() -> ResponseReturnValue:
    """
    Kår-level förtroendeuppdrag, a register of posts, ordered per §18. Fast by
    default; the rolecount cross-check needs the slow organisation/group, so it
    is included only on ``?rolecount=1`` (fetched asynchronously by the frontend).
    """
    ml = _memberlist()
    result = fortroendeuppdrag(ml, _config())
    want_rolecount = request.args.get("rolecount") == "1"
    recon = rolecount_reconciliation(
        result.total_roles_parsed, _rolecount() if want_rolecount else None
    )
    recon["requested"] = want_rolecount
    return jsonify(
        term=ml.current_term_label,
        group_count=result.group_count,
        reconciliation=recon,
        assignments=[
            {
                "role_key": a.role_key,
                "role_name": a.role_name,
                "label": a.label,
                "member_no": a.member_no,
                "name": a.member_name,
                "section": a.section,
            }
            for a in result.assignments
        ],
        vacancies=[
            {
                "role_key": v.role_key,
                "label": v.label,
                "expected": v.expected,
                "filled": v.filled,
                "missing": v.missing,
            }
            for v in result.vacancies
        ],
    )


@api_bp.get("/fortroende.xlsx")
def api_fortroende_xlsx() -> ResponseReturnValue:
    """Stream the förtroendeuppdrag workbook (§18/§19)."""
    ml = _memberlist()
    result = fortroendeuppdrag(ml, _config())
    data = build_fortroende_xlsx(
        result,
        kar_name=_settings().kar_name,
        term_label=ml.current_term_label,
        generated_at=datetime.now(UTC),
        rolecount=_rolecount(),
    )
    return Response(
        data,
        mimetype=_XLSX_MIME,
        headers={"Content-Disposition": "attachment; filename=fortroendeuppdrag.xlsx"},
    )


@api_bp.get("/fortroende.pdf")
def api_fortroende_pdf() -> ResponseReturnValue:
    """Stream the förtroendeuppdrag A4 PDF (§18/§19); 503 if WeasyPrint absent."""
    ml = _memberlist()
    result = fortroendeuppdrag(ml, _config())
    rc = _rolecount()
    html = render_html(
        "fortroende.html",
        {
            "kar": _settings().kar_name,
            "term": ml.current_term_label,
            "generated": datetime.now(UTC).isoformat(timespec="seconds"),
            "group_count": result.group_count,
            "total_parsed": result.total_roles_parsed,
            "rolecount": rc,
            "rolecount_available": rc is not None,
            "rolecount_match": rc is not None and result.total_roles_parsed == rc,
            "sections": group_by_section(result.assignments),
            "vacancies": result.vacancies,
        },
    )
    try:
        pdf = html_to_pdf(html)
    except PdfUnavailable as e:
        return jsonify(error=str(e)), _HTTP_PDF_UNAVAILABLE
    return Response(
        pdf,
        mimetype=_PDF_MIME,
        headers={"Content-Disposition": "attachment; filename=fortroendeuppdrag.pdf"},
    )


@api_bp.get("/uppflyttning")
def api_uppflyttning() -> ResponseReturnValue:
    """The computed uppflyttning master set, grouped by status and target (§17)."""
    ml = _memberlist()
    ms = _master_set(ml)
    index = build_troop_index(ml, _config())
    utmanare_candidates = sorted(
        (
            {"avdelning": name, "troop_id": tid}
            for name, tid in index.name_to_id.items()
            if index.id_to_bracket.get(tid) is Bracket.UTMANARE
        ),
        key=lambda c: c["avdelning"],
    )
    elected = _elected_target(ml)
    with get_session(current_app.config["SESSIONMAKER"]) as s:
        decisions_count = len(get_decisions(s, ms.cohort_year))
    # Every avdelning, for the per-member target dropdown.
    avdelningar = sorted(
        (
            {"avdelning": name, "troop_id": tid, "bracket": str(index.id_to_bracket.get(tid, ""))}
            for name, tid in index.name_to_id.items()
        ),
        key=lambda c: c["avdelning"],
    )
    return jsonify(
        cohort_year=ms.cohort_year,
        ready=[_ser_move(e) for e in ms.ready()],
        pending=[_ser_move(e) for e in ms.pending()],
        off_cohort=[_ser_move(e) for e in ms.off_cohort()],
        excluded=[_ser_move(e) for e in ms.excluded()],
        kept=[_ser_move(e) for e in ms.kept()],
        by_target={t: [_ser_move(e) for e in es] for t, es in ms.by_target().items()},
        avdelningar=avdelningar,
        decisions_count=decisions_count,
        # For the Äventyrare→Utmanare target election (§17):
        utmanare_candidates=utmanare_candidates,
        elected_target=(
            {"avdelning": elected.avdelning, "troop_id": elected.troop_id} if elected else None
        ),
    )


def _validate_manual_troop_id(
    raw: object, config: KarConfig, index: object, *, acknowledged: bool
) -> tuple[int | None, dict | None]:
    """
    Validate a hand-typed troop_id for the Äventyrare→Utmanare election — the one
    place manual entry is allowed (§17), with these guards:
    the group id is rejected outright; the shape must be the observed five digits;
    an id absent from the data is unknown and needs an explicit acknowledgement.
    """
    try:
        tid = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None, {"error": "troop_id måste vara ett heltal", "needs_ack": False}
    if str(tid) == str(config.group_id):
        return None, {
            "error": f"{tid} är kårens id (group_id), inte en avdelning – avvisas",
            "needs_ack": False,
        }
    if not (_TROOP_ID_MIN <= tid <= _TROOP_ID_MAX):
        return None, {
            "error": f"{tid} har fel form – ett troop_id är fem siffror "
            f"({_TROOP_ID_MIN}–{_TROOP_ID_MAX})",
            "needs_ack": False,
        }
    if tid not in index.id_to_name and not acknowledged:  # type: ignore[attr-defined]
        return None, {
            "error": f"okänt troop_id {tid} – finns inte i data (ny/tom avdelning?). "
            "Bekräfta för att fortsätta.",
            "needs_ack": True,
        }
    return tid, None


@api_bp.post("/uppflyttning/target")
def api_elect_target() -> ResponseReturnValue:
    """
    Elect the Utmanare avdelning the Äventyrare cohort moves into (§17). A target
    may be picked from the dropdown (name → live id) or, for a brand-new avdelning
    too empty to appear in the memberlist, entered by direct troop_id — guarded.
    """
    ml = _memberlist()
    n = resolve_cohort_year(_config_n(), ml.current_term_label)  # may raise -> 409
    data = request.get_json(silent=True) or {}
    avdelning = data.get("avdelning")
    if not avdelning:
        return jsonify(error="avdelning is required"), 400
    index = build_troop_index(ml, _config())
    raw_tid = data.get("troop_id")
    if raw_tid not in (None, ""):
        troop_id, err = _validate_manual_troop_id(
            raw_tid, _config(), index, acknowledged=bool(data.get("acknowledge_unknown"))
        )
        if err is not None:
            return jsonify(err), 400
    else:
        troop_id = index.name_to_id.get(avdelning)
        if troop_id is None:
            return jsonify(
                error=f"{avdelning!r} saknar troop_id i data – ange ett troop_id manuellt "
                "för en ny/tom Utmanare-avdelning",
                needs_ack=False,
            ), 400
    with get_session(current_app.config["SESSIONMAKER"]) as s:
        set_elected_target(s, n, Bracket.UTMANARE, avdelning, int(troop_id), data.get("by"))
    return jsonify(status="ok", troop_id=int(troop_id))


@api_bp.delete("/uppflyttning/target")
def api_clear_target() -> ResponseReturnValue:
    """Clear the target election (moves revert to pending)."""
    ml = _memberlist()
    n = resolve_cohort_year(_config_n(), ml.current_term_label)
    with get_session(current_app.config["SESSIONMAKER"]) as s:
        clear_elected_target(s, n, Bracket.UTMANARE)
    return jsonify(status="ok")


@api_bp.post("/uppflyttning/reset")
def api_reset_uppflyttning() -> ResponseReturnValue:
    """Clear every per-member decision and the target election for this cohort year."""
    ml = _memberlist()
    n = resolve_cohort_year(_config_n(), ml.current_term_label)
    with get_session(current_app.config["SESSIONMAKER"]) as s:
        cleared = clear_all_decisions(s, n)
        clear_elected_target(s, n, Bracket.UTMANARE)
    return jsonify(status="ok", cleared=cleared)


@api_bp.post("/uppflyttning/decision")
def api_set_decision() -> ResponseReturnValue:
    """Set a per-member decision: target override, stay-a-year, or acknowledge (§17)."""
    ml = _memberlist()
    n = resolve_cohort_year(_config_n(), ml.current_term_label)  # may raise -> 409
    data = request.get_json(silent=True) or {}
    member_no = data.get("member_no")
    if not member_no:
        return jsonify(error="member_no is required"), 400
    with get_session(current_app.config["SESSIONMAKER"]) as s:
        upsert_decision(
            s,
            n,
            str(member_no),
            target_avdelning=data.get("target_avdelning"),
            stay_until=data.get("stay_until"),
            acknowledged=data.get("acknowledged"),
            by=data.get("by"),
        )
    return jsonify(status="ok", entry=_entry_for(ml, str(member_no)))


@api_bp.delete("/uppflyttning/decision")
def api_clear_decision() -> ResponseReturnValue:
    """Remove a member's stored decision (reverts to the computed default)."""
    ml = _memberlist()
    n = resolve_cohort_year(_config_n(), ml.current_term_label)
    member_no = request.args.get("member_no")
    if not member_no:
        return jsonify(error="member_no is required"), 400
    with get_session(current_app.config["SESSIONMAKER"]) as s:
        clear_decision(s, n, member_no)
    return jsonify(status="ok", entry=_entry_for(ml, member_no))


@api_bp.get("/uppflyttning/changelist.xlsx")
def api_changelist() -> ResponseReturnValue:
    """Stream the changelist workbook; 409 until off-cohort is acknowledged (§17)."""
    ml = _memberlist()
    ms = _master_set(ml)
    ack_by = request.args.get("ack_by")
    now = datetime.now(UTC)
    try:
        data = build_changelist(
            ms,
            kar_name=_settings().kar_name,
            term_label=ml.current_term_label,
            generated_at=now,
            config_version="placeholder" if _config().placeholder else "custom",
            ack_by=ack_by,
            ack_at=now if ack_by else None,
        )
    except ChangelistAckRequired as e:
        return jsonify(error=str(e), off_cohort=[_ser_move(x) for x in ms.off_cohort()]), 409
    return Response(
        data,
        mimetype=_XLSX_MIME,
        headers={
            "Content-Disposition": "attachment; filename=uppflyttning.xlsx",
        },
    )


@api_bp.get("/membership/drafts")
def api_membership_drafts() -> ResponseReturnValue:
    """Applicants with copy-paste email drafts (§10); fails soft per variant."""
    variant = request.args.get("variant", "waiting")
    if variant not in ("waiting", "awaiting_approval"):
        variant = "waiting"
    try:
        ml = _memberlist(variant)
    except _FETCH_ERRORS as e:
        return jsonify(variant=variant, unavailable=True, reason=str(e), applicants=[])
    try:
        n = resolve_cohort_year(_config_n(), ml.current_term_label)
    except CohortYearConflict:
        n = None
    with get_session(current_app.config["SESSIONMAKER"]) as s:
        templates = templates_by_key(s)
    drafts = generate_drafts(ml.members, _config(), n, templates, _settings().kar_name)
    by_no = {m.member_no: m for m in ml.members}
    return jsonify(
        variant=variant,
        unavailable=False,
        applicants=[
            {
                "member_no": d.member_no,
                "name": by_no[d.member_no].full_name if d.member_no in by_no else d.member_no,
                "unit": by_no[d.member_no].unit if d.member_no in by_no else None,
                "kind": d.kind,
                "to": d.to,
                "subject": d.subject,
                "body": d.body,
                "unsendable": d.unsendable,
            }
            for d in drafts
        ],
    )


@api_bp.get("/templates")
def api_templates() -> ResponseReturnValue:
    """Effective email templates (shipped defaults plus DB overrides)."""
    with get_session(current_app.config["SESSIONMAKER"]) as s:
        return jsonify(templates=effective_templates(s))


@api_bp.put("/templates/<key>")
def api_template_update(key: str) -> ResponseReturnValue:
    """Update an email template's subject/body (DB override)."""
    data = request.get_json(silent=True) or {}
    subject, body = data.get("subject"), data.get("body")
    if not subject or not body:
        return jsonify(error="subject and body are required"), 400
    try:
        with get_session(current_app.config["SESSIONMAKER"]) as s:
            upsert_template(s, key, subject, body, data.get("by"))
    except KeyError:
        return jsonify(error=f"unknown template key {key!r}"), 404
    return jsonify(status="ok")


@api_bp.get("/capabilities")
def api_capabilities() -> ResponseReturnValue:
    """What this deployment can do (§12)."""
    return jsonify(capabilities(_settings(), _config()))


@api_bp.get("/api-check")
def api_api_check() -> ResponseReturnValue:
    """Probe each Scoutnet endpoint key with a real read (§12)."""
    return jsonify(api_check(_settings(), current_app.config["SCOUTNET"]))
