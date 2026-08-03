"""Read-only JSON API (Phase 1). No write endpoints exist."""

from __future__ import annotations

from datetime import UTC, datetime

from flask import Blueprint, Response, current_app, jsonify, request

from karverktyg.db.session import get_session
from karverktyg.export import ChangelistAckRequired, build_changelist
from karverktyg.findings import compute_findings
from karverktyg.membership import effective_templates, generate_drafts, upsert_template
from karverktyg.membership.templates import templates_by_key
from karverktyg.uppflyttning import compute_master_set
from karverktyg.uppflyttning.cohort import CohortYearConflict, resolve_cohort_year
from karverktyg.uppflyttning.models import MoveEntry
from karverktyg.views import dues_by_avdelning, overview
from karverktyg.web.capabilities import capabilities

api_bp = Blueprint("api", __name__, url_prefix="/api")

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_SEVERITY_ORDER = {"security": 0, "warning": 1, "info": 2}


def _settings():
    return current_app.config["SETTINGS"]


def _config():
    return current_app.config["KAR_CONFIG"]


def _memberlist(variant: str = "active"):
    return current_app.config["SCOUTNET"].memberlist(variant)


def _config_n() -> int | None:
    s = _settings()
    return s.cohort_year if s.cohort_year is not None else _config().cohort_year_n


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
    }


@api_bp.get("/overview")
def api_overview():
    return jsonify(overview(_memberlist(), _settings()))


@api_bp.get("/dues")
def api_dues():
    ml = _memberlist()
    return jsonify(term=ml.prev_term_label, avdelningar=dues_by_avdelning(ml))


@api_bp.get("/waiting")
def api_waiting():
    def ser(ml):
        return [{"member_no": m.member_no, "name": m.full_name, "unit": m.unit} for m in ml.members]

    return jsonify(
        waiting=ser(_memberlist("waiting")), awaiting_approval=ser(_memberlist("awaiting_approval"))
    )


@api_bp.get("/findings")
def api_findings():
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
def api_uppflyttning():
    ml = _memberlist()
    ms = compute_master_set(ml, _config(), _config_n(), ml.current_term_label)
    return jsonify(
        cohort_year=ms.cohort_year,
        ready=[_ser_move(e) for e in ms.ready()],
        pending=[_ser_move(e) for e in ms.pending()],
        off_cohort=[_ser_move(e) for e in ms.off_cohort()],
        excluded=[_ser_move(e) for e in ms.excluded()],
        by_target={t: [_ser_move(e) for e in es] for t, es in ms.by_target().items()},
    )


@api_bp.get("/uppflyttning/changelist.xlsx")
def api_changelist():
    ml = _memberlist()
    ms = compute_master_set(ml, _config(), _config_n(), ml.current_term_label)
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
def api_membership_drafts():
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
def api_templates():
    with get_session(current_app.config["SESSIONMAKER"]) as s:
        return jsonify(templates=effective_templates(s))


@api_bp.put("/templates/<key>")
def api_template_update(key: str):
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
def api_capabilities():
    return jsonify(capabilities(_settings(), _config()))
