"""Idempotent send (§10). Check the message log before, write it after."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from karverktyg.db.models import MessageLog
from karverktyg.mail.base import MailMessage, MailSender


def already_sent(session: Session, member_no: str, message_type: str) -> bool:
    """Already sent."""
    stmt = select(MessageLog.id).where(
        MessageLog.member_no == member_no,
        MessageLog.message_type == message_type,
    )
    return session.execute(stmt).first() is not None


def send_once(
    sender: MailSender,
    session: Session,
    member_no: str,
    message_type: str,
    message: MailMessage,
) -> bool:
    """
    Send unless this (member, message_type) was already sent. Returns True if
    sent now, False if skipped as a duplicate.
    """
    if already_sent(session, member_no, message_type):
        return False
    sender.send(message)
    session.add(MessageLog(member_no=member_no, message_type=message_type))
    session.flush()
    return True
