"""Gmail sender (§10). Service account, domain-wide delegation, scope gmail.send.

The Google libraries are imported lazily so the base install and the test suite
need neither them nor credentials. This class is never used in tests.
"""

from __future__ import annotations

import base64
from email.message import EmailMessage

from karverktyg.mail.base import MailMessage, MailSender

_SCOPE = "https://www.googleapis.com/auth/gmail.send"


class GmailMailSender(MailSender):
    def __init__(self, sending_address: str, credentials_file: str):
        # Sending mailbox must be inside the Workspace domain (§10).
        self._from = sending_address
        self._credentials_file = credentials_file

    def _service(self):  # pragma: no cover - requires the google extra + creds
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError as e:
            raise RuntimeError(
                "Gmail sending needs the 'google' extra: uv sync --extra google"
            ) from e
        creds = service_account.Credentials.from_service_account_file(
            self._credentials_file, scopes=[_SCOPE], subject=self._from
        )
        return build("gmail", "v1", credentials=creds, cache_discovery=False)

    def send(self, message: MailMessage) -> None:  # pragma: no cover
        mime = EmailMessage()
        mime["To"] = ", ".join(message.to)
        mime["From"] = self._from
        mime["Subject"] = message.subject
        mime.set_content(message.body_text)
        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
        self._service().users().messages().send(userId="me", body={"raw": raw}).execute()
