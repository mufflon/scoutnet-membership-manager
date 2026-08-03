from __future__ import annotations

from sqlalchemy import create_engine

from karverktyg.db import Base, make_sessionmaker
from karverktyg.db.session import get_session
from karverktyg.mail import (
    MailMessage,
    MailSender,
    RecordingMailSender,
    resolve_recipients,
    send_once,
)
from karverktyg.scoutnet.models import Member


def _member(**emails):
    m = Member(member_no="1")
    m.emails = emails
    return m


def test_recipients_both_guardians_deduped():
    m = _member(contact_email_dad="Far@Ex.se", contact_email_mum="mor@ex.se")
    assert set(resolve_recipients(m)) == {"Far@Ex.se", "mor@ex.se"}
    # shared family address, different case -> one recipient
    m2 = _member(contact_email_dad="Fam@ex.se", contact_email_mum="fam@EX.se")
    assert len(resolve_recipients(m2)) == 1


def test_recipients_fallback_and_unsendable():
    assert resolve_recipients(_member(contact_email="me@ex.se")) == ["me@ex.se"]
    assert resolve_recipients(_member(email="own@ex.se")) == ["own@ex.se"]
    assert resolve_recipients(_member()) == []  # unsendable -> caller surfaces


def test_recording_sender_is_inert():
    sender = RecordingMailSender()
    assert isinstance(sender, MailSender)
    sender.send(MailMessage(to=["a@b.se"], subject="s", body_text="b"))
    assert len(sender.sent) == 1


def test_send_once_is_idempotent():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = make_sessionmaker(engine)
    sender = RecordingMailSender()
    msg = MailMessage(to=["a@b.se"], subject="s", body_text="b")

    with get_session(factory) as s:
        assert send_once(sender, s, "100", "reminder", msg) is True
    with get_session(factory) as s:
        assert send_once(sender, s, "100", "reminder", msg) is False  # duplicate
    assert len(sender.sent) == 1  # sent exactly once
