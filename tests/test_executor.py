from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine

from scoutnet_membership_manager.db import Base, make_sessionmaker
from scoutnet_membership_manager.scoutnet.client import ScoutnetError
from scoutnet_membership_manager.scoutnet.models import Member, MemberList, Role
from scoutnet_membership_manager.settings import Mode, Settings
from scoutnet_membership_manager.write.executor import (
    AllowlistViolation,
    Category,
    ExecutorError,
    IntendedMove,
    RunMode,
    WriteExecutor,
    drift_check,
    write_status_token,
)

NOW = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


class FakeReadWrite:
    """In-process stand-in for ReadWriteClient. Applies troop moves to memory."""

    def __init__(self, members: dict[str, dict]):
        self._members = {k: dict(v) for k, v in members.items()}
        self.calls: list[dict] = []  # update_membership payloads, in order
        self.raise_on: dict[str, Exception] = {}  # member_no -> exception to raise

    def memberlist(self, variant: str = "active", *, fresh: bool = False) -> MemberList:  # noqa: ARG002 - fake ignores variant/fresh
        members = []
        for mno, st in self._members.items():
            m = Member(
                member_no=mno,
                unit_troop_id=st.get("troop_id"),
                status_code=st.get("status", "2"),
                patrol_id=st.get("patrol_id"),
            )
            if st.get("leader"):
                m.roles = [Role("troop", st.get("troop_id") or 999, 1, "leader", "L")]
            members.append(m)
        return MemberList(members=members)

    def update_membership(self, payload: dict) -> dict:
        self.calls.append(payload)
        for mno in payload:
            if mno in self.raise_on:
                raise self.raise_on[mno]
        for mno, fields in payload.items():
            if mno in self._members:  # writing "confirmed" keeps them active (read code "2")
                self._members[mno]["troop_id"] = fields["troop_id"]
        return {"status": "ok"}


def _factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_sessionmaker(engine)


def _settings(tmp_path, allowlist, **kw):
    return Settings(
        mode=Mode.FIXTURE,
        snapshot_dir=tmp_path,
        write_allowlist=allowlist,
        chunk_delay_s=0,  # no real sleep in tests
        **kw,
    )


# --- status mapping / cancelled ban ---------------------------------------


def test_status_map_only_confirmed_and_cancelled_unreachable():
    from scoutnet_membership_manager.write.executor import _STATUS_WRITE_TOKENS

    assert write_status_token("2") == "confirmed"
    with pytest.raises(ExecutorError):
        write_status_token("9")  # unmapped -> refuse to guess
    with pytest.raises(ExecutorError):
        write_status_token(None)
    # Only "confirmed" is producible; "cancelled" can never be emitted (hard rule 3).
    assert set(_STATUS_WRITE_TOKENS.values()) == {"confirmed"}
    assert "cancelled" not in _STATUS_WRITE_TOKENS.values()


# --- allowlist -------------------------------------------------------------


def test_allowlist_refuses_off_list_member(tmp_path):
    # The allowlist is a stage-2 verify testing safeguard; it does not gate a
    # production uppflyttning (kind="uppflyttning"), only the verify path.
    client = FakeReadWrite({"100": {"troop_id": 10}, "200": {"troop_id": 10}})
    ex = WriteExecutor(client, _settings(tmp_path, allowlist=["100"]), _factory())
    moves = [IntendedMove("100", 10, 20), IntendedMove("200", 10, 20)]  # 200 not allowed
    with pytest.raises(AllowlistViolation):
        ex.run(moves, kind="stage2_verify", mode=RunMode.EXECUTE, now=NOW)
    assert client.calls == []  # nothing sent
    # An uppflyttning run is not allowlist-gated — the same off-list move is allowed.
    ex.run(moves, kind="uppflyttning", mode=RunMode.DRY_RUN, now=NOW)  # no raise


# --- dry-run ---------------------------------------------------------------


