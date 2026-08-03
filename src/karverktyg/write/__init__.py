"""
Write-side machinery (Phase 2, CLAUDE.md §8).

Currently: the pre-run snapshot writer. The executor, chunk loop and undo land
in later steps. Nothing here issues a write to Scoutnet — the snapshot is a
read plus a local file.
"""

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
    "SnapshotError",
    "SnapshotInfo",
    "build_snapshot_payload",
    "delete_snapshot",
    "list_snapshots",
    "purge_snapshots",
    "write_snapshot",
]
