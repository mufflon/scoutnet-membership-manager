"""
Write executor (CLAUDE.md §8).

Orchestrates a bulk membership write as a sequence of safety steps:

    allowlist -> one live read -> {snapshot + pre-flight drift check}
              -> journal -> serial chunk loop (per-chunk status re-read)
              -> reconcile

Invariants enforced here:

* **Dry-run is the default** (hard rule 4). A dry run performs no side effects —
  no snapshot, no journal, no send — but builds the exact payloads it *would*
  send, sharing that path with execute so the preview is faithful.
* **Chunk size defaults to 1 and chunks are strictly serial** (hard rules 5, §8);
  nothing here assumes a multi-member chunk is atomic.
* **Any non-200 stops the run** — no auto-retry, no next chunk (§8).
* **``cancelled`` is never produced.** The status map only ever emits
  ``confirmed`` (hard rule 3); an unmapped status raises rather than guessing.
* **The allowlist bounds the blast radius**: a member not on it is refused
  before anything happens (§8, HANDOVER §4).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

import httpx
from sqlalchemy import select, update

from karverktyg.db import Snapshot, WriteJournal, WriteRun, get_session
from karverktyg.scoutnet.client import ScoutnetError
from karverktyg.scoutnet.models import MemberList
from karverktyg.settings import Settings
from karverktyg.write.snapshot import write_snapshot

# Observed memberlist raw_value for "Aktiv" (§4). Every uppflyttning mover is
# active, so this is the only read-status we need to map for now.
ACTIVE_STATUS_CODE = "2"

# Write vocabulary (§3, §4). Read codes -> the strings update/membership expects.
# Only "confirmed" is needed for uppflyttning. Deliberately no "cancelled" entry:
# it is banned (hard rule 3) and must be unreachable, asserted by a test.
_STATUS_WRITE_TOKENS = {ACTIVE_STATUS_CODE: "confirmed"}

# A write fails on our own error or any httpx failure; either stops the run (§8).
_WRITE_ERRORS = (ScoutnetError, httpx.HTTPError)


class ExecutorError(RuntimeError):
    """A run could not proceed or a chunk failed."""


class AllowlistViolation(ExecutorError):
    """A member number in the intent is not on the write allowlist (§8)."""


def write_status_token(status_code: str | None) -> str:
    """
    Map a read status code to the write vocabulary (§3). Raises on an unmapped
    code — never guesses, and never returns ``cancelled``.
    """
    token = _STATUS_WRITE_TOKENS.get(status_code or "")
    if token is None:
        raise ExecutorError(
            f"no write-status mapping for status_code {status_code!r}; refusing to guess"
        )
    return token


class Category(StrEnum):
    """Pre-flight classification of one intended move against live state (§8)."""

    WILL_APPLY = "will_apply"
    ALREADY_APPLIED = "already_applied"  # already at target — a no-op
    DRIFTED = "drifted"  # unexpected placement / status / leader / gone


class RunMode(StrEnum):
    """Whether the run sends to Scoutnet."""

    DRY_RUN = "dry_run"
    EXECUTE = "execute"


@dataclass
class IntendedMove:
    """One member's intended move: put them in ``target_troop_id`` (§8)."""

    member_no: str
    source_troop_id: int | None
    target_troop_id: int
    label: str = ""  # target avdelning name, display only


@dataclass
class PreflightItem:
    """A move plus how it compares to current live state (§8 drift check)."""

    move: IntendedMove
    category: Category
    current_troop_id: int | None
    current_status: str | None
    reason: str = ""


@dataclass
class ChunkResult:
    """Outcome of one chunk (or, in dry-run, the payload that would be sent)."""

    chunk_id: int
    member_nos: list[str]
    payload: dict
    state: str  # planned | done | failed
    error: str | None = None


@dataclass
class RunResult:
    """The full outcome of a run, for the UI and tests."""

    mode: RunMode
    run_id: str | None
    preflight: list[PreflightItem]
    chunks: list[ChunkResult]
    run_state: str  # dry_run | done | failed
    snapshot_id: str | None = None
    reconcile: dict | None = None
    failed_chunk: int | None = None
    error: str | None = None
    journal: dict[str, int] = field(default_factory=dict)  # state -> count


class _ReadWrite(Protocol):
    """A read/write Scoutnet client — the real ``ReadWriteClient`` or a fake."""

    def memberlist(self, variant: str = "active", *, fresh: bool = False) -> MemberList: ...
    def update_membership(self, payload: dict) -> dict: ...