def test_dry_run_has_no_side_effects_but_faithful_payload(tmp_path):
    client = FakeReadWrite({"100": {"troop_id": 10}})
    sm = _factory()
    ex = WriteExecutor(client, _settings(tmp_path, allowlist=["100"]), sm)
    result = ex.run(
        [IntendedMove("100", 10, 20)], kind="uppflyttning", mode=RunMode.DRY_RUN, now=NOW
    )

    assert result.run_state == "dry_run" and result.run_id is None
    assert client.calls == []  # no send
    assert list(tmp_path.glob("*.json")) == []  # no snapshot file
    from scoutnet_membership_manager.write import list_snapshots

    assert list_snapshots(sm) == []  # no DB rows
    # payload it *would* send is faithful
    assert result.chunks[0].payload == {"100": {"status": "confirmed", "troop_id": 20}}


# --- execute ---------------------------------------------------------------


def test_execute_moves_journals_and_reconciles(tmp_path):
    client = FakeReadWrite({"100": {"troop_id": 10}, "200": {"troop_id": 10}})
    sm = _factory()
    ex = WriteExecutor(client, _settings(tmp_path, allowlist=["100", "200"]), sm)
    moves = [IntendedMove("100", 10, 20), IntendedMove("200", 10, 20)]

    result = ex.run(moves, kind="uppflyttning", mode=RunMode.EXECUTE, now=NOW)

    assert result.run_state == "done"
    assert result.journal == {"done": 2}
    assert result.reconcile == {"applied": 2, "mismatch": []}
    assert client._members["100"]["troop_id"] == 20  # actually moved
    assert len(list(tmp_path.glob("*.json"))) == 1  # snapshot written
    assert len(client.calls) == 2  # chunk size 1 -> one call per member


def test_snapshot_written_before_first_send(tmp_path):
    # Fail on the only member; the snapshot must already exist (taken before send).
    client = FakeReadWrite({"100": {"troop_id": 10}})
    client.raise_on["100"] = ScoutnetError("boom", status_code=400, body="bad")
    sm = _factory()
    ex = WriteExecutor(client, _settings(tmp_path, allowlist=["100"]), sm)

    result = ex.run(
        [IntendedMove("100", 10, 20)], kind="uppflyttning", mode=RunMode.EXECUTE, now=NOW
    )

    assert result.run_state == "failed"
    assert len(list(tmp_path.glob("*.json"))) == 1  # snapshot present despite the failed send


def test_failure_stops_run_leaving_later_chunks_untouched(tmp_path):
    client = FakeReadWrite(
        {"100": {"troop_id": 10}, "200": {"troop_id": 10}, "300": {"troop_id": 10}}
    )
    client.raise_on["200"] = ScoutnetError("boom", status_code=400, body="bad")
    sm = _factory()
    ex = WriteExecutor(client, _settings(tmp_path, allowlist=["100", "200", "300"]), sm)
    moves = [IntendedMove(m, 10, 20) for m in ("100", "200", "300")]

    result = ex.run(moves, kind="uppflyttning", mode=RunMode.EXECUTE, now=NOW)

    assert result.run_state == "failed" and result.failed_chunk == 1
    assert len(client.calls) == 2  # chunk 0 sent, chunk 1 attempted+failed, chunk 2 never tried
    assert client._members["100"]["troop_id"] == 20  # first applied
    assert client._members["300"]["troop_id"] == 10  # third untouched
    assert result.journal == {"done": 1, "failed": 1, "pending": 1}


def test_chunks_are_serial_in_plan_order(tmp_path):
    client = FakeReadWrite({m: {"troop_id": 10} for m in ("100", "200", "300")})
    ex = WriteExecutor(client, _settings(tmp_path, allowlist=["100", "200", "300"]), _factory())
    moves = [IntendedMove(m, 10, 20) for m in ("100", "200", "300")]

    ex.run(moves, kind="uppflyttning", mode=RunMode.EXECUTE, now=NOW)

    sent_order = [next(iter(p)) for p in client.calls]
    assert sent_order == ["100", "200", "300"]  # strictly serial, in order


