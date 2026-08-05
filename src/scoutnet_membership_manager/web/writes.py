"""
Write endpoints (Phase 2, CLAUDE.md §6, §8). All gated to ``read_write`` mode.

Dry-run is synchronous (fast, no side effects). Execute / resume / undo start a
background run via the RunManager and return a ``run_id`` the frontend polls;
progress is server-side state in the journal, so closing the tab is harmless.
"""

from __future__ import annotations

import uuid

from flask import Blueprint, current_app, jsonify, request
from flask.typing import ResponseReturnValue
from sqlalchemy import select

from scoutnet_membership_manager.db import WriteJournal, WriteRun, get_session
from scoutnet_membership_manager.roster import build_troop_index
from scoutnet_membership_manager.settings import Mode, Settings
from scoutnet_membership_manager.uppflyttning import scope_master_set
from scoutnet_membership_manager.uppflyttning.models import MasterSet
from scoutnet_membership_manager.web.api import _group_from, _master_set, _memberlist
from scoutnet_membership_manager.web.runs import run_active_in_db
from scoutnet_membership_manager.write import (
    IntendedMove,
    PreflightItem,
    RunMode,
    RunResult,
    WriteExecutor,
    assert_allowlist,
    delete_snapshot,
    list_snapshots,
    undo_available,
)

writes_bp = Blueprint("writes", __name__, url_prefix="/api")

_HTTP_FORBIDDEN = 403
_HTTP_CONFLICT = 409
_HTTP_ACCEPTED = 202
_HTTP_BAD_REQUEST = 400
_HTTP_NOT_FOUND = 404


def _settings() -> Settings:
    return current_app.config["SETTINGS"]


def _sm() -> object:
    return current_app.config["SESSIONMAKER"]


def _read_write_or_403() -> ResponseReturnValue | None:
    """Every write endpoint refuses outside read_write mode (§6)."""
    mode = _settings().mode
    if mode is not Mode.READ_WRITE:
        return jsonify(
            error=f"write operations require read_write mode (current: {mode.value})"
        ), _HTTP_FORBIDDEN
    return None


def _executor() -> WriteExecutor:
    return WriteExecutor(current_app.config["SCOUTNET"], _settings(), _sm())


def _moves_from_master(master_set: MasterSet) -> list[IntendedMove]:
    """The reviewed, override-applied set of ready moves (§17)."""
    return [
        IntendedMove(
            e.member_no, e.source_troop_id, e.target_troop_id, label=e.target_avdelning or ""
        )
        for e in master_set.ready()
    ]


# --- serialisation ---------------------------------------------------------


def _ser_preflight(p: PreflightItem) -> dict:
    return {
        "member_no": p.move.member_no,
        "target_troop_id": p.move.target_troop_id,
        "label": p.move.label,
        "category": str(p.category),
        "current_troop_id": p.current_troop_id,
        "current_status": p.current_status,
        "reason": p.reason,
    }


def _ser_result(r: RunResult) -> dict:
    return {
        "mode": str(r.mode),
        "run_id": r.run_id,
        "run_state": r.run_state,
        "snapshot_id": r.snapshot_id,
        "preflight": [_ser_preflight(p) for p in r.preflight],
        "chunks": [
            {
                "chunk_id": c.chunk_id,
                "member_nos": c.member_nos,
                "payload": c.payload,
                "state": c.state,
                "error": c.error,
            }
            for c in r.chunks
        ],
        "reconcile": r.reconcile,
        "failed_chunk": r.failed_chunk,
        "error": r.error,
        "journal": r.journal,
    }


def _run_status(run_id: str) -> dict | None:
    with get_session(_sm()) as s:
        run = s.get(WriteRun, run_id)
        if run is None:
            return None
        rows = (
            s.execute(
                select(WriteJournal)
                .where(WriteJournal.run_id == run_id)
                .order_by(WriteJournal.chunk_id)
            )
            .scalars()
            .all()
        )
        summary: dict[str, int] = {}
        members = []
        for row in rows:
            summary[row.state] = summary.get(row.state, 0) + 1
            members.append(
                {
                    "member_no": row.member_no,
                    "chunk_id": row.chunk_id,
                    "state": row.state,
                    "intended_troop_id": row.intended_troop_id,
                    "source_troop_id": row.source_troop_id,
                    "error": row.error,
                }
            )
        return {
            "run_id": run.id,
            "kind": run.kind,
            "mode": run.mode,
            "state": run.state,
            "cohort_year": run.cohort_year,
            "parent_run_id": run.parent_run_id,
            "snapshot_id": run.snapshot_id,
            "error": run.error,
            "journal": summary,
            "members": members,
        }


# --- endpoints -------------------------------------------------------------


