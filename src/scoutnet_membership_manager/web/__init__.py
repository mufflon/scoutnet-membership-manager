"""
Flask HTTP service and static frontend (CLAUDE.md §3).

The frontend talks only to this API, never to Scoutnet, Postgres or Google. The
app is read-only in Phase 1; there is no write endpoint.
"""

from scoutnet_membership_manager.web.app import create_app

__all__ = ["create_app"]