def test_resume_continues_from_failed_chunk_and_is_idempotent(tmp_path):
    client = FakeReadWrite(
        {"100": {"troop_id": 10}, "200": {"troop_id": 10}, "300": {"troop_id": 10}}
    )
    client.raise_on["200"] = ScoutnetError("boom", status_code=400, body="bad")
    sm = _factory()
    ex = WriteExecutor(client, _settings(tmp_path, allowlist=["100", "200", "300"]), sm)
    moves = [IntendedMove(m, 10, 20) for m in ("100", "200", "300")]

    first = ex.run(moves, kind="uppflyttning", mode=RunMode.EXECUTE, now=NOW)
    assert first.run_state == "failed"
    calls_before = len(client.calls)

    del client.raise_on["200"]  # the transient problem is resolved
    resumed = ex.resume(first.run_id, now=NOW)

    assert resumed.run_state == "done"
    # Only chunks 1 and 2 re-driven; chunk 0 (done) is not re-sent (idempotent skip).
    resumed_members = {next(iter(p)) for p in client.calls[calls_before:]}
    assert resumed_members == {"200", "300"}
    assert client._members["300"]["troop_id"] == 20  # tail applied on resume
    assert resumed.journal == {"done": 3}


# --- pre-flight drift ------------------------------------------------------


def test_drift_check_categories():
    members = MemberList(
        members=[
            Member(member_no="100", unit_troop_id=10, status_code="2"),  # will apply
            Member(member_no="200", unit_troop_id=20, status_code="2"),  # already at target
            Member(member_no="300", unit_troop_id=99, status_code="2"),  # unexpected avdelning
            Member(member_no="400", unit_troop_id=10, status_code="7"),  # unexpected status
            Member(member_no="500", unit_troop_id=10, status_code="2"),  # a leader now
        ]
    )
    members.members[4].roles = [Role("troop", 10, 1, "leader", "L")]
    moves = [IntendedMove(m, 10, 20) for m in ("100", "200", "300", "400", "500", "600")]

    by_no = {p.move.member_no: p for p in drift_check(moves, members)}

    assert by_no["100"].category is Category.WILL_APPLY
    assert by_no["200"].category is Category.ALREADY_APPLIED
    assert by_no["300"].category is Category.DRIFTED
    assert by_no["400"].category is Category.DRIFTED
    assert by_no["500"].category is Category.DRIFTED
    assert by_no["600"].category is Category.DRIFTED  # not in roster at all


def test_drift_check_can_include_leaders():
    members = MemberList(members=[Member(member_no="500", unit_troop_id=10, status_code="2")])
    members.members[0].roles = [Role("troop", 10, 1, "leader", "L")]
    moves = [IntendedMove("500", 10, 20)]
    # Default excludes leaders (uppflyttning rule); explicit single move includes them.
    assert drift_check(moves, members)[0].category is Category.DRIFTED
    assert drift_check(moves, members, exclude_leaders=False)[0].category is Category.WILL_APPLY


def test_execute_moves_a_leader_only_when_not_excluded(tmp_path):
    client = FakeReadWrite({"100": {"troop_id": 10, "leader": True}})
    ex = WriteExecutor(client, _settings(tmp_path, allowlist=["100"]), _factory())
    moves = [IntendedMove("100", 10, 20)]

    default = ex.run(moves, kind="uppflyttning", mode=RunMode.EXECUTE, now=NOW)
    assert default.journal == {}  # leader excluded -> nothing to do
    assert client._members["100"]["troop_id"] == 10

    verify = ex.run(
        moves, kind="stage2_verify", mode=RunMode.EXECUTE, now=NOW, exclude_leaders=False
    )
    assert verify.journal == {"done": 1}
    assert client._members["100"]["troop_id"] == 20  # the deliberate move applied


