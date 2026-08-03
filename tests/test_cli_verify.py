"""verify-write CLI (§8 stage 2): mode gate, dry-run, execute, undo, idempotency."""

from __future__ import annotations

from sqlalchemy import create_engine, select

from karverktyg.cli import main
from karverktyg.db import Base, WriteRun, get_session, make_sessionmaker
from test_executor import FakeReadWrite


def _factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_sessionmaker(engine)


def _rw_env(monkeypatch, tmp_path, allowlist='["100"]'):
    monkeypatch.setenv("SCOUTNET_MODE", "read_write")
    monkeypatch.setenv("SCOUTNET_ENTITY_ID", "1025")
    monkeypatch.setenv("SCOUTNET_MEMBERLIST_KEY", "k")
    monkeypatch.setenv("SCOUTNET_UPDATE_MEMBERSHIP_KEY", "w")
    monkeypatch.setenv("SCOUTNET_WRITE_ALLOWLIST", allowlist)
    monkeypatch.setenv("SCOUTNET_SNAPSHOT_DIR", str(tmp_path))
    monkeypatch.setenv("SCOUTNET_CHUNK_DELAY_S", "0")


def test_verify_write_requires_read_write(monkeypatch):
    monkeypatch.setenv("SCOUTNET_MODE", "fixture")
    assert main(["verify-write", "--member", "100", "--to", "20"]) == 2


def test_verify_write_dry_run_writes_nothing(monkeypatch, tmp_path):
    _rw_env(monkeypatch, tmp_path)
    fake = FakeReadWrite({"100": {"troop_id": 10}})
    monkeypatch.setattr("karverktyg.cli._build_rw", lambda _s: (fake, _factory()))

    assert main(["verify-write", "--member", "100", "--to", "20"]) == 0
    assert fake.calls == []  # dry-run sent nothing
    assert fake._members["100"]["troop_id"] == 10


def test_verify_write_execute_moves_the_member(monkeypatch, tmp_path):
    _rw_env(monkeypatch, tmp_path)
    fake = FakeReadWrite({"100": {"troop_id": 10}})
    monkeypatch.setattr("karverktyg.cli._build_rw", lambda _s: (fake, _factory()))

    assert main(["verify-write", "--member", "100", "--to", "20", "--execute"]) == 0
    assert fake._members["100"]["troop_id"] == 20


def test_verify_write_refuses_off_allowlist(monkeypatch, tmp_path):
    _rw_env(monkeypatch, tmp_path, allowlist='["999"]')  # 100 not allowed
    fake = FakeReadWrite({"100": {"troop_id": 10}})
    monkeypatch.setattr("karverktyg.cli._build_rw", lambda _s: (fake, _factory()))

    assert main(["verify-write", "--member", "100", "--to", "20", "--execute"]) == 1
    assert fake._members["100"]["troop_id"] == 10  # untouched


def test_verify_write_round_trip_and_idempotency(monkeypatch, tmp_path):
    _rw_env(monkeypatch, tmp_path)
    fake = FakeReadWrite({"100": {"troop_id": 10}})
    sm = _factory()
    monkeypatch.setattr("karverktyg.cli._build_rw", lambda _s: (fake, sm))

    # execute + idempotency re-apply
    assert (
        main(["verify-write", "--member", "100", "--to", "20", "--execute", "--idempotency"]) == 0
    )
    assert fake._members["100"]["troop_id"] == 20
    assert len(fake.calls) == 2  # the move, then the idempotency re-apply (no-op)

    # undo the run restores the member
    with get_session(sm) as s:
        run_id = (
            s.execute(select(WriteRun).where(WriteRun.kind == "stage2_verify")).scalars().first().id
        )
    assert main(["verify-write", "--undo-run", run_id, "--execute"]) == 0
    assert fake._members["100"]["troop_id"] == 10
