"""
Pre-run snapshots (CLAUDE.md §8).

Before the first request of any bulk run, capture the current placement of
**every** active member — movers and non-movers alike — so a run that touches
someone it should not can be detected and reversed. This is the recovery/undo
"before" board; the intended change (the "delta") lives in ``write_journal``.

**No personal data.** The tool can only ever write ``status`` / ``troop_id`` /
``patrol_id`` (§4), so those three fields plus ``member_no`` are the entire
restorable state — names, personnummer, dates of birth and addresses are never
at risk and never stored here. Leadership (``leader_of``) is recorded too as a
belt-and-suspenders audit record: the tool never moves leaders, but if anything
goes awry we still know who led what.

**A file on the volume, not the database.** The snapshot is an out-of-band
reference file so it survives a database migration or rebuild — the exact
situation in which you might need to read an old state. The DB ``snapshot`` row
is only an index (path, size, timestamp, run) for the UI; the file is
self-describing and readable on its own.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from sqlalchemy import select

from karverktyg.db import Snapshot, get_session
from karverktyg.scoutnet.models import Member, MemberList
from karverktyg.settings import Settings

SNAPSHOT_KIND = "memberlist_snapshot"


class SnapshotError(RuntimeError):
    """A snapshot could not be taken (e.g. no snapshot directory configured)."""


class _MemberlistSource(Protocol):
    """Anything that can serve a parsed memberlist — any of the read clients."""

    def memberlist(self, variant: str = "active") -> MemberList: ...


@dataclass
class SnapshotInfo:
    """Metadata about a stored snapshot (never any personal data)."""

    id: str
    run_id: str | None
    path: str
    size_bytes: int
    taken_at: datetime
    member_count: int | None = None


def _member_entry(m: Member) -> dict:
    """Placement + leadership for one member — the restorable state, no personal data."""
    return {
        # Membership: unit is single-valued (§11), so exactly one troop_id.
        "unit": m.unit,
        "troop_id": m.unit_troop_id,
        "status": m.status_code,
        "patrol_id": m.patrol_id,
        # Leadership audit record: troop-/group-scoped leader roles only. Patrol-
        # scoped youth roles are not leadership and are excluded (Role.is_leader).
        "leader_of": [
            {"scope": r.scope, "scope_id": r.scope_id, "role_key": r.role_key}
            for r in m.roles
            if r.is_leader
        ],
    }


def build_snapshot_payload(
    memberlist: MemberList, *, run_id: str | None, variant: str, taken_at: datetime
) -> dict:
    """
    Build the self-describing snapshot document. Members are keyed by
    ``member_no`` and sorted for a stable, diffable file. Contains no names,
    personnummer, dates of birth, emails, phones or addresses.
    """
    members = {
        m.member_no: _member_entry(m) for m in sorted(memberlist.members, key=lambda x: x.member_no)
    }
    return {
        "kind": SNAPSHOT_KIND,
        "run_id": run_id,
        "variant": variant,
        "taken_at": taken_at.isoformat(),
        "member_count": len(members),
        "members": members,
    }


def _naive_utc(dt: datetime) -> datetime:
    """Normalise to naive UTC, matching how DateTime round-trips from the DB."""
    return dt.astimezone(UTC).replace(tzinfo=None) if dt.tzinfo is not None else dt


def write_snapshot(
    client: _MemberlistSource,
    settings: Settings,
    sessionmaker: object,
    *,
    run_id: str | None = None,
    variant: str = "active",
    now: datetime | None = None,
    memberlist: MemberList | None = None,
) -> SnapshotInfo:
    """
    Capture a snapshot to the volume and index it in the DB. Raises
    ``SnapshotError`` if no ``snapshot_dir`` is configured — a bulk run must not
    proceed without its recovery artifact (§8). Pass ``memberlist`` to reuse a
    read the caller already made (the executor's single pre-flight read).
    """
    if settings.snapshot_dir is None:
        raise SnapshotError(
            "no SCOUTNET_SNAPSHOT_DIR configured; a bulk run requires a snapshot volume (§8)"
        )
    now = now or datetime.now(UTC)
    snapshot_id = str(uuid.uuid4())
    if memberlist is None:
        memberlist = client.memberlist(variant)
    payload = build_snapshot_payload(memberlist, run_id=run_id, variant=variant, taken_at=now)

    directory = Path(settings.snapshot_dir)
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"snapshot-{variant}-{now.strftime('%Y%m%dT%H%M%SZ')}-{snapshot_id[:8]}.json"
    path = directory / filename
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    size_bytes = path.stat().st_size
    taken_at = _naive_utc(now)

    with get_session(sessionmaker) as s:
        s.add(
            Snapshot(
                id=snapshot_id,
                run_id=run_id,
                path=str(path),
                size_bytes=size_bytes,
                taken_at=taken_at,
            )
        )
    return SnapshotInfo(
        id=snapshot_id,
        run_id=run_id,
        path=str(path),
        size_bytes=size_bytes,
        taken_at=taken_at,
        member_count=payload["member_count"],
    )


def list_snapshots(sessionmaker: object) -> list[SnapshotInfo]:
    """All snapshots, newest first — for the UI listing (§8)."""
    with get_session(sessionmaker) as s:
        rows = s.execute(select(Snapshot).order_by(Snapshot.taken_at.desc())).scalars().all()
        return [
            SnapshotInfo(
                id=r.id, run_id=r.run_id, path=r.path, size_bytes=r.size_bytes, taken_at=r.taken_at
            )
            for r in rows
        ]


def _unlink(path: str) -> None:
    Path(path).unlink(missing_ok=True)


def purge_snapshots(
    settings: Settings, sessionmaker: object, *, now: datetime | None = None
) -> list[SnapshotInfo]:
    """
    Time-based purge (§8): delete files (and their index rows) older than the
    retention window, but **always keep the most recent regardless of age** —
    otherwise a run could not be unwound once a later one happens.
    """
    now = now or datetime.now(UTC)
    cutoff = _naive_utc(now) - timedelta(days=settings.snapshot_retention_days)
    purged: list[SnapshotInfo] = []
    with get_session(sessionmaker) as s:
        rows = s.execute(select(Snapshot).order_by(Snapshot.taken_at.desc())).scalars().all()
        for index, row in enumerate(rows):
            if index == 0:  # newest — always kept
                continue
            if row.taken_at < cutoff:
                info = SnapshotInfo(
                    id=row.id,
                    run_id=row.run_id,
                    path=row.path,
                    size_bytes=row.size_bytes,
                    taken_at=row.taken_at,
                )
                _unlink(row.path)
                s.delete(row)
                purged.append(info)
    return purged


def delete_snapshot(sessionmaker: object, snapshot_id: str) -> SnapshotInfo | None:
    """Manually delete one snapshot's file and index row (§8). None if not found."""
    with get_session(sessionmaker) as s:
        row = s.get(Snapshot, snapshot_id)
        if row is None:
            return None
        info = SnapshotInfo(
            id=row.id,
            run_id=row.run_id,
            path=row.path,
            size_bytes=row.size_bytes,
            taken_at=row.taken_at,
        )
        _unlink(row.path)
        s.delete(row)
    return info
