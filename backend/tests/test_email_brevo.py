"""Unit tests for the Brevo email provider (HTTP API payload + failure safety)."""
from unittest.mock import MagicMock, patch

from app.core.config import Settings
from app.core.email import Attachment, _provider_ready, _send_via_brevo


def _settings(**overrides) -> Settings:
    base = dict(
        email_provider="brevo",
        brevo_api_key="test-key",
        email_from="Pappu AI CRM <noreply@example.com>",
    )
    base.update(overrides)
    return Settings(**base)


def test_provider_ready_requires_api_key():
    assert _provider_ready(_settings())
    assert not _provider_ready(_settings(brevo_api_key=None))


def test_send_via_brevo_builds_expected_payload():
    with patch("app.core.email.httpx.post") as post:
        post.return_value = MagicMock(status_code=201)
        _send_via_brevo(
            _settings(),
            to="user@example.com",
            subject="Hello",
            body="Body text",
            attachment=None,
        )

    (url,), kwargs = post.call_args
    assert url == "https://api.brevo.com/v3/smtp/email"
    assert kwargs["headers"]["api-key"] == "test-key"
    payload = kwargs["json"]
    assert payload["sender"] == {"email": "noreply@example.com", "name": "Pappu AI CRM"}
    assert payload["to"] == [{"email": "user@example.com"}]
    assert payload["subject"] == "Hello"
    assert payload["textContent"] == "Body text"
    assert "attachment" not in payload


def test_send_via_brevo_encodes_attachment_as_base64():
    with patch("app.core.email.httpx.post") as post:
        post.return_value = MagicMock(status_code=201)
        _send_via_brevo(
            _settings(),
            to="user@example.com",
            subject="Invite",
            body="See attached",
            attachment=Attachment(filename="event.ics", content=b"BEGIN:VCALENDAR"),
        )

    payload = post.call_args.kwargs["json"]
    assert payload["attachment"] == [
        {"name": "event.ics", "content": "QkVHSU46VkNBTEVOREFS"}
    ]


def test_deliver_and_record_survives_brevo_failure():
    """A Brevo outage must log the failure and record sent=False, never raise."""
    from app.core.email import _deliver_and_record

    with patch("app.core.email.httpx.post", side_effect=RuntimeError("brevo down")), \
         patch("app.db.base.SessionLocal") as session_cls:
        session = session_cls.return_value.__enter__.return_value
        _deliver_and_record(
            _settings(), "user@example.com", "Subj", "Body", "verification", None
        )

    outbox_row = session.add.call_args.args[0]
    assert outbox_row.sent is False
    session.commit.assert_called_once()
