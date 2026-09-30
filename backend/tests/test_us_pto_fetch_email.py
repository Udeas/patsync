"""Unparseable emails must be left unread (not silently discarded) so they
can be retried on the next fetch; only successfully-parsed emails get
marked \\Seen."""

from unittest.mock import MagicMock, patch

from app.us_pto.steps import fetch_email

PARSEABLE_HTML = b"""
<html><body>
<table>
<tr><td>OFFICE ACTION EMAIL DETAILS</td></tr>
<tr><td>Application Number:</td><td>12345678</td></tr>
<tr><td>Attorney Docket No.:</td><td>ABC-P001</td></tr>
<tr><td>Client:</td><td>Acme</td></tr>
<tr><td>Code</td><td>Description</td><td>Mailroom Date</td></tr>
<tr><td>CTNF</td><td>Non-Final Rejection</td><td>08/28/2026</td></tr>
</table>
</body></html>
"""

UNPARSEABLE_HTML = b"<html><body><p>Some unrelated newsletter content.</p></body></html>"


def _make_raw_message(html_bytes: bytes) -> list:
    msg = (
        b'1 (RFC822 {1})',
        b"Subject: Test Email\r\nContent-Type: text/html\r\n\r\n" + html_bytes,
    )
    return [msg]


@patch("app.us_pto.steps.fetch_email.imaplib.IMAP4_SSL")
def test_unparseable_email_left_unread_parseable_marked_seen(mock_imap_cls, monkeypatch):
    monkeypatch.setattr(fetch_email, "IMAP_USERNAME", "user@example.com")
    monkeypatch.setattr(fetch_email, "IMAP_PASSWORD", "secret")

    mock_imap = MagicMock()
    mock_imap_cls.return_value = mock_imap
    mock_imap.select.return_value = ("OK", [b""])
    mock_imap.search.return_value = ("OK", [b"1 2"])

    def fetch_side_effect(mid, spec):
        if mid == "1":
            return "OK", _make_raw_message(PARSEABLE_HTML)
        return "OK", _make_raw_message(UNPARSEABLE_HTML)

    mock_imap.fetch.side_effect = fetch_side_effect
    mock_imap.store.return_value = ("OK", [b""])

    rows, unparsed_count = fetch_email.fetch_emails()

    assert len(rows) == 1
    assert unparsed_count == 1
    mock_imap.store.assert_called_once_with("1", "+FLAGS", "\\Seen")


@patch("app.us_pto.steps.fetch_email.imaplib.IMAP4_SSL")
def test_no_unseen_messages_returns_zero_unparsed(mock_imap_cls, monkeypatch):
    monkeypatch.setattr(fetch_email, "IMAP_USERNAME", "user@example.com")
    monkeypatch.setattr(fetch_email, "IMAP_PASSWORD", "secret")

    mock_imap = MagicMock()
    mock_imap_cls.return_value = mock_imap
    mock_imap.select.return_value = ("OK", [b""])
    mock_imap.search.return_value = ("OK", [b""])

    rows, unparsed_count = fetch_email.fetch_emails()

    assert rows == []
    assert unparsed_count == 0
    mock_imap.store.assert_not_called()
