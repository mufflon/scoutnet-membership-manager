"""
Write-side machinery (Phase 2, CLAUDE.md §8).

Currently: the pre-run snapshot writer and the write executor (dry-run + execute,
serial chunk loop, journal, resume). Undo and the Flask/UI wiring land in later
steps.
"""

from karverktyg.write.executor import (
    ACTIVE_STATUS_CODE,
    AllowlistViolation,
    Category,
    ChunkResult,
    ExecutorError,
    IntendedMove,
    PreflightItem,
    RunMode,
    RunResult,
    WriteExecutor,
    assert_allowlist,
    build_inverse_moves,
    drift_check,
    undo_available,
    write_status_token,
)
from karverktyg.write.snapshot import (
    SnapshotError,
    SnapshotInfo,
    build_snapshot_payload,
    delete_snapshot,
    list_snapshots,
    purge_snapshots,
    write_snapshot,
)

__all__ = [
    "ACTIVE_STATUS_CODE",
    "AllowlistViolation",
    "Category",
    "ChunkResult",
    "ExecutorError",
    "IntendedMove",
    "PreflightItem",
    "RunMode",
    "RunResult",
    "SnapshotError",
    "SnapshotInfo",
    "WriteExecutor",
    "assert_allowlist",
    "build_inverse_moves",
    "build_snapshot_payload",
    "delete_snapshot",
    "drift_check",
    "list_snapshots",
    "purge_snapshots",
    "undo_available",
    "write_snapshot",
    "write_status_token",
]
