from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from scoutnet_membership_manager.db import Base, make_sessionmaker
from scoutnet_membership_manager.scoutnet.client import DEFAULT_FIXTURE, FixtureClient
from scoutnet_membership_manager.scoutnet.models import Member, MemberList, Role
from scoutnet_membership_manager.settings import Mode, Settings
from scoutnet_membership_manager.write import (
    SnapshotError,
    build_snapshot_payload,
    delete_snapshot,
    list_snapshots,
    purge_snapshots,
    write_snapshot,
)

# Substrings that would betray personal data leaking into a snapshot (§8).
_PERSONAL = ("ssno", "first_name", "last_name", "date_of_birth", "personnummer", "address", "@")


def _factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_sessionmaker(engine)


def _settings(tmp_path, **kw):
    return Settings(mode=Mode.FIXTURE, snapshot_dir=tmp_path, **kw)


def test_build_payload_records_placement_and_leadership_no_personal_data():
    scout = Member(
        member_no="100", unit="Hajarna", unit_troop_id=12345, status_code="2", patrol_id=7
    )
    leader = Member(member_no="200", unit="Ledare", unit_troop_id=99999, status_code="2")
    leader.roles = [
        Role(scope="troop", scope_id=12345, role_id=1, role_key="leader", role_name="Ledare"),
        Role(scope="group", scope_id=1025, role_id=2, role_key="other_leader", role_name="X"),
    ]
    # A patrol-scoped 'leader' key is a youth role, never adult leadership (§11).
    patrol_kid = Member(member_no="300", unit="Hajarna", unit_troop_id=12345, status_code="2")
    patrol_kid.roles = [
        Role(scope="patrol", scope_id=555, role_id=3, role_key="leader", role_name="Patrulledare")
    ]

    ml = MemberList(members=[scout, leader, patrol_kid])
    doc = build_snapshot_payload(
        ml, run_id=None, variant="active", taken_at=datetime(2026, 8, 3, tzinfo=UTC)
    )
    members = doc["members"]

    # Exactly the restorable placement + leadership, and nothing personal.
    assert set(members["100"]) == {"unit", "troop_id", "status", "patrol_id", "leader_of"}
    assert (members["100"]["troop_id"], members["100"]["patrol_id"]) == (12345, 7)
    assert members["100"]["leader_of"] == []
    # Both troop- and group-scoped leader roles recorded.
    assert {(x["scope"], x["scope_id"]) for x in members["200"]["leader_of"]} == {
        ("troop", 12345),
        ("group", 1025),
    }
    # Patrol-scoped role is not leadership.
    assert members["300"]["leader_of"] == []


def test_write_snapshot_creates_file_and_index_row(tmp_path):
    client = FixtureClient(DEFAULT_FIXTURE)
    factory = _factory()
    now = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)

    info = write_snapshot(client, _settings(tmp_path), factory, run_id="run-1", now=now)

    assert info.member_count == 182
    path = Path(info.path)
    assert path.exists() and path.parent == tmp_path
    doc = json.loads(path.read_text("utf-8"))
    assert doc["kind"] == "memberlist_snapshot"
    assert doc["run_id"] == "run-1"
    assert doc["member_count"] == 182
    assert len(doc["members"]) == 182

    rows = list_snapshots(factory)
    assert len(rows) == 1
    assert rows[0].run_id == "run-1"
    assert rows[0].size_bytes > 0


def test_snapshot_file_holds_no_personal_data(tmp_path):
    client = FixtureClient(DEFAULT_FIXTURE)
    info = write_snapshot(
        client, _settings(tmp_path), _factory(), now=datetime(2026, 8, 3, tzinfo=UTC)
    )
    text = Path(info.path).read_text("utf-8")
    for bad in _PERSONAL:
        assert bad not in text, f"snapshot leaked personal-data marker {bad!r}"


def test_write_snapshot_requires_snapshot_dir():
    client = FixtureClient(DEFAULT_FIXTURE)
    settings = Settings(mode=Mode.FIXTURE, snapshot_dir=None)
    with pytest.raises(SnapshotError):
        write_snapshot(client, settings, _factory())


def test_purge_keeps_recent_and_within_window(tmp_path):
    client = FixtureClient(DEFAULT_FIXTURE)
    settings = _settings(tmp_path, snapshot_retention_days=30)
    factory = _factory()
    now = datetime(2026, 8, 3, tzinfo=UTC)

    old = write_snapshot(client, settings, factory, run_id="old", now=now - timedelta(days=100))
    mid = write_snapshot(client, settings, factory, run_id="mid", now=now - timedelta(days=40))
    recent = write_snapshot(client, settings, factory, run_id="recent", now=now - timedelta(days=5))

    purged = {p.id for p in purge_snapshots(settings, factory, now=now)}

    assert old.id in purged and mid.id in purged  # older than the window, not newest
    assert recent.id not in purged
    assert not Path(old.path).exists() and not Path(mid.path).exists()
    assert Path(recent.path).exists()
    assert {r.id for r in list_snapshots(factory)} == {recent.id}


def test_purge_always_keeps_most_recent_even_if_old(tmp_path):
    client = FixtureClient(DEFAULT_FIXTURE)
    settings = _settings(tmp_path, snapshot_retention_days=30)
    factory = _factory()
    now = datetime(2026, 8, 3, tzinfo=UTC)

    only = write_snapshot(client, settings, factory, run_id="only", now=now - timedelta(days=365))

    assert purge_snapshots(settings, factory, now=now) == []  # newest is kept regardless of age
    assert Path(only.path).exists()
    assert len(list_snapshots(factory)) == 1


def test_delete_snapshot_removes_file_and_row(tmp_path):
    client = FixtureClient(DEFAULT_FIXTURE)
    factory = _factory()
    info = write_snapshot(
        client, _settings(tmp_path), factory, now=datetime(2026, 8, 3, tzinfo=UTC)
    )
    assert Path(info.path).exists()

    deleted = delete_snapshot(factory, info.id)

    assert deleted is not None and deleted.id == info.id
    assert not Path(info.path).exists()
    assert list_snapshots(factory) == []
    assert delete_snapshot(factory, "no-such-id") is None  # missing id is a no-op
