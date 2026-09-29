"""Email delivery abstraction.

Every send is recorded in the `email_outbox` table (audit + dev inbox). The
`console` provider (default) only records + logs, so all flows — verification,
reset, notifications — are real and testable without external credentials.
`smtp` delivers via any standard SMTP server (Gmail with an App Password,
Office 365, a transactional provider's SMTP endpoint, etc.). `brevo` delivers
via Brevo's transactional HTTP API — preferred in production because it works
on hosts that throttle or block outbound SMTP ports. Delivery failures are
logged and never raised, so a slow/down mail provider can never break
registration or password-reset.
"""
import base64
import logging
import smtplib
import socket
import threading
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr
from typing import NamedTuple

import httpx
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.modules.auth.models import EmailOutbox

logger = logging.getLogger("crm.email")


class Attachment(NamedTuple):
    filename: str
    content: bytes
    mimetype: str = "application/octet-stream"


class _IPv4SMTP(smtplib.SMTP):
    """Many containerized hosts (Render, etc.) have no IPv6 route, which
    makes stdlib smtplib fail with "Network is unreachable" whenever DNS
    returns an AAAA record before the A record — the default connect logic
    tries IPv6 first and never falls back. Forcing AF_INET here sidesteps
    that entirely; the hostname (for TLS SNI/cert checks) is untouched."""

    def _get_socket(self, host, port, timeout):
        family, socktype, proto, _, sockaddr = socket.getaddrinfo(
            host, port, socket.AF_INET, socket.SOCK_STREAM
        )[0]
        sock = socket.socket(family, socktype, proto)
        if timeout is not None:
            sock.settimeout(timeout)
        sock.connect(sockaddr)
        return sock


def _provider_ready(settings: Settings) -> bool:
    if settings.email_provider == "smtp":
        return bool(settings.smtp_host)
    if settings.email_provider == "brevo":
        return bool(settings.brevo_api_key)
    return False


def send_email(
    db: Session,
    *,
    to: str,
    subject: str,
    body: str,
    category: str,
    attachment: Attachment | None = None,
) -> None:
    settings = get_settings()
    delivered = False

    if settings.email_provider == "console":
        logger.info(
            "EMAIL [%s] to=%s subject=%s attachment=%s\n%s",
            category, to, subject, attachment.filename if attachment else None, body,
        )
        delivered = True
    elif not _provider_ready(settings):
        logger.warning(
            "EMAIL_PROVIDER=%s but required credentials are missing — "
            "email NOT sent for [%s] to=%s", settings.email_provider, category, to,
        )
    else:
        # Real delivery is a live network round-trip (1-3s) — never block the
        # request on it. The daemon thread delivers and records the outbox row
        # with its own session; the caller's transaction is untouched. The
        # console path stays synchronous so dev/test outbox reads are
        # deterministic.
        threading.Thread(
            target=_deliver_and_record,
            args=(settings, to, subject, body, category, attachment),
            daemon=True,
        ).start()
        return

    db.add(
        EmailOutbox(to_email=to, subject=subject, body=body, category=category, sent=delivered)
    )


def _deliver_and_record(
    settings: Settings, to: str, subject: str, body: str, category: str,
    attachment: Attachment | None,
) -> None:
    from app.db.base import SessionLocal

    delivered = False
    try:
        if settings.email_provider == "brevo":
            _send_via_brevo(settings, to=to, subject=subject, body=body, attachment=attachment)
        else:
            _send_via_smtp(settings, to=to, subject=subject, body=body, attachment=attachment)
        delivered = True
    except Exception as exc:  # delivery must never break anything upstream
        logger.error(
            "%s delivery failed [%s] to=%s: %s", settings.email_provider, category, to, exc
        )
    try:
        with SessionLocal() as db:
            db.add(EmailOutbox(
                to_email=to, subject=subject, body=body, category=category, sent=delivered,
            ))
            db.commit()
    except Exception:
        logger.exception("failed to record email_outbox row for [%s] to=%s", category, to)


def _send_via_smtp(
    settings: Settings, *, to: str, subject: str, body: str, attachment: Attachment | None
) -> None:
    if attachment:
        msg = MIMEMultipart()
        msg.attach(MIMEText(body, "plain", "utf-8"))
        part = MIMEApplication(attachment.content, Name=attachment.filename)
        part["Content-Disposition"] = f'attachment; filename="{attachment.filename}"'
        msg.attach(part)
    else:
        msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = settings.email_from
    msg["To"] = to

    with _IPv4SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_username and settings.smtp_password:
            server.login(settings.smtp_username, settings.smtp_password)
        server.sendmail(settings.email_from, [to], msg.as_string())
    logger.info("SMTP delivered to=%s subject=%s", to, subject)


def _send_via_brevo(
    settings: Settings, *, to: str, subject: str, body: str, attachment: Attachment | None
) -> None:
    sender_name, sender_email = parseaddr(settings.email_from)
    payload: dict = {
        "sender": {"email": sender_email, **({"name": sender_name} if sender_name else {})},
        "to": [{"email": to}],
        "subject": subject,
        "textContent": body,
    }
    if attachment:
        payload["attachment"] = [{
            "name": attachment.filename,
            "content": base64.b64encode(attachment.content).decode("ascii"),
        }]
    resp = httpx.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={"api-key": settings.brevo_api_key, "accept": "application/json"},
        json=payload,
        timeout=10,
    )
    resp.raise_for_status()
    logger.info("Brevo delivered to=%s subject=%s", to, subject)