@writes_bp.post("/uppflyttning/run")
def api_uppflyttning_run() -> ResponseReturnValue:
    """Dry-run (sync) or start an execute run (background) of the uppflyttning (§8, §17)."""
    if (err := _read_write_or_403()) is not None:
        return err
    data = request.get_json(silent=True) or {}
    execute = data.get("mode") == "execute"

    ml = _memberlist()
    # Scoped to the selected transition group so a run only writes what the
    # operator is looking at — never a transition they did not choose (§7 A).
    ms = scope_master_set(_master_set(ml), _group_from(data.get("group")))
    moves = _moves_from_master(ms)

    # Off-cohort acknowledgement gate before an execute run (§17).
    if execute and ms.off_cohort() and not data.get("ack_by"):
        return jsonify(
            error="off-cohort members must be acknowledged before execution",
            off_cohort=[{"member_no": e.member_no, "name": e.member_name} for e in ms.off_cohort()],
        ), _HTTP_CONFLICT
    if not moves:
        return jsonify(error="no members are ready to move"), _HTTP_BAD_REQUEST

    executor = _executor()

    # A production uppflyttning is not per-member allowlisted (§8): the operator is
    # authorised by read_write mode + config, and the change is authorised by their
    # deliberate save + this dry-run review + the confirmation. The write allowlist
    # is a stage-2 verify testing safeguard only. Dry-run and execute both proceed.
    if not execute:
        result = executor.run(moves, kind="uppflyttning", cohort_year=ms.cohort_year)
        return jsonify(_ser_result(result))
    return _launch("uppflyttning", ms.cohort_year, moves, executor)


@writes_bp.get("/write/verify")
def api_verify_info() -> ResponseReturnValue:
    """
    What the verify blade shows read-only: the allowlist and mode (§8). The
    allowlist is deployment config (SCOUTNET_WRITE_ALLOWLIST) and is not editable
    here — keys and allowlist never come from the UI (hard rule 7, §13).
    """
    if (err := _read_write_or_403()) is not None:
        return err
    memberlist = current_app.config["SCOUTNET"].memberlist("active")
    index = build_troop_index(memberlist, current_app.config["KAR_CONFIG"])
    by_no = memberlist.by_member_no()
    avdelningar = sorted(
        ({"avdelning": name, "troop_id": tid} for name, tid in index.name_to_id.items()),
        key=lambda a: a["avdelning"],
    )
    # Allowlisted members with names resolved from Scoutnet, for the picker.
    allowlist = [
        {"member_no": m, "name": by_no[m].full_name if m in by_no else None}
        for m in _settings().write_allowlist
    ]
    return jsonify(allowlist=allowlist, mode=_settings().mode.value, avdelningar=avdelningar)


@writes_bp.post("/write/verify")
def api_verify() -> ResponseReturnValue:
    """
    Stage-2 single-member move (§8): dry-run (sync) or background execute, on one
    allowlisted member. The web equivalent of the ``verify-write`` CLI; undo and
    status reuse the shared run endpoints.
    """
    if (err := _read_write_or_403()) is not None:
        return err
    data = request.get_json(silent=True) or {}
    member_no = str(data.get("member_no") or "").strip()
    raw_target = data.get("target_troop_id")
    if not member_no or raw_target is None:
        return jsonify(error="member_no and target_troop_id are required"), _HTTP_BAD_REQUEST
    try:
        target = int(raw_target)
    except (TypeError, ValueError):
        return jsonify(error="target_troop_id must be an integer"), _HTTP_BAD_REQUEST

    client = current_app.config["SCOUTNET"]
    memberlist = client.memberlist("active", fresh=True)
    member = memberlist.by_member_no().get(member_no)
    if member is None:
        return jsonify(error=f"member {member_no} not in active roster"), _HTTP_NOT_FOUND
    index = build_troop_index(memberlist, current_app.config["KAR_CONFIG"])
    label = next((name for name, tid in index.name_to_id.items() if tid == target), "")
    moves = [IntendedMove(member_no, member.unit_troop_id, target, label=label)]
    assert_allowlist(_settings(), moves)  # clean 400 on violation (errorhandler)
    executor = _executor()
    # A deliberate single-member test may target a leader (e.g. the operator's own
    # account), so it does not apply the uppflyttning leader-exclusion (§17).
    if data.get("mode") != "execute":
        return jsonify(
            _ser_result(executor.run(moves, kind="stage2_verify", exclude_leaders=False))
        )
    return _launch("stage2_verify", None, moves, executor, exclude_leaders=False)


@writes_bp.post("/write/runs/<run_id>/resume")
def api_resume(run_id: str) -> ResponseReturnValue:
    """Resume an interrupted/failed run from its journal (background, §8)."""
    if (err := _read_write_or_403()) is not None:
        return err
    executor = _executor()
    if _busy():
        return jsonify(error="a write run is already in progress"), _HTTP_CONFLICT

    def _job() -> None:
        executor.resume(run_id)

    current_app.config["RUN_MANAGER"].launch(_job)
    return jsonify(run_id=run_id, status="resuming"), _HTTP_ACCEPTED