def drift_check(moves: list[IntendedMove], memberlist: MemberList) -> list[PreflightItem]:
    """
    Compare each intended move to current live state (§8). ``will_apply`` only
    when the member is still in the expected source, still active and not a
    leader; ``already_applied`` when already at target; ``drifted`` otherwise.
    """
    by_no = memberlist.by_member_no()
    items: list[PreflightItem] = []
    for mv in moves:
        m = by_no.get(mv.member_no)
        if m is None:
            items.append(PreflightItem(mv, Category.DRIFTED, None, None, "not in active roster"))
            continue
        cur, status = m.unit_troop_id, m.status_code
        if cur == mv.target_troop_id:
            items.append(
                PreflightItem(mv, Category.ALREADY_APPLIED, cur, status, "already at target")
            )
        elif m.is_leader:
            items.append(
                PreflightItem(mv, Category.DRIFTED, cur, status, "now holds a leader role")
            )
        elif mv.source_troop_id is not None and cur != mv.source_troop_id:
            items.append(
                PreflightItem(mv, Category.DRIFTED, cur, status, f"in unexpected avdelning {cur}")
            )
        elif status != ACTIVE_STATUS_CODE:
            items.append(
                PreflightItem(mv, Category.DRIFTED, cur, status, f"unexpected status {status!r}")
            )
        else:
            items.append(PreflightItem(mv, Category.WILL_APPLY, cur, status, ""))
    return items


def _chunk(items: list, size: int) -> list[list]:
    size = max(1, size)
    return [items[i : i + size] for i in range(0, len(items), size)]


def assert_allowlist(settings: Settings, moves: list[IntendedMove]) -> None:
    """
    Refuse if any member is not on the write allowlist (§8, HANDOVER §4). Callable
    synchronously by the API so a violation is a clean 400, not a dead thread.
    """
    offenders = sorted({m.member_no for m in moves} - set(settings.write_allowlist))
    if offenders:
        raise AllowlistViolation(
            f"{len(offenders)} member(s) not on the write allowlist: {offenders[:5]}"
        )


def undo_available(sessionmaker: object, run_id: str) -> bool:
    """
    Whether ``run_id`` can be undone: the run exists and its snapshot is still
    retained (§8). Once the snapshot is purged, undo is gone and the UI says so.
    """
    with get_session(sessionmaker) as s:
        run = s.get(WriteRun, run_id)
        snap = s.execute(select(Snapshot).where(Snapshot.run_id == run_id)).scalars().first()
    return run is not None and snap is not None


def build_inverse_moves(sessionmaker: object, run_id: str) -> list[IntendedMove]:
    """
    The inverse of the moves ``run_id`` actually applied (§8). Only ``done``
    journal rows are reversed, and each target is the member's **observed prior**
    ``source_troop_id`` — never the intended change. A row with no prior troop
    is skipped (the endpoint cannot restore an absent placement); the pre-flight
    drift check then excludes any member since moved elsewhere.
    """
    with get_session(sessionmaker) as s:
        rows = (
            s.execute(
                select(WriteJournal).where(
                    WriteJournal.run_id == run_id, WriteJournal.state == "done"
                )
            )
            .scalars()
            .all()
        )
        return [
            IntendedMove(
                member_no=r.member_no,
                source_troop_id=r.intended_troop_id,  # where this run left them
                target_troop_id=r.source_troop_id,  # put them back (observed prior)
                label="undo",
            )
            for r in rows
            if r.source_troop_id is not None
        ]


