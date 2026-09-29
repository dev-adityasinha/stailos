"""WhatsApp delivery abstraction — mirrors core/email.py exactly.

Every send is recorded in the `whatsapp_outbox` table (audit + dev inbox).
The `console` provider (default) only records + logs, so registration
confirmations/reminders are real and testable without external credentials.
`meta_cloud` delivers via the WhatsApp Cloud API (Meta's official Business
API — free tier, 1000 user-initiated conversations/month), once the tenant
has a WhatsApp Business phone number and access token configured. Delivery
failures are logged and never raised, matching send_email's contract.
"""
import logging

import httpx
from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

logger = logging.getLogger("crm.whatsapp")

GRAPH_API_BASE = "https://graph.facebook.com/v20.0"


class WhatsAppOutbox(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Development mailbox: every outbound WhatsApp message is persisted
    here, same shape/purpose as auth.models.EmailOutbox."""

    __tablename__ = "whatsapp_outbox"

    to_phone: Mapped[str] = mapped_column(String(20), index=True)
    body: Mapped[str] = mapped_column(String(2000))
    category: Mapped[str] = mapped_column(String(50), index=True)
    sent: Mapped[bool] = mapped_column(Boolean, default=False)


def send_whatsapp(db: Session, *, to_phone: str, body: str, category: str) -> None:
    settings = get_settings()
    delivered = False

    if settings.whatsapp_provider == "console":
        logger.info("WHATSAPP [%s] to=%s\n%s", category, to_phone, body)
        delivered = True
    elif not (settings.whatsapp_phone_number_id and settings.whatsapp_access_token):
        logger.warning(
            "WHATSAPP_PROVIDER=%s but phone_number_id/access_token are missing — "
            "message NOT sent for [%s] to=%s", settings.whatsapp_provider, category, to_phone,
        )
    else:
        try:
            _send_via_meta_cloud(
                phone_number_id=settings.whatsapp_phone_number_id,
                access_token=settings.whatsapp_access_token,
                to_phone=to_phone, body=body,
            )
            delivered = True
        except Exception as exc:  # delivery must never break the caller's flow
            logger.error("WhatsApp delivery failed [%s] to=%s: %s", category, to_phone, exc)

    db.add(WhatsAppOutbox(to_phone=to_phone, body=body, category=category, sent=delivered))


def _send_via_meta_cloud(*, phone_number_id: str, access_token: str, to_phone: str, body: str) -> None:
    resp = httpx.post(
        f"{GRAPH_API_BASE}/{phone_number_id}/messages",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "messaging_product": "whatsapp",
            "to": to_phone.lstrip("+"),
            "type": "text",
            "text": {"body": body},
        },
        timeout=10.0,
    )
    resp.raise_for_status()
    logger.info("WhatsApp Cloud API delivered to=%s", to_phone)
