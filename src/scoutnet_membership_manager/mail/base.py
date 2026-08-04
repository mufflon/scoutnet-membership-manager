"""Mail sender interface and the recording fake (§10)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class MailMessage:
    """One outgoing email: recipients, subject, plain-text body."""

    to: list[str]
    subject: str
    body_text: str


class MailSender(ABC):
    """Interface for sending mail. Implementations: Gmail and a recording fake."""

    @abstractmethod
    def send(self, message: MailMessage) -> None:
        """Send one message. Raises on failure."""


class RecordingMailSender(MailSender):
    """
    Records messages instead of sending. Used in development and tests so the
    suite can never send real mail.
    """

    def __init__(self) -> None:
        self.sent: list[MailMessage] = []

    def send(self, message: MailMessage) -> None:
        """Record the message instead of sending it."""
        self.sent.append(message)
