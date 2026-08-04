"""
Email via the Gmail API (CLAUDE.md §10).

Two MailSender implementations: Gmail (service account, domain-wide delegation,
scope gmail.send only) and a recording fake used in development and tests.
Nothing in the test suite can send real mail. Sending is idempotent — the
message log is checked before and written after (§9, §10).
"""

from scoutnet_membership_manager.mail.base import MailMessage, MailSender, RecordingMailSender
from scoutnet_membership_manager.mail.recipients import resolve_recipients
from scoutnet_membership_manager.mail.service import already_sent, send_once

__all__ = [
    "MailMessage",
    "MailSender",
    "RecordingMailSender",
    "already_sent",
    "resolve_recipients",
    "send_once",
]