@writes_bp.post("/write/runs/<run_id>/undo")
def api_undo(run_id: str) -> ResponseReturnValue:
    """Undo a run — dry-run (sync) or background execute (§8)."""
    if (err := _read_write_or_403()) is not None:
        return err
    if not undo_available(_sm(), run_id):
        return jsonify(
            error="undo unavailable: the run's snapshot is no longer retained"
        ), _HTTP_CONFLICT
    executor = _executor()
    if (
        request.args.get("mode") != "execute"
        and (request.get_json(silent=True) or {}).get("mode") != "execute"
    ):
        return jsonify(_ser_result(executor.undo(run_id, mode=RunMode.DRY_RUN)))
    if _busy():
        return jsonify(error="a write run is already in progress"), _HTTP_CONFLICT
    new_run_id = str(uuid.uuid4())

    def _job() -> None:
        executor.undo(run_id, mode=RunMode.EXECUTE, new_run_id=new_run_id)

    current_app.config["RUN_MANAGER"].launch(_job)
    return jsonify(run_id=new_run_id, parent_run_id=run_id, status="undoing"), _HTTP_ACCEPTED


@writes_bp.get("/write/runs")
def api_list_runs() -> ResponseReturnValue:
    """All write runs, newest first."""
    if (err := _read_write_or_403()) is not None:
        return err
    with get_session(_sm()) as s:
        runs = s.execute(select(WriteRun).order_by(WriteRun.created_at.desc())).scalars().all()
        payload = [
            {
                "run_id": r.id,
                "kind": r.kind,
                "mode": r.mode,
                "state": r.state,
                "cohort_year": r.cohort_year,
                "parent_run_id": r.parent_run_id,
            }
            for r in runs
        ]
    return jsonify(runs=payload)


@writes_bp.get("/write/runs/<run_id>")
def api_run_status(run_id: str) -> ResponseReturnValue:
    """Server-side run state for polling (§8): journal counts + per-member state."""
    if (err := _read_write_or_403()) is not None:
        return err
    status = _run_status(run_id)
    if status is None:
        return jsonify(error=f"unknown run {run_id!r}"), _HTTP_NOT_FOUND
    status["undo_available"] = undo_available(_sm(), run_id)
    return jsonify(status)


@writes_bp.get("/write/snapshots")
def api_list_snapshots() -> ResponseReturnValue:
    """Snapshots with timestamp, size and originating run (§8)."""
    if (err := _read_write_or_403()) is not None:
        return err
    snaps = [
        {
            "id": s.id,
            "run_id": s.run_id,
            "size_bytes": s.size_bytes,
            "taken_at": s.taken_at.isoformat(),
        }
        for s in list_snapshots(_sm())
    ]
    return jsonify(snapshots=snaps)


@writes_bp.delete("/write/snapshots/<snapshot_id>")
def api_delete_snapshot(snapshot_id: str) -> ResponseReturnValue:
    """Manually delete a snapshot (§8). Undo of its run becomes unavailable."""
    if (err := _read_write_or_403()) is not None:
        return err
    info = delete_snapshot(_sm(), snapshot_id)
    if info is None:
        return jsonify(error=f"unknown snapshot {snapshot_id!r}"), _HTTP_NOT_FOUND
    return jsonify(status="deleted", id=snapshot_id)


# --- helpers ---------------------------------------------------------------


def _busy() -> bool:
    return current_app.config["RUN_MANAGER"].busy() or run_active_in_db(_sm())


def _record_run_failure(
    sm: object, run_id: str, kind: str, cohort_year: int | None, error: str
) -> None:
    """
    Mark a background run failed so the frontend poll returns a terminal state
    with a reason, instead of spinning on "Startar körning…" (§8). A run that
    fails before its row is created (e.g. no snapshot volume) has no row yet, so
    it is inserted here; otherwise the existing row is updated in place.
    """
    with get_session(sm) as s:
        run = s.get(WriteRun, run_id)
        if run is None:
            s.add(
                WriteRun(
                    id=run_id,
                    kind=kind,
                    cohort_year=cohort_year,
                    mode=RunMode.EXECUTE.value,
                    state="failed",
                    error=error,
                )
            )
        else:
            run.state = "failed"
            run.error = error


def _launch(
    kind: str,
    cohort_year: int | None,
    moves: list[IntendedMove],
    executor: WriteExecutor,
    *,
    exclude_leaders: bool = True,
) -> ResponseReturnValue:
    if _busy():
        return jsonify(error="a write run is already in progress"), _HTTP_CONFLICT
    run_id = str(uuid.uuid4())
    # Captured here in the request context: _job runs in a background thread where
    # current_app (and thus _sm()) is not bound.
    sm = _sm()

    def _job() -> None:
        try:
            executor.run(
                moves,
                kind=kind,
                cohort_year=cohort_year,
                mode=RunMode.EXECUTE,
                run_id=run_id,
                exclude_leaders=exclude_leaders,
            )
        except Exception as exc:
            # Persist any failure so the UI reports it instead of spinning; then
            # re-raise so the traceback still reaches the logs.
            _record_run_failure(sm, run_id, kind, cohort_year, str(exc))
            raise

    current_app.config["RUN_MANAGER"].launch(_job)
    return jsonify(run_id=run_id, status="started"), _HTTP_ACCEPTED
