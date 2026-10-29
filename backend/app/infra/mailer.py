"""Mailer adapters."""

import logging
import smtplib
from email.message import EmailMessage

log = logging.getLogger(__name__)


class SmtpMailer:
    def __init__(self, host: str, port: int, sender: str, user: str | None = None, password: str | None = None):
        self.host, self.port, self.sender, self.user, self.password = host, port, sender, user, password

    def send(self, *, to: str, subject: str, text: str) -> None:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.sender, to, subject
        msg.set_content(text)
        with smtplib.SMTP(self.host, self.port, timeout=15) as smtp:
            if self.user:
                smtp.starttls()
                smtp.login(self.user, self.password or "")
            smtp.send_message(msg)


class ConsoleMailer:
    """Logs emails instead of sending them (development without an SMTP server)."""

    def __init__(self) -> None:
        self.outbox: list[dict] = []

    def send(self, *, to: str, subject: str, text: str) -> None:
        self.outbox.append({"to": to, "subject": subject, "text": text})
        log.info("EMAIL to=%s subject=%s\n%s", to, subject, text)