class WriteExecutor:
    """Runs a bulk write with the §8 safety sequence. One instance per run."""

    def __init__(self, client: _ReadWrite, settings: Settings, sessionmaker: object) -> None:
        self._client = client
        self._settings = settings
        self._sm = sessionmaker

    # -- public API ---------------------------------------------------------

    def run(
        self,
        moves: list[IntendedMove],
        *,
        kind: str,
        cohort_year: int | None = None,
        parent_run_id: str | None = None,
        mode: RunMode = RunMode.DRY_RUN,
        now: datetime | None = None,
        run_id: str | None = None,
    ) -> RunResult:
        """
        Plan and (if ``mode`` is execute) perform a fresh run. Pass ``run_id`` to
        pre-allocate the id (so a background caller can return it and poll before
        the run finishes); otherwise one is generated.
        """
        now = now or datetime.now(UTC)
        self._check_allowlist(moves)
        memberlist = self._client.memberlist("active", fresh=True)
        preflight = drift_check(moves, memberlist)
        actionable = [p for p in preflight if p.category is Category.WILL_APPLY]

        if mode is RunMode.DRY_RUN:
            chunks = self._plan_chunks(actionable)
            return RunResult(RunMode.DRY_RUN, None, preflight, chunks, run_state="dry_run")

        run_id = run_id or str(uuid.uuid4())
        snapshot = write_snapshot(
            self._client, self._settings, self._sm, run_id=run_id, memberlist=memberlist, now=now
        )
        self._create_run(run_id, kind, cohort_year, snapshot.id, now, parent_run_id)
        chunk_items = _chunk(actionable, self._settings.chunk_size)
        self._write_journal(run_id, chunk_items)
        result = self._drive(run_id, list(enumerate(chunk_items)), now)
        # Surface the drift report and snapshot on the execute result too, so the
        # operator/UI can see what was excluded and which snapshot backs the run.
        result.preflight = preflight
        result.snapshot_id = snapshot.id
        return result

    def resume(self, run_id: str, *, now: datetime | None = None) -> RunResult:
        """
        Continue an interrupted/failed execute run from its journal (§8). Chunks
        already ``done`` are skipped; re-applying an applied change is a no-op.
        """
        now = now or datetime.now(UTC)
        rows = self._journal_rows(run_id)
        if not rows:
            raise ExecutorError(f"no journal for run {run_id!r}")
        pending: dict[int, list[PreflightItem]] = {}
        for chunk_id, member_no, target, source, state in rows:
            if state == "done":
                continue
            move = IntendedMove(member_no, source, target)
            pending.setdefault(chunk_id, []).append(
                PreflightItem(move, Category.WILL_APPLY, source, ACTIVE_STATUS_CODE)
            )
        self._set_run_state(run_id, "running")
        return self._drive(run_id, sorted(pending.items()), now)

    def undo(
        self,
        run_id: str,
        *,
        mode: RunMode = RunMode.DRY_RUN,
        now: datetime | None = None,
        new_run_id: str | None = None,
    ) -> RunResult:
        """
        Reverse a completed run (§8). An undo is itself a run — same snapshot,
        journal, chunking, dry-run-first, reconcile — with ``kind="undo"`` and
        ``parent_run_id`` set. The inverse is computed from *observed prior*
        state (the journal's ``source_troop_id``), and the pre-flight drift check
        excludes any member whose current placement no longer matches what this
        run set, so a later external edit is never overwritten.

        Only available while the run's snapshot is retained (§8).
        """
        if not undo_available(self._sm, run_id):
            raise ExecutorError(f"cannot undo run {run_id!r}: its snapshot is no longer retained")
        inverse = build_inverse_moves(self._sm, run_id)
        return self.run(
            inverse, kind="undo", parent_run_id=run_id, mode=mode, now=now, run_id=new_run_id
        )

    # -- internals ----------------------------------------------------------

    def _check_allowlist(self, moves: list[IntendedMove]) -> None:
        assert_allowlist(self._settings, moves)

    def _payload_for(self, items: list[PreflightItem], statuses: dict[str, str | None]) -> dict:
        """Build the update/membership body: status echoed back, troop_id moved (§8)."""
        payload = {}
        for item in items:
            token = write_status_token(statuses.get(item.move.member_no))
            payload[item.move.member_no] = {"status": token, "troop_id": item.move.target_troop_id}
        return payload

    def _plan_chunks(self, actionable: list[PreflightItem]) -> list[ChunkResult]:
        chunks: list[ChunkResult] = []
        for chunk_id, items in enumerate(_chunk(actionable, self._settings.chunk_size)):
            statuses = {i.move.member_no: i.current_status for i in items}
            payload = self._payload_for(items, statuses)
            chunks.append(
                ChunkResult(chunk_id, [i.move.member_no for i in items], payload, "planned")
            )
        return chunks

    def _drive(
        self, run_id: str, chunks: list[tuple[int, list[PreflightItem]]], now: datetime
    ) -> RunResult:
        """The serial chunk loop shared by fresh runs and resume."""
        results: list[ChunkResult] = []
        failed_chunk: int | None = None
        error: str | None = None
        all_items = [item for _, items in chunks for item in items]

        for position, (chunk_id, items) in enumerate(chunks):
            member_nos = [i.move.member_no for i in items]
            self._mark_chunk(run_id, chunk_id, "in_flight", bump=True)
            try:
                # Re-read status immediately before writing and echo it back (§8).
                live = self._client.memberlist("active", fresh=True).by_member_no()
                statuses = {
                    mno: (live[mno].status_code if mno in live else None) for mno in member_nos
                }
                payload = self._payload_for(items, statuses)
                self._client.update_membership(payload)
            except (*_WRITE_ERRORS, ExecutorError) as e:
                self._mark_chunk(run_id, chunk_id, "failed", error=str(e))
                self._set_run_state(run_id, "failed", finished_at=now)
                results.append(ChunkResult(chunk_id, member_nos, {}, "failed", str(e)))
                failed_chunk, error = chunk_id, str(e)
                break
            self._mark_chunk(run_id, chunk_id, "done")
            results.append(ChunkResult(chunk_id, member_nos, payload, "done"))
            if position < len(chunks) - 1:
                self._sleep(self._settings.chunk_delay_s)

        run_state = "failed" if failed_chunk is not None else "done"
        reconcile = None
        if failed_chunk is None:
            self._set_run_state(run_id, "done", finished_at=now)
            reconcile = self._reconcile(all_items)
        return RunResult(
            RunMode.EXECUTE,
            run_id,
            [],  # preflight already surfaced by run(); resume has none
            results,
            run_state=run_state,
            reconcile=reconcile,
            failed_chunk=failed_chunk,
            error=error,
            journal=self._journal_summary(run_id),
        )

    def _reconcile(self, items: list[PreflightItem]) -> dict:
        """Post-run: re-read (fresh) and confirm each member reached its target (§8)."""
        by_no = self._client.memberlist("active", fresh=True).by_member_no()
        applied, mismatch = 0, []
        for item in items:
            m = by_no.get(item.move.member_no)
            if m is not None and m.unit_troop_id == item.move.target_troop_id:
                applied += 1
            else:
                mismatch.append(item.move.member_no)
        return {"applied": applied, "mismatch": mismatch}

    def _sleep(self, seconds: float) -> None:
        # Isolated so the serial delay between chunks (§8) is trivial to skip in
        # tests (chunk_delay_s = 0). No concurrency anywhere — chunks are serial.
        if seconds > 0:
            import time

            time.sleep(seconds)

    # -- persistence --------------------------------------------------------

    def _create_run(
        self,
        run_id: str,
        kind: str,
        cohort_year: int | None,
        snapshot_id: str,
        now: datetime,
        parent_run_id: str | None = None,
    ) -> None:
        with get_session(self._sm) as s:
            s.add(
                WriteRun(
                    id=run_id,
                    kind=kind,
                    cohort_year=cohort_year,
                    parent_run_id=parent_run_id,
                    mode=RunMode.EXECUTE.value,
                    state="running",
                    snapshot_id=snapshot_id,
                    created_at=now.replace(tzinfo=None),
                )
            )

    def _write_journal(self, run_id: str, chunk_items: list[list[PreflightItem]]) -> None:
        with get_session(self._sm) as s:
            for chunk_id, items in enumerate(chunk_items):
                for item in items:
                    s.add(
                        WriteJournal(
                            run_id=run_id,
                            chunk_id=chunk_id,
                            member_no=item.move.member_no,
                            intended_status=write_status_token(item.current_status),
                            intended_troop_id=item.move.target_troop_id,
                            source_troop_id=item.current_troop_id,
                            state="pending",
                        )
                    )

    def _mark_chunk(
        self,
        run_id: str,
        chunk_id: int,
        state: str,
        *,
        error: str | None = None,
        bump: bool = False,
    ) -> None:
        values: dict = {"state": state}
        if error is not None:
            values["error"] = error
        if bump:
            values["attempts"] = WriteJournal.attempts + 1
        with get_session(self._sm) as s:
            s.execute(
                update(WriteJournal)
                .where(WriteJournal.run_id == run_id, WriteJournal.chunk_id == chunk_id)
                .values(**values)
            )

    def _set_run_state(
        self, run_id: str, state: str, *, finished_at: datetime | None = None
    ) -> None:
        values: dict = {"state": state}
        if finished_at is not None:
            values["finished_at"] = finished_at.replace(tzinfo=None)
        with get_session(self._sm) as s:
            s.execute(update(WriteRun).where(WriteRun.id == run_id).values(**values))

    def _journal_rows(self, run_id: str) -> list[tuple]:
        with get_session(self._sm) as s:
            rows = (
                s.execute(
                    select(WriteJournal)
                    .where(WriteJournal.run_id == run_id)
                    .order_by(WriteJournal.chunk_id, WriteJournal.id)
                )
                .scalars()
                .all()
            )
            return [
                (r.chunk_id, r.member_no, r.intended_troop_id, r.source_troop_id, r.state)
                for r in rows
            ]

    def _journal_summary(self, run_id: str) -> dict[str, int]:
        summary: dict[str, int] = {}
        for _cid, _mno, _t, _s, state in self._journal_rows(run_id):
            summary[state] = summary.get(state, 0) + 1
        return summary