def test_undo_restores_moved_members(tmp_path):
    client = FakeReadWrite({"100": {"troop_id": 10}, "200": {"troop_id": 10}})
    sm = _factory()
    ex = WriteExecutor(client, _settings(tmp_path, allowlist=["100", "200"]), sm)
    moves = [IntendedMove("100", 10, 20), IntendedMove("200", 10, 20)]

    run = ex.run(moves, kind="uppflyttning", mode=RunMode.EXECUTE, now=NOW)
    assert client._members["100"]["troop_id"] == 20  # moved

    undo = ex.undo(run.run_id, mode=RunMode.EXECUTE, now=NOW)

    assert undo.run_state == "done"
    assert client._members["100"]["troop_id"] == 10  # back where they were
    assert client._members["200"]["troop_id"] == 10


def test_undo_excludes_externally_changed_member(tmp_path):
    client = FakeReadWrite({"100": {"troop_id": 10}, "200": {"troop_id": 10}})
    sm = _factory()
    ex = WriteExecutor(client, _settings(tmp_path, allowlist=["100", "200"]), sm)
    moves = [IntendedMove("100", 10, 20), IntendedMove("200", 10, 20)]
    run = ex.run(moves, kind="uppflyttning", mode=RunMode.EXECUTE, now=NOW)

    # Someone moves 200 elsewhere in Scoutnet after the run.
    client._members["200"]["troop_id"] = 30

    undo = ex.undo(run.run_id, mode=RunMode.EXECUTE, now=NOW)

    assert client._members["100"]["troop_id"] == 10  # restored
    assert client._members["200"]["troop_id"] == 30  # left alone, not overwritten
    drifted = {p.move.member_no for p in undo.preflight if p.category is Category.DRIFTED}
    assert "200" in drifted


def test_undo_dry_run_shows_inverse_and_exclusions(tmp_path):
    client = FakeReadWrite({"100": {"troop_id": 10}, "200": {"troop_id": 10}})
    sm = _factory()
    ex = WriteExecutor(client, _settings(tmp_path, allowlist=["100", "200"]), sm)
    run = ex.run(
        [IntendedMove("100", 10, 20), IntendedMove("200", 10, 20)],
        kind="uppflyttning",
        mode=RunMode.EXECUTE,
        now=NOW,
    )
    client._members["200"]["troop_id"] = 30  # external change

    preview = ex.undo(run.run_id, mode=RunMode.DRY_RUN, now=NOW)

    cats = {p.move.member_no: p.category for p in preview.preflight}
    assert cats["100"] is Category.WILL_APPLY  # will be restored to 10
    assert cats["200"] is Category.DRIFTED  # excluded, with a reason
    planned = {mno for c in preview.chunks for mno in c.member_nos}
    assert planned == {"100"}  # only the restorable one is in the plan
    assert client._members["100"]["troop_id"] == 20  # dry-run changed nothing


def test_undo_unavailable_after_snapshot_purge(tmp_path):
    from scoutnet_membership_manager.write import delete_snapshot, list_snapshots

    client = FakeReadWrite({"100": {"troop_id": 10}})
    sm = _factory()
    ex = WriteExecutor(client, _settings(tmp_path, allowlist=["100"]), sm)
    run = ex.run([IntendedMove("100", 10, 20)], kind="uppflyttning", mode=RunMode.EXECUTE, now=NOW)

    delete_snapshot(sm, list_snapshots(sm)[0].id)  # snapshot purged

    with pytest.raises(ExecutorError):
        ex.undo(run.run_id, mode=RunMode.EXECUTE, now=NOW)


def test_only_will_apply_members_are_sent(tmp_path):
    # 200 is already at target -> excluded from the send; 100 will apply.
    client = FakeReadWrite({"100": {"troop_id": 10}, "200": {"troop_id": 20}})
    ex = WriteExecutor(client, _settings(tmp_path, allowlist=["100", "200"]), _factory())
    moves = [IntendedMove("100", 10, 20), IntendedMove("200", 10, 20)]

    result = ex.run(moves, kind="uppflyttning", mode=RunMode.EXECUTE, now=NOW)

    assert len(client.calls) == 1  # only 100 sent
    assert next(iter(client.calls[0])) == "100"
    assert result.journal == {"done": 1}
