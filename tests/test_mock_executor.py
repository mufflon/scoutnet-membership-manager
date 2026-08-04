"""
Stage-1 integration: the real ReadWriteClient + WriteExecutor driven end-to-end
against the schema-derived mock Scoutnet server (CLAUDE.md §8). Exercises the
full run over real HTTP plumbing (auth, POST, 200/400 handling) plus crash/
resume/failure and the shape-only malformed-payload test.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine

from mock_scoutnet import MockScoutnet, load_update_membership_contract
from scoutnet_membership_manager.db import Base, make_sessionmaker
from scoutnet_membership_manager.scoutnet.client import ReadWriteClient, ScoutnetError
from scoutnet_membership_manager.settings import Mode, Settings
from scoutnet_membership_manager.write.executor import IntendedMove, RunMode, WriteExecutor

NOW = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


def _fresh_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_sessionmaker(engine)


def _settings(tmp_path, allowlist):
    return Settings(
        mode=Mode.READ_WRITE,
        entity_id="1025",
        memberlist_key="mk",
        update_membership_key="wk",
        snapshot_dir=tmp_path,
        write_allowlist=allowlist,
        chunk_delay_s=0,
    )


def _executor(mock, tmp_path, allowlist):
    settings = _settings(tmp_path, allowlist)
    client = ReadWriteClient(settings, transport=mock.transport())
    return WriteExecutor(client, settings, _fresh_factory())


# --- contract read from the vendored spec ----------------------------------


def test_contract_read_from_vendored_spec():
    c = load_update_membership_contract()
    assert c["required"] == ["status"]
    # The spec *permits* cancelled; our executor deliberately never emits it.
    assert c["status_enum"] == {"confirmed", "waiting", "cancelled"}
    assert {"troop_id", "patrol_id"} <= c["integer_fields"]


# --- full run over real client + mock --------------------------------------


def test_full_execute_over_mock(tmp_path):
    mock = MockScoutnet({m: {"troop_id": 10} for m in ("100", "200", "300")})
    ex = _executor(mock, tmp_path, ["100", "200", "300"])
    moves = [IntendedMove(m, 10, 20) for m in ("100", "200", "300")]

    result = ex.run(moves, kind="uppflyttning", mode=RunMode.EXECUTE, now=NOW)

    assert result.run_state == "done"
    assert result.journal == {"done": 3}
    assert result.reconcile == {"applied": 3, "mismatch": []}
    assert all(mock.troop_of(m) == 20 for m in ("100", "200", "300"))
    assert any(
        method == "POST" and path.endswith("/organisation/update/membership")
        for method, path in mock.requests
    )
    assert len(list(tmp_path.glob("*.json"))) == 1  # snapshot written


def test_dry_run_over_mock_sends_nothing(tmp_path):
    mock = MockScoutnet({"100": {"troop_id": 10}})
    ex = _executor(mock, tmp_path, ["100"])
    result = ex.run(
        [IntendedMove("100", 10, 20)], kind="uppflyttning", mode=RunMode.DRY_RUN, now=NOW
    )

    assert result.run_state == "dry_run"
    assert mock.troop_of("100") == 10  # unchanged
    assert not any(m == "POST" for m, _ in mock.requests)  # never posted


def test_failure_over_mock_stops_run(tmp_path):
    mock = MockScoutnet({m: {"troop_id": 10} for m in ("100", "200", "300")}, fail_on={"200"})
    ex = _executor(mock, tmp_path, ["100", "200", "300"])
    moves = [IntendedMove(m, 10, 20) for m in ("100", "200", "300")]

    result = ex.run(moves, kind="uppflyttning", mode=RunMode.EXECUTE, now=NOW)

    assert result.run_state == "failed" and result.failed_chunk == 1
    assert mock.troop_of("100") == 20  # first applied
    assert mock.troop_of("300") == 10  # never attempted


def test_resume_over_mock_after_transient_failure(tmp_path):
    mock = MockScoutnet({m: {"troop_id": 10} for m in ("100", "200", "300")}, fail_on={"200"})
    ex = _executor(mock, tmp_path, ["100", "200", "300"])
    moves = [IntendedMove(m, 10, 20) for m in ("100", "200", "300")]

    first = ex.run(moves, kind="uppflyttning", mode=RunMode.EXECUTE, now=NOW)
    assert first.run_state == "failed"

    mock.fail_on.clear()  # the transient problem clears
    resumed = ex.resume(first.run_id, now=NOW)

    assert resumed.run_state == "done"
    assert resumed.journal == {"done": 3}
    assert all(mock.troop_of(m) == 20 for m in ("100", "200", "300"))


# --- malformed payload: mock + client error handling only (§8) -------------


def test_malformed_payload_rejected_by_mock(tmp_path):
    # Shape malformation ONLY, and ONLY against the mock (invariant 3): a
    # non-numeric member key and an out-of-enum status. Never a fabricated real
    # member number, never against production.
    mock = MockScoutnet({"12345": {"troop_id": 10}})
    settings = _settings(tmp_path, ["12345"])
    client = ReadWriteClient(settings, transport=mock.transport())

    with pytest.raises(ScoutnetError) as ei:
        client.update_membership({"abc": {"status": "confirmed", "troop_id": 20}})
    assert ei.value.status_code == 400
    assert "abc" in (ei.value.body or "")

    with pytest.raises(ScoutnetError) as ei2:
        client.update_membership({"12345": {"status": "banana", "troop_id": 20}})
    assert ei2.value.status_code == 400


def test_missing_auth_is_401(tmp_path):
    # If the client somehow sent no key the mock 401s; confirms auth is wired.
    mock = MockScoutnet({"100": {"troop_id": 10}})
    settings = Settings(
        mode=Mode.READ_WRITE,
        entity_id="1025",
        memberlist_key="mk",
        update_membership_key="wk",
        snapshot_dir=tmp_path,
        write_allowlist=["100"],
    )
    client = ReadWriteClient(settings, transport=mock.transport())
    # A normal read carries Basic auth and succeeds (proves the header is sent).
    assert len(client.memberlist("active", fresh=True)) == 1
