"""Read-only JSON API (Phase 1). No write endpoints exist."""

from __future__ import annotations

from datetime import UTC, datetime

from flask import Blueprint, Response, current_app, jsonify, request
from flask.typing import ResponseReturnValue

from karverktyg.config.models import Bracket, KarConfig
from karverktyg.db.session import get_session
from karverktyg.export import ChangelistAckRequired, build_changelist
from karverktyg.findings import compute_findings
from karverktyg.membership import effective_templates, generate_drafts, upsert_template
from karverktyg.membership.templates import templates_by_key
from karverktyg.roster import build_troop_index
from karverktyg.scoutnet.models import MemberList
from karverktyg.settings import Settings
from karverktyg.uppflyttning import (
    ElectedTarget,
    MasterSet,
    apply_overrides,
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
from karverktyg.views import dues_by_avdelning, overview
from karverktyg.web.capabilities import capabilities

api_bp = Blueprint("api", __name__, url_prefix="/api")

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_SEVERITY_ORDER = {"security": 0, "warning": 1, "info": 2}


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
        "status": str(e.status),
        "transition": str(e.transition),
        "note": e.note,
        "override": e.is_override,
        "acknowledged": e.acknowledged,
    }


@api_bp.get("/overview")
def api_overview() -> ResponseReturnValue:
    """Overview counts and term labels."""
    return jsonify(overview(_memberlist(), _settings()))


@api_bp.get("/dues")
def api_dues() -> ResponseReturnValue:
    """Per-avdelning payment breakdown for the invoiced term."""
    ml = _memberlist()
    return jsonify(term=ml.prev_term_label, avdelningar=dues_by_avdelning(ml))


@api_bp.get("/waiting")
def api_waiting() -> ResponseReturnValue:
    """Waiting list and awaiting-approval applicants."""

    def ser(ml: MemberList) -> list[dict]:
        return [{"member_no": m.member_no, "name": m.full_name, "unit": m.unit} for m in ml.members]

    return jsonify(
        waiting=ser(_memberlist("waiting")), awaiting_approval=ser(_memberlist("awaiting_approval"))
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
        by_target={t: [_ser_move(e) for e in es] for t, es in ms.by_target().items()},
        avdelningar=avdelningar,
        # For the Äventyrare→Utmanare target election (§17):
        utmanare_candidates=utmanare_candidates,
        elected_target=(
            {"avdelning": elected.avdelning, "troop_id": elected.troop_id} if elected else None
        ),
    )


@api_bp.post("/uppflyttning/target")
def api_elect_target() -> ResponseReturnValue:
    """Elect the Utmanare avdelning the Äventyrare cohort moves into (§17)."""
    ml = _memberlist()
    n = resolve_cohort_year(_config_n(), ml.current_term_label)  # may raise -> 409
    data = request.get_json(silent=True) or {}
    avdelning = data.get("avdelning")
    if not avdelning:
        return jsonify(error="avdelning is required"), 400
    index = build_troop_index(ml, _config())
    troop_id = data.get("troop_id") or index.name_to_id.get(avdelning)
    if troop_id is None:
        return jsonify(
            error=f"{avdelning!r} has no resolvable troop_id; supply troop_id for a "
            "not-yet-populated avdelning"
        ), 400
    with get_session(current_app.config["SESSIONMAKER"]) as s:
        set_elected_target(s, n, Bracket.UTMANARE, avdelning, int(troop_id), data.get("by"))
    return jsonify(status="ok")


@api_bp.delete("/uppflyttning/target")
def api_clear_target() -> ResponseReturnValue:
    """Clear the target election (moves revert to pending)."""
    ml = _memberlist()
    n = resolve_cohort_year(_config_n(), ml.current_term_label)
    with get_session(current_app.config["SESSIONMAKER"]) as s:
        clear_elected_target(s, n, Bracket.UTMANARE)
    return jsonify(status="ok")


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
    """Copy-paste membership-request email drafts for applicants (§10)."""
    variant = request.args.get("variant", "waiting")
    if variant not in ("waiting", "awaiting_approval"):
        variant = "waiting"
    ml = _memberlist(variant)
    try:
        n = resolve_cohort_year(_config_n(), ml.current_term_label)
    except CohortYearConflict:
        n = None
    with get_session(current_app.config["SESSIONMAKER"]) as s:
        templates = templates_by_key(s)
    drafts = generate_drafts(ml.members, _config(), n, templates, _settings().kar_name)
    return jsonify(
        variant=variant,
        drafts=[
            {
                "member_no": d.member_no,
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
